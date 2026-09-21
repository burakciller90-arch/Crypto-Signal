from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256

TREND_MOMENTUM_ENGINE_VERSION = "trend-momentum-v1/1"
TREND_MOMENTUM_FREEZE_SCHEMA_VERSION = "trend-momentum-evidence-freeze-v1/1"
_BPS = Decimal(10_000)


class TrendMomentumLabel(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


class MomentumPhase(StrEnum):
    ACCELERATING = "accelerating"
    STEADY = "steady"
    DECELERATING = "decelerating"
    FLAT = "flat"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class TrendMomentumConfig:
    lookback_bars: int = 24
    minimum_bars: int = 20
    short_horizon_intervals: int = 4
    medium_horizon_intervals: int = 12
    trend_return_min_bps: Decimal = Decimal(100)
    neutral_return_max_bps: Decimal = Decimal(50)
    directional_consistency_min: Decimal = Decimal("0.60")
    accelerating_rate_ratio: Decimal = Decimal("1.25")
    decelerating_rate_ratio: Decimal = Decimal("0.75")

    def __post_init__(self) -> None:
        if self.minimum_bars < 4:
            raise ValueError("minimum_bars must be at least 4")
        if self.lookback_bars < self.minimum_bars:
            raise ValueError("lookback_bars must be >= minimum_bars")
        if not 1 <= self.short_horizon_intervals < self.medium_horizon_intervals:
            raise ValueError("short horizon must be below medium horizon")
        if self.medium_horizon_intervals >= self.minimum_bars:
            raise ValueError("medium horizon must fit inside minimum history")
        if self.trend_return_min_bps <= Decimal(0):
            raise ValueError("trend return threshold must be positive")
        if not Decimal(0) <= self.neutral_return_max_bps:
            raise ValueError("neutral return threshold cannot be negative")
        if self.neutral_return_max_bps >= self.trend_return_min_bps:
            raise ValueError("neutral return threshold must be below trend threshold")
        if not Decimal(0) <= self.directional_consistency_min <= Decimal(1):
            raise ValueError("directional consistency threshold must be inside [0,1]")
        if self.decelerating_rate_ratio <= Decimal(0):
            raise ValueError("decelerating ratio must be positive")
        if self.decelerating_rate_ratio >= self.accelerating_rate_ratio:
            raise ValueError("decelerating ratio must be below accelerating ratio")


DEFAULT_TREND_MOMENTUM_CONFIG = TrendMomentumConfig()


@dataclass(frozen=True, slots=True)
class TrendMomentumMetrics:
    short_return_bps: Decimal
    medium_return_bps: Decimal
    long_return_bps: Decimal
    short_rate_bps_per_bar: Decimal
    medium_rate_bps_per_bar: Decimal
    long_rate_bps_per_bar: Decimal
    directional_consistency_ratio: Decimal
    short_to_medium_rate_ratio: Decimal | None

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.directional_consistency_ratio <= Decimal(1):
            raise ValueError("directional_consistency_ratio must be inside [0,1]")
        if (
            self.short_to_medium_rate_ratio is not None
            and self.short_to_medium_rate_ratio < Decimal(0)
        ):
            raise ValueError("short_to_medium_rate_ratio cannot be negative")


@dataclass(frozen=True, slots=True)
class TrendMomentumAnalysis:
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
    label: TrendMomentumLabel
    phase: MomentumPhase
    metrics: TrendMomentumMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "trend/momentum evidence identity")
        if self.engine_version != TREND_MOMENTUM_ENGINE_VERSION:
            raise ValueError("unsupported trend/momentum engine version")
        if self.as_of_ms < 0:
            raise ValueError("trend/momentum as_of_ms must be non-negative")
        if self.market_available_at_ms > self.as_of_ms:
            raise ValueError("trend/momentum market evidence is from the future")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("trend/momentum observed evidence is from the future")
        if self.consumed_bar_count <= 0:
            raise ValueError("trend/momentum analysis must consume at least one bar")
        if len(set(self.uncertainty_flags)) != len(self.uncertainty_flags):
            raise ValueError("trend/momentum uncertainty flags must be unique")
        if self.label is TrendMomentumLabel.UNRESOLVED:
            if not self.uncertainty_flags:
                raise ValueError("unresolved trend/momentum requires uncertainty")
            if self.metrics is not None:
                raise ValueError("unresolved trend/momentum cannot fabricate metrics")
            if self.phase is not MomentumPhase.UNRESOLVED:
                raise ValueError("unresolved trend/momentum requires unresolved phase")
        elif self.metrics is None:
            raise ValueError("resolved trend/momentum requires deterministic metrics")
        if self.label is TrendMomentumLabel.MIXED and not self.uncertainty_flags:
            raise ValueError("mixed trend/momentum requires explicit uncertainty")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("trend/momentum evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class TrendMomentumEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: TrendMomentumAnalysis
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "trend/momentum freeze identity")
        if self.schema_version != TREND_MOMENTUM_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported trend/momentum freeze schema")
        if not self.candles:
            raise ValueError("trend/momentum freeze requires consumed candles")
        if len(self.candles) != self.analysis.consumed_bar_count:
            raise ValueError("trend/momentum freeze candle count mismatch")
        last = self.candles[-1]
        if last.open_time_ms != self.analysis.source_cutoff_open_time_ms:
            raise ValueError("trend/momentum freeze source cutoff mismatch")
        if any(
            candle.close_time_ms > self.analysis.as_of_ms
            or candle.ingested_at_ms > self.analysis.as_of_ms
            or candle.source_timestamp_ms > self.analysis.as_of_ms
            for candle in self.candles
        ):
            raise ValueError("trend/momentum freeze contains future evidence")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("trend/momentum freeze identity mismatch")


def analyze_trend_momentum(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
    config: TrendMomentumConfig = DEFAULT_TREND_MOMENTUM_CONFIG,
) -> TrendMomentumAnalysis:
    eligible = _eligible_candles(candles, as_of_ms=as_of_ms)
    window = eligible[-config.lookback_bars :]
    first = window[0]

    metrics: TrendMomentumMetrics | None = None
    label = TrendMomentumLabel.UNRESOLVED
    phase = MomentumPhase.UNRESOLVED
    uncertainty: tuple[str, ...] = ()

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
        "engine_version": TREND_MOMENTUM_ENGINE_VERSION,
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
    return TrendMomentumAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=TREND_MOMENTUM_ENGINE_VERSION,
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


def build_trend_momentum_evidence_freeze(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
    config: TrendMomentumConfig = DEFAULT_TREND_MOMENTUM_CONFIG,
) -> TrendMomentumEvidenceFreeze:
    analysis = analyze_trend_momentum(candles, as_of_ms=as_of_ms, config=config)
    eligible = _eligible_candles(candles, as_of_ms=as_of_ms)
    consumed = tuple(eligible[-analysis.consumed_bar_count :])
    payload = {
        "schema_version": TREND_MOMENTUM_FREEZE_SCHEMA_VERSION,
        "analysis": analysis,
        "candles": consumed,
    }
    return TrendMomentumEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=TREND_MOMENTUM_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        candles=consumed,
    )


def _eligible_candles(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
) -> tuple[Candle, ...]:
    if not candles:
        raise ValueError("trend/momentum analysis requires candles")
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
        raise ValueError("trend/momentum candle context mismatch")
    opens = tuple(candle.open_time_ms for candle in ordered)
    if len(set(opens)) != len(opens):
        raise ValueError("trend/momentum candle opens must be unique")

    eligible = tuple(
        candle
        for candle in ordered
        if candle.is_closed
        and candle.close_time_ms <= as_of_ms
        and candle.ingested_at_ms <= as_of_ms
        and candle.source_timestamp_ms <= as_of_ms
    )
    if not eligible:
        raise ValueError("trend/momentum has no PIT-eligible closed candles")
    return eligible


def _metrics(
    candles: Sequence[Candle],
    *,
    config: TrendMomentumConfig,
) -> TrendMomentumMetrics:
    closes = tuple(candle.close for candle in candles)
    short = _return_bps(closes[-config.short_horizon_intervals - 1], closes[-1])
    medium = _return_bps(closes[-config.medium_horizon_intervals - 1], closes[-1])
    long = _return_bps(closes[0], closes[-1])

    short_rate = short / Decimal(config.short_horizon_intervals)
    medium_rate = medium / Decimal(config.medium_horizon_intervals)
    long_intervals = len(closes) - 1
    long_rate = long / Decimal(long_intervals)

    direction = _sign(long)
    steps = tuple(right - left for left, right in pairwise(closes))
    if direction == 0:
        consistency = Decimal(0)
    else:
        aligned = sum(1 for step in steps if _sign(step) == direction)
        consistency = Decimal(aligned) / Decimal(len(steps))

    rate_ratio = (
        None
        if medium_rate == Decimal(0)
        else abs(short_rate) / abs(medium_rate)
    )
    return TrendMomentumMetrics(
        short_return_bps=short,
        medium_return_bps=medium,
        long_return_bps=long,
        short_rate_bps_per_bar=short_rate,
        medium_rate_bps_per_bar=medium_rate,
        long_rate_bps_per_bar=long_rate,
        directional_consistency_ratio=consistency,
        short_to_medium_rate_ratio=rate_ratio,
    )


def _label(
    metrics: TrendMomentumMetrics,
    *,
    config: TrendMomentumConfig,
) -> tuple[TrendMomentumLabel, tuple[str, ...]]:
    long_sign = _sign(metrics.long_return_bps)
    medium_sign = _sign(metrics.medium_return_bps)
    short_sign = _sign(metrics.short_return_bps)
    horizon_aligned = (
        long_sign != 0
        and long_sign == medium_sign
        and long_sign == short_sign
    )
    strong_enough = (
        abs(metrics.long_return_bps) >= config.trend_return_min_bps
    )
    consistent = (
        metrics.directional_consistency_ratio
        >= config.directional_consistency_min
    )

    if horizon_aligned and strong_enough and consistent:
        if long_sign > 0:
            return TrendMomentumLabel.BULLISH, ()
        return TrendMomentumLabel.BEARISH, ()

    if all(
        abs(value) <= config.neutral_return_max_bps
        for value in (
            metrics.short_return_bps,
            metrics.medium_return_bps,
            metrics.long_return_bps,
        )
    ):
        return TrendMomentumLabel.NEUTRAL, ()

    flags: list[str] = []
    nonzero_signs = {
        sign
        for sign in (long_sign, medium_sign, short_sign)
        if sign != 0
    }
    if len(nonzero_signs) > 1:
        flags.append("horizon_direction_disagreement")
    if not consistent:
        flags.append("low_directional_consistency")
    if not strong_enough:
        flags.append("long_move_below_trend_threshold")
    if not flags:
        flags.append("mixed_trend_momentum")
    return TrendMomentumLabel.MIXED, tuple(flags)


def _phase(
    label: TrendMomentumLabel,
    metrics: TrendMomentumMetrics,
    *,
    config: TrendMomentumConfig,
) -> MomentumPhase:
    if label is TrendMomentumLabel.NEUTRAL:
        return MomentumPhase.FLAT
    if label is TrendMomentumLabel.MIXED:
        return MomentumPhase.MIXED
    if label is TrendMomentumLabel.UNRESOLVED:
        return MomentumPhase.UNRESOLVED

    ratio = metrics.short_to_medium_rate_ratio
    if ratio is None:
        return MomentumPhase.MIXED
    if ratio >= config.accelerating_rate_ratio:
        return MomentumPhase.ACCELERATING
    if ratio <= config.decelerating_rate_ratio:
        return MomentumPhase.DECELERATING
    return MomentumPhase.STEADY


def _return_bps(start: Decimal, end: Decimal) -> Decimal:
    return (end - start) / start * _BPS


def _sign(value: Decimal) -> int:
    if value > Decimal(0):
        return 1
    if value < Decimal(0):
        return -1
    return 0


def _analysis_payload(analysis: TrendMomentumAnalysis) -> dict[str, object]:
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


def _freeze_payload(freeze: TrendMomentumEvidenceFreeze) -> dict[str, object]:
    return {
        "schema_version": freeze.schema_version,
        "analysis": freeze.analysis,
        "candles": freeze.candles,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
