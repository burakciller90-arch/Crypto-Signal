"""Bounded accepted-pretrade -> orchestration -> atomic commit integration.

This module does not select signals, fetch venue rules, activate a runtime, or
contact an exchange. It only persists an already accepted PLANNED pre-trade
decision through the accepted deterministic orchestration and atomic paper
ledger boundaries. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.paper.commit import (
    PaperBundleCommitResult,
    commit_orchestration_bundle,
)
from crypto_signal.paper.execution import FrozenExecutionSnapshot
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.orchestration import (
    PaperOrchestrationBundle,
    orchestrate_paper_plan,
)
from crypto_signal.paper.pretrade import (
    PaperPretradeDecision,
    PaperPretradeStatus,
)
from crypto_signal.paper.state import PaperFundState

__all__ = [
    "REAL_CAPITAL",
    "PaperTradePipelineError",
    "PaperTradePipelineResult",
    "commit_planned_pretrade",
]


class PaperTradePipelineError(ValueError):
    """Raised when accepted pre-trade lineage cannot be committed safely."""


@dataclass(frozen=True, slots=True)
class PaperTradePipelineResult:
    """Auditable result of one bounded paper trade commit attempt."""

    pretrade_identity: str
    execution_snapshot_identity: str
    bundle: PaperOrchestrationBundle
    commit: PaperBundleCommitResult
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if len(self.pretrade_identity) != 64:
            raise ValueError("pretrade_identity must be SHA256")
        if len(self.execution_snapshot_identity) != 64:
            raise ValueError("execution_snapshot_identity must be SHA256")
        if (
            self.bundle.execution_snapshot_identity
            != self.execution_snapshot_identity
        ):
            raise ValueError("bundle execution snapshot identity mismatch")
        if self.bundle.fill is None or self.bundle.mutation is None:
            raise ValueError("trade pipeline result requires fill and mutation")
        expected_record_identities = (
            self.bundle.decision.record_identity,
            self.bundle.fill.record_identity,
            self.bundle.mutation.record_identity,
        )
        if self.commit.record_identities != expected_record_identities:
            raise ValueError(
                "commit result must exactly match decision/fill/mutation order"
            )
        if self.commit.state_after.real_capital != REAL_CAPITAL:
            raise ValueError("committed state must remain REAL_CAPITAL=0")


def commit_planned_pretrade(
    *,
    ledger: PaperFundLedger,
    state: PaperFundState,
    pretrade: PaperPretradeDecision,
    execution_snapshot: FrozenExecutionSnapshot,
) -> PaperTradePipelineResult:
    """Persist one accepted PLANNED pre-trade decision atomically/idempotently."""
    _validate_inputs(
        state=state,
        pretrade=pretrade,
        execution_snapshot=execution_snapshot,
    )
    plan = pretrade.plan
    if plan is None:
        raise PaperTradePipelineError("PLANNED pretrade lost its paper plan")

    bundle = orchestrate_paper_plan(
        state=state,
        plan=plan,
        snapshot=execution_snapshot,
    )
    if bundle.execution_snapshot_identity != pretrade.execution_snapshot_identity:
        raise PaperTradePipelineError(
            "orchestration bundle snapshot lineage mismatch"
        )
    if bundle.decision.action is not pretrade.action:
        raise PaperTradePipelineError("orchestration decision action mismatch")
    if bundle.decision.symbol is not pretrade.symbol:
        raise PaperTradePipelineError("orchestration decision symbol mismatch")
    if bundle.decision.quantity != pretrade.planned_quantity:
        raise PaperTradePipelineError("orchestration decision quantity mismatch")
    if bundle.decision.reference_price != pretrade.reference_price:
        raise PaperTradePipelineError(
            "orchestration decision reference price mismatch"
        )
    if bundle.fill is None or bundle.mutation is None:
        raise PaperTradePipelineError(
            "PLANNED trade orchestration must produce fill and mutation"
        )
    if bundle.fill.venue_reference != execution_snapshot.execution_reference:
        raise PaperTradePipelineError("fill is not bound to execution snapshot")

    committed = commit_orchestration_bundle(
        ledger=ledger,
        state=state,
        bundle=bundle,
    )
    return PaperTradePipelineResult(
        pretrade_identity=pretrade.pretrade_identity,
        execution_snapshot_identity=execution_snapshot.snapshot_identity,
        bundle=bundle,
        commit=committed,
        real_capital=REAL_CAPITAL,
    )


def _validate_inputs(
    *,
    state: PaperFundState,
    pretrade: PaperPretradeDecision,
    execution_snapshot: FrozenExecutionSnapshot,
) -> None:
    if (
        state.real_capital != REAL_CAPITAL
        or pretrade.real_capital != REAL_CAPITAL
        or execution_snapshot.real_capital != REAL_CAPITAL
    ):
        raise PaperTradePipelineError("REAL_CAPITAL must remain 0")
    if pretrade.status is not PaperPretradeStatus.PLANNED:
        raise PaperTradePipelineError("pipeline requires PLANNED pretrade")
    if pretrade.plan is None:
        raise PaperTradePipelineError("PLANNED pretrade requires paper plan")
    if pretrade.plan.fund_identity != state.fund_identity:
        raise PaperTradePipelineError("pretrade plan fund identity mismatch")
    if pretrade.execution_snapshot_identity != execution_snapshot.snapshot_identity:
        raise PaperTradePipelineError("execution snapshot identity mismatch")
    if execution_snapshot.symbol is not pretrade.symbol:
        raise PaperTradePipelineError("execution snapshot symbol mismatch")
    if execution_snapshot.policy_version != state.execution_policy_version:
        raise PaperTradePipelineError("execution snapshot policy mismatch")
    expected_input_marker = f"|input:{pretrade.execution_input_identity}"
    if not execution_snapshot.venue_reference.endswith(expected_input_marker):
        raise PaperTradePipelineError(
            "execution snapshot is not bound to pretrade execution input"
        )
