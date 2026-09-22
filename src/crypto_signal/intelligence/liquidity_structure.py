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

LIQUIDITY_STRUCTURE_ENGINE_VERSION = "liquidity-structure-v2-slice2/1"
LIQUIDITY_STRUCTURE_FREEZE_SCHEMA_VERSION = "liquidity-structure-freeze-v1/1"
_BPS = Decimal(10000)
_ONE_SECOND_MS = Decimal(1000)


class LiquidityStructureStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class LiquiditySide(StrEnum):
    BID = "bid"
    ASK = "ask"


class LiquidityLevelCandidate(StrEnum):
    PERSISTENT_POOL = "persistent_liquidity_pool_candidate"
    SPOOFING = "spoofing_candidate"
    HIDDEN_LIQUIDITY = "hidden_liquidity_candidate"


@dataclass(frozen=True, slots=True)
class LiquidityStructureConfig:
    depth_levels: int = 10
    lookback_ms: int = 120_000
    minimum_snapshots: int = 5
    max_snapshot_age_ms: int = 30_000
    max_snapshot_gap_ms: int = 30_000
    persistent_presence_fraction: Decimal = Decimal("0.60")
    material_notional_multiple: Decimal = Decimal("1.50")
    approach_bps: Decimal = Decimal(10)
    rapid_withdrawal_max_lifetime_ms: int = 30_000
    rapid_withdrawal_min_fraction: Decimal = Decimal("0.80")
    hidden_liquidity_min_replenishment_cycles: int = 2
    hidden_liquidity_min_replenishment_fraction: Decimal = Decimal("0.50")

    def __post_init__(self) -> None:
        if self.depth_levels <= 0:
            raise ValueError("liquidity structure depth_levels must be positive")
        if self.lookback_ms <= 0:
            raise ValueError("liquidity structure lookback_ms must be positive")
        if self.minimum_snapshots < 3:
            raise ValueError("liquidity structure minimum_snapshots must be at least 3")
        if self.max_snapshot_age_ms <= 0 or self.max_snapshot_gap_ms <= 0:
            raise ValueError("liquidity structure age/gap bounds must be positive")
        if self.rapid_withdrawal_max_lifetime_ms <= 0:
            raise ValueError("rapid withdrawal lifetime must be positive")
        if self.hidden_liquidity_min_replenishment_cycles < 1:
            raise ValueError("hidden-liquidity replenishment cycles must be positive")
        for label, value in (
            ("persistent_presence_fraction", self.persistent_presence_fraction),
            ("rapid_withdrawal_min_fraction", self.rapid_withdrawal_min_fraction),
            (
                "hidden_liquidity_min_replenishment_fraction",
                self.hidden_liquidity_min_replenishment_fraction,
            ),
        ):
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
            if not Decimal(0) < value <= Decimal(1):
                raise ValueError(f"{label} must be inside (0,1]")
        for label, value in (
            ("material_notional_multiple", self.material_notional_multiple),
            ("approach_bps", self.approach_bps),
        ):
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
            if value <= Decimal(0):
                raise ValueError(f"{label} must be positive")


DEFAULT_LIQUIDITY_STRUCTURE_CONFIG = LiquidityStructureConfig()


@dataclass(frozen=True, slots=True)
class LiquidityLevelEvidence:
    side: LiquiditySide
    price: Decimal
    snapshot_count: int
    presence_count: int
    presence_fraction: Decimal
    first_seen_ms: int
    last_seen_ms: int
    survival_ms: int
    max_notional: Decimal
    mean_present_notional: Decimal
    last_notional: Decimal
    gross_added_notional: Decimal
    gross_removed_notional: Decimal
    appearance_notional: Decimal
    cancellation_notional: Decimal
    replenishment_notional: Decimal
    depletion_notional: Decimal
    appearance_count: int
    disappearance_count: int
    replenishment_cycles: int
    min_distance_to_mid_bps: Decimal
    materiality_multiple: Decimal
    candidates: tuple[LiquidityLevelCandidate, ...]
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.snapshot_count < 1:
            raise ValueError("level evidence snapshot_count must be positive")
        if not 1 <= self.presence_count <= self.snapshot_count:
            raise ValueError("level evidence presence_count outside snapshot bounds")
        _require_finite(self.price, "level price")
        if self.price <= Decimal(0):
            raise ValueError("level price must be positive")
        _require_finite(self.presence_fraction, "presence_fraction")
        if not Decimal(0) < self.presence_fraction <= Decimal(1):
            raise ValueError("presence_fraction must be inside (0,1]")
        if min(self.first_seen_ms, self.last_seen_ms, self.survival_ms) < 0:
            raise ValueError("level timestamps/duration cannot be negative")
        if self.last_seen_ms < self.first_seen_ms:
            raise ValueError("level last_seen precedes first_seen")
        if self.survival_ms != self.last_seen_ms - self.first_seen_ms:
            raise ValueError("level survival_ms mismatch")
        for label, value in (
            ("max_notional", self.max_notional),
            ("mean_present_notional", self.mean_present_notional),
            ("last_notional", self.last_notional),
            ("gross_added_notional", self.gross_added_notional),
            ("gross_removed_notional", self.gross_removed_notional),
            ("appearance_notional", self.appearance_notional),
            ("cancellation_notional", self.cancellation_notional),
            ("replenishment_notional", self.replenishment_notional),
            ("depletion_notional", self.depletion_notional),
            ("min_distance_to_mid_bps", self.min_distance_to_mid_bps),
            ("materiality_multiple", self.materiality_multiple),
        ):
            _require_finite(value, label)
            if value < Decimal(0):
                raise ValueError(f"{label} cannot be negative")
        if self.max_notional <= Decimal(0) or self.mean_present_notional <= Decimal(0):
            raise ValueError("present level notionals must be positive")
        if min(
            self.appearance_count,
            self.disappearance_count,
            self.replenishment_cycles,
        ) < 0:
            raise ValueError("level counts cannot be negative")
        if len(self.candidates) != len(set(self.candidates)):
            raise ValueError("level candidates must be unique")
        has_behavior_candidate = any(
            item
            in {
                LiquidityLevelCandidate.SPOOFING,
                LiquidityLevelCandidate.HIDDEN_LIQUIDITY,
            }
            for item in self.candidates
        )
        if has_behavior_candidate and not self.uncertainty_flags:
            raise ValueError("behavior candidate requires uncertainty flags")


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
    bid_levels: tuple[LiquidityLevelEvidence, ...]
    ask_levels: tuple[LiquidityLevelEvidence, ...]
    bid_appearance_notional_per_second: Decimal | None
    bid_cancellation_notional_per_second: Decimal | None
    ask_appearance_notional_per_second: Decimal | None
    ask_cancellation_notional_per_second: Decimal | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "liquidity structure evidence identity")
        if self.engine_version != LIQUIDITY_STRUCTURE_ENGINE_VERSION:
            raise ValueError("unsupported liquidity structure engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("liquidity structure symbol must be uppercase")
        if min(self.as_of_ms, self.observed_at_ms, self.source_window_start_ms) < 0:
            raise ValueError("liquidity structure timestamps cannot be negative")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("liquidity structure cannot observe future evidence")
        if self.source_window_start_ms > self.as_of_ms:
            raise ValueError("liquidity structure window begins after as-of")
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
            if self.first_snapshot_identity is not None or self.last_snapshot_identity is not None:
                raise ValueError("empty structure window cannot carry snapshot identities")
        else:
            if self.first_snapshot_identity is None or self.last_snapshot_identity is None:
                raise ValueError("non-empty structure window requires boundary identities")
            _require_sha256(self.first_snapshot_identity, "first structure snapshot identity")
            _require_sha256(self.last_snapshot_identity, "last structure snapshot identity")
        rates = (
            self.bid_appearance_notional_per_second,
            self.bid_cancellation_notional_per_second,
            self.ask_appearance_notional_per_second,
            self.ask_cancellation_notional_per_second,
        )
        if self.status is LiquidityStructureStatus.MEASURED:
            if self.source_quality is not LiquiditySourceQuality.GOOD:
                raise ValueError("measured liquidity structure requires good source quality")
            if not self.bid_levels or not self.ask_levels:
                raise ValueError("measured liquidity structure requires both book sides")
            if any(value is None for value in rates):
                raise ValueError("measured liquidity structure requires rate metrics")
            for value in rates:
                assert value is not None
                _require_finite(value, "liquidity structure rate")
                if value < Decimal(0):
                    raise ValueError("liquidity structure rate cannot be negative")
        else:
            if self.source_quality is LiquiditySourceQuality.GOOD:
                raise ValueError("unresolved liquidity structure cannot claim good quality")
            if self.bid_levels or self.ask_levels:
                raise ValueError("unresolved liquidity structure cannot expose level evidence")
            if any(value is not None for value in rates):
                raise ValueError("unresolved liquidity structure cannot expose rates")
            if not self.uncertainty_flags:
                raise ValueError("unresolved liquidity structure requires uncertainty")
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
            if (
                snapshot.exchange is not self.analysis.exchange
                or snapshot.market_type is not self.analysis.market_type
                or snapshot.symbol != self.analysis.symbol
            ):
                raise ValueError("liquidity structure freeze context mismatch")
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
                    item.snapshot_identity for item in self.snapshots
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
        raise ValueError("liquidity structure requires at least one orderbook snapshot")

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
    _reject_duplicate_identities(books)
    exchange, market_type, symbol = _context(books)
    safe = tuple(
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
    window_start = max(0, as_of_ms - config.lookback_ms)
    selected = tuple(item for item in safe if item.event_at_ms >= window_start)

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

    latest = snapshots[-1]
    flags: list[str] = []
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

    bid_levels, bid_appearance, bid_cancel = _derive_side(
        snapshots=snapshots,
        side=LiquiditySide.BID,
        config=config,
    )
    ask_levels, ask_appearance, ask_cancel = _derive_side(
        snapshots=snapshots,
        side=LiquiditySide.ASK,
        config=config,
    )
    duration_ms = snapshots[-1].event_at_ms - snapshots[0].event_at_ms
    duration_seconds = Decimal(duration_ms) / _ONE_SECOND_MS
    uncertainty: list[str] = []
    all_levels = (*bid_levels, *ask_levels)
    if any(LiquidityLevelCandidate.SPOOFING in item.candidates for item in all_levels):
        uncertainty.append("spoofing_candidate_not_proof_of_actor_intent")
    if any(
        LiquidityLevelCandidate.HIDDEN_LIQUIDITY in item.candidates
        for item in all_levels
    ):
        uncertainty.append(
            "hidden_liquidity_candidate_requires_trade_flow_confirmation"
        )
    if any(
        item.candidates for item in all_levels
    ):
        uncertainty.append("orderbook_only_candidate_semantics")

    payload = {
        "as_of_ms": as_of_ms,
        "ask_appearance_notional_per_second": ask_appearance / duration_seconds,
        "ask_cancellation_notional_per_second": ask_cancel / duration_seconds,
        "ask_levels": [_level_payload(item) for item in ask_levels],
        "bid_appearance_notional_per_second": bid_appearance / duration_seconds,
        "bid_cancellation_notional_per_second": bid_cancel / duration_seconds,
        "bid_levels": [_level_payload(item) for item in bid_levels],
        "consumed_snapshot_count": len(snapshots),
        "engine_version": LIQUIDITY_STRUCTURE_ENGINE_VERSION,
        "exchange": exchange,
        "first_snapshot_identity": snapshots[0].snapshot_identity,
        "last_snapshot_identity": snapshots[-1].snapshot_identity,
        "latest_snapshot_age_ms": latest_age,
        "market_type": market_type,
        "observed_at_ms": max(item.ingested_at_ms for item in snapshots),
        "source_quality": LiquiditySourceQuality.GOOD,
        "source_window_end_ms": snapshots[-1].event_at_ms,
        "source_window_start_ms": source_window_start_ms,
        "status": LiquidityStructureStatus.MEASURED,
        "symbol": symbol,
        "uncertainty_flags": tuple(uncertainty),
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
        bid_levels=bid_levels,
        ask_levels=ask_levels,
        bid_appearance_notional_per_second=bid_appearance / duration_seconds,
        bid_cancellation_notional_per_second=bid_cancel / duration_seconds,
        ask_appearance_notional_per_second=ask_appearance / duration_seconds,
        ask_cancellation_notional_per_second=ask_cancel / duration_seconds,
        uncertainty_flags=tuple(uncertainty),
    )


def _derive_side(
    *,
    snapshots: tuple[OrderBookSnapshot, ...],
    side: LiquiditySide,
    config: LiquidityStructureConfig,
) -> tuple[tuple[LiquidityLevelEvidence, ...], Decimal, Decimal]:
    books = tuple(
        tuple((item.bids if side is LiquiditySide.BID else item.asks)[: config.depth_levels])
        for item in snapshots
    )
    prices = sorted(
        {level.price for levels in books for level in levels},
        reverse=side is LiquiditySide.BID,
    )
    series_by_price: dict[Decimal, tuple[Decimal, ...]] = {
        price: tuple(
            next((level.notional for level in levels if level.price == price), Decimal(0))
            for levels in books
        )
        for price in prices
    }
    present_means = {
        price: _mean(tuple(value for value in series if value > Decimal(0)))
        for price, series in series_by_price.items()
    }
    baseline = _median(tuple(present_means.values()))
    if baseline <= Decimal(0):
        raise ValueError("liquidity structure materiality baseline must be positive")

    appearance_total = Decimal(0)
    cancellation_total = Decimal(0)
    result: list[LiquidityLevelEvidence] = []
    for price in prices:
        series = series_by_price[price]
        presence_indices = tuple(
            index for index, value in enumerate(series) if value > Decimal(0)
        )
        present_values = tuple(series[index] for index in presence_indices)
        gross_added = Decimal(0)
        gross_removed = Decimal(0)
        appearance_notional = Decimal(0)
        cancellation_notional = Decimal(0)
        replenishment_notional = Decimal(0)
        depletion_notional = Decimal(0)
        appearance_count = 0
        disappearance_count = 0
        replenishment_cycles = 0
        depleted_since_replenishment = False
        previous = Decimal(0)

        for current in series:
            delta = current - previous
            if delta > Decimal(0):
                gross_added += delta
                if previous == Decimal(0):
                    appearance_notional += current
                    appearance_count += 1
                else:
                    replenishment_notional += delta
                    if depleted_since_replenishment:
                        replenishment_cycles += 1
                        depleted_since_replenishment = False
            elif delta < Decimal(0):
                removed = -delta
                gross_removed += removed
                depletion_notional += removed
                depleted_since_replenishment = True
                if current == Decimal(0):
                    cancellation_notional += previous
                    disappearance_count += 1
            previous = current

        appearance_total += appearance_notional
        cancellation_total += cancellation_notional

        first_index = presence_indices[0]
        last_index = presence_indices[-1]
        first_seen = snapshots[first_index].event_at_ms
        last_seen = snapshots[last_index].event_at_ms
        presence_fraction = Decimal(len(presence_indices)) / Decimal(len(snapshots))
        mean_present = present_means[price]
        materiality_multiple = mean_present / baseline
        min_distance = min(
            _distance_to_mid_bps(price, snapshots[index])
            for index in presence_indices
        )
        max_notional = max(present_values)
        last_notional = series[-1]

        candidates: list[LiquidityLevelCandidate] = []
        uncertainty_flags: list[str] = []
        material = materiality_multiple >= config.material_notional_multiple
        persistent = (
            material
            and presence_fraction >= config.persistent_presence_fraction
        )
        if persistent:
            candidates.append(LiquidityLevelCandidate.PERSISTENT_POOL)

        removed_fraction = (
            gross_removed / max_notional
            if max_notional > Decimal(0)
            else Decimal(0)
        )
        rapid_withdrawal = (
            material
            and last_notional == Decimal(0)
            and last_seen - first_seen <= config.rapid_withdrawal_max_lifetime_ms
            and removed_fraction >= config.rapid_withdrawal_min_fraction
            and min_distance <= config.approach_bps
        )
        if rapid_withdrawal:
            candidates.append(LiquidityLevelCandidate.SPOOFING)
            uncertainty_flags.append("candidate_only_no_actor_intent_attribution")

        hidden_candidate = (
            material
            and replenishment_cycles
            >= config.hidden_liquidity_min_replenishment_cycles
            and gross_removed > Decimal(0)
            and replenishment_notional
            >= gross_removed * config.hidden_liquidity_min_replenishment_fraction
        )
        if hidden_candidate:
            candidates.append(LiquidityLevelCandidate.HIDDEN_LIQUIDITY)
            uncertainty_flags.append("orderbook_refresh_requires_trade_flow_confirmation")

        result.append(
            LiquidityLevelEvidence(
                side=side,
                price=price,
                snapshot_count=len(snapshots),
                presence_count=len(presence_indices),
                presence_fraction=presence_fraction,
                first_seen_ms=first_seen,
                last_seen_ms=last_seen,
                survival_ms=last_seen - first_seen,
                max_notional=max_notional,
                mean_present_notional=mean_present,
                last_notional=last_notional,
                gross_added_notional=gross_added,
                gross_removed_notional=gross_removed,
                appearance_notional=appearance_notional,
                cancellation_notional=cancellation_notional,
                replenishment_notional=replenishment_notional,
                depletion_notional=depletion_notional,
                appearance_count=appearance_count,
                disappearance_count=disappearance_count,
                replenishment_cycles=replenishment_cycles,
                min_distance_to_mid_bps=min_distance,
                materiality_multiple=materiality_multiple,
                candidates=tuple(candidates),
                uncertainty_flags=tuple(uncertainty_flags),
            )
        )

    return tuple(result), appearance_total, cancellation_total


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
    payload: dict[str, object] = {
        "as_of_ms": as_of_ms,
        "ask_appearance_notional_per_second": None,
        "ask_cancellation_notional_per_second": None,
        "ask_levels": [],
        "bid_appearance_notional_per_second": None,
        "bid_cancellation_notional_per_second": None,
        "bid_levels": [],
        "consumed_snapshot_count": len(snapshots),
        "engine_version": LIQUIDITY_STRUCTURE_ENGINE_VERSION,
        "exchange": exchange,
        "first_snapshot_identity": (
            None if not snapshots else snapshots[0].snapshot_identity
        ),
        "last_snapshot_identity": (
            None if not snapshots else snapshots[-1].snapshot_identity
        ),
        "latest_snapshot_age_ms": (
            None if latest is None else as_of_ms - latest.event_at_ms
        ),
        "market_type": market_type,
        "observed_at_ms": observed_at_ms,
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
        first_snapshot_identity=None if not snapshots else snapshots[0].snapshot_identity,
        last_snapshot_identity=None if not snapshots else snapshots[-1].snapshot_identity,
        consumed_snapshot_count=len(snapshots),
        latest_snapshot_age_ms=None if latest is None else as_of_ms - latest.event_at_ms,
        source_quality=source_quality,
        status=LiquidityStructureStatus.UNRESOLVED,
        bid_levels=(),
        ask_levels=(),
        bid_appearance_notional_per_second=None,
        bid_cancellation_notional_per_second=None,
        ask_appearance_notional_per_second=None,
        ask_cancellation_notional_per_second=None,
        uncertainty_flags=flags,
    )


def _distance_to_mid_bps(price: Decimal, snapshot: OrderBookSnapshot) -> Decimal:
    mid = (snapshot.bids[0].price + snapshot.asks[0].price) / Decimal(2)
    return abs(price - mid) / mid * _BPS


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("cannot average an empty decimal series")
    return sum(values, start=Decimal(0)) / Decimal(len(values))


def _median(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("cannot take median of an empty decimal series")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)


def _context(
    snapshots: tuple[OrderBookSnapshot, ...],
) -> tuple[Exchange, MarketType, str]:
    first = snapshots[0]
    expected = (first.exchange, first.market_type, first.symbol)
    for snapshot in snapshots[1:]:
        actual = (snapshot.exchange, snapshot.market_type, snapshot.symbol)
        if actual != expected:
            raise ValueError("liquidity structure inputs must share one market context")
    return expected


def _reject_duplicate_identities(
    snapshots: tuple[OrderBookSnapshot, ...],
) -> None:
    identities = [item.snapshot_identity for item in snapshots]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate orderbook snapshot identity")


def _level_payload(level: LiquidityLevelEvidence) -> dict[str, object]:
    return {
        field: getattr(level, field)
        for field in level.__dataclass_fields__
    }


def _analysis_payload(
    analysis: LiquidityStructureAnalysis,
) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "ask_appearance_notional_per_second": analysis.ask_appearance_notional_per_second,
        "ask_cancellation_notional_per_second": analysis.ask_cancellation_notional_per_second,
        "ask_levels": [_level_payload(item) for item in analysis.ask_levels],
        "bid_appearance_notional_per_second": analysis.bid_appearance_notional_per_second,
        "bid_cancellation_notional_per_second": analysis.bid_cancellation_notional_per_second,
        "bid_levels": [_level_payload(item) for item in analysis.bid_levels],
        "consumed_snapshot_count": analysis.consumed_snapshot_count,
        "engine_version": analysis.engine_version,
        "exchange": analysis.exchange,
        "first_snapshot_identity": analysis.first_snapshot_identity,
        "last_snapshot_identity": analysis.last_snapshot_identity,
        "latest_snapshot_age_ms": analysis.latest_snapshot_age_ms,
        "market_type": analysis.market_type,
        "observed_at_ms": analysis.observed_at_ms,
        "source_quality": analysis.source_quality,
        "source_window_end_ms": analysis.source_window_end_ms,
        "source_window_start_ms": analysis.source_window_start_ms,
        "status": analysis.status,
        "symbol": analysis.symbol,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _require_finite(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be SHA256")
