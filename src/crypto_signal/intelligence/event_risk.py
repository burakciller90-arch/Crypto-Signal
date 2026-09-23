from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.data.event_risk import (
    EventCalendarCoverage,
    EventCategory,
    EventSourceQuality,
    StructuredEventObservation,
)
from crypto_signal.ledger.serialization import canonical_sha256

EVENT_RISK_ENGINE_VERSION = "event-risk-calendar-v1-slice1/1"
EVENT_RISK_FREEZE_SCHEMA_VERSION = "event-risk-calendar-freeze-v1/1"
DEFAULT_REQUIRED_EVENT_CATEGORIES = (
    EventCategory.INFLATION,
    EventCategory.CENTRAL_BANK,
    EventCategory.EMPLOYMENT,
    EventCategory.REGULATORY,
    EventCategory.EXCHANGE_SECURITY,
    EventCategory.LISTING,
    EventCategory.DELISTING,
)


class EventRiskState(StrEnum):
    CLEAR = "clear"
    PRE_EVENT_CAUTION = "pre_event_caution"
    EVENT_BLOCK = "event_block"
    POST_EVENT_STABILIZATION = "post_event_stabilization"
    DEGRADED_DATA = "degraded_data"


@dataclass(frozen=True, slots=True)
class EventRiskConfig:
    caution_lead_ms: int = 60 * 60_000
    block_before_ms: int = 15 * 60_000
    block_after_ms: int = 15 * 60_000
    stabilization_ms: int = 30 * 60_000
    max_coverage_age_ms: int = 6 * 60 * 60_000
    required_categories: tuple[EventCategory, ...] = DEFAULT_REQUIRED_EVENT_CATEGORIES

    def __post_init__(self) -> None:
        if min(
            self.caution_lead_ms,
            self.block_before_ms,
            self.block_after_ms,
            self.stabilization_ms,
            self.max_coverage_age_ms,
        ) <= 0:
            raise ValueError("event-risk timing values must be positive")
        if self.block_before_ms >= self.caution_lead_ms:
            raise ValueError("event-risk block-before must be shorter than caution lead")
        expected_categories = tuple(
            sorted(set(self.required_categories), key=lambda item: item.value)
        )
        if not expected_categories or expected_categories != tuple(
            sorted(self.required_categories, key=lambda item: item.value)
        ):
            raise ValueError("event-risk required categories must be non-empty and unique")


DEFAULT_EVENT_RISK_CONFIG = EventRiskConfig()


@dataclass(frozen=True, slots=True)
class EventRiskAnalysis:
    evidence_identity: str
    engine_version: str
    asset: str
    as_of_ms: int
    state: EventRiskState
    consumed_event_identities: tuple[str, ...]
    nearest_event_identity: str | None
    nearest_event_scheduled_at_ms: int | None
    coverage_identity: str | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "event-risk evidence identity")
        if self.coverage_identity is not None:
            _require_sha256(self.coverage_identity, "event-risk coverage identity")
        if self.engine_version != EVENT_RISK_ENGINE_VERSION:
            raise ValueError("unsupported event-risk engine version")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("event-risk asset must be non-empty uppercase")
        if self.as_of_ms < 0:
            raise ValueError("event-risk as_of_ms must be non-negative")
        if tuple(sorted(set(self.consumed_event_identities))) != self.consumed_event_identities:
            raise ValueError("event-risk consumed event identities must be unique and sorted")
        for identity in self.consumed_event_identities:
            _require_sha256(identity, "event-risk consumed event identity")
        if (self.nearest_event_identity is None) != (
            self.nearest_event_scheduled_at_ms is None
        ):
            raise ValueError("event-risk nearest event fields must appear together")
        if self.nearest_event_identity is not None:
            _require_sha256(self.nearest_event_identity, "event-risk nearest event identity")
        if self.state is EventRiskState.DEGRADED_DATA and not self.uncertainty_flags:
            raise ValueError("degraded event-risk state requires uncertainty")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("event-risk evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class EventRiskEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: EventRiskAnalysis
    coverage: EventCalendarCoverage | None
    events: tuple[StructuredEventObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "event-risk freeze identity")
        if self.schema_version != EVENT_RISK_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported event-risk freeze schema")
        if self.coverage is None:
            if self.analysis.coverage_identity is not None:
                raise ValueError("event-risk missing coverage identity mismatch")
        else:
            if self.coverage.coverage_identity != self.analysis.coverage_identity:
                raise ValueError("event-risk coverage identity mismatch")
            if self.coverage.observed_at_ms > self.analysis.as_of_ms:
                raise ValueError("event-risk freeze contains future coverage evidence")
        if any(
            max(item.source_timestamp_ms, item.ingested_at_ms) > self.analysis.as_of_ms
            for item in self.events
        ):
            raise ValueError("event-risk freeze contains unavailable event evidence")
        expected_ids = tuple(sorted(item.event_identity for item in self.events))
        if expected_ids != self.analysis.consumed_event_identities:
            raise ValueError("event-risk consumed event identity mismatch")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("event-risk freeze identity mismatch")


def analyze_event_risk(
    events: Sequence[StructuredEventObservation],
    *,
    coverage: EventCalendarCoverage | None,
    asset: str,
    as_of_ms: int,
    config: EventRiskConfig = DEFAULT_EVENT_RISK_CONFIG,
) -> EventRiskAnalysis:
    return build_event_risk_evidence_freeze(
        events,
        coverage=coverage,
        asset=asset,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_event_risk_evidence_freeze(
    events: Sequence[StructuredEventObservation],
    *,
    coverage: EventCalendarCoverage | None,
    asset: str,
    as_of_ms: int,
    config: EventRiskConfig = DEFAULT_EVENT_RISK_CONFIG,
) -> EventRiskEvidenceFreeze:
    if not asset or asset != asset.upper():
        raise ValueError("event-risk asset must be non-empty uppercase")
    if as_of_ms < 0:
        raise ValueError("event-risk as_of_ms must be non-negative")

    if coverage is None or coverage.observed_at_ms > as_of_ms:
        analysis = _analysis(
            asset=asset,
            as_of_ms=as_of_ms,
            state=EventRiskState.DEGRADED_DATA,
            events=(),
            coverage=None,
            nearest=None,
            flags=("event_calendar_coverage_unavailable_at_as_of",),
        )
        return _freeze(analysis, None, ())

    degraded_flags = _coverage_flags(coverage, as_of_ms=as_of_ms, config=config)
    if degraded_flags:
        analysis = _analysis(
            asset=asset,
            as_of_ms=as_of_ms,
            state=EventRiskState.DEGRADED_DATA,
            events=(),
            coverage=coverage,
            nearest=None,
            flags=degraded_flags,
        )
        return _freeze(analysis, coverage, ())

    horizon_start = as_of_ms - config.block_after_ms - config.stabilization_ms
    horizon_end = as_of_ms + config.caution_lead_ms
    relevant = tuple(
        sorted(
            (
                item
                for item in events
                if max(item.source_timestamp_ms, item.ingested_at_ms) <= as_of_ms
                and (not item.affected_assets or asset in item.affected_assets)
                and horizon_start <= item.scheduled_at_ms <= horizon_end
            ),
            key=lambda item: (
                item.scheduled_at_ms,
                item.provider_event_id,
                item.event_identity,
            ),
        )
    )
    _validate_event_context(relevant, coverage)
    _reject_duplicates(relevant)

    unverified = tuple(
        item for item in relevant if item.source_quality is EventSourceQuality.UNVERIFIED
    )
    if unverified:
        flags = (
            "unverified_event_source_in_active_horizon",
            "event_risk_requires_verified_calendar_evidence",
        )
        nearest = min(
            unverified,
            key=lambda item: (
                abs(item.scheduled_at_ms - as_of_ms),
                item.event_identity,
            ),
        )
        analysis = _analysis(
            asset=asset,
            as_of_ms=as_of_ms,
            state=EventRiskState.DEGRADED_DATA,
            events=relevant,
            coverage=coverage,
            nearest=nearest,
            flags=flags,
        )
        return _freeze(analysis, coverage, relevant)

    state, nearest = _state(relevant, as_of_ms=as_of_ms, config=config)
    flags: tuple[str, ...] = (
        "event_window_is_versioned_research_policy_not_universal_law",
        "event_risk_is_context_or_veto_not_directional_signal",
    )
    analysis = _analysis(
        asset=asset,
        as_of_ms=as_of_ms,
        state=state,
        events=relevant,
        coverage=coverage,
        nearest=nearest,
        flags=flags,
    )
    return _freeze(analysis, coverage, relevant)


def _coverage_flags(
    coverage: EventCalendarCoverage,
    *,
    as_of_ms: int,
    config: EventRiskConfig,
) -> tuple[str, ...]:
    flags: list[str] = []
    if as_of_ms - coverage.observed_at_ms > config.max_coverage_age_ms:
        flags.append("stale_event_calendar_coverage")
    required_start = max(0, as_of_ms - config.block_after_ms - config.stabilization_ms)
    required_end = as_of_ms + config.caution_lead_ms
    if coverage.coverage_start_ms > required_start:
        flags.append("event_calendar_past_horizon_incomplete")
    if coverage.coverage_end_ms < required_end:
        flags.append("event_calendar_future_horizon_incomplete")
    if coverage.source_quality is EventSourceQuality.UNVERIFIED:
        flags.append("unverified_event_calendar_coverage")
    missing_categories = tuple(
        category
        for category in config.required_categories
        if category not in coverage.categories
    )
    if missing_categories:
        flags.append("event_calendar_required_categories_incomplete")
    return tuple(flags)


def _validate_event_context(
    events: tuple[StructuredEventObservation, ...],
    coverage: EventCalendarCoverage,
) -> None:
    for item in events:
        if item.source_provider != coverage.source_provider:
            raise ValueError("event-risk event/coverage provider mismatch")
        if item.category not in coverage.categories:
            raise ValueError("event-risk event category outside declared coverage")


def _reject_duplicates(events: tuple[StructuredEventObservation, ...]) -> None:
    event_ids = tuple(item.event_identity for item in events)
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("duplicate structured event identity")
    provider_ids = tuple(item.provider_event_id for item in events)
    if len(provider_ids) != len(set(provider_ids)):
        raise ValueError("duplicate provider event id")


def _state(
    events: tuple[StructuredEventObservation, ...],
    *,
    as_of_ms: int,
    config: EventRiskConfig,
) -> tuple[EventRiskState, StructuredEventObservation | None]:
    if not events:
        return EventRiskState.CLEAR, None

    ranked: list[tuple[int, int, StructuredEventObservation, EventRiskState]] = []
    precedence = {
        EventRiskState.EVENT_BLOCK: 0,
        EventRiskState.PRE_EVENT_CAUTION: 1,
        EventRiskState.POST_EVENT_STABILIZATION: 2,
        EventRiskState.CLEAR: 3,
    }
    for item in events:
        delta = item.scheduled_at_ms - as_of_ms
        if -config.block_after_ms <= delta <= config.block_before_ms:
            state = EventRiskState.EVENT_BLOCK
        elif config.block_before_ms < delta <= config.caution_lead_ms:
            state = EventRiskState.PRE_EVENT_CAUTION
        elif (
            -(config.block_after_ms + config.stabilization_ms)
            <= delta
            < -config.block_after_ms
        ):
            state = EventRiskState.POST_EVENT_STABILIZATION
        else:
            state = EventRiskState.CLEAR
        ranked.append(
            (
                precedence[state],
                abs(delta),
                item,
                state,
            )
        )
    ranked.sort(key=lambda row: (row[0], row[1], row[2].event_identity))
    _, _, nearest, state = ranked[0]
    return state, nearest


def _analysis(
    *,
    asset: str,
    as_of_ms: int,
    state: EventRiskState,
    events: tuple[StructuredEventObservation, ...],
    coverage: EventCalendarCoverage | None,
    nearest: StructuredEventObservation | None,
    flags: tuple[str, ...],
) -> EventRiskAnalysis:
    ids = tuple(sorted(item.event_identity for item in events))
    payload = {
        "asset": asset,
        "as_of_ms": as_of_ms,
        "consumed_event_identities": ids,
        "coverage_identity": None if coverage is None else coverage.coverage_identity,
        "engine_version": EVENT_RISK_ENGINE_VERSION,
        "nearest_event_identity": None if nearest is None else nearest.event_identity,
        "nearest_event_scheduled_at_ms": (
            None if nearest is None else nearest.scheduled_at_ms
        ),
        "state": state,
        "uncertainty_flags": flags,
    }
    return EventRiskAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=EVENT_RISK_ENGINE_VERSION,
        asset=asset,
        as_of_ms=as_of_ms,
        state=state,
        consumed_event_identities=ids,
        nearest_event_identity=None if nearest is None else nearest.event_identity,
        nearest_event_scheduled_at_ms=(
            None if nearest is None else nearest.scheduled_at_ms
        ),
        coverage_identity=None if coverage is None else coverage.coverage_identity,
        uncertainty_flags=flags,
    )


def _freeze(
    analysis: EventRiskAnalysis,
    coverage: EventCalendarCoverage | None,
    events: tuple[StructuredEventObservation, ...],
) -> EventRiskEvidenceFreeze:
    payload = {
        "analysis_identity": analysis.evidence_identity,
        "coverage_identity": None if coverage is None else coverage.coverage_identity,
        "event_identities": [item.event_identity for item in events],
        "schema_version": EVENT_RISK_FREEZE_SCHEMA_VERSION,
    }
    return EventRiskEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=EVENT_RISK_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        coverage=coverage,
        events=events,
    )


def _analysis_payload(analysis: EventRiskAnalysis) -> dict[str, object]:
    return {
        "asset": analysis.asset,
        "as_of_ms": analysis.as_of_ms,
        "consumed_event_identities": analysis.consumed_event_identities,
        "coverage_identity": analysis.coverage_identity,
        "engine_version": analysis.engine_version,
        "nearest_event_identity": analysis.nearest_event_identity,
        "nearest_event_scheduled_at_ms": analysis.nearest_event_scheduled_at_ms,
        "state": analysis.state,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze_payload(freeze: EventRiskEvidenceFreeze) -> dict[str, object]:
    return {
        "analysis_identity": freeze.analysis.evidence_identity,
        "coverage_identity": freeze.coverage.coverage_identity,
        "event_identities": [item.event_identity for item in freeze.events],
        "schema_version": freeze.schema_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
