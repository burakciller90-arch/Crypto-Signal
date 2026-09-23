"""PIT-safe temporal public trade flow; no prediction or trade authority.

Complements the accepted single-window order_flow_microstructure engine.
CVD here is window-local and never presented as exchange-global CVD.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from crypto_signal.data.microstructure import AggressorSide, PublicTradeObservation
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256

ENGINE_VERSION = "m3-temporal-order-flow-slice1/1"
FREEZE_SCHEMA_VERSION = "m3-temporal-order-flow-freeze-v1/1"
_ZERO = Decimal(0)
_THOUSAND = Decimal(1000)


class TemporalFlowStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class TemporalFlowQuality(StrEnum):
    GOOD = "good"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class TemporalFlowConfig:
    window_ms: int = 120_000
    bucket_ms: int = 15_000
    minimum_trades: int = 5
    max_trade_age_ms: int = 30_000
    max_trade_gap_ms: int = 30_000
    large_print_min_notional: Decimal = Decimal(10_000)

    def __post_init__(self) -> None:
        for label, number in (
            ("window_ms", self.window_ms),
            ("bucket_ms", self.bucket_ms),
            ("minimum_trades", self.minimum_trades),
            ("max_trade_age_ms", self.max_trade_age_ms),
            ("max_trade_gap_ms", self.max_trade_gap_ms),
        ):
            if number <= 0:
                raise ValueError(f"{label} must be positive")
        if self.bucket_ms > self.window_ms:
            raise ValueError("bucket_ms cannot exceed window_ms")
        if self.max_trade_age_ms > self.window_ms:
            raise ValueError("max_trade_age_ms cannot exceed window_ms")
        if self.max_trade_gap_ms > self.window_ms:
            raise ValueError("max_trade_gap_ms cannot exceed window_ms")
        value = self.large_print_min_notional
        if value.is_nan() or value.is_infinite() or value <= _ZERO:
            raise ValueError("large_print_min_notional must be positive and finite")

    @property
    def identity(self) -> str:
        return canonical_sha256(
            {
                "bucket_ms": self.bucket_ms,
                "large_print_min_notional": self.large_print_min_notional,
                "max_trade_age_ms": self.max_trade_age_ms,
                "max_trade_gap_ms": self.max_trade_gap_ms,
                "minimum_trades": self.minimum_trades,
                "window_ms": self.window_ms,
            }
        )


DEFAULT_TEMPORAL_FLOW_CONFIG = TemporalFlowConfig()


@dataclass(frozen=True, slots=True)
class TemporalFlowBucket:
    bucket_start_ms: int
    bucket_end_exclusive_ms: int
    first_trade_ms: int
    last_trade_ms: int
    buy_notional: Decimal
    sell_notional: Decimal
    delta_notional: Decimal
    cvd_notional: Decimal
    trade_count: int
    large_buy_count: int
    large_sell_count: int

    def __post_init__(self) -> None:
        if not (
            0 <= self.bucket_start_ms
            <= self.first_trade_ms
            <= self.last_trade_ms
            < self.bucket_end_exclusive_ms
        ):
            raise ValueError("bucket trade events outside bucket interval")
        if self.trade_count <= 0:
            raise ValueError("only nonempty buckets may be frozen")
        if min(self.large_buy_count, self.large_sell_count) < 0:
            raise ValueError("large trade counts must be non-negative")
        if self.large_buy_count + self.large_sell_count > self.trade_count:
            raise ValueError("large trade count exceeds eligible trades")
        for label, value in (
            ("buy_notional", self.buy_notional),
            ("sell_notional", self.sell_notional),
            ("delta_notional", self.delta_notional),
            ("cvd_notional", self.cvd_notional),
        ):
            _finite(value, label)
        if self.buy_notional < _ZERO or self.sell_notional < _ZERO:
            raise ValueError("bucket notional cannot be negative")
        if self.buy_notional + self.sell_notional <= _ZERO:
            raise ValueError("bucket has no positive notional")
        if self.delta_notional != self.buy_notional - self.sell_notional:
            raise ValueError("bucket delta mismatch")


@dataclass(frozen=True, slots=True)
class TemporalFlowMetrics:
    buy_notional: Decimal
    sell_notional: Decimal
    delta_notional: Decimal
    cvd_window_end_notional: Decimal
    taker_imbalance: Decimal
    eligible_trade_count: int
    excluded_trade_count: int
    large_buy_count: int
    large_sell_count: int
    trade_velocity_per_second: Decimal
    first_eligible_trade_price: Decimal
    last_eligible_trade_price: Decimal
    buckets: tuple[TemporalFlowBucket, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("buy_notional", self.buy_notional),
            ("sell_notional", self.sell_notional),
            ("delta_notional", self.delta_notional),
            ("cvd_window_end_notional", self.cvd_window_end_notional),
            ("taker_imbalance", self.taker_imbalance),
            ("trade_velocity_per_second", self.trade_velocity_per_second),
            ("first_eligible_trade_price", self.first_eligible_trade_price),
            ("last_eligible_trade_price", self.last_eligible_trade_price),
        ):
            _finite(value, label)
        if self.buy_notional < _ZERO or self.sell_notional < _ZERO:
            raise ValueError("flow notionals cannot be negative")
        if self.buy_notional + self.sell_notional <= _ZERO:
            raise ValueError("measured flow needs positive volume")
        if self.delta_notional != self.buy_notional - self.sell_notional:
            raise ValueError("aggregate delta mismatch")
        if self.cvd_window_end_notional != self.delta_notional:
            raise ValueError("window-local CVD end mismatch")
        if not Decimal(-1) <= self.taker_imbalance <= Decimal(1):
            raise ValueError("taker imbalance outside [-1,1]")
        if self.taker_imbalance != (
            self.delta_notional / (self.buy_notional + self.sell_notional)
        ):
            raise ValueError("taker imbalance calculation mismatch")
        if self.eligible_trade_count <= 0 or self.excluded_trade_count < 0:
            raise ValueError("invalid trade counts")
        if min(self.large_buy_count, self.large_sell_count) < 0:
            raise ValueError("large print counts must be non-negative")
        if self.trade_velocity_per_second <= _ZERO:
            raise ValueError("trade velocity must be positive")
        if (
            self.first_eligible_trade_price <= _ZERO
            or self.last_eligible_trade_price <= _ZERO
        ):
            raise ValueError("trade prices must be positive")
        if not self.buckets:
            raise ValueError("measured flow needs nonempty buckets")
        if sum(item.trade_count for item in self.buckets) != self.eligible_trade_count:
            raise ValueError("bucket eligible trade count mismatch")
        if sum((item.buy_notional for item in self.buckets), _ZERO) != self.buy_notional:
            raise ValueError("bucket buy notional mismatch")
        if sum((item.sell_notional for item in self.buckets), _ZERO) != self.sell_notional:
            raise ValueError("bucket sell notional mismatch")
        if self.buckets[-1].cvd_notional != self.cvd_window_end_notional:
            raise ValueError("bucket CVD end mismatch")


@dataclass(frozen=True, slots=True)
class TemporalFlowAnalysis:
    evidence_identity: str
    engine_version: str
    config_identity: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    as_of_ms: int
    observed_at_ms: int
    window_start_ms: int
    window_end_ms: int | None
    first_trade_identity: str | None
    last_trade_identity: str | None
    consumed_trade_count: int
    latest_eligible_trade_age_ms: int | None
    quality: TemporalFlowQuality
    status: TemporalFlowStatus
    metrics: TemporalFlowMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _sha(self.evidence_identity, "temporal flow evidence")
        _sha(self.config_identity, "temporal flow config")
        if self.engine_version != ENGINE_VERSION:
            raise ValueError("unsupported temporal flow engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("temporal flow symbol must be uppercase")
        if not 0 <= self.window_start_ms <= self.as_of_ms:
            raise ValueError("invalid temporal flow window")
        if not 0 <= self.observed_at_ms <= self.as_of_ms:
            raise ValueError("future temporal flow observation")
        if self.window_end_ms is not None and not (
            self.window_start_ms <= self.window_end_ms <= self.as_of_ms
        ):
            raise ValueError("invalid temporal flow window end")
        if self.consumed_trade_count < 0:
            raise ValueError("negative consumed trade count")
        if self.consumed_trade_count:
            if self.first_trade_identity is None or self.last_trade_identity is None:
                raise ValueError("consumed trades require boundary identities")
            _sha(self.first_trade_identity, "first trade")
            _sha(self.last_trade_identity, "last trade")
        elif self.first_trade_identity is not None or self.last_trade_identity is not None:
            raise ValueError("empty flow cannot carry trade identities")
        if (
            self.latest_eligible_trade_age_ms is not None
            and self.latest_eligible_trade_age_ms < 0
        ):
            raise ValueError("negative latest eligible trade age")
        if self.status is TemporalFlowStatus.MEASURED:
            if self.quality is not TemporalFlowQuality.GOOD or self.metrics is None:
                raise ValueError("measured temporal flow requires good measured metrics")
        else:
            if self.quality is TemporalFlowQuality.GOOD or self.metrics is not None:
                raise ValueError("unresolved temporal flow cannot claim measured metrics")
            if not self.uncertainty_flags:
                raise ValueError("unresolved temporal flow requires uncertainty")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("temporal flow evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class TemporalFlowEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: TemporalFlowAnalysis
    trades: tuple[PublicTradeObservation, ...]

    def __post_init__(self) -> None:
        _sha(self.freeze_identity, "temporal flow freeze")
        if self.schema_version != FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported temporal flow freeze schema")
        if len(self.trades) != self.analysis.consumed_trade_count:
            raise ValueError("temporal flow freeze trade count mismatch")
        for trade in self.trades:
            if (
                trade.exchange is not self.analysis.exchange
                or trade.market_type is not self.analysis.market_type
                or trade.symbol != self.analysis.symbol
            ):
                raise ValueError("temporal flow freeze market context mismatch")
            if max(
                trade.event_at_ms,
                trade.source_timestamp_ms,
                trade.ingested_at_ms,
            ) > self.analysis.as_of_ms:
                raise ValueError("temporal flow freeze contains future evidence")
            if trade.event_at_ms < self.analysis.window_start_ms:
                raise ValueError("temporal flow freeze contains out-of-window evidence")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "schema_version": FREEZE_SCHEMA_VERSION,
                "trade_identities": [item.trade_identity for item in self.trades],
            }
        )
        if expected != self.freeze_identity:
            raise ValueError("temporal flow freeze identity mismatch")


def analyze_temporal_order_flow(
    trades: Sequence[PublicTradeObservation],
    *,
    as_of_ms: int,
    config: TemporalFlowConfig = DEFAULT_TEMPORAL_FLOW_CONFIG,
) -> TemporalFlowAnalysis:
    return build_temporal_order_flow_freeze(
        trades, as_of_ms=as_of_ms, config=config
    ).analysis


def build_temporal_order_flow_freeze(
    trades: Sequence[PublicTradeObservation],
    *,
    as_of_ms: int,
    config: TemporalFlowConfig = DEFAULT_TEMPORAL_FLOW_CONFIG,
) -> TemporalFlowEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("temporal flow as_of_ms must be nonnegative")
    if not trades:
        raise ValueError("temporal flow requires at least one source trade")
    ordered = tuple(
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
    ids = [item.trade_identity for item in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate temporal flow trade identity")
    exchange, market_type, symbol = (
        ordered[0].exchange,
        ordered[0].market_type,
        ordered[0].symbol,
    )
    if any(
        (item.exchange, item.market_type, item.symbol)
        != (exchange, market_type, symbol)
        for item in ordered[1:]
    ):
        raise ValueError("mixed temporal flow market context")
    start = max(0, as_of_ms - config.window_ms)
    selected = tuple(
        item
        for item in ordered
        if start <= item.event_at_ms <= as_of_ms
        and item.source_timestamp_ms <= as_of_ms
        and item.ingested_at_ms <= as_of_ms
    )
    analysis = _analyze_selected(
        selected,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        as_of_ms=as_of_ms,
        window_start_ms=start,
        config=config,
    )
    return TemporalFlowEvidenceFreeze(
        freeze_identity=canonical_sha256(
            {
                "analysis_identity": analysis.evidence_identity,
                "schema_version": FREEZE_SCHEMA_VERSION,
                "trade_identities": [item.trade_identity for item in selected],
            }
        ),
        schema_version=FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        trades=selected,
    )


def _analyze_selected(
    selected: tuple[PublicTradeObservation, ...],
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    as_of_ms: int,
    window_start_ms: int,
    config: TemporalFlowConfig,
) -> TemporalFlowAnalysis:
    eligible = tuple(item for item in selected if item.book_eligible)
    excluded_count = len(selected) - len(eligible)
    flags: list[str] = ["window_local_cvd_only"]
    if excluded_count:
        flags.append("block_or_rpi_excluded_from_aggressive_flow")
    if not selected:
        flags.append("trade_tape_unavailable_at_as_of")
    if len(eligible) < config.minimum_trades:
        flags.append("insufficient_eligible_public_trades")
    latest = eligible[-1] if eligible else None
    if latest is not None and as_of_ms - latest.event_at_ms > config.max_trade_age_ms:
        flags.append("stale_latest_eligible_trade")
    if eligible and eligible[-1].event_at_ms <= eligible[0].event_at_ms:
        flags.append("insufficient_temporal_span")
    if any(
        later.event_at_ms - earlier.event_at_ms > config.max_trade_gap_ms
        for earlier, later in pairwise(eligible)
    ):
        flags.append("eligible_trade_gap_exceeds_limit")
    blocking = {
        "trade_tape_unavailable_at_as_of",
        "insufficient_eligible_public_trades",
        "stale_latest_eligible_trade",
        "insufficient_temporal_span",
        "eligible_trade_gap_exceeds_limit",
    }
    metrics = None
    quality = TemporalFlowQuality.GOOD
    status = TemporalFlowStatus.MEASURED
    if any(flag in blocking for flag in flags):
        status = TemporalFlowStatus.UNRESOLVED
        quality = (
            TemporalFlowQuality.UNAVAILABLE
            if not selected
            else TemporalFlowQuality.DEGRADED
        )
    else:
        metrics = _derive_metrics(eligible, excluded_count, config)
        flags.append("large_prints_are_threshold_candidates_not_actor_attribution")
    payload: dict[str, object] = {
        "as_of_ms": as_of_ms,
        "config_identity": config.identity,
        "consumed_trade_count": len(selected),
        "engine_version": ENGINE_VERSION,
        "exchange": exchange,
        "first_trade_identity": (
            None if not selected else selected[0].trade_identity
        ),
        "last_trade_identity": (
            None if not selected else selected[-1].trade_identity
        ),
        "latest_eligible_trade_age_ms": (
            None if latest is None else as_of_ms - latest.event_at_ms
        ),
        "market_type": market_type,
        "metrics": None if metrics is None else _metrics_payload(metrics),
        "observed_at_ms": max(
            (item.ingested_at_ms for item in selected), default=0
        ),
        "quality": quality,
        "status": status,
        "symbol": symbol,
        "uncertainty_flags": tuple(flags),
        "window_end_ms": None if not selected else selected[-1].event_at_ms,
        "window_start_ms": window_start_ms,
    }
    return TemporalFlowAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=ENGINE_VERSION,
        config_identity=config.identity,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        as_of_ms=as_of_ms,
        observed_at_ms=max((item.ingested_at_ms for item in selected), default=0),
        window_start_ms=window_start_ms,
        window_end_ms=None if not selected else selected[-1].event_at_ms,
        first_trade_identity=None if not selected else selected[0].trade_identity,
        last_trade_identity=None if not selected else selected[-1].trade_identity,
        consumed_trade_count=len(selected),
        latest_eligible_trade_age_ms=(
            None if latest is None else as_of_ms - latest.event_at_ms
        ),
        quality=quality,
        status=status,
        metrics=metrics,
        uncertainty_flags=tuple(flags),
    )


def _derive_metrics(
    eligible: tuple[PublicTradeObservation, ...],
    excluded_count: int,
    config: TemporalFlowConfig,
) -> TemporalFlowMetrics:
    groups: dict[int, list[PublicTradeObservation]] = {}
    for trade in eligible:
        key = trade.event_at_ms // config.bucket_ms * config.bucket_ms
        groups.setdefault(key, []).append(trade)
    cvd = _ZERO
    buckets: list[TemporalFlowBucket] = []
    for start in sorted(groups):
        group = groups[start]
        buy = sum(
            (item.notional for item in group if item.aggressor_side is AggressorSide.BUY),
            _ZERO,
        )
        sell = sum(
            (item.notional for item in group if item.aggressor_side is AggressorSide.SELL),
            _ZERO,
        )
        delta = buy - sell
        cvd += delta
        buckets.append(
            TemporalFlowBucket(
                bucket_start_ms=start,
                bucket_end_exclusive_ms=start + config.bucket_ms,
                first_trade_ms=group[0].event_at_ms,
                last_trade_ms=group[-1].event_at_ms,
                buy_notional=buy,
                sell_notional=sell,
                delta_notional=delta,
                cvd_notional=cvd,
                trade_count=len(group),
                large_buy_count=sum(
                    item.aggressor_side is AggressorSide.BUY
                    and item.notional >= config.large_print_min_notional
                    for item in group
                ),
                large_sell_count=sum(
                    item.aggressor_side is AggressorSide.SELL
                    and item.notional >= config.large_print_min_notional
                    for item in group
                ),
            )
        )
    total_buy = sum((item.buy_notional for item in buckets), _ZERO)
    total_sell = sum((item.sell_notional for item in buckets), _ZERO)
    duration_seconds = (
        Decimal(eligible[-1].event_at_ms - eligible[0].event_at_ms) / _THOUSAND
    )
    return TemporalFlowMetrics(
        buy_notional=total_buy,
        sell_notional=total_sell,
        delta_notional=total_buy - total_sell,
        cvd_window_end_notional=cvd,
        taker_imbalance=(total_buy - total_sell) / (total_buy + total_sell),
        eligible_trade_count=len(eligible),
        excluded_trade_count=excluded_count,
        large_buy_count=sum(item.large_buy_count for item in buckets),
        large_sell_count=sum(item.large_sell_count for item in buckets),
        trade_velocity_per_second=Decimal(len(eligible)) / duration_seconds,
        first_eligible_trade_price=eligible[0].price,
        last_eligible_trade_price=eligible[-1].price,
        buckets=tuple(buckets),
    )


def _bucket_payload(item: TemporalFlowBucket) -> dict[str, object]:
    return {
        field: getattr(item, field)
        for field in item.__dataclass_fields__
    }


def _metrics_payload(metrics: TemporalFlowMetrics) -> dict[str, object]:
    return {
        field: (
            [_bucket_payload(item) for item in metrics.buckets]
            if field == "buckets"
            else getattr(metrics, field)
        )
        for field in metrics.__dataclass_fields__
    }


def _analysis_payload(analysis: TemporalFlowAnalysis) -> dict[str, object]:
    return {
        field: (
            None
            if field == "metrics" and analysis.metrics is None
            else _metrics_payload(analysis.metrics)
            if field == "metrics" and analysis.metrics is not None
            else getattr(analysis, field)
        )
        for field in analysis.__dataclass_fields__
        if field != "evidence_identity"
    }


def _finite(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be SHA256")
