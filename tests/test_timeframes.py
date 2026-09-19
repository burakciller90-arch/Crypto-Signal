import pytest

from crypto_signal.data.timeframes import spec


def test_v1_timeframe_mappings() -> None:
    assert spec("15m").bybit_interval == "15"
    assert spec("15m").binance_interval == "15m"
    assert spec("1h").duration_ms == 3_600_000
    assert spec("4h").bybit_interval == "240"
    assert spec("4h").binance_interval == "4h"
    assert spec("1D").bybit_interval == "D"
    assert spec("1D").binance_interval == "1d"
    assert spec("1W").bybit_interval == "W"
    assert spec("1W").binance_interval == "1w"


def test_unsupported_timeframe_is_explicit() -> None:
    with pytest.raises(ValueError, match="unsupported V1 timeframe"):
        spec("5m")
