"""Read-only Full Version integrated acceptance v2 verifier."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

REAL_CAPITAL = 0
FORBIDDEN_API_TOKENS = (
    "order",
    "broker",
    "credential",
    "api-key",
    "api_key",
    "secret",
    "execute",
    "write-authority",
)


def _get_json(base_url: str, path: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        headers={"Cache-Control": "no-store"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} did not return a JSON object")
    return payload


def _get_text(base_url: str, path: str = "/") -> str:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        headers={"Cache-Control": "no-store"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        body = response.read()
    if not isinstance(body, bytes):
        raise TypeError(f"{path} did not return bytes")
    return body.decode("utf-8")


def verify_openapi(spec: dict[str, Any]) -> None:
    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise RuntimeError("OpenAPI paths missing")
    for path, operations in paths.items():
        if not str(path).startswith("/api/"):
            continue
        if not isinstance(operations, dict):
            raise TypeError(f"invalid OpenAPI operations for {path}")
        methods = {str(method).lower() for method in operations}
        if methods != {"get"}:
            raise RuntimeError(
                f"non-read-only API surface: {path} methods={sorted(methods)}"
            )
        lowered = str(path).lower()
        if any(token in lowered for token in FORBIDDEN_API_TOKENS):
            raise RuntimeError(f"forbidden API authority token: {path}")


def verify_health(payload: dict[str, Any]) -> None:
    if payload.get("status") != "ok":
        raise RuntimeError("health status is not ok")
    if payload.get("read_only") is not True:
        raise RuntimeError("health is not read-only")
    if payload.get("real_capital") != REAL_CAPITAL:
        raise RuntimeError("health REAL_CAPITAL is not 0")
    if payload.get("ledger_present") is not True:
        raise RuntimeError("signal ledger missing")
    if payload.get("alert_outbox_present") is not True:
        raise RuntimeError("alert outbox missing")


def verify_intelligence(payload: dict[str, Any]) -> None:
    if payload.get("status") != "ready":
        raise RuntimeError("Intelligence Center is not ready")
    if payload.get("read_only") is not True:
        raise RuntimeError("Intelligence Center is not read-only")
    if payload.get("real_capital") != REAL_CAPITAL:
        raise RuntimeError("Intelligence Center REAL_CAPITAL is not 0")
    if payload.get("production_active_engine_count") != 0:
        raise RuntimeError("research engine production contribution is active")
    if payload.get("probability_status") != "not_calibrated":
        raise RuntimeError("research surface claims calibrated probability")
    count = payload.get("accepted_engine_count")
    if not isinstance(count, int) or count < 21:
        raise RuntimeError("accepted research catalog is incomplete")
    engines = payload.get("engines")
    if not isinstance(engines, list) or len(engines) != count:
        raise RuntimeError("research catalog count mismatch")
    for engine in engines:
        if not isinstance(engine, dict):
            raise TypeError("invalid Intelligence Center engine")
        if engine.get("production_contribution") != 0:
            raise RuntimeError("research catalog contribution is not zero")
        if engine.get("production_authority") is not False:
            raise RuntimeError("research catalog production authority is open")


def verify_paper_mission(payload: dict[str, Any]) -> None:
    if payload.get("status") != "ready":
        raise RuntimeError("paper Mission Control is not ready")
    if payload.get("read_only") is not True:
        raise RuntimeError("paper Mission Control is not read-only")
    if payload.get("real_capital") != REAL_CAPITAL:
        raise RuntimeError("paper REAL_CAPITAL is not 0")
    if payload.get("trade_policy") != "NOT_ACTIVATED":
        raise RuntimeError("paper write gate is not closed")
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        raise TypeError("paper snapshot missing")
    if snapshot.get("trade_policy") != "NOT_ACTIVATED":
        raise RuntimeError("paper snapshot write gate is not closed")
    if snapshot.get("real_capital") != REAL_CAPITAL:
        raise RuntimeError("paper snapshot REAL_CAPITAL is not 0")
    benchmarks = snapshot.get("benchmarks")
    if not isinstance(benchmarks, dict):
        raise TypeError("paper benchmarks missing")
    results = benchmarks.get("results")
    if not isinstance(results, list) or len(results) != 3:
        raise RuntimeError("paper benchmark coverage mismatch")


def verify_shell(html: str) -> None:
    for marker in (
        "GIFT EDITION · SADE BAŞLANGIÇ",
        'id="viewModeToggle"',
        "KISACA",
        'id="intelligenceSection"',
        "İSTİHBARAT LABORATUVARI",
    ):
        if marker not in html:
            raise RuntimeError(f"live Gift Edition marker missing: {marker}")


def _quick_check(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"runtime database missing: {path}")
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute("PRAGMA quick_check").fetchall()
    if rows != [("ok",)]:
        raise RuntimeError(f"SQLite quick_check failed: {path}: {rows!r}")


def verify_databases(root: Path) -> None:
    dev = root / "Development"
    for path in (
        dev / "runtime/ledger/live_signal_ledger.sqlite3",
        dev / "runtime/alerts/alert_outbox.sqlite3",
        dev / "runtime/paper/paper_fund.sqlite3",
        dev / "runtime/data/live_base_15m_cache.sqlite3",
    ):
        _quick_check(path)


def _count(pattern: str, root: Path) -> int:
    return sum(1 for _ in root.glob(pattern))


def _read_required(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"required continuity file missing: {path}")
    return path.read_text().strip()


def verify_continuity(root: Path) -> None:
    state = root / "Development/runtime/continuity"
    wake = state / "wake"
    shared = Path("/Users/Shared/.crypto-signal-wake-relay")
    if not (state / "user_pause").is_file():
        raise RuntimeError("local continuity pause missing")
    if not (shared / "user_pause").is_file():
        raise RuntimeError("shared continuity pause missing")
    if _count("leases/active/*.lease", state) != 0:
        raise RuntimeError("active continuity lease present")
    if _count("queue/*.wake", wake) != 0:
        raise RuntimeError("local wake queue is not empty")
    if _count("queue/*.wake", shared) != 0:
        raise RuntimeError("shared relay queue is not empty")

    urls = (
        _read_required(wake / "current_chat_url"),
        _read_required(wake / "expected_chat_url"),
        _read_required(shared / "current_chat_url"),
        _read_required(shared / "expected_chat_url"),
    )
    if len(set(urls)) != 1:
        raise RuntimeError("continuity chat binding is not exact")
    if _read_required(shared / "project_namespace") != "crypto-signal":
        raise RuntimeError("relay project namespace mismatch")

    relay_status = _read_required(shared / "relay_status")
    fields = {}
    for line in relay_status.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key] = value
    if fields.get("relay_protocol") != "crypto-relay-v2":
        raise RuntimeError("relay protocol is not v2")
    if fields.get("project_namespace") != "crypto-signal":
        raise RuntimeError("relay status namespace mismatch")
    if fields.get("target_url") != urls[0]:
        raise RuntimeError("relay target does not match exact chat binding")

    bridge_pid_raw = _read_required(state / "bridge.pid")
    try:
        bridge_pid = int(bridge_pid_raw)
    except ValueError as exc:
        raise RuntimeError("bridge pid invalid") from exc
    os.kill(bridge_pid, 0)
    command = subprocess.check_output(
        ["ps", "-p", str(bridge_pid), "-o", "command="],
        text=True,
    ).strip()
    expected = str(root / "Development/ops/continuity/bridge_watchdog.py")
    if expected not in command:
        raise RuntimeError("bridge process command mismatch")


def verify_ssd_runtime(root: Path) -> None:
    if not root.is_dir():
        raise RuntimeError("SSD root missing")
    free_bytes = shutil.disk_usage(root).free
    if free_bytes < 5 * 1024**3:
        raise RuntimeError("SSD free space below 5 GiB safety floor")

    for pid_name, command_fragment in (
        ("ssd-service-supervisor.pid", str(root / "ssd-service-supervisor.sh")),
        ("dashboard.pid", str(root / "Product/ops/run_dashboard.py")),
    ):
        raw = _read_required(root / pid_name)
        try:
            pid = int(raw)
        except ValueError as exc:
            raise RuntimeError(f"invalid {pid_name}") from exc
        os.kill(pid, 0)
        command = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True,
        ).strip()
        if command_fragment not in command:
            raise RuntimeError(f"{pid_name} process command mismatch")

    runner_output = subprocess.check_output(
        ["ps", "-axo", "pid=,command="],
        text=True,
    )
    runner_fragment = str(root / "Runner/bin/Runner.Listener run --startuptype service")
    if runner_fragment not in runner_output:
        raise RuntimeError("SSD self-hosted runner listener missing")

    legacy_paths = (
        Path("/Users/crypto-signal-agent/Crypto-Signal"),
        Path("/Users/crypto-signal-agent/Crypto-Signal-Live"),
        Path("/Users/crypto-signal-agent/Crypto-Signal-Product"),
        Path("/Users/crypto-signal-agent/Crypto-Signal-Alerts"),
        Path("/Users/crypto-signal-agent/Crypto-Signal-Paper"),
    )
    present = [str(path) for path in legacy_paths if path.exists()]
    if present:
        raise RuntimeError(f"legacy internal runtime paths present: {present}")


def run(*, root: Path, base_url: str) -> None:
    if os.getuid() != 504:
        raise RuntimeError("R13 verifier must run as UID504")

    health = _get_json(base_url, "/api/health")
    intelligence = _get_json(base_url, "/api/intelligence-center")
    paper = _get_json(base_url, "/api/paper/mission-control")
    openapi = _get_json(base_url, "/api/openapi.json")
    shell = _get_text(base_url)

    verify_health(health)
    verify_intelligence(intelligence)
    verify_paper_mission(paper)
    verify_openapi(openapi)
    verify_shell(shell)
    verify_databases(root)
    verify_continuity(root)
    verify_ssd_runtime(root)

    print(
        "R13_INTEGRATED_RUNTIME_VERIFIER_PASS=YES",
        f"accepted_engines={intelligence['accepted_engine_count']}",
        "research_production_contribution=0",
        "paper_trade_policy=NOT_ACTIVATED",
        "continuity_paused=YES",
        "REAL_CAPITAL=0",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/Volumes/Crypto-504/Crypto-Signal"),
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:48700")
    args = parser.parse_args()
    run(root=args.root, base_url=args.base_url)


if __name__ == "__main__":
    main()
