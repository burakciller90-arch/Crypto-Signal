#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from crypto_signal.paper.epochs import EPOCH_2_LEDGER_FILENAME
from crypto_signal.product.web import (
    DEFAULT_ALERT_OUTBOX_PATH,
    DEFAULT_CANDLE_CACHE_PATH,
    DEFAULT_LEDGER_PATH,
    DEFAULT_PAPER_LEDGER_PATH,
    PRODUCT_ROOT_CHOICES,
    PRODUCT_ROOT_STREAM,
    create_app,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=48700)
    parser.add_argument(
        "--product-root",
        choices=PRODUCT_ROOT_CHOICES,
        default=PRODUCT_ROOT_STREAM,
        help="product root surface; use galactech for immediate rollback",
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument(
        "--alert-outbox",
        type=Path,
        default=DEFAULT_ALERT_OUTBOX_PATH,
    )
    parser.add_argument(
        "--paper-ledger",
        type=Path,
        default=DEFAULT_PAPER_LEDGER_PATH,
    )
    parser.add_argument(
        "--candle-cache",
        type=Path,
        default=DEFAULT_CANDLE_CACHE_PATH,
    )
    parser.add_argument("--decision-evidence", type=Path, default=None)
    parser.add_argument("--epoch2-ledger", type=Path, default=None)
    parser.add_argument("--shadow-intent-journal", type=Path, default=None)
    parser.add_argument("--shadow-cycle-manifest", type=Path, default=None)
    parser.add_argument("--runtime-replay-observation", type=Path, default=None)
    parser.add_argument("--market-tape", type=Path, default=None)
    parser.add_argument(
        "--market-tape-collector-runtime",
        type=Path,
        default=None,
    )
    parser.add_argument("--cold-archive", type=Path, default=None)
    parser.add_argument("--provider-divergence", type=Path, default=None)
    parser.add_argument("--event-source-runtime", type=Path, default=None)
    parser.add_argument("--wc2-cohort", type=Path, default=None)
    parser.add_argument("--stream-ledger", type=Path, default=None)
    parser.add_argument(
        "--learning-memory",
        type=Path,
        default=None,
        help="optional read-only Learning Memory SQLite path",
    )
    return parser.parse_args()


def resolve_runtime_paths(args: argparse.Namespace) -> dict[str, Path]:
    runtime_root = args.ledger.parent.parent
    return {
        "decision_evidence_path": (
            args.decision_evidence
            or runtime_root / "decision" / "decision_evidence.sqlite3"
        ),
        "epoch2_ledger_path": (
            args.epoch2_ledger
            or runtime_root / "paper" / EPOCH_2_LEDGER_FILENAME
        ),
        "shadow_intent_journal_path": (
            args.shadow_intent_journal
            or runtime_root / "r25" / "r25.shadow-intent.sqlite3"
        ),
        "shadow_cycle_manifest_path": (
            args.shadow_cycle_manifest
            or runtime_root / "r25" / "r25.shadow-cycle.sqlite3"
        ),
        "runtime_replay_observation_path": (
            args.runtime_replay_observation
            or runtime_root / "r25" / "r25.shadow-replay.sqlite3"
        ),
        "market_tape_path": (
            args.market_tape
            or runtime_root / "market_tape" / "market_tape.sqlite3"
        ),
        "market_tape_collector_runtime_path": (
            args.market_tape_collector_runtime
            or runtime_root / "market_tape" / "collector_runtime.sqlite3"
        ),
        "cold_archive_path": (
            args.cold_archive
            or runtime_root / "market_tape" / "cold"
        ),
        "provider_divergence_path": (
            args.provider_divergence
            or runtime_root / "data" / "provider_divergence.sqlite3"
        ),
        "event_source_runtime_path": (
            args.event_source_runtime
            or runtime_root / "events" / "event_source.sqlite3"
        ),
        "wc2_cohort_path": (
            getattr(args, "wc2_cohort", None)
            or runtime_root / "wc2" / "wc2_untouched_forward.sqlite3"
        ),
        "stream_ledger_path": (
            getattr(args, "stream_ledger", None)
            or runtime_root / "stream" / "intelligence_stream.sqlite3"
        ),
        "options_surface_path": (
            runtime_root / "market_tape" / "options_surface.sqlite3"
        ),
    }


def main() -> None:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("port must be between 1 and 65535")
    runtime_paths = resolve_runtime_paths(args)
    app = create_app(
        args.ledger,
        args.alert_outbox,
        paper_ledger_path=args.paper_ledger,
        candle_cache_path=args.candle_cache,
        learning_memory_path=args.learning_memory,
        product_root=args.product_root,
        **runtime_paths,
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
