from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_collection import (
    collect_bybit_market_tape_snapshot,
)
from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType


class FakeMicrostructureAdapter:
    async def fetch_snapshot(
        self,
        *,
        symbol: str,
        book_depth: int = 25,
        trade_limit: int = 60,
    ):
        assert book_depth == 50
        assert trade_limit == 60
        book = build_orderbook_snapshot(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol=symbol,
            event_at_ms=1_000,
            source_timestamp_ms=1_001,
            response_time_ms=1_002,
            ingested_at_ms=1_003,
            update_id=10,
            sequence=20,
            bids=(OrderBookLevel(Decimal(100), Decimal(2)),),
            asks=(OrderBookLevel(Decimal(101), Decimal(3)),),
            source=DataSource.REST,
            adapter_version="fake-microstructure/1",
        )
        trades = (
            build_public_trade_observation(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol=symbol,
                exec_id="trade-1",
                sequence=30,
                aggressor_side=AggressorSide.BUY,
                price=Decimal("100.5"),
                size=Decimal("0.1"),
                event_at_ms=1_001,
                source_timestamp_ms=1_002,
                ingested_at_ms=1_003,
                is_block_trade=False,
                is_rpi_trade=False,
                source=DataSource.REST,
                adapter_version="fake-microstructure/1",
            ),
        )
        return book, trades


class FakeDerivativesAdapter:
    async def fetch_observations(
        self,
        *,
        symbol: str,
        oi_interval: str = "15min",
        oi_limit: int = 8,
        end_ms: int | None = None,
    ):
        assert oi_interval == "15min"
        assert oi_limit == 16
        assert end_ms is None
        return (
            build_derivatives_observation(
                exchange=Exchange.BYBIT,
                instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
                symbol=symbol,
                event_at_ms=1_002,
                funding_rate=Decimal("0.0001"),
                open_interest=Decimal(1_000),
                mark_price=Decimal("100.7"),
                index_price=Decimal("100.5"),
                funding_interval_hours=8,
                source=DataSource.REST,
                source_timestamp_ms=1_003,
                ingested_at_ms=1_004,
                adapter_version="fake-derivatives/1",
            ),
        )


@pytest.mark.anyio
async def test_market_tape_collection_persists_existing_engine_inputs(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")

    result = await collect_bybit_market_tape_snapshot(
        store=store,
        microstructure_adapter=FakeMicrostructureAdapter(),
        derivatives_adapter=FakeDerivativesAdapter(),
        symbol="BTCUSDT",
        book_depth=50,
        trade_limit=60,
        oi_interval="15min",
        oi_limit=16,
    )

    assert result.symbol == "BTCUSDT"
    assert result.inserted_total == 3
    assert result.trade_inserted == 1
    assert result.derivatives_inserted == 1
    assert store.counts().total == 3


@pytest.mark.anyio
async def test_market_tape_collection_is_idempotent_on_replay(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    kwargs = {
        "store": store,
        "microstructure_adapter": FakeMicrostructureAdapter(),
        "derivatives_adapter": FakeDerivativesAdapter(),
        "symbol": "BTCUSDT",
        "book_depth": 50,
        "trade_limit": 60,
        "oi_interval": "15min",
        "oi_limit": 16,
    }

    first = await collect_bybit_market_tape_snapshot(**kwargs)
    second = await collect_bybit_market_tape_snapshot(**kwargs)

    assert first.inserted_total == 3
    assert second.inserted_total == 0
    assert second.trade_unchanged == 1
    assert second.derivatives_unchanged == 1
    assert store.counts().total == 3
