from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest

from crypto_signal.data.adapters.bybit_liquidation_ws import (
    BYBIT_LINEAR_PUBLIC_WS_URL,
    BybitLinearLiquidationStream,
    BybitLiquidationWireBatch,
    build_bybit_liquidation_wire_batch,
    bybit_liquidation_subscription,
)
from crypto_signal.data.liquidation_wire_collection import (
    persist_bybit_liquidation_wire_stream,
)
from crypto_signal.data.liquidations import LiquidatedPositionSide
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.raw_market_tape import RawMarketTapeStore


def _payload(
    *,
    ts: int = 2_000,
    symbol: str = "BTCUSDT",
) -> dict[str, object]:
    return {
        "topic": f"allLiquidation.{symbol}",
        "type": "snapshot",
        "ts": ts,
        "data": [
            {
                "T": ts - 400,
                "s": symbol,
                "S": "Buy",
                "v": "0.25",
                "p": "100.5",
            },
            {
                "T": ts - 100,
                "s": symbol,
                "S": "Sell",
                "v": "0.10",
                "p": "101.0",
            },
        ],
    }


def test_official_linear_topic_contract_is_explicit_and_deterministic() -> None:
    assert BybitLinearLiquidationStream.WS_URL == BYBIT_LINEAR_PUBLIC_WS_URL
    assert BYBIT_LINEAR_PUBLIC_WS_URL == (
        "wss://stream.bybit.com/v5/public/linear"
    )
    assert bybit_liquidation_subscription(("BTCUSDT", "ETHUSDT")) == (
        '{"args":["allLiquidation.BTCUSDT",'
        '"allLiquidation.ETHUSDT"],"op":"subscribe"}'
    )


def test_wire_batch_maps_position_side_and_message_coverage() -> None:
    batch = build_bybit_liquidation_wire_batch(
        _payload(),
        expected_symbol="BTCUSDT",
        ingested_at_ms=2_010,
    )

    assert batch.symbol == "BTCUSDT"
    assert batch.source_timestamp_ms == 2_000
    assert batch.event_at_ms == 1_900
    assert batch.ingested_at_ms == 2_010
    assert len(batch.events) == 2
    assert batch.events[0].liquidated_position_side is LiquidatedPositionSide.LONG
    assert batch.events[1].liquidated_position_side is LiquidatedPositionSide.SHORT
    assert batch.events[0].bankruptcy_notional == Decimal("25.125")
    assert batch.coverage.coverage_start_ms == 1_600
    assert batch.coverage.coverage_end_ms == 2_000
    assert batch.coverage.observed_at_ms == 2_010


def test_empty_provider_message_does_not_invent_zero_event_coverage() -> None:
    payload = _payload()
    payload["data"] = []

    with pytest.raises(ValueError, match="silence is not converted"):
        build_bybit_liquidation_wire_batch(
            payload,
            expected_symbol="BTCUSDT",
            ingested_at_ms=2_010,
        )


def test_non_usdt_symbol_is_rejected_by_development_collector() -> None:
    with pytest.raises(ValueError, match="USDT linear"):
        bybit_liquidation_subscription(("BTCUSD",))


async def _batches() -> AsyncIterator[BybitLiquidationWireBatch]:
    yield build_bybit_liquidation_wire_batch(
        _payload(ts=2_000),
        expected_symbol="BTCUSDT",
        ingested_at_ms=2_010,
    )
    yield build_bybit_liquidation_wire_batch(
        _payload(ts=3_000),
        expected_symbol="BTCUSDT",
        ingested_at_ms=3_010,
    )


@pytest.mark.anyio
async def test_wire_collection_persists_raw_before_normalized_batch(
    tmp_path,
) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    raw_store = RawMarketTapeStore(tmp_path / "raw_market_tape.sqlite3")

    result = await persist_bybit_liquidation_wire_stream(
        store=store,
        raw_store=raw_store,
        batches=_batches(),
        max_messages=1,
    )

    assert result.observed_messages == 1
    assert result.raw_inserted == 1
    assert result.raw_unchanged == 0
    assert result.liquidation_inserted == 2
    assert result.liquidation_unchanged == 0
    assert result.coverage_inserted == 1
    assert result.coverage_unchanged == 0
    assert result.normalized_inserted_total == 3
    assert raw_store.count() == 1
    assert store.counts().liquidations == 2
    assert store.counts().liquidation_coverage == 1
    assert raw_store.quick_check() is True
    assert store.quick_check() is True


@pytest.mark.anyio
async def test_wire_collection_retry_is_append_only_and_idempotent(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    raw_store = RawMarketTapeStore(tmp_path / "raw_market_tape.sqlite3")

    first = await persist_bybit_liquidation_wire_stream(
        store=store,
        raw_store=raw_store,
        batches=_batches(),
        max_messages=1,
    )
    second = await persist_bybit_liquidation_wire_stream(
        store=store,
        raw_store=raw_store,
        batches=_batches(),
        max_messages=1,
    )

    assert first.raw_inserted == 1
    assert second.raw_inserted == 0
    assert second.raw_unchanged == 1
    assert second.liquidation_inserted == 0
    assert second.liquidation_unchanged == 2
    assert second.coverage_inserted == 0
    assert second.coverage_unchanged == 1
    assert raw_store.count() == 1
    assert store.counts().liquidations == 2
    assert store.counts().liquidation_coverage == 1


@pytest.mark.anyio
async def test_wire_collection_requires_positive_bound_when_provided(
    tmp_path,
) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    raw_store = RawMarketTapeStore(tmp_path / "raw_market_tape.sqlite3")
    with pytest.raises(ValueError, match="max_messages"):
        await persist_bybit_liquidation_wire_stream(
            store=store,
            raw_store=raw_store,
            batches=_batches(),
            max_messages=0,
        )
