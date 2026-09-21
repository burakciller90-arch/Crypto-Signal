from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.models import MethodologyKind
from crypto_signal.data.cross_market import (
    CrossMarketSeries,
    CrossMarketUnit,
    build_cross_market_daily_record,
    build_cross_market_window_observation,
)
from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.intelligence.cross_market_context import (
    CROSS_MARKET_ENGINE_VERSION,
    CROSS_MARKET_FREEZE_SCHEMA_VERSION,
    CrossMarketLabel,
    CryptoDirection,
    RatesDirection,
    VixDirection,
    analyze_cross_market_context,
    build_cross_market_evidence_freeze,
)

_DAY_MS = 24 * 60 * 60 * 1000
_AS_OF_MS = 196 * _DAY_MS
_DAYS = (190, 191, 192, 193, 194)


def _macro_observation(
    *,
    series: CrossMarketSeries,
    values: tuple[Decimal, ...],
    days: tuple[int, ...] = _DAYS,
    observed_at_ms: int = _AS_OF_MS,
):
    unit = (
        CrossMarketUnit.INDEX_POINTS
        if series is CrossMarketSeries.CBOE_VIX_CLOSE
        else CrossMarketUnit.PERCENT
    )
    records = tuple(
        build_cross_market_daily_record(
            series=series,
            unit=unit,
            day_start_ms=day * _DAY_MS,
            value=value,
        )
        for day, value in zip(days, values, strict=True)
    )
    return build_cross_market_window_observation(
        series=series,
        unit=unit,
        observed_at_ms=observed_at_ms,
        records=records,
        source=DataSource.REST,
        adapter_version="cross-market-engine-test/1",
    )


def _vix(
    *,
    values: tuple[Decimal, ...] = (
        Decimal("20"),
        Decimal("19"),
        Decimal("18"),
        Decimal("17"),
        Decimal("16"),
    ),
    days: tuple[int, ...] = _DAYS,
    observed_at_ms: int = _AS_OF_MS,
):
    return _macro_observation(
        series=CrossMarketSeries.CBOE_VIX_CLOSE,
        values=values,
        days=days,
        observed_at_ms=observed_at_ms,
    )


def _treasury(
    *,
    values: tuple[Decimal, ...] = (
        Decimal("4.50"),
        Decimal("4.55"),
        Decimal("4.60"),
        Decimal("4.65"),
        Decimal("4.70"),
    ),
    days: tuple[int, ...] = _DAYS,
    observed_at_ms: int = _AS_OF_MS,
):
    return _macro_observation(
        series=CrossMarketSeries.US_TREASURY_10Y_YIELD,
        values=values,
        days=days,
        observed_at_ms=observed_at_ms,
    )


def _btc_candle(
    day: int,
    close: Decimal,
    *,
    available_at_ms: int = _AS_OF_MS,
    symbol: str = "BTCUSDT",
    timeframe: str = "1D",
) -> Candle:
    open_price = close - Decimal("0.5")
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        timeframe=timeframe,
        open_time_ms=day * _DAY_MS,
        close_time_ms=(day + 1) * _DAY_MS - 1,
        open=open_price,
        high=close + Decimal("1"),
        low=open_price - Decimal("1"),
        close=close,
        volume=Decimal("10"),
        quote_volume=Decimal("1000"),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=available_at_ms,
        ingested_at_ms=available_at_ms,
        adapter_version="bybit-v5-spot/test",
    )


def _btc_rising() -> tuple[Candle, ...]:
    closes = (
        Decimal("100"),
        Decimal("101"),
        Decimal("102"),
        Decimal("103"),
        Decimal("105"),
    )
    return tuple(
        _btc_candle(day, close)
        for day, close in zip(_DAYS, closes, strict=True)
    )


def test_relief_alignment_is_deterministic_and_frozen() -> None:
    btc = _btc_rising()
    vix = _vix()
    treasury = _treasury()

    first = build_cross_market_evidence_freeze(
        btc,
        (vix,),
        (treasury,),
        as_of_ms=_AS_OF_MS,
    )
    second = build_cross_market_evidence_freeze(
        btc,
        (vix,),
        (treasury,),
        as_of_ms=_AS_OF_MS,
    )

    assert first == second
    assert first.schema_version == CROSS_MARKET_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == CROSS_MARKET_ENGINE_VERSION
    assert first.analysis.label is CrossMarketLabel.BTC_VIX_RELIEF_ALIGNMENT
    assert first.analysis.crypto_direction is CryptoDirection.RISING
    assert first.analysis.vix_direction is VixDirection.FALLING
    assert first.analysis.rates_direction is RatesDirection.RISING
    assert first.analysis.metrics is not None
    assert first.analysis.metrics.btc_return_pct == Decimal("5")
    assert first.analysis.metrics.vix_change_pct == Decimal("-20")
    assert first.analysis.metrics.treasury_10y_change_bps == Decimal("20")
    assert first.analysis.metrics.common_session_count == 5
    assert first.analysis.uncertainty_flags == ()
    assert len(first.freeze_identity) == 64


def test_stress_and_same_direction_labels_are_descriptive_only() -> None:
    falling_btc = tuple(
        _btc_candle(day, close)
        for day, close in zip(
            _DAYS,
            (
                Decimal("100"),
                Decimal("99"),
                Decimal("98"),
                Decimal("97"),
                Decimal("95"),
            ),
            strict=True,
        )
    )
    rising_vix = _vix(
        values=(
            Decimal("16"),
            Decimal("17"),
            Decimal("18"),
            Decimal("19"),
            Decimal("20"),
        )
    )
    stress = analyze_cross_market_context(
        falling_btc,
        (rising_vix,),
        (_treasury(),),
        as_of_ms=_AS_OF_MS,
    )
    same_direction = analyze_cross_market_context(
        _btc_rising(),
        (rising_vix,),
        (_treasury(),),
        as_of_ms=_AS_OF_MS,
    )

    assert stress.label is CrossMarketLabel.BTC_VIX_STRESS_ALIGNMENT
    assert stress.crypto_direction is CryptoDirection.FALLING
    assert stress.vix_direction is VixDirection.RISING
    assert same_direction.label is CrossMarketLabel.BTC_VIX_SAME_DIRECTION
    assert same_direction.crypto_direction is CryptoDirection.RISING
    assert same_direction.vix_direction is VixDirection.RISING


def test_missing_or_stale_macro_evidence_is_unresolved() -> None:
    missing = analyze_cross_market_context(
        _btc_rising(),
        (),
        (_treasury(),),
        as_of_ms=_AS_OF_MS,
    )
    stale_vix = _vix(
        days=(188, 189, 190, 191, 192),
        observed_at_ms=_AS_OF_MS - 2 * _DAY_MS,
    )
    stale = analyze_cross_market_context(
        _btc_rising(),
        (stale_vix,),
        (_treasury(),),
        as_of_ms=_AS_OF_MS,
    )

    assert missing.label is CrossMarketLabel.UNRESOLVED
    assert missing.metrics is None
    assert "vix_observation_unavailable_at_as_of" in missing.uncertainty_flags
    assert stale.label is CrossMarketLabel.UNRESOLVED
    assert stale.metrics is None
    assert "stale_vix_observation" in stale.uncertainty_flags


def test_incomplete_macro_or_btc_alignment_fails_closed() -> None:
    short_vix = _vix(
        values=(
            Decimal("20"),
            Decimal("19"),
            Decimal("18"),
            Decimal("17"),
        ),
        days=(191, 192, 193, 194),
    )
    macro_gap = analyze_cross_market_context(
        _btc_rising(),
        (short_vix,),
        (_treasury(),),
        as_of_ms=_AS_OF_MS,
    )
    missing_btc = analyze_cross_market_context(
        _btc_rising()[:-1],
        (_vix(),),
        (_treasury(),),
        as_of_ms=_AS_OF_MS,
    )

    assert macro_gap.label is CrossMarketLabel.UNRESOLVED
    assert macro_gap.metrics is None
    assert macro_gap.uncertainty_flags == (
        "insufficient_common_macro_sessions",
    )
    assert missing_btc.label is CrossMarketLabel.UNRESOLVED
    assert missing_btc.metrics is None
    assert missing_btc.uncertainty_flags == (
        "incomplete_btc_macro_alignment",
    )


def test_future_ingestion_cannot_change_historical_freeze() -> None:
    baseline = build_cross_market_evidence_freeze(
        _btc_rising(),
        (_vix(),),
        (_treasury(),),
        as_of_ms=_AS_OF_MS,
    )
    future_vix = _vix(
        values=(
            Decimal("40"),
            Decimal("42"),
            Decimal("44"),
            Decimal("46"),
            Decimal("48"),
        ),
        observed_at_ms=_AS_OF_MS + 10_000,
    )
    future_treasury = _treasury(
        values=(
            Decimal("6.0"),
            Decimal("6.1"),
            Decimal("6.2"),
            Decimal("6.3"),
            Decimal("6.4"),
        ),
        observed_at_ms=_AS_OF_MS + 10_000,
    )
    future_btc = tuple(
        _btc_candle(
            day,
            Decimal("200") + Decimal(offset),
            available_at_ms=_AS_OF_MS + 10_000,
        )
        for offset, day in enumerate(_DAYS)
    )

    with_future = build_cross_market_evidence_freeze(
        _btc_rising() + future_btc,
        (_vix(), future_vix),
        (_treasury(), future_treasury),
        as_of_ms=_AS_OF_MS,
    )

    assert with_future == baseline


def test_duplicate_observations_and_identity_tampering_fail_closed() -> None:
    vix = _vix()
    treasury = _treasury()

    with pytest.raises(ValueError, match="duplicate VIX"):
        analyze_cross_market_context(
            _btc_rising(),
            (vix, vix),
            (treasury,),
            as_of_ms=_AS_OF_MS,
        )

    freeze = build_cross_market_evidence_freeze(
        _btc_rising(),
        (vix,),
        (treasury,),
        as_of_ms=_AS_OF_MS,
    )
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_wrong_macro_or_btc_context_is_rejected() -> None:
    treasury_as_vix = _treasury()
    with pytest.raises(ValueError, match="VIX input"):
        analyze_cross_market_context(
            _btc_rising(),
            (treasury_as_vix,),
            (_treasury(),),
            as_of_ms=_AS_OF_MS,
        )

    bad_symbol = tuple(
        _btc_candle(day, Decimal("100"), symbol="ETHUSDT")
        for day in _DAYS
    )
    with pytest.raises(ValueError, match="BTCUSDT"):
        analyze_cross_market_context(
            bad_symbol,
            (_vix(),),
            (_treasury(),),
            as_of_ms=_AS_OF_MS,
        )


def test_stage8_cross_market_is_observation_only_ablation_zero() -> None:
    assert set(MethodologyKind) == {
        MethodologyKind.PRICE_ACTION,
        MethodologyKind.HARMONIC,
        MethodologyKind.ELLIOTT,
    }

    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/crypto_signal/confluence/models.py",
        "src/crypto_signal/confluence/adapters.py",
        "src/crypto_signal/ledger/bundle.py",
        "src/crypto_signal/signals/models.py",
        "src/crypto_signal/paper/mission_control.py",
    ):
        source = (root / relative).read_text()
        assert "crypto_signal.intelligence.cross_market_context" not in source
