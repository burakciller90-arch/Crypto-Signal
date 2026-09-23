from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from test_decision_proof_live_feed import (
    AS_OF,
    _available,
    _forecast,
    _slices,
)

from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    build_decision_proof_snapshot,
)
from crypto_signal.product.explainable_intelligence import (
    R23CertaintyCeiling,
    build_explainable_intelligence,
)


def _proof(*, calibrated: bool = False):
    forecast = _forecast(calibrated=calibrated)
    return build_decision_proof_snapshot(forecast, _slices(forecast))


def test_r23_simple_and_pro_bind_the_same_exact_decision_proof_slices() -> None:
    proof = _proof()
    explanation = build_explainable_intelligence(proof)

    assert explanation.proof_identity == proof.proof_identity
    assert explanation.forecast_identity == proof.forecast_identity
    assert explanation.certainty_ceiling is R23CertaintyCeiling.INCOMPLETE
    assert explanation.evidence_summary == proof.evidence_summary
    assert explanation.private_reasoning_exposed is False
    assert explanation.read_only is True
    assert explanation.production_authority is False
    assert explanation.real_capital == 0

    for simple, pro, source in zip(
        explanation.simple_evidence,
        explanation.pro_evidence,
        proof.evidence_slices,
        strict=True,
    ):
        assert simple.domain is source.domain is pro.domain
        assert simple.slice_identity == source.slice_identity == pro.slice_identity
        assert simple.availability is source.availability is pro.availability
        assert simple.verdict is source.verdict is pro.verdict


def test_r23_simple_never_upgrades_missing_evidence_to_confirmation() -> None:
    proof = _proof()
    explanation = build_explainable_intelligence(proof)

    order_book = next(
        item
        for item in explanation.simple_evidence
        if item.domain is ProofEvidenceDomain.ORDER_BOOK
    )
    assert order_book.availability is ProofEvidenceAvailability.INSUFFICIENT
    assert order_book.verdict is ProofEvidenceVerdict.INSUFFICIENT
    assert order_book.text == (
        "Order-book pressure does not have enough accepted evidence yet."
    )
    assert "confirm" not in order_book.text.lower()
    assert "certain" not in order_book.text.lower()

    with pytest.raises(ValueError, match="may not exceed"):
        replace(
            order_book,
            text="Order-book pressure confirms the setup with certainty.",
        )


def test_r23_conflicting_technical_evidence_stays_conflicting_in_simple_view() -> None:
    forecast = _forecast()
    slices = list(_slices(forecast))
    index = next(
        i
        for i, item in enumerate(slices)
        if item.domain is ProofEvidenceDomain.ORDER_BOOK
    )
    slices[index] = _available(
        ProofEvidenceDomain.ORDER_BOOK,
        forecast.source_evidence_identities[0],
        verdict=ProofEvidenceVerdict.CONTRADICT,
        observed_at_ms=AS_OF,
    )
    proof = build_decision_proof_snapshot(forecast, tuple(slices))
    explanation = build_explainable_intelligence(proof)

    line = next(
        item
        for item in explanation.simple_evidence
        if item.domain is ProofEvidenceDomain.ORDER_BOOK
    )
    assert line.verdict is ProofEvidenceVerdict.CONTRADICT
    assert line.text == "Order-book pressure is working against the current setup."
    assert explanation.evidence_summary.contradict_count == 1
    # Other missing domains still cap the overall explanation at INCOMPLETE.
    assert explanation.certainty_ceiling is R23CertaintyCeiling.INCOMPLETE


def test_r23_pro_exposes_roadmap_components_source_quality_and_exact_timestamps() -> None:
    explanation = build_explainable_intelligence(_proof())

    methodology = next(
        item
        for item in explanation.pro_evidence
        if item.domain is ProofEvidenceDomain.METHODOLOGY
    )
    assert methodology.technical_components == ("PA", "methodology")
    assert methodology.source_quality == "accepted_source"
    assert methodology.market_available_at_ms == AS_OF - 1
    assert methodology.observed_at_ms == AS_OF
    assert methodology.freshness_0_1 == Decimal("0.90")
    assert methodology.evidence_identities
    assert methodology.summary_codes == ("methodology_available",)
    assert "source_quality=accepted_source" in methodology.text
    assert f"observed_at_ms={AS_OF}" in methodology.text

    order_flow = next(
        item
        for item in explanation.pro_evidence
        if item.domain is ProofEvidenceDomain.ORDER_FLOW_CVD
    )
    assert order_flow.technical_components == ("CVD", "delta", "absorption")
    assert order_flow.availability is ProofEvidenceAvailability.INSUFFICIENT
    assert order_flow.evidence_identities == ()
    assert "no accepted measurement" in order_flow.text

    derivatives = next(
        item
        for item in explanation.pro_evidence
        if item.domain is ProofEvidenceDomain.DERIVATIVES
    )
    assert derivatives.technical_components == ("OI", "funding", "basis")


def test_r23_probability_language_never_converts_confluence_to_probability() -> None:
    uncalibrated = build_explainable_intelligence(_proof())
    assert uncalibrated.calibrated_probability_0_1 is None
    assert uncalibrated.probability_text.startswith("Probability is not calibrated")
    assert "82" not in uncalibrated.probability_text

    calibrated = build_explainable_intelligence(_proof(calibrated=True))
    assert calibrated.calibrated_probability_0_1 == Decimal("0.67")
    assert calibrated.probability_text == (
        "Calibrated probability for this exact forecast scope: "
        "67% (status=calibrated)."
    )
    assert calibrated.proof_identity != uncalibrated.proof_identity
    assert calibrated.explanation_identity != uncalibrated.explanation_identity


def test_r23_simple_and_pro_summaries_are_deterministic_from_same_ceiling() -> None:
    explanation = build_explainable_intelligence(_proof())
    assert explanation.simple_summary == (
        "Some market evidence is missing or unsupported. "
        "Treat this as incomplete, not as confirmation."
    )
    assert "certainty_ceiling=incomplete" in explanation.pro_summary
    assert (
        f"available={explanation.evidence_summary.available_count}/"
        f"{explanation.evidence_summary.total_domain_count}"
    ) in explanation.pro_summary
    assert "bounded_uncertainty" in explanation.pro_summary


def test_r23_identity_is_immutable_and_manual_text_rewrite_fails_closed() -> None:
    explanation = build_explainable_intelligence(_proof())
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(
            explanation,
            event_context_state="invented_state",
        )
    with pytest.raises(ValueError, match="exceeds technical certainty"):
        replace(
            explanation,
            simple_summary="This setup is certain to succeed.",
        )
