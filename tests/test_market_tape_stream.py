from __future__ import annotations

from pathlib import Path

import pytest

from crypto_signal.data.market_tape_stream import (
    MarketTapeChannel,
    MarketTapeSequenceGuard,
    MarketTapeSequenceStatus,
    MarketTapeStreamConflictError,
    MarketTapeStreamStore,
    build_raw_market_event,
)
from crypto_signal.data.models import Exchange, MarketType


def _event(
    *,
    first: int | None,
    last: int | None,
    event_at_ms: int = 1_000,
    payload_value: str = "a",
    channel: MarketTapeChannel = MarketTapeChannel.ORDERBOOK_DELTA,
):
    return build_raw_market_event(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        channel=channel,
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms,
        ingested_at_ms=event_at_ms + 1,
        first_sequence=first,
        last_sequence=last,
        payload={"value": payload_value},
        adapter_version="test-ws/1",
    )


def test_raw_stream_store_is_append_only_and_replay_idempotent(tmp_path: Path) -> None:
    store = MarketTapeStreamStore(tmp_path / "market_tape.sqlite3")
    event = _event(first=10, last=12)

    assert store.append(event) is True
    assert store.append(event) is False
    assert store.count() == 1
    assert store.quick_check() is True
    assert store.latest_event_at_ms() == 1_000
    assert store.recent(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        channel=MarketTapeChannel.ORDERBOOK_DELTA,
    ) == (event,)


def test_raw_stream_same_sequence_range_conflict_fails_closed(tmp_path: Path) -> None:
    store = MarketTapeStreamStore(tmp_path / "market_tape.sqlite3")
    first = _event(first=10, last=12, payload_value="a")
    conflict = _event(first=10, last=12, payload_value="b", event_at_ms=1_001)

    assert store.append(first) is True
    with pytest.raises(MarketTapeStreamConflictError):
        store.append(conflict)
    assert store.count() == 1


def test_raw_stream_store_coexists_with_core_market_tape_meta(tmp_path: Path) -> None:
    from crypto_signal.data.market_tape import MarketTapeStore

    path = tmp_path / "market_tape.sqlite3"
    core = MarketTapeStore(path)
    core.initialize()

    stream = MarketTapeStreamStore(path)
    stream.initialize()

    assert core.quick_check() is True
    assert stream.quick_check() is True
    assert stream.count() == 0


def test_sequence_guard_classifies_initial_contiguous_overlap_and_stale() -> None:
    guard = MarketTapeSequenceGuard()

    initial = guard.observe(_event(first=100, last=105))
    assert initial.status is MarketTapeSequenceStatus.INITIAL
    assert initial.expected_next_sequence == 106

    contiguous = guard.observe(_event(first=106, last=110, event_at_ms=2_000))
    assert contiguous.status is MarketTapeSequenceStatus.CONTIGUOUS
    assert contiguous.previous_last_sequence == 105
    assert contiguous.expected_next_sequence == 111

    overlap = guard.observe(_event(first=109, last=115, event_at_ms=3_000))
    assert overlap.status is MarketTapeSequenceStatus.OVERLAP
    assert overlap.previous_last_sequence == 110
    assert overlap.expected_next_sequence == 116

    stale = guard.observe(_event(first=109, last=112, event_at_ms=4_000))
    assert stale.status is MarketTapeSequenceStatus.DUPLICATE_OR_STALE
    assert stale.previous_last_sequence == 115
    assert stale.expected_next_sequence == 116


def test_sequence_guard_gap_requires_resync_and_does_not_advance_state() -> None:
    guard = MarketTapeSequenceGuard()
    guard.observe(_event(first=100, last=105))

    gap = guard.observe(_event(first=110, last=115, event_at_ms=2_000))
    assert gap.status is MarketTapeSequenceStatus.GAP
    assert gap.requires_resync is True
    assert gap.expected_next_sequence == 106

    recovery = guard.observe(_event(first=106, last=109, event_at_ms=3_000))
    assert recovery.status is MarketTapeSequenceStatus.CONTIGUOUS
    assert recovery.previous_last_sequence == 105


def test_sequence_guard_unsequenced_event_does_not_create_fake_sequence() -> None:
    guard = MarketTapeSequenceGuard()
    observation = guard.observe(
        _event(
            first=None,
            last=None,
            channel=MarketTapeChannel.PUBLIC_TRADE,
        )
    )
    assert observation.status is MarketTapeSequenceStatus.UNSEQUENCED
    assert observation.expected_next_sequence is None


def test_sequence_guard_reset_from_snapshot() -> None:
    guard = MarketTapeSequenceGuard()
    guard.reset(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        channel=MarketTapeChannel.ORDERBOOK_DELTA,
        last_sequence=500,
    )

    next_event = guard.observe(_event(first=501, last=510))
    assert next_event.status is MarketTapeSequenceStatus.CONTIGUOUS
    assert next_event.previous_last_sequence == 500


def test_raw_event_ingestion_time_does_not_change_market_identity() -> None:
    first = build_raw_market_event(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        channel=MarketTapeChannel.PUBLIC_TRADE,
        event_at_ms=1_000,
        source_timestamp_ms=1_001,
        ingested_at_ms=1_010,
        first_sequence=10,
        last_sequence=10,
        payload={"event": "same"},
        adapter_version="test-ws/1",
    )
    later_replay = build_raw_market_event(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        channel=MarketTapeChannel.PUBLIC_TRADE,
        event_at_ms=1_000,
        source_timestamp_ms=1_001,
        ingested_at_ms=2_000,
        first_sequence=10,
        last_sequence=10,
        payload={"event": "same"},
        adapter_version="test-ws/1",
    )

    assert first.event_identity == later_replay.event_identity
