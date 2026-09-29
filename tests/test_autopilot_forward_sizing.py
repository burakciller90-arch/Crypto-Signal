from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from test_autopilot_forward_runtime import _paths
from test_immutable_forecast_stream import _event_context
from test_position_sizing_intelligence import _policy

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.autopilot_forward_runtime import (
    CanonicalPaperAutopilotForwardRuntime,
)
from crypto_signal.paper.autopilot_forward_sizing import (
    FP3EligibleFixedFractionalSizingBridge,
    FP3SizingProcessDisposition,
    FP3SizingStageStatus,
    FP3SizingStageStore,
    build_fp3_sizing_risk_inputs,
)
from crypto_signal.paper.canonical_sizing import promote_fixed_fractional_sizing
from crypto_signal.paper.canonical_sizing_events import (
    CanonicalSizingEventLedger,
    build_canonical_sizing_event,
)
from crypto_signal.paper.canonical_vault_decisions import CanonicalVaultDecisionLedger
from crypto_signal.paper.canonical_vault_eligibility import promote_vault_eligibility
from crypto_signal.paper.capital_science_bridge import assess_unified_decision_capital
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.position_sizing_intelligence import (
    build_position_sizing_risk_context,
    evaluate_position_sizing_intelligence,
)
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.intelligence_stream_capital_forward_evidence import (
    build_capital_forward_auxiliary_evidence,
)
from crypto_signal.product.intelligence_stream_capital_sizing import (
    project_sizing_event_to_stream,
)


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _front(tmp_path: Path):
    epoch2_path, stream_path, autopilot_path, issuance = _paths(tmp_path)
    assessed_at_ms = issuance.forecast.issued_at_ms + 1
    runtime = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    runtime.ensure_activated(activated_at_ms=issuance.forecast.issued_at_ms)
    result = runtime.process_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=assessed_at_ms,
        processed_at_ms=assessed_at_ms + 5,
    )
    assert result.receipt is not None
    return epoch2_path, stream_path, autopilot_path, issuance, result.receipt


def _current_vault(epoch2_path: Path, vault_id: PaperVaultId):
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    return next(item for item in state.vault_snapshots if item.vault_id is vault_id)


def _risk(
    *,
    epoch2_path: Path,
    front_assessed_at_ms: int,
    vault_id: PaperVaultId = PaperVaultId.CORE,
    correlation: Decimal = Decimal("0.20"),
    drawdown: Decimal | None = None,
):
    current = _current_vault(epoch2_path, vault_id)
    as_of_ms = max(front_assessed_at_ms, current.snapshot_at_ms)
    return build_fp3_sizing_risk_inputs(
        vault_id=vault_id,
        asset="BTCUSDT",
        as_of_ms=as_of_ms,
        expected_win_r=Decimal("2.00"),
        expected_loss_r=Decimal("1.00"),
        transaction_cost_r=Decimal("0.10"),
        absolute_correlation_0_1=correlation,
        current_drawdown_fraction=(
            current.drawdown_fraction if drawdown is None else drawdown
        ),
        volatility_fraction=Decimal("0.10"),
        liquidity_score_0_1=Decimal("0.90"),
        source_evidence_identities=tuple(
            sorted(
                {
                    _sha("correlation"),
                    _sha("expected-payoff"),
                    _sha("liquidity"),
                    _sha("transaction-cost"),
                    _sha("volatility"),
                }
            )
        ),
    )


def _selected_at_ms(
    *,
    epoch2_path: Path,
    front,
    risk,
) -> int:
    decisions = CanonicalVaultDecisionLedger(
        epoch2_path
    ).read_assessment_decisions(front.allocator_assessment_identity)
    latest_decision_at_ms = max(int(item["decided_at_ms"]) for item in decisions)
    return max(risk.as_of_ms, latest_decision_at_ms) + 1


def test_fp3_b_eligible_core_promotes_only_fixed_fractional_and_replays(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    bridge = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )

    before_r22 = R22Epoch2AtomicTape(epoch2_path).audit_all_read_only()
    first = bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 1,
    )
    second = bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 100,
    )

    assert first.disposition is FP3SizingProcessDisposition.INSERTED
    assert first.receipt is not None
    assert first.receipt.stage_status is FP3SizingStageStatus.SIZED
    assert first.receipt.selection_identity is not None
    assert first.receipt.sizing_event_identity is not None
    assert first.receipt.stream_event_identity is not None
    assert first.receipt.narrative_identity is not None
    assert first.receipt.fixed_fractional_status == "available_shadow"
    assert "fixed_fractional_only" in first.receipt.reason_codes
    assert first.receipt.real_capital == 0

    assert second.disposition is FP3SizingProcessDisposition.REPLAYED
    assert second.receipt == first.receipt
    assert R22Epoch2AtomicTape(epoch2_path).audit_all_read_only() == before_r22

    event = CanonicalSizingEventLedger(epoch2_path).read(
        first.receipt.sizing_event_identity
    )
    assert event is not None
    assert event["vault_id"] == PaperVaultId.CORE.value
    assert event["selection_identity"] == first.receipt.selection_identity

    with sqlite3.connect(epoch2_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM s11_canonical_sizing_events"
        ).fetchone()
    assert count is not None
    assert int(count[0]) == 1


def test_fp3_b_risk_gate_holds_without_canonical_sizing_or_r22_trade(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
        correlation=Decimal("0.95"),
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    bridge = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    before_r22 = R22Epoch2AtomicTape(epoch2_path).audit_all_read_only()

    held = bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 1,
    )
    replay = bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 10,
    )

    assert held.disposition is FP3SizingProcessDisposition.HELD_RISK_GATE
    assert held.receipt is not None
    assert held.receipt.stage_status is FP3SizingStageStatus.HELD_RISK_GATE
    assert held.receipt.selection_identity is None
    assert held.receipt.sizing_event_identity is None
    assert "correlation_limit_breached" in held.receipt.reason_codes
    assert replay.disposition is FP3SizingProcessDisposition.REPLAYED
    assert replay.receipt == held.receipt
    assert R22Epoch2AtomicTape(epoch2_path).audit_all_read_only() == before_r22

    with sqlite3.connect(epoch2_path) as connection:
        table = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='s11_canonical_sizing_events'
            """
        ).fetchone()
        count = (
            0
            if table is None
            else int(
                connection.execute(
                    "SELECT COUNT(*) FROM s11_canonical_sizing_events"
                ).fetchone()[0]
            )
        )
    assert count == 0


def test_fp3_b_hold_vault_never_enters_sizing(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
        vault_id=PaperVaultId.TACTICAL,
    )
    bridge = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )

    result = bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.TACTICAL,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=risk.as_of_ms + 1,
        processed_at_ms=risk.as_of_ms + 2,
    )

    assert (
        result.disposition
        is FP3SizingProcessDisposition.SKIPPED_NOT_ELIGIBLE
    )
    assert result.receipt is None
    assert FP3SizingStageStore(autopilot_path).read(
        forecast_identity=issuance.forecast.forecast_identity,
        vault_id=PaperVaultId.TACTICAL,
    ) is None


def test_fp3_b_rejects_drawdown_that_disagrees_with_r21(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
        drawdown=Decimal("0.01"),
    )
    bridge = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )

    with pytest.raises(ValueError, match="drawdown differs"):
        bridge.process(
            issuance,
            event_context=_event_context(),
            base_asset="BTC",
            vault_id=PaperVaultId.CORE,
            policy=_policy(),
            risk_inputs=risk,
            selected_at_ms=risk.as_of_ms + 1,
            processed_at_ms=risk.as_of_ms + 2,
        )


def test_fp3_b_recovers_when_canonical_event_exists_but_stage_receipt_is_missing(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    event_context = _event_context()

    auxiliary = build_capital_forward_auxiliary_evidence(
        issuance,
        event_context=event_context,
    )
    capital = assess_unified_decision_capital(
        issuance,
        event_context=event_context,
        base_asset="BTC",
        assessed_at_ms=front.assessed_at_ms,
        tactical_microstructure=auxiliary.tactical,
        opportunity_recovery=auxiliary.opportunity,
    )
    eligibility = promote_vault_eligibility(
        capital.candidate,
        capital.allocation,
        vault_id=PaperVaultId.CORE,
    )
    envelope = next(
        item
        for item in capital.allocation.vaults
        if item.vault_id is PaperVaultId.CORE
    )
    current = _current_vault(epoch2_path, PaperVaultId.CORE)
    context = build_position_sizing_risk_context(
        vault_id=PaperVaultId.CORE,
        asset=risk.asset,
        as_of_ms=risk.as_of_ms,
        allocator_assessment_identity=front.allocator_assessment_identity,
        allocator_candidate_identity=front.allocator_candidate_identity,
        expected_win_r=risk.expected_win_r,
        expected_loss_r=risk.expected_loss_r,
        transaction_cost_r=risk.transaction_cost_r,
        absolute_correlation_0_1=risk.absolute_correlation_0_1,
        current_drawdown_fraction=risk.current_drawdown_fraction,
        volatility_fraction=risk.volatility_fraction,
        liquidity_score_0_1=risk.liquidity_score_0_1,
        source_evidence_identities=tuple(
            sorted(
                {
                    *risk.source_evidence_identities,
                    risk.risk_input_identity,
                    eligibility.proof_identity,
                    current.snapshot_identity,
                }
            )
        ),
    )
    assessment = evaluate_position_sizing_intelligence(
        policy=_policy(),
        vault=envelope,
        context=context,
    )
    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=current,
        selected_at_ms=selected_at_ms,
    )
    event = build_canonical_sizing_event(selection, eligibility)
    assert CanonicalSizingEventLedger(epoch2_path).append(event) is True
    project_sizing_event_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        sizing_event_identity=event.event_identity,
    )
    assert FP3SizingStageStore(autopilot_path).read(
        forecast_identity=issuance.forecast.forecast_identity,
        vault_id=PaperVaultId.CORE,
    ) is None

    recovered = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    ).process(
        issuance,
        event_context=event_context,
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 20,
    )

    assert recovered.disposition is FP3SizingProcessDisposition.RECOVERED
    assert recovered.receipt is not None
    assert recovered.receipt.sizing_event_identity == event.event_identity


def test_fp3_b_sizing_stage_receipt_is_physically_immutable(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    result = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    ).process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 1,
    )
    assert result.receipt is not None

    with sqlite3.connect(autopilot_path) as connection, pytest.raises(
        sqlite3.IntegrityError,
        match="immutable FP3 sizing stage truth",
    ):
        connection.execute(
            """
            UPDATE fp3_paper_autopilot_sizing_receipts
            SET vault_id = ?
            WHERE receipt_identity = ?
            """,
            (PaperVaultId.TACTICAL.value, result.receipt.receipt_identity),
        )

    persisted = FP3SizingStageStore(autopilot_path).read(
        forecast_identity=issuance.forecast.forecast_identity,
        vault_id=PaperVaultId.CORE,
    )
    assert persisted == result.receipt


def test_fp3_b_rejects_selection_before_front_decision_chronology(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    decisions = CanonicalVaultDecisionLedger(
        epoch2_path
    ).read_assessment_decisions(front.allocator_assessment_identity)
    latest_decision_at_ms = max(int(item["decided_at_ms"]) for item in decisions)
    bridge = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )

    with pytest.raises(ValueError, match="follow latest canonical vault decision"):
        bridge.process(
            issuance,
            event_context=_event_context(),
            base_asset="BTC",
            vault_id=PaperVaultId.CORE,
            policy=_policy(),
            risk_inputs=risk,
            selected_at_ms=latest_decision_at_ms,
            processed_at_ms=latest_decision_at_ms + 1,
        )
