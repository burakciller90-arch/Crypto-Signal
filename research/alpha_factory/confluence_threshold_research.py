from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from crypto_signal.intelligence.confluence_matrix_v2 import (
    LOCKED_M6_THRESHOLD_HYPOTHESES,
    ConfluenceMatrixPolicy,
    ConfluenceMatrixResolution,
    ConfluenceMatrixSnapshot,
)
from crypto_signal.intelligence.meta_intelligence import MetaDirection
from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.foundation import PartitionRole, ResearchPartition

M6_THRESHOLD_RESEARCH_ENGINE_VERSION = "m6-threshold-forward-research-v1-slice2/1"
M6_THRESHOLD_RESEARCH_SCHEMA_VERSION = "m6-threshold-forward-research-v1/1"
M6_THRESHOLD_RESEARCH_SEMANTIC = (
    "descriptive_chronological_forward_comparison_not_selection_or_probability"
)
M6_THRESHOLD_RESULT_SEMANTIC = "descriptive_net_outcome_summary_not_probability"
REAL_CAPITAL = 0
_R_QUANTUM = Decimal("0.0001")
_FRACTION_QUANTUM = Decimal("0.0001")


class ThresholdResearchStatus(StrEnum):
    EVALUATED = "evaluated"
    NOT_YET_EVALUABLE = "not_yet_evaluable"
    NO_EVIDENCE = "no_evidence"


@dataclass(frozen=True, slots=True)
class ConfluenceThresholdResearchConfig:
    config_identity: str
    schema_version: str
    engine_version: str
    matrix_policy_identity: str
    thresholds: tuple[Decimal, ...]
    created_at_ms: int
    window_start_ms: int
    window_end_ms: int
    outcome_definition: str
    semantic: str = M6_THRESHOLD_RESEARCH_SEMANTIC
    automatic_winner_selection: bool = False
    automatic_promotion: bool = False
    calibrated_probability_claim: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.config_identity, "M6 threshold config identity")
        _require_sha256(self.matrix_policy_identity, "M6 matrix policy identity")
        if self.schema_version != M6_THRESHOLD_RESEARCH_SCHEMA_VERSION:
            raise ValueError("unsupported M6 threshold research schema")
        if self.engine_version != M6_THRESHOLD_RESEARCH_ENGINE_VERSION:
            raise ValueError("unsupported M6 threshold research engine")
        if self.thresholds != LOCKED_M6_THRESHOLD_HYPOTHESES:
            raise ValueError("M6 threshold research must compare locked 70/75/80/85")
        if self.created_at_ms < 0 or self.window_start_ms < 0:
            raise ValueError("M6 threshold research timestamps must be non-negative")
        if self.window_end_ms <= self.window_start_ms:
            raise ValueError("M6 threshold research requires start before end")
        if self.created_at_ms >= self.window_start_ms:
            raise ValueError("M6 threshold config must predate forward window")
        if not self.outcome_definition.strip():
            raise ValueError("M6 threshold outcome_definition must be non-empty")
        if self.semantic != M6_THRESHOLD_RESEARCH_SEMANTIC:
            raise ValueError("M6 threshold research semantic mismatch")
        if (
            self.automatic_winner_selection
            or self.automatic_promotion
            or self.calibrated_probability_claim
            or self.production_authority
        ):
            raise ValueError(
                "M6 threshold research cannot select, promote, calibrate or deploy"
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.config_identity != canonical_sha256(_config_payload(self)):
            raise ValueError("M6 threshold config identity mismatch")


@dataclass(frozen=True, slots=True)
class ConfluenceThresholdForwardObservation:
    observation_identity: str
    schema_version: str
    engine_version: str
    matrix_snapshot_identity: str
    matrix_policy_identity: str
    candidate_direction: MetaDirection
    decision_as_of_ms: int
    outcome_available_at_ms: int
    support_score_0_100: Decimal
    opposition_score_0_100: Decimal
    matrix_resolution: ConfluenceMatrixResolution
    evidence_coverage_0_100: Decimal
    evidence_quality_0_1: Decimal | None
    freshness_0_1: Decimal | None
    material_conflict_count: int
    gross_outcome_r: Decimal
    explicit_cost_r: Decimal
    net_outcome_r: Decimal
    source_outcome_identity: str

    def __post_init__(self) -> None:
        _require_sha256(
            self.observation_identity,
            "M6 threshold observation identity",
        )
        _require_sha256(
            self.matrix_snapshot_identity,
            "M6 threshold matrix snapshot identity",
        )
        _require_sha256(
            self.matrix_policy_identity,
            "M6 threshold matrix policy identity",
        )
        _require_sha256(
            self.source_outcome_identity,
            "M6 threshold source outcome identity",
        )
        if self.schema_version != M6_THRESHOLD_RESEARCH_SCHEMA_VERSION:
            raise ValueError("unsupported M6 threshold observation schema")
        if self.engine_version != M6_THRESHOLD_RESEARCH_ENGINE_VERSION:
            raise ValueError("unsupported M6 threshold observation engine")
        if self.candidate_direction not in {
            MetaDirection.BULLISH,
            MetaDirection.BEARISH,
        }:
            raise ValueError("M6 threshold candidate direction must be directional")
        if min(self.decision_as_of_ms, self.outcome_available_at_ms) < 0:
            raise ValueError("M6 threshold observation timestamps must be non-negative")
        if self.outcome_available_at_ms <= self.decision_as_of_ms:
            raise ValueError("M6 threshold outcome must become available after decision")
        for score_value in (
            self.support_score_0_100,
            self.opposition_score_0_100,
            self.evidence_coverage_0_100,
        ):
            if score_value < 0 or score_value > 100:
                raise ValueError("M6 threshold score must be inside [0,100]")
        for quality_value in (self.evidence_quality_0_1, self.freshness_0_1):
            if quality_value is not None:
                _require_unit_interval(
                    quality_value,
                    "M6 threshold quality/freshness",
                )
        if self.material_conflict_count < 0:
            raise ValueError("M6 threshold conflict count cannot be negative")
        if self.explicit_cost_r < 0:
            raise ValueError("M6 threshold explicit cost cannot be negative")
        if self.net_outcome_r != self.gross_outcome_r - self.explicit_cost_r:
            raise ValueError("M6 threshold net outcome must equal gross minus cost")
        if self.observation_identity != canonical_sha256(
            _forward_observation_payload(self)
        ):
            raise ValueError("M6 threshold observation identity mismatch")


@dataclass(frozen=True, slots=True)
class ConfluenceThresholdResult:
    result_identity: str
    schema_version: str
    engine_version: str
    threshold: Decimal
    eligible_decision_count: int
    activation_count: int
    blocked_count: int
    positive_net_count: int
    negative_net_count: int
    flat_net_count: int
    gross_r_total: Decimal
    explicit_cost_r_total: Decimal
    net_r_total: Decimal
    mean_net_r: Decimal | None
    positive_net_fraction: Decimal | None
    semantic: str = M6_THRESHOLD_RESULT_SEMANTIC
    calibrated_probability_claim: bool = False
    winner_selected: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.result_identity, "M6 threshold result identity")
        if self.schema_version != M6_THRESHOLD_RESEARCH_SCHEMA_VERSION:
            raise ValueError("unsupported M6 threshold result schema")
        if self.engine_version != M6_THRESHOLD_RESEARCH_ENGINE_VERSION:
            raise ValueError("unsupported M6 threshold result engine")
        if self.threshold not in LOCKED_M6_THRESHOLD_HYPOTHESES:
            raise ValueError("unsupported M6 threshold hypothesis")
        if min(
            self.eligible_decision_count,
            self.activation_count,
            self.blocked_count,
            self.positive_net_count,
            self.negative_net_count,
            self.flat_net_count,
        ) < 0:
            raise ValueError("M6 threshold result counts cannot be negative")
        if self.activation_count + self.blocked_count != self.eligible_decision_count:
            raise ValueError("M6 threshold activation/blocked count mismatch")
        if (
            self.positive_net_count
            + self.negative_net_count
            + self.flat_net_count
            != self.activation_count
        ):
            raise ValueError("M6 threshold outcome count mismatch")
        if self.explicit_cost_r_total < 0:
            raise ValueError("M6 threshold total explicit cost cannot be negative")
        if self.net_r_total != self.gross_r_total - self.explicit_cost_r_total:
            raise ValueError("M6 threshold total net R must equal gross minus cost")
        if self.activation_count == 0:
            if self.mean_net_r is not None or self.positive_net_fraction is not None:
                raise ValueError("empty M6 threshold activation cannot expose means")
        else:
            if self.mean_net_r is None or self.positive_net_fraction is None:
                raise ValueError("M6 threshold activation requires descriptive means")
            _require_unit_interval(
                self.positive_net_fraction,
                "M6 threshold positive net fraction",
            )
        if self.semantic != M6_THRESHOLD_RESULT_SEMANTIC:
            raise ValueError("M6 threshold result semantic mismatch")
        if self.calibrated_probability_claim or self.winner_selected:
            raise ValueError("M6 threshold result cannot claim probability or winner")
        if self.production_authority:
            raise ValueError("M6 threshold result has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.result_identity != canonical_sha256(_result_payload(self)):
            raise ValueError("M6 threshold result identity mismatch")


@dataclass(frozen=True, slots=True)
class ConfluenceThresholdResearchManifest:
    manifest_identity: str
    schema_version: str
    engine_version: str
    config_identity: str
    partition_identity: str
    status: ThresholdResearchStatus
    observation_identities: tuple[str, ...]
    result_identities: tuple[str, ...]
    semantic: str = M6_THRESHOLD_RESEARCH_SEMANTIC
    automatic_winner_selection: bool = False
    automatic_promotion: bool = False
    calibrated_probability_claim: bool = False
    threshold_winner: Decimal | None = None
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.manifest_identity, "M6 threshold manifest identity")
        _require_sha256(self.config_identity, "M6 threshold manifest config identity")
        _require_sha256(
            self.partition_identity,
            "M6 threshold manifest partition identity",
        )
        if self.schema_version != M6_THRESHOLD_RESEARCH_SCHEMA_VERSION:
            raise ValueError("unsupported M6 threshold manifest schema")
        if self.engine_version != M6_THRESHOLD_RESEARCH_ENGINE_VERSION:
            raise ValueError("unsupported M6 threshold manifest engine")
        _require_identity_tuple(
            self.observation_identities,
            "M6 threshold manifest observation",
        )
        _require_identity_tuple(
            self.result_identities,
            "M6 threshold manifest result",
        )
        if self.status is ThresholdResearchStatus.EVALUATED:
            if not self.observation_identities or not self.result_identities:
                raise ValueError("evaluated M6 threshold manifest requires evidence/results")
        else:
            if self.result_identities:
                raise ValueError("unevaluated M6 threshold manifest cannot expose results")
        if self.semantic != M6_THRESHOLD_RESEARCH_SEMANTIC:
            raise ValueError("M6 threshold manifest semantic mismatch")
        if (
            self.automatic_winner_selection
            or self.automatic_promotion
            or self.calibrated_probability_claim
            or self.threshold_winner is not None
            or self.production_authority
        ):
            raise ValueError(
                "M6 threshold manifest cannot select, promote, calibrate or deploy"
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.manifest_identity != canonical_sha256(_manifest_payload(self)):
            raise ValueError("M6 threshold manifest identity mismatch")


def build_confluence_threshold_research_config(
    policy: ConfluenceMatrixPolicy,
    *,
    created_at_ms: int,
    window_start_ms: int,
    window_end_ms: int,
    outcome_definition: str,
) -> ConfluenceThresholdResearchConfig:
    thresholds = policy.threshold_hypotheses
    if thresholds != LOCKED_M6_THRESHOLD_HYPOTHESES:
        raise ValueError("M6 policy does not contain locked threshold hypotheses")
    payload = {
        "automatic_promotion": False,
        "automatic_winner_selection": False,
        "calibrated_probability_claim": False,
        "created_at_ms": created_at_ms,
        "engine_version": M6_THRESHOLD_RESEARCH_ENGINE_VERSION,
        "matrix_policy_identity": policy.policy_identity,
        "outcome_definition": outcome_definition,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": M6_THRESHOLD_RESEARCH_SCHEMA_VERSION,
        "semantic": M6_THRESHOLD_RESEARCH_SEMANTIC,
        "thresholds": thresholds,
        "window_end_ms": window_end_ms,
        "window_start_ms": window_start_ms,
    }
    return ConfluenceThresholdResearchConfig(
        config_identity=canonical_sha256(payload),
        schema_version=M6_THRESHOLD_RESEARCH_SCHEMA_VERSION,
        engine_version=M6_THRESHOLD_RESEARCH_ENGINE_VERSION,
        matrix_policy_identity=policy.policy_identity,
        thresholds=thresholds,
        created_at_ms=created_at_ms,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        outcome_definition=outcome_definition,
    )


def build_confluence_threshold_forward_observation(
    snapshot: ConfluenceMatrixSnapshot,
    *,
    outcome_available_at_ms: int,
    gross_outcome_r: Decimal,
    explicit_cost_r: Decimal,
    source_outcome_identity: str,
) -> ConfluenceThresholdForwardObservation:
    net = gross_outcome_r - explicit_cost_r
    payload = {
        "candidate_direction": snapshot.candidate_direction,
        "decision_as_of_ms": snapshot.as_of_ms,
        "engine_version": M6_THRESHOLD_RESEARCH_ENGINE_VERSION,
        "evidence_coverage_0_100": snapshot.evidence_coverage_0_100,
        "evidence_quality_0_1": snapshot.evidence_quality_0_1,
        "explicit_cost_r": explicit_cost_r,
        "freshness_0_1": snapshot.freshness_0_1,
        "gross_outcome_r": gross_outcome_r,
        "material_conflict_count": len(snapshot.material_conflict_identities),
        "matrix_policy_identity": snapshot.policy_identity,
        "matrix_resolution": snapshot.resolution,
        "matrix_snapshot_identity": snapshot.snapshot_identity,
        "net_outcome_r": net,
        "opposition_score_0_100": snapshot.opposition_score_0_100,
        "outcome_available_at_ms": outcome_available_at_ms,
        "schema_version": M6_THRESHOLD_RESEARCH_SCHEMA_VERSION,
        "source_outcome_identity": source_outcome_identity,
        "support_score_0_100": snapshot.support_score_0_100,
    }
    return ConfluenceThresholdForwardObservation(
        observation_identity=canonical_sha256(payload),
        schema_version=M6_THRESHOLD_RESEARCH_SCHEMA_VERSION,
        engine_version=M6_THRESHOLD_RESEARCH_ENGINE_VERSION,
        matrix_snapshot_identity=snapshot.snapshot_identity,
        matrix_policy_identity=snapshot.policy_identity,
        candidate_direction=snapshot.candidate_direction,
        decision_as_of_ms=snapshot.as_of_ms,
        outcome_available_at_ms=outcome_available_at_ms,
        support_score_0_100=snapshot.support_score_0_100,
        opposition_score_0_100=snapshot.opposition_score_0_100,
        matrix_resolution=snapshot.resolution,
        evidence_coverage_0_100=snapshot.evidence_coverage_0_100,
        evidence_quality_0_1=snapshot.evidence_quality_0_1,
        freshness_0_1=snapshot.freshness_0_1,
        material_conflict_count=len(snapshot.material_conflict_identities),
        gross_outcome_r=gross_outcome_r,
        explicit_cost_r=explicit_cost_r,
        net_outcome_r=net,
        source_outcome_identity=source_outcome_identity,
    )


def evaluate_confluence_threshold_hypotheses(
    config: ConfluenceThresholdResearchConfig,
    partition: ResearchPartition,
    observations: Sequence[ConfluenceThresholdForwardObservation] = (),
    *,
    as_of_ms: int,
) -> tuple[
    tuple[ConfluenceThresholdResult, ...],
    ConfluenceThresholdResearchManifest,
]:
    if partition.role is not PartitionRole.UNTOUCHED_FORWARD:
        raise ValueError("M6 threshold research requires UNTOUCHED_FORWARD partition")
    if (
        partition.start_ms != config.window_start_ms
        or partition.end_ms != config.window_end_ms
    ):
        raise ValueError("M6 threshold partition does not match frozen window")
    if as_of_ms < 0:
        raise ValueError("M6 threshold evaluation as_of_ms must be non-negative")

    if as_of_ms < config.window_end_ms:
        return (), _manifest(
            config=config,
            partition=partition,
            status=ThresholdResearchStatus.NOT_YET_EVALUABLE,
            observations=(),
            results=(),
        )

    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.decision_as_of_ms,
                item.matrix_snapshot_identity,
                item.observation_identity,
            ),
        )
    )
    if not ordered:
        return (), _manifest(
            config=config,
            partition=partition,
            status=ThresholdResearchStatus.NO_EVIDENCE,
            observations=(),
            results=(),
        )

    _validate_forward_evidence(config, partition, ordered)
    results = tuple(
        _evaluate_threshold(threshold, ordered)
        for threshold in config.thresholds
    )
    return results, _manifest(
        config=config,
        partition=partition,
        status=ThresholdResearchStatus.EVALUATED,
        observations=ordered,
        results=results,
    )


def _validate_forward_evidence(
    config: ConfluenceThresholdResearchConfig,
    partition: ResearchPartition,
    observations: tuple[ConfluenceThresholdForwardObservation, ...],
) -> None:
    if len(observations) != partition.row_count:
        raise ValueError("M6 threshold observation count must match forward partition")
    snapshot_ids = tuple(sorted(item.matrix_snapshot_identity for item in observations))
    if len(set(snapshot_ids)) != len(snapshot_ids):
        raise ValueError("M6 threshold forward snapshots must be unique")
    if snapshot_ids != partition.evidence_identities:
        raise ValueError("M6 threshold forward snapshots do not match partition evidence")
    observation_ids = tuple(sorted(item.observation_identity for item in observations))
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("M6 threshold forward observations must be unique")

    for item in observations:
        if item.matrix_policy_identity != config.matrix_policy_identity:
            raise ValueError("M6 threshold observation policy mismatch")
        if not config.window_start_ms <= item.decision_as_of_ms < config.window_end_ms:
            raise ValueError("M6 threshold decision lies outside frozen forward window")
        if item.outcome_available_at_ms > config.window_end_ms:
            raise ValueError("M6 threshold outcome unavailable by forward window end")


def _evaluate_threshold(
    threshold: Decimal,
    observations: tuple[ConfluenceThresholdForwardObservation, ...],
) -> ConfluenceThresholdResult:
    activated = tuple(
        item
        for item in observations
        if (
            item.matrix_resolution is ConfluenceMatrixResolution.MEASURED
            and item.support_score_0_100 >= threshold
        )
    )
    positive = sum(item.net_outcome_r > 0 for item in activated)
    negative = sum(item.net_outcome_r < 0 for item in activated)
    flat = sum(item.net_outcome_r == 0 for item in activated)
    gross_total = sum(
        (item.gross_outcome_r for item in activated),
        start=Decimal(0),
    )
    cost_total = sum(
        (item.explicit_cost_r for item in activated),
        start=Decimal(0),
    )
    net_total = gross_total - cost_total
    activation_count = len(activated)
    mean_net = (
        None
        if activation_count == 0
        else _q_r(net_total / Decimal(activation_count))
    )
    positive_fraction = (
        None
        if activation_count == 0
        else _q_fraction(Decimal(positive) / Decimal(activation_count))
    )
    gross_total = _q_r(gross_total)
    cost_total = _q_r(cost_total)
    net_total = _q_r(net_total)
    payload = {
        "activation_count": activation_count,
        "blocked_count": len(observations) - activation_count,
        "calibrated_probability_claim": False,
        "eligible_decision_count": len(observations),
        "engine_version": M6_THRESHOLD_RESEARCH_ENGINE_VERSION,
        "explicit_cost_r_total": cost_total,
        "flat_net_count": flat,
        "gross_r_total": gross_total,
        "mean_net_r": mean_net,
        "negative_net_count": negative,
        "net_r_total": net_total,
        "positive_net_count": positive,
        "positive_net_fraction": positive_fraction,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": M6_THRESHOLD_RESEARCH_SCHEMA_VERSION,
        "semantic": M6_THRESHOLD_RESULT_SEMANTIC,
        "threshold": threshold,
        "winner_selected": False,
    }
    return ConfluenceThresholdResult(
        result_identity=canonical_sha256(payload),
        schema_version=M6_THRESHOLD_RESEARCH_SCHEMA_VERSION,
        engine_version=M6_THRESHOLD_RESEARCH_ENGINE_VERSION,
        threshold=threshold,
        eligible_decision_count=len(observations),
        activation_count=activation_count,
        blocked_count=len(observations) - activation_count,
        positive_net_count=positive,
        negative_net_count=negative,
        flat_net_count=flat,
        gross_r_total=gross_total,
        explicit_cost_r_total=cost_total,
        net_r_total=net_total,
        mean_net_r=mean_net,
        positive_net_fraction=positive_fraction,
    )


def _manifest(
    *,
    config: ConfluenceThresholdResearchConfig,
    partition: ResearchPartition,
    status: ThresholdResearchStatus,
    observations: tuple[ConfluenceThresholdForwardObservation, ...],
    results: tuple[ConfluenceThresholdResult, ...],
) -> ConfluenceThresholdResearchManifest:
    observation_ids = tuple(sorted(item.observation_identity for item in observations))
    result_ids = tuple(sorted(item.result_identity for item in results))
    payload = {
        "automatic_promotion": False,
        "automatic_winner_selection": False,
        "calibrated_probability_claim": False,
        "config_identity": config.config_identity,
        "engine_version": M6_THRESHOLD_RESEARCH_ENGINE_VERSION,
        "observation_identities": observation_ids,
        "partition_identity": partition.partition_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "result_identities": result_ids,
        "schema_version": M6_THRESHOLD_RESEARCH_SCHEMA_VERSION,
        "semantic": M6_THRESHOLD_RESEARCH_SEMANTIC,
        "status": status,
        "threshold_winner": None,
    }
    return ConfluenceThresholdResearchManifest(
        manifest_identity=canonical_sha256(payload),
        schema_version=M6_THRESHOLD_RESEARCH_SCHEMA_VERSION,
        engine_version=M6_THRESHOLD_RESEARCH_ENGINE_VERSION,
        config_identity=config.config_identity,
        partition_identity=partition.partition_identity,
        status=status,
        observation_identities=observation_ids,
        result_identities=result_ids,
    )


def _config_payload(config: ConfluenceThresholdResearchConfig) -> dict[str, object]:
    return {
        "automatic_promotion": config.automatic_promotion,
        "automatic_winner_selection": config.automatic_winner_selection,
        "calibrated_probability_claim": config.calibrated_probability_claim,
        "created_at_ms": config.created_at_ms,
        "engine_version": config.engine_version,
        "matrix_policy_identity": config.matrix_policy_identity,
        "outcome_definition": config.outcome_definition,
        "production_authority": config.production_authority,
        "real_capital": config.real_capital,
        "schema_version": config.schema_version,
        "semantic": config.semantic,
        "thresholds": config.thresholds,
        "window_end_ms": config.window_end_ms,
        "window_start_ms": config.window_start_ms,
    }


def _forward_observation_payload(
    observation: ConfluenceThresholdForwardObservation,
) -> dict[str, object]:
    return {
        "candidate_direction": observation.candidate_direction,
        "decision_as_of_ms": observation.decision_as_of_ms,
        "engine_version": observation.engine_version,
        "evidence_coverage_0_100": observation.evidence_coverage_0_100,
        "evidence_quality_0_1": observation.evidence_quality_0_1,
        "explicit_cost_r": observation.explicit_cost_r,
        "freshness_0_1": observation.freshness_0_1,
        "gross_outcome_r": observation.gross_outcome_r,
        "material_conflict_count": observation.material_conflict_count,
        "matrix_policy_identity": observation.matrix_policy_identity,
        "matrix_resolution": observation.matrix_resolution,
        "matrix_snapshot_identity": observation.matrix_snapshot_identity,
        "net_outcome_r": observation.net_outcome_r,
        "opposition_score_0_100": observation.opposition_score_0_100,
        "outcome_available_at_ms": observation.outcome_available_at_ms,
        "schema_version": observation.schema_version,
        "source_outcome_identity": observation.source_outcome_identity,
        "support_score_0_100": observation.support_score_0_100,
    }


def _result_payload(result: ConfluenceThresholdResult) -> dict[str, object]:
    return {
        "activation_count": result.activation_count,
        "blocked_count": result.blocked_count,
        "calibrated_probability_claim": result.calibrated_probability_claim,
        "eligible_decision_count": result.eligible_decision_count,
        "engine_version": result.engine_version,
        "explicit_cost_r_total": result.explicit_cost_r_total,
        "flat_net_count": result.flat_net_count,
        "gross_r_total": result.gross_r_total,
        "mean_net_r": result.mean_net_r,
        "negative_net_count": result.negative_net_count,
        "net_r_total": result.net_r_total,
        "positive_net_count": result.positive_net_count,
        "positive_net_fraction": result.positive_net_fraction,
        "production_authority": result.production_authority,
        "real_capital": result.real_capital,
        "schema_version": result.schema_version,
        "semantic": result.semantic,
        "threshold": result.threshold,
        "winner_selected": result.winner_selected,
    }


def _manifest_payload(
    manifest: ConfluenceThresholdResearchManifest,
) -> dict[str, object]:
    return {
        "automatic_promotion": manifest.automatic_promotion,
        "automatic_winner_selection": manifest.automatic_winner_selection,
        "calibrated_probability_claim": manifest.calibrated_probability_claim,
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "observation_identities": manifest.observation_identities,
        "partition_identity": manifest.partition_identity,
        "production_authority": manifest.production_authority,
        "real_capital": manifest.real_capital,
        "result_identities": manifest.result_identities,
        "schema_version": manifest.schema_version,
        "semantic": manifest.semantic,
        "status": manifest.status,
        "threshold_winner": manifest.threshold_winner,
    }


def _q_r(value: Decimal) -> Decimal:
    return value.quantize(_R_QUANTUM, rounding=ROUND_HALF_UP)


def _q_fraction(value: Decimal) -> Decimal:
    return value.quantize(_FRACTION_QUANTUM, rounding=ROUND_HALF_UP)


def _require_unit_interval(value: Decimal, label: str) -> None:
    if (
        value.is_nan()
        or value.is_infinite()
        or value < Decimal(0)
        or value > Decimal(1)
    ):
        raise ValueError(f"{label} must be inside [0,1]")


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
