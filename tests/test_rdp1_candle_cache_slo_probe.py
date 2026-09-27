from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import ops.rdp1_candle_cache_slo_probe as probe


def _seed(
    path: Path,
    *,
    close_ms: int,
    ingested_lag_ms: int,
) -> None:
    with sqlite3.connect(path) as db:
        db.execute(
            """
            CREATE TABLE candles (
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time_ms INTEGER NOT NULL,
                close_time_ms INTEGER NOT NULL,
                source_timestamp_ms INTEGER NOT NULL,
                ingested_at_ms INTEGER NOT NULL,
                adapter_version TEXT NOT NULL,
                is_closed INTEGER NOT NULL
            )
            """
        )
        rows = []
        for exchange, symbol in probe.CONTEXTS:
            rows.append(
                (
                    exchange,
                    "spot",
                    symbol,
                    probe.TIMEFRAME,
                    close_ms - 899_999,
                    close_ms,
                    close_ms + 20_000,
                    close_ms + ingested_lag_ms,
                    "test/1",
                    1,
                )
            )
        db.executemany(
            """
            INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def test_closed_candle_slo_probe_accepts_fresh_timely_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    now_ms = 2_000_000
    cache = tmp_path / "cache.sqlite3"
    _seed(cache, close_ms=1_100_000, ingested_lag_ms=60_000)
    monkeypatch.setattr(
        probe.time,
        "time_ns",
        lambda: now_ms * 1_000_000,
    )

    assert probe.run(cache) == 0


def test_closed_candle_slo_probe_rejects_late_availability(
    tmp_path: Path,
    monkeypatch,
) -> None:
    now_ms = 2_000_000
    cache = tmp_path / "cache.sqlite3"
    _seed(cache, close_ms=1_100_000, ingested_lag_ms=120_000)
    monkeypatch.setattr(
        probe.time,
        "time_ns",
        lambda: now_ms * 1_000_000,
    )

    assert probe.run(cache) == 2
