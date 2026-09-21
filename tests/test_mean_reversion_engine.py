from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.models import MethodologyKind
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.intelligence.mean_reversion import (
    DEFAULT_MEAN_REVERSION_CONFIG,
    MEAN_REVERSION_ENGINE_VERSION,
    MEAN_REVERSION_FREEZE_SCHEMA_VERSION,
    MeanReversionConfig,
    MeanReversionLabel,
    ReversionPhase,
    analyze_mean_reversion,
    build_mean_reversion_evidence_freeze,
)

_STEP_MS = 15 * 60_000


def _candle(
    *,
    index: int,
    close: Decimal,
    symbol: str = "BTCUSDT",
    ingested_at_ms: int | None = None,
    source_timestamp_ms: int | None = None,
) -> Candle:
    open_time_ms = index * _STEP_MS
    close_time_ms = open_time_ms + _STEP_MS - 1
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
        high=close + Decimal("0.5"),
        low=close - Decimal("0.5"),
        close=close,
        volume=Decimal(1),
        quote_volume=close,
        trade_count=1,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingested_ms,
        adapter_version="mean-reversion-test/1",
    )


def _series(closes: list[Decimal]) -> tuple[Candle, ...]:
    return tuple(
        _candle(index=index, close=close)
        for index, close in enumerate(closes)
    )


def _as_of(candles: tuple[Candle, ...]) -> int:
    return candles[-1].close_time_ms


def test_stretched_high_snapback_is_deterministic_and_frozen() -> None:
    candles = _series(
        [Decimal(100)] * 19
        + [Decimal(140), Decimal(138), Decimal(136), Decimal(134), Decimal(132)]
    )

    first = build_mean_reversion_evidence_freeze(
        candles,
        as_of_ms=_as_of(candles),
    )
    second = build_mean_reversion_evidence_freeze(
        tuple(reversed(candles)),
        as_of_ms=_as_of(candles),
    )

    assert first == second
    assert first.schema_version == MEAN_REVERSION_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == MEAN_REVERSION_ENGINE_VERSION
    assert first.analysis.label is MeanReversionLabel.STRETCHED_HIGH
    assert first.analysis.phase is ReversionPhase.SNAPBACK
    assert first.analysis.metrics is not None
    assert first.analysis.metrics.center_price == Decimal(100)
    assert first.analysis.metrics.deviation_bps == Decimal(3200)
    assert first.analysis.metrics.range_position_ratio == Decimal("0.8")
    assert first.analysis.metrics.short_return_bps < Decimal(0)
    assert first.analysis.uncertainty_flags == ()
    assert first.candles == candles
    assert len(first.freeze_identity) == 64
    assert len(first.analysis.evidence_identity) == 64


def test_stretched_low_snapback_is_labeled_low() -> None:
    candles = _series(
        [Decimal(100)] * 19
        + [Decimal(60), Decimal(62), Decimal(64), Decimal(66), Decimal(68)]
    )

    result = analyze_mean_reversion(candles, as_of_ms=_as_of(candles))

    assert result.label is MeanReversionLabel.STRETCHED_LOW
    assert result.phase is ReversionPhase.SNAPBACK
    assert result.metrics is not None
    assert result.metrics.deviation_bps == Decimal(-3200)
    assert result.metrics.range_position_ratio == Decimal("0.2")
    assert result.metrics.short_return_bps > Decimal(0)


def test_stretched_high_can_still_be_extending_not_snapback() -> None:
    candles = _series(
        [Decimal(100)] * 19
        + [Decimal(110), Decimal(115), Decimal(120), Decimal(125), Decimal(130)]
    )

    result = analyze_mean_reversion(candles, as_of_ms=_as_of(candles))

    assert result.label is MeanReversionLabel.STRETCHED_HIGH
    assert result.phase is ReversionPhase.EXTENDING
    assert result.metrics is not None
    assert result.metrics.short_return_bps > Decimal(0)


def test_near_center_market_is_neutral_without_probability_claim() -> None:
    pattern = (Decimal("100.00"), Decimal("100.10"))
    candles = _series([pattern[index % 2] for index in range(24)])

    result = analyze_mean_reversion(candles, as_of_ms=_as_of(candles))

    assert result.label is MeanReversionLabel.NEUTRAL
    assert result.phase is ReversionPhase.STALLED
    assert result.metrics is not None
    assert (
        result.metrics.absolute_deviation_bps
        <= DEFAULT_MEAN_REVERSION_CONFIG.neutral_deviation_max_bps
    )
    assert result.uncertainty_flags == ()


def test_mid_deviation_is_mixed_with_explicit_uncertainty() -> None:
    candles = _series(
        [Decimal(100)] * 19
        + [
            Decimal("100.50"),
            Decimal("100.75"),
            Decimal("101.00"),
            Decimal("101.25"),
            Decimal("101.50"),
        ]
    )

    result = analyze_mean_reversion(candles, as_of_ms=_as_of(candles))

    assert result.label is MeanReversionLabel.MIXED
    assert result.phase is ReversionPhase.MIXED
    assert result.metrics is not None
    assert "deviation_below_stretch_threshold" in result.uncertainty_flags


def test_insufficient_history_is_explicitly_unresolved() -> None:
    candles = _series([Decimal(100 + index) for index in range(10)])

    result = analyze_mean_reversion(candles, as_of_ms=_as_of(candles))

    assert result.label is MeanReversionLabel.UNRESOLVED
    assert result.phase is ReversionPhase.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("insufficient_history",)


def test_gap_is_unresolved_instead_of_interpolated() -> None:
    candles = list(_series([Decimal(100 + index) for index in range(24)]))
    del candles[12]
    ordered = tuple(candles)

    result = analyze_mean_reversion(ordered, as_of_ms=_as_of(ordered))

    assert result.label is MeanReversionLabel.UNRESOLVED
    assert result.phase is ReversionPhase.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("candle_gaps",)


def test_future_candle_cannot_change_point_in_time_freeze() -> None:
    candles = _series(
        [Decimal(100)] * 19
        + [Decimal(140), Decimal(138), Decimal(136), Decimal(134), Decimal(132)]
    )
    as_of_ms = _as_of(candles)
    future = _candle(
        index=24,
        close=Decimal(1_000),
        ingested_at_ms=as_of_ms + _STEP_MS,
        source_timestamp_ms=as_of_ms + _STEP_MS,
    )

    baseline = build_mean_reversion_evidence_freeze(
        candles,
        as_of_ms=as_of_ms,
    )
    with_future = build_mean_reversion_evidence_freeze(
        (*candles, future),
        as_of_ms=as_of_ms,
    )

    assert with_future == baseline
    assert future not in with_future.candles


def test_freeze_and_analysis_identity_tampering_fail_closed() -> None:
    candles = _series(
        [Decimal(100)] * 19
        + [Decimal(140), Decimal(138), Decimal(136), Decimal(134), Decimal(132)]
    )
    freeze = build_mean_reversion_evidence_freeze(
        candles,
        as_of_ms=_as_of(candles),
    )

    with pytest.raises(
        ValueError,
        match="mean-reversion freeze identity mismatch",
    ):
        replace(freeze, freeze_identity="f" * 64)

    with pytest.raises(
        ValueError,
        match="mean-reversion evidence identity mismatch",
    ):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_mixed_context_is_rejected() -> None:
    candles = list(_series([Decimal(100 + index) for index in range(24)]))
    candles[-1] = _candle(index=23, close=Decimal(123), symbol="ETHUSDT")

    with pytest.raises(ValueError, match="context mismatch"):
        analyze_mean_reversion(tuple(candles), as_of_ms=_as_of(tuple(candles)))


def test_invalid_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="neutral deviation threshold"):
        MeanReversionConfig(
            neutral_deviation_max_bps=Decimal(250),
            stretched_deviation_min_bps=Decimal(200),
        )


def test_stage8_mean_reversion_is_observation_only_ablation_zero() -> None:
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
        assert "crypto_signal.intelligence.mean_reversion" not in source
