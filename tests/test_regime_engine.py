from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.models import MethodologyKind
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.intelligence.regime import (
    DEFAULT_REGIME_CONFIG,
    REGIME_ENGINE_VERSION,
    REGIME_FREEZE_SCHEMA_VERSION,
    RegimeConfig,
    RegimeLabel,
    VolatilityState,
    analyze_regime,
    build_regime_evidence_freeze,
)

_STEP_MS = 15 * 60_000


def _candle(
    *,
    index: int,
    close: Decimal,
    range_width: Decimal = Decimal(1),
    symbol: str = "BTCUSDT",
    ingested_at_ms: int | None = None,
    source_timestamp_ms: int | None = None,
) -> Candle:
    open_time_ms = index * _STEP_MS
    close_time_ms = open_time_ms + _STEP_MS - 1
    half = range_width / Decimal(2)
    source_ms = (
        close_time_ms
        if source_timestamp_ms is None
        else source_timestamp_ms
    )
    ingested_ms = close_time_ms if ingested_at_ms is None else ingested_at_ms
    return Candle(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol=symbol,
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=close,
        high=close + half,
        low=close - half,
        close=close,
        volume=Decimal(1),
        quote_volume=close,
        trade_count=1,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingested_ms,
        adapter_version="regime-test/1",
    )


def _series(
    closes: list[Decimal],
    *,
    expanded_last_four: bool = False,
) -> tuple[Candle, ...]:
    return tuple(
        _candle(
            index=index,
            close=close,
            range_width=(
                Decimal(6)
                if expanded_last_four and index >= len(closes) - 4
                else Decimal(1)
            ),
        )
        for index, close in enumerate(closes)
    )


def _as_of(candles: tuple[Candle, ...]) -> int:
    return candles[-1].close_time_ms


def test_clear_uptrend_is_deterministic_and_frozen() -> None:
    candles = _series([Decimal(100 + index) for index in range(24)])

    first = build_regime_evidence_freeze(
        candles,
        as_of_ms=_as_of(candles),
    )
    second = build_regime_evidence_freeze(
        tuple(reversed(candles)),
        as_of_ms=_as_of(candles),
    )

    assert first == second
    assert first.schema_version == REGIME_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == REGIME_ENGINE_VERSION
    assert first.analysis.label is RegimeLabel.TREND_UP
    assert first.analysis.volatility is VolatilityState.NORMAL
    assert first.analysis.metrics is not None
    assert first.analysis.metrics.efficiency_ratio == Decimal(1)
    assert first.analysis.uncertainty_flags == ()
    assert first.candles == candles
    assert len(first.freeze_identity) == 64
    assert len(first.analysis.evidence_identity) == 64


def test_clear_downtrend_is_labeled_down() -> None:
    candles = _series([Decimal(123 - index) for index in range(24)])

    result = analyze_regime(candles, as_of_ms=_as_of(candles))

    assert result.label is RegimeLabel.TREND_DOWN
    assert result.metrics is not None
    assert result.metrics.signed_displacement_bps < Decimal(0)


def test_choppy_low_displacement_is_range() -> None:
    pattern = (Decimal(100), Decimal(101), Decimal(100), Decimal(99))
    candles = _series([pattern[index % 4] for index in range(24)])

    result = analyze_regime(candles, as_of_ms=_as_of(candles))

    assert result.label is RegimeLabel.RANGE
    assert result.metrics is not None
    assert (
        result.metrics.efficiency_ratio
        <= DEFAULT_REGIME_CONFIG.range_efficiency_max
    )
    assert (
        result.metrics.absolute_displacement_bps
        <= DEFAULT_REGIME_CONFIG.range_displacement_max_bps
    )


def test_high_efficiency_but_tiny_move_is_transition_with_uncertainty() -> None:
    candles = _series(
        [Decimal(100) + Decimal(index) / Decimal(50) for index in range(24)]
    )

    result = analyze_regime(candles, as_of_ms=_as_of(candles))

    assert result.label is RegimeLabel.TRANSITION
    assert "mixed_directional_efficiency" in result.uncertainty_flags
    assert "low_magnitude_direction" in result.uncertainty_flags


def test_recent_range_expansion_is_separate_from_direction_label() -> None:
    candles = _series(
        [Decimal(100 + index) for index in range(24)],
        expanded_last_four=True,
    )

    result = analyze_regime(candles, as_of_ms=_as_of(candles))

    assert result.label is RegimeLabel.TREND_UP
    assert result.volatility is VolatilityState.EXPANDED
    assert result.metrics is not None
    assert (
        result.metrics.volatility_ratio
        >= DEFAULT_REGIME_CONFIG.volatility_expanded_ratio
    )


def test_insufficient_history_is_explicitly_unresolved() -> None:
    candles = _series([Decimal(100 + index) for index in range(10)])

    result = analyze_regime(candles, as_of_ms=_as_of(candles))

    assert result.label is RegimeLabel.UNRESOLVED
    assert result.volatility is VolatilityState.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("insufficient_history",)


def test_gap_is_unresolved_instead_of_silently_interpolated() -> None:
    candles = list(_series([Decimal(100 + index) for index in range(24)]))
    del candles[12]
    ordered = tuple(candles)

    result = analyze_regime(ordered, as_of_ms=_as_of(ordered))

    assert result.label is RegimeLabel.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("candle_gaps",)


def test_future_candle_cannot_change_point_in_time_freeze() -> None:
    candles = _series([Decimal(100 + index) for index in range(24)])
    as_of_ms = _as_of(candles)
    future = _candle(
        index=24,
        close=Decimal(1_000),
        ingested_at_ms=as_of_ms + _STEP_MS,
        source_timestamp_ms=as_of_ms + _STEP_MS,
    )

    baseline = build_regime_evidence_freeze(candles, as_of_ms=as_of_ms)
    with_future = build_regime_evidence_freeze(
        (*candles, future),
        as_of_ms=as_of_ms,
    )

    assert with_future == baseline
    assert future not in with_future.candles


def test_freeze_and_analysis_identity_tampering_fail_closed() -> None:
    candles = _series([Decimal(100 + index) for index in range(24)])
    freeze = build_regime_evidence_freeze(candles, as_of_ms=_as_of(candles))

    with pytest.raises(ValueError, match="regime freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)

    with pytest.raises(ValueError, match="regime evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_mixed_context_is_rejected() -> None:
    candles = list(_series([Decimal(100 + index) for index in range(24)]))
    candles[-1] = _candle(index=23, close=Decimal(123), symbol="ETHUSDT")

    with pytest.raises(ValueError, match="context mismatch"):
        analyze_regime(tuple(candles), as_of_ms=_as_of(tuple(candles)))


def test_invalid_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="range efficiency"):
        RegimeConfig(
            range_efficiency_max=Decimal("0.60"),
            trend_efficiency_min=Decimal("0.55"),
        )


def test_stage8_regime_is_observation_only_not_production_confluence() -> None:
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
    ):
        source = (root / relative).read_text()
        assert "crypto_signal.intelligence.regime" not in source
