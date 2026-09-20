import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.aggregation import aggregate_closed_15m
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.ledger.live_clock import (
    LiveFreezeStatus,
    freeze_live_candles,
    freeze_live_provider,
)
from crypto_signal.ledger.store import ImmutableSignalLedger, LedgerWriteDisposition

BASE_MS = 900_000
START_MS = int(datetime(2026, 9, 10, tzinfo=UTC).timestamp() * 1000)


class FakeAdapter:
    def __init__(self, items: tuple[Candle, ...]) -> None:
        self.items = items
        self.calls = 0

    async def fetch_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> tuple[Candle, ...]:
        self.calls += 1
        assert symbol == "BTCUSDT"
        assert timeframe == "15m"
        assert limit >= len(self.items)
        assert start_ms is None
        assert end_ms is None
        return self.items


def market_candles(
    *,
    closed_count: int = 120,
) -> tuple[Candle, ...]:
    output: list[Candle] = []
    for index in range(closed_count):
        block = index % 16
        base = Decimal(1000 + (index // 16) * 3)
        if block in {3, 4, 5}:
            base += Decimal(25)
        elif block in {10, 11, 12}:
            base -= Decimal(21)
        close = base + (Decimal(4) if index % 2 == 0 else Decimal(-4))
        open_time_ms = START_MS + index * BASE_MS
        close_time_ms = open_time_ms + BASE_MS - 1
        output.append(
            Candle(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol="BTCUSDT",
                timeframe="15m",
                open_time_ms=open_time_ms,
                close_time_ms=close_time_ms,
                open=base,
                high=max(base, close) + Decimal(3),
                low=min(base, close) - Decimal(3),
                close=close,
                volume=Decimal(1),
                quote_volume=Decimal(1000),
                trade_count=None,
                is_closed=True,
                source=DataSource.REST,
                source_timestamp_ms=close_time_ms + 1,
                ingested_at_ms=close_time_ms + 2,
                adapter_version="fake/1",
            )
        )

    open_time_ms = START_MS + closed_count * BASE_MS
    output.append(
        Candle(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
            open_time_ms=open_time_ms,
            close_time_ms=open_time_ms + BASE_MS - 1,
            open=Decimal(1000),
            high=Decimal(1005),
            low=Decimal(995),
            close=Decimal(1001),
            volume=Decimal(1),
            quote_volume=Decimal(1000),
            trade_count=None,
            is_closed=False,
            source=DataSource.REST,
            source_timestamp_ms=open_time_ms + 100,
            ingested_at_ms=open_time_ms + 100,
            adapter_version="fake/1",
        )
    )
    return tuple(output)


def test_live_clock_freezes_once_per_closed_source_cutoff(
    tmp_path: Path,
) -> None:
    items = market_candles()
    adapter = FakeAdapter(items)
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    now_value = max(candle.ingested_at_ms for candle in items) + 1_000

    first = asyncio.run(
        freeze_live_provider(
            adapter=adapter,
            ledger=ledger,
            limit=len(items),
            minimum_closed_candles=100,
            now_ms=lambda: now_value,
        )
    )
    second = asyncio.run(
        freeze_live_provider(
            adapter=adapter,
            ledger=ledger,
            limit=len(items),
            minimum_closed_candles=100,
            now_ms=lambda: now_value + 5_000,
        )
    )

    assert first.status is LiveFreezeStatus.FROZEN
    assert first.signal_freeze_identity is not None
    assert first.bundle_identity is not None
    assert first.signal_state is not None
    assert first.confluence_score is not None
    assert first.lifecycle_disposition is LedgerWriteDisposition.INSERTED
    assert first.source_cutoff_open_time_ms == items[-2].open_time_ms

    assert second.status is LiveFreezeStatus.ALREADY_FROZEN
    assert second.source_cutoff_open_time_ms == first.source_cutoff_open_time_ms
    assert second.signal_freeze_identity is None
    assert ledger.count_freezes() == 1
    assert ledger.count_lifecycle_evaluations() == 1
    assert adapter.calls == 2


def test_live_clock_rejects_gap_before_freeze(tmp_path: Path) -> None:
    items = list(market_candles())
    del items[40]
    adapter = FakeAdapter(tuple(items))
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    now_value = max(candle.ingested_at_ms for candle in items) + 1_000

    with pytest.raises(ValueError, match="refuses candle gaps"):
        asyncio.run(
            freeze_live_provider(
                adapter=adapter,
                ledger=ledger,
                limit=len(items),
                minimum_closed_candles=100,
                now_ms=lambda: now_value,
            )
        )

    assert ledger.count_freezes() == 0


def test_live_clock_requires_minimum_history(tmp_path: Path) -> None:
    items = market_candles(closed_count=80)
    adapter = FakeAdapter(items)
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    now_value = max(candle.ingested_at_ms for candle in items) + 1_000

    with pytest.raises(ValueError, match="insufficient closed candle history"):
        asyncio.run(
            freeze_live_provider(
                adapter=adapter,
                ledger=ledger,
                limit=len(items),
                minimum_closed_candles=100,
                now_ms=lambda: now_value,
            )
        )

    assert ledger.count_freezes() == 0


def test_direct_candle_freeze_matches_provider_path_exactly(
    tmp_path: Path,
) -> None:
    items = market_candles()
    now_value = max(candle.ingested_at_ms for candle in items) + 1_000

    provider_ledger = ImmutableSignalLedger(
        tmp_path / "provider.sqlite3"
    )
    direct_ledger = ImmutableSignalLedger(
        tmp_path / "direct.sqlite3"
    )

    provider_result = asyncio.run(
        freeze_live_provider(
            adapter=FakeAdapter(items),
            ledger=provider_ledger,
            limit=len(items),
            minimum_closed_candles=100,
            now_ms=lambda: now_value,
        )
    )
    direct_result = freeze_live_candles(
        candles=items,
        ledger=direct_ledger,
        minimum_closed_candles=100,
        now_ms=lambda: now_value,
    )

    assert provider_result == direct_result
    assert provider_ledger.list_freezes() == direct_ledger.list_freezes()
    assert (
        provider_ledger.list_lifecycle_evaluations()
        == direct_ledger.list_lifecycle_evaluations()
    )


def test_direct_candle_freeze_preserves_source_cutoff_idempotence(
    tmp_path: Path,
) -> None:
    items = market_candles()
    ledger = ImmutableSignalLedger(tmp_path / "direct.sqlite3")
    now_value = max(candle.ingested_at_ms for candle in items) + 1_000

    first = freeze_live_candles(
        candles=items,
        ledger=ledger,
        minimum_closed_candles=100,
        now_ms=lambda: now_value,
    )
    second = freeze_live_candles(
        candles=items,
        ledger=ledger,
        minimum_closed_candles=100,
        now_ms=lambda: now_value + 5_000,
    )

    assert first.status is LiveFreezeStatus.FROZEN
    assert second.status is LiveFreezeStatus.ALREADY_FROZEN
    assert second.source_cutoff_open_time_ms == first.source_cutoff_open_time_ms
    assert ledger.count_freezes() == 1
    assert ledger.count_lifecycle_evaluations() == 1


def test_direct_candle_freeze_accepts_canonical_aggregated_history(
    tmp_path: Path,
) -> None:
    base = tuple(
        item
        for item in market_candles(closed_count=120)
        if item.is_closed
    )
    aggregation = aggregate_closed_15m(
        base,
        target_timeframe="1h",
    )
    assert aggregation.incomplete == ()
    assert len(aggregation.candles) == 30

    now_value = max(
        candle.ingested_at_ms for candle in aggregation.candles
    ) + 1_000
    ledger = ImmutableSignalLedger(tmp_path / "aggregated.sqlite3")

    result = freeze_live_candles(
        candles=aggregation.candles,
        ledger=ledger,
        minimum_closed_candles=20,
        now_ms=lambda: now_value,
    )

    assert result.status is LiveFreezeStatus.FROZEN
    freeze = ledger.list_freezes()[0]
    assert freeze.timeframe == "1h"
    assert freeze.source_cutoff_open_time_ms == (
        aggregation.candles[-1].open_time_ms
    )
    assert ledger.count_lifecycle_evaluations() == 1


def test_direct_candle_freeze_rejects_non_positive_minimum(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="minimum closed candle count must be positive",
    ):
        freeze_live_candles(
            candles=market_candles(),
            ledger=ImmutableSignalLedger(tmp_path / "invalid.sqlite3"),
            minimum_closed_candles=0,
        )
