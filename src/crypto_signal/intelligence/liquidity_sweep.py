from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookSnapshot,
    PublicTradeObservation,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.intelligence.liquidity_dynamics import LiquiditySourceQuality
from crypto_signal.intelligence.liquidity_structure import (
    DEFAULT_LIQUIDITY_STRUCTURE_CONFIG,
    LiquidityLevelCandidate,
    LiquidityLevelEvidence,
    LiquiditySide,
    LiquidityStructureConfig,
    LiquidityStructureStatus,
    build_liquidity_structure_evidence_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256

LIQUIDITY_SWEEP_ENGINE_VERSION = "liquidity-sweep-v2-slice3/1"
LIQUIDITY_SWEEP_FREEZE_SCHEMA_VERSION = "liquidity-sweep-freeze-v1/1"
_BPS = Decimal(10000)


class LiquiditySweepStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class LiquiditySweepState(StrEnum):
    NONE = "none"
    BID_SIDE_CANDIDATE = "bid_side_liquidity_sweep_candidate"
    ASK_SIDE_CANDIDATE = "ask_side_liquidity_sweep_candidate"
    BOTH_SIDES_CANDIDATE = "both_sides_liquidity_sweep_candidate"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class LiquiditySweepConfig:
    lookback_ms: int = 120_000
    minimum_orderbook_snapshots: int = 5
    minimum_public_trades: int = 3
    max_snapshot_age_ms: int = 30_000
    max_trade_age_ms: int = 30_000
    max_snapshot_gap_ms: int = 30_000
    pool_touch_tolerance_bps: Decimal = Decimal(5)
    max_pool_interaction_distance_bps: Decimal = Decimal(100)
    minimum_depth_depletion_fraction: Decimal = Decimal("0.20")
    minimum_aggressor_share: Decimal = Decimal("0.60")
    minimum_displacement_bps: Decimal = Decimal(5)
    minimum_follow_through_trades: int = 1
    recovery_tolerance_bps: Decimal = Decimal(3)
    structure_config: LiquidityStructureConfig = DEFAULT_LIQUIDITY_STRUCTURE_CONFIG

    def __post_init__(self) -> None:
        for label, value in (
            ("lookback_ms", self.lookback_ms),
            ("minimum_orderbook_snapshots", self.minimum_orderbook_snapshots),
            ("minimum_public_trades", self.minimum_public_trades),
            ("max_snapshot_age_ms", self.max_snapshot_age_ms),
            ("max_trade_age_ms", self.max_trade_age_ms),
            ("max_snapshot_gap_ms", self.max_snapshot_gap_ms),
            ("minimum_follow_through_trades", self.minimum_follow_through_trades),
        ):
            if value <= 0:
                raise ValueError(f"{label} must be positive")
        for label, value in (
            ("pool_touch_tolerance_bps", self.pool_touch_tolerance_bps),
            (
                "max_pool_interaction_distance_bps",
                self.max_pool_interaction_distance_bps,
            ),
            ("minimum_displacement_bps", self.minimum_displacement_bps),
            ("recovery_tolerance_bps", self.recovery_tolerance_bps),
        ):
            if value.is_nan() or value.is_infinite() or value <= Decimal(0):
                raise ValueError(f"{label} must be a positive finite Decimal")
        if (
            self.max_pool_interaction_distance_bps
            <= self.pool_touch_tolerance_bps
        ):
            raise ValueError(
                "max_pool_interaction_distance_bps must exceed touch tolerance"
            )
        for label, value in (
            (
                "minimum_depth_depletion_fraction",
                self.minimum_depth_depletion_fraction,
            ),
            ("minimum_aggressor_share", self.minimum_aggressor_share),
        ):
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
            if not Decimal(0) < value <= Decimal(1):
                raise ValueError(f"{label} must be inside (0,1]")


DEFAULT_LIQUIDITY_SWEEP_CONFIG = LiquiditySweepConfig()


@dataclass(frozen=True, slots=True)
class LiquiditySweepCandidate:
    side: LiquiditySide
    pool_price: Decimal
    pool_presence_fraction: Decimal
    pool_materiality_multiple: Decimal
    first_interaction_ms: int
    last_interaction_ms: int
    interaction_trade_count: int
    aggressive_trade_count: int
    opposing_trade_count: int
    aggressive_notional: Decimal
    opposing_notional: Decimal
    aggressor_share: Decimal
    depth_depletion_fraction: Decimal
    max_displacement_bps: Decimal
    follow_through_trade_count: int
    recovered: bool
    recovery_at_ms: int | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.side not in {LiquiditySide.BID, LiquiditySide.ASK}:
            raise ValueError("liquidity sweep candidate requires bid or ask side")
        for label, value in (
            ("pool_price", self.pool_price),
            ("pool_presence_fraction", self.pool_presence_fraction),
            ("pool_materiality_multiple", self.pool_materiality_multiple),
            ("aggressive_notional", self.aggressive_notional),
            ("opposing_notional", self.opposing_notional),
            ("aggressor_share", self.aggressor_share),
            ("depth_depletion_fraction", self.depth_depletion_fraction),
            ("max_displacement_bps", self.max_displacement_bps),
        ):
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
        if self.pool_price <= Decimal(0):
            raise ValueError("pool_price must be positive")
        if not Decimal(0) < self.pool_presence_fraction <= Decimal(1):
            raise ValueError("pool_presence_fraction must be inside (0,1]")
        if self.pool_materiality_multiple <= Decimal(0):
            raise ValueError("pool_materiality_multiple must be positive")
        if min(
            self.first_interaction_ms,
            self.last_interaction_ms,
            self.interaction_trade_count,
            self.aggressive_trade_count,
            self.opposing_trade_count,
            self.follow_through_trade_count,
        ) < 0:
            raise ValueError("liquidity sweep candidate counts/times cannot be negative")
        if self.last_interaction_ms < self.first_interaction_ms:
            raise ValueError("liquidity sweep interaction time ordering invalid")
        if self.interaction_trade_count <= 0 or self.aggressive_trade_count <= 0:
            raise ValueError("liquidity sweep candidate requires aggressive interaction")
        if self.aggressive_trade_count + self.opposing_trade_count != self.interaction_trade_count:
            raise ValueError("liquidity sweep trade-count decomposition mismatch")
        if self.aggressive_notional <= Decimal(0) or self.opposing_notional < Decimal(0):
            raise ValueError("liquidity sweep candidate notional invalid")
        if not Decimal(0) < self.aggressor_share <= Decimal(1):
            raise ValueError("aggressor_share must be inside (0,1]")
        if not Decimal(0) <= self.depth_depletion_fraction <= Decimal(1):
            raise ValueError("depth_depletion_fraction must be inside [0,1]")
        if self.max_displacement_bps < Decimal(0):
            raise ValueError("max_displacement_bps cannot be negative")
        if self.recovered != (self.recovery_at_ms is not None):
            raise ValueError("recovery flag/timestamp mismatch")
        if self.recovery_at_ms is not None and self.recovery_at_ms < self.first_interaction_ms:
            raise ValueError("recovery cannot predate interaction")
        if not self.uncertainty_flags:
            raise ValueError("liquidity sweep candidate requires uncertainty flags")


@dataclass(frozen=True, slots=True)
class LiquiditySweepAnalysis:
    evidence_identity: str
    engine_version: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    as_of_ms: int
    observed_at_ms: int
    source_window_start_ms: int
    source_window_end_ms: int | None
    first_snapshot_identity: str | None
    last_snapshot_identity: str | None
    first_trade_identity: str | None
    last_trade_identity: str | None
    consumed_snapshot_count: int
    consumed_trade_count: int
    latest_snapshot_age_ms: int | None
    latest_trade_age_ms: int | None
    source_quality: LiquiditySourceQuality
    status: LiquiditySweepStatus
    sweep_state: LiquiditySweepState
    structure_evidence_identity: str | None
    structure_freeze_identity: str | None
    evaluated_persistent_pool_count: int
    candidates: tuple[LiquiditySweepCandidate, ...]
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "liquidity sweep evidence identity")
        if self.engine_version != LIQUIDITY_SWEEP_ENGINE_VERSION:
            raise ValueError("unsupported liquidity sweep engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("liquidity sweep symbol must be uppercase")
        if min(self.as_of_ms, self.observed_at_ms, self.source_window_start_ms) < 0:
            raise ValueError("liquidity sweep timestamps cannot be negative")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("liquidity sweep cannot observe future evidence")
        if self.source_window_start_ms > self.as_of_ms:
            raise ValueError("liquidity sweep window starts after as-of")
        if (
            self.source_window_end_ms is not None
            and not self.source_window_start_ms
            <= self.source_window_end_ms
            <= self.as_of_ms
        ):
            raise ValueError("liquidity sweep window end outside PIT bounds")
        if min(
            self.consumed_snapshot_count,
            self.consumed_trade_count,
            self.evaluated_persistent_pool_count,
        ) < 0:
            raise ValueError("liquidity sweep counts cannot be negative")
        for value in (self.latest_snapshot_age_ms, self.latest_trade_age_ms):
            if value is not None and value < 0:
                raise ValueError("liquidity sweep latest age cannot be negative")
        _validate_boundary_identity_pair(
            self.consumed_snapshot_count,
            self.first_snapshot_identity,
            self.last_snapshot_identity,
            "snapshot",
        )
        _validate_boundary_identity_pair(
            self.consumed_trade_count,
            self.first_trade_identity,
            self.last_trade_identity,
            "trade",
        )
        if self.status is LiquiditySweepStatus.MEASURED:
            if self.source_quality is not LiquiditySourceQuality.GOOD:
                raise ValueError("measured liquidity sweep requires good source quality")
            if self.sweep_state is LiquiditySweepState.UNAVAILABLE:
                raise ValueError("measured liquidity sweep cannot be unavailable")
            if self.structure_evidence_identity is None or self.structure_freeze_identity is None:
                raise ValueError("measured liquidity sweep requires structure identities")
            _require_sha256(self.structure_evidence_identity, "structure evidence identity")
            _require_sha256(self.structure_freeze_identity, "structure freeze identity")
            if self.sweep_state is LiquiditySweepState.NONE and self.candidates:
                raise ValueError("NONE sweep state cannot carry candidates")
            if self.sweep_state is not LiquiditySweepState.NONE and not self.candidates:
                raise ValueError("candidate sweep state requires candidates")
        else:
            if self.source_quality is LiquiditySourceQuality.GOOD:
                raise ValueError("unresolved liquidity sweep cannot claim good quality")
            if self.sweep_state is not LiquiditySweepState.UNAVAILABLE:
                raise ValueError("unresolved liquidity sweep must be unavailable")
            if self.candidates:
                raise ValueError("unresolved liquidity sweep cannot carry candidates")
            if not self.uncertainty_flags:
                raise ValueError("unresolved liquidity sweep requires uncertainty")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("liquidity sweep evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class LiquiditySweepEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: LiquiditySweepAnalysis
    snapshots: tuple[OrderBookSnapshot, ...]
    trades: tuple[PublicTradeObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "liquidity sweep freeze identity")
        if self.schema_version != LIQUIDITY_SWEEP_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported liquidity sweep freeze schema")
        if self.analysis.consumed_snapshot_count != len(self.snapshots):
            raise ValueError("liquidity sweep snapshot count mismatch")
        if self.analysis.consumed_trade_count != len(self.trades):
            raise ValueError("liquidity sweep trade count mismatch")
        for snapshot in self.snapshots:
            _require_context(
                self.analysis.exchange,
                self.analysis.market_type,
                self.analysis.symbol,
                snapshot.exchange,
                snapshot.market_type,
                snapshot.symbol,
            )
            if max(
                snapshot.event_at_ms,
                snapshot.source_timestamp_ms,
                snapshot.response_time_ms,
                snapshot.ingested_at_ms,
            ) > self.analysis.as_of_ms:
                raise ValueError("liquidity sweep freeze contains future snapshot")
        for trade in self.trades:
            _require_context(
                self.analysis.exchange,
                self.analysis.market_type,
                self.analysis.symbol,
                trade.exchange,
                trade.market_type,
                trade.symbol,
            )
            if max(
                trade.event_at_ms,
                trade.source_timestamp_ms,
                trade.ingested_at_ms,
            ) > self.analysis.as_of_ms:
                raise ValueError("liquidity sweep freeze contains future trade")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "schema_version": LIQUIDITY_SWEEP_FREEZE_SCHEMA_VERSION,
                "snapshot_identities": [
                    item.snapshot_identity for item in self.snapshots
                ],
                "trade_identities": [item.trade_identity for item in self.trades],
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("liquidity sweep freeze identity mismatch")


def analyze_liquidity_sweeps(
    orderbooks: Sequence[OrderBookSnapshot],
    trades: Sequence[PublicTradeObservation],
    *,
    as_of_ms: int,
    config: LiquiditySweepConfig = DEFAULT_LIQUIDITY_SWEEP_CONFIG,
) -> LiquiditySweepAnalysis:
    return build_liquidity_sweep_evidence_freeze(
        orderbooks,
        trades,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_liquidity_sweep_evidence_freeze(
    orderbooks: Sequence[OrderBookSnapshot],
    trades: Sequence[PublicTradeObservation],
    *,
    as_of_ms: int,
    config: LiquiditySweepConfig = DEFAULT_LIQUIDITY_SWEEP_CONFIG,
) -> LiquiditySweepEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("liquidity sweep as_of_ms must be non-negative")
    if not orderbooks:
        raise ValueError("liquidity sweep requires at least one orderbook snapshot")

    books = tuple(
        sorted(
            orderbooks,
            key=lambda item: (
                item.event_at_ms,
                item.sequence,
                item.update_id,
                item.snapshot_identity,
            ),
        )
    )
    trades_sorted = tuple(
        sorted(
            trades,
            key=lambda item: (
                item.event_at_ms,
                item.sequence,
                item.exec_id,
                item.trade_identity,
            ),
        )
    )
    _reject_duplicate_snapshot_identities(books)
    _reject_duplicate_trade_identities(trades_sorted)

    exchange, market_type, symbol = _book_context(books)
    for trade in trades_sorted:
        _require_context(
            exchange,
            market_type,
            symbol,
            trade.exchange,
            trade.market_type,
            trade.symbol,
        )

    safe_books = tuple(
        item
        for item in books
        if max(
            item.event_at_ms,
            item.source_timestamp_ms,
            item.response_time_ms,
            item.ingested_at_ms,
        )
        <= as_of_ms
    )
    safe_trades = tuple(
        item
        for item in trades_sorted
        if max(
            item.event_at_ms,
            item.source_timestamp_ms,
            item.ingested_at_ms,
        )
        <= as_of_ms
        and item.book_eligible
    )
    window_start = max(0, as_of_ms - config.lookback_ms)
    selected_books = tuple(
        item for item in safe_books if item.event_at_ms >= window_start
    )
    selected_trades = tuple(
        item for item in safe_trades if item.event_at_ms >= window_start
    )

    analysis = _analyze_selected(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        snapshots=selected_books,
        trades=selected_trades,
        as_of_ms=as_of_ms,
        source_window_start_ms=window_start,
        config=config,
    )
    freeze_identity = canonical_sha256(
        {
            "analysis_identity": analysis.evidence_identity,
            "schema_version": LIQUIDITY_SWEEP_FREEZE_SCHEMA_VERSION,
            "snapshot_identities": [
                item.snapshot_identity for item in selected_books
            ],
            "trade_identities": [
                item.trade_identity for item in selected_trades
            ],
        }
    )
    return LiquiditySweepEvidenceFreeze(
        freeze_identity=freeze_identity,
        schema_version=LIQUIDITY_SWEEP_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        snapshots=selected_books,
        trades=selected_trades,
    )


def _analyze_selected(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    snapshots: tuple[OrderBookSnapshot, ...],
    trades: tuple[PublicTradeObservation, ...],
    as_of_ms: int,
    source_window_start_ms: int,
    config: LiquiditySweepConfig,
) -> LiquiditySweepAnalysis:
    flags: list[str] = []
    latest_snapshot = snapshots[-1] if snapshots else None
    latest_trade = trades[-1] if trades else None

    if not snapshots:
        flags.append("orderbook_unavailable_at_as_of")
    elif len(snapshots) < config.minimum_orderbook_snapshots:
        flags.append("insufficient_orderbook_snapshots")
    if not trades:
        flags.append("public_trade_unavailable_at_as_of")
    elif len(trades) < config.minimum_public_trades:
        flags.append("insufficient_public_trades")
    if latest_snapshot is not None:
        if as_of_ms - latest_snapshot.event_at_ms > config.max_snapshot_age_ms:
            flags.append("stale_latest_orderbook")
    if latest_trade is not None:
        if as_of_ms - latest_trade.event_at_ms > config.max_trade_age_ms:
            flags.append("stale_latest_public_trade")
    if any(
        right.event_at_ms - left.event_at_ms > config.max_snapshot_gap_ms
        for left, right in pairwise(snapshots)
    ):
        flags.append("snapshot_gap_exceeds_limit")

    if flags:
        return _unresolved(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            snapshots=snapshots,
            trades=trades,
            as_of_ms=as_of_ms,
            source_window_start_ms=source_window_start_ms,
            flags=tuple(flags),
        )

    structure_freeze = build_liquidity_structure_evidence_freeze(
        snapshots,
        as_of_ms=as_of_ms,
        config=config.structure_config,
    )
    structure = structure_freeze.analysis
    if structure.status is not LiquidityStructureStatus.MEASURED:
        return _unresolved(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            snapshots=snapshots,
            trades=trades,
            as_of_ms=as_of_ms,
            source_window_start_ms=source_window_start_ms,
            flags=(
                "liquidity_structure_unresolved",
                *structure.uncertainty_flags,
            ),
        )

    persistent_levels = tuple(
        level
        for level in (*structure.bid_levels, *structure.ask_levels)
        if LiquidityLevelCandidate.PERSISTENT_POOL in level.candidates
    )
    candidates = tuple(
        candidate
        for level in persistent_levels
        if (
            candidate := _evaluate_pool(
                level=level,
                trades=trades,
                config=config,
            )
        )
        is not None
    )
    sweep_state = _sweep_state(candidates)
    uncertainty: list[str] = []
    if not persistent_levels:
        uncertainty.append("no_persistent_liquidity_pool_in_window")
    elif not candidates:
        uncertainty.append("no_qualified_liquidity_sweep_candidate")
    else:
        uncertainty.extend(
            (
                "liquidity_sweep_candidate_not_stop_hunt_proof",
                "public_trade_tape_does_not_identify_actor_intent",
            )
        )

    observed_at_ms = max(
        max(item.ingested_at_ms for item in snapshots),
        max(item.ingested_at_ms for item in trades),
    )
    source_window_end_ms = max(
        snapshots[-1].event_at_ms,
        trades[-1].event_at_ms,
    )
    payload: dict[str, object] = {
        "as_of_ms": as_of_ms,
        "candidates": [_candidate_payload(item) for item in candidates],
        "consumed_snapshot_count": len(snapshots),
        "consumed_trade_count": len(trades),
        "engine_version": LIQUIDITY_SWEEP_ENGINE_VERSION,
        "evaluated_persistent_pool_count": len(persistent_levels),
        "exchange": exchange,
        "first_snapshot_identity": snapshots[0].snapshot_identity,
        "first_trade_identity": trades[0].trade_identity,
        "last_snapshot_identity": snapshots[-1].snapshot_identity,
        "last_trade_identity": trades[-1].trade_identity,
        "latest_snapshot_age_ms": as_of_ms - snapshots[-1].event_at_ms,
        "latest_trade_age_ms": as_of_ms - trades[-1].event_at_ms,
        "market_type": market_type,
        "observed_at_ms": observed_at_ms,
        "source_quality": LiquiditySourceQuality.GOOD,
        "source_window_end_ms": source_window_end_ms,
        "source_window_start_ms": source_window_start_ms,
        "status": LiquiditySweepStatus.MEASURED,
        "structure_evidence_identity": structure.evidence_identity,
        "structure_freeze_identity": structure_freeze.freeze_identity,
        "sweep_state": sweep_state,
        "symbol": symbol,
        "uncertainty_flags": tuple(uncertainty),
    }
    return LiquiditySweepAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=LIQUIDITY_SWEEP_ENGINE_VERSION,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        as_of_ms=as_of_ms,
        observed_at_ms=observed_at_ms,
        source_window_start_ms=source_window_start_ms,
        source_window_end_ms=source_window_end_ms,
        first_snapshot_identity=snapshots[0].snapshot_identity,
        last_snapshot_identity=snapshots[-1].snapshot_identity,
        first_trade_identity=trades[0].trade_identity,
        last_trade_identity=trades[-1].trade_identity,
        consumed_snapshot_count=len(snapshots),
        consumed_trade_count=len(trades),
        latest_snapshot_age_ms=as_of_ms - snapshots[-1].event_at_ms,
        latest_trade_age_ms=as_of_ms - trades[-1].event_at_ms,
        source_quality=LiquiditySourceQuality.GOOD,
        status=LiquiditySweepStatus.MEASURED,
        sweep_state=sweep_state,
        structure_evidence_identity=structure.evidence_identity,
        structure_freeze_identity=structure_freeze.freeze_identity,
        evaluated_persistent_pool_count=len(persistent_levels),
        candidates=candidates,
        uncertainty_flags=tuple(uncertainty),
    )


def _evaluate_pool(
    *,
    level: LiquidityLevelEvidence,
    trades: tuple[PublicTradeObservation, ...],
    config: LiquiditySweepConfig,
) -> LiquiditySweepCandidate | None:
    pool = level.price
    touch = config.pool_touch_tolerance_bps / _BPS
    band = config.max_pool_interaction_distance_bps / _BPS
    if level.side is LiquiditySide.BID:
        lower = pool * (Decimal(1) - band)
        upper = pool * (Decimal(1) + touch)
        interaction = tuple(
            item for item in trades if lower <= item.price <= upper
        )
        aggressive_side = AggressorSide.SELL
    else:
        lower = pool * (Decimal(1) - touch)
        upper = pool * (Decimal(1) + band)
        interaction = tuple(
            item for item in trades if lower <= item.price <= upper
        )
        aggressive_side = AggressorSide.BUY

    if not interaction:
        return None

    aggressive = tuple(
        item for item in interaction if item.aggressor_side is aggressive_side
    )
    opposing = tuple(
        item for item in interaction if item.aggressor_side is not aggressive_side
    )
    if not aggressive:
        return None

    aggressive_notional = sum(
        (item.notional for item in aggressive),
        start=Decimal(0),
    )
    opposing_notional = sum(
        (item.notional for item in opposing),
        start=Decimal(0),
    )
    total_notional = aggressive_notional + opposing_notional
    aggressor_share = (
        aggressive_notional / total_notional
        if total_notional > Decimal(0)
        else Decimal(0)
    )
    depletion_fraction = min(
        Decimal(1),
        level.gross_removed_notional / level.max_notional,
    )
    if level.side is LiquiditySide.BID:
        extreme_price = min(item.price for item in interaction)
        displacement_bps = max(
            Decimal(0),
            (pool - extreme_price) / pool * _BPS,
        )
        extreme_index = next(
            index
            for index, item in enumerate(interaction)
            if item.price == extreme_price
        )
        displacement_threshold = pool * (
            Decimal(1) - config.minimum_displacement_bps / _BPS
        )
        displacement_index = next(
            (
                index
                for index, item in enumerate(interaction)
                if item.aggressor_side is AggressorSide.SELL
                and item.price <= displacement_threshold
            ),
            None,
        )
        follow_through = (
            0
            if displacement_index is None
            else sum(
                1
                for item in interaction[displacement_index + 1 :]
                if item.aggressor_side is AggressorSide.SELL
                and item.price < pool
            )
        )
        recovery_threshold = pool * (
            Decimal(1) - config.recovery_tolerance_bps / _BPS
        )
        recovery_trade = next(
            (
                item
                for item in interaction[extreme_index + 1 :]
                if item.price >= recovery_threshold
            ),
            None,
        )
    else:
        extreme_price = max(item.price for item in interaction)
        displacement_bps = max(
            Decimal(0),
            (extreme_price - pool) / pool * _BPS,
        )
        extreme_index = next(
            index
            for index, item in enumerate(interaction)
            if item.price == extreme_price
        )
        displacement_threshold = pool * (
            Decimal(1) + config.minimum_displacement_bps / _BPS
        )
        displacement_index = next(
            (
                index
                for index, item in enumerate(interaction)
                if item.aggressor_side is AggressorSide.BUY
                and item.price >= displacement_threshold
            ),
            None,
        )
        follow_through = (
            0
            if displacement_index is None
            else sum(
                1
                for item in interaction[displacement_index + 1 :]
                if item.aggressor_side is AggressorSide.BUY
                and item.price > pool
            )
        )
        recovery_threshold = pool * (
            Decimal(1) + config.recovery_tolerance_bps / _BPS
        )
        recovery_trade = next(
            (
                item
                for item in interaction[extreme_index + 1 :]
                if item.price <= recovery_threshold
            ),
            None,
        )

    qualifies = (
        depletion_fraction >= config.minimum_depth_depletion_fraction
        and aggressor_share >= config.minimum_aggressor_share
        and displacement_bps >= config.minimum_displacement_bps
        and follow_through >= config.minimum_follow_through_trades
    )
    if not qualifies:
        return None

    return LiquiditySweepCandidate(
        side=level.side,
        pool_price=pool,
        pool_presence_fraction=level.presence_fraction,
        pool_materiality_multiple=level.materiality_multiple,
        first_interaction_ms=interaction[0].event_at_ms,
        last_interaction_ms=interaction[-1].event_at_ms,
        interaction_trade_count=len(interaction),
        aggressive_trade_count=len(aggressive),
        opposing_trade_count=len(opposing),
        aggressive_notional=aggressive_notional,
        opposing_notional=opposing_notional,
        aggressor_share=aggressor_share,
        depth_depletion_fraction=depletion_fraction,
        max_displacement_bps=displacement_bps,
        follow_through_trade_count=follow_through,
        recovered=recovery_trade is not None,
        recovery_at_ms=(
            None if recovery_trade is None else recovery_trade.event_at_ms
        ),
        uncertainty_flags=(
            "candidate_only_not_stop_hunt_proof",
            "public_trade_flow_does_not_identify_actor_intent",
        ),
    )


def _sweep_state(
    candidates: tuple[LiquiditySweepCandidate, ...],
) -> LiquiditySweepState:
    has_bid = any(item.side is LiquiditySide.BID for item in candidates)
    has_ask = any(item.side is LiquiditySide.ASK for item in candidates)
    if has_bid and has_ask:
        return LiquiditySweepState.BOTH_SIDES_CANDIDATE
    if has_bid:
        return LiquiditySweepState.BID_SIDE_CANDIDATE
    if has_ask:
        return LiquiditySweepState.ASK_SIDE_CANDIDATE
    return LiquiditySweepState.NONE


def _unresolved(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    snapshots: tuple[OrderBookSnapshot, ...],
    trades: tuple[PublicTradeObservation, ...],
    as_of_ms: int,
    source_window_start_ms: int,
    flags: tuple[str, ...],
) -> LiquiditySweepAnalysis:
    latest_snapshot = snapshots[-1] if snapshots else None
    latest_trade = trades[-1] if trades else None
    observed_at_ms = max(
        (
            *(item.ingested_at_ms for item in snapshots),
            *(item.ingested_at_ms for item in trades),
            0,
        )
    )
    end_candidates = (
        *(item.event_at_ms for item in snapshots),
        *(item.event_at_ms for item in trades),
    )
    source_window_end_ms = max(end_candidates) if end_candidates else None
    payload: dict[str, object] = {
        "as_of_ms": as_of_ms,
        "candidates": [],
        "consumed_snapshot_count": len(snapshots),
        "consumed_trade_count": len(trades),
        "engine_version": LIQUIDITY_SWEEP_ENGINE_VERSION,
        "evaluated_persistent_pool_count": 0,
        "exchange": exchange,
        "first_snapshot_identity": (
            None if not snapshots else snapshots[0].snapshot_identity
        ),
        "first_trade_identity": (
            None if not trades else trades[0].trade_identity
        ),
        "last_snapshot_identity": (
            None if not snapshots else snapshots[-1].snapshot_identity
        ),
        "last_trade_identity": (
            None if not trades else trades[-1].trade_identity
        ),
        "latest_snapshot_age_ms": (
            None
            if latest_snapshot is None
            else as_of_ms - latest_snapshot.event_at_ms
        ),
        "latest_trade_age_ms": (
            None if latest_trade is None else as_of_ms - latest_trade.event_at_ms
        ),
        "market_type": market_type,
        "observed_at_ms": observed_at_ms,
        "source_quality": LiquiditySourceQuality.DEGRADED,
        "source_window_end_ms": source_window_end_ms,
        "source_window_start_ms": source_window_start_ms,
        "status": LiquiditySweepStatus.UNRESOLVED,
        "structure_evidence_identity": None,
        "structure_freeze_identity": None,
        "sweep_state": LiquiditySweepState.UNAVAILABLE,
        "symbol": symbol,
        "uncertainty_flags": flags,
    }
    return LiquiditySweepAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=LIQUIDITY_SWEEP_ENGINE_VERSION,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        as_of_ms=as_of_ms,
        observed_at_ms=observed_at_ms,
        source_window_start_ms=source_window_start_ms,
        source_window_end_ms=source_window_end_ms,
        first_snapshot_identity=None if not snapshots else snapshots[0].snapshot_identity,
        last_snapshot_identity=None if not snapshots else snapshots[-1].snapshot_identity,
        first_trade_identity=None if not trades else trades[0].trade_identity,
        last_trade_identity=None if not trades else trades[-1].trade_identity,
        consumed_snapshot_count=len(snapshots),
        consumed_trade_count=len(trades),
        latest_snapshot_age_ms=(
            None
            if latest_snapshot is None
            else as_of_ms - latest_snapshot.event_at_ms
        ),
        latest_trade_age_ms=(
            None if latest_trade is None else as_of_ms - latest_trade.event_at_ms
        ),
        source_quality=LiquiditySourceQuality.DEGRADED,
        status=LiquiditySweepStatus.UNRESOLVED,
        sweep_state=LiquiditySweepState.UNAVAILABLE,
        structure_evidence_identity=None,
        structure_freeze_identity=None,
        evaluated_persistent_pool_count=0,
        candidates=(),
        uncertainty_flags=flags,
    )


def _candidate_payload(candidate: LiquiditySweepCandidate) -> dict[str, object]:
    return {
        field: getattr(candidate, field)
        for field in candidate.__dataclass_fields__
    }


def _analysis_payload(analysis: LiquiditySweepAnalysis) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "candidates": [_candidate_payload(item) for item in analysis.candidates],
        "consumed_snapshot_count": analysis.consumed_snapshot_count,
        "consumed_trade_count": analysis.consumed_trade_count,
        "engine_version": analysis.engine_version,
        "evaluated_persistent_pool_count": analysis.evaluated_persistent_pool_count,
        "exchange": analysis.exchange,
        "first_snapshot_identity": analysis.first_snapshot_identity,
        "first_trade_identity": analysis.first_trade_identity,
        "last_snapshot_identity": analysis.last_snapshot_identity,
        "last_trade_identity": analysis.last_trade_identity,
        "latest_snapshot_age_ms": analysis.latest_snapshot_age_ms,
        "latest_trade_age_ms": analysis.latest_trade_age_ms,
        "market_type": analysis.market_type,
        "observed_at_ms": analysis.observed_at_ms,
        "source_quality": analysis.source_quality,
        "source_window_end_ms": analysis.source_window_end_ms,
        "source_window_start_ms": analysis.source_window_start_ms,
        "status": analysis.status,
        "structure_evidence_identity": analysis.structure_evidence_identity,
        "structure_freeze_identity": analysis.structure_freeze_identity,
        "sweep_state": analysis.sweep_state,
        "symbol": analysis.symbol,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _validate_boundary_identity_pair(
    count: int,
    first_identity: str | None,
    last_identity: str | None,
    label: str,
) -> None:
    if count == 0:
        if first_identity is not None or last_identity is not None:
            raise ValueError(f"empty {label} window cannot carry identities")
        return
    if first_identity is None or last_identity is None:
        raise ValueError(f"non-empty {label} window requires identities")
    _require_sha256(first_identity, f"first {label} identity")
    _require_sha256(last_identity, f"last {label} identity")


def _book_context(
    snapshots: tuple[OrderBookSnapshot, ...],
) -> tuple[Exchange, MarketType, str]:
    first = snapshots[0]
    expected = (first.exchange, first.market_type, first.symbol)
    for item in snapshots[1:]:
        actual = (item.exchange, item.market_type, item.symbol)
        if actual != expected:
            raise ValueError("liquidity sweep orderbooks must share one market context")
    return expected


def _require_context(
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    actual_exchange: Exchange,
    actual_market_type: MarketType,
    actual_symbol: str,
) -> None:
    if (
        actual_exchange is not exchange
        or actual_market_type is not market_type
        or actual_symbol != symbol
    ):
        raise ValueError("liquidity sweep evidence must share one market context")


def _reject_duplicate_snapshot_identities(
    snapshots: tuple[OrderBookSnapshot, ...],
) -> None:
    identities = [item.snapshot_identity for item in snapshots]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate liquidity sweep snapshot identity")


def _reject_duplicate_trade_identities(
    trades: tuple[PublicTradeObservation, ...],
) -> None:
    identities = [item.trade_identity for item in trades]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate liquidity sweep trade identity")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be SHA256")
