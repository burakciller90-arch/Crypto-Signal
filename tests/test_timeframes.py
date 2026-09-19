from datetime import UTC, datetime

import pytest

from crypto_signal.data.timeframes import bucket_open_ms, is_aligned_open, spec


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


def test_weekly_grid_is_monday_utc_not_unix_epoch_week() -> None:
    monday = int(datetime(2026, 9, 14, tzinfo=UTC).timestamp() * 1000)
    thursday = int(datetime(2026, 9, 17, tzinfo=UTC).timestamp() * 1000)
    wednesday = int(datetime(2026, 9, 16, 12, 30, tzinfo=UTC).timestamp() * 1000)

    assert is_aligned_open(monday, "1W") is True
    assert is_aligned_open(thursday, "1W") is False
    assert bucket_open_ms(wednesday, "1W") == monday


def test_intraday_and_daily_grids_keep_zero_anchor() -> None:
    midnight = int(datetime(2026, 9, 20, tzinfo=UTC).timestamp() * 1000)

    assert is_aligned_open(midnight, "1D") is True
    assert is_aligned_open(midnight + 3_600_000, "1h") is True
    assert bucket_open_ms(midnight + 5_400_000, "1h") == midnight + 3_600_000
