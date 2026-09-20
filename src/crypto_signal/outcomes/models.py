from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.signals.models import SignalState


class OutcomeState(StrEnum):
    SUCCESS_TP1 = "success_tp1"
    SUCCESS_TP2 = "success_tp2"
    SUCCESS_TP3 = "success_tp3"
    FAIL_SL = "fail_sl"
    AMBIGUOUS = "ambiguous"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    INVALIDATED = "invalidated"
    NOT_EVALUABLE = "not_evaluable"


class OutcomeResolutionStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    NOT_EVALUABLE = "not_evaluable"


class EvidenceClass(StrEnum):
    RETROSPECTIVE = "retrospective"
    WALK_FORWARD = "walk_forward"
    LIVE_UNTOUCHED_FORWARD = "live_untouched_forward"


class OutcomeCoverageStatus(StrEnum):
    NO_NEW_EVIDENCE = "no_new_evidence"
    COMPLETE = "complete"
    INCOMPLETE_GAPS = "incomplete_gaps"


class OutcomeAmbiguityReason(StrEnum):
    ENTRY_AND_INVALIDATION_SAME_CANDLE = (
        "entry_and_invalidation_same_candle"
    )
    ENTRY_AND_TARGET_SAME_CANDLE = "entry_and_target_same_candle"
    INVALIDATION_AND_NEW_TARGET_SAME_CANDLE = (
        "invalidation_and_new_target_same_candle"
    )


class OutcomeNotEvaluableReason(StrEnum):
    SIGNAL_NOT_ACTIVE = "signal_not_active"
    MISSING_GEOMETRY = "missing_geometry"
    UNSUPPORTED_TARGET_STRUCTURE = "unsupported_target_structure"
    DATA_GAPS = "data_gaps"


@dataclass(frozen=True, slots=True)
class OutcomeEvaluation:
    outcome_identity: str
    signal_freeze_identity: str
    evidence_class: EvidenceClass
    evaluated_as_of_ms: int
    resolution_status: OutcomeResolutionStatus
    outcome_state: OutcomeState | None
    signal_initial_state: SignalState
    coverage_status: OutcomeCoverageStatus
    max_holding_bars: int
    expected_bar_count: int
    observed_bar_count: int
    missing_open_times_ms: tuple[int, ...]
    skipped_partial_decision_bucket: bool
    entry_observed: bool
    entry_candle_identity: tuple[str, str, str, str, int] | None
    highest_target_index: int
    outcome_candle_identity: tuple[str, str, str, str, int] | None
    ambiguity_reason: OutcomeAmbiguityReason | None
    not_evaluable_reason: OutcomeNotEvaluableReason | None

    def __post_init__(self) -> None:
        if len(self.outcome_identity) != 64:
            raise ValueError("outcome identity must be SHA256")
        try:
            int(self.outcome_identity, 16)
        except ValueError as exc:
            raise ValueError("outcome identity must be hexadecimal") from exc
        if len(self.signal_freeze_identity) != 64:
            raise ValueError("signal freeze identity must be SHA256")
        if self.evaluated_as_of_ms < 0:
            raise ValueError("outcome as-of must be non-negative")
        if self.max_holding_bars <= 0:
            raise ValueError("max_holding_bars must be positive")
        if self.expected_bar_count < 0 or self.observed_bar_count < 0:
            raise ValueError("outcome bar counts must be non-negative")
        if self.observed_bar_count > self.expected_bar_count:
            raise ValueError("observed bars cannot exceed expected bars")
        if tuple(sorted(set(self.missing_open_times_ms))) != (
            self.missing_open_times_ms
        ):
            raise ValueError("missing outcome opens must be sorted and unique")
        if self.coverage_status is OutcomeCoverageStatus.INCOMPLETE_GAPS:
            if not self.missing_open_times_ms:
                raise ValueError("incomplete coverage requires missing opens")
        elif self.missing_open_times_ms:
            raise ValueError("only incomplete coverage may carry missing opens")
        if not 0 <= self.highest_target_index <= 3:
            raise ValueError("highest target index must be between 0 and 3")
        if self.entry_observed != (self.entry_candle_identity is not None):
            raise ValueError("entry observation fields are inconsistent")

        if self.resolution_status is OutcomeResolutionStatus.PENDING:
            if self.outcome_state is not None:
                raise ValueError("pending outcome cannot have outcome state")
            if self.not_evaluable_reason is not None:
                raise ValueError("pending outcome cannot have not-evaluable reason")
        elif self.resolution_status is OutcomeResolutionStatus.NOT_EVALUABLE:
            if self.outcome_state is not OutcomeState.NOT_EVALUABLE:
                raise ValueError(
                    "not-evaluable resolution requires NOT_EVALUABLE state"
                )
            if self.not_evaluable_reason is None:
                raise ValueError(
                    "not-evaluable resolution requires explicit reason"
                )
        else:
            if self.outcome_state is None:
                raise ValueError("resolved outcome requires outcome state")
            if self.outcome_state is OutcomeState.NOT_EVALUABLE:
                raise ValueError(
                    "resolved outcome cannot use NOT_EVALUABLE state"
                )
            if self.not_evaluable_reason is not None:
                raise ValueError(
                    "resolved outcome cannot have not-evaluable reason"
                )

        if self.outcome_state is OutcomeState.AMBIGUOUS:
            if self.ambiguity_reason is None:
                raise ValueError("ambiguous outcome requires explicit reason")
        elif self.ambiguity_reason is not None:
            raise ValueError("only ambiguous outcome may carry ambiguity reason")
