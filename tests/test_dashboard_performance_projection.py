from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_json
from crypto_signal.outcomes.evaluator import compute_outcome_identity
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeCoverageStatus,
    OutcomeEvaluation,
    OutcomeResolutionStatus,
    OutcomeState,
)
from crypto_signal.product.models import ProductDataStatus
from crypto_signal.product.reader import DashboardReader
from crypto_signal.signals.models import (
    EntryReferenceModel,
    HistoricalStatsStatus,
    MethodologyVersionRef,
    ProbabilityStatus,
    RiskRewardTarget,
    SignalAgreementSummary,
    SignalDecision,
    SignalDirection,
    SignalGeometry,
    SignalState,
)


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def create_schema(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE signal_freezes (
                bundle_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT NOT NULL UNIQUE,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                as_of_ms INTEGER NOT NULL,
                source_cutoff_open_time_ms INTEGER NOT NULL,
                signal_state TEXT NOT NULL,
                direction TEXT NOT NULL,
                bundle_json TEXT NOT NULL,
                frozen_at_ms INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE outcome_evaluations (
                outcome_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT NOT NULL,
                evidence_class TEXT NOT NULL,
                evaluated_as_of_ms INTEGER NOT NULL,
                resolution_status TEXT NOT NULL,
                outcome_state TEXT,
                max_holding_bars INTEGER NOT NULL,
                outcome_json TEXT NOT NULL,
                appended_at_ms INTEGER NOT NULL
            )
            """
        )


def make_decision(seed: str) -> SignalDecision:
    geometry = SignalGeometry(
        source_evidence_id=f"harmonic-{seed}",
        source_methodology=MethodologyKind.HARMONIC,
        entry_zone=PriceZone(Decimal(100), Decimal(102)),
        entry_reference_price=Decimal(101),
        entry_reference_model=(
            EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
        ),
        invalidation_price=Decimal(90),
        invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
        targets=(
            RiskRewardTarget("target_1", Decimal(110), Decimal(1)),
            RiskRewardTarget("target_2", Decimal(120), Decimal(2)),
            RiskRewardTarget("target_3", Decimal(130), Decimal(3)),
        ),
    )
    return SignalDecision(
        freeze_identity=digest(f"signal-{seed}"),
        signal_version="signal-v1/1",
        state=SignalState.ACTIVE,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=1_000,
        direction=SignalDirection.BULLISH,
        setup_type="gartley",
        geometry=geometry,
        agreement=SignalAgreementSummary(
            confluence_score=Decimal("66.67"),
            score_semantic=ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY,
            support_method_count=2,
            opposing_method_count=0,
            resolved_method_count=2,
            total_methodology_slots=3,
            pairwise_relations=(),
        ),
        selected_evidence_ids=(f"harmonic-{seed}",),
        methodology_versions=(
            MethodologyVersionRef(
                methodology=MethodologyKind.HARMONIC,
                version="harmonic-v1/1",
            ),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=(),
        evidence_summary=(),
    )


def make_outcome(
    decision: SignalDecision,
    *,
    evidence_class: EvidenceClass,
    state: OutcomeState | None,
    evaluated_as_of_ms: int,
    max_holding_bars: int = 4,
    resolution: OutcomeResolutionStatus = OutcomeResolutionStatus.RESOLVED,
) -> OutcomeEvaluation:
    highest = (
        0
        if state is None
        else {
            OutcomeState.SUCCESS_TP1: 1,
            OutcomeState.SUCCESS_TP2: 2,
            OutcomeState.SUCCESS_TP3: 3,
        }.get(state, 0)
    )
    draft = OutcomeEvaluation(
        outcome_identity="0" * 64,
        signal_freeze_identity=decision.freeze_identity,
        evidence_class=evidence_class,
        evaluated_as_of_ms=evaluated_as_of_ms,
        resolution_status=resolution,
        outcome_state=state,
        signal_initial_state=SignalState.ACTIVE,
        coverage_status=OutcomeCoverageStatus.COMPLETE,
        max_holding_bars=max_holding_bars,
        expected_bar_count=1,
        observed_bar_count=1,
        missing_open_times_ms=(),
        skipped_partial_decision_bucket=True,
        entry_observed=True,
        entry_candle_identity=("bybit", "spot", "BTCUSDT", "15m", 1_800),
        highest_target_index=highest,
        outcome_candle_identity=(
            None
            if state is None
            else ("bybit", "spot", "BTCUSDT", "15m", 2_700)
        ),
        ambiguity_reason=None,
        not_evaluable_reason=None,
    )
    return replace(
        draft,
        outcome_identity=compute_outcome_identity(draft),
    )


def insert_signal(path: Path, decision: SignalDecision, *, seed: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO signal_freezes (
                bundle_identity,
                signal_freeze_identity,
                exchange,
                market_type,
                symbol,
                timeframe,
                as_of_ms,
                source_cutoff_open_time_ms,
                signal_state,
                direction,
                bundle_json,
                frozen_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest(f"bundle-{seed}"),
                decision.freeze_identity,
                decision.exchange.value,
                decision.market_type.value,
                decision.symbol,
                decision.timeframe,
                decision.as_of_ms,
                900,
                decision.state.value,
                decision.direction.value,
                canonical_json({"signal_decision": decision}),
                1_100,
            ),
        )


def insert_outcome(path: Path, outcome: OutcomeEvaluation) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO outcome_evaluations (
                outcome_identity,
                signal_freeze_identity,
                evidence_class,
                evaluated_as_of_ms,
                resolution_status,
                outcome_state,
                max_holding_bars,
                outcome_json,
                appended_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome.outcome_identity,
                outcome.signal_freeze_identity,
                outcome.evidence_class.value,
                outcome.evaluated_as_of_ms,
                outcome.resolution_status.value,
                None if outcome.outcome_state is None else outcome.outcome_state.value,
                outcome.max_holding_bars,
                canonical_json(outcome),
                outcome.evaluated_as_of_ms + 1,
            ),
        )


def test_performance_projection_preserves_evidence_classes_and_r(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_schema(path)

    retrospective = make_decision("retro")
    live = make_decision("live")
    insert_signal(path, retrospective, seed="retro")
    insert_signal(path, live, seed="live")
    insert_outcome(
        path,
        make_outcome(
            retrospective,
            evidence_class=EvidenceClass.RETROSPECTIVE,
            state=OutcomeState.SUCCESS_TP2,
            evaluated_as_of_ms=2_000,
        ),
    )
    insert_outcome(
        path,
        make_outcome(
            live,
            evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
            state=OutcomeState.FAIL_SL,
            evaluated_as_of_ms=3_000,
        ),
    )

    view = DashboardReader(path).performance_availability()

    assert view.status is ProductDataStatus.READY
    assert view.outcome_snapshot_count == 2
    assert {
        item.evidence_class: item.count
        for item in view.evidence_class_counts
    } == {
        EvidenceClass.RETROSPECTIVE: 1,
        EvidenceClass.LIVE_UNTOUCHED_FORWARD: 1,
    }
    assert len(view.groups) == 2

    by_class = {group.evidence_class: group for group in view.groups}
    retro_group = by_class[EvidenceClass.RETROSPECTIVE]
    live_group = by_class[EvidenceClass.LIVE_UNTOUCHED_FORWARD]
    assert retro_group.max_holding_bars == 4
    assert live_group.max_holding_bars == 4

    (retro_segment,) = retro_group.segments
    (live_segment,) = live_group.segments
    assert retro_segment.success_n == 1
    assert retro_segment.fail_sl_n == 0
    assert retro_segment.historical_success_fraction == Decimal(1)
    assert retro_segment.average_r == Decimal(2)
    assert live_segment.success_n == 0
    assert live_segment.fail_sl_n == 1
    assert live_segment.historical_success_fraction == Decimal(0)
    assert live_segment.average_r == Decimal(-1)


def test_performance_projection_uses_latest_snapshot_per_signal_and_horizon(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_schema(path)
    decision = make_decision("latest")
    insert_signal(path, decision, seed="latest")

    pending = make_outcome(
        decision,
        evidence_class=EvidenceClass.WALK_FORWARD,
        state=None,
        evaluated_as_of_ms=2_000,
        resolution=OutcomeResolutionStatus.PENDING,
    )
    success = make_outcome(
        decision,
        evidence_class=EvidenceClass.WALK_FORWARD,
        state=OutcomeState.SUCCESS_TP1,
        evaluated_as_of_ms=3_000,
    )
    insert_outcome(path, pending)
    insert_outcome(path, success)

    view = DashboardReader(path).performance_availability()

    assert view.outcome_snapshot_count == 2
    (group,) = view.groups
    assert group.stored_snapshot_count == 2
    assert group.selected_latest_signal_count == 1
    (segment,) = group.segments
    assert segment.total_n == 1
    assert segment.pending_n == 0
    assert segment.success_n == 1


def test_performance_projection_does_not_merge_holding_horizons(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_schema(path)
    first = make_decision("h4")
    second = make_decision("h8")
    insert_signal(path, first, seed="h4")
    insert_signal(path, second, seed="h8")
    insert_outcome(
        path,
        make_outcome(
            first,
            evidence_class=EvidenceClass.RETROSPECTIVE,
            state=OutcomeState.SUCCESS_TP1,
            evaluated_as_of_ms=2_000,
            max_holding_bars=4,
        ),
    )
    insert_outcome(
        path,
        make_outcome(
            second,
            evidence_class=EvidenceClass.RETROSPECTIVE,
            state=OutcomeState.FAIL_SL,
            evaluated_as_of_ms=2_100,
            max_holding_bars=8,
        ),
    )

    view = DashboardReader(path).performance_availability()

    assert [(group.evidence_class, group.max_holding_bars) for group in view.groups] == [
        (EvidenceClass.RETROSPECTIVE, 4),
        (EvidenceClass.RETROSPECTIVE, 8),
    ]
