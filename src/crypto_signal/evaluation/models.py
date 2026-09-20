from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.confluence.models import MethodologyKind
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.outcomes.evaluator import verify_outcome_identity
from crypto_signal.outcomes.models import EvidenceClass, OutcomeEvaluation, OutcomeState
from crypto_signal.signals.models import (
    EntryReferenceModel,
    SignalDecision,
    SignalDirection,
)


class ConfluenceScoreBucket(StrEnum):
    SCORE_0 = "score_0"
    SCORE_GT_0_LE_33_33 = "score_gt_0_le_33_33"
    SCORE_GT_33_33_LE_66_67 = "score_gt_33_33_le_66_67"
    SCORE_GT_66_67_LE_100 = "score_gt_66_67_le_100"


class HistoricalFrequencySemantic(StrEnum):
    DESCRIPTIVE_FREQUENCY_NOT_PROBABILITY = (
        "descriptive_frequency_not_probability"
    )


class PromotionSemantic(StrEnum):
    PRODUCT_VISIBILITY_POLICY_NOT_STATISTICAL_SIGNIFICANCE = (
        "product_visibility_policy_not_statistical_significance"
    )


@dataclass(frozen=True, slots=True)
class EvaluatedSignal:
    decision: SignalDecision
    outcome: OutcomeEvaluation
    regime_label: str | None = None

    def __post_init__(self) -> None:
        if self.outcome.signal_freeze_identity != self.decision.freeze_identity:
            raise ValueError("outcome does not belong to signal decision")
        verify_outcome_identity(self.outcome)
        if self.regime_label is not None and not self.regime_label.strip():
            raise ValueError("regime label must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class SegmentKey:
    evidence_class: EvidenceClass
    source_methodology: MethodologyKind | None
    setup_type: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    signal_direction: SignalDirection
    confluence_score_bucket: ConfluenceScoreBucket
    regime_label: str | None
    entry_reference_model: EntryReferenceModel | None
    target_count: int
    target_labels: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.setup_type.strip():
            raise ValueError("segment setup type must be non-empty")
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("segment market identity must be non-empty")
        if self.regime_label is not None and not self.regime_label.strip():
            raise ValueError("segment regime label must be non-empty when provided")
        if self.target_count < 0:
            raise ValueError("target count must be non-negative")
        if self.target_count != len(self.target_labels):
            raise ValueError("target count must equal target label count")
        if len(set(self.target_labels)) != len(self.target_labels):
            raise ValueError("target labels must be unique")


@dataclass(frozen=True, slots=True)
class ShadowRObservation:
    signal_freeze_identity: str
    outcome_state: OutcomeState
    outcome_evaluated_as_of_ms: int
    decision_as_of_ms: int
    value_r: Decimal

    def __post_init__(self) -> None:
        if len(self.signal_freeze_identity) != 64:
            raise ValueError("shadow-R signal identity must be SHA256")
        if self.outcome_evaluated_as_of_ms < 0 or self.decision_as_of_ms < 0:
            raise ValueError("shadow-R timestamps must be non-negative")


@dataclass(frozen=True, slots=True)
class SegmentMetrics:
    key: SegmentKey
    total_n: int
    pending_n: int
    resolved_n: int
    not_evaluable_n: int
    success_n: int
    fail_sl_n: int
    ambiguous_n: int
    timeout_n: int
    cancelled_n: int
    invalidated_n: int
    decisive_n: int
    r_evaluable_n: int
    historical_success_fraction: Decimal | None
    historical_frequency_semantic: HistoricalFrequencySemantic
    r_observations: tuple[ShadowRObservation, ...]
    average_r: Decimal | None
    median_r: Decimal | None
    cumulative_r: Decimal | None
    max_drawdown_r: Decimal | None
    min_r: Decimal | None
    max_r: Decimal | None
    minimum_decisive_sample_size_for_promotion: int
    promotion_eligible: bool
    promotion_semantic: PromotionSemantic

    def __post_init__(self) -> None:
        counts = (
            self.total_n,
            self.pending_n,
            self.resolved_n,
            self.not_evaluable_n,
            self.success_n,
            self.fail_sl_n,
            self.ambiguous_n,
            self.timeout_n,
            self.cancelled_n,
            self.invalidated_n,
            self.decisive_n,
            self.r_evaluable_n,
        )
        if any(value < 0 for value in counts):
            raise ValueError("segment counts must be non-negative")
        if self.total_n != (
            self.pending_n + self.resolved_n + self.not_evaluable_n
        ):
            raise ValueError("segment resolution counts do not equal total")
        if self.decisive_n != self.success_n + self.fail_sl_n:
            raise ValueError("decisive count must equal success + fail_sl")
        if self.r_evaluable_n != len(self.r_observations):
            raise ValueError("R-evaluable count must equal R observation count")
        if self.r_evaluable_n > self.total_n:
            raise ValueError("R-evaluable count cannot exceed total")
        if self.minimum_decisive_sample_size_for_promotion <= 0:
            raise ValueError("promotion sample threshold must be positive")
        if self.promotion_eligible != (
            self.decisive_n
            >= self.minimum_decisive_sample_size_for_promotion
        ):
            raise ValueError("promotion eligibility is inconsistent with threshold")
        if self.historical_success_fraction is None:
            if self.decisive_n != 0:
                raise ValueError(
                    "decisive outcomes require historical success fraction"
                )
        else:
            if self.decisive_n <= 0:
                raise ValueError(
                    "historical success fraction requires decisive outcomes"
                )
            if not Decimal(0) <= self.historical_success_fraction <= Decimal(1):
                raise ValueError(
                    "historical success fraction must be between 0 and 1"
                )

        r_fields = (
            self.average_r,
            self.median_r,
            self.cumulative_r,
            self.max_drawdown_r,
            self.min_r,
            self.max_r,
        )
        if self.r_evaluable_n == 0:
            if any(value is not None for value in r_fields):
                raise ValueError("R statistics require R-evaluable observations")
        else:
            if any(value is None for value in r_fields):
                raise ValueError("R-evaluable observations require all R statistics")
            if self.max_drawdown_r is not None and self.max_drawdown_r < 0:
                raise ValueError("max drawdown R must be non-negative")
