"""R23 Explainable Intelligence: SIMPLE and PRO views of the same Decision Proof.

The layer is a deterministic read-only projection of accepted R20.5 evidence.
It adds no market facts, probabilities, private reasoning or execution authority.
SIMPLE may translate mechanics into plain language, but it may never upgrade the
availability, verdict or certainty ceiling of the underlying technical evidence.
REAL_CAPITAL=0.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.decision_proof import (
    DecisionProofEvidenceSlice,
    DecisionProofEvidenceSummary,
    DecisionProofSnapshot,
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
)

R23_SCHEMA_VERSION = "r23-explainable-intelligence-v1/1"
R23_ENGINE_VERSION = "r23-explainable-intelligence-v1/1"
REAL_CAPITAL = 0


class R23CertaintyCeiling(StrEnum):
    INCOMPLETE = "incomplete"
    CONFLICTED = "conflicted"
    CONDITIONAL = "conditional"
    CALIBRATED_CONDITIONAL = "calibrated_conditional"


_SIMPLE_LABELS: dict[ProofEvidenceDomain, str] = {
    ProofEvidenceDomain.FROZEN_CHART: "Frozen chart evidence",
    ProofEvidenceDomain.CONSUMED_CANDLES: "Price candles",
    ProofEvidenceDomain.ORDER_BOOK: "Order-book pressure",
    ProofEvidenceDomain.LIQUIDITY_MAP: "Nearby liquidity",
    ProofEvidenceDomain.LIQUIDATION_MAP: "Liquidation pressure",
    ProofEvidenceDomain.ORDER_FLOW_CVD: "Buyer/seller flow",
    ProofEvidenceDomain.DERIVATIVES: "Futures positioning",
    ProofEvidenceDomain.ONCHAIN: "On-chain activity",
    ProofEvidenceDomain.EVENT_CONTEXT: "Event risk",
    ProofEvidenceDomain.METHODOLOGY: "Price-action methodology",
    ProofEvidenceDomain.PROBABILITY_CALIBRATION: "Probability calibration",
}

_PRO_COMPONENTS: dict[ProofEvidenceDomain, tuple[str, ...]] = {
    ProofEvidenceDomain.FROZEN_CHART: ("frozen_chart",),
    ProofEvidenceDomain.CONSUMED_CANDLES: ("consumed_candles",),
    ProofEvidenceDomain.ORDER_BOOK: ("order_book_imbalance",),
    ProofEvidenceDomain.LIQUIDITY_MAP: ("liquidity",),
    ProofEvidenceDomain.LIQUIDATION_MAP: ("liquidations",),
    ProofEvidenceDomain.ORDER_FLOW_CVD: ("CVD", "delta", "absorption"),
    ProofEvidenceDomain.DERIVATIVES: ("OI", "funding", "basis"),
    ProofEvidenceDomain.ONCHAIN: ("onchain",),
    ProofEvidenceDomain.EVENT_CONTEXT: ("event_risk",),
    ProofEvidenceDomain.METHODOLOGY: ("PA", "methodology"),
    ProofEvidenceDomain.PROBABILITY_CALIBRATION: ("probability_calibration",),
}


@dataclass(frozen=True, slots=True)
class R23SimpleEvidenceLine:
    domain: ProofEvidenceDomain
    slice_identity: str
    availability: ProofEvidenceAvailability
    verdict: ProofEvidenceVerdict
    text: str

    def __post_init__(self) -> None:
        _require_sha256(self.slice_identity, "R23 simple slice identity")
        expected = _simple_text(self.domain, self.availability, self.verdict)
        if self.text != expected:
            raise ValueError("R23 SIMPLE text may not exceed or rewrite evidence semantics")


@dataclass(frozen=True, slots=True)
class R23ProEvidenceLine:
    domain: ProofEvidenceDomain
    slice_identity: str
    availability: ProofEvidenceAvailability
    verdict: ProofEvidenceVerdict
    technical_components: tuple[str, ...]
    evidence_identities: tuple[str, ...]
    market_available_at_ms: int | None
    observed_at_ms: int | None
    freshness_0_1: Decimal | None
    source_quality: str | None
    summary_codes: tuple[str, ...]
    text: str

    def __post_init__(self) -> None:
        _require_sha256(self.slice_identity, "R23 PRO slice identity")
        if self.technical_components != _PRO_COMPONENTS[self.domain]:
            raise ValueError("R23 PRO technical components must match canonical domain")
        if self.evidence_identities != tuple(sorted(set(self.evidence_identities))):
            raise ValueError("R23 PRO evidence identities must be sorted and unique")
        for identity in self.evidence_identities:
            _require_sha256(identity, "R23 PRO evidence identity")
        if self.summary_codes != tuple(sorted(set(self.summary_codes))):
            raise ValueError("R23 PRO summary codes must be sorted and unique")
        if not self.summary_codes or any(not item.strip() for item in self.summary_codes):
            raise ValueError("R23 PRO requires non-empty summary codes")
        if self.availability is ProofEvidenceAvailability.AVAILABLE:
            if not self.evidence_identities:
                raise ValueError("R23 available PRO line requires evidence")
            if self.market_available_at_ms is None or self.observed_at_ms is None:
                raise ValueError("R23 available PRO line requires exact timestamps")
            if self.freshness_0_1 is None or self.source_quality is None:
                raise ValueError("R23 available PRO line requires freshness/source quality")
            if self.source_quality.strip() == "":
                raise ValueError("R23 PRO source quality cannot be blank")
            if self.freshness_0_1 < Decimal(0) or self.freshness_0_1 > Decimal(1):
                raise ValueError("R23 PRO freshness outside [0,1]")
        else:
            if self.evidence_identities:
                raise ValueError("R23 unavailable PRO line cannot invent evidence")
            if any(
                value is not None
                for value in (
                    self.market_available_at_ms,
                    self.observed_at_ms,
                    self.freshness_0_1,
                    self.source_quality,
                )
            ):
                raise ValueError("R23 unavailable PRO line cannot invent measurements")
        expected = _pro_text(
            self.domain,
            self.availability,
            self.verdict,
            self.technical_components,
            self.source_quality,
            self.market_available_at_ms,
            self.observed_at_ms,
            self.freshness_0_1,
            self.summary_codes,
        )
        if self.text != expected:
            raise ValueError("R23 PRO text must be deterministic from accepted evidence")


@dataclass(frozen=True, slots=True)
class R23ExplainableIntelligenceSnapshot:
    explanation_identity: str
    schema_version: str
    engine_version: str
    proof_identity: str
    forecast_identity: str
    symbol: str
    timeframe: str
    issued_at_ms: int
    source_as_of_ms: int
    direction: str
    signal_state: str
    conditional_thesis: str
    certainty_ceiling: R23CertaintyCeiling
    probability_status: str
    calibrated_probability_0_1: Decimal | None
    probability_text: str
    event_context_state: str
    confluence_support_score_0_100: Decimal
    confluence_opposition_score_0_100: Decimal
    uncertainty_flags: tuple[str, ...]
    evidence_summary: DecisionProofEvidenceSummary
    simple_summary: str
    simple_evidence: tuple[R23SimpleEvidenceLine, ...]
    pro_summary: str
    pro_evidence: tuple[R23ProEvidenceLine, ...]
    private_reasoning_exposed: bool = False
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.explanation_identity, "R23 explanation identity")
        _require_sha256(self.proof_identity, "R23 proof identity")
        _require_sha256(self.forecast_identity, "R23 forecast identity")
        if self.schema_version != R23_SCHEMA_VERSION:
            raise ValueError("unsupported R23 schema")
        if self.engine_version != R23_ENGINE_VERSION:
            raise ValueError("unsupported R23 engine")
        for value, label in (
            (self.symbol, "R23 symbol"),
            (self.timeframe, "R23 timeframe"),
            (self.direction, "R23 direction"),
            (self.signal_state, "R23 signal state"),
            (self.conditional_thesis, "R23 conditional thesis"),
            (self.probability_status, "R23 probability status"),
            (self.probability_text, "R23 probability text"),
            (self.event_context_state, "R23 event context state"),
            (self.simple_summary, "R23 SIMPLE summary"),
            (self.pro_summary, "R23 PRO summary"),
        ):
            if not value.strip():
                raise ValueError(f"{label} cannot be blank")
        if min(self.issued_at_ms, self.source_as_of_ms) < 0:
            raise ValueError("R23 timestamps must be non-negative")
        if self.issued_at_ms < self.source_as_of_ms:
            raise ValueError("R23 issuance cannot predate source as-of")
        for score in (
            self.confluence_support_score_0_100,
            self.confluence_opposition_score_0_100,
        ):
            if score < Decimal(0) or score > Decimal(100):
                raise ValueError("R23 confluence score outside [0,100]")
        if self.calibrated_probability_0_1 is not None:
            if (
                self.calibrated_probability_0_1 < Decimal(0)
                or self.calibrated_probability_0_1 > Decimal(1)
            ):
                raise ValueError("R23 calibrated probability outside [0,1]")

        expected_domains = tuple(sorted(ProofEvidenceDomain, key=lambda item: item.value))
        if tuple(item.domain for item in self.simple_evidence) != expected_domains:
            raise ValueError("R23 SIMPLE requires exact canonical evidence domains")
        if tuple(item.domain for item in self.pro_evidence) != expected_domains:
            raise ValueError("R23 PRO requires exact canonical evidence domains")
        for simple, pro in zip(self.simple_evidence, self.pro_evidence, strict=True):
            if (
                simple.domain is not pro.domain
                or simple.slice_identity != pro.slice_identity
                or simple.availability is not pro.availability
                or simple.verdict is not pro.verdict
            ):
                raise ValueError("R23 SIMPLE and PRO must use the same exact evidence slice")

        if self.simple_summary != _simple_summary(self.certainty_ceiling):
            raise ValueError("R23 SIMPLE summary exceeds technical certainty ceiling")
        if self.pro_summary != _pro_summary(
            self.certainty_ceiling,
            self.evidence_summary,
            self.uncertainty_flags,
        ):
            raise ValueError("R23 PRO summary is not evidence-derived")
        if self.probability_text != _probability_text(
            self.calibrated_probability_0_1,
            self.probability_status,
        ):
            raise ValueError("R23 probability wording is not evidence-derived")
        if self.private_reasoning_exposed:
            raise ValueError("R23 must not expose private reasoning")
        if not self.read_only:
            raise ValueError("R23 must remain read-only")
        if self.production_authority:
            raise ValueError("R23 has no production/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.explanation_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("R23 explanation identity mismatch")


def build_explainable_intelligence(
    proof: DecisionProofSnapshot,
) -> R23ExplainableIntelligenceSnapshot:
    if proof.private_reasoning_exposed:
        raise ValueError("R23 cannot consume proof that exposes private reasoning")
    if not proof.read_only or proof.production_authority or proof.real_capital != 0:
        raise ValueError("R23 proof authority boundary mismatch")

    simple = tuple(_simple_line(item) for item in proof.evidence_slices)
    pro = tuple(_pro_line(item) for item in proof.evidence_slices)
    ceiling = _certainty_ceiling(proof)
    probability_text = _probability_text(
        proof.calibrated_probability_0_1,
        proof.probability_status,
    )
    payload: dict[str, object] = {
        "proof_identity": proof.proof_identity,
        "forecast_identity": proof.forecast_identity,
        "symbol": proof.symbol,
        "timeframe": proof.timeframe,
        "issued_at_ms": proof.issued_at_ms,
        "source_as_of_ms": proof.source_as_of_ms,
        "direction": proof.direction,
        "signal_state": proof.signal_state,
        "conditional_thesis": proof.conditional_thesis,
        "certainty_ceiling": ceiling,
        "probability_status": proof.probability_status,
        "calibrated_probability_0_1": proof.calibrated_probability_0_1,
        "probability_text": probability_text,
        "event_context_state": proof.event_context_state,
        "confluence_support_score_0_100": proof.confluence_support_score_0_100,
        "confluence_opposition_score_0_100": proof.confluence_opposition_score_0_100,
        "uncertainty_flags": proof.uncertainty_flags,
        "evidence_summary": proof.evidence_summary,
        "simple_summary": _simple_summary(ceiling),
        "simple_evidence": simple,
        "pro_summary": _pro_summary(
            ceiling,
            proof.evidence_summary,
            proof.uncertainty_flags,
        ),
        "pro_evidence": pro,
        "private_reasoning_exposed": False,
        "read_only": True,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": R23_SCHEMA_VERSION,
        "engine_version": R23_ENGINE_VERSION,
    }
    return R23ExplainableIntelligenceSnapshot(
        explanation_identity=canonical_sha256(payload),
        schema_version=R23_SCHEMA_VERSION,
        engine_version=R23_ENGINE_VERSION,
        proof_identity=proof.proof_identity,
        forecast_identity=proof.forecast_identity,
        symbol=proof.symbol,
        timeframe=proof.timeframe,
        issued_at_ms=proof.issued_at_ms,
        source_as_of_ms=proof.source_as_of_ms,
        direction=proof.direction,
        signal_state=proof.signal_state,
        conditional_thesis=proof.conditional_thesis,
        certainty_ceiling=ceiling,
        probability_status=proof.probability_status,
        calibrated_probability_0_1=proof.calibrated_probability_0_1,
        probability_text=probability_text,
        event_context_state=proof.event_context_state,
        confluence_support_score_0_100=proof.confluence_support_score_0_100,
        confluence_opposition_score_0_100=proof.confluence_opposition_score_0_100,
        uncertainty_flags=proof.uncertainty_flags,
        evidence_summary=proof.evidence_summary,
        simple_summary=_simple_summary(ceiling),
        simple_evidence=simple,
        pro_summary=_pro_summary(
            ceiling,
            proof.evidence_summary,
            proof.uncertainty_flags,
        ),
        pro_evidence=pro,
    )


def _simple_line(item: DecisionProofEvidenceSlice) -> R23SimpleEvidenceLine:
    return R23SimpleEvidenceLine(
        domain=item.domain,
        slice_identity=item.slice_identity,
        availability=item.availability,
        verdict=item.verdict,
        text=_simple_text(item.domain, item.availability, item.verdict),
    )


def _pro_line(item: DecisionProofEvidenceSlice) -> R23ProEvidenceLine:
    components = _PRO_COMPONENTS[item.domain]
    return R23ProEvidenceLine(
        domain=item.domain,
        slice_identity=item.slice_identity,
        availability=item.availability,
        verdict=item.verdict,
        technical_components=components,
        evidence_identities=item.evidence_identities,
        market_available_at_ms=item.market_available_at_ms,
        observed_at_ms=item.observed_at_ms,
        freshness_0_1=item.freshness_0_1,
        source_quality=item.source_quality,
        summary_codes=item.summary_codes,
        text=_pro_text(
            item.domain,
            item.availability,
            item.verdict,
            components,
            item.source_quality,
            item.market_available_at_ms,
            item.observed_at_ms,
            item.freshness_0_1,
            item.summary_codes,
        ),
    )


def _simple_text(
    domain: ProofEvidenceDomain,
    availability: ProofEvidenceAvailability,
    verdict: ProofEvidenceVerdict,
) -> str:
    label = _SIMPLE_LABELS[domain]
    if availability is not ProofEvidenceAvailability.AVAILABLE:
        return f"{label} does not have enough accepted evidence yet."
    if verdict is ProofEvidenceVerdict.SUPPORT:
        return f"{label} supports the current setup."
    if verdict is ProofEvidenceVerdict.CONTRADICT:
        return f"{label} is working against the current setup."
    if verdict is ProofEvidenceVerdict.NEUTRAL:
        return f"{label} is not giving a directional confirmation."
    raise ValueError("available R23 evidence cannot be INSUFFICIENT")


def _pro_text(
    domain: ProofEvidenceDomain,
    availability: ProofEvidenceAvailability,
    verdict: ProofEvidenceVerdict,
    components: tuple[str, ...],
    source_quality: str | None,
    market_available_at_ms: int | None,
    observed_at_ms: int | None,
    freshness_0_1: Decimal | None,
    summary_codes: tuple[str, ...],
) -> str:
    component_text = "/".join(components)
    code_text = ",".join(summary_codes)
    if availability is not ProofEvidenceAvailability.AVAILABLE:
        return (
            f"{domain.value} [{component_text}] availability={availability.value}; "
            f"verdict={verdict.value}; codes={code_text}; no accepted measurement."
        )
    assert source_quality is not None
    assert market_available_at_ms is not None
    assert observed_at_ms is not None
    assert freshness_0_1 is not None
    return (
        f"{domain.value} [{component_text}] availability=available; "
        f"verdict={verdict.value}; source_quality={source_quality}; "
        f"market_available_at_ms={market_available_at_ms}; "
        f"observed_at_ms={observed_at_ms}; freshness={_decimal_text(freshness_0_1)}; "
        f"codes={code_text}."
    )


def _certainty_ceiling(proof: DecisionProofSnapshot) -> R23CertaintyCeiling:
    summary = proof.evidence_summary
    if summary.insufficient_count > 0:
        return R23CertaintyCeiling.INCOMPLETE
    if summary.contradict_count > 0:
        return R23CertaintyCeiling.CONFLICTED
    if proof.uncertainty_flags:
        return R23CertaintyCeiling.CONDITIONAL
    if proof.calibrated_probability_0_1 is not None:
        return R23CertaintyCeiling.CALIBRATED_CONDITIONAL
    return R23CertaintyCeiling.CONDITIONAL


def _simple_summary(ceiling: R23CertaintyCeiling) -> str:
    if ceiling is R23CertaintyCeiling.INCOMPLETE:
        return (
            "Some market evidence is missing or unsupported. "
            "Treat this as incomplete, not as confirmation."
        )
    if ceiling is R23CertaintyCeiling.CONFLICTED:
        return (
            "Accepted evidence disagrees. "
            "Treat this as a conditional setup with conflicting signals."
        )
    if ceiling is R23CertaintyCeiling.CALIBRATED_CONDITIONAL:
        return (
            "The setup has calibrated probability evidence for this scope, "
            "but it remains conditional and can invalidate."
        )
    return (
        "The evidence describes a conditional setup, not a certainty. "
        "Use the trigger and invalidation defined by the frozen forecast."
    )


def _pro_summary(
    ceiling: R23CertaintyCeiling,
    summary: DecisionProofEvidenceSummary,
    uncertainty_flags: tuple[str, ...],
) -> str:
    flags = ",".join(uncertainty_flags) if uncertainty_flags else "none"
    return (
        f"certainty_ceiling={ceiling.value}; support={summary.support_count}; "
        f"contradict={summary.contradict_count}; neutral={summary.neutral_count}; "
        f"insufficient={summary.insufficient_count}; available={summary.available_count}/"
        f"{summary.total_domain_count}; uncertainty_flags={flags}."
    )


def _probability_text(
    calibrated_probability_0_1: Decimal | None,
    probability_status: str,
) -> str:
    if calibrated_probability_0_1 is None:
        return (
            f"Probability is not calibrated for this forecast scope "
            f"(status={probability_status})."
        )
    percent = calibrated_probability_0_1 * Decimal(100)
    return (
        f"Calibrated probability for this exact forecast scope: "
        f"{_decimal_text(percent)}% (status={probability_status})."
    )


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _snapshot_payload(
    snapshot: R23ExplainableIntelligenceSnapshot,
) -> dict[str, object]:
    return {
        field.name: getattr(snapshot, field.name)
        for field in fields(snapshot)
        if field.name != "explanation_identity"
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
