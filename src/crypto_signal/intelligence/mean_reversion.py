from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from statistics import median

from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256

MEAN_REVERSION_ENGINE_VERSION = "mean-reversion-v1/1"
MEAN_REVERSION_FREEZE_SCHEMA_VERSION = "mean-reversion-evidence-freeze-v1/1"
_BPS = Decimal(10_000)


class MeanReversionLabel(StrEnum):
    STRETCHED_HIGH = "stretched_high"
    STRETCHED_LOW = "stretched_low"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


class ReversionPhase(StrEnum):
    SNAPBACK = "snapback"
    EXTENDING = "extending"
    STALLED = "stalled"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class MeanReversionConfig:
    lookback_bars: int = 24
    minimum_bars: int = 20
    short_horizon_intervals: int = 4
    stretched_deviation_min_bps: Decimal = Decimal(200)
    neutral_deviation_max_bps: Decimal = Decimal(75)
    extreme_position_high: Decimal = Decimal("0.80")
    extreme_position_low: Decimal = Decimal("0.20")
    phase_return_min_bps: Decimal = Decimal(50)

    def __post_init__(self) -> None:
        if self.minimum_bars < 4:
            raise ValueError("minimum_bars must be at least 4")
        if self.lookback_bars < self.minimum_bars:
            raise ValueError("lookback_bars must be >= minimum_bars")
        if not 1 <= self.short_horizon_intervals < self.minimum_bars:
            raise ValueError("short horizon must fit inside minimum history")
        if self.stretched_deviation_min_bps <= Decimal(0):
            raise ValueError("stretched deviation threshold must be positive")
        if not Decimal(0) <= self.neutral_deviation_max_bps:
            raise ValueError("neutral deviation threshold cannot be negative")
        if self.neutral_deviation_max_bps >= self.stretched_deviation_min_bps:
            raise ValueError(
                "neutral deviation threshold must be below stretched threshold"
            )
        if not Decimal(0) < self.extreme_position_low < Decimal("0.5"):
            raise ValueError("low extreme position must be inside (0,0.5)")
        if not Decimal("0.5") < self.extreme_position_high < Decimal(1):
            raise ValueError("high extreme position must be inside (0.5,1)")
        if self.extreme_position_low >= self.extreme_position_high:
            raise ValueError("low extreme position must be below high extreme")
        if self.phase_return_min_bps <= Decimal(0):
            raise ValueError("phase return threshold must be positive")


DEFAULT_MEAN_REVERSION_CONFIG = MeanReversionConfig()


@dataclass(frozen=True, slots=True)
class MeanReversionMetrics:
    center_price: Decimal
    last_price: Decimal
    deviation_bps: Decimal
    absolute_deviation_bps: Decimal
    median_abs_deviation_bps: Decimal
    range_position_ratio: Decimal | None
    short_return_bps: Decimal

    def __post_init__(self) -> None:
        if self.center_price <= Decimal(0):
            raise ValueError("center price must be positive")
        if self.last_price <= Decimal(0):
            raise ValueError("last price must be positive")
        if self.absolute_deviation_bps != abs(self.deviation_bps):
            raise ValueError("absolute deviation mismatch")
        if self.median_abs_deviation_bps < Decimal(0):
            raise ValueError("median absolute deviation cannot be negative")
        if self.range_position_ratio is not None and not (
            Decimal(0) <= self.range_position_ratio <= Decimal(1)
        ):
            raise ValueError("range position must be inside [0,1]")


@dataclass(frozen=True, slots=True)
class MeanReversionAnalysis:
    evidence_identity: str
    engine_version: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    market_available_at_ms: int
    observed_at_ms: int
    source_cutoff_open_time_ms: int
    consumed_bar_count: int
    label: MeanReversionLabel
    phase: ReversionPhase
    metrics: MeanReversionMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "mean-reversion evidence identity")
        if self.engine_version != MEAN_REVERSION_ENGINE_VERSION:
            raise ValueError("unsupported mean-reversion engine version")
        if self.as_of_ms < 0:
            raise ValueError("mean-reversion as_of_ms must be non-negative")
        if self.market_available_at_ms > self.as_of_ms:
            raise ValueError("mean-reversion market evidence is from the future")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("mean-reversion observed evidence is from the future")
        if self.consumed_bar_count <= 0:
            raise ValueError("mean-reversion analysis must consume at least one bar")
        if len(set(self.uncertainty_flags)) != len(self.uncertainty_flags):
            raise ValueError("mean-reversion uncertainty flags must be unique")
        if self.label is MeanReversionLabel.UNRESOLVED:
            if not self.uncertainty_flags:
                raise ValueError("unresolved mean-reversion requires uncertainty")
            if self.metrics is not None:
                raise ValueError("unresolved mean-reversion cannot fabricate metrics")
            if self.phase is not ReversionPhase.UNRESOLVED:
                raise ValueError("unresolved mean-reversion requires unresolved phase")
        elif self.metrics is None:
            raise ValueError("resolved mean-reversion requires deterministic metrics")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("mean-reversion evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class MeanReversionEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: MeanReversionAnalysis
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "mean-reversion freeze identity")
        if self.schema_version != MEAN_REVERSION_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported mean-reversion freeze schema")
        if not self.candles:
            raise ValueError("mean-reversion freeze requires consumed candles")
        if len(self.candles) != self.analysis.consumed_bar_count:
            raise ValueError("mean-reversion freeze candle count mismatch")
        last = self.candles[-1]
        if last.open_time_ms != self.analysis.source_cutoff_open_time_ms:
            raise ValueError("mean-reversion freeze source cutoff mismatch")
        if any(
            candle.close_time_ms > self.analysis.as_of_ms
            or candle.ingested_at_ms > self.analysis.as_of_ms
            or candle.source_timestamp_ms > self.analysis.as_of_ms
            for candle in self.candles
        ):
            raise ValueError("mean-reversion freeze contains future evidence")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("mean-reversion freeze identity mismatch")


def analyze_mean_reversion(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
    config: MeanReversionConfig = DEFAULT_MEAN_REVERSION_CONFIG,
) -> MeanReversionAnalysis:
    eligible = _eligible_candles(candles, as_of_ms=as_of_ms)
    window = eligible[-config.lookback_bars :]
    first = window[0]

    uncertainty: tuple[str, ...] = ()
    metrics: MeanReversionMetrics | None = None
    label = MeanReversionLabel.UNRESOLVED
    phase = ReversionPhase.UNRESOLVED

    gaps = detect_gaps(window, first.timeframe)
    if len(window) < config.minimum_bars:
        uncertainty = ("insufficient_history",)
    elif gaps:
        uncertainty = ("candle_gaps",)
    else:
        metrics = _metrics(window, config=config)
        label, uncertainty = _label(metrics, config=config)
        phase = _phase(label, metrics, config=config)

    payload = {
        "engine_version": MEAN_REVERSION_ENGINE_VERSION,
        "exchange": first.exchange,
        "market_type": first.market_type,
        "symbol": first.symbol,
        "timeframe": first.timeframe,
        "as_of_ms": as_of_ms,
        "market_available_at_ms": window[-1].close_time_ms,
        "observed_at_ms": max(candle.ingested_at_ms for candle in window),
        "source_cutoff_open_time_ms": window[-1].open_time_ms,
        "consumed_bar_count": len(window),
        "label": label,
        "phase": phase,
        "metrics": metrics,
        "uncertainty_flags": uncertainty,
    }
    return MeanReversionAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=MEAN_REVERSION_ENGINE_VERSION,
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=as_of_ms,
        market_available_at_ms=window[-1].close_time_ms,
        observed_at_ms=max(candle.ingested_at_ms for candle in window),
        source_cutoff_open_time_ms=window[-1].open_time_ms,
        consumed_bar_count=len(window),
        label=label,
        phase=phase,
        metrics=metrics,
        uncertainty_flags=uncertainty,
    )


def build_mean_reversion_evidence_freeze(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
    config: MeanReversionConfig = DEFAULT_MEAN_REVERSION_CONFIG,
) -> MeanReversionEvidenceFreeze:
    analysis = analyze_mean_reversion(candles, as_of_ms=as_of_ms, config=config)
    eligible = _eligible_candles(candles, as_of_ms=as_of_ms)
    consumed = tuple(eligible[-analysis.consumed_bar_count :])
    payload = {
        "schema_version": MEAN_REVERSION_FREEZE_SCHEMA_VERSION,
        "analysis": analysis,
        "candles": consumed,
    }
    return MeanReversionEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=MEAN_REVERSION_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        candles=consumed,
    )


def _eligible_candles(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
) -> tuple[Candle, ...]:
    if not candles:
        raise ValueError("mean-reversion analysis requires candles")
    if as_of_ms < 0:
        raise ValueError("as_of_ms must be non-negative")

    ordered = tuple(sorted(candles, key=lambda candle: candle.open_time_ms))
    context = (
        ordered[0].exchange,
        ordered[0].market_type,
        ordered[0].symbol,
        ordered[0].timeframe,
    )
    if any(
        (
            candle.exchange,
            candle.market_type,
            candle.symbol,
            candle.timeframe,
        )
        != context
        for candle in ordered
    ):
        raise ValueError("mean-reversion candle context mismatch")
    opens = tuple(candle.open_time_ms for candle in ordered)
    if len(set(opens)) != len(opens):
        raise ValueError("mean-reversion candle opens must be unique")

    eligible = tuple(
        candle
        for candle in ordered
        if candle.is_closed
        and candle.close_time_ms <= as_of_ms
        and candle.ingested_at_ms <= as_of_ms
        and candle.source_timestamp_ms <= as_of_ms
    )
    if not eligible:
        raise ValueError("mean-reversion analysis has no PIT-eligible closed candles")
    return eligible


def _metrics(
    candles: Sequence[Candle],
    *,
    config: MeanReversionConfig,
) -> MeanReversionMetrics:
    closes = tuple(candle.close for candle in candles)
    center = median(closes)
    if center <= Decimal(0):
        raise ValueError("mean-reversion center price must be positive")

    last = closes[-1]
    deviation = (last - center) / center * _BPS
    deviations = tuple(abs(close - center) / center * _BPS for close in closes)
    mad_bps = median(deviations)

    low = min(closes)
    high = max(closes)
    range_position = (
        None if high == low else (last - low) / (high - low)
    )

    start = closes[-1 - config.short_horizon_intervals]
    short_return = (last - start) / start * _BPS

    return MeanReversionMetrics(
        center_price=center,
        last_price=last,
        deviation_bps=deviation,
        absolute_deviation_bps=abs(deviation),
        median_abs_deviation_bps=mad_bps,
        range_position_ratio=range_position,
        short_return_bps=short_return,
    )


def _label(
    metrics: MeanReversionMetrics,
    *,
    config: MeanReversionConfig,
) -> tuple[MeanReversionLabel, tuple[str, ...]]:
    if metrics.absolute_deviation_bps <= config.neutral_deviation_max_bps:
        return MeanReversionLabel.NEUTRAL, ()

    position = metrics.range_position_ratio
    if (
        metrics.deviation_bps >= config.stretched_deviation_min_bps
        and position is not None
        and position >= config.extreme_position_high
    ):
        return MeanReversionLabel.STRETCHED_HIGH, ()

    if (
        metrics.deviation_bps <= -config.stretched_deviation_min_bps
        and position is not None
        and position <= config.extreme_position_low
    ):
        return MeanReversionLabel.STRETCHED_LOW, ()

    flags: list[str] = []
    if metrics.absolute_deviation_bps < config.stretched_deviation_min_bps:
        flags.append("deviation_below_stretch_threshold")
    if position is None:
        flags.append("flat_range_position")
    elif (
        config.extreme_position_low
        < position
        < config.extreme_position_high
    ):
        flags.append("range_position_not_extreme")
    if not flags:
        flags.append("mixed_mean_reversion")
    return MeanReversionLabel.MIXED, tuple(flags)


def _phase(
    label: MeanReversionLabel,
    metrics: MeanReversionMetrics,
    *,
    config: MeanReversionConfig,
) -> ReversionPhase:
    if label is MeanReversionLabel.UNRESOLVED:
        return ReversionPhase.UNRESOLVED
    if label is MeanReversionLabel.MIXED:
        return ReversionPhase.MIXED
    if label is MeanReversionLabel.NEUTRAL:
        return ReversionPhase.STALLED

    threshold = config.phase_return_min_bps
    if label is MeanReversionLabel.STRETCHED_HIGH:
        if metrics.short_return_bps <= -threshold:
            return ReversionPhase.SNAPBACK
        if metrics.short_return_bps >= threshold:
            return ReversionPhase.EXTENDING
        return ReversionPhase.STALLED

    if metrics.short_return_bps >= threshold:
        return ReversionPhase.SNAPBACK
    if metrics.short_return_bps <= -threshold:
        return ReversionPhase.EXTENDING
    return ReversionPhase.STALLED


def _analysis_payload(analysis: MeanReversionAnalysis) -> dict[str, object]:
    return {
        "engine_version": analysis.engine_version,
        "exchange": analysis.exchange,
        "market_type": analysis.market_type,
        "symbol": analysis.symbol,
        "timeframe": analysis.timeframe,
        "as_of_ms": analysis.as_of_ms,
        "market_available_at_ms": analysis.market_available_at_ms,
        "observed_at_ms": analysis.observed_at_ms,
        "source_cutoff_open_time_ms": analysis.source_cutoff_open_time_ms,
        "consumed_bar_count": analysis.consumed_bar_count,
        "label": analysis.label,
        "phase": analysis.phase,
        "metrics": analysis.metrics,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze_payload(freeze: MeanReversionEvidenceFreeze) -> dict[str, object]:
    return {
        "schema_version": freeze.schema_version,
        "analysis": freeze.analysis,
        "candles": freeze.candles,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
