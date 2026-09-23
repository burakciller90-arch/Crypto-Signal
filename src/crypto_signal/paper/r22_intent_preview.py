"""R25 Slice 8: explicit-review R22 intent previews without ledger mutation.

This module reuses the accepted R22 intent contract. It never appends to the R22
development tape or the canonical Epoch 2 ledger. Trade previews require one exact,
explicitly selected AVAILABLE_SHADOW sizing result plus explicit quantity/price.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import Epoch2ActivationRecord
from crypto_signal.paper.models import (
    DecisionIntentRecord,
    PaperAction,
    PaperSymbol,
    build_decision_intent,
)
from crypto_signal.paper.position_sizing_bridge import (
    PositionSizingBridgeResult,
    SizingBridgeState,
    SizingBridgeVaultResult,
)
from crypto_signal.paper.position_sizing_intelligence import (
    SizingMethod,
    SizingMethodResult,
    SizingMethodStatus,
)
from crypto_signal.paper.transaction_tape import (
    PaperTapeIntent,
    build_tape_intent,
)
from crypto_signal.signals.models import SignalDirection
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

R22_INTENT_PREVIEW_VERSION = "r25-r22-intent-preview-v1/1"
REVIEW_MODE = "explicit_research_review_input"
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class ReviewedSizingSelection:
    selection_identity: str
    sizing_bridge_identity: str
    vault_result_identity: str
    vault_id: object
    assessment_identity: str
    sizing_result_identity: str
    method: SizingMethod
    reviewed_at_ms: int
    review_mode: str = REVIEW_MODE
    automatic_selection: bool = False
    canonical_notional_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.selection_identity, "review selection"),
            (self.sizing_bridge_identity, "review sizing bridge"),
            (self.vault_result_identity, "review vault result"),
            (self.assessment_identity, "review sizing assessment"),
            (self.sizing_result_identity, "review sizing result"),
        ):
            _require_sha256(value, label)
        if self.reviewed_at_ms < 0:
            raise ValueError("reviewed_at_ms must be non-negative")
        if self.review_mode != REVIEW_MODE:
            raise ValueError("unsupported sizing review mode")
        if (
            self.automatic_selection
            or self.canonical_notional_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("reviewed sizing selection cannot grant authority")
        if self.selection_identity != canonical_sha256(_selection_payload(self)):
            raise ValueError("reviewed sizing selection identity mismatch")


@dataclass(frozen=True, slots=True)
class R22IntentPreview:
    preview_identity: str
    activation_identity: str
    forecast_identity: str
    proof_identity: str
    sizing_bridge_identity: str
    sizing_vault_result_identity: str
    review_selection_identity: str | None
    intent: PaperTapeIntent
    decision: DecisionIntentRecord | None
    previewed_at_ms: int
    preview_version: str = R22_INTENT_PREVIEW_VERSION
    tape_write_authority: bool = False
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.preview_identity, "R22 preview"),
            (self.activation_identity, "R22 preview activation"),
            (self.forecast_identity, "R22 preview forecast"),
            (self.proof_identity, "R22 preview proof"),
            (self.sizing_bridge_identity, "R22 preview sizing bridge"),
            (self.sizing_vault_result_identity, "R22 preview vault result"),
        ):
            _require_sha256(value, label)
        if self.review_selection_identity is not None:
            _require_sha256(self.review_selection_identity, "R22 review selection")
        if self.preview_version != R22_INTENT_PREVIEW_VERSION:
            raise ValueError("unsupported R22 intent preview version")
        if self.previewed_at_ms < 0:
            raise ValueError("R22 preview time must be non-negative")
        if self.intent.activation_identity != self.activation_identity:
            raise ValueError("R22 preview intent activation mismatch")
        if self.intent.action is PaperAction.HOLD_CASH:
            if self.review_selection_identity is not None or self.decision is not None:
                raise ValueError("HOLD_CASH preview cannot carry reviewed trade selection")
        else:
            if self.review_selection_identity is None or self.decision is None:
                raise ValueError("trade preview requires reviewed selection and decision")
            if self.intent.decision_identity != self.decision.record_identity:
                raise ValueError("R22 preview decision lineage mismatch")
            if self.intent.forecast_identity != self.forecast_identity:
                raise ValueError("R22 preview forecast lineage mismatch")
            if self.intent.proof_identity != self.proof_identity:
                raise ValueError("R22 preview proof lineage mismatch")
        if (
            self.tape_write_authority
            or self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("R22 preview cannot grant write/execution authority")
        if self.preview_identity != canonical_sha256(_preview_payload(self)):
            raise ValueError("R22 intent preview identity mismatch")


def build_reviewed_sizing_selection(
    sizing: PositionSizingBridgeResult,
    *,
    vault_id: object,
    sizing_result_identity: str,
    reviewed_at_ms: int,
) -> ReviewedSizingSelection:
    """Explicitly select one existing shadow result; never algorithmically rank it."""
    _require_sha256(sizing_result_identity, "review sizing result")
    vault_result = _find_vault_result(sizing, vault_id)
    if vault_result.state is not SizingBridgeState.ASSESSED_SHADOW:
        raise ValueError("review selection requires ASSESSED_SHADOW vault")
    if vault_result.assessment is None:
        raise ValueError("review selection lost sizing assessment")
    selected = _find_sizing_result(vault_result, sizing_result_identity)
    if selected.status is not SizingMethodStatus.AVAILABLE_SHADOW:
        raise ValueError("review selection requires AVAILABLE_SHADOW sizing result")
    if reviewed_at_ms < sizing.sized_at_ms:
        raise ValueError("sizing review cannot predate sizing assessment")

    payload = {
        "assessment_identity": vault_result.assessment.assessment_identity,
        "automatic_selection": False,
        "canonical_notional_authority": False,
        "method": selected.method,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "review_mode": REVIEW_MODE,
        "reviewed_at_ms": reviewed_at_ms,
        "sizing_bridge_identity": sizing.bridge_identity,
        "sizing_result_identity": selected.result_identity,
        "vault_id": vault_result.vault_id,
        "vault_result_identity": vault_result.result_identity,
    }
    return ReviewedSizingSelection(
        selection_identity=canonical_sha256(payload),
        sizing_bridge_identity=sizing.bridge_identity,
        vault_result_identity=vault_result.result_identity,
        vault_id=vault_result.vault_id,
        assessment_identity=vault_result.assessment.assessment_identity,
        sizing_result_identity=selected.result_identity,
        method=selected.method,
        reviewed_at_ms=reviewed_at_ms,
    )


def build_r22_intent_preview(
    issuance: UnifiedDecisionIssuance,
    sizing: PositionSizingBridgeResult,
    activation: Epoch2ActivationRecord,
    *,
    vault_id: object,
    previewed_at_ms: int,
    reviewed_selection: ReviewedSizingSelection | None = None,
    action: PaperAction | None = None,
    quantity: Decimal | None = None,
    reference_price: Decimal | None = None,
    reason: str | None = None,
    invalidation_context: str | None = None,
    reason_codes: tuple[str, ...] = (),
    previous_intent_identity: str | None = None,
) -> R22IntentPreview:
    """Build an R22-compatible preview object without writing any ledger."""
    if sizing.forecast_identity != issuance.forecast.forecast_identity:
        raise ValueError("R22 preview sizing/forecast lineage mismatch")
    if sizing.proof_identity != issuance.proof.proof_identity:
        raise ValueError("R22 preview sizing/proof lineage mismatch")
    if previewed_at_ms < max(
        activation.activated_at_ms,
        issuance.forecast.issued_at_ms,
        sizing.sized_at_ms,
    ):
        raise ValueError("R22 preview predates activation/forecast/sizing")

    vault_result = _find_vault_result(sizing, vault_id)
    if reviewed_selection is None:
        if any(
            value is not None
            for value in (
                action,
                quantity,
                reference_price,
                reason,
                invalidation_context,
            )
        ):
            raise ValueError("unreviewed R22 preview cannot carry trade fields")
        hold_policy_identity = canonical_sha256(
            {
                "forecast_identity": issuance.forecast.forecast_identity,
                "proof_identity": issuance.proof.proof_identity,
                "sizing_bridge_identity": sizing.bridge_identity,
                "sizing_vault_result_identity": vault_result.result_identity,
                "semantic": "no_explicit_reviewed_sizing_selection_hold_cash",
            }
        )
        hold_reasons = tuple(
            sorted(
                {
                    *vault_result.reason_codes,
                    *reason_codes,
                    "no_explicit_reviewed_sizing_selection",
                }
            )
        )
        intent = build_tape_intent(
            activation,
            vault_id=vault_result.vault_id,
            action=PaperAction.HOLD_CASH,
            decided_at_ms=previewed_at_ms,
            reason_codes=hold_reasons,
            hold_policy_identity=hold_policy_identity,
            previous_intent_identity=previous_intent_identity,
        )
        decision = None
        review_identity = None
    else:
        _validate_review_selection(
            sizing=sizing,
            vault_result=vault_result,
            selection=reviewed_selection,
        )
        if previewed_at_ms < reviewed_selection.reviewed_at_ms:
            raise ValueError("R22 preview cannot predate sizing review")
        if action is not PaperAction.BUY:
            raise ValueError("Slice8 reviewed entry preview supports BUY only")
        if issuance.forecast.direction is not SignalDirection.BULLISH:
            raise ValueError("BUY preview requires bullish immutable forecast")
        if (
            quantity is None
            or reference_price is None
            or reason is None
            or invalidation_context is None
        ):
            raise ValueError("reviewed trade preview requires explicit decision fields")
        if not reason.strip() or not invalidation_context.strip():
            raise ValueError("reviewed trade reason/invalidation cannot be blank")

        assessment = vault_result.assessment
        assert assessment is not None
        selected = _find_sizing_result(
            vault_result,
            reviewed_selection.sizing_result_identity,
        )
        symbol = PaperSymbol(issuance.forecast.symbol)
        decision = build_decision_intent(
            fund_identity=activation.activation_identity,
            decided_at_ms=previewed_at_ms,
            action=PaperAction.BUY,
            symbol=symbol,
            quantity=quantity,
            reference_price=reference_price,
            reason=reason,
            invalidation_context=invalidation_context,
        )
        trade_reasons = tuple(
            sorted(
                {
                    *reason_codes,
                    "explicit_reviewed_sizing_selection",
                    f"sizing_method:{selected.method.value}",
                }
            )
        )
        intent = build_tape_intent(
            activation,
            vault_id=vault_result.vault_id,
            action=PaperAction.BUY,
            decided_at_ms=previewed_at_ms,
            reason_codes=trade_reasons,
            forecast=issuance.forecast,
            proof=issuance.proof,
            sizing_assessment=assessment,
            sizing_result=selected,
            decision=decision,
            previous_intent_identity=previous_intent_identity,
        )
        review_identity = reviewed_selection.selection_identity

    payload = {
        "activation_identity": activation.activation_identity,
        "canonical_epoch2_write_authority": False,
        "decision_identity": None if decision is None else decision.record_identity,
        "forecast_identity": issuance.forecast.forecast_identity,
        "intent_identity": intent.intent_identity,
        "preview_version": R22_INTENT_PREVIEW_VERSION,
        "previewed_at_ms": previewed_at_ms,
        "production_authority": False,
        "proof_identity": issuance.proof.proof_identity,
        "real_capital": REAL_CAPITAL,
        "review_selection_identity": review_identity,
        "sizing_bridge_identity": sizing.bridge_identity,
        "sizing_vault_result_identity": vault_result.result_identity,
        "tape_write_authority": False,
    }
    return R22IntentPreview(
        preview_identity=canonical_sha256(payload),
        activation_identity=activation.activation_identity,
        forecast_identity=issuance.forecast.forecast_identity,
        proof_identity=issuance.proof.proof_identity,
        sizing_bridge_identity=sizing.bridge_identity,
        sizing_vault_result_identity=vault_result.result_identity,
        review_selection_identity=review_identity,
        intent=intent,
        decision=decision,
        previewed_at_ms=previewed_at_ms,
    )


def _validate_review_selection(
    *,
    sizing: PositionSizingBridgeResult,
    vault_result: SizingBridgeVaultResult,
    selection: ReviewedSizingSelection,
) -> None:
    if selection.sizing_bridge_identity != sizing.bridge_identity:
        raise ValueError("review selection sizing bridge mismatch")
    if selection.vault_result_identity != vault_result.result_identity:
        raise ValueError("review selection vault result mismatch")
    if selection.vault_id != vault_result.vault_id:
        raise ValueError("review selection vault mismatch")
    if vault_result.state is not SizingBridgeState.ASSESSED_SHADOW:
        raise ValueError("review selection cannot override non-assessed vault")
    if vault_result.assessment is None:
        raise ValueError("review selection lost assessment")
    if selection.assessment_identity != vault_result.assessment.assessment_identity:
        raise ValueError("review selection assessment mismatch")
    selected = _find_sizing_result(vault_result, selection.sizing_result_identity)
    if selected.method is not selection.method:
        raise ValueError("review selection sizing method mismatch")
    if selected.status is not SizingMethodStatus.AVAILABLE_SHADOW:
        raise ValueError("review selection no longer references available shadow result")


def _find_vault_result(
    sizing: PositionSizingBridgeResult,
    vault_id: object,
) -> SizingBridgeVaultResult:
    result = next(
        (item for item in sizing.vault_results if item.vault_id == vault_id),
        None,
    )
    if result is None:
        raise ValueError("unknown sizing bridge vault")
    return result


def _find_sizing_result(
    vault_result: SizingBridgeVaultResult,
    result_identity: str,
) -> SizingMethodResult:
    assessment = vault_result.assessment
    if assessment is None:
        raise ValueError("vault has no sizing assessment")
    result = next(
        (
            item
            for item in assessment.results
            if item.result_identity == result_identity
        ),
        None,
    )
    if result is None:
        raise ValueError("sizing result does not belong to exact vault assessment")
    return result


def _selection_payload(selection: ReviewedSizingSelection) -> dict[str, object]:
    return {
        "assessment_identity": selection.assessment_identity,
        "automatic_selection": selection.automatic_selection,
        "canonical_notional_authority": selection.canonical_notional_authority,
        "method": selection.method,
        "production_authority": selection.production_authority,
        "real_capital": selection.real_capital,
        "review_mode": selection.review_mode,
        "reviewed_at_ms": selection.reviewed_at_ms,
        "sizing_bridge_identity": selection.sizing_bridge_identity,
        "sizing_result_identity": selection.sizing_result_identity,
        "vault_id": selection.vault_id,
        "vault_result_identity": selection.vault_result_identity,
    }


def _preview_payload(preview: R22IntentPreview) -> dict[str, object]:
    return {
        "activation_identity": preview.activation_identity,
        "canonical_epoch2_write_authority": preview.canonical_epoch2_write_authority,
        "decision_identity": (
            None if preview.decision is None else preview.decision.record_identity
        ),
        "forecast_identity": preview.forecast_identity,
        "intent_identity": preview.intent.intent_identity,
        "preview_version": preview.preview_version,
        "previewed_at_ms": preview.previewed_at_ms,
        "production_authority": preview.production_authority,
        "proof_identity": preview.proof_identity,
        "real_capital": preview.real_capital,
        "review_selection_identity": preview.review_selection_identity,
        "sizing_bridge_identity": preview.sizing_bridge_identity,
        "sizing_vault_result_identity": preview.sizing_vault_result_identity,
        "tape_write_authority": preview.tape_write_authority,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
