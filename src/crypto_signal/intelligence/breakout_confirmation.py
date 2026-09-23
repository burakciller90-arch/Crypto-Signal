"""M3 Slice 3: PIT-safe breakout confirmation/failure interaction evidence.

This layer combines already-accepted temporal flow, liquidity-sweep and absorption
freezes with closed candles. It does not recompute upstream evidence and does not
produce trade commands, probability or actor attribution.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.intelligence.liquidity_structure import LiquiditySide
from crypto_signal.intelligence.liquidity_sweep import (
    LiquiditySweepCandidate,
    LiquiditySweepEvidenceFreeze,
    LiquiditySweepStatus,
)
from crypto_signal.intelligence.order_flow_patterns import (
    AbsorptionCandidate,
    AbsorptionEvidenceFreeze,
    AbsorptionSide,
    PatternStatus,
)
from crypto_signal.intelligence.temporal_order_flow import (
    TemporalFlowEvidenceFreeze,
    TemporalFlowStatus,
)
from crypto_signal.ledger.serialization import canonical_sha256

BREAKOUT_ENGINE_VERSION = "m3-breakout-confirmation-slice3/1"
BREAKOUT_FREEZE_SCHEMA_VERSION = "m3-breakout-confirmation-freeze-v1/1"
_ZERO = Decimal(0)
_ONE = Decimal(1)
_BPS = Decimal(10000)


class BreakoutStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class BreakoutSide(StrEnum):
    UPSIDE = "upside"
    DOWNSIDE = "downside"


class BreakoutState(StrEnum):
    CONFIRMED = "breakout_confirmed_candidate"
    FAILURE = "breakout_failure_candidate"


@dataclass(frozen=True, slots=True)
class BreakoutConfig:
    minimum_closed_candles: int = 2
    minimum_close_distance_bps: Decimal = Decimal(10)
    minimum_taker_imbalance: Decimal = Decimal("0.15")
    reentry_tolerance_bps: Decimal = Decimal(10)
    absorption_level_tolerance_bps: Decimal = Decimal(15)

    def __post_init__(self) -> None:
        if self.minimum_closed_candles < 2:
            raise ValueError("minimum_closed_candles must be at least 2")
        for label, value in (
            ("minimum_close_distance_bps", self.minimum_close_distance_bps),
            ("reentry_tolerance_bps", self.reentry_tolerance_bps),
            ("absorption_level_tolerance_bps", self.absorption_level_tolerance_bps),
        ):
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
            if value <= _ZERO:
                raise ValueError(f"{label} must be positive")
        if (
            self.minimum_taker_imbalance.is_nan()
            or self.minimum_taker_imbalance.is_infinite()
        ):
            raise ValueError("minimum_taker_imbalance must be finite")
        if not _ZERO < self.minimum_taker_imbalance <= _ONE:
            raise ValueError("minimum_taker_imbalance must be inside (0,1]")

    @property
    def identity(self) -> str:
        return canonical_sha256(
            {
                "absorption_level_tolerance_bps": self.absorption_level_tolerance_bps,
                "minimum_close_distance_bps": self.minimum_close_distance_bps,
                "minimum_closed_candles": self.minimum_closed_candles,
                "minimum_taker_imbalance": self.minimum_taker_imbalance,
                "reentry_tolerance_bps": self.reentry_tolerance_bps,
            }
        )


DEFAULT_BREAKOUT_CONFIG = BreakoutConfig()


@dataclass(frozen=True, slots=True)
class BreakoutCandidate:
    side: BreakoutSide
    state: BreakoutState
    reference_level: Decimal
    sweep_first_interaction_ms: int
    sweep_last_interaction_ms: int
    latest_candle_identity: str
    latest_candle_close_ms: int
    latest_close: Decimal
    close_distance_bps: Decimal
    taker_imbalance: Decimal
    sweep_recovered: bool
    sweep_recovery_at_ms: int | None
    opposing_absorption_present: bool
    absorption_evidence_identity: str | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.reference_level <= _ZERO or self.latest_close <= _ZERO:
            raise ValueError("breakout prices must be positive")
        if self.latest_candle_close_ms < 0:
            raise ValueError("breakout candle timestamp cannot be negative")
        _sha(self.latest_candle_identity, "breakout latest candle")
        for label, value in (
            ("close_distance_bps", self.close_distance_bps),
            ("taker_imbalance", self.taker_imbalance),
        ):
            _finite(value, label)
        if self.close_distance_bps < _ZERO:
            raise ValueError("breakout close distance cannot be negative")
        if not Decimal(-1) <= self.taker_imbalance <= _ONE:
            raise ValueError("breakout taker imbalance outside [-1,1]")
        if self.sweep_recovered != (self.sweep_recovery_at_ms is not None):
            raise ValueError("breakout sweep recovery flag/timestamp mismatch")
        if self.opposing_absorption_present != (
            self.absorption_evidence_identity is not None
        ):
            raise ValueError("breakout absorption flag/identity mismatch")
        if self.absorption_evidence_identity is not None:
            _sha(self.absorption_evidence_identity, "breakout absorption evidence")
        if not self.uncertainty_flags:
            raise ValueError("breakout candidate requires uncertainty")
        if self.state is BreakoutState.CONFIRMED:
            if self.sweep_recovered or self.opposing_absorption_present:
                raise ValueError("confirmed breakout cannot carry recovery/opposing absorption")
            if self.side is BreakoutSide.UPSIDE and self.taker_imbalance <= _ZERO:
                raise ValueError("upside confirmation requires positive flow")
            if self.side is BreakoutSide.DOWNSIDE and self.taker_imbalance >= _ZERO:
                raise ValueError("downside confirmation requires negative flow")
        if self.state is BreakoutState.FAILURE:
            if not self.sweep_recovered or not self.opposing_absorption_present:
                raise ValueError("breakout failure requires recovery plus opposing absorption")


@dataclass(frozen=True, slots=True)
class BreakoutAnalysis:
    evidence_identity: str
    engine_version: str
    config_identity: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    observed_at_ms: int
    flow_evidence_identity: str
    flow_freeze_identity: str
    sweep_evidence_identity: str
    sweep_freeze_identity: str
    absorption_evidence_identity: str
    absorption_freeze_identity: str
    consumed_candle_count: int
    first_candle_identity: str | None
    last_candle_identity: str | None
    status: BreakoutStatus
    candidates: tuple[BreakoutCandidate, ...]
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("breakout evidence", self.evidence_identity),
            ("breakout config", self.config_identity),
            ("breakout flow evidence", self.flow_evidence_identity),
            ("breakout flow freeze", self.flow_freeze_identity),
            ("breakout sweep evidence", self.sweep_evidence_identity),
            ("breakout sweep freeze", self.sweep_freeze_identity),
            ("breakout absorption evidence", self.absorption_evidence_identity),
            ("breakout absorption freeze", self.absorption_freeze_identity),
        ):
            _sha(value, label)
        if self.engine_version != BREAKOUT_ENGINE_VERSION:
            raise ValueError("unsupported breakout engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("breakout symbol must be uppercase")
        if not self.timeframe:
            raise ValueError("breakout timeframe must be non-empty")
        if not 0 <= self.observed_at_ms <= self.as_of_ms:
            raise ValueError("breakout observed_at outside PIT boundary")
        if self.consumed_candle_count < 0:
            raise ValueError("negative breakout candle count")
        _validate_identity_bounds(
            self.consumed_candle_count,
            self.first_candle_identity,
            self.last_candle_identity,
        )
        if self.status is BreakoutStatus.UNRESOLVED:
            if self.candidates:
                raise ValueError("unresolved breakout cannot carry candidates")
            if not self.uncertainty_flags:
                raise ValueError("unresolved breakout requires uncertainty")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("breakout evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class BreakoutEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: BreakoutAnalysis
    flow_freeze: TemporalFlowEvidenceFreeze
    sweep_freeze: LiquiditySweepEvidenceFreeze
    absorption_freeze: AbsorptionEvidenceFreeze
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        _sha(self.freeze_identity, "breakout freeze")
        if self.schema_version != BREAKOUT_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported breakout freeze schema")
        if len(self.candles) != self.analysis.consumed_candle_count:
            raise ValueError("breakout candle count mismatch")
        if self.flow_freeze.freeze_identity != self.analysis.flow_freeze_identity:
            raise ValueError("breakout flow freeze mismatch")
        if self.sweep_freeze.freeze_identity != self.analysis.sweep_freeze_identity:
            raise ValueError("breakout sweep freeze mismatch")
        if self.absorption_freeze.freeze_identity != self.analysis.absorption_freeze_identity:
            raise ValueError("breakout absorption freeze mismatch")
        for candle in self.candles:
            _require_context(
                self.analysis.exchange,
                self.analysis.market_type,
                self.analysis.symbol,
                candle.exchange,
                candle.market_type,
                candle.symbol,
                "breakout candle",
            )
            if candle.timeframe != self.analysis.timeframe:
                raise ValueError("breakout candle timeframe mismatch")
            if (
                not candle.is_closed
                or candle.close_time_ms > self.analysis.as_of_ms
                or candle.source_timestamp_ms > self.analysis.as_of_ms
                or candle.ingested_at_ms > self.analysis.as_of_ms
            ):
                raise ValueError("breakout freeze contains non-PIT candle")
        expected = canonical_sha256(
            {
                "absorption_freeze_identity": self.absorption_freeze.freeze_identity,
                "analysis_identity": self.analysis.evidence_identity,
                "candle_identities": [_candle_identity(item) for item in self.candles],
                "flow_freeze_identity": self.flow_freeze.freeze_identity,
                "schema_version": BREAKOUT_FREEZE_SCHEMA_VERSION,
                "sweep_freeze_identity": self.sweep_freeze.freeze_identity,
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("breakout freeze identity mismatch")


def build_breakout_confirmation_freeze(
    candles: Sequence[Candle],
    flow_freeze: TemporalFlowEvidenceFreeze,
    sweep_freeze: LiquiditySweepEvidenceFreeze,
    absorption_freeze: AbsorptionEvidenceFreeze,
    *,
    as_of_ms: int,
    config: BreakoutConfig = DEFAULT_BREAKOUT_CONFIG,
) -> BreakoutEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("breakout as_of_ms must be nonnegative")
    ordered = tuple(sorted(candles, key=lambda item: (item.open_time_ms, item.close_time_ms)))
    if not ordered:
        raise ValueError("breakout requires source candles")
    _reject_duplicate_candles(ordered)

    exchange, market_type, symbol, timeframe = _candle_context(ordered)
    flow = flow_freeze.analysis
    sweep = sweep_freeze.analysis
    absorption = absorption_freeze.analysis

    for actual_exchange, actual_market_type, actual_symbol, label in (
        (flow.exchange, flow.market_type, flow.symbol, "flow"),
        (sweep.exchange, sweep.market_type, sweep.symbol, "sweep"),
        (absorption.exchange, absorption.market_type, absorption.symbol, "absorption"),
    ):
        _require_context(
            exchange,
            market_type,
            symbol,
            actual_exchange,
            actual_market_type,
            actual_symbol,
            f"breakout {label}",
        )

    if not (
        flow.as_of_ms == sweep.as_of_ms == absorption.as_of_ms == as_of_ms
    ):
        raise ValueError("breakout requires exact upstream as_of alignment")
    if absorption_freeze.flow_freeze.freeze_identity != flow_freeze.freeze_identity:
        raise ValueError("breakout absorption must use the same flow freeze")

    selected = tuple(
        item
        for item in ordered
        if item.is_closed
        and item.close_time_ms <= as_of_ms
        and item.source_timestamp_ms <= as_of_ms
        and item.ingested_at_ms <= as_of_ms
        and item.open_time_ms >= flow.window_start_ms
    )
    flags: list[str] = [
        "candidate_not_trade_command",
        "breakout_confirmation_not_probability",
        "sweep_and_absorption_are_bounded_evidence",
    ]
    status = BreakoutStatus.MEASURED
    candidates: tuple[BreakoutCandidate, ...] = ()

    if flow.status is not TemporalFlowStatus.MEASURED or flow.metrics is None:
        status = BreakoutStatus.UNRESOLVED
        flags.append("temporal_flow_unresolved")
    elif sweep.status is not LiquiditySweepStatus.MEASURED:
        status = BreakoutStatus.UNRESOLVED
        flags.append("liquidity_sweep_unresolved")
    elif absorption.status is not PatternStatus.MEASURED:
        status = BreakoutStatus.UNRESOLVED
        flags.append("absorption_unresolved")
    elif len(selected) < config.minimum_closed_candles:
        status = BreakoutStatus.UNRESOLVED
        flags.append("insufficient_closed_candle_coverage")
    else:
        latest = selected[-1]
        found: list[BreakoutCandidate] = []
        for sweep_candidate in sweep.candidates:
            candidate = _candidate(
                sweep_candidate,
                latest,
                flow.metrics.taker_imbalance,
                absorption_freeze,
                config,
            )
            if candidate is not None:
                found.append(candidate)
        candidates = tuple(
            sorted(
                found,
                key=lambda item: (
                    item.latest_candle_close_ms,
                    item.reference_level,
                    item.side.value,
                    item.state.value,
                ),
            )
        )
        if not candidates:
            flags.append("no_qualified_breakout_confirmation_or_failure")

    observed_at_ms = max(
        flow.observed_at_ms,
        sweep.observed_at_ms,
        absorption.observed_at_ms,
        max((item.ingested_at_ms for item in selected), default=0),
    )
    payload: dict[str, object] = {
        "absorption_evidence_identity": absorption.evidence_identity,
        "absorption_freeze_identity": absorption_freeze.freeze_identity,
        "as_of_ms": as_of_ms,
        "candidates": [_candidate_payload(item) for item in candidates],
        "config_identity": config.identity,
        "consumed_candle_count": len(selected),
        "engine_version": BREAKOUT_ENGINE_VERSION,
        "exchange": exchange,
        "first_candle_identity": None if not selected else _candle_identity(selected[0]),
        "flow_evidence_identity": flow.evidence_identity,
        "flow_freeze_identity": flow_freeze.freeze_identity,
        "last_candle_identity": None if not selected else _candle_identity(selected[-1]),
        "market_type": market_type,
        "observed_at_ms": observed_at_ms,
        "status": status,
        "sweep_evidence_identity": sweep.evidence_identity,
        "sweep_freeze_identity": sweep_freeze.freeze_identity,
        "symbol": symbol,
        "timeframe": timeframe,
        "uncertainty_flags": tuple(flags),
    }
    analysis = BreakoutAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=BREAKOUT_ENGINE_VERSION,
        config_identity=config.identity,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        as_of_ms=as_of_ms,
        observed_at_ms=observed_at_ms,
        flow_evidence_identity=flow.evidence_identity,
        flow_freeze_identity=flow_freeze.freeze_identity,
        sweep_evidence_identity=sweep.evidence_identity,
        sweep_freeze_identity=sweep_freeze.freeze_identity,
        absorption_evidence_identity=absorption.evidence_identity,
        absorption_freeze_identity=absorption_freeze.freeze_identity,
        consumed_candle_count=len(selected),
        first_candle_identity=None if not selected else _candle_identity(selected[0]),
        last_candle_identity=None if not selected else _candle_identity(selected[-1]),
        status=status,
        candidates=candidates,
        uncertainty_flags=tuple(flags),
    )
    return BreakoutEvidenceFreeze(
        freeze_identity=canonical_sha256(
            {
                "absorption_freeze_identity": absorption_freeze.freeze_identity,
                "analysis_identity": analysis.evidence_identity,
                "candle_identities": [_candle_identity(item) for item in selected],
                "flow_freeze_identity": flow_freeze.freeze_identity,
                "schema_version": BREAKOUT_FREEZE_SCHEMA_VERSION,
                "sweep_freeze_identity": sweep_freeze.freeze_identity,
            }
        ),
        schema_version=BREAKOUT_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        flow_freeze=flow_freeze,
        sweep_freeze=sweep_freeze,
        absorption_freeze=absorption_freeze,
        candles=selected,
    )


def _candidate(
    sweep: LiquiditySweepCandidate,
    latest: Candle,
    taker_imbalance: Decimal,
    absorption_freeze: AbsorptionEvidenceFreeze,
    config: BreakoutConfig,
) -> BreakoutCandidate | None:
    level = sweep.pool_price
    if sweep.side is LiquiditySide.ASK:
        side = BreakoutSide.UPSIDE
        close_distance = max(_ZERO, (latest.close - level) / level * _BPS)
        confirmed_close = latest.close >= level * (
            _ONE + config.minimum_close_distance_bps / _BPS
        )
        reentered = latest.close <= level * (
            _ONE + config.reentry_tolerance_bps / _BPS
        )
        flow_confirms = taker_imbalance >= config.minimum_taker_imbalance
        absorption_side = AbsorptionSide.ASK
    else:
        side = BreakoutSide.DOWNSIDE
        close_distance = max(_ZERO, (level - latest.close) / level * _BPS)
        confirmed_close = latest.close <= level * (
            _ONE - config.minimum_close_distance_bps / _BPS
        )
        reentered = latest.close >= level * (
            _ONE - config.reentry_tolerance_bps / _BPS
        )
        flow_confirms = taker_imbalance <= -config.minimum_taker_imbalance
        absorption_side = AbsorptionSide.BID

    absorption = _nearby_absorption(
        absorption_freeze,
        side=absorption_side,
        level=level,
        tolerance_bps=config.absorption_level_tolerance_bps,
    )

    if (
        confirmed_close
        and flow_confirms
        and not sweep.recovered
        and absorption is None
    ):
        return BreakoutCandidate(
            side=side,
            state=BreakoutState.CONFIRMED,
            reference_level=level,
            sweep_first_interaction_ms=sweep.first_interaction_ms,
            sweep_last_interaction_ms=sweep.last_interaction_ms,
            latest_candle_identity=_candle_identity(latest),
            latest_candle_close_ms=latest.close_time_ms,
            latest_close=latest.close,
            close_distance_bps=close_distance,
            taker_imbalance=taker_imbalance,
            sweep_recovered=False,
            sweep_recovery_at_ms=None,
            opposing_absorption_present=False,
            absorption_evidence_identity=None,
            uncertainty_flags=(
                "candidate_only_not_future_return_prediction",
                "confirmation_requires_current_frozen_evidence",
            ),
        )

    if sweep.recovered and reentered and absorption is not None:
        return BreakoutCandidate(
            side=side,
            state=BreakoutState.FAILURE,
            reference_level=level,
            sweep_first_interaction_ms=sweep.first_interaction_ms,
            sweep_last_interaction_ms=sweep.last_interaction_ms,
            latest_candle_identity=_candle_identity(latest),
            latest_candle_close_ms=latest.close_time_ms,
            latest_close=latest.close,
            close_distance_bps=close_distance,
            taker_imbalance=taker_imbalance,
            sweep_recovered=True,
            sweep_recovery_at_ms=sweep.recovery_at_ms,
            opposing_absorption_present=True,
            absorption_evidence_identity=absorption_freeze.analysis.evidence_identity,
            uncertainty_flags=(
                "candidate_only_breakout_failure_context",
                "absorption_not_proof_of_actor_or_iceberg",
            ),
        )
    return None


def _nearby_absorption(
    freeze: AbsorptionEvidenceFreeze,
    *,
    side: AbsorptionSide,
    level: Decimal,
    tolerance_bps: Decimal,
) -> AbsorptionCandidate | None:
    tolerance = tolerance_bps / _BPS
    lower = level * (_ONE - tolerance)
    upper = level * (_ONE + tolerance)
    for candidate in freeze.analysis.candidates:
        if candidate.side is side and lower <= candidate.level_price <= upper:
            return candidate
    return None


def _candle_context(
    candles: tuple[Candle, ...],
) -> tuple[Exchange, MarketType, str, str]:
    first = candles[0]
    expected = (first.exchange, first.market_type, first.symbol, first.timeframe)
    for candle in candles[1:]:
        actual = (candle.exchange, candle.market_type, candle.symbol, candle.timeframe)
        if actual != expected:
            raise ValueError("mixed breakout candle context")
    return expected


def _reject_duplicate_candles(candles: tuple[Candle, ...]) -> None:
    identities = [_candle_identity(item) for item in candles]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate breakout candle identity")


def _require_context(
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    actual_exchange: Exchange,
    actual_market_type: MarketType,
    actual_symbol: str,
    label: str,
) -> None:
    if (
        actual_exchange is not exchange
        or actual_market_type is not market_type
        or actual_symbol != symbol
    ):
        raise ValueError(f"{label} market context mismatch")


def _candle_identity(candle: Candle) -> str:
    return canonical_sha256(
        {
            "adapter_version": candle.adapter_version,
            "close": candle.close,
            "close_time_ms": candle.close_time_ms,
            "exchange": candle.exchange,
            "high": candle.high,
            "ingested_at_ms": candle.ingested_at_ms,
            "is_closed": candle.is_closed,
            "low": candle.low,
            "market_type": candle.market_type,
            "open": candle.open,
            "open_time_ms": candle.open_time_ms,
            "quote_volume": candle.quote_volume,
            "source": candle.source,
            "source_timestamp_ms": candle.source_timestamp_ms,
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "trade_count": candle.trade_count,
            "volume": candle.volume,
        }
    )


def _candidate_payload(candidate: BreakoutCandidate) -> dict[str, object]:
    return {
        field: getattr(candidate, field)
        for field in candidate.__dataclass_fields__
    }


def _analysis_payload(analysis: BreakoutAnalysis) -> dict[str, object]:
    return {
        "absorption_evidence_identity": analysis.absorption_evidence_identity,
        "absorption_freeze_identity": analysis.absorption_freeze_identity,
        "as_of_ms": analysis.as_of_ms,
        "candidates": [_candidate_payload(item) for item in analysis.candidates],
        "config_identity": analysis.config_identity,
        "consumed_candle_count": analysis.consumed_candle_count,
        "engine_version": analysis.engine_version,
        "exchange": analysis.exchange,
        "first_candle_identity": analysis.first_candle_identity,
        "flow_evidence_identity": analysis.flow_evidence_identity,
        "flow_freeze_identity": analysis.flow_freeze_identity,
        "last_candle_identity": analysis.last_candle_identity,
        "market_type": analysis.market_type,
        "observed_at_ms": analysis.observed_at_ms,
        "status": analysis.status,
        "sweep_evidence_identity": analysis.sweep_evidence_identity,
        "sweep_freeze_identity": analysis.sweep_freeze_identity,
        "symbol": analysis.symbol,
        "timeframe": analysis.timeframe,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _validate_identity_bounds(
    count: int,
    first_identity: str | None,
    last_identity: str | None,
) -> None:
    if count == 0:
        if first_identity is not None or last_identity is not None:
            raise ValueError("empty breakout candle set cannot carry identities")
        return
    if first_identity is None or last_identity is None:
        raise ValueError("nonempty breakout candle set requires boundary identities")
    _sha(first_identity, "first breakout candle")
    _sha(last_identity, "last breakout candle")


def _finite(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be SHA256")
