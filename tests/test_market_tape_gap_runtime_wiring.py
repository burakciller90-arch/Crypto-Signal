from __future__ import annotations

import sys
from pathlib import Path

from ops.run_market_tape_stream import (
    DEFAULT_GAP_LEDGER_DB,
    DEFAULT_MAX_INGESTION_SILENCE_MS,
    parse_args,
)


def test_market_tape_stream_gap_runtime_defaults_are_canonical(
    monkeypatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["run_market_tape_stream.py"])

    args = parse_args()

    assert args.gap_ledger_db == DEFAULT_GAP_LEDGER_DB
    assert str(args.gap_ledger_db).startswith("/Volumes/Crypto-504/")
    assert args.max_ingestion_silence_ms == DEFAULT_MAX_INGESTION_SILENCE_MS
    assert args.max_ingestion_silence_ms > args.heartbeat_interval_ms
    assert Path(args.gap_ledger_db).name == "market_data_gaps.sqlite3"
