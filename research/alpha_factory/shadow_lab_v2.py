from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.foundation import (
    PromotionGateAssessment,
    PromotionGateStatus,
    RESEARCH_AUTHORITY,
    ResearchExperimentManifest,
)

SHADOW_LAB_V2_ENGINE_VERSION = "r21.5-shadow-lab-v2-slice1/1"
SHADOW_LAB_V2_SCHEMA_VERSION = "r21.5-shadow-lab-v2/1"
SHADOW_AUTHORITY = "shadow_research_only_no_canonical_write"
REAL_CAPITAL = 0


class ShadowResearchFamily(StrEnum):
    CONFLUENCE_THRESHOLD = "confluence_threshold"
    ALTERNATIVE_PRIORS_WEIGHTS = "alternative_priors_weights"
    SCALPING_MICROSTRUCTURE = "scalping_microstructure"
    FRACTIONAL_KELLY = "fractional_kelly"
    ARBITRAGE_MARKET_NEUTRAL = "arbitrage_market_neutral"
    ENTRY_EXIT = "entry_exit"
    HORIZON = "horizon"
    EVENT_WINDOW = "event_window"
    LIQUIDITY_DEFINITION = "liquidity_definition"
    WALLET_FILTER = "wallet_filter"


class ShadowReviewState(StrEnum):
    BLOCKED = "blocked"
    READY_FOR_EXPLICIT_REVIEW = "ready_for_explicit_review"


@dataclass(frozen=True, slots=True)
class ShadowMetric:
    name: str
    value: Decimal
    unit: str
    evidence_identity: str

    def __post_init__(self) -> None:
        _require_text(self.name, "shadow metric name")
        _require_text(self.unit, "shadow metric unit")
        _require_sha256(self.evidence_identity, "shadow metric evidence identity")
        if self.value.is_nan() or self.value.is_infinite():
            raise ValueError("shadow metric value must be finite")


@dataclass(frozen=True, slots=True)
class ShadowVariant:
    variant_identity: str
    schema_version: str
    engine_version: str
    family: ShadowResearchFamily
    name: str
    policy_version: str
    hypothesis: str
    experiment_identity: str
    parameter_identity: str
    untouched_forward_identity: str
    robustness_identity: str
    cost_stress_identity: str
    promotion_assessment_identity: str
    review_state: ShadowReviewState
    metrics: tuple[ShadowMetric, ...]
    authority: str = SHADOW_AUTHORITY
    can_self_promote: bool = False
    champion_write_authority: bool = False
    canonical_capital_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.variant_identity, "shadow variant identity")
        for identity, label in (
            (self.experiment_identity, "shadow experiment identity"),
            (self.parameter_identity, "shadow parameter identity"),
            (self.untouched_forward_identity, "shadow untouched-forward identity"),
            (self.robustness_identity, "shadow robustness identity"),
            (self.cost_stress_identity, "shadow cost-stress identity"),
            (self.promotion_assessment_identity, "shadow promotion assessment identity"),
        ):
            _require_sha256(identity, label)
        if self.schema_version != SHADOW_LAB_V2_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow Lab v2 schema")
        if self.engine_version != SHADOW_LAB_V2_ENGINE_VERSION:
            raise ValueError("unsupported Shadow Lab v2 engine")
        for value, label in (
            (self.name, "shadow variant name"),
            (self.policy_version, "shadow policy version"),
            (self.hypothesis, "shadow hypothesis"),
        ):
            _require_text(value, label)
        if not self.metrics:
            raise ValueError("shadow variant requires descriptive metrics")
        names = tuple(item.name for item in self.metrics)
        if names != tuple(sorted(set(names))):
            raise ValueError("shadow metrics must be unique and sorted by name")
        if self.authority != SHADOW_AUTHORITY:
            raise ValueError("Shadow Lab authority must remain research-only")
        if (
            self.can_self_promote
            or self.champion_write_authority
            or self.canonical_capital_write_authority
            or self.production_authority
        ):
            raise ValueError("Shadow Lab cannot self-promote or mutate canonical state")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.variant_identity != canonical_sha256(_variant_payload(self)):
            raise ValueError("shadow variant identity mismatch")


@dataclass(frozen=True, slots=True)
class ShadowLabComparison:
    comparison_identity: str
    schema_version: str
    engine_version: str
    champion_policy_identity: str
    created_at_ms: int
    variant_identities: tuple[str, ...]
    represented_families: tuple[ShadowResearchFamily, ...]
    review_ready_variant_identities: tuple[str, ...]
    blocked_variant_identities: tuple[str, ...]
    winner_identity: str | None = None
    authority: str = SHADOW_AUTHORITY
    automatic_winner_selection: bool = False
    automatic_promotion: bool = False
    champion_write_authority: bool = False
    canonical_capital_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.comparison_identity, "shadow comparison identity")
        _require_sha256(self.champion_policy_identity, "shadow champion policy identity")
        if self.schema_version != SHADOW_LAB_V2_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow Lab comparison schema")
        if self.engine_version != SHADOW_LAB_V2_ENGINE_VERSION:
            raise ValueError("unsupported Shadow Lab comparison engine")
        if self.created_at_ms < 0:
            raise ValueError("shadow comparison time must be non-negative")
        for values, label in (
            (self.variant_identities, "shadow comparison variant"),
            (self.review_ready_variant_identities, "shadow review-ready variant"),
            (self.blocked_variant_identities, "shadow blocked variant"),
        ):
            _require_identity_tuple(values, label)
        if not self.variant_identities:
            raise ValueError("shadow comparison requires variants")
        if set(self.review_ready_variant_identities).intersection(
            self.blocked_variant_identities
        ):
            raise ValueError("shadow variant cannot be both review-ready and blocked")
        if set(self.review_ready_variant_identities).union(
            self.blocked_variant_identities
        ) != set(self.variant_identities):
            raise ValueError("shadow comparison state partition mismatch")
        if self.represented_families != tuple(
            sorted(set(self.represented_families), key=lambda item: item.value)
        ):
            raise ValueError("shadow represented families must be canonical")
        if self.winner_identity is not None:
            raise ValueError("Shadow Lab comparison cannot select a winner")
        if self.authority != SHADOW_AUTHORITY:
            raise ValueError("Shadow Lab comparison authority must remain research-only")
        if (
            self.automatic_winner_selection
            or self.automatic_promotion
            or self.champion_write_authority
            or self.canonical_capital_write_authority
            or self.production_authority
        ):
            raise ValueError("Shadow Lab comparison cannot promote or mutate canonical state")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.comparison_identity != canonical_sha256(_comparison_payload(self)):
            raise ValueError("shadow comparison identity mismatch")


def build_shadow_variant(
    *,
    family: ShadowResearchFamily,
    name: str,
    policy_version: str,
    hypothesis: str,
    experiment: ResearchExperimentManifest,
    parameter_identity: str,
    untouched_forward_identity: str,
    robustness_identity: str,
    cost_stress_identity: str,
    promotion_assessment: PromotionGateAssessment,
    metrics: tuple[ShadowMetric, ...],
) -> ShadowVariant:
    if experiment.authority != RESEARCH_AUTHORITY:
        raise ValueError("Shadow Lab requires research-only Alpha Factory experiment")
    if promotion_assessment.experiment_identity != experiment.experiment_identity:
        raise ValueError("shadow promotion assessment/experiment mismatch")
    review_state = (
        ShadowReviewState.BLOCKED
        if promotion_assessment.status is PromotionGateStatus.BLOCKED
        else ShadowReviewState.READY_FOR_EXPLICIT_REVIEW
    )
    ordered_metrics = tuple(sorted(metrics, key=lambda item: item.name))
    payload = {
        "authority": SHADOW_AUTHORITY,
        "can_self_promote": False,
        "canonical_capital_write_authority": False,
        "champion_write_authority": False,
        "cost_stress_identity": cost_stress_identity,
        "engine_version": SHADOW_LAB_V2_ENGINE_VERSION,
        "experiment_identity": experiment.experiment_identity,
        "family": family,
        "hypothesis": hypothesis,
        "metrics": ordered_metrics,
        "name": name,
        "parameter_identity": parameter_identity,
        "policy_version": policy_version,
        "production_authority": False,
        "promotion_assessment_identity": promotion_assessment.assessment_identity,
        "real_capital": REAL_CAPITAL,
        "review_state": review_state,
        "robustness_identity": robustness_identity,
        "schema_version": SHADOW_LAB_V2_SCHEMA_VERSION,
        "untouched_forward_identity": untouched_forward_identity,
    }
    return ShadowVariant(
        variant_identity=canonical_sha256(payload),
        schema_version=SHADOW_LAB_V2_SCHEMA_VERSION,
        engine_version=SHADOW_LAB_V2_ENGINE_VERSION,
        family=family,
        name=name,
        policy_version=policy_version,
        hypothesis=hypothesis,
        experiment_identity=experiment.experiment_identity,
        parameter_identity=parameter_identity,
        untouched_forward_identity=untouched_forward_identity,
        robustness_identity=robustness_identity,
        cost_stress_identity=cost_stress_identity,
        promotion_assessment_identity=promotion_assessment.assessment_identity,
        review_state=review_state,
        metrics=ordered_metrics,
    )


def build_shadow_lab_comparison(
    *,
    champion_policy_identity: str,
    created_at_ms: int,
    variants: tuple[ShadowVariant, ...],
) -> ShadowLabComparison:
    _require_sha256(champion_policy_identity, "shadow champion policy identity")
    by_identity = {item.variant_identity: item for item in variants}
    if len(by_identity) != len(variants):
        raise ValueError("shadow comparison variant identities must be unique")
    if not variants:
        raise ValueError("shadow comparison requires variants")
    ordered = tuple(sorted(variants, key=lambda item: item.variant_identity))
    variant_ids = tuple(item.variant_identity for item in ordered)
    ready = tuple(
        item.variant_identity
        for item in ordered
        if item.review_state is ShadowReviewState.READY_FOR_EXPLICIT_REVIEW
    )
    blocked = tuple(
        item.variant_identity
        for item in ordered
        if item.review_state is ShadowReviewState.BLOCKED
    )
    families = tuple(sorted({item.family for item in ordered}, key=lambda item: item.value))
    payload = {
        "authority": SHADOW_AUTHORITY,
        "automatic_promotion": False,
        "automatic_winner_selection": False,
        "blocked_variant_identities": blocked,
        "canonical_capital_write_authority": False,
        "champion_policy_identity": champion_policy_identity,
        "champion_write_authority": False,
        "created_at_ms": created_at_ms,
        "engine_version": SHADOW_LAB_V2_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "represented_families": families,
        "review_ready_variant_identities": ready,
        "schema_version": SHADOW_LAB_V2_SCHEMA_VERSION,
        "variant_identities": variant_ids,
        "winner_identity": None,
    }
    return ShadowLabComparison(
        comparison_identity=canonical_sha256(payload),
        schema_version=SHADOW_LAB_V2_SCHEMA_VERSION,
        engine_version=SHADOW_LAB_V2_ENGINE_VERSION,
        champion_policy_identity=champion_policy_identity,
        created_at_ms=created_at_ms,
        variant_identities=variant_ids,
        represented_families=families,
        review_ready_variant_identities=ready,
        blocked_variant_identities=blocked,
    )


def _variant_payload(variant: ShadowVariant) -> dict[str, object]:
    return {
        "authority": variant.authority,
        "can_self_promote": variant.can_self_promote,
        "canonical_capital_write_authority": variant.canonical_capital_write_authority,
        "champion_write_authority": variant.champion_write_authority,
        "cost_stress_identity": variant.cost_stress_identity,
        "engine_version": variant.engine_version,
        "experiment_identity": variant.experiment_identity,
        "family": variant.family,
        "hypothesis": variant.hypothesis,
        "metrics": variant.metrics,
        "name": variant.name,
        "parameter_identity": variant.parameter_identity,
        "policy_version": variant.policy_version,
        "production_authority": variant.production_authority,
        "promotion_assessment_identity": variant.promotion_assessment_identity,
        "real_capital": variant.real_capital,
        "review_state": variant.review_state,
        "robustness_identity": variant.robustness_identity,
        "schema_version": variant.schema_version,
        "untouched_forward_identity": variant.untouched_forward_identity,
    }


def _comparison_payload(comparison: ShadowLabComparison) -> dict[str, object]:
    return {
        "authority": comparison.authority,
        "automatic_promotion": comparison.automatic_promotion,
        "automatic_winner_selection": comparison.automatic_winner_selection,
        "blocked_variant_identities": comparison.blocked_variant_identities,
        "canonical_capital_write_authority": comparison.canonical_capital_write_authority,
        "champion_policy_identity": comparison.champion_policy_identity,
        "champion_write_authority": comparison.champion_write_authority,
        "created_at_ms": comparison.created_at_ms,
        "engine_version": comparison.engine_version,
        "production_authority": comparison.production_authority,
        "real_capital": comparison.real_capital,
        "represented_families": comparison.represented_families,
        "review_ready_variant_identities": comparison.review_ready_variant_identities,
        "schema_version": comparison.schema_version,
        "variant_identities": comparison.variant_identities,
        "winner_identity": comparison.winner_identity,
    }


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} identities must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
