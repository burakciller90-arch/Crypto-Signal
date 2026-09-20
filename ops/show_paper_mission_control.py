#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from crypto_signal.paper.dry_run import PaperActivationDryRunError
from crypto_signal.paper.event_scanner import PaperSignalEventScanError
from crypto_signal.paper.mission_control import (
    PaperMissionControlError,
    read_paper_mission_control_snapshot,
)
from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.performance import PaperTradePerformanceError
from crypto_signal.paper.portfolio import PaperPortfolioError

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_PAPER_LEDGER = BASE / "runtime" / "paper" / "paper_fund.sqlite3"
DEFAULT_SIGNAL_LEDGER = BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
DEFAULT_CANDLE_CACHE = BASE / "runtime" / "data" / "live_base_15m_cache.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ledger", type=Path, default=DEFAULT_PAPER_LEDGER)
    parser.add_argument("--signal-ledger", type=Path, default=DEFAULT_SIGNAL_LEDGER)
    parser.add_argument("--candle-cache", type=Path, default=DEFAULT_CANDLE_CACHE)
    parser.add_argument("--observed-at-ms", type=int)
    parser.add_argument("--max-candidates", type=int, default=100)
    return parser.parse_args()


def _render(value: object | None) -> str:
    return "-" if value is None else str(value)


def main() -> int:
    args = parse_args()
    if REAL_CAPITAL != 0:
        print("PAPER_MISSION_CONTROL_ERROR=REAL_CAPITAL", file=sys.stderr, flush=True)
        return 1
    observed_at_ms = (
        time.time_ns() // 1_000_000
        if args.observed_at_ms is None
        else args.observed_at_ms
    )
    try:
        snapshot = read_paper_mission_control_snapshot(
            paper_ledger_path=args.paper_ledger,
            signal_ledger_path=args.signal_ledger,
            candle_cache_path=args.candle_cache,
            observed_at_ms=observed_at_ms,
            max_candidates=args.max_candidates,
        )
    except (
        OSError,
        PaperActivationDryRunError,
        PaperMissionControlError,
        PaperPortfolioError,
        PaperSignalEventScanError,
        PaperTradePerformanceError,
        ValueError,
    ) as exc:
        print(
            f"PAPER_MISSION_CONTROL_ERROR={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    for cadence in snapshot.decision_cadence:
        print(
            "PAPER_MISSION_CONTROL_CADENCE "
            f"symbol={cadence.symbol.value} "
            f"status={cadence.status.value} "
            f"binance_asof={'-' if cadence.binance is None else cadence.binance.signal_as_of_ms} "
            f"bybit_asof={'-' if cadence.bybit is None else cadence.bybit.signal_as_of_ms} "
            f"binance_cutoff={'-' if cadence.binance is None else cadence.binance.source_cutoff_open_time_ms} "
            f"bybit_cutoff={'-' if cadence.bybit is None else cadence.bybit.source_cutoff_open_time_ms} "
            f"paired_asof={_render(cadence.paired_as_of_ms)} "
            f"paired_cutoff={_render(cadence.paired_source_cutoff_open_time_ms)} "
            f"candidate_available={'YES' if cadence.candidate_available else 'NO'} "
            "REAL_CAPITAL=0",
            flush=True,
        )

    for candidate in snapshot.candidates:
        steps = "|".join(
            f"{step.stage.value}:{step.state.value}:{step.code}"
            for step in candidate.trace.steps
        )
        print(
            "PAPER_MISSION_CONTROL_CANDIDATE "
            f"event={candidate.event_identity} "
            f"symbol={candidate.symbol.value} "
            f"signal_as_of_ms={candidate.signal_as_of_ms} "
            f"status={candidate.terminal_status.value} "
            f"action={candidate.candidate_action.value} "
            f"reason={candidate.reason_code} "
            f"trace={candidate.trace.trace_identity} "
            f"steps={steps} "
            "REAL_CAPITAL=0",
            flush=True,
        )

    stream = snapshot.signal_stream
    portfolio = snapshot.portfolio
    performance = snapshot.performance
    trade_success = (
        "NOT_YET_MEASURED"
        if performance.status.value == "not_yet_measured"
        else "AVAILABLE"
    )
    print(
        "PAPER_MISSION_CONTROL_OK "
        f"snapshot={snapshot.snapshot_identity} "
        f"observed_at_ms={snapshot.observed_at_ms} "
        f"activation={snapshot.activation_identity} "
        f"cutoff_ms={snapshot.activation_cutoff_ms} "
        f"baseline_freezes={snapshot.baseline_signal_freeze_count} "
        f"signal_freezes={stream.total_freeze_count} "
        f"latest_signal={_render(stream.latest_signal_freeze_identity)} "
        f"latest_frozen_at_ms={_render(stream.latest_frozen_at_ms)} "
        f"latest_signal_age_ms={_render(stream.latest_freeze_age_ms)} "
        f"latest_exchange={_render(stream.latest_exchange)} "
        f"latest_symbol={_render(stream.latest_symbol)} "
        f"latest_timeframe={_render(stream.latest_timeframe)} "
        f"latest_state={_render(stream.latest_signal_state)} "
        f"latest_direction={_render(stream.latest_direction)} "
        f"eligible_freezes={snapshot.eligible_post_activation_freezes} "
        f"incomplete_pairs={snapshot.incomplete_provider_pairs} "
        f"processed_skips={snapshot.processed_event_skips} "
        f"candidates={len(snapshot.candidates)} "
        f"ready_candidates={snapshot.ready_candidate_count} "
        f"attention_required={'YES' if snapshot.attention_required else 'NO'} "
        f"portfolio={portfolio.availability.value} "
        f"cash_usdt={portfolio.cash_usdt} "
        f"positions={len(portfolio.positions)} "
        f"nav_usdt={_render(portfolio.nav_usdt)} "
        f"pnl_usdt={_render(portfolio.pnl_usdt)} "
        f"total_return_fraction={_render(portfolio.total_return_fraction)} "
        f"performance={performance.status.value} "
        f"closed_trades={performance.closed_trade_count} "
        f"open_trades={performance.open_trade_count} "
        f"win_rate_fraction={_render(performance.win_rate_fraction)} "
        f"trade_success={trade_success} "
        f"trade_policy={snapshot.trade_policy} "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
