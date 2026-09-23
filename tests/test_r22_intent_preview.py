from __future__ import annotations

from decimal import Decimal

import pytest
from test_position_sizing_bridge import _capital, _core_risk, _vault_result
from test_position_sizing_intelligence import _policy

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import build_epoch2_activation_record
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction, PaperSymbol
from crypto_signal.paper.position_sizing_bridge import assess_capital_position_sizing
from crypto_signal.paper.position_sizing_intelligence import SizingMethod
from crypto_signal.paper.r22_intent_preview import (
    build_accepted_intent_market_reference,
    build_r22_intent_preview,
    build_reviewed_sizing_selection,
)


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _sizing(tmp_path):
    issuance, capital = _capital(tmp_path)
    sizing = assess_capital_position_sizing(
        issuance,
        capital,
        policy=_policy(),
        sized_at_ms=issuance.forecast.issued_at_ms + 3,
        risk_inputs=(_core_risk(issuance),),
    )
    return issuance, sizing


def _activation():
    return build_epoch2_activation_record(
        activated_at_ms=1_000,
        epoch1_ledger_sha256=_sha("immutable-epoch1-for-preview"),
    )


def _fixed_selection(sizing):
    core = _vault_result(sizing, PaperVaultId.CORE)
    assert core.assessment is not None
    fixed = next(
        item
        for item in core.assessment.results
        if item.method is SizingMethod.FIXED_FRACTIONAL
    )
    selection = build_reviewed_sizing_selection(
        sizing,
        vault_id=PaperVaultId.CORE,
        sizing_result_identity=fixed.result_identity,
        reviewed_at_ms=sizing.sized_at_ms + 1,
    )
    return fixed, selection


def _market_reference(issuance, *, price: str = "100"):
    return build_accepted_intent_market_reference(
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=issuance.forecast.issued_at_ms + 2,
        reference_price=Decimal(price),
        source_evidence_identities=(
            _sha("book-top"),
            _sha("mark-price"),
        ),
    )


def test_explicit_review_builds_non_mutating_r22_buy_preview(tmp_path) -> None:
    issuance, sizing = _sizing(tmp_path)
    fixed, selection = _fixed_selection(sizing)
    reference = _market_reference(issuance)
    before_paths = tuple(sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")))

    preview = build_r22_intent_preview(
        issuance,
        sizing,
        _activation(),
        vault_id=PaperVaultId.CORE,
        previewed_at_ms=sizing.sized_at_ms + 2,
        reviewed_selection=selection,
        market_reference=reference,
        quantity=Decimal("0.10"),
        reason_codes=("r25_slice8_reviewed_preview",),
    )

    after_paths = tuple(sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")))
    assert after_paths == before_paths
    assert preview.intent.action is PaperAction.BUY
    assert preview.decision is not None
    assert preview.decision.symbol is PaperSymbol.BTCUSDT
    assert preview.decision.quantity == Decimal("0.10")
    assert preview.decision.reference_price == Decimal(100)
    assert (
        preview.decision.quantity * preview.decision.reference_price
        <= fixed.hypothetical_notional_usdt
    )
    assert preview.review_selection_identity == selection.selection_identity
    assert preview.market_reference_identity == reference.reference_identity
    assert preview.intent.forecast_identity == issuance.forecast.forecast_identity
    assert preview.intent.proof_identity == issuance.proof.proof_identity
    assert preview.intent.sizing_decision_identity == fixed.result_identity
    assert "explicit_reviewed_sizing_selection" in preview.intent.reason_codes
    assert "source_bound_market_reference" in preview.intent.reason_codes
    assert preview.tape_write_authority is False
    assert preview.canonical_epoch2_write_authority is False
    assert preview.production_authority is False
    assert preview.real_capital == 0


def test_no_review_defaults_to_hold_cash_without_trade_lineage(tmp_path) -> None:
    issuance, sizing = _sizing(tmp_path)
    preview = build_r22_intent_preview(
        issuance,
        sizing,
        _activation(),
        vault_id=PaperVaultId.CORE,
        previewed_at_ms=sizing.sized_at_ms + 1,
    )

    assert preview.intent.action is PaperAction.HOLD_CASH
    assert preview.decision is None
    assert preview.review_selection_identity is None
    assert preview.market_reference_identity is None
    assert preview.intent.forecast_identity is None
    assert preview.intent.proof_identity is None
    assert preview.intent.sizing_assessment_identity is None
    assert preview.intent.sizing_decision_identity is None
    assert "no_explicit_reviewed_sizing_selection" in preview.intent.reason_codes


def test_uncalibrated_kelly_cannot_be_explicitly_reviewed_as_available(tmp_path) -> None:
    _, sizing = _sizing(tmp_path)
    core = _vault_result(sizing, PaperVaultId.CORE)
    assert core.assessment is not None
    kelly = next(
        item
        for item in core.assessment.results
        if item.method is SizingMethod.KELLY_HALF
    )
    with pytest.raises(ValueError, match="AVAILABLE_SHADOW"):
        build_reviewed_sizing_selection(
            sizing,
            vault_id=PaperVaultId.CORE,
            sizing_result_identity=kelly.result_identity,
            reviewed_at_ms=sizing.sized_at_ms + 1,
        )


def test_reviewed_quantity_cannot_exceed_exact_shadow_notional(tmp_path) -> None:
    issuance, sizing = _sizing(tmp_path)
    _, selection = _fixed_selection(sizing)
    with pytest.raises(ValueError, match="exceeds exact shadow sizing envelope"):
        build_r22_intent_preview(
            issuance,
            sizing,
            _activation(),
            vault_id=PaperVaultId.CORE,
            previewed_at_ms=sizing.sized_at_ms + 2,
            reviewed_selection=selection,
            market_reference=_market_reference(issuance),
            quantity=Decimal("0.13"),
        )


def test_trade_preview_rejects_wrong_or_future_market_reference(tmp_path) -> None:
    issuance, sizing = _sizing(tmp_path)
    _, selection = _fixed_selection(sizing)

    wrong_symbol = build_accepted_intent_market_reference(
        symbol=PaperSymbol.ETHUSDT,
        observed_at_ms=issuance.forecast.issued_at_ms + 2,
        reference_price=Decimal(100),
        source_evidence_identities=(_sha("eth-reference"),),
    )
    with pytest.raises(ValueError, match="symbol mismatch"):
        build_r22_intent_preview(
            issuance,
            sizing,
            _activation(),
            vault_id=PaperVaultId.CORE,
            previewed_at_ms=sizing.sized_at_ms + 2,
            reviewed_selection=selection,
            market_reference=wrong_symbol,
            quantity=Decimal("0.10"),
        )

    future_reference = build_accepted_intent_market_reference(
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=sizing.sized_at_ms + 50,
        reference_price=Decimal(100),
        source_evidence_identities=(_sha("future-reference"),),
    )
    with pytest.raises(ValueError, match="outside decision window"):
        build_r22_intent_preview(
            issuance,
            sizing,
            _activation(),
            vault_id=PaperVaultId.CORE,
            previewed_at_ms=sizing.sized_at_ms + 2,
            reviewed_selection=selection,
            market_reference=future_reference,
            quantity=Decimal("0.10"),
        )


def test_unreviewed_preview_cannot_smuggle_market_or_quantity(tmp_path) -> None:
    issuance, sizing = _sizing(tmp_path)
    with pytest.raises(ValueError, match="unreviewed R22 preview"):
        build_r22_intent_preview(
            issuance,
            sizing,
            _activation(),
            vault_id=PaperVaultId.CORE,
            previewed_at_ms=sizing.sized_at_ms + 2,
            market_reference=_market_reference(issuance),
            quantity=Decimal("0.10"),
        )
