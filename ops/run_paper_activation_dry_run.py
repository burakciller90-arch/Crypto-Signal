#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

from crypto_signal.paper.dry_run import (
    PaperActivationDryRunError,
    evaluate_paper_activation_dry_run,
    read_paper_activation_read_only,
)
from crypto_signal.paper.event_scanner import (
    PaperSignalEventScanError,
    scan_post_activation_signal_events,
)
from crypto_signal.paper.models import REAL_CAPITAL

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_PAPER_LEDGER = BASE / "runtime" / "paper" / "paper_fund.sqlite3"
DEFAULT_SIGNAL_LEDGER = BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
DEFAULT_CANDLE_CACHE = BASE / "runtime" / "data" / "live_base_15m_cache.sqlite3"
DEFAULT_MAX_EVENTS = 100
_PAPER_TABLES = (
    "paper_fund_creations",
    "paper_decision_intents",
    "paper_simulated_fills",
    "paper_position_cash_mutations",
    "paper_nav_snapshots",
    "paper_replay_index",
    "paper_activation_state",
    "paper_processed_events",
    "paper_venue_rule_snapshots",
)


class PaperStableDryRunError(RuntimeError):
    """Raised when the bounded stable observation cannot be proven read-only."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ledger", type=Path, default=DEFAULT_PAPER_LEDGER)
    parser.add_argument("--signal-ledger", type=Path, default=DEFAULT_SIGNAL_LEDGER)
    parser.add_argument("--candle-cache", type=Path, default=DEFAULT_CANDLE_CACHE)
    parser.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS)
    return parser.parse_args()


def _paper_db_fingerprint(path: Path) -> str:
    if not path.exists():
        raise PaperStableDryRunError("paper ledger does not exist")
    uri = f"file:{path.resolve()}?mode=ro"
    payload: list[tuple[str, tuple[tuple[object, ...], ...]]] = []
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.execute("PRAGMA query_only=ON")
            for table in _PAPER_TABLES:
                exists = connection.execute(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE type = 'table' AND name = ?
                    """,
                    (table,),
                ).fetchone()
                if exists is None:
                    raise PaperStableDryRunError(
                        f"paper ledger missing required table: {table}"
                    )
                rows = connection.execute(
                    f"SELECT * FROM {table} ORDER BY 1"
                ).fetchall()
                payload.append(
                    (table, tuple(tuple(value for value in row) for row in rows))
                )
    except sqlite3.Error as exc:
        raise PaperStableDryRunError(
            f"failed to fingerprint paper ledger: {exc}"
        ) from exc
    return hashlib.sha256(repr(tuple(payload)).encode()).hexdigest()


def main() -> int:
    args = parse_args()
    if REAL_CAPITAL != 0:
        print("PAPER_DRY_RUN_ERROR=REAL_CAPITAL", file=sys.stderr, flush=True)
        return 1
    if args.max_events <= 0:
        print(
            "PAPER_DRY_RUN_ERROR=max-events must be positive",
            file=sys.stderr,
            flush=True,
        )
        return 1
    try:
        before = _paper_db_fingerprint(args.paper_ledger)
        activation = read_paper_activation_read_only(args.paper_ledger)
        scan = scan_post_activation_signal_events(
            signal_ledger_path=args.signal_ledger,
            paper_ledger_path=args.paper_ledger,
            activation=activation,
        )
        if len(scan.candidates) > args.max_events:
            raise PaperStableDryRunError(
                "post-activation candidate count exceeds bounded max-events"
            )

        evaluated_at_ms = time.time_ns() // 1_000_000
        statuses: Counter[str] = Counter()
        for event in scan.candidates:
            result = evaluate_paper_activation_dry_run(
                event=event,
                activation=activation,
                paper_ledger_path=args.paper_ledger,
                candle_cache_path=args.candle_cache,
                evaluated_at_ms=evaluated_at_ms,
            )
            statuses[result.status.value] += 1
            execution_identity = (
                "-"
                if result.execution_input is None
                else result.execution_input.input_identity
            )
            sizing_status = (
                "-" if result.sizing is None else result.sizing.status.value
            )
            pretrade_status = (
                "-"
                if result.venue_bound_pretrade is None
                else result.venue_bound_pretrade.pretrade.status.value
            )
            print(
                "PAPER_DRY_RUN_EVENT "
                f"event={event.event_identity} "
                f"symbol={event.symbol.value} "
                f"signal_as_of_ms={event.signal_as_of_ms} "
                f"status={result.status.value} "
                f"action={result.autonomy.candidate_action.value} "
                f"reason={result.autonomy.reason_code.value} "
                f"execution_input={execution_identity} "
                f"venue_rules={result.venue_rule_snapshot_identity or '-'} "
                f"sizing={sizing_status} "
                f"pretrade={pretrade_status} "
                "REAL_CAPITAL=0",
                flush=True,
            )

        after = _paper_db_fingerprint(args.paper_ledger)
        if after != before:
            raise PaperStableDryRunError(
                "paper DB changed during read-only activation dry-run"
            )
        rendered_statuses = (
            ", ".join(
                f"{name}:{count}"
                for name, count in sorted(statuses.items())
            )
            or "-"
        )
        print(
            "PAPER_DRY_RUN_OK "
            f"activation={activation.activation_identity} "
            f"cutoff_ms={activation.activation_cutoff_ms} "
            f"eligible_freezes={scan.eligible_freeze_count} "
            f"incomplete_pairs={scan.incomplete_pair_count} "
            f"processed_skips={scan.processed_skip_count} "
            f"candidates={len(scan.candidates)} "
            f"evaluated_at_ms={evaluated_at_ms} "
            f"statuses={rendered_statuses} "
            "paper_db_unchanged=YES "
            "trade_policy=NOT_ACTIVATED "
            "REAL_CAPITAL=0",
            flush=True,
        )
        return 0
    except (
        OSError,
        PaperActivationDryRunError,
        PaperSignalEventScanError,
        PaperStableDryRunError,
        sqlite3.Error,
        ValueError,
    ) as exc:
        print(
            f"PAPER_DRY_RUN_ERROR={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
