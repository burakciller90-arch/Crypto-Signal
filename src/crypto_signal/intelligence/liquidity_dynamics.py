from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.microstructure import OrderBookSnapshot
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256

LIQUIDITY_DYNAMICS_ENGINE_VERSION = "liquidity-dynamics-v1/1"
LIQUIDITY_DYNAMICS_FREEZE_SCHEMA_VERSION = "liquidity-dynamics-freeze-v1/1"
_ONE_SECOND_MS = Decimal(1000)


class LiquidityDynamicsStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class LiquiditySourceQuality(StrEnum):
    GOOD = "good"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class LiquidityDynamicsConfig:
    depth_levels: int = 10
    lookback_ms: int = 120_000
    minimum_snapshots: int = 3
    max_snapshot_age_ms: int = 30_000
    max_snapshot_gap_ms: int = 30_000

    def __post_init__(self) -> None:
        if self.depth_levels <= 0:
            raise ValueError("liquidity depth_levels must be positive")
        if self.lookback_ms <= 0:
            raise ValueError("liquidity lookback_ms must be positive")
        if self.minimum_snapshots < 2:
            raise ValueError("liquidity minimum_snapshots must be at least 2")
        if self.max_snapshot_age_ms <= 0:
            raise ValueError("liquidity max_snapshot_age_ms must be positive")
        if self.max_snapshot_gap_ms <= 0:
            raise ValueError("liquidity max_snapshot_gap_ms must be positive")


DEFAULT_LIQUIDITY_DYNAMICS_CONFIG = LiquidityDynamicsConfig()


@dataclass(frozen=True, slots=True)
class LiquidityDynamicsMetrics:
    depth_levels: int
    snapshot_count: int
    transition_count: int
    duration_ms: int
    first_bid_depth_notional: Decimal
    last_bid_depth_notional: Decimal
    first_ask_depth_notional: Decimal
    last_ask_depth_notional: Decimal
    gross_bid_added_notional: Decimal
    gross_bid_removed_notional: Decimal
    gross_ask_added_notional: Decimal
    gross_ask_removed_notional: Decimal
    net_bid_depth_change_notional: Decimal
    net_ask_depth_change_notional: Decimal
    bid_added_notional_per_second: Decimal
    bid_removed_notional_per_second: Decimal
    ask_added_notional_per_second: Decimal
    ask_removed_notional_per_second: Decimal
    bid_depth_change_notional_per_second: Decimal
    ask_depth_change_notional_per_second: Decimal
    best_bid_depletion_notional: Decimal
    best_bid_replenishment_notional: Decimal
    best_ask_depletion_notional: Decimal
    best_ask_replenishment_notional: Decimal
    best_bid_price_persistence_fraction: Decimal
    best_ask_price_persistence_fraction: Decimal

    def __post_init__(self) -> None:
        if self.depth_levels <= 0:
            raise ValueError("liquidity metrics depth_levels must be positive")
        if self.snapshot_count < 2:
            raise ValueError("liquidity metrics require at least two snapshots")
        if self.transition_count != self.snapshot_count - 1:
            raise ValueError("liquidity transition count mismatch")
        if self.duration_ms <= 0:
            raise ValueError("liquidity metrics require positive duration")
        for label, value in (
            ("first_bid_depth_notional", self.first_bid_depth_notional),
            ("last_bid_depth_notional", self.last_bid_depth_notional),
            ("first_ask_depth_notional", self.first_ask_depth_notional),
            ("last_ask_depth_notional", self.last_ask_depth_notional),
            ("gross_bid_added_notional", self.gross_bid_added_notional),
            ("gross_bid_removed_notional", self.gross_bid_removed_notional),
            ("gross_ask_added_notional", self.gross_ask_added_notional),
            ("gross_ask_removed_notional", self.gross_ask_removed_notional),
            ("bid_added_notional_per_second", self.bid_added_notional_per_second),
            ("bid_removed_notional_per_second", self.bid_removed_notional_per_second),
            ("ask_added_notional_per_second", self.ask_added_notional_per_second),
            ("ask_removed_notional_per_second", self.ask_removed_notional_per_second),
            ("best_bid_depletion_notional", self.best_bid_depletion_notional),
            ("best_bid_replenishment_notional", self.best_bid_replenishment_notional),
            ("best_ask_depletion_notional", self.best_ask_depletion_notional),
            ("best_ask_replenishment_notional", self.best_ask_replenishment_notional),
        ):
            _require_finite(value, label)
            if value < Decimal(0):
                raise ValueError(f"{label} must be non-negative")
        for label, value in (
            ("net_bid_depth_change_notional", self.net_bid_depth_change_notional),
            ("net_ask_depth_change_notional", self.net_ask_depth_change_notional),
            (
                "bid_depth_change_notional_per_second",
                self.bid_depth_change_notional_per_second,
            ),
            (
                "ask_depth_change_notional_per_second",
                self.ask_depth_change_notional_per_second,
            ),
        ):
            _require_finite(value, label)
        for label, value in (
            (
                "best_bid_price_persistence_fraction",
                self.best_bid_price_persistence_fraction,
            ),
            (
                "best_ask_price_persistence_fraction",
                self.best_ask_price_persistence_fraction,
            ),
        ):
            _require_finite(value, label)
            if not Decimal(0) <= value <= Decimal(1):
                raise ValueError(f"{label} must be inside [0,1]")


@dataclass(frozen=True, slots=True)
class LiquidityDynamicsAnalysis:
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
    status: LiquidityDynamicsStatus
    metrics: LiquidityDynamicsMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "liquidity evidence identity")
        if self.engine_version != LIQUIDITY_DYNAMICS_ENGINE_VERSION:
            raise ValueError("unsupported liquidity dynamics engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("liquidity dynamics symbol must be uppercase")
        if min(self.as_of_ms, self.observed_at_ms, self.source_window_start_ms) < 0:
            raise ValueError("liquidity analysis timestamps must be non-negative")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("liquidity analysis cannot observe future evidence")
        if self.source_window_start_ms > self.as_of_ms:
            raise ValueError("liquidity source window starts after as-of")
        if self.source_window_end_ms is not None:
            if not self.source_window_start_ms <= self.source_window_end_ms <= self.as_of_ms:
                raise ValueError("liquidity source window end outside PIT bounds")
        if self.consumed_snapshot_count < 0:
            raise ValueError("liquidity snapshot count cannot be negative")
        if self.latest_snapshot_age_ms is not None and self.latest_snapshot_age_ms < 0:
            raise ValueError("liquidity latest snapshot age cannot be negative")
        if self.consumed_snapshot_count == 0:
            if self.first_snapshot_identity is not None or self.last_snapshot_identity is not None:
                raise ValueError("empty liquidity window cannot carry snapshot identities")
        else:
            if self.first_snapshot_identity is None or self.last_snapshot_identity is None:
                raise ValueError("non-empty liquidity window requires boundary identities")
            _require_sha256(self.first_snapshot_identity, "first liquidity snapshot identity")
            _require_sha256(self.last_snapshot_identity, "last liquidity snapshot identity")
        if self.status is LiquidityDynamicsStatus.MEASURED:
            if self.metrics is None:
                raise ValueError("measured liquidity dynamics require metrics")
            if self.source_quality is not LiquiditySourceQuality.GOOD:
                raise ValueError("measured liquidity dynamics require good source quality")
        else:
            if self.metrics is not None:
                raise ValueError("unresolved liquidity dynamics cannot carry metrics")
            if not self.uncertainty_flags:
                raise ValueError("unresolved liquidity dynamics require uncertainty")
            if self.source_quality is LiquiditySourceQuality.GOOD:
                raise ValueError("unresolved liquidity dynamics cannot claim good quality")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("liquidity evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class LiquidityDynamicsEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: LiquidityDynamicsAnalysis
    snapshots: tuple[OrderBookSnapshot, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "liquidity freeze identity")
        if self.schema_version != LIQUIDITY_DYNAMICS_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported liquidity freeze schema")
        if self.analysis.consumed_snapshot_count != len(self.snapshots):
            raise ValueError("liquidity freeze snapshot count mismatch")
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
                raise ValueError("liquidity freeze contains future evidence")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "schema_version": LIQUIDITY_DYNAMICS_FREEZE_SCHEMA_VERSION,
                "snapshot_identities": [
                    snapshot.snapshot_identity for snapshot in self.snapshots
                ],
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("liquidity freeze identity mismatch")


def analyze_liquidity_dynamics(
    orderbooks: Sequence[OrderBookSnapshot],
    *,
    as_of_ms: int,
    config: LiquidityDynamicsConfig = DEFAULT_LIQUIDITY_DYNAMICS_CONFIG,
) -> LiquidityDynamicsAnalysis:
    return build_liquidity_dynamics_evidence_freeze(
        orderbooks,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_liquidity_dynamics_evidence_freeze(
    orderbooks: Sequence[OrderBookSnapshot],
    *,
    as_of_ms: int,
    config: LiquidityDynamicsConfig = DEFAULT_LIQUIDITY_DYNAMICS_CONFIG,
) -> LiquidityDynamicsEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("liquidity as_of_ms must be non-negative")
    if not orderbooks:
        raise ValueError("liquidity dynamics require at least one orderbook snapshot")

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
            "schema_version": LIQUIDITY_DYNAMICS_FREEZE_SCHEMA_VERSION,
            "snapshot_identities": [item.snapshot_identity for item in selected],
        }
    )
    return LiquidityDynamicsEvidenceFreeze(
        freeze_identity=freeze_identity,
        schema_version=LIQUIDITY_DYNAMICS_FREEZE_SCHEMA_VERSION,
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
    config: LiquidityDynamicsConfig,
) -> LiquidityDynamicsAnalysis:
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
        for left, right in zip(snapshots, snapshots[1:], strict=False)
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

    metrics = _derive_metrics(snapshots=snapshots, depth_levels=config.depth_levels)
    payload = {
        "as_of_ms": as_of_ms,
        "consumed_snapshot_count": len(snapshots),
        "engine_version": LIQUIDITY_DYNAMICS_ENGINE_VERSION,
        "exchange": exchange,
        "first_snapshot_identity": snapshots[0].snapshot_identity,
        "last_snapshot_identity": snapshots[-1].snapshot_identity,
        "latest_snapshot_age_ms": latest_age,
        "market_type": market_type,
        "metrics": _metrics_payload(metrics),
        "observed_at_ms": max(item.ingested_at_ms for item in snapshots),
        "source_quality": LiquiditySourceQuality.GOOD,
        "source_window_end_ms": snapshots[-1].event_at_ms,
        "source_window_start_ms": source_window_start_ms,
        "status": LiquidityDynamicsStatus.MEASURED,
        "symbol": symbol,
        "uncertainty_flags": (),
    }
    return LiquidityDynamicsAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=LIQUIDITY_DYNAMICS_ENGINE_VERSION,
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
        status=LiquidityDynamicsStatus.MEASURED,
        metrics=metrics,
        uncertainty_flags=(),
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
) -> LiquidityDynamicsAnalysis:
    observed_at_ms = max((item.ingested_at_ms for item in snapshots), default=0)
    latest = snapshots[-1] if snapshots else None
    payload = {
        "as_of_ms": as_of_ms,
        "consumed_snapshot_count": len(snapshots),
        "engine_version": LIQUIDITY_DYNAMICS_ENGINE_VERSION,
        "exchange": exchange,
        "first_snapshot_identity": (
            None if not snapshots else snapshots[0].snapshot_identity
        ),
        "last_snapshot_identity": (
            None if latest is None else latest.snapshot_identity
        ),
        "latest_snapshot_age_ms": (
            None if latest is None else as_of_ms - latest.event_at_ms
        ),
        "market_type": market_type,
        "metrics": None,
        "observed_at_ms": observed_at_ms,
        "source_quality": source_quality,
        "source_window_end_ms": None if latest is None else latest.event_at_ms,
        "source_window_start_ms": source_window_start_ms,
        "status": LiquidityDynamicsStatus.UNRESOLVED,
        "symbol": symbol,
        "uncertainty_flags": flags,
    }
    return LiquidityDynamicsAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=LIQUIDITY_DYNAMICS_ENGINE_VERSION,
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
        status=LiquidityDynamicsStatus.UNRESOLVED,
        metrics=None,
        uncertainty_flags=flags,
    )


def _derive_metrics(
    *,
    snapshots: tuple[OrderBookSnapshot, ...],
    depth_levels: int,
) -> LiquidityDynamicsMetrics:
    first = snapshots[0]
    last = snapshots[-1]
    duration_ms = last.event_at_ms - first.event_at_ms
    if duration_ms <= 0:
        raise ValueError("liquidity metrics require chronological snapshots")

    first_bid_depth = _depth_notional(first.bids, depth_levels)
    last_bid_depth = _depth_notional(last.bids, depth_levels)
    first_ask_depth = _depth_notional(first.asks, depth_levels)
    last_ask_depth = _depth_notional(last.asks, depth_levels)

    gross_bid_added = Decimal(0)
    gross_bid_removed = Decimal(0)
    gross_ask_added = Decimal(0)
    gross_ask_removed = Decimal(0)
    best_bid_depletion = Decimal(0)
    best_bid_replenishment = Decimal(0)
    best_ask_depletion = Decimal(0)
    best_ask_replenishment = Decimal(0)
    bid_persistent = 0
    ask_persistent = 0

    for previous, current in zip(snapshots, snapshots[1:], strict=False):
        bid_added, bid_removed = _visible_depth_change(
            previous.bids,
            current.bids,
            depth_levels,
        )
        ask_added, ask_removed = _visible_depth_change(
            previous.asks,
            current.asks,
            depth_levels,
        )
        gross_bid_added += bid_added
        gross_bid_removed += bid_removed
        gross_ask_added += ask_added
        gross_ask_removed += ask_removed

        bid_depletion, bid_replenishment = _best_level_change(
            previous.bids,
            current.bids,
            depth_levels,
        )
        ask_depletion, ask_replenishment = _best_level_change(
            previous.asks,
            current.asks,
            depth_levels,
        )
        best_bid_depletion += bid_depletion
        best_bid_replenishment += bid_replenishment
        best_ask_depletion += ask_depletion
        best_ask_replenishment += ask_replenishment
        bid_persistent += previous.bids[0].price == current.bids[0].price
        ask_persistent += previous.asks[0].price == current.asks[0].price

    duration_seconds = Decimal(duration_ms) / _ONE_SECOND_MS
    transition_count = len(snapshots) - 1
    transition_denominator = Decimal(transition_count)

    return LiquidityDynamicsMetrics(
        depth_levels=depth_levels,
        snapshot_count=len(snapshots),
        transition_count=transition_count,
        duration_ms=duration_ms,
        first_bid_depth_notional=first_bid_depth,
        last_bid_depth_notional=last_bid_depth,
        first_ask_depth_notional=first_ask_depth,
        last_ask_depth_notional=last_ask_depth,
        gross_bid_added_notional=gross_bid_added,
        gross_bid_removed_notional=gross_bid_removed,
        gross_ask_added_notional=gross_ask_added,
        gross_ask_removed_notional=gross_ask_removed,
        net_bid_depth_change_notional=last_bid_depth - first_bid_depth,
        net_ask_depth_change_notional=last_ask_depth - first_ask_depth,
        bid_added_notional_per_second=gross_bid_added / duration_seconds,
        bid_removed_notional_per_second=gross_bid_removed / duration_seconds,
        ask_added_notional_per_second=gross_ask_added / duration_seconds,
        ask_removed_notional_per_second=gross_ask_removed / duration_seconds,
        bid_depth_change_notional_per_second=(
            last_bid_depth - first_bid_depth
        )
        / duration_seconds,
        ask_depth_change_notional_per_second=(
            last_ask_depth - first_ask_depth
        )
        / duration_seconds,
        best_bid_depletion_notional=best_bid_depletion,
        best_bid_replenishment_notional=best_bid_replenishment,
        best_ask_depletion_notional=best_ask_depletion,
        best_ask_replenishment_notional=best_ask_replenishment,
        best_bid_price_persistence_fraction=(
            Decimal(bid_persistent) / transition_denominator
        ),
        best_ask_price_persistence_fraction=(
            Decimal(ask_persistent) / transition_denominator
        ),
    )


def _depth_notional(
    levels: Sequence[object],
    depth_levels: int,
) -> Decimal:
    return sum(
        (getattr(level, "notional") for level in levels[:depth_levels]),
        start=Decimal(0),
    )


def _visible_depth_change(
    previous_levels: Sequence[object],
    current_levels: Sequence[object],
    depth_levels: int,
) -> tuple[Decimal, Decimal]:
    previous = {
        getattr(level, "price"): getattr(level, "notional")
        for level in previous_levels[:depth_levels]
    }
    current = {
        getattr(level, "price"): getattr(level, "notional")
        for level in current_levels[:depth_levels]
    }
    added = Decimal(0)
    removed = Decimal(0)
    for price in previous.keys() | current.keys():
        delta = current.get(price, Decimal(0)) - previous.get(price, Decimal(0))
        if delta > 0:
            added += delta
        elif delta < 0:
            removed -= delta
    return added, removed


def _best_level_change(
    previous_levels: Sequence[object],
    current_levels: Sequence[object],
    depth_levels: int,
) -> tuple[Decimal, Decimal]:
    previous_best = previous_levels[0]
    previous_price = getattr(previous_best, "price")
    previous_notional = getattr(previous_best, "notional")
    current = {
        getattr(level, "price"): getattr(level, "notional")
        for level in current_levels[:depth_levels]
    }
    delta = current.get(previous_price, Decimal(0)) - previous_notional
    if delta < 0:
        return -delta, Decimal(0)
    if delta > 0:
        return Decimal(0), delta
    return Decimal(0), Decimal(0)


def _context(
    snapshots: tuple[OrderBookSnapshot, ...],
) -> tuple[Exchange, MarketType, str]:
    first = snapshots[0]
    expected = (first.exchange, first.market_type, first.symbol)
    for snapshot in snapshots[1:]:
        actual = (snapshot.exchange, snapshot.market_type, snapshot.symbol)
        if actual != expected:
            raise ValueError("liquidity dynamics inputs must share one market context")
    return expected


def _reject_duplicate_identities(
    snapshots: tuple[OrderBookSnapshot, ...],
) -> None:
    identities = [item.snapshot_identity for item in snapshots]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate orderbook snapshot identity")


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
        raise ValueError("liquidity freeze context mismatch")


def _metrics_payload(metrics: LiquidityDynamicsMetrics) -> dict[str, object]:
    return {
        field: getattr(metrics, field)
        for field in metrics.__dataclass_fields__
    }


def _analysis_payload(
    analysis: LiquidityDynamicsAnalysis,
) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
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
