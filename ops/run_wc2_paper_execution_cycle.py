#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_execution_runtime import (
    process_wc2_paper_execution_cycle,
)

ROOT = Path("/Volumes/Crypto-504/Crypto-Signal/Development")
RUNTIME = ROOT / "runtime"

DEFAULTS = {
    "signal_ledger": RUNTIME / "ledger/live_signal_ledger.sqlite3",
    "decision_evidence": RUNTIME / "decision/decision_evidence.sqlite3",
    "cohort_journal": RUNTIME / "wc2/wc2_untouched_forward.sqlite3",
    "epoch2": RUNTIME / "paper/paper_fund_epoch2.sqlite3",
    "execution_protocol": (
        RUNTIME / "wc2/wc2_paper_execution.wc2-paper-execution-protocol.sqlite3"
    ),
    "runtime_activation": (
        RUNTIME / "wc2/wc2_paper_execution.wc2-paper-execution-runtime.sqlite3"
    ),
    "execution_journal": (
        RUNTIME / "wc2/wc2_paper_execution.wc2-paper-execution.sqlite3"
    ),
    "candle_cache": RUNTIME / "data/live_base_15m_cache.sqlite3",
    "venue_rules": RUNTIME / "paper/paper_fund.sqlite3",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for name, path in DEFAULTS.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, default=path)
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    selected = {
        "signal_ledger_path": args.signal_ledger,
        "decision_evidence_path": args.decision_evidence,
        "cohort_journal_path": args.cohort_journal,
        "epoch2_path": args.epoch2,
        "execution_protocol_path": args.execution_protocol,
        "runtime_activation_path": args.runtime_activation,
        "execution_journal_path": args.execution_journal,
        "candle_cache_path": args.candle_cache,
        "venue_rule_store_path": args.venue_rules,
    }
    if any(
        not str(path).startswith("/Volumes/Crypto-504/")
        for path in selected.values()
    ):
        print("WC2_EXECUTION_CYCLE_ERROR=NON_CANONICAL_PATH", file=sys.stderr)
        return 2
    required = {
        key: path
        for key, path in selected.items()
        if key != "execution_journal_path"
    }
    missing = [key for key, path in required.items() if not path.is_file()]
    if missing:
        print(
            "WC2_EXECUTION_CYCLE_ERROR=MISSING_INPUTS:" + ",".join(sorted(missing)),
            file=sys.stderr,
        )
        return 3
    try:
        result = process_wc2_paper_execution_cycle(
            **selected,
            observed_at_ms=time.time_ns() // 1_000_000,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(
            f"WC2_EXECUTION_CYCLE_ERROR={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 4

    print(
        "WC2_EXECUTION_CYCLE "
        f"observed_at_ms={result.observed_at_ms} "
        f"scanned_pair_n={result.scanned_pair_n} "
        f"eligible_event_n={result.eligible_event_n} "
        f"already_terminal_n={result.already_terminal_n} "
        f"expired_gap_n={result.expired_gap_n} "
        f"waiting_lineage_n={result.waiting_lineage_n} "
        f"waiting_execution_input_n={result.waiting_execution_input_n} "
        f"waiting_venue_rules_n={result.waiting_venue_rules_n} "
        f"hold_cash_n={result.hold_cash_n} "
        f"sizing_rejected_n={result.sizing_rejected_n} "
        f"pretrade_rejected_n={result.pretrade_rejected_n} "
        f"executed_n={result.executed_n} "
        f"appended_n={len(result.appended_record_identities)}",
        flush=True,
    )
    print(
        "WC2_EXECUTION_CYCLE_HISTORICAL_BACKFILL=NO "
        "WC2_EXECUTION_CYCLE_REAL_ORDER_AUTHORITY=NO "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
