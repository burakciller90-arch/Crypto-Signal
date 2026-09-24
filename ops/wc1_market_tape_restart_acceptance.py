from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from crypto_signal.data.market_data_gap_ledger import (
    GapEventKind,
    MarketDataGapLedger,
)
from crypto_signal.data.market_tape_collector_runtime import (
    CollectorStartKind,
    MarketTapeCollectorInstance,
    MarketTapeCollectorRuntimeStore,
)

REAL_CAPITAL = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bounded WC1 Market Tape collector restart acceptance."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/Volumes/Crypto-504/Crypto-Signal"),
    )
    parser.add_argument("--ready-timeout-seconds", type=int, default=420)
    parser.add_argument("--restart-timeout-seconds", type=int, default=420)
    parser.add_argument("--product-timeout-seconds", type=int, default=180)
    return parser.parse_args()


def _require_canonical_root(root: Path) -> None:
    expected = Path("/Volumes/Crypto-504/Crypto-Signal")
    if root.resolve() != expected.resolve():
        raise RuntimeError(f"WC1 canonical root mismatch: {root}")


def _lock_holder(lock_path: Path) -> int | None:
    result = subprocess.run(
        ["/usr/sbin/lsof", "-t", str(lock_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    for raw in result.stdout.splitlines():
        value = raw.strip()
        if value.isdigit():
            return int(value)
    return None


def _parse_process_identity(raw: str) -> tuple[int | None, tuple[str, ...]]:
    line = raw.strip()
    if not line:
        return None, ()
    parts = line.split()
    if len(parts) < 2 or not parts[0].isdigit():
        return None, ()
    return int(parts[0]), tuple(parts[1:])


def _process_identity(pid: int) -> tuple[int | None, tuple[str, ...]]:
    result = subprocess.run(
        ["/bin/ps", "-ww", "-p", str(pid), "-o", "uid=,args="],
        check=False,
        capture_output=True,
        text=True,
    )
    return _parse_process_identity(result.stdout)


def _is_expected_collector(pid: int, runner: Path) -> bool:
    uid, argv = _process_identity(pid)
    expected_python = runner.parent.parent / ".venv" / "bin" / "python"
    return (
        uid == 504
        and len(argv) >= 2
        and argv[0] == str(expected_python)
        and argv[1] == str(runner)
    )


def _wait_for_initial_state(
    *,
    runtime_store: MarketTapeCollectorRuntimeStore,
    gap_ledger: MarketDataGapLedger,
    lock_path: Path,
    runner: Path,
    timeout_seconds: int,
) -> tuple[int, MarketTapeCollectorInstance]:
    deadline = time.monotonic() + timeout_seconds
    last_reason = "not_started"
    while time.monotonic() < deadline:
        pid = _lock_holder(lock_path)
        if pid is None:
            last_reason = "lock_holder_missing"
            time.sleep(2)
            continue
        if not _is_expected_collector(pid, runner):
            last_reason = f"unexpected_lock_holder_pid={pid}"
            time.sleep(2)
            continue
        try:
            instance = runtime_store.latest_instance(
                provider="bybit",
                source="market_tape_stream",
            )
            gap_ok = gap_ledger.quick_check()
        except (OSError, ValueError, sqlite3.Error) as exc:
            last_reason = f"state_not_readable:{type(exc).__name__}:{exc}"
            time.sleep(2)
            continue
        if instance is None:
            last_reason = "collector_instance_missing"
            time.sleep(2)
            continue
        heartbeat = runtime_store.latest_heartbeat(instance.instance_identity)
        if heartbeat is None:
            last_reason = "collector_heartbeat_missing"
            time.sleep(2)
            continue
        if not gap_ok:
            last_reason = "gap_ledger_quick_check_failed"
            time.sleep(2)
            continue
        return pid, instance
    raise RuntimeError(f"WC1 initial collector state timeout: {last_reason}")


def _wait_for_restart(
    *,
    old_pid: int,
    old_instance: MarketTapeCollectorInstance,
    runtime_store: MarketTapeCollectorRuntimeStore,
    gap_ledger: MarketDataGapLedger,
    lock_path: Path,
    runner: Path,
    timeout_seconds: int,
) -> tuple[int, MarketTapeCollectorInstance]:
    deadline = time.monotonic() + timeout_seconds
    last_reason = "restart_not_started"
    while time.monotonic() < deadline:
        pid = _lock_holder(lock_path)
        if pid is None or pid == old_pid:
            last_reason = "new_lock_holder_not_ready"
            time.sleep(2)
            continue
        if not _is_expected_collector(pid, runner):
            last_reason = f"unexpected_new_lock_holder_pid={pid}"
            time.sleep(2)
            continue
        instance = runtime_store.latest_instance(
            provider="bybit",
            source="market_tape_stream",
        )
        if instance is None or instance.instance_identity == old_instance.instance_identity:
            last_reason = "new_collector_instance_not_persisted"
            time.sleep(2)
            continue
        if instance.start_kind is not CollectorStartKind.RESTART:
            raise RuntimeError(
                "WC1 restarted collector did not persist RESTART start kind"
            )
        if instance.previous_instance_identity != old_instance.instance_identity:
            raise RuntimeError(
                "WC1 restarted collector predecessor identity mismatch"
            )
        heartbeat = runtime_store.latest_heartbeat(instance.instance_identity)
        if heartbeat is None:
            last_reason = "new_collector_heartbeat_not_persisted"
            time.sleep(2)
            continue
        if not gap_ledger.quick_check():
            raise RuntimeError("WC1 gap ledger quick_check failed after restart")
        return pid, instance
    raise RuntimeError(f"WC1 collector restart timeout: {last_reason}")


def _verify_gap_chain(gap_ledger: MarketDataGapLedger) -> tuple[int, int]:
    events = gap_ledger.events()
    latest: dict[str, str] = {}
    terminal: set[str] = set()
    for event in events:
        expected = latest.get(event.gap_identity)
        if expected is None:
            if event.event_kind is not GapEventKind.OBSERVED:
                raise RuntimeError("WC1 gap chain begins without OBSERVED root")
            if event.previous_event_identity is not None:
                raise RuntimeError("WC1 gap root carries predecessor")
        else:
            if event.previous_event_identity != expected:
                raise RuntimeError("WC1 gap predecessor chain mismatch")
            if event.gap_identity in terminal:
                raise RuntimeError("WC1 gap event appended after terminal state")
        latest[event.gap_identity] = event.event_identity
        if event.event_kind in {GapEventKind.RECOVERED, GapEventKind.UNRECOVERED}:
            terminal.add(event.gap_identity)
        if event.production_authority or event.real_capital != REAL_CAPITAL:
            raise RuntimeError("WC1 gap evidence authority mismatch")
    return len(events), len(latest)


def _read_product_truth(timeout_seconds: int) -> dict[str, Any]:
    with urllib.request.urlopen(
        "http://127.0.0.1:48700/api/market-tape-runtime/status",
        timeout=timeout_seconds,
    ) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise TypeError("WC1 Product Market Tape payload is not an object")
    return body


def main() -> int:
    args = _parse_args()
    _require_canonical_root(args.root)
    development = args.root / "Development"
    runtime = development / "runtime" / "market_tape"
    runner = development / "ops" / "run_market_tape_stream.py"
    lock_path = runtime / "market_tape_stream.lock"
    runtime_db = runtime / "collector_runtime.sqlite3"
    gap_db = runtime / "market_data_gaps.sqlite3"

    for required in (development, runner, runtime / "market_tape.sqlite3", runtime / "raw_market_tape.sqlite3"):
        if not required.exists():
            raise RuntimeError(f"WC1 required runtime path missing: {required}")

    runtime_store = MarketTapeCollectorRuntimeStore(runtime_db)
    gap_ledger = MarketDataGapLedger(gap_db)

    old_pid, old_instance = _wait_for_initial_state(
        runtime_store=runtime_store,
        gap_ledger=gap_ledger,
        lock_path=lock_path,
        runner=runner,
        timeout_seconds=args.ready_timeout_seconds,
    )
    old_heartbeat = runtime_store.latest_heartbeat(old_instance.instance_identity)
    if old_heartbeat is None:
        raise RuntimeError("WC1 initial heartbeat disappeared")
    if old_instance.production_authority or old_instance.real_capital != REAL_CAPITAL:
        raise RuntimeError("WC1 initial collector authority mismatch")

    print(
        "WC1_RESTART_DRILL_BEFORE "
        f"pid={old_pid} instance={old_instance.instance_identity} "
        f"start_kind={old_instance.start_kind.value} "
        f"heartbeat_seq={old_heartbeat.sequence_no}",
        flush=True,
    )

    os.kill(old_pid, signal.SIGTERM)

    new_pid, new_instance = _wait_for_restart(
        old_pid=old_pid,
        old_instance=old_instance,
        runtime_store=runtime_store,
        gap_ledger=gap_ledger,
        lock_path=lock_path,
        runner=runner,
        timeout_seconds=args.restart_timeout_seconds,
    )
    new_heartbeat = runtime_store.latest_heartbeat(new_instance.instance_identity)
    if new_heartbeat is None:
        raise RuntimeError("WC1 restarted heartbeat disappeared")
    if new_instance.production_authority or new_instance.real_capital != REAL_CAPITAL:
        raise RuntimeError("WC1 restarted collector authority mismatch")

    gap_event_count, gap_count = _verify_gap_chain(gap_ledger)

    product = _read_product_truth(args.product_timeout_seconds)
    if product.get("status") != "ready":
        raise RuntimeError("WC1 Product Market Tape status is not ready")
    if product.get("online_status") != "NOT_ASSERTED":
        raise RuntimeError("WC1 Product must not infer Market Tape ONLINE")
    if product.get("read_only") is not True or product.get("real_capital") != 0:
        raise RuntimeError("WC1 Product authority/read-only boundary mismatch")
    collector = product.get("collector_runtime")
    if not isinstance(collector, dict):
        raise TypeError("WC1 Product collector runtime evidence missing")
    if collector.get("instance_identity") != new_instance.instance_identity:
        raise RuntimeError("WC1 Product collector instance identity mismatch")
    if collector.get("process_evidence_status") != "HEARTBEAT_FRESH":
        raise RuntimeError("WC1 Product collector heartbeat is not fresh")

    print(
        "WC1_RESTART_DRILL_AFTER "
        f"pid={new_pid} instance={new_instance.instance_identity} "
        f"previous={new_instance.previous_instance_identity} "
        f"heartbeat_seq={new_heartbeat.sequence_no} "
        f"gap_events={gap_event_count} gaps={gap_count}",
        flush=True,
    )
    print("WC1_MARKET_TAPE_RESTART_LINEAGE_PASS=YES", flush=True)
    print("WC1_MARKET_TAPE_GAP_CHAIN_PASS=YES", flush=True)
    print("WC1_MARKET_TAPE_PRODUCT_TRUTH_PASS=YES", flush=True)
    print("WC1_MARKET_TAPE_ONLINE_NOT_ASSERTED_PASS=YES", flush=True)
    print("WC1_MARKET_TAPE_RESTART_DRILL_PASS=YES", flush=True)
    print("REAL_CAPITAL=0", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
