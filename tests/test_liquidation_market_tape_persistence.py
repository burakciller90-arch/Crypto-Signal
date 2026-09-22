from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.liquidations import (
    LiquidatedPositionSide,
    build_liquidation_feed_coverage,
    build_liquidation_observation,
)
from crypto_signal.data.market_tape import (
    MarketTapeConflictError,
    MarketTapeStore,
    MarketTapeWriteDisposition,
)
from crypto_signal.data.market_tape_collection import persist_liquidation_batch
from crypto_signal.data.models import DataSource, Exchange


def _event(
    *,
    event_at_ms: int,
    source_timestamp_ms: int | None = None,
    ingested_at_ms: int | None = None,
    source_row_index: int = 0,
    side: LiquidatedPositionSide = LiquidatedPositionSide.LONG,
    size: str = "2",
    price: str = "100",
    adapter_version: str = "bybit-liquidation-test/1",
):
    source_ms = (
        event_at_ms + 10
        if source_timestamp_ms is None
        else source_timestamp_ms
    )
    ingest_ms = (
        source_ms + 10
        if ingested_at_ms is None
        else ingested_at_ms
    )
    return build_liquidation_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        liquidated_position_side=side,
        size=Decimal(size),
        bankruptcy_price=Decimal(price),
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingest_ms,
        source_row_index=source_row_index,
        source=DataSource.WEBSOCKET,
        adapter_version=adapter_version,
    )


def _coverage(
    *,
    start_ms: int = 1_000,
    end_ms: int = 2_000,
    observed_at_ms: int = 2_000,
    adapter_version: str = "bybit-liquidation-test/1",
):
    return build_liquidation_feed_coverage(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        coverage_start_ms=start_ms,
        coverage_end_ms=end_ms,
        observed_at_ms=observed_at_ms,
        source=DataSource.WEBSOCKET,
        adapter_version=adapter_version,
    )


def _schema_version(path) -> str:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT value
            FROM market_tape_meta
            WHERE key = 'schema_version'
            """
        ).fetchone()
    assert row is not None
    return str(row[0])


def test_market_tape_migrates_v1_1_to_v1_2_without_losing_history(tmp_path) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    store.initialize()

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS migration_sentinel (
                id INTEGER PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO migration_sentinel(id, value) VALUES (1, 'preserve-me')"
        )
        connection.execute(
            """
            UPDATE market_tape_meta
            SET value = 'market-tape-schema-v1/1'
            WHERE key = 'schema_version'
            """
        )
        connection.execute("DROP TABLE market_tape_liquidations")
        connection.execute("DROP TABLE market_tape_liquidation_coverage")

    store.initialize()

    assert _schema_version(path) == "market-tape-schema-v1/2"
    with sqlite3.connect(path) as connection:
        sentinel = connection.execute(
            "SELECT value FROM migration_sentinel WHERE id = 1"
        ).fetchone()
        tables = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }
    assert sentinel == ("preserve-me",)
    assert "market_tape_liquidations" in tables
    assert "market_tape_liquidation_coverage" in tables
    assert store.quick_check() is True


def test_market_tape_unknown_schema_fails_closed(tmp_path) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    store.initialize()

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE market_tape_meta
            SET value = 'market-tape-schema-unknown'
            WHERE key = 'schema_version'
            """
        )

    with pytest.raises(MarketTapeConflictError, match="schema version mismatch"):
        store.initialize()


def test_liquidation_provider_event_replay_is_idempotent_and_conflicts_fail_closed(
    tmp_path,
) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    first = _event(
        event_at_ms=1_500,
        source_timestamp_ms=1_510,
        ingested_at_ms=1_520,
        source_row_index=3,
        size="2",
        price="100",
        adapter_version="bybit-liquidation-test/1",
    )
    later_ingest = _event(
        event_at_ms=1_500,
        source_timestamp_ms=1_510,
        ingested_at_ms=1_900,
        source_row_index=3,
        size="2",
        price="100",
        adapter_version="bybit-liquidation-test/2",
    )
    conflicting_reparse = _event(
        event_at_ms=1_500,
        source_timestamp_ms=1_510,
        ingested_at_ms=1_920,
        source_row_index=3,
        size="3",
        price="100",
        adapter_version="bybit-liquidation-test/2",
    )

    assert first.liquidation_identity != later_ingest.liquidation_identity
    assert (
        store.append_liquidation(first)
        is MarketTapeWriteDisposition.INSERTED
    )
    assert (
        store.append_liquidation(later_ingest)
        is MarketTapeWriteDisposition.UNCHANGED
    )
    with pytest.raises(
        MarketTapeConflictError,
        match="provider identity conflicts with market truth",
    ):
        store.append_liquidation(conflicting_reparse)

    assert store.recent_liquidations(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
    ) == (first,)
    counts = store.counts()
    assert counts.liquidations == 1
    assert counts.total == 1
    assert store.latest_event_at_ms() == 1_500


def test_liquidation_coverage_reobservation_does_not_rewrite_first_evidence(
    tmp_path,
) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    first = _coverage(observed_at_ms=2_000)
    later = _coverage(observed_at_ms=2_500)

    assert first.coverage_identity == later.coverage_identity
    assert (
        store.append_liquidation_coverage(first)
        is MarketTapeWriteDisposition.INSERTED
    )
    assert (
        store.append_liquidation_coverage(later)
        is MarketTapeWriteDisposition.UNCHANGED
    )

    persisted = store.recent_liquidation_coverage(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
    )
    assert persisted == (first,)
    counts = store.counts()
    assert counts.liquidation_coverage == 1
    assert counts.total == 1


def test_liquidation_replay_is_pit_safe_and_excludes_late_ingest(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    coverage = _coverage(observed_at_ms=2_000)
    safe = _event(
        event_at_ms=1_500,
        source_timestamp_ms=1_510,
        ingested_at_ms=1_520,
        source_row_index=1,
    )
    late = _event(
        event_at_ms=1_600,
        source_timestamp_ms=1_610,
        ingested_at_ms=2_500,
        source_row_index=2,
        side=LiquidatedPositionSide.SHORT,
    )
    outside = _event(
        event_at_ms=2_100,
        source_timestamp_ms=2_110,
        ingested_at_ms=2_120,
        source_row_index=3,
    )

    store.append_liquidation_coverage(coverage)
    store.append_liquidation(safe)
    store.append_liquidation(late)
    store.append_liquidation(outside)

    replay = store.liquidation_replay(
        coverage_identity=coverage.coverage_identity,
        as_of_ms=2_000,
    )

    assert replay.coverage == coverage
    assert replay.as_of_ms == 2_000
    assert replay.events == (safe,)


def test_zero_event_replay_is_supported_only_by_persisted_coverage(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    coverage = _coverage(observed_at_ms=2_000)
    store.append_liquidation_coverage(coverage)

    replay = store.liquidation_replay(
        coverage_identity=coverage.coverage_identity,
        as_of_ms=2_000,
    )
    assert replay.coverage == coverage
    assert replay.events == ()

    with pytest.raises(
        MarketTapeConflictError,
        match="coverage is not persisted",
    ):
        store.liquidation_replay(
            coverage_identity="f" * 64,
            as_of_ms=2_000,
        )

    future_coverage = _coverage(
        start_ms=3_000,
        end_ms=4_000,
        observed_at_ms=4_100,
        adapter_version="bybit-liquidation-test/future",
    )
    store.append_liquidation_coverage(future_coverage)
    with pytest.raises(
        MarketTapeConflictError,
        match="coverage is future evidence",
    ):
        store.liquidation_replay(
            coverage_identity=future_coverage.coverage_identity,
            as_of_ms=4_000,
        )


def test_liquidation_batch_persists_coverage_last_and_is_idempotent(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    coverage = _coverage(observed_at_ms=2_000)
    events = (
        _event(
            event_at_ms=1_400,
            source_timestamp_ms=1_410,
            ingested_at_ms=1_420,
            source_row_index=2,
            side=LiquidatedPositionSide.SHORT,
        ),
        _event(
            event_at_ms=1_300,
            source_timestamp_ms=1_310,
            ingested_at_ms=1_320,
            source_row_index=1,
        ),
    )

    first = persist_liquidation_batch(
        store=store,
        events=events,
        coverage=coverage,
    )
    second = persist_liquidation_batch(
        store=store,
        events=events,
        coverage=coverage,
    )

    assert first.observed_events == 2
    assert first.liquidation_inserted == 2
    assert first.liquidation_unchanged == 0
    assert first.coverage_disposition is MarketTapeWriteDisposition.INSERTED
    assert first.inserted_total == 3

    assert second.observed_events == 2
    assert second.liquidation_inserted == 0
    assert second.liquidation_unchanged == 2
    assert second.coverage_disposition is MarketTapeWriteDisposition.UNCHANGED
    assert second.inserted_total == 0

    replay = store.liquidation_replay(
        coverage_identity=coverage.coverage_identity,
        as_of_ms=2_000,
    )
    assert replay.events == tuple(sorted(
        events,
        key=lambda item: (
            item.event_at_ms,
            item.source_timestamp_ms,
            item.source_row_index,
            item.liquidation_identity,
        ),
    ))


@pytest.mark.parametrize(
    ("event", "expected_message"),
    [
        (
            _event(
                event_at_ms=900,
                source_timestamp_ms=910,
                ingested_at_ms=920,
                source_row_index=1,
            ),
            "outside coverage window",
        ),
        (
            _event(
                event_at_ms=1_500,
                source_timestamp_ms=1_510,
                ingested_at_ms=2_100,
                source_row_index=2,
            ),
            "not observable by coverage timestamp",
        ),
    ],
)
def test_liquidation_batch_rejects_invalid_window_evidence_before_coverage_write(
    tmp_path,
    event,
    expected_message: str,
) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    coverage = _coverage(observed_at_ms=2_000)

    with pytest.raises(ValueError, match=expected_message):
        persist_liquidation_batch(
            store=store,
            events=(event,),
            coverage=coverage,
        )

    assert store.recent_liquidation_coverage(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
    ) == ()


def test_liquidation_batch_rejects_context_mismatch_before_any_write(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    coverage = _coverage(observed_at_ms=2_000)
    wrong_symbol = build_liquidation_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="ETHUSDT",
        liquidated_position_side=LiquidatedPositionSide.LONG,
        size=Decimal("1"),
        bankruptcy_price=Decimal("100"),
        event_at_ms=1_500,
        source_timestamp_ms=1_510,
        ingested_at_ms=1_520,
        source_row_index=1,
        source=DataSource.WEBSOCKET,
        adapter_version="bybit-liquidation-test/1",
    )

    with pytest.raises(ValueError, match="context mismatch"):
        persist_liquidation_batch(
            store=store,
            events=(wrong_symbol,),
            coverage=coverage,
        )

    counts = store.counts()
    assert counts.liquidations == 0
    assert counts.liquidation_coverage == 0


def test_empty_liquidation_batch_can_publish_observed_zero_event_coverage(
    tmp_path,
) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    coverage = _coverage(observed_at_ms=2_000)

    result = persist_liquidation_batch(
        store=store,
        events=(),
        coverage=coverage,
    )

    assert result.observed_events == 0
    assert result.liquidation_inserted == 0
    assert result.coverage_disposition is MarketTapeWriteDisposition.INSERTED
    replay = store.liquidation_replay(
        coverage_identity=coverage.coverage_identity,
        as_of_ms=2_000,
    )
    assert replay.events == ()
