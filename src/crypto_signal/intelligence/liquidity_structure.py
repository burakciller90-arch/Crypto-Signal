from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from crypto_signal.data.microstructure import OrderBookSnapshot
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.intelligence.liquidity_dynamics import LiquiditySourceQuality
from crypto_signal.ledger.serialization import canonical_sha256

LIQUIDITY_STRUCTURE_ENGINE_VERSION = "liquidity-structure-v1/1"
LIQUIDITY_STRUCTURE_FREEZE_SCHEMA_VERSION = "liquidity-structure-freeze-v1/1"
_ONE_SECOND_MS = Decimal(1000)


class LiquidityStructureStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class LiquidityLevelSide(StrEnum):
    BID = "bid"
    ASK = "ask"


class LiquidityStructureCandidateKind(StrEnum):
    LIQUIDITY_SWEEP = "liquidity_sweep_candidate"
    GHOST_ORDER = "ghost_order_candidate"
    HIDDEN_LIQUIDITY = "hidden_liquidity_candidate"
    SHALLOW_BOOK = "shallow_book_candidate"


@dataclass(frozen=True, slots=True)
class LiquidityStructureConfig:
    depth_levels: int = 10
    lookback_ms: int = 120_000
    minimum_snapshots: int = 5
    max_snapshot_age_ms: int = 30_000
    max_snapshot_gap_ms: int = 30_000
    persistent_min_presence_fraction: Decimal = Decimal("0.60")
    minimum_pool_snapshots: int = 3
    large_level_multiplier: Decimal = Decimal(3)
    ghost_min_snapshots: int = 2
    hidden_liquidity_min_replenishments: int = 2
    shallow_depth_fraction: Decimal = Decimal("0.35")

    def __post_init__(self) -> None:
        if self.depth_levels <= 0:
            raise ValueError("liquidity structure depth_levels must be positive")
        if self.lookback_ms <= 0:
            raise ValueError("liquidity structure lookback_ms must be positive")
        if self.minimum_snapshots < 2:
            raise ValueError("liquidity structure minimum_snapshots must be at least 2")
        if self.max_snapshot_age_ms <= 0:
            raise ValueError("liquidity structure max_snapshot_age_ms must be positive")
        if self.max_snapshot_gap_ms <= 0:
            raise ValueError("liquidity structure max_snapshot_gap_ms must be positive")
        _require_fraction(
            self.persistent_min_presence_fraction,
            "persistent_min_presence_fraction",
            include_one=True,
        )
        if self.minimum_pool_snapshots < 2:
            raise ValueError("minimum_pool_snapshots must be at least 2")
        _require_finite(self.large_level_multiplier, "large_level_multiplier")
        if self.large_level_multiplier <= Decimal(1):
            raise ValueError("large_level_multiplier must be greater than 1")
        if self.ghost_min_snapshots < 1:
            raise ValueError("ghost_min_snapshots must be positive")
        if self.hidden_liquidity_min_replenishments < 1:
            raise ValueError("hidden_liquidity_min_replenishments must be positive")
        _require_fraction(
            self.shallow_depth_fraction,
            "shallow_depth_fraction",
            include_one=False,
        )


DEFAULT_LIQUIDITY_STRUCTURE_CONFIG = LiquidityStructureConfig()


@dataclass(frozen=True, slots=True)
class PersistentLiquidityPool:
    pool_identity: str
    side: LiquidityLevelSide
    price: Decimal
    first_seen_ms: int
    last_seen_ms: int
    snapshots_present: int
    total_snapshots: int
    presence_fraction: Decimal
    mean_notional: Decimal
    max_notional: Decimal
    latest_notional: Decimal
    appearance_events: int
    disappearance_events: int
    replenishment_events: int

    def __post_init__(self) -> None:
        _require_sha256(self.pool_identity, "liquidity pool identity")
        _require_positive_finite(self.price, "liquidity pool price")
        if min(self.first_seen_ms, self.last_seen_ms) < 0:
            raise ValueError("liquidity pool timestamps must be non-negative")
        if self.last_seen_ms < self.first_seen_ms:
            raise ValueError("liquidity pool last_seen_ms precedes first_seen_ms")
        if self.snapshots_present <= 0 or self.total_snapshots <= 0:
            raise ValueError("liquidity pool snapshot counts must be positive")
        if self.snapshots_present > self.total_snapshots:
            raise ValueError("liquidity pool snapshots_present exceeds total")
        _require_fraction(
            self.presence_fraction,
            "liquidity pool presence_fraction",
            include_one=True,
        )
        for label, value in (
            ("mean_notional", self.mean_notional),
            ("max_notional", self.max_notional),
            ("latest_notional", self.latest_notional),
        ):
            _require_finite(value, label)
            if value < Decimal(0):
                raise ValueError(f"{label} must be non-negative")
        if self.mean_notional <= Decimal(0) or self.max_notional <= Decimal(0):
            raise ValueError("liquidity pool mean/max notional must be positive")
        if min(
            self.appearance_events,
            self.disappearance_events,
            self.replenishment_events,
        ) < 0:
            raise ValueError("liquidity pool event counts cannot be negative")
        if self.pool_identity != canonical_sha256(_pool_payload(self)):
            raise ValueError("liquidity pool identity mismatch")


@dataclass(frozen=True, slots=True)
class LiquidityStructureCandidate:
    candidate_identity: str
    kind: LiquidityStructureCandidateKind
    side: LiquidityLevelSide
    price: Decimal
    observed_start_ms: int
    observed_end_ms: int
    supporting_snapshot_count: int
    peak_notional: Decimal
    reason_codes: tuple[str, ...]
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.candidate_identity, "liquidity candidate identity")
        _require_positive_finite(self.price, "liquidity candidate price")
        if min(self.observed_start_ms, self.observed_end_ms) < 0:
            raise ValueError("liquidity candidate timestamps must be non-negative")
        if self.observed_end_ms < self.observed_start_ms:
            raise ValueError("liquidity candidate end precedes start")
        if self.supporting_snapshot_count <= 0:
            raise ValueError("liquidity candidate requires supporting snapshots")
        _require_positive_finite(self.peak_notional, "candidate peak_notional")
        if not self.reason_codes:
            raise ValueError("liquidity candidate requires reason codes")
        if not self.uncertainty_flags:
            raise ValueError("liquidity candidate requires uncertainty flags")
        if self.candidate_identity != canonical_sha256(_candidate_payload(self)):
            raise ValueError("liquidity candidate identity mismatch")


@dataclass(frozen=True, slots=True)
class LiquidityStructureMetrics:
    snapshot_count: int
    duration_ms: int
    bid_appearance_events: int
    bid_disappearance_events: int
    bid_replenishment_events: int
    ask_appearance_events: int
    ask_disappearance_events: int
    ask_replenishment_events: int
    bid_appearance_events_per_second: Decimal
    bid_disappearance_events_per_second: Decimal
    ask_appearance_events_per_second: Decimal
    ask_disappearance_events_per_second: Decimal
    latest_bid_depth_notional: Decimal
    median_bid_depth_notional: Decimal
    latest_ask_depth_notional: Decimal
    median_ask_depth_notional: Decimal

    def __post_init__(self) -> None:
        if self.snapshot_count < 2:
            raise ValueError("liquidity structure metrics require two snapshots")
        if self.duration_ms <= 0:
            raise ValueError("liquidity structure metrics require positive duration")
        if min(
            self.bid_appearance_events,
            self.bid_disappearance_events,
            self.bid_replenishment_events,
            self.ask_appearance_events,
            self.ask_disappearance_events,
            self.ask_replenishment_events,
        ) < 0:
            raise ValueError("liquidity structure event counts cannot be negative")
        for label, value in (
            (
                "bid_appearance_events_per_second",
                self.bid_appearance_events_per_second,
            ),
            (
                "bid_disappearance_events_per_second",
                self.bid_disappearance_events_per_second,
            ),
            (
                "ask_appearance_events_per_second",
                self.ask_appearance_events_per_second,
            ),
            (
                "ask_disappearance_events_per_second",
                self.ask_disappearance_events_per_second,
            ),
            ("latest_bid_depth_notional", self.latest_bid_depth_notional),
            ("median_bid_depth_notional", self.median_bid_depth_notional),
            ("latest_ask_depth_notional", self.latest_ask_depth_notional),
            ("median_ask_depth_notional", self.median_ask_depth_notional),
        ):
            _require_finite(value, label)
            if value < Decimal(0):
                raise ValueError(f"{label} must be non-negative")


@dataclass(frozen=True, slots=True)
class LiquidityStructureAnalysis:
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
    consumed_snapshot_count: int
    latest_snapshot_age_ms: int | None
    source_quality: LiquiditySourceQuality
    status: LiquidityStructureStatus
    metrics: LiquidityStructureMetrics | None
    persistent_pools: tuple[PersistentLiquidityPool, ...]
    candidates: tuple[LiquidityStructureCandidate, ...]
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "liquidity structure evidence identity")
        if self.engine_version != LIQUIDITY_STRUCTURE_ENGINE_VERSION:
            raise ValueError("unsupported liquidity structure engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("liquidity structure symbol must be uppercase")
        if min(self.as_of_ms, self.observed_at_ms, self.source_window_start_ms) < 0:
            raise ValueError("liquidity structure timestamps must be non-negative")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("liquidity structure cannot observe future evidence")
        if self.source_window_start_ms > self.as_of_ms:
            raise ValueError("liquidity structure window starts after as-of")
        if (
            self.source_window_end_ms is not None
            and not self.source_window_start_ms
            <= self.source_window_end_ms
            <= self.as_of_ms
        ):
            raise ValueError("liquidity structure window end outside PIT bounds")
        if self.consumed_snapshot_count < 0:
            raise ValueError("liquidity structure snapshot count cannot be negative")
        if self.latest_snapshot_age_ms is not None and self.latest_snapshot_age_ms < 0:
            raise ValueError("liquidity structure latest age cannot be negative")
        if self.consumed_snapshot_count == 0:
            if self.first_snapshot_identity is not None:
                raise ValueError("empty structure cannot carry first snapshot identity")
            if self.last_snapshot_identity is not None:
                raise ValueError("empty structure cannot carry last snapshot identity")
        else:
            if self.first_snapshot_identity is None:
                raise ValueError("non-empty structure requires first snapshot identity")
            if self.last_snapshot_identity is None:
                raise ValueError("non-empty structure requires last snapshot identity")
            _require_sha256(
                self.first_snapshot_identity,
                "first liquidity structure snapshot identity",
            )
            _require_sha256(
                self.last_snapshot_identity,
                "last liquidity structure snapshot identity",
            )
        if self.status is LiquidityStructureStatus.MEASURED:
            if self.metrics is None:
                raise ValueError("measured liquidity structure requires metrics")
            if self.source_quality is not LiquiditySourceQuality.GOOD:
                raise ValueError("measured liquidity structure requires good quality")
        else:
            if self.metrics is not None:
                raise ValueError("unresolved liquidity structure cannot carry metrics")
            if self.persistent_pools or self.candidates:
                raise ValueError("unresolved liquidity structure cannot claim evidence")
            if not self.uncertainty_flags:
                raise ValueError("unresolved liquidity structure requires uncertainty")
            if self.source_quality is LiquiditySourceQuality.GOOD:
                raise ValueError("unresolved liquidity structure cannot claim good quality")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("liquidity structure evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class LiquidityStructureEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: LiquidityStructureAnalysis
    snapshots: tuple[OrderBookSnapshot, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "liquidity structure freeze identity")
        if self.schema_version != LIQUIDITY_STRUCTURE_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported liquidity structure freeze schema")
        if self.analysis.consumed_snapshot_count != len(self.snapshots):
            raise ValueError("liquidity structure freeze snapshot count mismatch")
        for snapshot in self.snapshots:
            _require_same_context(
                self.analysis.exchange,
                self.analysis.market_type,
                self.analysis.symbol,
                snapshot,
            )
            if max(
                snapshot.event_at_ms,
                snapshot.source_timestamp_ms,
                snapshot.response_time_ms,
                snapshot.ingested_at_ms,
            ) > self.analysis.as_of_ms:
                raise ValueError("liquidity structure freeze contains future evidence")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "schema_version": LIQUIDITY_STRUCTURE_FREEZE_SCHEMA_VERSION,
                "snapshot_identities": [
                    snapshot.snapshot_identity for snapshot in self.snapshots
                ],
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("liquidity structure freeze identity mismatch")


def analyze_liquidity_structure(
    orderbooks: Sequence[OrderBookSnapshot],
    *,
    as_of_ms: int,
    config: LiquidityStructureConfig = DEFAULT_LIQUIDITY_STRUCTURE_CONFIG,
) -> LiquidityStructureAnalysis:
    return build_liquidity_structure_evidence_freeze(
        orderbooks,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_liquidity_structure_evidence_freeze(
    orderbooks: Sequence[OrderBookSnapshot],
    *,
    as_of_ms: int,
    config: LiquidityStructureConfig = DEFAULT_LIQUIDITY_STRUCTURE_CONFIG,
) -> LiquidityStructureEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("liquidity structure as_of_ms must be non-negative")
    if not orderbooks:
        raise ValueError("liquidity structure requires orderbook snapshots")

    books_sorted = tuple(
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
    _reject_duplicate_identities(books_sorted)
    exchange, market_type, symbol = _context(books_sorted)

    safe_books = tuple(
        item
        for item in books_sorted
        if max(
            item.event_at_ms,
            item.source_timestamp_ms,
            item.response_time_ms,
            item.ingested_at_ms,
        )
        <= as_of_ms
    )
    window_start = max(0, as_of_ms - config.lookback_ms)
    selected = tuple(item for item in safe_books if item.event_at_ms >= window_start)

    analysis = _analyze_selected(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        snapshots=selected,
        as_of_ms=as_of_ms,
        source_window_start_ms=window_start,
        config=config,
    )
    freeze_identity = canonical_sha256(
        {
            "analysis_identity": analysis.evidence_identity,
            "schema_version": LIQUIDITY_STRUCTURE_FREEZE_SCHEMA_VERSION,
            "snapshot_identities": [item.snapshot_identity for item in selected],
        }
    )
    return LiquidityStructureEvidenceFreeze(
        freeze_identity=freeze_identity,
        schema_version=LIQUIDITY_STRUCTURE_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        snapshots=selected,
    )


def _analyze_selected(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    snapshots: tuple[OrderBookSnapshot, ...],
    as_of_ms: int,
    source_window_start_ms: int,
    config: LiquidityStructureConfig,
) -> LiquidityStructureAnalysis:
    if not snapshots:
        return _unresolved(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            snapshots=snapshots,
            as_of_ms=as_of_ms,
            source_window_start_ms=source_window_start_ms,
            source_quality=LiquiditySourceQuality.UNAVAILABLE,
            flags=("orderbook_unavailable_at_as_of",),
        )

    flags: list[str] = []
    latest = snapshots[-1]
    latest_age = as_of_ms - latest.event_at_ms
    if latest_age > config.max_snapshot_age_ms:
        flags.append("stale_latest_orderbook")
    if len(snapshots) < config.minimum_snapshots:
        flags.append("insufficient_orderbook_snapshots")
    if any(
        len(item.bids) < config.depth_levels or len(item.asks) < config.depth_levels
        for item in snapshots
    ):
        flags.append("insufficient_orderbook_depth")
    if any(
        right.event_at_ms - left.event_at_ms > config.max_snapshot_gap_ms
        for left, right in pairwise(snapshots)
    ):
        flags.append("snapshot_gap_exceeds_limit")
    if snapshots[-1].event_at_ms <= snapshots[0].event_at_ms:
        flags.append("insufficient_temporal_span")

    if flags:
        return _unresolved(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            snapshots=snapshots,
            as_of_ms=as_of_ms,
            source_window_start_ms=source_window_start_ms,
            source_quality=LiquiditySourceQuality.DEGRADED,
            flags=tuple(flags),
        )

    bid_maps = tuple(_side_map(item, LiquidityLevelSide.BID, config) for item in snapshots)
    ask_maps = tuple(_side_map(item, LiquidityLevelSide.ASK, config) for item in snapshots)
    duration_ms = snapshots[-1].event_at_ms - snapshots[0].event_at_ms

    bid_events = _event_totals(bid_maps)
    ask_events = _event_totals(ask_maps)
    bid_depths = tuple(sum(levels.values(), start=Decimal(0)) for levels in bid_maps)
    ask_depths = tuple(sum(levels.values(), start=Decimal(0)) for levels in ask_maps)

    metrics = LiquidityStructureMetrics(
        snapshot_count=len(snapshots),
        duration_ms=duration_ms,
        bid_appearance_events=bid_events[0],
        bid_disappearance_events=bid_events[1],
        bid_replenishment_events=bid_events[2],
        ask_appearance_events=ask_events[0],
        ask_disappearance_events=ask_events[1],
        ask_replenishment_events=ask_events[2],
        bid_appearance_events_per_second=_event_rate(bid_events[0], duration_ms),
        bid_disappearance_events_per_second=_event_rate(
            bid_events[1],
            duration_ms,
        ),
        ask_appearance_events_per_second=_event_rate(ask_events[0], duration_ms),
        ask_disappearance_events_per_second=_event_rate(
            ask_events[1],
            duration_ms,
        ),
        latest_bid_depth_notional=bid_depths[-1],
        median_bid_depth_notional=_median(bid_depths),
        latest_ask_depth_notional=ask_depths[-1],
        median_ask_depth_notional=_median(ask_depths),
    )

    pools = tuple(
        sorted(
            (
                *_persistent_pools(
                    side=LiquidityLevelSide.BID,
                    maps=bid_maps,
                    snapshots=snapshots,
                    config=config,
                ),
                *_persistent_pools(
                    side=LiquidityLevelSide.ASK,
                    maps=ask_maps,
                    snapshots=snapshots,
                    config=config,
                ),
            ),
            key=lambda item: (item.side.value, item.price),
        )
    )

    candidates = _derive_candidates(
        snapshots=snapshots,
        bid_maps=bid_maps,
        ask_maps=ask_maps,
        bid_depths=bid_depths,
        ask_depths=ask_depths,
        pools=pools,
        config=config,
    )

    uncertainty_flags: tuple[str, ...] = ()
    if candidates:
        uncertainty_flags = (
            "candidate_labels_are_bounded_evidence_not_actor_intent_or_causality",
        )

    payload = {
        "as_of_ms": as_of_ms,
        "candidates": [item.candidate_identity for item in candidates],
        "consumed_snapshot_count": len(snapshots),
        "engine_version": LIQUIDITY_STRUCTURE_ENGINE_VERSION,
        "exchange": exchange,
        "first_snapshot_identity": snapshots[0].snapshot_identity,
        "last_snapshot_identity": snapshots[-1].snapshot_identity,
        "latest_snapshot_age_ms": latest_age,
        "market_type": market_type,
        "metrics": _metrics_payload(metrics),
        "observed_at_ms": max(item.ingested_at_ms for item in snapshots),
        "persistent_pools": [item.pool_identity for item in pools],
        "source_quality": LiquiditySourceQuality.GOOD,
        "source_window_end_ms": snapshots[-1].event_at_ms,
        "source_window_start_ms": source_window_start_ms,
        "status": LiquidityStructureStatus.MEASURED,
        "symbol": symbol,
        "uncertainty_flags": uncertainty_flags,
    }
    return LiquidityStructureAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=LIQUIDITY_STRUCTURE_ENGINE_VERSION,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        as_of_ms=as_of_ms,
        observed_at_ms=max(item.ingested_at_ms for item in snapshots),
        source_window_start_ms=source_window_start_ms,
        source_window_end_ms=snapshots[-1].event_at_ms,
        first_snapshot_identity=snapshots[0].snapshot_identity,
        last_snapshot_identity=snapshots[-1].snapshot_identity,
        consumed_snapshot_count=len(snapshots),
        latest_snapshot_age_ms=latest_age,
        source_quality=LiquiditySourceQuality.GOOD,
        status=LiquidityStructureStatus.MEASURED,
        metrics=metrics,
        persistent_pools=pools,
        candidates=candidates,
        uncertainty_flags=uncertainty_flags,
    )


def _unresolved(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    snapshots: tuple[OrderBookSnapshot, ...],
    as_of_ms: int,
    source_window_start_ms: int,
    source_quality: LiquiditySourceQuality,
    flags: tuple[str, ...],
) -> LiquidityStructureAnalysis:
    latest = snapshots[-1] if snapshots else None
    observed_at_ms = max((item.ingested_at_ms for item in snapshots), default=0)
    payload = {
        "as_of_ms": as_of_ms,
        "candidates": [],
        "consumed_snapshot_count": len(snapshots),
        "engine_version": LIQUIDITY_STRUCTURE_ENGINE_VERSION,
        "exchange": exchange,
        "first_snapshot_identity": (
            None if not snapshots else snapshots[0].snapshot_identity
        ),
        "last_snapshot_identity": None if latest is None else latest.snapshot_identity,
        "latest_snapshot_age_ms": (
            None if latest is None else as_of_ms - latest.event_at_ms
        ),
        "market_type": market_type,
        "metrics": None,
        "observed_at_ms": observed_at_ms,
        "persistent_pools": [],
        "source_quality": source_quality,
        "source_window_end_ms": None if latest is None else latest.event_at_ms,
        "source_window_start_ms": source_window_start_ms,
        "status": LiquidityStructureStatus.UNRESOLVED,
        "symbol": symbol,
        "uncertainty_flags": flags,
    }
    return LiquidityStructureAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=LIQUIDITY_STRUCTURE_ENGINE_VERSION,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        as_of_ms=as_of_ms,
        observed_at_ms=observed_at_ms,
        source_window_start_ms=source_window_start_ms,
        source_window_end_ms=None if latest is None else latest.event_at_ms,
        first_snapshot_identity=(
            None if not snapshots else snapshots[0].snapshot_identity
        ),
        last_snapshot_identity=None if latest is None else latest.snapshot_identity,
        consumed_snapshot_count=len(snapshots),
        latest_snapshot_age_ms=(
            None if latest is None else as_of_ms - latest.event_at_ms
        ),
        source_quality=source_quality,
        status=LiquidityStructureStatus.UNRESOLVED,
        metrics=None,
        persistent_pools=(),
        candidates=(),
        uncertainty_flags=flags,
    )


def _side_map(
    snapshot: OrderBookSnapshot,
    side: LiquidityLevelSide,
    config: LiquidityStructureConfig,
) -> dict[Decimal, Decimal]:
    levels = snapshot.bids if side is LiquidityLevelSide.BID else snapshot.asks
    return {
        level.price: level.notional
        for level in levels[: config.depth_levels]
    }


def _event_totals(
    maps: tuple[dict[Decimal, Decimal], ...],
) -> tuple[int, int, int]:
    appearances = 0
    disappearances = 0
    replenishments = 0
    for left, right in pairwise(maps):
        prices = set(left) | set(right)
        for price in prices:
            previous = left.get(price, Decimal(0))
            current = right.get(price, Decimal(0))
            if previous == Decimal(0) and current > Decimal(0):
                appearances += 1
            elif previous > Decimal(0) and current == Decimal(0):
                disappearances += 1
            elif previous > Decimal(0) and current > previous:
                replenishments += 1
    return appearances, disappearances, replenishments


def _persistent_pools(
    *,
    side: LiquidityLevelSide,
    maps: tuple[dict[Decimal, Decimal], ...],
    snapshots: tuple[OrderBookSnapshot, ...],
    config: LiquidityStructureConfig,
) -> tuple[PersistentLiquidityPool, ...]:
    pools: list[PersistentLiquidityPool] = []
    prices = sorted({price for levels in maps for price in levels})
    for price in prices:
        values = tuple(levels.get(price, Decimal(0)) for levels in maps)
        present_indices = tuple(
            index for index, value in enumerate(values) if value > Decimal(0)
        )
        if not present_indices:
            continue
        presence_fraction = Decimal(len(present_indices)) / Decimal(len(maps))
        if len(present_indices) < config.minimum_pool_snapshots:
            continue
        if presence_fraction < config.persistent_min_presence_fraction:
            continue

        present_values = tuple(values[index] for index in present_indices)
        appearance_events, disappearance_events, replenishment_events = (
            _level_event_counts(values)
        )
        first_seen_ms = snapshots[present_indices[0]].event_at_ms
        last_seen_ms = snapshots[present_indices[-1]].event_at_ms
        mean_notional = (
            sum(present_values, start=Decimal(0))
            / Decimal(len(present_values))
        )
        max_notional = max(present_values)
        latest_notional = values[-1]
        payload = {
            "appearance_events": appearance_events,
            "disappearance_events": disappearance_events,
            "first_seen_ms": first_seen_ms,
            "last_seen_ms": last_seen_ms,
            "latest_notional": latest_notional,
            "max_notional": max_notional,
            "mean_notional": mean_notional,
            "presence_fraction": presence_fraction,
            "price": price,
            "replenishment_events": replenishment_events,
            "side": side,
            "snapshots_present": len(present_indices),
            "total_snapshots": len(maps),
        }
        pools.append(
            PersistentLiquidityPool(
                pool_identity=canonical_sha256(payload),
                side=side,
                price=price,
                first_seen_ms=first_seen_ms,
                last_seen_ms=last_seen_ms,
                snapshots_present=len(present_indices),
                total_snapshots=len(maps),
                presence_fraction=presence_fraction,
                mean_notional=mean_notional,
                max_notional=max_notional,
                latest_notional=latest_notional,
                appearance_events=appearance_events,
                disappearance_events=disappearance_events,
                replenishment_events=replenishment_events,
            )
        )
    return tuple(pools)


def _derive_candidates(
    *,
    snapshots: tuple[OrderBookSnapshot, ...],
    bid_maps: tuple[dict[Decimal, Decimal], ...],
    ask_maps: tuple[dict[Decimal, Decimal], ...],
    bid_depths: tuple[Decimal, ...],
    ask_depths: tuple[Decimal, ...],
    pools: tuple[PersistentLiquidityPool, ...],
    config: LiquidityStructureConfig,
) -> tuple[LiquidityStructureCandidate, ...]:
    candidates: list[LiquidityStructureCandidate] = []

    pool_lookup = {(pool.side, pool.price): pool for pool in pools}
    for pool in pools:
        maps = bid_maps if pool.side is LiquidityLevelSide.BID else ask_maps
        values = tuple(levels.get(pool.price, Decimal(0)) for levels in maps)
        present_indices = tuple(
            index for index, value in enumerate(values) if value > Decimal(0)
        )
        last_present = present_indices[-1]
        if last_present < len(snapshots) - 1 and _quote_traversed_pool(
            side=pool.side,
            price=pool.price,
            snapshots=snapshots[last_present + 1 :],
        ):
            candidates.append(
                _candidate(
                    kind=LiquidityStructureCandidateKind.LIQUIDITY_SWEEP,
                    side=pool.side,
                    price=pool.price,
                    start_ms=pool.first_seen_ms,
                    end_ms=snapshots[-1].event_at_ms,
                    supporting_snapshot_count=pool.snapshots_present,
                    peak_notional=pool.max_notional,
                    reason_codes=(
                        "persistent_pool_disappeared",
                        "best_quote_traversed_pool_price",
                    ),
                    uncertainty_flags=(
                        "orderbook_only_sweep_candidate_not_trade_causality",
                    ),
                )
            )

        if (
            pool.replenishment_events
            >= config.hidden_liquidity_min_replenishments
        ):
            candidates.append(
                _candidate(
                    kind=LiquidityStructureCandidateKind.HIDDEN_LIQUIDITY,
                    side=pool.side,
                    price=pool.price,
                    start_ms=pool.first_seen_ms,
                    end_ms=pool.last_seen_ms,
                    supporting_snapshot_count=pool.snapshots_present,
                    peak_notional=pool.max_notional,
                    reason_codes=(
                        "repeated_same_price_replenishment",
                        "level_persisted_across_window",
                    ),
                    uncertainty_flags=(
                        "orderbook_only_replenishment_not_proof_of_hidden_liquidity",
                    ),
                )
            )

    for side, maps in (
        (LiquidityLevelSide.BID, bid_maps),
        (LiquidityLevelSide.ASK, ask_maps),
    ):
        reference = _median(
            tuple(
                value
                for levels in maps
                for value in levels.values()
                if value > Decimal(0)
            )
        )
        if reference <= Decimal(0):
            continue
        prices = sorted({price for levels in maps for price in levels})
        for price in prices:
            if (side, price) in pool_lookup:
                continue
            values = tuple(levels.get(price, Decimal(0)) for levels in maps)
            present_indices = tuple(
                index for index, value in enumerate(values) if value > Decimal(0)
            )
            if len(present_indices) < config.ghost_min_snapshots:
                continue
            first_present = present_indices[0]
            last_present = present_indices[-1]
            if first_present == 0 or last_present == len(maps) - 1:
                continue
            peak = max(values)
            if peak < reference * config.large_level_multiplier:
                continue
            if _quote_traversed_pool(
                side=side,
                price=price,
                snapshots=snapshots[last_present + 1 :],
            ):
                continue
            candidates.append(
                _candidate(
                    kind=LiquidityStructureCandidateKind.GHOST_ORDER,
                    side=side,
                    price=price,
                    start_ms=snapshots[first_present].event_at_ms,
                    end_ms=snapshots[last_present].event_at_ms,
                    supporting_snapshot_count=len(present_indices),
                    peak_notional=peak,
                    reason_codes=(
                        "large_transient_level_appeared",
                        "level_disappeared_without_quote_traversal",
                    ),
                    uncertainty_flags=(
                        "orderbook_only_cannot_distinguish_cancel_reprice_or_execution",
                    ),
                )
            )

    for side, depths in (
        (LiquidityLevelSide.BID, bid_depths),
        (LiquidityLevelSide.ASK, ask_depths),
    ):
        median_depth = _median(depths)
        latest_depth = depths[-1]
        if (
            median_depth > Decimal(0)
            and latest_depth
            <= median_depth * config.shallow_depth_fraction
        ):
            best = (
                snapshots[-1].bids[0]
                if side is LiquidityLevelSide.BID
                else snapshots[-1].asks[0]
            )
            candidates.append(
                _candidate(
                    kind=LiquidityStructureCandidateKind.SHALLOW_BOOK,
                    side=side,
                    price=best.price,
                    start_ms=snapshots[0].event_at_ms,
                    end_ms=snapshots[-1].event_at_ms,
                    supporting_snapshot_count=len(snapshots),
                    peak_notional=max(depths),
                    reason_codes=(
                        "latest_depth_below_window_median_fraction",
                    ),
                    uncertainty_flags=(
                        "relative_depth_condition_not_directional_prediction",
                    ),
                )
            )

    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.kind.value,
                item.side.value,
                item.price,
                item.observed_start_ms,
                item.candidate_identity,
            ),
        )
    )


def _candidate(
    *,
    kind: LiquidityStructureCandidateKind,
    side: LiquidityLevelSide,
    price: Decimal,
    start_ms: int,
    end_ms: int,
    supporting_snapshot_count: int,
    peak_notional: Decimal,
    reason_codes: tuple[str, ...],
    uncertainty_flags: tuple[str, ...],
) -> LiquidityStructureCandidate:
    payload = {
        "kind": kind,
        "observed_end_ms": end_ms,
        "observed_start_ms": start_ms,
        "peak_notional": peak_notional,
        "price": price,
        "reason_codes": reason_codes,
        "side": side,
        "supporting_snapshot_count": supporting_snapshot_count,
        "uncertainty_flags": uncertainty_flags,
    }
    return LiquidityStructureCandidate(
        candidate_identity=canonical_sha256(payload),
        kind=kind,
        side=side,
        price=price,
        observed_start_ms=start_ms,
        observed_end_ms=end_ms,
        supporting_snapshot_count=supporting_snapshot_count,
        peak_notional=peak_notional,
        reason_codes=reason_codes,
        uncertainty_flags=uncertainty_flags,
    )


def _level_event_counts(
    values: tuple[Decimal, ...],
) -> tuple[int, int, int]:
    appearances = 0
    disappearances = 0
    replenishments = 0
    for previous, current in pairwise(values):
        if previous == Decimal(0) and current > Decimal(0):
            appearances += 1
        elif previous > Decimal(0) and current == Decimal(0):
            disappearances += 1
        elif previous > Decimal(0) and current > previous:
            replenishments += 1
    return appearances, disappearances, replenishments


def _quote_traversed_pool(
    *,
    side: LiquidityLevelSide,
    price: Decimal,
    snapshots: tuple[OrderBookSnapshot, ...],
) -> bool:
    if side is LiquidityLevelSide.BID:
        return any(snapshot.bids[0].price < price for snapshot in snapshots)
    return any(snapshot.asks[0].price > price for snapshot in snapshots)


def _event_rate(count: int, duration_ms: int) -> Decimal:
    return Decimal(count) * _ONE_SECOND_MS / Decimal(duration_ms)


def _median(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        return Decimal(0)
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)


def _analysis_payload(analysis: LiquidityStructureAnalysis) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "candidates": [item.candidate_identity for item in analysis.candidates],
        "consumed_snapshot_count": analysis.consumed_snapshot_count,
        "engine_version": analysis.engine_version,
        "exchange": analysis.exchange,
        "first_snapshot_identity": analysis.first_snapshot_identity,
        "last_snapshot_identity": analysis.last_snapshot_identity,
        "latest_snapshot_age_ms": analysis.latest_snapshot_age_ms,
        "market_type": analysis.market_type,
        "metrics": (
            None if analysis.metrics is None else _metrics_payload(analysis.metrics)
        ),
        "observed_at_ms": analysis.observed_at_ms,
        "persistent_pools": [
            item.pool_identity for item in analysis.persistent_pools
        ],
        "source_quality": analysis.source_quality,
        "source_window_end_ms": analysis.source_window_end_ms,
        "source_window_start_ms": analysis.source_window_start_ms,
        "status": analysis.status,
        "symbol": analysis.symbol,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _metrics_payload(metrics: LiquidityStructureMetrics) -> dict[str, object]:
    return {
        "ask_appearance_events": metrics.ask_appearance_events,
        "ask_appearance_events_per_second": (
            metrics.ask_appearance_events_per_second
        ),
        "ask_disappearance_events": metrics.ask_disappearance_events,
        "ask_disappearance_events_per_second": (
            metrics.ask_disappearance_events_per_second
        ),
        "ask_replenishment_events": metrics.ask_replenishment_events,
        "bid_appearance_events": metrics.bid_appearance_events,
        "bid_appearance_events_per_second": (
            metrics.bid_appearance_events_per_second
        ),
        "bid_disappearance_events": metrics.bid_disappearance_events,
        "bid_disappearance_events_per_second": (
            metrics.bid_disappearance_events_per_second
        ),
        "bid_replenishment_events": metrics.bid_replenishment_events,
        "duration_ms": metrics.duration_ms,
        "latest_ask_depth_notional": metrics.latest_ask_depth_notional,
        "latest_bid_depth_notional": metrics.latest_bid_depth_notional,
        "median_ask_depth_notional": metrics.median_ask_depth_notional,
        "median_bid_depth_notional": metrics.median_bid_depth_notional,
        "snapshot_count": metrics.snapshot_count,
    }


def _pool_payload(pool: PersistentLiquidityPool) -> dict[str, object]:
    return {
        "appearance_events": pool.appearance_events,
        "disappearance_events": pool.disappearance_events,
        "first_seen_ms": pool.first_seen_ms,
        "last_seen_ms": pool.last_seen_ms,
        "latest_notional": pool.latest_notional,
        "max_notional": pool.max_notional,
        "mean_notional": pool.mean_notional,
        "presence_fraction": pool.presence_fraction,
        "price": pool.price,
        "replenishment_events": pool.replenishment_events,
        "side": pool.side,
        "snapshots_present": pool.snapshots_present,
        "total_snapshots": pool.total_snapshots,
    }


def _candidate_payload(
    candidate: LiquidityStructureCandidate,
) -> dict[str, object]:
    return {
        "kind": candidate.kind,
        "observed_end_ms": candidate.observed_end_ms,
        "observed_start_ms": candidate.observed_start_ms,
        "peak_notional": candidate.peak_notional,
        "price": candidate.price,
        "reason_codes": candidate.reason_codes,
        "side": candidate.side,
        "supporting_snapshot_count": candidate.supporting_snapshot_count,
        "uncertainty_flags": candidate.uncertainty_flags,
    }


def _context(
    snapshots: tuple[OrderBookSnapshot, ...],
) -> tuple[Exchange, MarketType, str]:
    first = snapshots[0]
    for snapshot in snapshots[1:]:
        _require_same_context(
            first.exchange,
            first.market_type,
            first.symbol,
            snapshot,
        )
    return first.exchange, first.market_type, first.symbol


def _require_same_context(
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    snapshot: OrderBookSnapshot,
) -> None:
    if (
        snapshot.exchange is not exchange
        or snapshot.market_type is not market_type
        or snapshot.symbol != symbol
    ):
        raise ValueError("liquidity structure requires one market context")


def _reject_duplicate_identities(
    snapshots: tuple[OrderBookSnapshot, ...],
) -> None:
    identities = [item.snapshot_identity for item in snapshots]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate orderbook snapshot identity")


def _require_fraction(
    value: Decimal,
    label: str,
    *,
    include_one: bool,
) -> None:
    _require_finite(value, label)
    upper_ok = value <= Decimal(1) if include_one else value < Decimal(1)
    if value <= Decimal(0) or not upper_ok:
        bound = "(0,1]" if include_one else "(0,1)"
        raise ValueError(f"{label} must be inside {bound}")


def _require_positive_finite(value: Decimal, label: str) -> None:
    _require_finite(value, label)
    if value <= Decimal(0):
        raise ValueError(f"{label} must be positive")


def _require_finite(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
