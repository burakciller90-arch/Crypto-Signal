from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.models import MethodologyKind
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.intelligence.breakout_volatility import (
    BREAKOUT_VOLATILITY_ENGINE_VERSION,
    BREAKOUT_VOLATILITY_FREEZE_SCHEMA_VERSION,
    BreakoutLabel,
    BreakoutVolatilityConfig,
    BreakoutVolatilityState,
    analyze_breakout_volatility,
    build_breakout_volatility_evidence_freeze,
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
        adapter_version="breakout-volatility-test/1",
    )


def _flat_history(
    *,
    current_close: Decimal,
    current_range: Decimal = Decimal(1),
) -> tuple[Candle, ...]:
    candles = [
        _candle(index=index, close=Decimal(100))
        for index in range(23)
    ]
    candles.append(
        _candle(
            index=23,
            close=current_close,
            range_width=current_range,
        )
    )
    return tuple(candles)


def _as_of(candles: tuple[Candle, ...]) -> int:
    return candles[-1].close_time_ms


def test_breakout_up_is_deterministic_frozen_and_expanded() -> None:
    candles = _flat_history(
        current_close=Decimal(103),
        current_range=Decimal(6),
    )

    first = build_breakout_volatility_evidence_freeze(
        candles,
        as_of_ms=_as_of(candles),
    )
    second = build_breakout_volatility_evidence_freeze(
        tuple(reversed(candles)),
        as_of_ms=_as_of(candles),
    )

    assert first == second
    assert first.schema_version == BREAKOUT_VOLATILITY_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == BREAKOUT_VOLATILITY_ENGINE_VERSION
    assert first.analysis.label is BreakoutLabel.BREAKOUT_UP
    assert first.analysis.volatility is BreakoutVolatilityState.EXPANDED
    assert first.analysis.metrics is not None
    assert first.analysis.metrics.reference_high == Decimal("100.5")
    assert first.analysis.metrics.reference_low == Decimal("99.5")
    assert first.analysis.metrics.close_vs_high_bps > Decimal(0)
    assert first.analysis.metrics.volatility_ratio > Decimal(1)
    assert first.analysis.uncertainty_flags == ()
    assert first.candles == candles
    assert len(first.freeze_identity) == 64
    assert len(first.analysis.evidence_identity) == 64


def test_breakout_down_is_labeled_down() -> None:
    candles = _flat_history(current_close=Decimal(97))

    result = analyze_breakout_volatility(candles, as_of_ms=_as_of(candles))

    assert result.label is BreakoutLabel.BREAKOUT_DOWN
    assert result.metrics is not None
    assert result.metrics.close_vs_low_bps < Decimal(0)


def test_boundary_probe_is_explicit_not_promoted_to_breakout() -> None:
    candles = _flat_history(current_close=Decimal("100.6"))

    result = analyze_breakout_volatility(candles, as_of_ms=_as_of(candles))

    assert result.label is BreakoutLabel.PROBE_UP
    assert result.uncertainty_flags == ("breakout_buffer_not_cleared",)


def test_inside_range_can_be_volatility_compressed() -> None:
    candles = _flat_history(
        current_close=Decimal(100),
        current_range=Decimal("0.20"),
    )

    result = analyze_breakout_volatility(candles, as_of_ms=_as_of(candles))

    assert result.label is BreakoutLabel.INSIDE_RANGE
    assert result.volatility is BreakoutVolatilityState.COMPRESSED
    assert result.metrics is not None
    assert result.metrics.volatility_ratio < Decimal(1)


def test_inside_range_can_be_volatility_expanded_without_breakout() -> None:
    candles = _flat_history(
        current_close=Decimal(100),
        current_range=Decimal(6),
    )

    result = analyze_breakout_volatility(candles, as_of_ms=_as_of(candles))

    assert result.label is BreakoutLabel.INSIDE_RANGE
    assert result.volatility is BreakoutVolatilityState.EXPANDED
    assert result.metrics is not None
    assert result.metrics.current_range_bps > result.metrics.baseline_range_bps


def test_zero_baseline_range_is_unresolved_not_fake_compression() -> None:
    candles = tuple(
        _candle(
            index=index,
            close=Decimal(100),
            range_width=Decimal(0),
        )
        for index in range(24)
    )

    result = analyze_breakout_volatility(candles, as_of_ms=_as_of(candles))

    assert result.label is BreakoutLabel.UNRESOLVED
    assert result.volatility is BreakoutVolatilityState.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("zero_baseline_range",)


def test_insufficient_history_is_explicitly_unresolved() -> None:
    candles = tuple(
        _candle(index=index, close=Decimal(100))
        for index in range(10)
    )

    result = analyze_breakout_volatility(candles, as_of_ms=_as_of(candles))

    assert result.label is BreakoutLabel.UNRESOLVED
    assert result.volatility is BreakoutVolatilityState.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("insufficient_history",)


def test_gap_is_unresolved_instead_of_interpolated() -> None:
    candles = list(_flat_history(current_close=Decimal(103)))
    del candles[12]
    ordered = tuple(candles)

    result = analyze_breakout_volatility(ordered, as_of_ms=_as_of(ordered))

    assert result.label is BreakoutLabel.UNRESOLVED
    assert result.volatility is BreakoutVolatilityState.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("candle_gaps",)


def test_future_candle_cannot_change_point_in_time_freeze() -> None:
    candles = _flat_history(current_close=Decimal(103))
    as_of_ms = _as_of(candles)
    future = _candle(
        index=24,
        close=Decimal(1_000),
        range_width=Decimal(100),
        ingested_at_ms=as_of_ms + _STEP_MS,
        source_timestamp_ms=as_of_ms + _STEP_MS,
    )

    baseline = build_breakout_volatility_evidence_freeze(
        candles,
        as_of_ms=as_of_ms,
    )
    with_future = build_breakout_volatility_evidence_freeze(
        (*candles, future),
        as_of_ms=as_of_ms,
    )

    assert with_future == baseline
    assert future not in with_future.candles


def test_freeze_and_analysis_identity_tampering_fail_closed() -> None:
    candles = _flat_history(current_close=Decimal(103))
    freeze = build_breakout_volatility_evidence_freeze(
        candles,
        as_of_ms=_as_of(candles),
    )

    with pytest.raises(
        ValueError,
        match="breakout/volatility freeze identity mismatch",
    ):
        replace(freeze, freeze_identity="f" * 64)

    with pytest.raises(
        ValueError,
        match="breakout/volatility evidence identity mismatch",
    ):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_mixed_context_is_rejected() -> None:
    candles = list(_flat_history(current_close=Decimal(103)))
    candles[-1] = _candle(
        index=23,
        close=Decimal(103),
        symbol="ETHUSDT",
    )

    with pytest.raises(ValueError, match="context mismatch"):
        analyze_breakout_volatility(
            tuple(candles),
            as_of_ms=_as_of(tuple(candles)),
        )


def test_invalid_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="reference_bars"):
        BreakoutVolatilityConfig(
            minimum_bars=20,
            reference_bars=20,
        )


def test_stage8_breakout_volatility_is_observation_only_ablation_zero() -> None:
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
        assert "crypto_signal.intelligence.breakout_volatility" not in source
