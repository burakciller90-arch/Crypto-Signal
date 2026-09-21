from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from statistics import median

from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256

BREAKOUT_VOLATILITY_ENGINE_VERSION = "breakout-volatility-v1/1"
BREAKOUT_VOLATILITY_FREEZE_SCHEMA_VERSION = (
    "breakout-volatility-evidence-freeze-v1/1"
)
_BPS = Decimal(10_000)


class BreakoutLabel(StrEnum):
    BREAKOUT_UP = "breakout_up"
    BREAKOUT_DOWN = "breakout_down"
    PROBE_UP = "probe_up"
    PROBE_DOWN = "probe_down"
    INSIDE_RANGE = "inside_range"
    UNRESOLVED = "unresolved"


class BreakoutVolatilityState(StrEnum):
    COMPRESSED = "compressed"
    NORMAL = "normal"
    EXPANDED = "expanded"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class BreakoutVolatilityConfig:
    lookback_bars: int = 24
    minimum_bars: int = 20
    reference_bars: int = 12
    breakout_buffer_bps: Decimal = Decimal(20)
    volatility_expanded_ratio: Decimal = Decimal("1.50")
    volatility_compressed_ratio: Decimal = Decimal("0.75")

    def __post_init__(self) -> None:
        if self.minimum_bars < 4:
            raise ValueError("minimum_bars must be at least 4")
        if self.lookback_bars < self.minimum_bars:
            raise ValueError("lookback_bars must be >= minimum_bars")
        if not 2 <= self.reference_bars < self.minimum_bars:
            raise ValueError("reference_bars must fit inside minimum history")
        if self.breakout_buffer_bps < Decimal(0):
            raise ValueError("breakout buffer cannot be negative")
        if self.volatility_compressed_ratio <= Decimal(0):
            raise ValueError("compressed volatility ratio must be positive")
        if (
            self.volatility_compressed_ratio
            >= self.volatility_expanded_ratio
        ):
            raise ValueError(
                "compressed volatility ratio must be below expanded ratio"
            )


DEFAULT_BREAKOUT_VOLATILITY_CONFIG = BreakoutVolatilityConfig()


@dataclass(frozen=True, slots=True)
class BreakoutVolatilityMetrics:
    reference_high: Decimal
    reference_low: Decimal
    reference_width_bps: Decimal
    close_price: Decimal
    close_vs_high_bps: Decimal
    close_vs_low_bps: Decimal
    current_range_bps: Decimal
    baseline_range_bps: Decimal
    volatility_ratio: Decimal

    def __post_init__(self) -> None:
        if self.reference_high <= Decimal(0):
            raise ValueError("reference high must be positive")
        if self.reference_low <= Decimal(0):
            raise ValueError("reference low must be positive")
        if self.reference_high < self.reference_low:
            raise ValueError("reference high cannot be below reference low")
        if self.close_price <= Decimal(0):
            raise ValueError("close price must be positive")
        for label, value in (
            ("reference_width_bps", self.reference_width_bps),
            ("current_range_bps", self.current_range_bps),
            ("baseline_range_bps", self.baseline_range_bps),
            ("volatility_ratio", self.volatility_ratio),
        ):
            if value < Decimal(0):
                raise ValueError(f"{label} cannot be negative")


@dataclass(frozen=True, slots=True)
class BreakoutVolatilityAnalysis:
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
    label: BreakoutLabel
    volatility: BreakoutVolatilityState
    metrics: BreakoutVolatilityMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(
            self.evidence_identity,
            "breakout/volatility evidence identity",
        )
        if self.engine_version != BREAKOUT_VOLATILITY_ENGINE_VERSION:
            raise ValueError("unsupported breakout/volatility engine version")
        if self.as_of_ms < 0:
            raise ValueError("breakout/volatility as_of_ms must be non-negative")
        if self.market_available_at_ms > self.as_of_ms:
            raise ValueError("breakout/volatility market evidence is from the future")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("breakout/volatility observed evidence is from the future")
        if self.consumed_bar_count <= 0:
            raise ValueError(
                "breakout/volatility analysis must consume at least one bar"
            )
        if len(set(self.uncertainty_flags)) != len(self.uncertainty_flags):
            raise ValueError("breakout/volatility uncertainty flags must be unique")
        if self.label is BreakoutLabel.UNRESOLVED:
            if not self.uncertainty_flags:
                raise ValueError("unresolved breakout/volatility requires uncertainty")
            if self.metrics is not None:
                raise ValueError(
                    "unresolved breakout/volatility cannot fabricate metrics"
                )
            if self.volatility is not BreakoutVolatilityState.UNRESOLVED:
                raise ValueError(
                    "unresolved breakout requires unresolved volatility"
                )
        elif self.metrics is None:
            raise ValueError(
                "resolved breakout/volatility requires deterministic metrics"
            )
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("breakout/volatility evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class BreakoutVolatilityEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: BreakoutVolatilityAnalysis
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        _require_sha256(
            self.freeze_identity,
            "breakout/volatility freeze identity",
        )
        if self.schema_version != BREAKOUT_VOLATILITY_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported breakout/volatility freeze schema")
        if not self.candles:
            raise ValueError("breakout/volatility freeze requires consumed candles")
        if len(self.candles) != self.analysis.consumed_bar_count:
            raise ValueError("breakout/volatility freeze candle count mismatch")
        last = self.candles[-1]
        if last.open_time_ms != self.analysis.source_cutoff_open_time_ms:
            raise ValueError("breakout/volatility freeze source cutoff mismatch")
        if any(
            candle.close_time_ms > self.analysis.as_of_ms
            or candle.ingested_at_ms > self.analysis.as_of_ms
            or candle.source_timestamp_ms > self.analysis.as_of_ms
            for candle in self.candles
        ):
            raise ValueError("breakout/volatility freeze contains future evidence")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("breakout/volatility freeze identity mismatch")


def analyze_breakout_volatility(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
    config: BreakoutVolatilityConfig = DEFAULT_BREAKOUT_VOLATILITY_CONFIG,
) -> BreakoutVolatilityAnalysis:
    eligible = _eligible_candles(candles, as_of_ms=as_of_ms)
    window = eligible[-config.lookback_bars :]
    first = window[0]

    uncertainty: tuple[str, ...] = ()
    metrics: BreakoutVolatilityMetrics | None = None
    label = BreakoutLabel.UNRESOLVED
    volatility = BreakoutVolatilityState.UNRESOLVED

    gaps = detect_gaps(window, first.timeframe)
    if len(window) < config.minimum_bars:
        uncertainty = ("insufficient_history",)
    elif gaps:
        uncertainty = ("candle_gaps",)
    else:
        metrics = _metrics(window, config=config)
        if metrics is None:
            uncertainty = ("zero_baseline_range",)
        else:
            label, uncertainty = _label(metrics, config=config)
            volatility = _volatility_state(metrics, config=config)

    payload = {
        "engine_version": BREAKOUT_VOLATILITY_ENGINE_VERSION,
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
    return BreakoutVolatilityAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=BREAKOUT_VOLATILITY_ENGINE_VERSION,
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


def build_breakout_volatility_evidence_freeze(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
    config: BreakoutVolatilityConfig = DEFAULT_BREAKOUT_VOLATILITY_CONFIG,
) -> BreakoutVolatilityEvidenceFreeze:
    analysis = analyze_breakout_volatility(
        candles,
        as_of_ms=as_of_ms,
        config=config,
    )
    eligible = _eligible_candles(candles, as_of_ms=as_of_ms)
    consumed = tuple(eligible[-analysis.consumed_bar_count :])
    payload = {
        "schema_version": BREAKOUT_VOLATILITY_FREEZE_SCHEMA_VERSION,
        "analysis": analysis,
        "candles": consumed,
    }
    return BreakoutVolatilityEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=BREAKOUT_VOLATILITY_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        candles=consumed,
    )


def _eligible_candles(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
) -> tuple[Candle, ...]:
    if not candles:
        raise ValueError("breakout/volatility analysis requires candles")
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
        raise ValueError("breakout/volatility candle context mismatch")
    opens = tuple(candle.open_time_ms for candle in ordered)
    if len(set(opens)) != len(opens):
        raise ValueError("breakout/volatility candle opens must be unique")

    eligible = tuple(
        candle
        for candle in ordered
        if candle.is_closed
        and candle.close_time_ms <= as_of_ms
        and candle.ingested_at_ms <= as_of_ms
        and candle.source_timestamp_ms <= as_of_ms
    )
    if not eligible:
        raise ValueError(
            "breakout/volatility analysis has no PIT-eligible closed candles"
        )
    return eligible


def _metrics(
    candles: Sequence[Candle],
    *,
    config: BreakoutVolatilityConfig,
) -> BreakoutVolatilityMetrics | None:
    current = candles[-1]
    reference = candles[-1 - config.reference_bars : -1]
    reference_high = max(candle.high for candle in reference)
    reference_low = min(candle.low for candle in reference)

    prior_ranges = tuple(
        (candle.high - candle.low) / candle.close * _BPS
        for candle in candles[:-1]
    )
    baseline_range = median(prior_ranges)
    if baseline_range <= Decimal(0):
        return None

    current_range = (current.high - current.low) / current.close * _BPS
    volatility_ratio = current_range / baseline_range
    width = (reference_high - reference_low) / reference_low * _BPS
    close_vs_high = (current.close - reference_high) / reference_high * _BPS
    close_vs_low = (current.close - reference_low) / reference_low * _BPS

    return BreakoutVolatilityMetrics(
        reference_high=reference_high,
        reference_low=reference_low,
        reference_width_bps=width,
        close_price=current.close,
        close_vs_high_bps=close_vs_high,
        close_vs_low_bps=close_vs_low,
        current_range_bps=current_range,
        baseline_range_bps=baseline_range,
        volatility_ratio=volatility_ratio,
    )


def _label(
    metrics: BreakoutVolatilityMetrics,
    *,
    config: BreakoutVolatilityConfig,
) -> tuple[BreakoutLabel, tuple[str, ...]]:
    upper_threshold = metrics.reference_high * (
        Decimal(1) + config.breakout_buffer_bps / _BPS
    )
    lower_threshold = metrics.reference_low * (
        Decimal(1) - config.breakout_buffer_bps / _BPS
    )

    if metrics.close_price > upper_threshold:
        return BreakoutLabel.BREAKOUT_UP, ()
    if metrics.close_price < lower_threshold:
        return BreakoutLabel.BREAKOUT_DOWN, ()
    if metrics.close_price > metrics.reference_high:
        return BreakoutLabel.PROBE_UP, ("breakout_buffer_not_cleared",)
    if metrics.close_price < metrics.reference_low:
        return BreakoutLabel.PROBE_DOWN, ("breakout_buffer_not_cleared",)
    return BreakoutLabel.INSIDE_RANGE, ()


def _volatility_state(
    metrics: BreakoutVolatilityMetrics,
    *,
    config: BreakoutVolatilityConfig,
) -> BreakoutVolatilityState:
    if metrics.volatility_ratio >= config.volatility_expanded_ratio:
        return BreakoutVolatilityState.EXPANDED
    if metrics.volatility_ratio <= config.volatility_compressed_ratio:
        return BreakoutVolatilityState.COMPRESSED
    return BreakoutVolatilityState.NORMAL


def _analysis_payload(
    analysis: BreakoutVolatilityAnalysis,
) -> dict[str, object]:
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


def _freeze_payload(
    freeze: BreakoutVolatilityEvidenceFreeze,
) -> dict[str, object]:
    return {
        "schema_version": freeze.schema_version,
        "analysis": freeze.analysis,
        "candles": freeze.candles,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
