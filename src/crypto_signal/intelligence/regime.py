from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise
from statistics import median

from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256

REGIME_ENGINE_VERSION = "regime-labeling-v1/1"
REGIME_FREEZE_SCHEMA_VERSION = "regime-evidence-freeze-v1/1"
_BPS = Decimal(10_000)


class RegimeLabel(StrEnum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    TRANSITION = "transition"
    UNRESOLVED = "unresolved"


class VolatilityState(StrEnum):
    COMPRESSED = "compressed"
    NORMAL = "normal"
    EXPANDED = "expanded"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class RegimeConfig:
    lookback_bars: int = 24
    minimum_bars: int = 20
    recent_volatility_bars: int = 4
    trend_efficiency_min: Decimal = Decimal("0.55")
    range_efficiency_max: Decimal = Decimal("0.30")
    trend_displacement_min_bps: Decimal = Decimal(100)
    range_displacement_max_bps: Decimal = Decimal(100)
    volatility_expanded_ratio: Decimal = Decimal("1.50")
    volatility_compressed_ratio: Decimal = Decimal("0.75")

    def __post_init__(self) -> None:
        if self.minimum_bars < 3:
            raise ValueError("minimum_bars must be at least 3")
        if self.lookback_bars < self.minimum_bars:
            raise ValueError("lookback_bars must be >= minimum_bars")
        if not 1 <= self.recent_volatility_bars < self.minimum_bars:
            raise ValueError(
                "recent_volatility_bars must be inside the minimum window"
            )
        if not Decimal(0) <= self.range_efficiency_max:
            raise ValueError("range efficiency threshold cannot be negative")
        if self.trend_efficiency_min > Decimal(1):
            raise ValueError("trend efficiency threshold cannot exceed one")
        if self.range_efficiency_max >= self.trend_efficiency_min:
            raise ValueError("range efficiency must be below trend efficiency")
        if min(
            self.trend_displacement_min_bps,
            self.range_displacement_max_bps,
        ) < Decimal(0):
            raise ValueError("displacement thresholds cannot be negative")
        if self.volatility_compressed_ratio <= Decimal(0):
            raise ValueError("compressed volatility ratio must be positive")
        if (
            self.volatility_compressed_ratio
            >= self.volatility_expanded_ratio
        ):
            raise ValueError(
                "compressed volatility ratio must be below expanded ratio"
            )


DEFAULT_REGIME_CONFIG = RegimeConfig()


@dataclass(frozen=True, slots=True)
class RegimeMetrics:
    signed_displacement_bps: Decimal
    absolute_displacement_bps: Decimal
    path_length_bps: Decimal
    efficiency_ratio: Decimal
    baseline_range_bps: Decimal
    recent_range_bps: Decimal
    volatility_ratio: Decimal

    def __post_init__(self) -> None:
        for label, value in (
            ("absolute_displacement_bps", self.absolute_displacement_bps),
            ("path_length_bps", self.path_length_bps),
            ("efficiency_ratio", self.efficiency_ratio),
            ("baseline_range_bps", self.baseline_range_bps),
            ("recent_range_bps", self.recent_range_bps),
            ("volatility_ratio", self.volatility_ratio),
        ):
            if value < Decimal(0):
                raise ValueError(f"{label} cannot be negative")
        if self.efficiency_ratio > Decimal(1):
            raise ValueError("efficiency_ratio cannot exceed one")


@dataclass(frozen=True, slots=True)
class RegimeAnalysis:
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
    label: RegimeLabel
    volatility: VolatilityState
    metrics: RegimeMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "regime evidence identity")
        if self.engine_version != REGIME_ENGINE_VERSION:
            raise ValueError("unsupported regime engine version")
        if self.as_of_ms < 0:
            raise ValueError("regime as_of_ms must be non-negative")
        if self.market_available_at_ms > self.as_of_ms:
            raise ValueError("regime market evidence is from the future")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("regime observed evidence is from the future")
        if self.consumed_bar_count <= 0:
            raise ValueError("regime analysis must consume at least one bar")
        if len(set(self.uncertainty_flags)) != len(self.uncertainty_flags):
            raise ValueError("regime uncertainty flags must be unique")
        if self.label is RegimeLabel.UNRESOLVED:
            if not self.uncertainty_flags:
                raise ValueError("unresolved regime requires uncertainty")
            if self.metrics is not None:
                raise ValueError("unresolved regime cannot fabricate metrics")
            if self.volatility is not VolatilityState.UNRESOLVED:
                raise ValueError("unresolved regime requires unresolved volatility")
        elif self.metrics is None:
            raise ValueError("resolved regime requires deterministic metrics")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("regime evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class RegimeEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: RegimeAnalysis
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "regime freeze identity")
        if self.schema_version != REGIME_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported regime freeze schema")
        if not self.candles:
            raise ValueError("regime freeze requires consumed candles")
        if len(self.candles) != self.analysis.consumed_bar_count:
            raise ValueError("regime freeze candle count mismatch")
        last = self.candles[-1]
        if last.open_time_ms != self.analysis.source_cutoff_open_time_ms:
            raise ValueError("regime freeze source cutoff mismatch")
        if any(
            candle.close_time_ms > self.analysis.as_of_ms
            or candle.ingested_at_ms > self.analysis.as_of_ms
            or candle.source_timestamp_ms > self.analysis.as_of_ms
            for candle in self.candles
        ):
            raise ValueError("regime freeze contains future evidence")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("regime freeze identity mismatch")


def analyze_regime(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
    config: RegimeConfig = DEFAULT_REGIME_CONFIG,
) -> RegimeAnalysis:
    eligible = _eligible_candles(candles, as_of_ms=as_of_ms)
    window = eligible[-config.lookback_bars :]
    first = window[0]

    uncertainty: tuple[str, ...] = ()
    metrics: RegimeMetrics | None = None
    label = RegimeLabel.UNRESOLVED
    volatility = VolatilityState.UNRESOLVED

    gaps = detect_gaps(window, first.timeframe)
    if len(window) < config.minimum_bars:
        uncertainty = ("insufficient_history",)
    elif gaps:
        uncertainty = ("candle_gaps",)
    else:
        metrics = _metrics(window, config=config)
        volatility = _volatility_state(metrics, config=config)
        label, uncertainty = _label(metrics, config=config)

    payload = {
        "engine_version": REGIME_ENGINE_VERSION,
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
        "volatility": volatility,
        "metrics": metrics,
        "uncertainty_flags": uncertainty,
    }
    return RegimeAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=REGIME_ENGINE_VERSION,
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
        volatility=volatility,
        metrics=metrics,
        uncertainty_flags=uncertainty,
    )


def build_regime_evidence_freeze(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
    config: RegimeConfig = DEFAULT_REGIME_CONFIG,
) -> RegimeEvidenceFreeze:
    analysis = analyze_regime(candles, as_of_ms=as_of_ms, config=config)
    eligible = _eligible_candles(candles, as_of_ms=as_of_ms)
    consumed = tuple(eligible[-analysis.consumed_bar_count :])
    draft = RegimeEvidenceFreeze(
        freeze_identity="0" * 64,
        schema_version=REGIME_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        candles=consumed,
    )
    return RegimeEvidenceFreeze(
        freeze_identity=canonical_sha256(_freeze_payload(draft)),
        schema_version=draft.schema_version,
        analysis=draft.analysis,
        candles=draft.candles,
    )


def _eligible_candles(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
) -> tuple[Candle, ...]:
    if not candles:
        raise ValueError("regime analysis requires candles")
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
        raise ValueError("regime candle context mismatch")
    opens = tuple(candle.open_time_ms for candle in ordered)
    if len(set(opens)) != len(opens):
        raise ValueError("regime candle opens must be unique")

    eligible = tuple(
        candle
        for candle in ordered
        if candle.is_closed
        and candle.close_time_ms <= as_of_ms
        and candle.ingested_at_ms <= as_of_ms
        and candle.source_timestamp_ms <= as_of_ms
    )
    if not eligible:
        raise ValueError("regime analysis has no PIT-eligible closed candles")
    return eligible


def _metrics(
    candles: Sequence[Candle],
    *,
    config: RegimeConfig,
) -> RegimeMetrics:
    closes = tuple(candle.close for candle in candles)
    signed_displacement = (closes[-1] - closes[0]) / closes[0] * _BPS
    absolute_displacement = abs(signed_displacement)
    path = sum(
        (
            abs(right - left) / left * _BPS
            for left, right in pairwise(closes)
        ),
        start=Decimal(0),
    )
    efficiency = (
        Decimal(0) if path == Decimal(0) else absolute_displacement / path
    )

    ranges = tuple(
        (candle.high - candle.low) / candle.close * _BPS
        for candle in candles
    )
    recent_count = config.recent_volatility_bars
    baseline_ranges = ranges[:-recent_count]
    recent_ranges = ranges[-recent_count:]
    baseline = median(baseline_ranges)
    recent = median(recent_ranges)
    volatility_ratio = (
        Decimal(0) if baseline == Decimal(0) else recent / baseline
    )
    return RegimeMetrics(
        signed_displacement_bps=signed_displacement,
        absolute_displacement_bps=absolute_displacement,
        path_length_bps=path,
        efficiency_ratio=efficiency,
        baseline_range_bps=baseline,
        recent_range_bps=recent,
        volatility_ratio=volatility_ratio,
    )


def _label(
    metrics: RegimeMetrics,
    *,
    config: RegimeConfig,
) -> tuple[RegimeLabel, tuple[str, ...]]:
    if (
        metrics.efficiency_ratio >= config.trend_efficiency_min
        and metrics.absolute_displacement_bps
        >= config.trend_displacement_min_bps
    ):
        if metrics.signed_displacement_bps > Decimal(0):
            return RegimeLabel.TREND_UP, ()
        if metrics.signed_displacement_bps < Decimal(0):
            return RegimeLabel.TREND_DOWN, ()
        return RegimeLabel.TRANSITION, ("zero_signed_trend_displacement",)

    if (
        metrics.efficiency_ratio <= config.range_efficiency_max
        and metrics.absolute_displacement_bps
        <= config.range_displacement_max_bps
    ):
        return RegimeLabel.RANGE, ()

    flags: list[str] = ["mixed_directional_efficiency"]
    if (
        metrics.efficiency_ratio >= config.trend_efficiency_min
        and metrics.absolute_displacement_bps
        < config.trend_displacement_min_bps
    ):
        flags.append("low_magnitude_direction")
    return RegimeLabel.TRANSITION, tuple(flags)


def _volatility_state(
    metrics: RegimeMetrics,
    *,
    config: RegimeConfig,
) -> VolatilityState:
    if metrics.volatility_ratio >= config.volatility_expanded_ratio:
        return VolatilityState.EXPANDED
    if metrics.volatility_ratio <= config.volatility_compressed_ratio:
        return VolatilityState.COMPRESSED
    return VolatilityState.NORMAL


def _analysis_payload(analysis: RegimeAnalysis) -> dict[str, object]:
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
        "volatility": analysis.volatility,
        "metrics": analysis.metrics,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze_payload(freeze: RegimeEvidenceFreeze) -> dict[str, object]:
    return {
        "schema_version": freeze.schema_version,
        "analysis": freeze.analysis,
        "candles": freeze.candles,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
