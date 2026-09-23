"""M3 Slice 2: PIT-safe price/CVD divergence and bounded absorption evidence.

These engines produce research evidence candidates only. They do not predict returns,
identify actors, prove iceberg execution, or authorize trades.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from crypto_signal.data.microstructure import AggressorSide, PublicTradeObservation
from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.intelligence.liquidity_structure import (
    LiquidityLevelEvidence,
    LiquidityStructureEvidenceFreeze,
    LiquidityStructureStatus,
)
from crypto_signal.intelligence.temporal_order_flow import (
    TemporalFlowEvidenceFreeze,
    TemporalFlowStatus,
)
from crypto_signal.ledger.serialization import canonical_sha256

DIVERGENCE_ENGINE_VERSION = "m3-price-cvd-divergence-slice2/1"
DIVERGENCE_FREEZE_SCHEMA_VERSION = "m3-price-cvd-divergence-freeze-v1/1"
ABSORPTION_ENGINE_VERSION = "m3-absorption-slice2/1"
ABSORPTION_FREEZE_SCHEMA_VERSION = "m3-absorption-freeze-v1/1"

_ZERO = Decimal(0)
_ONE = Decimal(1)
_BPS = Decimal(10000)


class PatternStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class DivergenceSide(StrEnum):
    BULLISH = "bullish_price_cvd_divergence_candidate"
    BEARISH = "bearish_price_cvd_divergence_candidate"


class AbsorptionSide(StrEnum):
    BID = "bid_absorption_candidate"
    ASK = "ask_absorption_candidate"


@dataclass(frozen=True, slots=True)
class DivergenceConfig:
    minimum_closed_candles: int = 5
    pivot_radius: int = 1
    minimum_price_change_bps: Decimal = Decimal(5)
    minimum_cvd_change_notional: Decimal = Decimal(0)
    max_endpoint_trade_gap_ms: int = 30_000
    minimum_endpoint_trade_count: int = 1

    def __post_init__(self) -> None:
        if self.minimum_closed_candles < 5:
            raise ValueError("minimum_closed_candles must be at least 5")
        if self.pivot_radius < 1:
            raise ValueError("pivot_radius must be positive")
        if self.minimum_endpoint_trade_count < 1:
            raise ValueError("minimum_endpoint_trade_count must be positive")
        if self.max_endpoint_trade_gap_ms <= 0:
            raise ValueError("max_endpoint_trade_gap_ms must be positive")
        for label, value in (
            ("minimum_price_change_bps", self.minimum_price_change_bps),
            ("minimum_cvd_change_notional", self.minimum_cvd_change_notional),
        ):
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
            if value < _ZERO:
                raise ValueError(f"{label} cannot be negative")

    @property
    def identity(self) -> str:
        return canonical_sha256(
            {
                "max_endpoint_trade_gap_ms": self.max_endpoint_trade_gap_ms,
                "minimum_closed_candles": self.minimum_closed_candles,
                "minimum_cvd_change_notional": self.minimum_cvd_change_notional,
                "minimum_endpoint_trade_count": self.minimum_endpoint_trade_count,
                "minimum_price_change_bps": self.minimum_price_change_bps,
                "pivot_radius": self.pivot_radius,
            }
        )


DEFAULT_DIVERGENCE_CONFIG = DivergenceConfig()


@dataclass(frozen=True, slots=True)
class DivergenceCandidate:
    side: DivergenceSide
    first_candle_identity: str
    second_candle_identity: str
    first_open_time_ms: int
    second_open_time_ms: int
    first_endpoint_ms: int
    second_endpoint_ms: int
    first_price: Decimal
    second_price: Decimal
    price_change_bps: Decimal
    first_cvd_notional: Decimal
    second_cvd_notional: Decimal
    cvd_change_notional: Decimal
    first_endpoint_trade_count: int
    second_endpoint_trade_count: int
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _sha(self.first_candle_identity, "first divergence candle")
        _sha(self.second_candle_identity, "second divergence candle")
        if self.second_open_time_ms <= self.first_open_time_ms:
            raise ValueError("divergence candles must be chronological")
        if self.second_endpoint_ms <= self.first_endpoint_ms:
            raise ValueError("divergence endpoints must be chronological")
        if min(self.first_endpoint_trade_count, self.second_endpoint_trade_count) < 1:
            raise ValueError("divergence endpoints require real trade coverage")
        for label, value in (
            ("first_price", self.first_price),
            ("second_price", self.second_price),
            ("price_change_bps", self.price_change_bps),
            ("first_cvd_notional", self.first_cvd_notional),
            ("second_cvd_notional", self.second_cvd_notional),
            ("cvd_change_notional", self.cvd_change_notional),
        ):
            _finite(value, label)
        if self.first_price <= _ZERO or self.second_price <= _ZERO:
            raise ValueError("divergence prices must be positive")
        if self.price_change_bps <= _ZERO:
            raise ValueError("divergence price change must be positive")
        if not self.uncertainty_flags:
            raise ValueError("divergence candidate requires uncertainty")
        if (
            self.side is DivergenceSide.BULLISH
            and (self.second_price >= self.first_price or self.cvd_change_notional <= _ZERO)
        ):
            raise ValueError("bullish divergence direction mismatch")
        if (
            self.side is DivergenceSide.BEARISH
            and (self.second_price <= self.first_price or self.cvd_change_notional >= _ZERO)
        ):
            raise ValueError("bearish divergence direction mismatch")


@dataclass(frozen=True, slots=True)
class DivergenceAnalysis:
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
    consumed_candle_count: int
    first_candle_identity: str | None
    last_candle_identity: str | None
    latest_candle_age_ms: int | None
    status: PatternStatus
    candidates: tuple[DivergenceCandidate, ...]
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _sha(self.evidence_identity, "divergence evidence")
        _sha(self.config_identity, "divergence config")
        _sha(self.flow_evidence_identity, "divergence flow evidence")
        _sha(self.flow_freeze_identity, "divergence flow freeze")
        if self.engine_version != DIVERGENCE_ENGINE_VERSION:
            raise ValueError("unsupported divergence engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("divergence symbol must be uppercase")
        if not self.timeframe:
            raise ValueError("divergence timeframe must be non-empty")
        if not 0 <= self.observed_at_ms <= self.as_of_ms:
            raise ValueError("divergence observed_at outside PIT boundary")
        if self.consumed_candle_count < 0:
            raise ValueError("negative divergence candle count")
        _validate_identity_bounds(
            self.consumed_candle_count,
            self.first_candle_identity,
            self.last_candle_identity,
            "divergence candle",
        )
        if self.latest_candle_age_ms is not None and self.latest_candle_age_ms < 0:
            raise ValueError("negative latest divergence candle age")
        if self.status is PatternStatus.UNRESOLVED:
            if self.candidates:
                raise ValueError("unresolved divergence cannot carry candidates")
            if not self.uncertainty_flags:
                raise ValueError("unresolved divergence requires uncertainty")
        if self.evidence_identity != canonical_sha256(_divergence_analysis_payload(self)):
            raise ValueError("divergence evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class DivergenceEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: DivergenceAnalysis
    flow_freeze: TemporalFlowEvidenceFreeze
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        _sha(self.freeze_identity, "divergence freeze")
        if self.schema_version != DIVERGENCE_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported divergence freeze schema")
        if len(self.candles) != self.analysis.consumed_candle_count:
            raise ValueError("divergence candle count mismatch")
        if self.flow_freeze.analysis.evidence_identity != self.analysis.flow_evidence_identity:
            raise ValueError("divergence flow evidence mismatch")
        if self.flow_freeze.freeze_identity != self.analysis.flow_freeze_identity:
            raise ValueError("divergence flow freeze mismatch")
        for candle in self.candles:
            _require_candle_context(candle, self.analysis)
            if (
                not candle.is_closed
                or candle.close_time_ms > self.analysis.as_of_ms
                or candle.source_timestamp_ms > self.analysis.as_of_ms
                or candle.ingested_at_ms > self.analysis.as_of_ms
            ):
                raise ValueError("divergence freeze contains non-PIT candle")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "candle_identities": [_candle_identity(item) for item in self.candles],
                "flow_freeze_identity": self.flow_freeze.freeze_identity,
                "schema_version": DIVERGENCE_FREEZE_SCHEMA_VERSION,
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("divergence freeze identity mismatch")


@dataclass(frozen=True, slots=True)
class AbsorptionConfig:
    interaction_tolerance_bps: Decimal = Decimal(15)
    minimum_aggressor_share: Decimal = Decimal("0.60")
    minimum_aggressive_trade_count: int = 2
    minimum_replenishment_cycles: int = 1
    minimum_replenishment_fraction: Decimal = Decimal("0.25")
    minimum_level_presence_fraction: Decimal = Decimal("0.50")
    max_price_nonresponse_bps: Decimal = Decimal(20)

    def __post_init__(self) -> None:
        for label, value in (
            ("interaction_tolerance_bps", self.interaction_tolerance_bps),
            ("max_price_nonresponse_bps", self.max_price_nonresponse_bps),
        ):
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
            if value <= _ZERO:
                raise ValueError(f"{label} must be positive")
        for label, value in (
            ("minimum_aggressor_share", self.minimum_aggressor_share),
            ("minimum_replenishment_fraction", self.minimum_replenishment_fraction),
            ("minimum_level_presence_fraction", self.minimum_level_presence_fraction),
        ):
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
            if not _ZERO < value <= _ONE:
                raise ValueError(f"{label} must be inside (0,1]")
        if self.minimum_aggressive_trade_count < 1:
            raise ValueError("minimum_aggressive_trade_count must be positive")
        if self.minimum_replenishment_cycles < 1:
            raise ValueError("minimum_replenishment_cycles must be positive")

    @property
    def identity(self) -> str:
        return canonical_sha256(
            {
                "interaction_tolerance_bps": self.interaction_tolerance_bps,
                "max_price_nonresponse_bps": self.max_price_nonresponse_bps,
                "minimum_aggressive_trade_count": self.minimum_aggressive_trade_count,
                "minimum_aggressor_share": self.minimum_aggressor_share,
                "minimum_level_presence_fraction": self.minimum_level_presence_fraction,
                "minimum_replenishment_cycles": self.minimum_replenishment_cycles,
                "minimum_replenishment_fraction": self.minimum_replenishment_fraction,
            }
        )


DEFAULT_ABSORPTION_CONFIG = AbsorptionConfig()


@dataclass(frozen=True, slots=True)
class AbsorptionCandidate:
    side: AbsorptionSide
    level_price: Decimal
    level_presence_fraction: Decimal
    level_materiality_multiple: Decimal
    aggressive_trade_count: int
    opposing_trade_count: int
    aggressive_notional: Decimal
    opposing_notional: Decimal
    aggressor_share: Decimal
    replenishment_notional: Decimal
    replenishment_cycles: int
    replenishment_fraction_of_aggressive_flow: Decimal
    max_price_response_bps: Decimal
    first_interaction_ms: int
    last_interaction_ms: int
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        if min(self.aggressive_trade_count, self.opposing_trade_count) < 0:
            raise ValueError("absorption trade counts cannot be negative")
        if self.aggressive_trade_count <= 0:
            raise ValueError("absorption candidate requires aggressive trades")
        if self.replenishment_cycles <= 0:
            raise ValueError("absorption candidate requires replenishment")
        if self.last_interaction_ms < self.first_interaction_ms:
            raise ValueError("absorption interaction ordering invalid")
        for label, value in (
            ("level_price", self.level_price),
            ("level_presence_fraction", self.level_presence_fraction),
            ("level_materiality_multiple", self.level_materiality_multiple),
            ("aggressive_notional", self.aggressive_notional),
            ("opposing_notional", self.opposing_notional),
            ("aggressor_share", self.aggressor_share),
            ("replenishment_notional", self.replenishment_notional),
            (
                "replenishment_fraction_of_aggressive_flow",
                self.replenishment_fraction_of_aggressive_flow,
            ),
            ("max_price_response_bps", self.max_price_response_bps),
        ):
            _finite(value, label)
        if self.level_price <= _ZERO:
            raise ValueError("absorption level price must be positive")
        if not _ZERO < self.level_presence_fraction <= _ONE:
            raise ValueError("absorption level presence outside (0,1]")
        if self.level_materiality_multiple <= _ZERO:
            raise ValueError("absorption level materiality must be positive")
        if self.aggressive_notional <= _ZERO or self.opposing_notional < _ZERO:
            raise ValueError("absorption notional invalid")
        if not _ZERO < self.aggressor_share <= _ONE:
            raise ValueError("absorption aggressor share outside (0,1]")
        if self.replenishment_notional <= _ZERO:
            raise ValueError("absorption replenishment must be positive")
        if self.replenishment_fraction_of_aggressive_flow <= _ZERO:
            raise ValueError("absorption replenishment fraction must be positive")
        if self.max_price_response_bps < _ZERO:
            raise ValueError("absorption price response cannot be negative")
        if not self.uncertainty_flags:
            raise ValueError("absorption candidate requires uncertainty")


@dataclass(frozen=True, slots=True)
class AbsorptionAnalysis:
    evidence_identity: str
    engine_version: str
    config_identity: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    as_of_ms: int
    observed_at_ms: int
    flow_evidence_identity: str
    flow_freeze_identity: str
    structure_evidence_identity: str
    structure_freeze_identity: str
    overlap_start_ms: int | None
    overlap_end_ms: int | None
    status: PatternStatus
    candidates: tuple[AbsorptionCandidate, ...]
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("absorption evidence", self.evidence_identity),
            ("absorption config", self.config_identity),
            ("absorption flow evidence", self.flow_evidence_identity),
            ("absorption flow freeze", self.flow_freeze_identity),
            ("absorption structure evidence", self.structure_evidence_identity),
            ("absorption structure freeze", self.structure_freeze_identity),
        ):
            _sha(value, label)
        if self.engine_version != ABSORPTION_ENGINE_VERSION:
            raise ValueError("unsupported absorption engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("absorption symbol must be uppercase")
        if not 0 <= self.observed_at_ms <= self.as_of_ms:
            raise ValueError("absorption observed_at outside PIT boundary")
        if (self.overlap_start_ms is None) != (self.overlap_end_ms is None):
            raise ValueError("absorption overlap bounds must be paired")
        if (
            self.overlap_start_ms is not None
            and self.overlap_end_ms is not None
            and not 0 <= self.overlap_start_ms <= self.overlap_end_ms <= self.as_of_ms
        ):
            raise ValueError("invalid absorption overlap window")
        if self.status is PatternStatus.UNRESOLVED:
            if self.candidates:
                raise ValueError("unresolved absorption cannot carry candidates")
            if not self.uncertainty_flags:
                raise ValueError("unresolved absorption requires uncertainty")
        if self.evidence_identity != canonical_sha256(_absorption_analysis_payload(self)):
            raise ValueError("absorption evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class AbsorptionEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: AbsorptionAnalysis
    flow_freeze: TemporalFlowEvidenceFreeze
    structure_freeze: LiquidityStructureEvidenceFreeze

    def __post_init__(self) -> None:
        _sha(self.freeze_identity, "absorption freeze")
        if self.schema_version != ABSORPTION_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported absorption freeze schema")
        if self.flow_freeze.freeze_identity != self.analysis.flow_freeze_identity:
            raise ValueError("absorption flow freeze mismatch")
        if self.structure_freeze.freeze_identity != self.analysis.structure_freeze_identity:
            raise ValueError("absorption structure freeze mismatch")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "flow_freeze_identity": self.flow_freeze.freeze_identity,
                "schema_version": ABSORPTION_FREEZE_SCHEMA_VERSION,
                "structure_freeze_identity": self.structure_freeze.freeze_identity,
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("absorption freeze identity mismatch")


def build_price_cvd_divergence_freeze(
    candles: Sequence[Candle],
    flow_freeze: TemporalFlowEvidenceFreeze,
    *,
    as_of_ms: int,
    config: DivergenceConfig = DEFAULT_DIVERGENCE_CONFIG,
) -> DivergenceEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("divergence as_of_ms must be nonnegative")
    flow = flow_freeze.analysis
    ordered = tuple(
        sorted(candles, key=lambda item: (item.open_time_ms, item.close_time_ms))
    )
    if not ordered:
        raise ValueError("divergence requires source candles")
    _reject_duplicate_candles(ordered)
    exchange, market_type, symbol, timeframe = _candle_context(ordered)
    _require_market_context(
        exchange,
        market_type,
        symbol,
        flow.exchange,
        flow.market_type,
        flow.symbol,
        "divergence flow",
    )
    if flow.as_of_ms != as_of_ms:
        raise ValueError("divergence requires exact flow/as_of alignment")

    selected = tuple(
        item
        for item in ordered
        if item.is_closed
        and item.close_time_ms <= as_of_ms
        and item.source_timestamp_ms <= as_of_ms
        and item.ingested_at_ms <= as_of_ms
        and item.open_time_ms >= flow.window_start_ms
    )
    flags: list[str] = ["window_local_cvd_only", "candidate_not_prediction"]
    status = PatternStatus.MEASURED
    candidates: tuple[DivergenceCandidate, ...] = ()

    if flow.status is not TemporalFlowStatus.MEASURED or flow.metrics is None:
        status = PatternStatus.UNRESOLVED
        flags.append("temporal_flow_unresolved")
    elif len(selected) < config.minimum_closed_candles:
        status = PatternStatus.UNRESOLVED
        flags.append("insufficient_closed_candle_coverage")
    elif len(selected) < config.pivot_radius * 2 + 3:
        status = PatternStatus.UNRESOLVED
        flags.append("insufficient_candles_for_pivots")
    else:
        lows = _pivot_indices(selected, radius=config.pivot_radius, use_low=True)
        highs = _pivot_indices(selected, radius=config.pivot_radius, use_low=False)
        found: list[DivergenceCandidate] = []
        found.extend(
            item
            for pair in pairwise(lows)
            if (
                item := _divergence_candidate(
                    selected[pair[0]],
                    selected[pair[1]],
                    flow_freeze,
                    side=DivergenceSide.BULLISH,
                    config=config,
                )
            )
            is not None
        )
        found.extend(
            item
            for pair in pairwise(highs)
            if (
                item := _divergence_candidate(
                    selected[pair[0]],
                    selected[pair[1]],
                    flow_freeze,
                    side=DivergenceSide.BEARISH,
                    config=config,
                )
            )
            is not None
        )
        candidates = tuple(
            sorted(found, key=lambda item: (item.second_endpoint_ms, item.side.value))
        )
        if not candidates:
            flags.append("no_qualified_price_cvd_divergence_candidate")

    observed_at_ms = max(
        [flow.observed_at_ms, *(item.ingested_at_ms for item in selected)],
        default=flow.observed_at_ms,
    )
    payload: dict[str, object] = {
        "as_of_ms": as_of_ms,
        "candidates": [_divergence_candidate_payload(item) for item in candidates],
        "config_identity": config.identity,
        "consumed_candle_count": len(selected),
        "engine_version": DIVERGENCE_ENGINE_VERSION,
        "exchange": exchange,
        "first_candle_identity": None if not selected else _candle_identity(selected[0]),
        "flow_evidence_identity": flow.evidence_identity,
        "flow_freeze_identity": flow_freeze.freeze_identity,
        "last_candle_identity": None if not selected else _candle_identity(selected[-1]),
        "latest_candle_age_ms": None if not selected else as_of_ms - selected[-1].close_time_ms,
        "market_type": market_type,
        "observed_at_ms": observed_at_ms,
        "status": status,
        "symbol": symbol,
        "timeframe": timeframe,
        "uncertainty_flags": tuple(flags),
    }
    analysis = DivergenceAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=DIVERGENCE_ENGINE_VERSION,
        config_identity=config.identity,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        as_of_ms=as_of_ms,
        observed_at_ms=observed_at_ms,
        flow_evidence_identity=flow.evidence_identity,
        flow_freeze_identity=flow_freeze.freeze_identity,
        consumed_candle_count=len(selected),
        first_candle_identity=None if not selected else _candle_identity(selected[0]),
        last_candle_identity=None if not selected else _candle_identity(selected[-1]),
        latest_candle_age_ms=None if not selected else as_of_ms - selected[-1].close_time_ms,
        status=status,
        candidates=candidates,
        uncertainty_flags=tuple(flags),
    )
    return DivergenceEvidenceFreeze(
        freeze_identity=canonical_sha256(
            {
                "analysis_identity": analysis.evidence_identity,
                "candle_identities": [_candle_identity(item) for item in selected],
                "flow_freeze_identity": flow_freeze.freeze_identity,
                "schema_version": DIVERGENCE_FREEZE_SCHEMA_VERSION,
            }
        ),
        schema_version=DIVERGENCE_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        flow_freeze=flow_freeze,
        candles=selected,
    )


def build_absorption_freeze(
    flow_freeze: TemporalFlowEvidenceFreeze,
    structure_freeze: LiquidityStructureEvidenceFreeze,
    *,
    as_of_ms: int,
    config: AbsorptionConfig = DEFAULT_ABSORPTION_CONFIG,
) -> AbsorptionEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("absorption as_of_ms must be nonnegative")
    flow = flow_freeze.analysis
    structure = structure_freeze.analysis
    _require_market_context(
        flow.exchange,
        flow.market_type,
        flow.symbol,
        structure.exchange,
        structure.market_type,
        structure.symbol,
        "absorption structure",
    )
    if flow.as_of_ms != as_of_ms or structure.as_of_ms != as_of_ms:
        raise ValueError("absorption requires exact flow/structure/as_of alignment")

    flags: list[str] = [
        "candidate_not_proof_of_iceberg_or_actor_intent",
        "public_trade_flow_and_visible_book_replenishment_only",
    ]
    status = PatternStatus.MEASURED
    candidates: tuple[AbsorptionCandidate, ...] = ()
    overlap_start = max(flow.window_start_ms, structure.source_window_start_ms)
    flow_end = flow.window_end_ms
    structure_end = structure.source_window_end_ms
    overlap_end = (
        None
        if flow_end is None or structure_end is None
        else min(flow_end, structure_end)
    )

    if flow.status is not TemporalFlowStatus.MEASURED or flow.metrics is None:
        status = PatternStatus.UNRESOLVED
        flags.append("temporal_flow_unresolved")
    elif structure.status is not LiquidityStructureStatus.MEASURED:
        status = PatternStatus.UNRESOLVED
        flags.append("liquidity_structure_unresolved")
    elif overlap_end is None or overlap_end < overlap_start:
        status = PatternStatus.UNRESOLVED
        flags.append("no_temporal_overlap_between_flow_and_book")
    else:
        eligible_trades = tuple(
            trade
            for trade in flow_freeze.trades
            if trade.book_eligible and overlap_start <= trade.event_at_ms <= overlap_end
        )
        found: list[AbsorptionCandidate] = []
        for level in structure.bid_levels:
            candidate = _absorption_candidate(
                level,
                eligible_trades,
                side=AbsorptionSide.BID,
                config=config,
            )
            if candidate is not None:
                found.append(candidate)
        for level in structure.ask_levels:
            candidate = _absorption_candidate(
                level,
                eligible_trades,
                side=AbsorptionSide.ASK,
                config=config,
            )
            if candidate is not None:
                found.append(candidate)
        candidates = tuple(
            sorted(found, key=lambda item: (item.last_interaction_ms, item.side.value))
        )
        if not candidates:
            flags.append("no_qualified_absorption_candidate")

    observed_at_ms = max(flow.observed_at_ms, structure.observed_at_ms)
    payload: dict[str, object] = {
        "as_of_ms": as_of_ms,
        "candidates": [_absorption_candidate_payload(item) for item in candidates],
        "config_identity": config.identity,
        "engine_version": ABSORPTION_ENGINE_VERSION,
        "exchange": flow.exchange,
        "flow_evidence_identity": flow.evidence_identity,
        "flow_freeze_identity": flow_freeze.freeze_identity,
        "market_type": flow.market_type,
        "observed_at_ms": observed_at_ms,
        "overlap_end_ms": overlap_end,
        "overlap_start_ms": overlap_start if overlap_end is not None else None,
        "status": status,
        "structure_evidence_identity": structure.evidence_identity,
        "structure_freeze_identity": structure_freeze.freeze_identity,
        "symbol": flow.symbol,
        "uncertainty_flags": tuple(flags),
    }
    analysis = AbsorptionAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=ABSORPTION_ENGINE_VERSION,
        config_identity=config.identity,
        exchange=flow.exchange,
        market_type=flow.market_type,
        symbol=flow.symbol,
        as_of_ms=as_of_ms,
        observed_at_ms=observed_at_ms,
        flow_evidence_identity=flow.evidence_identity,
        flow_freeze_identity=flow_freeze.freeze_identity,
        structure_evidence_identity=structure.evidence_identity,
        structure_freeze_identity=structure_freeze.freeze_identity,
        overlap_start_ms=overlap_start if overlap_end is not None else None,
        overlap_end_ms=overlap_end,
        status=status,
        candidates=candidates,
        uncertainty_flags=tuple(flags),
    )
    return AbsorptionEvidenceFreeze(
        freeze_identity=canonical_sha256(
            {
                "analysis_identity": analysis.evidence_identity,
                "flow_freeze_identity": flow_freeze.freeze_identity,
                "schema_version": ABSORPTION_FREEZE_SCHEMA_VERSION,
                "structure_freeze_identity": structure_freeze.freeze_identity,
            }
        ),
        schema_version=ABSORPTION_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        flow_freeze=flow_freeze,
        structure_freeze=structure_freeze,
    )


def _divergence_candidate(
    first: Candle,
    second: Candle,
    flow_freeze: TemporalFlowEvidenceFreeze,
    *,
    side: DivergenceSide,
    config: DivergenceConfig,
) -> DivergenceCandidate | None:
    first_coverage = _endpoint_flow(flow_freeze, first)
    second_coverage = _endpoint_flow(flow_freeze, second)
    if first_coverage is None or second_coverage is None:
        return None
    first_cvd, first_count, first_gap = first_coverage
    second_cvd, second_count, second_gap = second_coverage
    if (
        first_count < config.minimum_endpoint_trade_count
        or second_count < config.minimum_endpoint_trade_count
        or first_gap > config.max_endpoint_trade_gap_ms
        or second_gap > config.max_endpoint_trade_gap_ms
    ):
        return None

    if side is DivergenceSide.BULLISH:
        first_price = first.low
        second_price = second.low
        if second_price >= first_price:
            return None
        price_change = (first_price - second_price) / first_price * _BPS
        cvd_change = second_cvd - first_cvd
        if (
            price_change < config.minimum_price_change_bps
            or cvd_change <= config.minimum_cvd_change_notional
        ):
            return None
    else:
        first_price = first.high
        second_price = second.high
        if second_price <= first_price:
            return None
        price_change = (second_price - first_price) / first_price * _BPS
        cvd_change = second_cvd - first_cvd
        if (
            price_change < config.minimum_price_change_bps
            or cvd_change >= -config.minimum_cvd_change_notional
        ):
            return None

    return DivergenceCandidate(
        side=side,
        first_candle_identity=_candle_identity(first),
        second_candle_identity=_candle_identity(second),
        first_open_time_ms=first.open_time_ms,
        second_open_time_ms=second.open_time_ms,
        first_endpoint_ms=first.close_time_ms,
        second_endpoint_ms=second.close_time_ms,
        first_price=first_price,
        second_price=second_price,
        price_change_bps=price_change,
        first_cvd_notional=first_cvd,
        second_cvd_notional=second_cvd,
        cvd_change_notional=cvd_change,
        first_endpoint_trade_count=first_count,
        second_endpoint_trade_count=second_count,
        uncertainty_flags=(
            "window_local_cvd_not_exchange_global",
            "divergence_candidate_not_directional_prediction",
        ),
    )


def _endpoint_flow(
    flow_freeze: TemporalFlowEvidenceFreeze,
    candle: Candle,
) -> tuple[Decimal, int, int] | None:
    eligible = tuple(
        trade
        for trade in flow_freeze.trades
        if trade.book_eligible and trade.event_at_ms <= candle.close_time_ms
    )
    in_candle = tuple(
        trade
        for trade in eligible
        if candle.open_time_ms <= trade.event_at_ms <= candle.close_time_ms
    )
    if not eligible or not in_candle:
        return None
    cvd = sum(
        (
            trade.notional
            if trade.aggressor_side is AggressorSide.BUY
            else -trade.notional
            for trade in eligible
        ),
        _ZERO,
    )
    gap = candle.close_time_ms - eligible[-1].event_at_ms
    if gap < 0:
        raise ValueError("divergence endpoint trade postdates candle")
    return cvd, len(in_candle), gap


def _pivot_indices(
    candles: tuple[Candle, ...],
    *,
    radius: int,
    use_low: bool,
) -> tuple[int, ...]:
    indices: list[int] = []
    for index in range(radius, len(candles) - radius):
        center = candles[index].low if use_low else candles[index].high
        neighbours = tuple(
            (candles[pos].low if use_low else candles[pos].high)
            for pos in range(index - radius, index + radius + 1)
            if pos != index
        )
        if use_low and all(center < value for value in neighbours):
            indices.append(index)
        if not use_low and all(center > value for value in neighbours):
            indices.append(index)
    return tuple(indices)


def _absorption_candidate(
    level: LiquidityLevelEvidence,
    trades: tuple[PublicTradeObservation, ...],
    *,
    side: AbsorptionSide,
    config: AbsorptionConfig,
) -> AbsorptionCandidate | None:
    if (
        level.presence_fraction < config.minimum_level_presence_fraction
        or level.replenishment_cycles < config.minimum_replenishment_cycles
        or level.replenishment_notional <= _ZERO
    ):
        return None

    tolerance = config.interaction_tolerance_bps / _BPS
    lower = level.price * (_ONE - tolerance)
    upper = level.price * (_ONE + tolerance)
    interaction = tuple(
        trade
        for trade in trades
        if level.first_seen_ms <= trade.event_at_ms <= level.last_seen_ms
        and lower <= trade.price <= upper
    )
    if not interaction:
        return None

    aggressive_side = (
        AggressorSide.SELL if side is AbsorptionSide.BID else AggressorSide.BUY
    )
    aggressive = tuple(
        trade for trade in interaction if trade.aggressor_side is aggressive_side
    )
    opposing = tuple(
        trade for trade in interaction if trade.aggressor_side is not aggressive_side
    )
    if len(aggressive) < config.minimum_aggressive_trade_count:
        return None

    aggressive_notional = sum((item.notional for item in aggressive), _ZERO)
    opposing_notional = sum((item.notional for item in opposing), _ZERO)
    total = aggressive_notional + opposing_notional
    if total <= _ZERO:
        return None
    aggressor_share = aggressive_notional / total
    if aggressor_share < config.minimum_aggressor_share:
        return None

    replenishment_fraction = level.replenishment_notional / aggressive_notional
    if replenishment_fraction < config.minimum_replenishment_fraction:
        return None

    if side is AbsorptionSide.BID:
        extreme = min(item.price for item in interaction)
        response_bps = max(_ZERO, (level.price - extreme) / level.price * _BPS)
    else:
        extreme = max(item.price for item in interaction)
        response_bps = max(_ZERO, (extreme - level.price) / level.price * _BPS)
    if response_bps > config.max_price_nonresponse_bps:
        return None

    return AbsorptionCandidate(
        side=side,
        level_price=level.price,
        level_presence_fraction=level.presence_fraction,
        level_materiality_multiple=level.materiality_multiple,
        aggressive_trade_count=len(aggressive),
        opposing_trade_count=len(opposing),
        aggressive_notional=aggressive_notional,
        opposing_notional=opposing_notional,
        aggressor_share=aggressor_share,
        replenishment_notional=level.replenishment_notional,
        replenishment_cycles=level.replenishment_cycles,
        replenishment_fraction_of_aggressive_flow=replenishment_fraction,
        max_price_response_bps=response_bps,
        first_interaction_ms=interaction[0].event_at_ms,
        last_interaction_ms=interaction[-1].event_at_ms,
        uncertainty_flags=(
            "candidate_not_proof_of_iceberg_execution",
            "candidate_not_actor_intent_or_manipulation",
        ),
    )


def _candle_context(
    candles: tuple[Candle, ...],
) -> tuple[Exchange, MarketType, str, str]:
    first = candles[0]
    expected = (first.exchange, first.market_type, first.symbol, first.timeframe)
    if any(
        (item.exchange, item.market_type, item.symbol, item.timeframe) != expected
        for item in candles[1:]
    ):
        raise ValueError("mixed divergence candle context")
    return expected


def _require_candle_context(candle: Candle, analysis: DivergenceAnalysis) -> None:
    if (
        candle.exchange is not analysis.exchange
        or candle.market_type is not analysis.market_type
        or candle.symbol != analysis.symbol
        or candle.timeframe != analysis.timeframe
    ):
        raise ValueError("divergence freeze candle context mismatch")


def _require_market_context(
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


def _reject_duplicate_candles(candles: tuple[Candle, ...]) -> None:
    identities = [_candle_identity(item) for item in candles]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate divergence candle identity")


def _candle_identity(candle: Candle) -> str:
    return canonical_sha256(_candle_payload(candle))


def _candle_payload(candle: Candle) -> dict[str, object]:
    return {
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


def _divergence_candidate_payload(
    item: DivergenceCandidate,
) -> dict[str, object]:
    return {
        field: getattr(item, field)
        for field in item.__dataclass_fields__
    }


def _absorption_candidate_payload(
    item: AbsorptionCandidate,
) -> dict[str, object]:
    return {
        field: getattr(item, field)
        for field in item.__dataclass_fields__
    }


def _divergence_analysis_payload(analysis: DivergenceAnalysis) -> dict[str, object]:
    return {
        field: (
            [_divergence_candidate_payload(item) for item in analysis.candidates]
            if field == "candidates"
            else getattr(analysis, field)
        )
        for field in analysis.__dataclass_fields__
        if field != "evidence_identity"
    }


def _absorption_analysis_payload(analysis: AbsorptionAnalysis) -> dict[str, object]:
    return {
        field: (
            [_absorption_candidate_payload(item) for item in analysis.candidates]
            if field == "candidates"
            else getattr(analysis, field)
        )
        for field in analysis.__dataclass_fields__
        if field != "evidence_identity"
    }


def _validate_identity_bounds(
    count: int,
    first_identity: str | None,
    last_identity: str | None,
    label: str,
) -> None:
    if count == 0:
        if first_identity is not None or last_identity is not None:
            raise ValueError(f"empty {label} set cannot carry identities")
        return
    if first_identity is None or last_identity is None:
        raise ValueError(f"nonempty {label} set requires identities")
    _sha(first_identity, f"first {label}")
    _sha(last_identity, f"last {label}")


def _finite(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be SHA256")
