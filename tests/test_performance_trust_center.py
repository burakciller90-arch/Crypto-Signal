from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_decision_proof_live_feed import _forecast
from test_event_risk_circuit_breaker import (
    AS_OF as EVENT_AS_OF,
    _config,
    _event_risk,
    _market_quality,
    _news,
)
from test_historical_evaluation import decision
from test_transaction_tape_atomic import _trade_bundle

from crypto_signal.confluence.models import (
    EvidenceDirection,
    MethodologyKind,
    MethodologyPairRelation,
    PairRelation,
)
from crypto_signal.forecast_stream import (
    R20_FORECAST_ENGINE_VERSION,
    R20_RESOLUTION_SCHEMA_VERSION,
    ForecastResolution,
    ForecastResolutionState,
    append_forecast,
    append_resolution,
    empty_forecast_stream,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerState,
    evaluate_circuit_breaker,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.outcomes.models import EvidenceClass, OutcomeState
from crypto_signal.paper.epoch2_accounting import Epoch2LedgerState
from crypto_signal.product.performance_trust_center import (
    R24MetricStatus,
    build_performance_trust_center,
)
from crypto_signal.signals.models import SignalDirection, SignalState

OBSERVED_AT = EVENT_AS_OF + 100_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _resolution(
    forecast,
    *,
    state: ForecastResolutionState,
    source_state: OutcomeState,
    evaluated_at_ms: int,
    seed: str,
) -> ForecastResolution:
    payload = {
        "engine_version": R20_FORECAST_ENGINE_VERSION,
        "evaluated_at_ms": evaluated_at_ms,
        "evidence_class": EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        "forecast_identity": forecast.forecast_identity,
        "original_forecast_unchanged": True,
        "production_authority": False,
        "real_capital": 0,
        "reason_codes": (f"r24_{seed}",),
        "schema_version": R20_RESOLUTION_SCHEMA_VERSION,
        "signal_freeze_identity": forecast.signal_freeze_identity,
        "source_outcome_identity": _sha(f"outcome-{seed}"),
        "source_outcome_state": source_state,
        "state": state,
    }
    return ForecastResolution(
        resolution_identity=canonical_sha256(payload),
        schema_version=R20_RESOLUTION_SCHEMA_VERSION,
        engine_version=R20_FORECAST_ENGINE_VERSION,
        forecast_identity=forecast.forecast_identity,
        signal_freeze_identity=forecast.signal_freeze_identity,
        source_outcome_identity=_sha(f"outcome-{seed}"),
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        evaluated_at_ms=evaluated_at_ms,
        state=state,
        source_outcome_state=source_state,
        reason_codes=(f"r24_{seed}",),
    )


def _stream():
    winner = _forecast()
    loser = _forecast(calibrated=True)
    stream = empty_forecast_stream()
    for forecast in sorted(
        (winner, loser),
        key=lambda item: (item.issued_at_ms, item.forecast_identity),
    ):
        stream = append_forecast(stream, forecast)
    hit = _resolution(
        winner,
        state=ForecastResolutionState.HIT_TARGET,
        source_state=OutcomeState.SUCCESS_TP1,
        evaluated_at_ms=1_100_000,
        seed="hit",
    )
    invalidated = _resolution(
        loser,
        state=ForecastResolutionState.INVALIDATED,
        source_state=OutcomeState.FAIL_SL,
        evaluated_at_ms=1_200_000,
        seed="loss",
    )
    for resolution in (hit, invalidated):
        stream = append_resolution(stream, resolution)
    return stream


def _decisions():
    active = decision("r24-active")

    abstain = replace(
        decision("r24-abstain"),
        state=SignalState.NO_SIGNAL,
        direction=SignalDirection.NONE,
        geometry=None,
    )

    conflict_base = decision("r24-conflict")
    conflict_relation = MethodologyPairRelation(
        left=MethodologyKind.PRICE_ACTION,
        right=MethodologyKind.HARMONIC,
        relation=PairRelation.CONTRADICT,
        left_direction=EvidenceDirection.BULLISH,
        right_direction=EvidenceDirection.BEARISH,
    )
    conflict = replace(
        conflict_base,
        agreement=replace(
            conflict_base.agreement,
            support_method_count=1,
            opposing_method_count=1,
            resolved_method_count=2,
            pairwise_relations=(conflict_relation,),
        ),
    )

    ambiguity_base = decision("r24-ambiguity")
    ambiguity_relation = MethodologyPairRelation(
        left=MethodologyKind.HARMONIC,
        right=MethodologyKind.ELLIOTT,
        relation=PairRelation.INTERNAL_AMBIGUITY,
        left_direction=EvidenceDirection.UNRESOLVED,
        right_direction=EvidenceDirection.UNRESOLVED,
    )
    ambiguous = replace(
        ambiguity_base,
        agreement=replace(
            ambiguity_base.agreement,
            support_method_count=1,
            opposing_method_count=0,
            resolved_method_count=1,
            pairwise_relations=(ambiguity_relation,),
        ),
    )
    return (active, abstain, conflict, ambiguous)


def _events():
    clear = evaluate_circuit_breaker(
        _event_risk(None),
        _news(multi=True),
        _market_quality(),
        config=_config(),
    )
    blocked = evaluate_circuit_breaker(
        _event_risk(5),
        _news(multi=True),
        _market_quality(),
        config=_config(),
    )
    assert clear.state is CircuitBreakerState.CLEAR
    assert blocked.state is CircuitBreakerState.EVENT_BLOCK
    return (clear, blocked)


def _paper(tmp_path: Path):
    _, before, _, fill, after_vaults, parent, _ = _trade_bundle(tmp_path)
    state = Epoch2LedgerState(
        activation=before.activation,
        vault_snapshots=after_vaults,
        consolidated_snapshot=parent,
    )
    history = (before.consolidated_snapshot, parent)
    return state, history, (fill,)


def _center(tmp_path: Path):
    state, history, fills = _paper(tmp_path)
    return build_performance_trust_center(
        observed_at_ms=OBSERVED_AT,
        forecast_stream=_stream(),
        signal_decisions=_decisions(),
        epoch2_state=state,
        consolidated_history=history,
        transaction_fills=fills,
        event_analyses=_events(),
    )


def test_r24_keeps_winner_and_loser_in_same_labeled_forward_cohort(
    tmp_path: Path,
) -> None:
    center = _center(tmp_path)
    live = next(
        item
        for item in center.forecast.cohorts
        if item.evidence_class is EvidenceClass.LIVE_UNTOUCHED_FORWARD
    )
    retrospective = next(
        item
        for item in center.forecast.cohorts
        if item.evidence_class is EvidenceClass.RETROSPECTIVE
    )
    assert live.resolved_n == 2
    assert live.hit_target_n == 1
    assert live.invalidated_n == 1
    assert live.decisive_accuracy_fraction == Decimal("0.5")
    assert retrospective.resolved_n == 0
    assert retrospective.decisive_accuracy_fraction is None
    assert center.winners_and_losers_visible_together is True
    assert center.evidence_classes_merged_for_accuracy is False


def test_r24_brier_and_reliability_use_calibrated_untouched_forward_only(
    tmp_path: Path,
) -> None:
    center = _center(tmp_path)
    calibration = center.calibration
    assert calibration.status is R24MetricStatus.AVAILABLE
    assert calibration.evidence_class is EvidenceClass.LIVE_UNTOUCHED_FORWARD
    assert calibration.sample_count == 1
    assert calibration.brier_score == Decimal("0.4489")
    assert calibration.mean_absolute_calibration_gap == Decimal("0.67")
    assert len(calibration.reliability_points) == 1
    point = calibration.reliability_points[0]
    assert point.predicted_probability_0_1 == Decimal("0.67")
    assert point.hit_target_count == 0
    assert point.observed_hit_fraction == Decimal(0)
    assert point.absolute_calibration_gap == Decimal("0.67")
    assert "not_probability_authorization" in calibration.semantic


def test_r24_decision_rates_are_truthful_and_separately_labeled(
    tmp_path: Path,
) -> None:
    center = _center(tmp_path)
    decisions = center.decisions
    assert decisions.total_decision_n == 4
    assert decisions.abstain_n == 1
    assert decisions.conflict_n == 1
    assert decisions.ambiguous_n == 1
    assert decisions.abstain_rate_fraction == Decimal("0.25")
    assert decisions.conflict_rate_fraction == Decimal("0.25")
    assert decisions.ambiguous_rate_fraction == Decimal("0.25")


def test_r24_event_block_exposes_frequency_but_not_fake_effectiveness(
    tmp_path: Path,
) -> None:
    center = _center(tmp_path)
    event = center.event_block
    assert event.analysis_n == 2
    assert event.event_block_n == 1
    assert event.event_block_rate_fraction == Decimal("0.5")
    assert event.effectiveness_status is R24MetricStatus.NOT_YET_MEASURED
    assert event.effectiveness_fraction is None
    assert "counterfactual" in event.effectiveness_reason


def test_r24_epoch2_vault_cost_drawdown_and_unmeasured_profit_factor(
    tmp_path: Path,
) -> None:
    center = _center(tmp_path)
    paper = center.paper_capital
    assert paper.nav_usdt == Decimal(998)
    assert paper.realized_pnl_usdt == Decimal(0)
    assert paper.unrealized_pnl_usdt == Decimal(-2)
    assert paper.max_drawdown_fraction == Decimal("0.002")
    assert paper.fee_usdt == Decimal(1)
    assert paper.spread_usdt == Decimal("0.4")
    assert paper.slippage_usdt == Decimal("0.6")
    assert paper.closed_trade_count == 0
    assert paper.profit_factor_status is R24MetricStatus.NOT_YET_MEASURED
    assert paper.profit_factor is None
    assert len(paper.vaults) == 3
    assert paper.vaults[0].vault_id.value == "CORE"


def test_r24_version_comparison_remains_evidence_class_labeled(
    tmp_path: Path,
) -> None:
    center = _center(tmp_path)
    assert len(center.version_cohorts) == 1
    cohort = center.version_cohorts[0]
    assert cohort.evidence_class is EvidenceClass.LIVE_UNTOUCHED_FORWARD
    assert cohort.resolved_n == 2
    assert cohort.hit_target_n == 1
    assert cohort.invalidated_n == 1
    assert cohort.version_key[0].startswith("forecast_engine=")


def test_r24_risk_adjusted_metrics_remain_unmeasured_without_valid_return_series(
    tmp_path: Path,
) -> None:
    center = _center(tmp_path)
    assert center.risk_adjusted.status is R24MetricStatus.NOT_YET_MEASURED
    assert center.risk_adjusted.sharpe_ratio is None
    assert center.risk_adjusted.sortino_ratio is None
    assert "fixed_period_return_series" in center.risk_adjusted.reason


def test_r24_rejects_future_evidence_duplicate_decisions_and_truncated_history(
    tmp_path: Path,
) -> None:
    state, history, fills = _paper(tmp_path)
    stream = _stream()
    decisions = _decisions()

    with pytest.raises(ValueError, match="future"):
        build_performance_trust_center(
            observed_at_ms=1,
            forecast_stream=stream,
            signal_decisions=decisions,
            epoch2_state=state,
            consolidated_history=history,
            transaction_fills=fills,
            event_analyses=(),
        )

    with pytest.raises(ValueError, match="duplicate freeze"):
        build_performance_trust_center(
            observed_at_ms=OBSERVED_AT,
            forecast_stream=stream,
            signal_decisions=(decisions[0], decisions[0]),
            epoch2_state=state,
            consolidated_history=history,
            transaction_fills=fills,
            event_analyses=(),
        )

    with pytest.raises(ValueError, match="first consolidated history item"):
        build_performance_trust_center(
            observed_at_ms=OBSERVED_AT,
            forecast_stream=stream,
            signal_decisions=decisions,
            epoch2_state=state,
            consolidated_history=(history[-1],),
            transaction_fills=fills,
            event_analyses=(),
        )


def test_r24_identity_and_authority_boundaries_fail_closed(tmp_path: Path) -> None:
    center = _center(tmp_path)
    assert center.private_reasoning_exposed is False
    assert center.read_only is True
    assert center.production_authority is False
    assert center.real_capital == 0

    with pytest.raises(ValueError, match="identity mismatch"):
        replace(center, observed_at_ms=center.observed_at_ms + 1)
    with pytest.raises(ValueError, match="winners and losers"):
        replace(center, winners_and_losers_visible_together=False)
    with pytest.raises(ValueError, match="merge backtest"):
        replace(center, evidence_classes_merged_for_accuracy=True)
