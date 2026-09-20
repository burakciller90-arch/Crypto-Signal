from __future__ import annotations

from decimal import Decimal
from typing import Any

from crypto_signal.confluence.models import (
    EvidenceDirection,
    InvalidationTrigger,
    MethodologyKind,
    MethodologyPairRelation,
    PairRelation,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeAmbiguityReason,
    OutcomeCoverageStatus,
    OutcomeEvaluation,
    OutcomeNotEvaluableReason,
    OutcomeResolutionStatus,
    OutcomeState,
)
from crypto_signal.signals.models import (
    EntryReferenceModel,
    HistoricalStatsStatus,
    LifecycleEvaluationStatus,
    LifecycleTransitionReason,
    MethodologyVersionRef,
    ProbabilityStatus,
    RiskRewardTarget,
    SignalAgreementSummary,
    SignalDecision,
    SignalDirection,
    SignalGeometry,
    SignalLifecycleEvaluation,
    SignalState,
    SignalStateTransition,
)


class LedgerDeserializationError(ValueError):
    """Raised when persisted canonical JSON cannot be reconstructed safely."""


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LedgerDeserializationError(f"{label} must be a mapping")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise LedgerDeserializationError(f"{label} must be a list")
    return value


def require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerDeserializationError(f"{label} must be a non-empty string")
    return value


def require_int(value: Any, label: str) -> int:
    if not isinstance(value, int):
        raise LedgerDeserializationError(f"{label} must be an integer")
    return value


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise LedgerDeserializationError(f"{label} must be a boolean")
    return value


def require_decimal(value: Any, label: str) -> Decimal:
    text = require_str(value, label)
    try:
        return Decimal(text)
    except Exception as exc:
        raise LedgerDeserializationError(
            f"{label} must be an exact decimal string"
        ) from exc


def optional_str(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return require_str(value, label)


def optional_identity(
    value: Any,
    label: str,
) -> tuple[str, str, str, str, int] | None:
    if value is None:
        return None
    items = require_list(value, label)
    if len(items) != 5:
        raise LedgerDeserializationError(f"{label} must have five items")
    return (
        require_str(items[0], f"{label}[0]"),
        require_str(items[1], f"{label}[1]"),
        require_str(items[2], f"{label}[2]"),
        require_str(items[3], f"{label}[3]"),
        require_int(items[4], f"{label}[4]"),
    )


def parse_signal_decision(value: Any) -> SignalDecision:
    root = require_mapping(value, "signal_decision")
    agreement_raw = require_mapping(root.get("agreement"), "signal agreement")
    pairwise = tuple(
        MethodologyPairRelation(
            left=MethodologyKind(
                require_str(item_map.get("left"), "pair left")
            ),
            right=MethodologyKind(
                require_str(item_map.get("right"), "pair right")
            ),
            relation=PairRelation(
                require_str(item_map.get("relation"), "pair relation")
            ),
            left_direction=EvidenceDirection(
                require_str(
                    item_map.get("left_direction"),
                    "pair left direction",
                )
            ),
            right_direction=EvidenceDirection(
                require_str(
                    item_map.get("right_direction"),
                    "pair right direction",
                )
            ),
        )
        for item in require_list(
            agreement_raw.get("pairwise_relations"),
            "signal pairwise relations",
        )
        for item_map in [require_mapping(item, "signal pair relation")]
    )
    agreement = SignalAgreementSummary(
        confluence_score=require_decimal(
            agreement_raw.get("confluence_score"),
            "signal confluence score",
        ),
        score_semantic=ScoreSemantic(
            require_str(
                agreement_raw.get("score_semantic"),
                "signal score semantic",
            )
        ),
        support_method_count=require_int(
            agreement_raw.get("support_method_count"),
            "signal support count",
        ),
        opposing_method_count=require_int(
            agreement_raw.get("opposing_method_count"),
            "signal opposition count",
        ),
        resolved_method_count=require_int(
            agreement_raw.get("resolved_method_count"),
            "signal resolved count",
        ),
        total_methodology_slots=require_int(
            agreement_raw.get("total_methodology_slots"),
            "signal methodology slot count",
        ),
        pairwise_relations=pairwise,
    )

    geometry_raw = root.get("geometry")
    geometry: SignalGeometry | None
    if geometry_raw is None:
        geometry = None
    else:
        geometry_map = require_mapping(geometry_raw, "signal geometry")
        entry_zone = require_mapping(
            geometry_map.get("entry_zone"),
            "signal entry zone",
        )
        targets = tuple(
            RiskRewardTarget(
                label=require_str(target_map.get("label"), "target label"),
                target_price=require_decimal(
                    target_map.get("target_price"),
                    "target price",
                ),
                reference_rr=require_decimal(
                    target_map.get("reference_rr"),
                    "target reference rr",
                ),
            )
            for target in require_list(
                geometry_map.get("targets"),
                "signal targets",
            )
            for target_map in [require_mapping(target, "signal target")]
        )
        geometry = SignalGeometry(
            source_evidence_id=require_str(
                geometry_map.get("source_evidence_id"),
                "geometry source evidence id",
            ),
            source_methodology=MethodologyKind(
                require_str(
                    geometry_map.get("source_methodology"),
                    "geometry source methodology",
                )
            ),
            entry_zone=PriceZone(
                low=require_decimal(entry_zone.get("low"), "entry zone low"),
                high=require_decimal(entry_zone.get("high"), "entry zone high"),
            ),
            entry_reference_price=require_decimal(
                geometry_map.get("entry_reference_price"),
                "entry reference price",
            ),
            entry_reference_model=EntryReferenceModel(
                require_str(
                    geometry_map.get("entry_reference_model"),
                    "entry reference model",
                )
            ),
            invalidation_price=require_decimal(
                geometry_map.get("invalidation_price"),
                "invalidation price",
            ),
            invalidation_trigger=InvalidationTrigger(
                require_str(
                    geometry_map.get("invalidation_trigger"),
                    "invalidation trigger",
                )
            ),
            targets=targets,
        )

    versions = tuple(
        MethodologyVersionRef(
            methodology=MethodologyKind(
                require_str(version_map.get("methodology"), "methodology")
            ),
            version=require_str(version_map.get("version"), "methodology version"),
        )
        for version in require_list(
            root.get("methodology_versions"),
            "methodology versions",
        )
        for version_map in [require_mapping(version, "methodology version")]
    )

    try:
        return SignalDecision(
            freeze_identity=require_str(
                root.get("freeze_identity"),
                "signal freeze identity",
            ),
            signal_version=require_str(
                root.get("signal_version"),
                "signal version",
            ),
            state=SignalState(
                require_str(root.get("state"), "signal state")
            ),
            exchange=__import__(
                "crypto_signal.data.models",
                fromlist=["Exchange"],
            ).Exchange(require_str(root.get("exchange"), "signal exchange")),
            market_type=__import__(
                "crypto_signal.data.models",
                fromlist=["MarketType"],
            ).MarketType(
                require_str(root.get("market_type"), "signal market type")
            ),
            symbol=require_str(root.get("symbol"), "signal symbol"),
            timeframe=require_str(root.get("timeframe"), "signal timeframe"),
            as_of_ms=require_int(root.get("as_of_ms"), "signal as-of"),
            direction=SignalDirection(
                require_str(root.get("direction"), "signal direction")
            ),
            setup_type=require_str(root.get("setup_type"), "signal setup type"),
            geometry=geometry,
            agreement=agreement,
            selected_evidence_ids=tuple(
                require_str(item, "selected evidence id")
                for item in require_list(
                    root.get("selected_evidence_ids"),
                    "selected evidence ids",
                )
            ),
            methodology_versions=versions,
            probability_status=ProbabilityStatus(
                require_str(
                    root.get("probability_status"),
                    "probability status",
                )
            ),
            historical_stats_status=HistoricalStatsStatus(
                require_str(
                    root.get("historical_stats_status"),
                    "historical stats status",
                )
            ),
            uncertainty_flags=tuple(
                require_str(item, "uncertainty flag")
                for item in require_list(
                    root.get("uncertainty_flags"),
                    "uncertainty flags",
                )
            ),
            evidence_summary=tuple(
                require_str(item, "evidence summary")
                for item in require_list(
                    root.get("evidence_summary"),
                    "evidence summary",
                )
            ),
        )
    except (ValueError, TypeError) as exc:
        if isinstance(exc, LedgerDeserializationError):
            raise
        raise LedgerDeserializationError(
            "signal decision is semantically invalid"
        ) from exc


def parse_outcome_evaluation(value: Any) -> OutcomeEvaluation:
    root = require_mapping(value, "outcome_evaluation")
    outcome_state_raw = root.get("outcome_state")
    ambiguity_raw = root.get("ambiguity_reason")
    not_evaluable_raw = root.get("not_evaluable_reason")

    try:
        return OutcomeEvaluation(
            outcome_identity=require_str(
                root.get("outcome_identity"),
                "outcome identity",
            ),
            signal_freeze_identity=require_str(
                root.get("signal_freeze_identity"),
                "outcome signal identity",
            ),
            evidence_class=EvidenceClass(
                require_str(root.get("evidence_class"), "evidence class")
            ),
            evaluated_as_of_ms=require_int(
                root.get("evaluated_as_of_ms"),
                "outcome evaluated as-of",
            ),
            resolution_status=OutcomeResolutionStatus(
                require_str(
                    root.get("resolution_status"),
                    "outcome resolution status",
                )
            ),
            outcome_state=(
                None
                if outcome_state_raw is None
                else OutcomeState(
                    require_str(outcome_state_raw, "outcome state")
                )
            ),
            signal_initial_state=SignalState(
                require_str(
                    root.get("signal_initial_state"),
                    "signal initial state",
                )
            ),
            coverage_status=OutcomeCoverageStatus(
                require_str(
                    root.get("coverage_status"),
                    "outcome coverage status",
                )
            ),
            max_holding_bars=require_int(
                root.get("max_holding_bars"),
                "max holding bars",
            ),
            expected_bar_count=require_int(
                root.get("expected_bar_count"),
                "expected bar count",
            ),
            observed_bar_count=require_int(
                root.get("observed_bar_count"),
                "observed bar count",
            ),
            missing_open_times_ms=tuple(
                require_int(item, "missing open time")
                for item in require_list(
                    root.get("missing_open_times_ms"),
                    "missing open times",
                )
            ),
            skipped_partial_decision_bucket=require_bool(
                root.get("skipped_partial_decision_bucket"),
                "skipped partial decision bucket",
            ),
            entry_observed=require_bool(
                root.get("entry_observed"),
                "entry observed",
            ),
            entry_candle_identity=optional_identity(
                root.get("entry_candle_identity"),
                "entry candle identity",
            ),
            highest_target_index=require_int(
                root.get("highest_target_index"),
                "highest target index",
            ),
            outcome_candle_identity=optional_identity(
                root.get("outcome_candle_identity"),
                "outcome candle identity",
            ),
            ambiguity_reason=(
                None
                if ambiguity_raw is None
                else OutcomeAmbiguityReason(
                    require_str(ambiguity_raw, "ambiguity reason")
                )
            ),
            not_evaluable_reason=(
                None
                if not_evaluable_raw is None
                else OutcomeNotEvaluableReason(
                    require_str(
                        not_evaluable_raw,
                        "not evaluable reason",
                    )
                )
            ),
        )
    except (ValueError, TypeError) as exc:
        if isinstance(exc, LedgerDeserializationError):
            raise
        raise LedgerDeserializationError(
            "outcome evaluation is semantically invalid"
        ) from exc


def parse_lifecycle_evaluation(value: Any) -> SignalLifecycleEvaluation:
    root = require_mapping(value, "lifecycle_evaluation")
    transition_raw = root.get("transition")
    transition: SignalStateTransition | None = None

    if transition_raw is not None:
        item = require_mapping(transition_raw, "lifecycle transition")
        trigger = optional_identity(
            item.get("trigger_candle_identity"),
            "transition trigger candle identity",
        )
        if trigger is None:
            raise LedgerDeserializationError(
                "lifecycle transition requires trigger candle identity"
            )
        transition = SignalStateTransition(
            transition_identity=require_str(
                item.get("transition_identity"),
                "transition identity",
            ),
            signal_freeze_identity=require_str(
                item.get("signal_freeze_identity"),
                "transition signal identity",
            ),
            from_state=SignalState(
                require_str(item.get("from_state"), "transition from state")
            ),
            to_state=SignalState(
                require_str(item.get("to_state"), "transition to state")
            ),
            reason=LifecycleTransitionReason(
                require_str(item.get("reason"), "transition reason")
            ),
            trigger_candle_identity=trigger,
            market_confirmed_at_ms=require_int(
                item.get("market_confirmed_at_ms"),
                "transition market confirmation",
            ),
            observed_at_ms=require_int(
                item.get("observed_at_ms"),
                "transition observed time",
            ),
            evaluated_as_of_ms=require_int(
                item.get("evaluated_as_of_ms"),
                "transition evaluated as-of",
            ),
            first_trigger_candle_certain=require_bool(
                item.get("first_trigger_candle_certain"),
                "transition first-trigger certainty",
            ),
        )

    try:
        return SignalLifecycleEvaluation(
            signal_freeze_identity=require_str(
                root.get("signal_freeze_identity"),
                "lifecycle signal identity",
            ),
            evaluated_as_of_ms=require_int(
                root.get("evaluated_as_of_ms"),
                "lifecycle evaluated as-of",
            ),
            current_state=SignalState(
                require_str(
                    root.get("current_state"),
                    "lifecycle current state",
                )
            ),
            status=LifecycleEvaluationStatus(
                require_str(root.get("status"), "lifecycle status")
            ),
            missing_open_times_ms=tuple(
                require_int(item, "lifecycle missing open")
                for item in require_list(
                    root.get("missing_open_times_ms"),
                    "lifecycle missing opens",
                )
            ),
            skipped_partial_decision_bucket=require_bool(
                root.get("skipped_partial_decision_bucket"),
                "lifecycle skipped partial decision bucket",
            ),
            transition=transition,
        )
    except (ValueError, TypeError) as exc:
        if isinstance(exc, LedgerDeserializationError):
            raise
        raise LedgerDeserializationError(
            "lifecycle evaluation is semantically invalid"
        ) from exc
