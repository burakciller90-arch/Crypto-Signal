#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from crypto_signal.paper.dry_run import (
    evaluate_paper_activation_dry_run,
    explain_paper_activation_dry_run,
    read_paper_activation_read_only,
)
from crypto_signal.paper.event_scanner import scan_post_activation_signal_events
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.write_authority import (
    PaperWriteAuthorityError,
    append_paper_write_authority_event,
    load_current_paper_write_authority,
)

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_PAPER_LEDGER = BASE / "runtime" / "paper" / "paper_fund.sqlite3"
DEFAULT_SIGNAL_LEDGER = BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
DEFAULT_CANDLE_CACHE = BASE / "runtime" / "data" / "live_base_15m_cache.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("enable", "disable"), required=True)
    parser.add_argument("--paper-ledger", type=Path, default=DEFAULT_PAPER_LEDGER)
    parser.add_argument("--signal-ledger", type=Path, default=DEFAULT_SIGNAL_LEDGER)
    parser.add_argument("--candle-cache", type=Path, default=DEFAULT_CANDLE_CACHE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if REAL_CAPITAL != 0:
        print("PAPER_WRITE_AUTHORITY_ERROR=REAL_CAPITAL", file=sys.stderr, flush=True)
        return 1
    now_ms = time.time_ns() // 1_000_000
    ledger = PaperFundLedger(args.paper_ledger)
    try:
        activation = read_paper_activation_read_only(args.paper_ledger)
        current = load_current_paper_write_authority(ledger)
        if args.mode == "enable":
            if current is not None and current.enabled:
                print(
                    "PAPER_WRITE_AUTHORITY_OK "
                    f"write=unchanged authority={current.authority_event_identity} "
                    "enabled=YES evidence_events="
                    f"{len(current.reviewed_event_identities)} "
                    "REAL_CAPITAL=0",
                    flush=True,
                )
                return 0

            scan = scan_post_activation_signal_events(
                signal_ledger_path=args.signal_ledger,
                paper_ledger_path=args.paper_ledger,
                activation=activation,
                observed_at_ms=now_ms,
            )
            if not scan.candidates:
                raise PaperWriteAuthorityError(
                    "enable requires current reviewed post-activation candidates"
                )
            reviewed_events: list[str] = []
            reviewed_traces: list[str] = []
            for event in scan.candidates:
                result = evaluate_paper_activation_dry_run(
                    event=event,
                    activation=activation,
                    paper_ledger_path=args.paper_ledger,
                    candle_cache_path=args.candle_cache,
                    evaluated_at_ms=now_ms,
                )
                trace = explain_paper_activation_dry_run(result)
                reviewed_events.append(event.event_identity)
                reviewed_traces.append(trace.trace_identity)
                print(
                    "PAPER_WRITE_AUTHORITY_EVIDENCE "
                    f"event={event.event_identity} "
                    f"trace={trace.trace_identity} "
                    f"symbol={event.symbol.value} "
                    f"status={result.status.value} "
                    f"action={result.autonomy.candidate_action.value} "
                    f"reason={result.autonomy.reason_code.value} "
                    "REAL_CAPITAL=0",
                    flush=True,
                )
            disposition, event = append_paper_write_authority_event(
                ledger=ledger,
                activation=activation,
                enabled=True,
                created_at_ms=now_ms,
                reason="mechanically reviewed post-activation dry-run evidence",
                reviewed_event_identities=tuple(reviewed_events),
                reviewed_trace_identities=tuple(reviewed_traces),
            )
        else:
            if current is None or not current.enabled:
                print(
                    "PAPER_WRITE_AUTHORITY_OK "
                    f"write=unchanged authority={'-' if current is None else current.authority_event_identity} "
                    "enabled=NO evidence_events=0 REAL_CAPITAL=0",
                    flush=True,
                )
                return 0
            disposition, event = append_paper_write_authority_event(
                ledger=ledger,
                activation=activation,
                enabled=False,
                created_at_ms=now_ms,
                reason="explicit virtual-paper write authority disable",
            )

        print(
            "PAPER_WRITE_AUTHORITY_OK "
            f"write={disposition.value} "
            f"authority={event.authority_event_identity} "
            f"enabled={'YES' if event.enabled else 'NO'} "
            f"evidence_events={len(event.reviewed_event_identities)} "
            "REAL_CAPITAL=0",
            flush=True,
        )
        return 0
    except (OSError, PaperWriteAuthorityError, ValueError) as exc:
        print(
            f"PAPER_WRITE_AUTHORITY_ERROR={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
