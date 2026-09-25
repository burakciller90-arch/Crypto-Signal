from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_messages import StreamFactBundle
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
    STREAM_SOURCE_EVENT_SCHEMA_VERSION,
    StreamActivationBoundary,
    StreamCategory,
    StreamImportance,
    StreamSourceEvent,
)
from crypto_signal.product.intelligence_stream_policy import (
    StreamMateriality,
    StreamPublicationDisposition,
)
from crypto_signal.product.provider_divergence_runtime import (
    ProviderDivergenceRuntimeTruth,
)

STREAM_CONTEXT_PROJECTOR_POLICY_SCHEMA_VERSION = (
    "intelligence-stream-context-projector-policy-v1/1"
)
STREAM_CONTEXT_PROJECTOR_POLICY_VERSION = "stream-v1-context-projectors/1"
STREAM_CONTEXT_CANDIDATE_SCHEMA_VERSION = (
    "intelligence-stream-context-analytical-candidate-v1/1"
)


class StreamContextSourceKind(StrEnum):
    EVENT_RISK = "event_risk"
    PROVIDER_QUALITY = "provider_quality"


class StreamProviderQualityState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class StreamContextProjectorPolicy:
    policy_identity: str
    policy_version: str
    publish_initial_non_clear_event_risk: bool = True
    publish_initial_provider_degradation: bool = True
    provider_non_full_overlap_is_degraded: bool = True
    schema_version: str = STREAM_CONTEXT_PROJECTOR_POLICY_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "Stream context policy identity")
        if self.policy_version != STREAM_CONTEXT_PROJECTOR_POLICY_VERSION:
            raise ValueError("unsupported Stream context projector policy")
        _require_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_CONTEXT_PROJECTOR_POLICY_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("Stream context projector policy identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamContextAnalyticalCandidate:
    candidate_identity: str
    policy_identity: str
    policy_version: str
    source_kind: StreamContextSourceKind
    source_snapshot_identity: str
    previous_source_snapshot_identity: str | None
    target_fact_bundle_identity: str
    story_identity: str
    category: StreamCategory
    subtype: str
    importance: StreamImportance
    disposition: StreamPublicationDisposition
    materiality: StreamMateriality
    asset: str
    symbol: str
    timeframe: str
    event_at_ms: int
    previous_state: str | None
    current_state: str
    reason_codes: tuple[str, ...]
    evidence_identities: tuple[str, ...]
    source_event_identity: str | None
    stream_event_identity: str | None
    schema_version: str = STREAM_CONTEXT_CANDIDATE_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.candidate_identity, "Stream context candidate identity"),
            (self.policy_identity, "Stream context candidate policy"),
            (self.source_snapshot_identity, "Stream context source snapshot"),
            (self.target_fact_bundle_identity, "Stream context target fact"),
            (self.story_identity, "Stream context story identity"),
        ):
            _require_sha256(value, label)
        for optional_identity, label in (
            (
                self.previous_source_snapshot_identity,
                "Stream context previous source snapshot",
            ),
            (self.source_event_identity, "Stream context projected source event"),
            (self.stream_event_identity, "Stream context stream event"),
        ):
            if optional_identity is not None:
                _require_sha256(optional_identity, label)
        if self.policy_version != STREAM_CONTEXT_PROJECTOR_POLICY_VERSION:
            raise ValueError("Stream context candidate policy version mismatch")
        for value, label in (
            (self.subtype, "Stream context subtype"),
            (self.asset, "Stream context asset"),
            (self.symbol, "Stream context symbol"),
            (self.timeframe, "Stream context timeframe"),
            (self.current_state, "Stream context current state"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.previous_state is not None and not self.previous_state.strip():
            raise ValueError("Stream context previous state cannot be blank")
        if self.event_at_ms < 0:
            raise ValueError("Stream context event time must be non-negative")
        _require_text_tuple(self.reason_codes, "Stream context reason")
        if not self.reason_codes:
            raise ValueError("Stream context candidate requires reason codes")
        _require_identity_tuple(
            self.evidence_identities,
            "Stream context evidence identity",
        )
        if not self.evidence_identities:
            raise ValueError("Stream context candidate requires evidence")
        published = self.disposition is StreamPublicationDisposition.PUBLISH
        if published:
            if self.materiality is not StreamMateriality.MATERIAL:
                raise ValueError("published Stream context candidate must be material")
            if self.source_event_identity is None or self.stream_event_identity is None:
                raise ValueError("published Stream context candidate requires source event")
        else:
            if self.materiality is not StreamMateriality.ROUTINE:
                raise ValueError("silent Stream context candidate must be routine")
            if self.source_event_identity is not None or self.stream_event_identity is not None:
                raise ValueError("silent Stream context candidate cannot expose source event")
        _require_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_CONTEXT_CANDIDATE_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.candidate_identity != canonical_sha256(_candidate_payload(self)):
            raise ValueError("Stream context candidate identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamContextProjection:
    candidate: StreamContextAnalyticalCandidate
    source_event: StreamSourceEvent | None

    def __post_init__(self) -> None:
        if self.candidate.disposition is StreamPublicationDisposition.PUBLISH:
            if self.source_event is None:
                raise ValueError("published context projection requires source event")
            if (
                self.candidate.source_event_identity
                != self.source_event.source_event_identity
            ):
                raise ValueError("context candidate/source-event identity mismatch")
            if (
                self.candidate.stream_event_identity
                != self.source_event.stream_event_identity
            ):
                raise ValueError("context candidate/stream-event identity mismatch")
            if self.candidate.category is not self.source_event.category:
                raise ValueError("context candidate/source-event category mismatch")
            if self.candidate.subtype != self.source_event.subtype:
                raise ValueError("context candidate/source-event subtype mismatch")
        elif self.source_event is not None:
            raise ValueError("silent context projection cannot carry source event")


def build_stream_context_projector_policy() -> StreamContextProjectorPolicy:
    payload = {
        "engine_version": STREAM_ENGINE_VERSION,
        "policy_version": STREAM_CONTEXT_PROJECTOR_POLICY_VERSION,
        "production_authority": False,
        "provider_non_full_overlap_is_degraded": True,
        "publish_initial_non_clear_event_risk": True,
        "publish_initial_provider_degradation": True,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_CONTEXT_PROJECTOR_POLICY_SCHEMA_VERSION,
    }
    return StreamContextProjectorPolicy(
        policy_identity=canonical_sha256(payload),
        policy_version=STREAM_CONTEXT_PROJECTOR_POLICY_VERSION,
    )


def project_event_risk_context(
    policy: StreamContextProjectorPolicy,
    activation: StreamActivationBoundary,
    target_fact: StreamFactBundle,
    current: CircuitBreakerAnalysis,
    *,
    previous: CircuitBreakerAnalysis | None = None,
) -> StreamContextProjection:
    _validate_target_time(
        activation,
        target_fact,
        current_at_ms=current.as_of_ms,
    )
    if current.asset != target_fact.asset:
        raise ValueError("Event Risk context asset/decision mismatch")
    if previous is not None:
        if previous.asset != current.asset:
            raise ValueError("Event Risk previous/current asset mismatch")
        if previous.as_of_ms >= current.as_of_ms:
            raise ValueError("Event Risk transition must move forward in time")

    disposition, subtype, importance, reasons = _event_risk_transition(
        policy,
        previous,
        current,
    )
    evidence_ids = tuple(
        sorted(
            {
                current.evidence_identity,
                current.event_risk_identity,
                current.news_evidence_identity,
                *(
                    ()
                    if current.market_quality_identity is None
                    else (current.market_quality_identity,)
                ),
            }
        )
    )
    return _context_projection(
        policy=policy,
        activation=activation,
        target_fact=target_fact,
        source_kind=StreamContextSourceKind.EVENT_RISK,
        source_snapshot_identity=current.evidence_identity,
        previous_source_snapshot_identity=(
            None if previous is None else previous.evidence_identity
        ),
        category=StreamCategory.RISK,
        subtype=subtype,
        importance=importance,
        disposition=disposition,
        event_at_ms=current.as_of_ms,
        previous_state=None if previous is None else previous.state.value,
        current_state=current.state.value,
        reason_codes=reasons,
        evidence_identities=evidence_ids,
    )


def project_provider_quality_context(
    policy: StreamContextProjectorPolicy,
    activation: StreamActivationBoundary,
    target_fact: StreamFactBundle,
    current: ProviderDivergenceRuntimeTruth,
    *,
    previous: ProviderDivergenceRuntimeTruth | None = None,
) -> StreamContextProjection:
    _validate_target_time(
        activation,
        target_fact,
        current_at_ms=current.observed_at_ms,
    )
    if current.symbol != target_fact.symbol:
        raise ValueError("provider quality symbol/decision mismatch")
    if current.timeframe != target_fact.timeframe:
        raise ValueError("provider quality timeframe/decision mismatch")
    if previous is not None:
        if (previous.symbol, previous.timeframe) != (
            current.symbol,
            current.timeframe,
        ):
            raise ValueError("provider quality previous/current market mismatch")
        if previous.observed_at_ms >= current.observed_at_ms:
            raise ValueError("provider quality transition must move forward in time")

    current_reasons = _provider_degradation_reasons(policy, current)
    current_state = (
        StreamProviderQualityState.DEGRADED
        if current_reasons
        else StreamProviderQualityState.HEALTHY
    )
    previous_state: StreamProviderQualityState | None = None
    if previous is not None:
        previous_state = (
            StreamProviderQualityState.DEGRADED
            if _provider_degradation_reasons(policy, previous)
            else StreamProviderQualityState.HEALTHY
        )

    if previous_state is None:
        publish = (
            current_state is StreamProviderQualityState.DEGRADED
            and policy.publish_initial_provider_degradation
        )
        reasons = (
            ("initial_provider_quality_degraded", *current_reasons)
            if publish
            else ("initial_provider_quality_healthy",)
        )
    elif previous_state is current_state:
        publish = False
        reasons = ("no_material_provider_quality_state_transition",)
    elif current_state is StreamProviderQualityState.DEGRADED:
        publish = True
        reasons = ("provider_quality_degraded", *current_reasons)
    else:
        publish = True
        reasons = ("provider_quality_recovered",)

    if publish and current_state is StreamProviderQualityState.DEGRADED:
        subtype = "data_quality_degraded"
        importance = StreamImportance.CRITICAL
    elif publish:
        subtype = "data_quality_recovered"
        importance = StreamImportance.IMPORTANT
    else:
        subtype = "provider_quality_state_unchanged"
        importance = StreamImportance.ROUTINE

    return _context_projection(
        policy=policy,
        activation=activation,
        target_fact=target_fact,
        source_kind=StreamContextSourceKind.PROVIDER_QUALITY,
        source_snapshot_identity=current.snapshot_identity,
        previous_source_snapshot_identity=(
            None if previous is None else previous.snapshot_identity
        ),
        category=StreamCategory.SYSTEM,
        subtype=subtype,
        importance=importance,
        disposition=(
            StreamPublicationDisposition.PUBLISH
            if publish
            else StreamPublicationDisposition.SILENT
        ),
        event_at_ms=current.observed_at_ms,
        previous_state=(
            None if previous_state is None else previous_state.value
        ),
        current_state=current_state.value,
        reason_codes=tuple(sorted(set(reasons))),
        evidence_identities=(current.snapshot_identity,),
    )


def _event_risk_transition(
    policy: StreamContextProjectorPolicy,
    previous: CircuitBreakerAnalysis | None,
    current: CircuitBreakerAnalysis,
) -> tuple[
    StreamPublicationDisposition,
    str,
    StreamImportance,
    tuple[str, ...],
]:
    blocking = {
        CircuitBreakerState.EVENT_BLOCK,
        CircuitBreakerState.DEGRADED_DATA,
        CircuitBreakerState.ABSTAIN,
    }
    if previous is None:
        if current.state is CircuitBreakerState.CLEAR:
            return (
                StreamPublicationDisposition.SILENT,
                "event_risk_state_unchanged",
                StreamImportance.ROUTINE,
                ("initial_event_risk_clear",),
            )
        if not policy.publish_initial_non_clear_event_risk:
            return (
                StreamPublicationDisposition.SILENT,
                "event_risk_state_unchanged",
                StreamImportance.ROUTINE,
                ("initial_non_clear_event_risk_silent_by_policy",),
            )
        if current.state in blocking:
            return (
                StreamPublicationDisposition.PUBLISH,
                "event_risk_block",
                StreamImportance.CRITICAL,
                ("initial_event_risk_blocking_state",),
            )
        return (
            StreamPublicationDisposition.PUBLISH,
            "event_risk_change",
            StreamImportance.IMPORTANT,
            ("initial_event_risk_caution",),
        )

    if previous.state is current.state:
        return (
            StreamPublicationDisposition.SILENT,
            "event_risk_state_unchanged",
            StreamImportance.ROUTINE,
            ("no_material_event_risk_state_transition",),
        )
    if current.state is CircuitBreakerState.CLEAR:
        return (
            StreamPublicationDisposition.PUBLISH,
            "event_risk_recovery",
            StreamImportance.IMPORTANT,
            ("event_risk_recovered_to_clear",),
        )
    if current.state in blocking:
        return (
            StreamPublicationDisposition.PUBLISH,
            "event_risk_block",
            StreamImportance.CRITICAL,
            ("event_risk_entered_blocking_state",),
        )
    return (
        StreamPublicationDisposition.PUBLISH,
        "event_risk_change",
        StreamImportance.IMPORTANT,
        ("event_risk_state_changed",),
    )


def _provider_degradation_reasons(
    policy: StreamContextProjectorPolicy,
    truth: ProviderDivergenceRuntimeTruth,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    for side, quality in (
        ("left", truth.left_quality),
        ("right", truth.right_quality),
    ):
        if not quality.available:
            reasons.add(f"{side}_provider_unavailable")
        if quality.stale:
            reasons.add(f"{side}_provider_stale")
        if quality.gap_count > 0 or quality.gap_missing_candles > 0:
            reasons.add(f"{side}_provider_gap")
    if policy.provider_non_full_overlap_is_degraded:
        if truth.grid_state == "partial_overlap":
            reasons.add("provider_grid_partial_overlap")
        elif truth.grid_state == "no_overlap":
            reasons.add("provider_grid_no_overlap")
    return tuple(sorted(reasons))


def _validate_target_time(
    activation: StreamActivationBoundary,
    target_fact: StreamFactBundle,
    *,
    current_at_ms: int,
) -> None:
    if current_at_ms < activation.activated_at_ms:
        raise ValueError("Stream context event predates activation boundary")
    if current_at_ms < target_fact.event_at_ms:
        raise ValueError("Stream context event predates target decision fact")


def _context_projection(
    *,
    policy: StreamContextProjectorPolicy,
    activation: StreamActivationBoundary,
    target_fact: StreamFactBundle,
    source_kind: StreamContextSourceKind,
    source_snapshot_identity: str,
    previous_source_snapshot_identity: str | None,
    category: StreamCategory,
    subtype: str,
    importance: StreamImportance,
    disposition: StreamPublicationDisposition,
    event_at_ms: int,
    previous_state: str | None,
    current_state: str,
    reason_codes: tuple[str, ...],
    evidence_identities: tuple[str, ...],
) -> StreamContextProjection:
    reasons = tuple(sorted(set(reason_codes)))
    evidence = tuple(sorted(set(evidence_identities)))
    published = disposition is StreamPublicationDisposition.PUBLISH
    source_event: StreamSourceEvent | None = None
    projected_source_identity: str | None = None
    stream_event_identity: str | None = None

    if published:
        projected_source_identity = canonical_sha256(
            {
                "policy_identity": policy.policy_identity,
                "projector_kind": source_kind,
                "source_snapshot_identity": source_snapshot_identity,
                "story_identity": target_fact.story_identity,
                "target_fact_bundle_identity": target_fact.fact_bundle_identity,
            }
        )
        event_payload = {
            "activation_identity": activation.activation_identity,
            "asset": target_fact.asset,
            "category": category,
            "decision_context_identity": target_fact.decision_context_identity,
            "engine_version": STREAM_ENGINE_VERSION,
            "event_at_ms": event_at_ms,
            "evidence_identities": evidence,
            "forecast_identity": target_fact.forecast_identity,
            "importance": importance,
            "materiality_codes": reasons,
            "production_authority": False,
            "proof_identity": target_fact.proof_identity,
            "read_only": True,
            "real_capital": REAL_CAPITAL,
            "resolution_identity": None,
            "schema_version": STREAM_SOURCE_EVENT_SCHEMA_VERSION,
            "source_as_of_ms": event_at_ms,
            "source_event_identity": projected_source_identity,
            "subtype": subtype,
            "symbol": target_fact.symbol,
            "timeframe": target_fact.timeframe,
        }
        stream_event_identity = canonical_sha256(event_payload)
        source_event = StreamSourceEvent(
            stream_event_identity=stream_event_identity,
            activation_identity=activation.activation_identity,
            source_event_identity=projected_source_identity,
            category=category,
            subtype=subtype,
            importance=importance,
            asset=target_fact.asset,
            symbol=target_fact.symbol,
            timeframe=target_fact.timeframe,
            event_at_ms=event_at_ms,
            source_as_of_ms=event_at_ms,
            forecast_identity=target_fact.forecast_identity,
            proof_identity=target_fact.proof_identity,
            resolution_identity=None,
            decision_context_identity=target_fact.decision_context_identity,
            evidence_identities=evidence,
            materiality_codes=reasons,
        )

    payload = {
        "asset": target_fact.asset,
        "category": category,
        "current_state": current_state,
        "disposition": disposition,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": event_at_ms,
        "evidence_identities": evidence,
        "importance": importance,
        "materiality": (
            StreamMateriality.MATERIAL if published else StreamMateriality.ROUTINE
        ),
        "policy_identity": policy.policy_identity,
        "policy_version": policy.policy_version,
        "previous_source_snapshot_identity": previous_source_snapshot_identity,
        "previous_state": previous_state,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "reason_codes": reasons,
        "schema_version": STREAM_CONTEXT_CANDIDATE_SCHEMA_VERSION,
        "source_event_identity": projected_source_identity,
        "source_kind": source_kind,
        "source_snapshot_identity": source_snapshot_identity,
        "story_identity": target_fact.story_identity,
        "stream_event_identity": stream_event_identity,
        "subtype": subtype,
        "symbol": target_fact.symbol,
        "target_fact_bundle_identity": target_fact.fact_bundle_identity,
        "timeframe": target_fact.timeframe,
    }
    candidate = StreamContextAnalyticalCandidate(
        candidate_identity=canonical_sha256(payload),
        policy_identity=policy.policy_identity,
        policy_version=policy.policy_version,
        source_kind=source_kind,
        source_snapshot_identity=source_snapshot_identity,
        previous_source_snapshot_identity=previous_source_snapshot_identity,
        target_fact_bundle_identity=target_fact.fact_bundle_identity,
        story_identity=target_fact.story_identity,
        category=category,
        subtype=subtype,
        importance=importance,
        disposition=disposition,
        materiality=(
            StreamMateriality.MATERIAL if published else StreamMateriality.ROUTINE
        ),
        asset=target_fact.asset,
        symbol=target_fact.symbol,
        timeframe=target_fact.timeframe,
        event_at_ms=event_at_ms,
        previous_state=previous_state,
        current_state=current_state,
        reason_codes=reasons,
        evidence_identities=evidence,
        source_event_identity=projected_source_identity,
        stream_event_identity=stream_event_identity,
    )
    return StreamContextProjection(candidate=candidate, source_event=source_event)


def _policy_payload(value: StreamContextProjectorPolicy) -> dict[str, object]:
    return {
        "engine_version": value.engine_version,
        "policy_version": value.policy_version,
        "production_authority": value.production_authority,
        "provider_non_full_overlap_is_degraded": (
            value.provider_non_full_overlap_is_degraded
        ),
        "publish_initial_non_clear_event_risk": (
            value.publish_initial_non_clear_event_risk
        ),
        "publish_initial_provider_degradation": (
            value.publish_initial_provider_degradation
        ),
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
    }


def _candidate_payload(
    value: StreamContextAnalyticalCandidate,
) -> dict[str, object]:
    return {
        "asset": value.asset,
        "category": value.category,
        "current_state": value.current_state,
        "disposition": value.disposition,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "evidence_identities": value.evidence_identities,
        "importance": value.importance,
        "materiality": value.materiality,
        "policy_identity": value.policy_identity,
        "policy_version": value.policy_version,
        "previous_source_snapshot_identity": value.previous_source_snapshot_identity,
        "previous_state": value.previous_state,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "reason_codes": value.reason_codes,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
        "source_kind": value.source_kind,
        "source_snapshot_identity": value.source_snapshot_identity,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "subtype": value.subtype,
        "symbol": value.symbol,
        "target_fact_bundle_identity": value.target_fact_bundle_identity,
        "timeframe": value.timeframe,
    }


def _require_authority(
    *,
    schema_version: str,
    expected_schema: str,
    engine_version: str,
    read_only: bool,
    production_authority: bool,
    real_capital: int,
) -> None:
    if schema_version != expected_schema:
        raise ValueError("unsupported Stream context projector schema")
    if engine_version != STREAM_ENGINE_VERSION:
        raise ValueError("unsupported Stream context projector engine")
    if not read_only:
        raise ValueError("Stream context projector truth must remain read-only")
    if production_authority:
        raise ValueError("Stream context projector cannot grant production authority")
    if real_capital != REAL_CAPITAL:
        raise ValueError("REAL_CAPITAL must remain 0")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_text_tuple(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be unique and sorted")
    if any(not value.strip() for value in values):
        raise ValueError(f"{label} cannot contain blank values")
