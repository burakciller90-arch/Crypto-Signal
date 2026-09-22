from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.derivatives import DerivativesObservation
from crypto_signal.data.liquidations import (
    LiquidatedPositionSide,
    LiquidationFeedCoverage,
    LiquidationObservation,
)
from crypto_signal.data.models import Exchange
from crypto_signal.ledger.serialization import canonical_sha256

LIQUIDATION_HEATMAP_ENGINE_VERSION = "liquidation-heatmap-v2-slice4/1"
LIQUIDATION_HEATMAP_FREEZE_SCHEMA_VERSION = "liquidation-heatmap-freeze-v1/1"
_BPS = Decimal(10000)


class LiquidationHeatmapStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class LiquidationSourceQuality(StrEnum):
    GOOD = "good"
    DEGRADED = "degraded"


class ObservedLiquidationState(StrEnum):
    OBSERVED = "observed"
    NONE_OBSERVED = "none_observed"
    UNAVAILABLE = "unavailable"


class LiquidationEstimationStatus(StrEnum):
    NOT_ESTIMATED = "not_estimated"


@dataclass(frozen=True, slots=True)
class LiquidationHeatmapConfig:
    lookback_ms: int = 15 * 60_000
    max_mark_age_ms: int = 60_000
    bin_width_bps: Decimal = Decimal(25)
    minimum_cluster_events: int = 2
    minimum_cluster_notional_share: Decimal = Decimal("0.20")

    def __post_init__(self) -> None:
        for label, int_value in (
            ("lookback_ms", self.lookback_ms),
            ("max_mark_age_ms", self.max_mark_age_ms),
            ("minimum_cluster_events", self.minimum_cluster_events),
        ):
            if int_value <= 0:
                raise ValueError(f"{label} must be positive")
        if (
            self.bin_width_bps.is_nan()
            or self.bin_width_bps.is_infinite()
            or self.bin_width_bps <= Decimal(0)
        ):
            raise ValueError("bin_width_bps must be a positive finite Decimal")
        if (
            self.minimum_cluster_notional_share.is_nan()
            or self.minimum_cluster_notional_share.is_infinite()
            or not Decimal(0) < self.minimum_cluster_notional_share <= Decimal(1)
        ):
            raise ValueError(
                "minimum_cluster_notional_share must be inside (0,1]"
            )


DEFAULT_LIQUIDATION_HEATMAP_CONFIG = LiquidationHeatmapConfig()


@dataclass(frozen=True, slots=True)
class ObservedLiquidationBin:
    lower_distance_bps: Decimal
    upper_distance_bps: Decimal
    event_count: int
    long_liquidation_count: int
    short_liquidation_count: int
    bankruptcy_notional: Decimal
    notional_share: Decimal
    minimum_bankruptcy_price: Decimal
    maximum_bankruptcy_price: Decimal
    observed_cluster: bool

    def __post_init__(self) -> None:
        for label, value in (
            ("lower_distance_bps", self.lower_distance_bps),
            ("upper_distance_bps", self.upper_distance_bps),
            ("bankruptcy_notional", self.bankruptcy_notional),
            ("notional_share", self.notional_share),
            ("minimum_bankruptcy_price", self.minimum_bankruptcy_price),
            ("maximum_bankruptcy_price", self.maximum_bankruptcy_price),
        ):
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
        if self.upper_distance_bps <= self.lower_distance_bps:
            raise ValueError("liquidation heatmap bin bounds invalid")
        if self.event_count <= 0:
            raise ValueError("liquidation heatmap bin requires events")
        if min(self.long_liquidation_count, self.short_liquidation_count) < 0:
            raise ValueError("liquidation heatmap side counts cannot be negative")
        if (
            self.long_liquidation_count + self.short_liquidation_count
            != self.event_count
        ):
            raise ValueError("liquidation heatmap side-count decomposition mismatch")
        if self.bankruptcy_notional <= Decimal(0):
            raise ValueError("liquidation heatmap bin notional must be positive")
        if not Decimal(0) < self.notional_share <= Decimal(1):
            raise ValueError("liquidation heatmap notional_share outside (0,1]")
        if (
            self.minimum_bankruptcy_price <= Decimal(0)
            or self.maximum_bankruptcy_price < self.minimum_bankruptcy_price
        ):
            raise ValueError("liquidation heatmap price bounds invalid")


@dataclass(frozen=True, slots=True)
class LiquidationHeatmapAnalysis:
    evidence_identity: str
    engine_version: str
    exchange: Exchange
    symbol: str
    as_of_ms: int
    source_window_start_ms: int
    source_window_end_ms: int | None
    coverage_identity: str | None
    mark_observation_identity: str | None
    reference_mark_price: Decimal | None
    latest_mark_age_ms: int | None
    consumed_event_count: int
    first_event_identity: str | None
    last_event_identity: str | None
    total_bankruptcy_notional: Decimal | None
    long_liquidation_notional: Decimal | None
    short_liquidation_notional: Decimal | None
    source_quality: LiquidationSourceQuality
    status: LiquidationHeatmapStatus
    observed_state: ObservedLiquidationState
    bins: tuple[ObservedLiquidationBin, ...]
    observed_cluster_count: int
    estimated_leverage_concentration_status: LiquidationEstimationStatus
    liquidation_risk_zone_status: LiquidationEstimationStatus
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "liquidation heatmap evidence identity")
        if self.engine_version != LIQUIDATION_HEATMAP_ENGINE_VERSION:
            raise ValueError("unsupported liquidation heatmap engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("liquidation heatmap symbol must be uppercase")
        if min(self.as_of_ms, self.source_window_start_ms) < 0:
            raise ValueError("liquidation heatmap timestamps cannot be negative")
        if self.source_window_start_ms > self.as_of_ms:
            raise ValueError("liquidation heatmap window begins after as-of")
        if (
            self.source_window_end_ms is not None
            and not self.source_window_start_ms
            <= self.source_window_end_ms
            <= self.as_of_ms
        ):
            raise ValueError("liquidation heatmap window end outside PIT bounds")
        if self.consumed_event_count < 0 or self.observed_cluster_count < 0:
            raise ValueError("liquidation heatmap counts cannot be negative")
        _validate_event_identity_pair(
            self.consumed_event_count,
            self.first_event_identity,
            self.last_event_identity,
        )
        if self.latest_mark_age_ms is not None and self.latest_mark_age_ms < 0:
            raise ValueError("liquidation mark age cannot be negative")
        if self.status is LiquidationHeatmapStatus.MEASURED:
            if self.source_quality is not LiquidationSourceQuality.GOOD:
                raise ValueError("measured liquidation heatmap requires good quality")
            if self.coverage_identity is None or self.mark_observation_identity is None:
                raise ValueError("measured liquidation heatmap requires source identities")
            _require_sha256(self.coverage_identity, "liquidation coverage identity")
            _require_sha256(
                self.mark_observation_identity,
                "liquidation mark observation identity",
            )
            if self.reference_mark_price is None or self.reference_mark_price <= Decimal(0):
                raise ValueError("measured liquidation heatmap requires mark price")
            if self.total_bankruptcy_notional is None:
                raise ValueError("measured liquidation heatmap requires total notional")
            if self.long_liquidation_notional is None or self.short_liquidation_notional is None:
                raise ValueError("measured liquidation heatmap requires side notional")
            if self.observed_state is ObservedLiquidationState.UNAVAILABLE:
                raise ValueError("measured liquidation heatmap cannot be unavailable")
            if self.observed_state is ObservedLiquidationState.NONE_OBSERVED:
                if self.consumed_event_count != 0 or self.bins:
                    raise ValueError("none-observed heatmap cannot carry events/bins")
            if self.observed_state is ObservedLiquidationState.OBSERVED:
                if self.consumed_event_count <= 0 or not self.bins:
                    raise ValueError("observed heatmap requires events and bins")
        else:
            if self.source_quality is LiquidationSourceQuality.GOOD:
                raise ValueError("unresolved liquidation heatmap cannot claim good quality")
            if self.observed_state is not ObservedLiquidationState.UNAVAILABLE:
                raise ValueError("unresolved liquidation heatmap must be unavailable")
            if self.bins:
                raise ValueError("unresolved liquidation heatmap cannot publish bins")
            if not self.uncertainty_flags:
                raise ValueError("unresolved liquidation heatmap requires uncertainty")

        if (
            self.estimated_leverage_concentration_status
            is not LiquidationEstimationStatus.NOT_ESTIMATED
            or self.liquidation_risk_zone_status
            is not LiquidationEstimationStatus.NOT_ESTIMATED
        ):
            raise ValueError("Slice 4 must not estimate future liquidation risk")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("liquidation heatmap evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class LiquidationHeatmapEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: LiquidationHeatmapAnalysis
    coverage: LiquidationFeedCoverage
    mark_reference: DerivativesObservation
    events: tuple[LiquidationObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "liquidation heatmap freeze identity")
        if self.schema_version != LIQUIDATION_HEATMAP_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported liquidation heatmap freeze schema")
        if self.analysis.consumed_event_count != len(self.events):
            raise ValueError("liquidation heatmap freeze event count mismatch")
        for event in self.events:
            if max(
                event.event_at_ms,
                event.source_timestamp_ms,
                event.ingested_at_ms,
            ) > self.analysis.as_of_ms:
                raise ValueError("liquidation heatmap freeze contains future event")
        if max(
            self.mark_reference.event_at_ms,
            self.mark_reference.source_timestamp_ms,
            self.mark_reference.ingested_at_ms,
        ) > self.analysis.as_of_ms:
            raise ValueError("liquidation heatmap freeze contains future mark reference")
        if self.coverage.observed_at_ms > self.analysis.as_of_ms:
            raise ValueError("liquidation heatmap freeze contains future coverage")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "coverage_identity": self.coverage.coverage_identity,
                "event_identities": [item.liquidation_identity for item in self.events],
                "mark_observation_identity": self.mark_reference.observation_identity,
                "schema_version": LIQUIDATION_HEATMAP_FREEZE_SCHEMA_VERSION,
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("liquidation heatmap freeze identity mismatch")


def analyze_liquidation_heatmap(
    events: Sequence[LiquidationObservation],
    *,
    coverage: LiquidationFeedCoverage,
    mark_reference: DerivativesObservation,
    as_of_ms: int,
    config: LiquidationHeatmapConfig = DEFAULT_LIQUIDATION_HEATMAP_CONFIG,
) -> LiquidationHeatmapAnalysis:
    return build_liquidation_heatmap_evidence_freeze(
        events,
        coverage=coverage,
        mark_reference=mark_reference,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_liquidation_heatmap_evidence_freeze(
    events: Sequence[LiquidationObservation],
    *,
    coverage: LiquidationFeedCoverage,
    mark_reference: DerivativesObservation,
    as_of_ms: int,
    config: LiquidationHeatmapConfig = DEFAULT_LIQUIDATION_HEATMAP_CONFIG,
) -> LiquidationHeatmapEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("liquidation heatmap as_of_ms must be non-negative")
    _require_shared_context(events, coverage, mark_reference)

    ordered = tuple(
        sorted(
            events,
            key=lambda item: (
                item.event_at_ms,
                item.source_timestamp_ms,
                item.source_row_index,
                item.liquidation_identity,
            ),
        )
    )
    _reject_duplicate_event_identities(ordered)

    safe = tuple(
        item
        for item in ordered
        if max(
            item.event_at_ms,
            item.source_timestamp_ms,
            item.ingested_at_ms,
        )
        <= as_of_ms
    )
    window_start = max(0, as_of_ms - config.lookback_ms)
    selected = tuple(item for item in safe if item.event_at_ms >= window_start)

    analysis = _analyze_selected(
        selected,
        coverage=coverage,
        mark_reference=mark_reference,
        as_of_ms=as_of_ms,
        source_window_start_ms=window_start,
        config=config,
    )
    freeze_identity = canonical_sha256(
        {
            "analysis_identity": analysis.evidence_identity,
            "coverage_identity": coverage.coverage_identity,
            "event_identities": [item.liquidation_identity for item in selected],
            "mark_observation_identity": mark_reference.observation_identity,
            "schema_version": LIQUIDATION_HEATMAP_FREEZE_SCHEMA_VERSION,
        }
    )
    return LiquidationHeatmapEvidenceFreeze(
        freeze_identity=freeze_identity,
        schema_version=LIQUIDATION_HEATMAP_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        coverage=coverage,
        mark_reference=mark_reference,
        events=selected,
    )


def _analyze_selected(
    events: tuple[LiquidationObservation, ...],
    *,
    coverage: LiquidationFeedCoverage,
    mark_reference: DerivativesObservation,
    as_of_ms: int,
    source_window_start_ms: int,
    config: LiquidationHeatmapConfig,
) -> LiquidationHeatmapAnalysis:
    flags: list[str] = []
    mark_safe = max(
        mark_reference.event_at_ms,
        mark_reference.source_timestamp_ms,
        mark_reference.ingested_at_ms,
    ) <= as_of_ms
    if not mark_safe:
        flags.append("future_mark_reference")
    if coverage.observed_at_ms > as_of_ms:
        flags.append("future_feed_coverage")
    if coverage.coverage_start_ms > source_window_start_ms:
        flags.append("incomplete_feed_coverage_start")
    if coverage.coverage_end_ms < as_of_ms:
        flags.append("incomplete_feed_coverage_end")

    mark_price = mark_reference.mark_price
    if mark_price is None:
        flags.append("mark_price_unavailable")
    latest_mark_age_ms = (
        None
        if not mark_safe
        else as_of_ms - mark_reference.event_at_ms
    )
    if (
        latest_mark_age_ms is not None
        and latest_mark_age_ms > config.max_mark_age_ms
    ):
        flags.append("stale_mark_reference")

    if flags:
        return _unresolved(
            events,
            coverage=coverage,
            mark_reference=mark_reference,
            as_of_ms=as_of_ms,
            source_window_start_ms=source_window_start_ms,
            flags=tuple(flags),
        )

    assert mark_price is not None
    total_notional = sum(
        (item.bankruptcy_notional for item in events),
        start=Decimal(0),
    )
    long_notional = sum(
        (
            item.bankruptcy_notional
            for item in events
            if item.liquidated_position_side is LiquidatedPositionSide.LONG
        ),
        start=Decimal(0),
    )
    short_notional = total_notional - long_notional
    bins = _build_bins(
        events,
        reference_mark_price=mark_price,
        total_notional=total_notional,
        config=config,
    )
    observed_state = (
        ObservedLiquidationState.OBSERVED
        if events
        else ObservedLiquidationState.NONE_OBSERVED
    )
    uncertainties = (
        "observed_liquidations_are_not_future_liquidation_risk",
        "estimated_leverage_concentration_not_available",
        "liquidation_risk_zone_not_estimated",
    )
    source_window_end_ms = as_of_ms
    payload: dict[str, object] = {
        "as_of_ms": as_of_ms,
        "bins": [_bin_payload(item) for item in bins],
        "consumed_event_count": len(events),
        "coverage_identity": coverage.coverage_identity,
        "engine_version": LIQUIDATION_HEATMAP_ENGINE_VERSION,
        "estimated_leverage_concentration_status": (
            LiquidationEstimationStatus.NOT_ESTIMATED
        ),
        "exchange": coverage.exchange,
        "first_event_identity": (
            None if not events else events[0].liquidation_identity
        ),
        "last_event_identity": (
            None if not events else events[-1].liquidation_identity
        ),
        "latest_mark_age_ms": latest_mark_age_ms,
        "liquidation_risk_zone_status": LiquidationEstimationStatus.NOT_ESTIMATED,
        "long_liquidation_notional": long_notional,
        "mark_observation_identity": mark_reference.observation_identity,
        "observed_cluster_count": sum(item.observed_cluster for item in bins),
        "observed_state": observed_state,
        "reference_mark_price": mark_price,
        "short_liquidation_notional": short_notional,
        "source_quality": LiquidationSourceQuality.GOOD,
        "source_window_end_ms": source_window_end_ms,
        "source_window_start_ms": source_window_start_ms,
        "status": LiquidationHeatmapStatus.MEASURED,
        "symbol": coverage.symbol,
        "total_bankruptcy_notional": total_notional,
        "uncertainty_flags": uncertainties,
    }
    return LiquidationHeatmapAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=LIQUIDATION_HEATMAP_ENGINE_VERSION,
        exchange=coverage.exchange,
        symbol=coverage.symbol,
        as_of_ms=as_of_ms,
        source_window_start_ms=source_window_start_ms,
        source_window_end_ms=source_window_end_ms,
        coverage_identity=coverage.coverage_identity,
        mark_observation_identity=mark_reference.observation_identity,
        reference_mark_price=mark_price,
        latest_mark_age_ms=latest_mark_age_ms,
        consumed_event_count=len(events),
        first_event_identity=None if not events else events[0].liquidation_identity,
        last_event_identity=None if not events else events[-1].liquidation_identity,
        total_bankruptcy_notional=total_notional,
        long_liquidation_notional=long_notional,
        short_liquidation_notional=short_notional,
        source_quality=LiquidationSourceQuality.GOOD,
        status=LiquidationHeatmapStatus.MEASURED,
        observed_state=observed_state,
        bins=bins,
        observed_cluster_count=sum(item.observed_cluster for item in bins),
        estimated_leverage_concentration_status=(
            LiquidationEstimationStatus.NOT_ESTIMATED
        ),
        liquidation_risk_zone_status=LiquidationEstimationStatus.NOT_ESTIMATED,
        uncertainty_flags=uncertainties,
    )


def _build_bins(
    events: tuple[LiquidationObservation, ...],
    *,
    reference_mark_price: Decimal,
    total_notional: Decimal,
    config: LiquidationHeatmapConfig,
) -> tuple[ObservedLiquidationBin, ...]:
    if not events:
        return ()

    grouped: dict[int, list[LiquidationObservation]] = {}
    for event in events:
        distance_bps = (
            (event.bankruptcy_price - reference_mark_price)
            / reference_mark_price
            * _BPS
        )
        bin_index = int(distance_bps // config.bin_width_bps)
        grouped.setdefault(bin_index, []).append(event)

    result: list[ObservedLiquidationBin] = []
    for bin_index in sorted(grouped):
        members = grouped[bin_index]
        notional = sum(
            (item.bankruptcy_notional for item in members),
            start=Decimal(0),
        )
        share = notional / total_notional
        lower = Decimal(bin_index) * config.bin_width_bps
        upper = lower + config.bin_width_bps
        prices = [item.bankruptcy_price for item in members]
        result.append(
            ObservedLiquidationBin(
                lower_distance_bps=lower,
                upper_distance_bps=upper,
                event_count=len(members),
                long_liquidation_count=sum(
                    item.liquidated_position_side
                    is LiquidatedPositionSide.LONG
                    for item in members
                ),
                short_liquidation_count=sum(
                    item.liquidated_position_side
                    is LiquidatedPositionSide.SHORT
                    for item in members
                ),
                bankruptcy_notional=notional,
                notional_share=share,
                minimum_bankruptcy_price=min(prices),
                maximum_bankruptcy_price=max(prices),
                observed_cluster=(
                    len(members) >= config.minimum_cluster_events
                    and share >= config.minimum_cluster_notional_share
                ),
            )
        )
    return tuple(result)


def _unresolved(
    events: tuple[LiquidationObservation, ...],
    *,
    coverage: LiquidationFeedCoverage,
    mark_reference: DerivativesObservation,
    as_of_ms: int,
    source_window_start_ms: int,
    flags: tuple[str, ...],
) -> LiquidationHeatmapAnalysis:
    safe_mark = max(
        mark_reference.event_at_ms,
        mark_reference.source_timestamp_ms,
        mark_reference.ingested_at_ms,
    ) <= as_of_ms
    latest_mark_age_ms = (
        as_of_ms - mark_reference.event_at_ms if safe_mark else None
    )
    payload: dict[str, object] = {
        "as_of_ms": as_of_ms,
        "bins": [],
        "consumed_event_count": len(events),
        "coverage_identity": None,
        "engine_version": LIQUIDATION_HEATMAP_ENGINE_VERSION,
        "estimated_leverage_concentration_status": (
            LiquidationEstimationStatus.NOT_ESTIMATED
        ),
        "exchange": coverage.exchange,
        "first_event_identity": (
            None if not events else events[0].liquidation_identity
        ),
        "last_event_identity": (
            None if not events else events[-1].liquidation_identity
        ),
        "latest_mark_age_ms": latest_mark_age_ms,
        "liquidation_risk_zone_status": LiquidationEstimationStatus.NOT_ESTIMATED,
        "long_liquidation_notional": None,
        "mark_observation_identity": None,
        "observed_cluster_count": 0,
        "observed_state": ObservedLiquidationState.UNAVAILABLE,
        "reference_mark_price": None,
        "short_liquidation_notional": None,
        "source_quality": LiquidationSourceQuality.DEGRADED,
        "source_window_end_ms": None,
        "source_window_start_ms": source_window_start_ms,
        "status": LiquidationHeatmapStatus.UNRESOLVED,
        "symbol": coverage.symbol,
        "total_bankruptcy_notional": None,
        "uncertainty_flags": flags,
    }
    return LiquidationHeatmapAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=LIQUIDATION_HEATMAP_ENGINE_VERSION,
        exchange=coverage.exchange,
        symbol=coverage.symbol,
        as_of_ms=as_of_ms,
        source_window_start_ms=source_window_start_ms,
        source_window_end_ms=None,
        coverage_identity=None,
        mark_observation_identity=None,
        reference_mark_price=None,
        latest_mark_age_ms=latest_mark_age_ms,
        consumed_event_count=len(events),
        first_event_identity=None if not events else events[0].liquidation_identity,
        last_event_identity=None if not events else events[-1].liquidation_identity,
        total_bankruptcy_notional=None,
        long_liquidation_notional=None,
        short_liquidation_notional=None,
        source_quality=LiquidationSourceQuality.DEGRADED,
        status=LiquidationHeatmapStatus.UNRESOLVED,
        observed_state=ObservedLiquidationState.UNAVAILABLE,
        bins=(),
        observed_cluster_count=0,
        estimated_leverage_concentration_status=(
            LiquidationEstimationStatus.NOT_ESTIMATED
        ),
        liquidation_risk_zone_status=LiquidationEstimationStatus.NOT_ESTIMATED,
        uncertainty_flags=flags,
    )


def _require_shared_context(
    events: Sequence[LiquidationObservation],
    coverage: LiquidationFeedCoverage,
    mark_reference: DerivativesObservation,
) -> None:
    expected = (
        coverage.exchange,
        coverage.instrument_type,
        coverage.symbol,
    )
    mark_context = (
        mark_reference.exchange,
        mark_reference.instrument_type,
        mark_reference.symbol,
    )
    if mark_context != expected:
        raise ValueError("liquidation heatmap mark/coverage context mismatch")
    for event in events:
        actual = (event.exchange, event.instrument_type, event.symbol)
        if actual != expected:
            raise ValueError("liquidation heatmap event context mismatch")


def _reject_duplicate_event_identities(
    events: tuple[LiquidationObservation, ...],
) -> None:
    identities = [item.liquidation_identity for item in events]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate liquidation event identity")


def _validate_event_identity_pair(
    count: int,
    first_identity: str | None,
    last_identity: str | None,
) -> None:
    if count == 0:
        if first_identity is not None or last_identity is not None:
            raise ValueError("empty liquidation window cannot carry event identities")
        return
    if first_identity is None or last_identity is None:
        raise ValueError("non-empty liquidation window requires event identities")
    _require_sha256(first_identity, "first liquidation event identity")
    _require_sha256(last_identity, "last liquidation event identity")


def _bin_payload(item: ObservedLiquidationBin) -> dict[str, object]:
    return {
        field: getattr(item, field)
        for field in item.__dataclass_fields__
    }


def _analysis_payload(analysis: LiquidationHeatmapAnalysis) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "bins": [_bin_payload(item) for item in analysis.bins],
        "consumed_event_count": analysis.consumed_event_count,
        "coverage_identity": analysis.coverage_identity,
        "engine_version": analysis.engine_version,
        "estimated_leverage_concentration_status": (
            analysis.estimated_leverage_concentration_status
        ),
        "exchange": analysis.exchange,
        "first_event_identity": analysis.first_event_identity,
        "last_event_identity": analysis.last_event_identity,
        "latest_mark_age_ms": analysis.latest_mark_age_ms,
        "liquidation_risk_zone_status": analysis.liquidation_risk_zone_status,
        "long_liquidation_notional": analysis.long_liquidation_notional,
        "mark_observation_identity": analysis.mark_observation_identity,
        "observed_cluster_count": analysis.observed_cluster_count,
        "observed_state": analysis.observed_state,
        "reference_mark_price": analysis.reference_mark_price,
        "short_liquidation_notional": analysis.short_liquidation_notional,
        "source_quality": analysis.source_quality,
        "source_window_end_ms": analysis.source_window_end_ms,
        "source_window_start_ms": analysis.source_window_start_ms,
        "status": analysis.status,
        "symbol": analysis.symbol,
        "total_bankruptcy_notional": analysis.total_bankruptcy_notional,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be SHA256")
