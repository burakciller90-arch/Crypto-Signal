from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.ledger.serialization import canonical_sha256

M6_CONFLUENCE_ENGINE_VERSION = "m6-confluence-matrix-v2-slice1/1"
M6_CONFLUENCE_POLICY_SCHEMA_VERSION = "m6-confluence-policy-v2/1"
M6_FAMILY_EVIDENCE_SCHEMA_VERSION = "m6-family-evidence-v2/1"
M6_SCORE_SEMANTIC = "weighted_support_opposition_points_not_probability"
M6_PROBABILITY_STATUS = "not_calibrated"
REAL_CAPITAL = 0
_SCORE_QUANTUM = Decimal("0.01")


class ConfluenceFamily(StrEnum):
    GEOMETRY = "geometry_pa_elliott_harmonic"
    LIQUIDITY = "liquidity"
    ORDER_FLOW = "order_flow_absorption"
    DERIVATIVES = "derivatives"
    ONCHAIN = "onchain_smart_money"


class ConfluenceMatrixResolution(StrEnum):
    MEASURED = "measured"
    PARTIAL = "partial"
    CONFLICT = "conflict"
    ABSTAIN = "abstain"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class ConfluenceFamilyPrior:
    family: ConfluenceFamily
    weight: Decimal

    def __post_init__(self) -> None:
        if self.weight <= Decimal(0) or self.weight > Decimal(1):
            raise ValueError("confluence family prior weight must be inside (0,1]")


LOCKED_M6_PRIORS = (
    ConfluenceFamilyPrior(ConfluenceFamily.GEOMETRY, Decimal("0.20")),
    ConfluenceFamilyPrior(ConfluenceFamily.LIQUIDITY, Decimal("0.25")),
    ConfluenceFamilyPrior(ConfluenceFamily.ORDER_FLOW, Decimal("0.25")),
    ConfluenceFamilyPrior(ConfluenceFamily.DERIVATIVES, Decimal("0.15")),
    ConfluenceFamilyPrior(ConfluenceFamily.ONCHAIN, Decimal("0.15")),
)
LOCKED_M6_THRESHOLD_HYPOTHESES = (
    Decimal(70),
    Decimal(75),
    Decimal(80),
    Decimal(85),
)


@dataclass(frozen=True, slots=True)
class ConfluenceMatrixPolicy:
    policy_identity: str
    schema_version: str
    engine_version: str
    policy_version: str
    priors: tuple[ConfluenceFamilyPrior, ...]
    threshold_hypotheses: tuple[Decimal, ...]
    event_risk_outside_matrix: bool = True
    probability_status: str = M6_PROBABILITY_STATUS
    score_semantic: str = M6_SCORE_SEMANTIC
    automatic_activation: bool = False
    automatic_promotion: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "M6 policy identity")
        if self.schema_version != M6_CONFLUENCE_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported M6 confluence policy schema")
        if self.engine_version != M6_CONFLUENCE_ENGINE_VERSION:
            raise ValueError("unsupported M6 confluence policy engine")
        if not self.policy_version.strip():
            raise ValueError("M6 policy_version must be non-empty")
        families = tuple(item.family for item in self.priors)
        if set(families) != set(ConfluenceFamily) or len(families) != len(
            ConfluenceFamily
        ):
            raise ValueError("M6 policy must contain exactly one prior per family")
        if families != tuple(sorted(families, key=lambda item: item.value)):
            raise ValueError("M6 policy priors must be canonical")
        total = sum((item.weight for item in self.priors), start=Decimal(0))
        if total != Decimal(1):
            raise ValueError("M6 family priors must sum exactly to 1")
        if tuple(sorted(set(self.threshold_hypotheses))) != self.threshold_hypotheses:
            raise ValueError("M6 threshold hypotheses must be unique and sorted")
        if not self.threshold_hypotheses:
            raise ValueError("M6 policy requires threshold hypotheses")
        if any(
            value <= Decimal(0) or value > Decimal(100)
            for value in self.threshold_hypotheses
        ):
            raise ValueError("M6 threshold hypotheses must be inside (0,100]")
        if not self.event_risk_outside_matrix:
            raise ValueError("Event Risk must remain outside the M6 100-point matrix")
        if self.probability_status != M6_PROBABILITY_STATUS:
            raise ValueError("M6 probability must remain not calibrated")
        if self.score_semantic != M6_SCORE_SEMANTIC:
            raise ValueError("M6 score semantic mismatch")
        if self.automatic_activation or self.automatic_promotion or self.production_authority:
            raise ValueError("M6 Slice1 has no activation/promotion/production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("M6 policy identity mismatch")


@dataclass(frozen=True, slots=True)
class ConfluenceFamilyEvidence:
    evidence_identity: str
    schema_version: str
    engine_version: str
    family: ConfluenceFamily
    asset: str
    timeframe: str
    regime: str
    as_of_ms: int
    state: MetaEvidenceState
    direction: MetaDirection | None
    directional_strength_0_1: Decimal | None
    evidence_quality_0_1: Decimal | None
    freshness_0_1: Decimal | None
    market_available_at_ms: int | None
    observed_at_ms: int | None
    source_engine_ids: tuple[str, ...]
    source_evidence_identities: tuple[str, ...]
    material_conflict_identities: tuple[str, ...]
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "M6 family evidence identity")
        if self.schema_version != M6_FAMILY_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported M6 family evidence schema")
        if self.engine_version != M6_CONFLUENCE_ENGINE_VERSION:
            raise ValueError("unsupported M6 family evidence engine")
        for text_value, label in (
            (self.asset, "M6 family asset"),
            (self.timeframe, "M6 family timeframe"),
            (self.regime, "M6 family regime"),
        ):
            _require_text(text_value, label)
        if self.as_of_ms < 0:
            raise ValueError("M6 family as_of_ms must be non-negative")
        _require_text_tuple(self.source_engine_ids, "M6 source engine")
        _require_identity_tuple(
            self.source_evidence_identities,
            "M6 source evidence identity",
        )
        _require_identity_tuple(
            self.material_conflict_identities,
            "M6 material conflict identity",
        )
        _require_text_tuple(self.uncertainty_flags, "M6 uncertainty flag")
        if (self.market_available_at_ms is None) != (self.observed_at_ms is None):
            raise ValueError("M6 evidence timestamps must both exist or both be absent")
        if self.market_available_at_ms is not None:
            assert self.observed_at_ms is not None
            if min(self.market_available_at_ms, self.observed_at_ms) < 0:
                raise ValueError("M6 evidence timestamps must be non-negative")
            if self.market_available_at_ms > self.observed_at_ms:
                raise ValueError("M6 evidence cannot be observed before availability")
            if self.observed_at_ms > self.as_of_ms:
                raise ValueError("M6 evidence cannot be observed after as_of")

        measures = (
            self.directional_strength_0_1,
            self.evidence_quality_0_1,
            self.freshness_0_1,
        )
        if self.state in {MetaEvidenceState.OBSERVED, MetaEvidenceState.ABSTAIN}:
            if self.market_available_at_ms is None:
                raise ValueError("measured M6 family evidence requires timestamps")
            if not self.source_engine_ids or not self.source_evidence_identities:
                raise ValueError("measured M6 family evidence requires source evidence")
            if any(value is None for value in measures):
                raise ValueError("measured M6 family evidence requires quality measures")
            for measure_value in measures:
                assert measure_value is not None
                _require_unit_interval(measure_value, "M6 family measure")
            if self.state is MetaEvidenceState.OBSERVED and self.direction is None:
                raise ValueError("observed M6 family evidence requires direction")
            if self.state is MetaEvidenceState.ABSTAIN and self.direction is not None:
                raise ValueError("abstaining M6 family evidence cannot carry direction")
        else:
            if self.direction is not None:
                raise ValueError("unavailable M6 family evidence cannot carry direction")
            if any(value is not None for value in measures):
                raise ValueError("unavailable M6 family evidence cannot carry measures")
            if self.market_available_at_ms is not None:
                raise ValueError("unavailable M6 family evidence cannot carry timestamps")
        if self.evidence_identity != canonical_sha256(_family_evidence_payload(self)):
            raise ValueError("M6 family evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class ConfluenceFamilyContribution:
    family: ConfluenceFamily
    state: MetaEvidenceState
    direction: MetaDirection | None
    prior_weight: Decimal
    directional_strength_0_1: Decimal | None
    support_points: Decimal
    opposition_points: Decimal
    evidence_quality_0_1: Decimal | None
    freshness_0_1: Decimal | None
    material_conflict_count: int
    source_evidence_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.prior_weight <= 0 or self.prior_weight > 1:
            raise ValueError("M6 contribution prior must be inside (0,1]")
        for value in (self.support_points, self.opposition_points):
            if value < 0 or value > 100:
                raise ValueError("M6 contribution points must be inside [0,100]")
        if self.material_conflict_count < 0:
            raise ValueError("M6 material conflict count cannot be negative")
        _require_identity_tuple(
            self.source_evidence_identities,
            "M6 contribution source evidence",
        )


@dataclass(frozen=True, slots=True)
class ConfluenceMatrixSnapshot:
    snapshot_identity: str
    engine_version: str
    policy_identity: str
    asset: str
    timeframe: str
    regime: str
    as_of_ms: int
    candidate_direction: MetaDirection
    family_evidence_identities: tuple[str, ...]
    contributions: tuple[ConfluenceFamilyContribution, ...]
    support_score_0_100: Decimal
    opposition_score_0_100: Decimal
    evidence_coverage_0_100: Decimal
    evidence_quality_0_1: Decimal | None
    freshness_0_1: Decimal | None
    material_conflict_identities: tuple[str, ...]
    resolution: ConfluenceMatrixResolution
    threshold_hypotheses: tuple[Decimal, ...]
    score_semantic: str = M6_SCORE_SEMANTIC
    probability_status: str = M6_PROBABILITY_STATUS
    event_risk_outside_matrix: bool = True
    automatic_activation: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "M6 snapshot identity")
        _require_sha256(self.policy_identity, "M6 snapshot policy identity")
        for text_value, label in (
            (self.asset, "M6 snapshot asset"),
            (self.timeframe, "M6 snapshot timeframe"),
            (self.regime, "M6 snapshot regime"),
        ):
            _require_text(text_value, label)
        if self.engine_version != M6_CONFLUENCE_ENGINE_VERSION:
            raise ValueError("unsupported M6 snapshot engine")
        if self.as_of_ms < 0:
            raise ValueError("M6 snapshot as_of_ms must be non-negative")
        if self.candidate_direction not in {
            MetaDirection.BULLISH,
            MetaDirection.BEARISH,
        }:
            raise ValueError("M6 candidate direction must be bullish or bearish")
        _require_identity_tuple(
            self.family_evidence_identities,
            "M6 family evidence identity",
        )
        if len(self.family_evidence_identities) != len(ConfluenceFamily):
            raise ValueError("M6 snapshot requires exactly five family evidence identities")
        if len(self.contributions) != len(ConfluenceFamily):
            raise ValueError("M6 snapshot requires exactly five family contributions")
        if tuple(item.family for item in self.contributions) != tuple(
            sorted(ConfluenceFamily, key=lambda item: item.value)
        ):
            raise ValueError("M6 contributions must be canonical by family")
        for score_value in (
            self.support_score_0_100,
            self.opposition_score_0_100,
            self.evidence_coverage_0_100,
        ):
            if score_value < 0 or score_value > 100:
                raise ValueError("M6 matrix score must be inside [0,100]")
        for quality_value in (self.evidence_quality_0_1, self.freshness_0_1):
            if quality_value is not None:
                _require_unit_interval(
                    quality_value,
                    "M6 aggregate quality/freshness",
                )
        _require_identity_tuple(
            self.material_conflict_identities,
            "M6 snapshot material conflict",
        )
        if self.resolution is ConfluenceMatrixResolution.MEASURED:
            if self.evidence_coverage_0_100 != Decimal("100.00"):
                raise ValueError("measured M6 snapshot requires full family coverage")
            if self.material_conflict_identities:
                raise ValueError("measured M6 snapshot cannot carry material conflict")
        if (
            self.resolution is ConfluenceMatrixResolution.CONFLICT
            and not self.material_conflict_identities
        ):
            raise ValueError("conflict M6 snapshot requires material conflict evidence")
        if (
            self.resolution is ConfluenceMatrixResolution.ABSTAIN
            and not any(
                item.state is MetaEvidenceState.ABSTAIN
                for item in self.contributions
            )
        ):
            raise ValueError("abstain M6 snapshot requires abstaining family evidence")
        if self.score_semantic != M6_SCORE_SEMANTIC:
            raise ValueError("M6 snapshot score semantic mismatch")
        if self.probability_status != M6_PROBABILITY_STATUS:
            raise ValueError("M6 snapshot probability remains not calibrated")
        if not self.event_risk_outside_matrix:
            raise ValueError("Event Risk must remain outside M6 score")
        if self.automatic_activation or self.production_authority:
            raise ValueError("M6 Slice1 has no activation/production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("M6 snapshot identity mismatch")


def build_locked_m6_policy(
    *,
    policy_version: str = "locked-v1.1-m6-priors/1",
) -> ConfluenceMatrixPolicy:
    priors = tuple(sorted(LOCKED_M6_PRIORS, key=lambda item: item.family.value))
    thresholds = tuple(sorted(LOCKED_M6_THRESHOLD_HYPOTHESES))
    payload = {
        "automatic_activation": False,
        "automatic_promotion": False,
        "engine_version": M6_CONFLUENCE_ENGINE_VERSION,
        "event_risk_outside_matrix": True,
        "policy_version": policy_version,
        "priors": priors,
        "probability_status": M6_PROBABILITY_STATUS,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": M6_CONFLUENCE_POLICY_SCHEMA_VERSION,
        "score_semantic": M6_SCORE_SEMANTIC,
        "threshold_hypotheses": thresholds,
    }
    return ConfluenceMatrixPolicy(
        policy_identity=canonical_sha256(payload),
        schema_version=M6_CONFLUENCE_POLICY_SCHEMA_VERSION,
        engine_version=M6_CONFLUENCE_ENGINE_VERSION,
        policy_version=policy_version,
        priors=priors,
        threshold_hypotheses=thresholds,
    )


def build_confluence_family_evidence(
    *,
    family: ConfluenceFamily,
    asset: str,
    timeframe: str,
    regime: str,
    as_of_ms: int,
    state: MetaEvidenceState,
    direction: MetaDirection | None,
    directional_strength_0_1: Decimal | None,
    evidence_quality_0_1: Decimal | None,
    freshness_0_1: Decimal | None,
    market_available_at_ms: int | None,
    observed_at_ms: int | None,
    source_engine_ids: tuple[str, ...] = (),
    source_evidence_identities: tuple[str, ...] = (),
    material_conflict_identities: tuple[str, ...] = (),
    uncertainty_flags: tuple[str, ...] = (),
) -> ConfluenceFamilyEvidence:
    engines = tuple(sorted(set(source_engine_ids)))
    evidence_ids = tuple(sorted(set(source_evidence_identities)))
    conflicts = tuple(sorted(set(material_conflict_identities)))
    flags = tuple(sorted(set(uncertainty_flags)))
    payload = {
        "as_of_ms": as_of_ms,
        "asset": asset,
        "direction": direction,
        "directional_strength_0_1": directional_strength_0_1,
        "engine_version": M6_CONFLUENCE_ENGINE_VERSION,
        "evidence_quality_0_1": evidence_quality_0_1,
        "family": family,
        "freshness_0_1": freshness_0_1,
        "market_available_at_ms": market_available_at_ms,
        "material_conflict_identities": conflicts,
        "observed_at_ms": observed_at_ms,
        "regime": regime,
        "schema_version": M6_FAMILY_EVIDENCE_SCHEMA_VERSION,
        "source_engine_ids": engines,
        "source_evidence_identities": evidence_ids,
        "state": state,
        "timeframe": timeframe,
        "uncertainty_flags": flags,
    }
    return ConfluenceFamilyEvidence(
        evidence_identity=canonical_sha256(payload),
        schema_version=M6_FAMILY_EVIDENCE_SCHEMA_VERSION,
        engine_version=M6_CONFLUENCE_ENGINE_VERSION,
        family=family,
        asset=asset,
        timeframe=timeframe,
        regime=regime,
        as_of_ms=as_of_ms,
        state=state,
        direction=direction,
        directional_strength_0_1=directional_strength_0_1,
        evidence_quality_0_1=evidence_quality_0_1,
        freshness_0_1=freshness_0_1,
        market_available_at_ms=market_available_at_ms,
        observed_at_ms=observed_at_ms,
        source_engine_ids=engines,
        source_evidence_identities=evidence_ids,
        material_conflict_identities=conflicts,
        uncertainty_flags=flags,
    )


def evaluate_confluence_matrix(
    policy: ConfluenceMatrixPolicy,
    evidence: tuple[ConfluenceFamilyEvidence, ...],
    *,
    candidate_direction: MetaDirection,
    external_material_conflict_identities: tuple[str, ...] = (),
) -> ConfluenceMatrixSnapshot:
    if candidate_direction not in {MetaDirection.BULLISH, MetaDirection.BEARISH}:
        raise ValueError("M6 candidate direction must be bullish or bearish")
    if len(evidence) != len(ConfluenceFamily):
        raise ValueError("M6 evaluation requires exactly five family evidence objects")
    by_family = {item.family: item for item in evidence}
    if len(by_family) != len(ConfluenceFamily) or set(by_family) != set(ConfluenceFamily):
        raise ValueError("M6 evaluation requires exactly one evidence object per family")

    ordered = tuple(by_family[family] for family in sorted(ConfluenceFamily, key=lambda x: x.value))
    first = ordered[0]
    context = (first.asset, first.timeframe, first.regime, first.as_of_ms)
    if any(
        (item.asset, item.timeframe, item.regime, item.as_of_ms) != context
        for item in ordered
    ):
        raise ValueError("M6 family evidence must share exact context")

    from crypto_signal.intelligence.evidence_overlap import (
        analyze_confluence_evidence_overlap,
    )

    overlap_analysis = analyze_confluence_evidence_overlap(ordered)
    external_conflicts = tuple(
        sorted(set(external_material_conflict_identities))
    )
    for identity in external_conflicts:
        _require_sha256(identity, "M6 external material conflict")
    priors = {item.family: item.weight for item in policy.priors}
    opposite = (
        MetaDirection.BEARISH
        if candidate_direction is MetaDirection.BULLISH
        else MetaDirection.BULLISH
    )

    contributions: list[ConfluenceFamilyContribution] = []
    support_total = Decimal(0)
    opposition_total = Decimal(0)
    coverage_weight = Decimal(0)
    quality_weighted = Decimal(0)
    freshness_weighted = Decimal(0)
    measured_weight = Decimal(0)
    conflict_ids: set[str] = set(external_conflicts)

    for item in ordered:
        prior = priors[item.family]
        support_points = Decimal(0)
        opposition_points = Decimal(0)
        if item.state in {MetaEvidenceState.OBSERVED, MetaEvidenceState.ABSTAIN}:
            coverage_weight += prior
            assert item.evidence_quality_0_1 is not None
            assert item.freshness_0_1 is not None
            quality_weighted += prior * item.evidence_quality_0_1
            freshness_weighted += prior * item.freshness_0_1
            measured_weight += prior
        if item.state is MetaEvidenceState.OBSERVED:
            assert item.directional_strength_0_1 is not None
            attribution = overlap_analysis.attribution_factor(item.family)
            if item.direction is candidate_direction:
                support_points = (
                    prior
                    * item.directional_strength_0_1
                    * Decimal(100)
                    * attribution
                )
            elif item.direction is opposite:
                opposition_points = (
                    prior
                    * item.directional_strength_0_1
                    * Decimal(100)
                    * attribution
                )
        support_total += support_points
        opposition_total += opposition_points
        conflict_ids.update(item.material_conflict_identities)
        contributions.append(
            ConfluenceFamilyContribution(
                family=item.family,
                state=item.state,
                direction=item.direction,
                prior_weight=prior,
                directional_strength_0_1=item.directional_strength_0_1,
                support_points=_q(support_points),
                opposition_points=_q(opposition_points),
                evidence_quality_0_1=item.evidence_quality_0_1,
                freshness_0_1=item.freshness_0_1,
                material_conflict_count=len(item.material_conflict_identities),
                source_evidence_identities=item.source_evidence_identities,
            )
        )

    if any(item.state is MetaEvidenceState.ABSTAIN for item in ordered):
        resolution = ConfluenceMatrixResolution.ABSTAIN
    elif conflict_ids:
        resolution = ConfluenceMatrixResolution.CONFLICT
    elif any(item.state is MetaEvidenceState.NOT_EVALUABLE for item in ordered):
        resolution = ConfluenceMatrixResolution.NOT_EVALUABLE
    elif any(item.state is MetaEvidenceState.NO_EVIDENCE for item in ordered):
        resolution = ConfluenceMatrixResolution.PARTIAL
    else:
        resolution = ConfluenceMatrixResolution.MEASURED

    aggregate_quality = (
        None if measured_weight == 0 else quality_weighted / measured_weight
    )
    aggregate_freshness = (
        None if measured_weight == 0 else freshness_weighted / measured_weight
    )
    evidence_ids = tuple(sorted(item.evidence_identity for item in ordered))
    ordered_conflicts = tuple(sorted(conflict_ids))
    support_score = _q(support_total)
    opposition_score = _q(opposition_total)
    coverage_score = _q(coverage_weight * Decimal(100))
    if aggregate_quality is not None:
        aggregate_quality = _q_unit(aggregate_quality)
    if aggregate_freshness is not None:
        aggregate_freshness = _q_unit(aggregate_freshness)

    payload = {
        "as_of_ms": first.as_of_ms,
        "asset": first.asset,
        "automatic_activation": False,
        "candidate_direction": candidate_direction,
        "contributions": tuple(contributions),
        "engine_version": M6_CONFLUENCE_ENGINE_VERSION,
        "event_risk_outside_matrix": True,
        "evidence_coverage_0_100": coverage_score,
        "evidence_quality_0_1": aggregate_quality,
        "family_evidence_identities": evidence_ids,
        "freshness_0_1": aggregate_freshness,
        "material_conflict_identities": ordered_conflicts,
        "opposition_score_0_100": opposition_score,
        "policy_identity": policy.policy_identity,
        "probability_status": M6_PROBABILITY_STATUS,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "regime": first.regime,
        "resolution": resolution,
        "score_semantic": M6_SCORE_SEMANTIC,
        "support_score_0_100": support_score,
        "threshold_hypotheses": policy.threshold_hypotheses,
        "timeframe": first.timeframe,
    }
    return ConfluenceMatrixSnapshot(
        snapshot_identity=canonical_sha256(payload),
        engine_version=M6_CONFLUENCE_ENGINE_VERSION,
        policy_identity=policy.policy_identity,
        asset=first.asset,
        timeframe=first.timeframe,
        regime=first.regime,
        as_of_ms=first.as_of_ms,
        candidate_direction=candidate_direction,
        family_evidence_identities=evidence_ids,
        contributions=tuple(contributions),
        support_score_0_100=support_score,
        opposition_score_0_100=opposition_score,
        evidence_coverage_0_100=coverage_score,
        evidence_quality_0_1=aggregate_quality,
        freshness_0_1=aggregate_freshness,
        material_conflict_identities=ordered_conflicts,
        resolution=resolution,
        threshold_hypotheses=policy.threshold_hypotheses,
    )


def _policy_payload(policy: ConfluenceMatrixPolicy) -> dict[str, object]:
    return {
        "automatic_activation": policy.automatic_activation,
        "automatic_promotion": policy.automatic_promotion,
        "engine_version": policy.engine_version,
        "event_risk_outside_matrix": policy.event_risk_outside_matrix,
        "policy_version": policy.policy_version,
        "priors": policy.priors,
        "probability_status": policy.probability_status,
        "production_authority": policy.production_authority,
        "real_capital": policy.real_capital,
        "schema_version": policy.schema_version,
        "score_semantic": policy.score_semantic,
        "threshold_hypotheses": policy.threshold_hypotheses,
    }


def _family_evidence_payload(
    evidence: ConfluenceFamilyEvidence,
) -> dict[str, object]:
    return {
        "as_of_ms": evidence.as_of_ms,
        "asset": evidence.asset,
        "direction": evidence.direction,
        "directional_strength_0_1": evidence.directional_strength_0_1,
        "engine_version": evidence.engine_version,
        "evidence_quality_0_1": evidence.evidence_quality_0_1,
        "family": evidence.family,
        "freshness_0_1": evidence.freshness_0_1,
        "market_available_at_ms": evidence.market_available_at_ms,
        "material_conflict_identities": evidence.material_conflict_identities,
        "observed_at_ms": evidence.observed_at_ms,
        "regime": evidence.regime,
        "schema_version": evidence.schema_version,
        "source_engine_ids": evidence.source_engine_ids,
        "source_evidence_identities": evidence.source_evidence_identities,
        "state": evidence.state,
        "timeframe": evidence.timeframe,
        "uncertainty_flags": evidence.uncertainty_flags,
    }


def _snapshot_payload(snapshot: ConfluenceMatrixSnapshot) -> dict[str, object]:
    return {
        "as_of_ms": snapshot.as_of_ms,
        "asset": snapshot.asset,
        "automatic_activation": snapshot.automatic_activation,
        "candidate_direction": snapshot.candidate_direction,
        "contributions": snapshot.contributions,
        "engine_version": snapshot.engine_version,
        "event_risk_outside_matrix": snapshot.event_risk_outside_matrix,
        "evidence_coverage_0_100": snapshot.evidence_coverage_0_100,
        "evidence_quality_0_1": snapshot.evidence_quality_0_1,
        "family_evidence_identities": snapshot.family_evidence_identities,
        "freshness_0_1": snapshot.freshness_0_1,
        "material_conflict_identities": snapshot.material_conflict_identities,
        "opposition_score_0_100": snapshot.opposition_score_0_100,
        "policy_identity": snapshot.policy_identity,
        "probability_status": snapshot.probability_status,
        "production_authority": snapshot.production_authority,
        "real_capital": snapshot.real_capital,
        "regime": snapshot.regime,
        "resolution": snapshot.resolution,
        "score_semantic": snapshot.score_semantic,
        "support_score_0_100": snapshot.support_score_0_100,
        "threshold_hypotheses": snapshot.threshold_hypotheses,
        "timeframe": snapshot.timeframe,
    }


def _q(value: Decimal) -> Decimal:
    return value.quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)


def _q_unit(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")


def _require_text_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_text(value, label)


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_unit_interval(value: Decimal, label: str) -> None:
    if (
        value.is_nan()
        or value.is_infinite()
        or value < Decimal(0)
        or value > Decimal(1)
    ):
        raise ValueError(f"{label} must be inside [0,1]")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
