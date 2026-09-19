from decimal import Decimal

import pytest

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType


def make_candle(**changes: object) -> Candle:
    values: dict[str, object] = {
        "exchange": Exchange.BYBIT,
        "market_type": MarketType.SPOT,
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "open_time_ms": 1_710_000_000_000,
        "close_time_ms": 1_710_000_899_999,
        "open": Decimal(100),
        "high": Decimal(110),
        "low": Decimal(90),
        "close": Decimal(105),
        "volume": Decimal("12.5"),
        "quote_volume": Decimal(1250),
        "trade_count": None,
        "is_closed": True,
        "source": DataSource.REST,
        "source_timestamp_ms": 1_710_001_000_000,
        "ingested_at_ms": 1_710_001_000_001,
        "adapter_version": "test/1",
    }
    values.update(changes)
    return Candle(**values)  # type: ignore[arg-type]


def test_candle_identity_is_provider_neutral_key() -> None:
    candle = make_candle()
    assert candle.identity == ("bybit", "spot", "BTCUSDT", "15m", 1_710_000_000_000)


@pytest.mark.parametrize(
    ("field", "value"),
    [("high", Decimal(99)), ("low", Decimal(106)), ("volume", Decimal(-1))],
)
def test_candle_rejects_impossible_market_data(field: str, value: Decimal) -> None:
    with pytest.raises(ValueError):
        make_candle(**{field: value})
