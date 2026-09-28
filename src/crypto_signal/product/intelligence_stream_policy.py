from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.decision_proof import LiveFeedEventKind
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
    StreamCategory,
    StreamImportance,
    StreamSourceEvent,
)

STREAM_MATERIALITY_POLICY_SCHEMA_VERSION = "intelligence-stream-materiality-policy-v1/1"
STREAM_MATERIALITY_DECISION_SCHEMA_VERSION = (
    "intelligence-stream-materiality-decision-v1/1"
)
STREAM_MATERIALITY_POLICY_VERSION = "stream-v1-core-materiality/1"
STREAM_PROJECTOR_REGISTRY_VERSION = "stream-v1-source-projector-registry/1"


class StreamMateriality(StrEnum):
    ROUTINE = "routine"
    MATERIAL = "material"


class StreamPublicationDisposition(StrEnum):
    PUBLISH = "publish"
    SILENT = "silent"


class StreamProjectorImplementationState(StrEnum):
    IMPLEMENTED = "implemented"
    REQUIRES_CHANGE_DETECTION = "requires_change_detection"
    LATER_PHASE = "later_phase"
    DEFERRED_SOURCE = "deferred_source"
    RESEARCH_ONLY = "research_only"


@dataclass(frozen=True, slots=True)
class StreamMaterialityRule:
    category: StreamCategory
    subtype: str
    importance: StreamImportance
    disposition: StreamPublicationDisposition
    materiality: StreamMateriality
    reason_code: str

    def __post_init__(self) -> None:
        if not self.subtype.strip() or not self.reason_code.strip():
            raise ValueError("Stream materiality rule text must be non-empty")


@dataclass(frozen=True, slots=True)
class StreamMaterialityPolicy:
    policy_identity: str
    policy_version: str
    rules: tuple[StreamMaterialityRule, ...]
    schema_version: str = STREAM_MATERIALITY_POLICY_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "Stream materiality policy identity")
        if self.policy_version != STREAM_MATERIALITY_POLICY_VERSION:
            raise ValueError("unsupported Stream materiality policy version")
        keys = tuple(
            (item.category.value, item.subtype, item.importance.value)
            for item in self.rules
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("Stream materiality rules must be unique and canonical")
        if not self.rules:
            raise ValueError("Stream materiality policy requires at least one rule")
        _require_common_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_MATERIALITY_POLICY_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("Stream materiality policy identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamMaterialityDecision:
    decision_identity: str
    policy_identity: str
    policy_version: str
    source_event_identity: str
    disposition: StreamPublicationDisposition
    materiality: StreamMateriality
    reason_codes: tuple[str, ...]
    schema_version: str = STREAM_MATERIALITY_DECISION_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.decision_identity, "Stream materiality decision identity")
        _require_sha256(self.policy_identity, "Stream materiality decision policy")
        _require_sha256(self.source_event_identity, "Stream materiality source event")
        if self.policy_version != STREAM_MATERIALITY_POLICY_VERSION:
            raise ValueError("Stream materiality decision policy version mismatch")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("Stream materiality reasons must be unique and sorted")
        if not self.reason_codes:
            raise ValueError("Stream materiality decision requires reason code")
        _require_common_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_MATERIALITY_DECISION_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.decision_identity != canonical_sha256(_decision_payload(self)):
            raise ValueError("Stream materiality decision identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamProjectorSpec:
    projector_id: str
    source_system: str
    category: StreamCategory
    subtypes: tuple[str, ...]
    implementation_state: StreamProjectorImplementationState
    target_phase: str
    customer_stream_scope: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.projector_id, "Stream projector id"),
            (self.source_system, "Stream projector source system"),
            (self.target_phase, "Stream projector target phase"),
            (self.customer_stream_scope, "Stream projector scope"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if tuple(sorted(set(self.subtypes))) != self.subtypes:
            raise ValueError("Stream projector subtypes must be unique and sorted")
        if not self.subtypes:
            raise ValueError("Stream projector requires at least one subtype")


def build_stream_materiality_policy() -> StreamMaterialityPolicy:
    rules = tuple(
        sorted(
            (
                StreamMaterialityRule(
                    category=StreamCategory.DECISION,
                    subtype=LiveFeedEventKind.FORECAST_ISSUED.value,
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="canonical_forecast_issuance_is_material",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.OUTCOME,
                    subtype=LiveFeedEventKind.FORECAST_RESOLVED.value,
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="canonical_forecast_resolution_is_material",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.MARKET,
                    subtype="geometry_material_change",
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="material_geometry_state_transition",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.MARKET,
                    subtype="trigger_transition",
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="material_geometry_trigger_transition",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.INTELLIGENCE,
                    subtype="liquidity_material_change",
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="material_liquidity_state_transition",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.INTELLIGENCE,
                    subtype="order_flow_material_change",
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="material_order_flow_state_transition",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.INTELLIGENCE,
                    subtype="derivatives_material_change",
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="material_derivatives_state_transition",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.RISK,
                    subtype="event_risk_block",
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="material_event_risk_block",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.RISK,
                    subtype="event_risk_change",
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="material_event_risk_state_transition",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.RISK,
                    subtype="event_risk_recovery",
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="material_event_risk_recovery",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.SYSTEM,
                    subtype="data_quality_degraded",
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="decision_relevant_provider_quality_degraded",
                ),
                StreamMaterialityRule(
                    category=StreamCategory.SYSTEM,
                    subtype="data_quality_recovered",
                    importance=StreamImportance.IMPORTANT,
                    disposition=StreamPublicationDisposition.PUBLISH,
                    materiality=StreamMateriality.MATERIAL,
                    reason_code="decision_relevant_provider_quality_recovered",
                ),
            ),
            key=lambda item: (
                item.category.value,
                item.subtype,
                item.importance.value,
            ),
        )
    )
    payload = {
        "engine_version": STREAM_ENGINE_VERSION,
        "policy_version": STREAM_MATERIALITY_POLICY_VERSION,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "rules": rules,
        "schema_version": STREAM_MATERIALITY_POLICY_SCHEMA_VERSION,
    }
    return StreamMaterialityPolicy(
        policy_identity=canonical_sha256(payload),
        policy_version=STREAM_MATERIALITY_POLICY_VERSION,
        rules=rules,
    )


def evaluate_stream_materiality(
    policy: StreamMaterialityPolicy,
    event: StreamSourceEvent,
) -> StreamMaterialityDecision:
    selected = next(
        (
            rule
            for rule in policy.rules
            if (
                rule.category is event.category
                and rule.subtype == event.subtype
                and rule.importance is event.importance
            )
        ),
        None,
    )
    if selected is None:
        disposition = StreamPublicationDisposition.SILENT
        materiality = StreamMateriality.ROUTINE
        reasons = ("no_material_publish_rule_for_source_event",)
    else:
        disposition = selected.disposition
        materiality = selected.materiality
        reasons = (selected.reason_code,)
    payload = {
        "disposition": disposition,
        "engine_version": STREAM_ENGINE_VERSION,
        "materiality": materiality,
        "policy_identity": policy.policy_identity,
        "policy_version": policy.policy_version,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "reason_codes": reasons,
        "schema_version": STREAM_MATERIALITY_DECISION_SCHEMA_VERSION,
        "source_event_identity": event.stream_event_identity,
    }
    return StreamMaterialityDecision(
        decision_identity=canonical_sha256(payload),
        policy_identity=policy.policy_identity,
        policy_version=policy.policy_version,
        source_event_identity=event.stream_event_identity,
        disposition=disposition,
        materiality=materiality,
        reason_codes=reasons,
    )


def accepted_stream_projector_registry() -> tuple[StreamProjectorSpec, ...]:
    specs = (
        StreamProjectorSpec(
            projector_id="r20_5_forecast_issued",
            source_system="R20/R20.5 Decision Evidence Ledger",
            category=StreamCategory.DECISION,
            subtypes=(LiveFeedEventKind.FORECAST_ISSUED.value,),
            implementation_state=StreamProjectorImplementationState.IMPLEMENTED,
            target_phase="S2",
            customer_stream_scope="exact persisted forecast issuance",
        ),
        StreamProjectorSpec(
            projector_id="r20_5_forecast_resolved",
            source_system="R20/R20.5 Decision Evidence Ledger",
            category=StreamCategory.OUTCOME,
            subtypes=(LiveFeedEventKind.FORECAST_RESOLVED.value,),
            implementation_state=StreamProjectorImplementationState.IMPLEMENTED,
            target_phase="S2",
            customer_stream_scope="exact persisted forecast resolution",
        ),
        StreamProjectorSpec(
            projector_id="market_geometry_change",
            source_system="Signal Freeze / Decision Context",
            category=StreamCategory.MARKET,
            subtypes=("geometry_material_change", "trigger_transition"),
            implementation_state=(
                StreamProjectorImplementationState.IMPLEMENTED
            ),
            target_phase="S3-S4",
            customer_stream_scope="material geometry/trigger change only",
        ),
        StreamProjectorSpec(
            projector_id="liquidity_change",
            source_system="Market Tape / Liquidity evidence",
            category=StreamCategory.INTELLIGENCE,
            subtypes=("liquidity_material_change",),
            implementation_state=(
                StreamProjectorImplementationState.IMPLEMENTED
            ),
            target_phase="S3-S4",
            customer_stream_scope="material liquidity/sweep evidence change only",
        ),
        StreamProjectorSpec(
            projector_id="order_flow_change",
            source_system="Market Tape / Order Flow evidence",
            category=StreamCategory.INTELLIGENCE,
            subtypes=("order_flow_material_change",),
            implementation_state=(
                StreamProjectorImplementationState.IMPLEMENTED
            ),
            target_phase="S3-S4",
            customer_stream_scope="material CVD/absorption evidence change only",
        ),
        StreamProjectorSpec(
            projector_id="derivatives_change",
            source_system="Market Tape derivatives evidence",
            category=StreamCategory.INTELLIGENCE,
            subtypes=("derivatives_material_change",),
            implementation_state=(
                StreamProjectorImplementationState.IMPLEMENTED
            ),
            target_phase="S3-S4",
            customer_stream_scope="material derivatives context change only",
        ),
        StreamProjectorSpec(
            projector_id="onchain_change",
            source_system="On-chain Capital Flow / DefiLlama stablecoin evidence",
            category=StreamCategory.INTELLIGENCE,
            subtypes=("onchain_material_change",),
            implementation_state=(
                StreamProjectorImplementationState.IMPLEMENTED
            ),
            target_phase="RDP7",
            customer_stream_scope=(
                "accepted neutral stablecoin capital context only"
            ),
        ),
        StreamProjectorSpec(
            projector_id="event_risk_change",
            source_system="Event Source / Event Risk circuit breaker",
            category=StreamCategory.RISK,
            subtypes=("event_risk_block", "event_risk_change", "event_risk_recovery"),
            implementation_state=(
                StreamProjectorImplementationState.IMPLEMENTED
            ),
            target_phase="S3-S4",
            customer_stream_scope="material approach/block/recovery only",
        ),
        StreamProjectorSpec(
            projector_id="provider_quality_change",
            source_system="Operational Truth / Provider Divergence",
            category=StreamCategory.SYSTEM,
            subtypes=("data_quality_degraded", "data_quality_recovered"),
            implementation_state=(
                StreamProjectorImplementationState.IMPLEMENTED
            ),
            target_phase="S3-S4",
            customer_stream_scope="decision-relevant degradation/recovery only",
        ),
        StreamProjectorSpec(
            projector_id="bitcoin_network_context",
            source_system="Blockstream Bitcoin Network",
            category=StreamCategory.INTELLIGENCE,
            subtypes=("bitcoin_network_material_change",),
            implementation_state=StreamProjectorImplementationState.DEFERRED_SOURCE,
            target_phase="S3+",
            customer_stream_scope="requires accepted always-on Stream persistence",
        ),
        StreamProjectorSpec(
            projector_id="m5_smart_money_research",
            source_system="Exchange Flow / Wallet Cohort / Large Transfer",
            category=StreamCategory.INTELLIGENCE,
            subtypes=("smart_money_research_context",),
            implementation_state=StreamProjectorImplementationState.RESEARCH_ONLY,
            target_phase="deferred",
            customer_stream_scope="no live provider activation; not live customer chatter",
        ),
        StreamProjectorSpec(
            projector_id="paper_capital_transition",
            source_system="Capital Science / Position Sizing / R22 / R21",
            category=StreamCategory.CAPITAL,
            subtypes=(
                "capital_accounting_updated",
                "capital_blocked",
                "capital_candidate",
                "capital_eligible",
                "capital_executed",
                "capital_exited",
                "capital_hold",
                "capital_outcome",
                "capital_reduced",
                "capital_sized",
            ),
            implementation_state=StreamProjectorImplementationState.IMPLEMENTED,
            target_phase="S11",
            customer_stream_scope="canonical three-vault paper-capital lifecycle",
        ),
    )
    return tuple(sorted(specs, key=lambda item: item.projector_id))


def _policy_payload(value: StreamMaterialityPolicy) -> dict[str, object]:
    return {
        "engine_version": value.engine_version,
        "policy_version": value.policy_version,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "rules": value.rules,
        "schema_version": value.schema_version,
    }


def _decision_payload(value: StreamMaterialityDecision) -> dict[str, object]:
    return {
        "disposition": value.disposition,
        "engine_version": value.engine_version,
        "materiality": value.materiality,
        "policy_identity": value.policy_identity,
        "policy_version": value.policy_version,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "reason_codes": value.reason_codes,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
    }


def _require_common_authority(
    *,
    schema_version: str,
    expected_schema: str,
    engine_version: str,
    read_only: bool,
    production_authority: bool,
    real_capital: int,
) -> None:
    if schema_version != expected_schema:
        raise ValueError("unsupported Stream policy schema version")
    if engine_version != STREAM_ENGINE_VERSION:
        raise ValueError("unsupported Stream policy engine version")
    if not read_only:
        raise ValueError("Stream policy truth must remain read-only")
    if production_authority:
        raise ValueError("Stream policy cannot grant production authority")
    if real_capital != REAL_CAPITAL:
        raise ValueError("REAL_CAPITAL must remain 0")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
