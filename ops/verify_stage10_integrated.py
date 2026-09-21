from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

EXPECTED_BENCHMARKS = (
    "cash_100_usdt",
    "btc_buy_hold_100_usdt",
    "btc_eth_sol_equal_weight_100_usdt",
)
READ_ENDPOINTS = (
    "/api/health",
    "/api/command-center?recent_limit=8",
    "/api/market-radar",
    "/api/navigation",
    "/api/signals?limit=20&offset=0",
    "/api/performance",
    "/api/alerts?limit=20",
    "/api/education",
    "/api/paper/mission-control",
)


@dataclass(frozen=True, slots=True)
class PaperCounts:
    fund_creations: int
    decision_intents: int
    simulated_fills: int
    position_cash_mutations: int
    nav_snapshots: int
    replay_index: int
    activation_state: int
    processed_events: int


def _get_json(
    base_url: str,
    path: str,
    *,
    timeout_seconds: float = 12.0,
    attempts: int = 3,
    retry_delay_seconds: float = 0.25,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if attempts <= 0:
        raise ValueError("attempts must be positive")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds cannot be negative")

    url = f"{base_url.rstrip('/')}{path}"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            headers={"Cache-Control": "no-store"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"{path} returned HTTP {response.status}"
                    )
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise TypeError(f"{path} did not return a JSON object")
            return payload
        except (
            TimeoutError,
            urllib.error.URLError,
        ) as exc:
            last_error = exc
            if attempt == attempts:
                break
            print(
                "STAGE10_RUNTIME_GET_RETRY "
                f"path={path} "
                f"attempt={attempt}/{attempts} "
                f"error={type(exc).__name__}",
                flush=True,
            )
            if retry_delay_seconds:
                time.sleep(retry_delay_seconds)

    assert last_error is not None
    raise RuntimeError(
        f"{path} failed after {attempts} attempts: "
        f"{type(last_error).__name__}: {last_error}"
    ) from last_error


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if row is None:
        raise RuntimeError(f"missing count row for {table}")
    return int(row[0])


def _paper_counts(path: Path) -> PaperCounts:
    if not path.exists():
        raise RuntimeError(f"paper ledger missing: {path}")
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        connection.execute("PRAGMA query_only=ON")
        return PaperCounts(
            fund_creations=_table_count(connection, "paper_fund_creations"),
            decision_intents=_table_count(connection, "paper_decision_intents"),
            simulated_fills=_table_count(connection, "paper_simulated_fills"),
            position_cash_mutations=_table_count(
                connection,
                "paper_position_cash_mutations",
            ),
            nav_snapshots=_table_count(connection, "paper_nav_snapshots"),
            replay_index=_table_count(connection, "paper_replay_index"),
            activation_state=_table_count(connection, "paper_activation_state"),
            processed_events=_table_count(connection, "paper_processed_events"),
        )


def _verify_openapi(base_url: str) -> None:
    spec = _get_json(base_url, "/api/openapi.json")
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
                f"non-read-only product API surface: {path} methods={sorted(methods)}"
            )
        lowered = str(path).lower()
        for token in (
            "order",
            "broker",
            "credential",
            "api-key",
            "api_key",
            "secret",
            "execute",
            "write-authority",
        ):
            if token in lowered:
                raise RuntimeError(f"forbidden product API path token: {path}")


def _verify_health(payload: dict[str, Any]) -> None:
    if payload.get("status") != "ok":
        raise RuntimeError("product health is not ok")
    if payload.get("read_only") is not True:
        raise RuntimeError("product health is not read-only")
    if payload.get("real_capital") != 0:
        raise RuntimeError("product health REAL_CAPITAL is not 0")
    if payload.get("ledger_present") is not True:
        raise RuntimeError("signal ledger is not present")


def _verify_paper_mission(payload: dict[str, Any]) -> None:
    if payload.get("status") != "ready":
        raise RuntimeError("paper Mission Control is not ready")
    if payload.get("read_only") is not True:
        raise RuntimeError("paper Mission Control is not read-only")
    if payload.get("real_capital") != 0:
        raise RuntimeError("paper Mission Control REAL_CAPITAL is not 0")
    if payload.get("trade_policy") != "NOT_ACTIVATED":
        raise RuntimeError("paper write policy is not closed")

    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        raise TypeError("paper Mission Control snapshot missing")
    if snapshot.get("version") != "paper_mission_control.v4":
        raise RuntimeError("paper Mission Control v4 is not deployed")
    if snapshot.get("real_capital") != 0:
        raise RuntimeError("paper snapshot REAL_CAPITAL is not 0")
    if snapshot.get("trade_policy") != "NOT_ACTIVATED":
        raise RuntimeError("paper snapshot write policy is not closed")

    benchmarks = snapshot.get("benchmarks")
    if not isinstance(benchmarks, dict):
        raise TypeError("benchmark snapshot missing")
    results = benchmarks.get("results")
    if not isinstance(results, list):
        raise TypeError("benchmark results missing")
    kinds = tuple(item.get("kind") for item in results if isinstance(item, dict))
    if kinds != EXPECTED_BENCHMARKS:
        raise RuntimeError(f"benchmark coverage mismatch: {kinds!r}")
    if benchmarks.get("start_at_ms") != snapshot.get("activation_cutoff_ms"):
        raise RuntimeError("benchmark start does not match activation cutoff")
    if benchmarks.get("observed_at_ms") != snapshot.get("observed_at_ms"):
        raise RuntimeError("benchmark observation time mismatch")

    comparisons = snapshot.get("benchmark_comparisons")
    if not isinstance(comparisons, list) or len(comparisons) != 3:
        raise RuntimeError("benchmark comparisons missing")
    comparison_kinds = tuple(
        item.get("kind") for item in comparisons if isinstance(item, dict)
    )
    if comparison_kinds != EXPECTED_BENCHMARKS:
        raise RuntimeError("benchmark comparison coverage mismatch")

    performance = snapshot.get("performance")
    if not isinstance(performance, dict):
        raise TypeError("paper performance snapshot missing")
    window = performance.get("window")
    if not isinstance(window, dict):
        raise TypeError("paper performance window missing")
    if window.get("measurement_start_at_ms") != snapshot.get("activation_cutoff_ms"):
        raise RuntimeError("performance window does not start at activation cutoff")
    if window.get("observed_at_ms") != snapshot.get("observed_at_ms"):
        raise RuntimeError("performance window observation mismatch")
    turnover = Decimal(str(window.get("turnover_fraction")))
    if turnover < Decimal(0):
        raise RuntimeError("performance turnover cannot be negative")
    duration_raw = window.get("duration_ms")
    if not isinstance(duration_raw, int):
        raise TypeError("performance window duration missing")
    duration_ms = duration_raw
    cash_fraction_raw = window.get("cash_time_fraction")
    invested_fraction_raw = window.get("invested_time_fraction")
    if duration_ms > 0:
        cash_fraction = Decimal(str(cash_fraction_raw))
        invested_fraction = Decimal(str(invested_fraction_raw))
        if not (Decimal(0) <= cash_fraction <= Decimal(1)):
            raise RuntimeError("cash-time fraction outside [0,1]")
        if cash_fraction + invested_fraction != Decimal(1):
            raise RuntimeError("cash/invested time fractions do not reconcile")
    if performance.get("status") == "not_yet_measured":
        if performance.get("expectancy_usdt_per_closed_trade") is not None:
            raise RuntimeError("unmeasured performance fabricated expectancy")
        if performance.get("expectancy_return_fraction_per_closed_trade") is not None:
            raise RuntimeError("unmeasured performance fabricated return expectancy")


def _verify_paper_counts(counts: PaperCounts) -> None:
    if counts.fund_creations != 1:
        raise RuntimeError("paper fund creation count is not exactly one")
    if counts.activation_state != 1:
        raise RuntimeError("paper activation singleton is not exactly one")
    if counts.decision_intents != 0:
        raise RuntimeError("paper decision intents appeared while write gate is closed")
    if counts.simulated_fills != 0:
        raise RuntimeError("paper simulated fills appeared while write gate is closed")
    if counts.position_cash_mutations != 0:
        raise RuntimeError("paper cash/position mutations appeared while gate is closed")
    if counts.nav_snapshots != 0:
        raise RuntimeError("paper NAV mutations appeared while write gate is closed")
    if counts.processed_events != 0:
        raise RuntimeError("paper processed events appeared while write gate is closed")


def run(*, base_url: str, paper_ledger: Path, cycles: int, pause_seconds: float) -> None:
    if cycles <= 0:
        raise ValueError("cycles must be positive")
    if pause_seconds < 0:
        raise ValueError("pause_seconds cannot be negative")

    before = _paper_counts(paper_ledger)
    _verify_paper_counts(before)
    _verify_openapi(base_url)

    last_health: dict[str, Any] | None = None
    last_mission: dict[str, Any] | None = None
    for _ in range(cycles):
        responses = {path: _get_json(base_url, path) for path in READ_ENDPOINTS}
        last_health = responses["/api/health"]
        last_mission = responses["/api/paper/mission-control"]
        _verify_health(last_health)
        _verify_paper_mission(last_mission)
        if pause_seconds:
            time.sleep(pause_seconds)

    after = _paper_counts(paper_ledger)
    _verify_paper_counts(after)
    if after != before:
        raise RuntimeError(
            f"paper ledger changed during read-only endurance: before={before} after={after}"
        )
    if last_health is None or last_mission is None:
        raise AssertionError("endurance loop produced no observations")

    snapshot = last_mission["snapshot"]
    print(
        "STAGE10_RUNTIME_ACCEPTANCE_PASS=YES",
        f"cycles={cycles}",
        f"product_version={last_health.get('product_version')}",
        f"mission_version={snapshot.get('version')}",
        f"benchmark_snapshot={snapshot['benchmarks'].get('snapshot_identity')}",
        f"paper_counts={after}",
        "trade_policy=NOT_ACTIVATED",
        "REAL_CAPITAL=0",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:48700")
    parser.add_argument(
        "--paper-ledger",
        type=Path,
        default=Path(
            "/Users/crypto-signal-agent/Crypto-Signal/runtime/paper/paper_fund.sqlite3"
        ),
    )
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--pause-seconds", type=float, default=0.05)
    args = parser.parse_args()
    run(
        base_url=args.base_url,
        paper_ledger=args.paper_ledger,
        cycles=args.cycles,
        pause_seconds=args.pause_seconds,
    )


if __name__ == "__main__":
    main()
