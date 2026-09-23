from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_DOWN, Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.smart_capital_allocator import (
    VaultCapitalEnvelope,
    VaultEligibilityState,
)
from research.alpha_factory.probability_calibration_gate import (
    CalibratedProbabilityEvidence,
    R19ProbabilityStatus,
)

POSITION_SIZING_ENGINE_VERSION = "position-sizing-intelligence-v1-slice1/1"
POSITION_SIZING_SCHEMA_VERSION = "position-sizing-intelligence-v1/1"
POSITION_SIZING_SEMANTIC = "shadow_sizing_comparison_not_canonical_notional"
REAL_CAPITAL = 0
_FRACTION_QUANTUM = Decimal("0.000001")
_NOTIONAL_QUANTUM = Decimal("0.0001")
_EDGE_QUANTUM = Decimal("0.000001")


class SizingMethod(StrEnum):
    FIXED_FRACTIONAL = "fixed_fractional"
    KELLY_FULL = "kelly_full"
    KELLY_HALF = "kelly_half"
    KELLY_QUARTER = "kelly_quarter"


class SizingMethodStatus(StrEnum):
    AVAILABLE_SHADOW = "available_shadow"
    DISABLED_NO_CALIBRATED_PROBABILITY = "disabled_no_calibrated_probability"
    HOLD_ALLOCATOR_NOT_ELIGIBLE = "hold_allocator_not_eligible"
    HOLD_RISK_GATE = "hold_risk_gate"
    HOLD_NON_POSITIVE_CALIBRATED_EDGE = "hold_non_positive_calibrated_edge"


@dataclass(frozen=True, slots=True)
class PositionSizingPolicy:
    policy_identity: str
    schema_version: str
    engine_version: str
    policy_version: str
    fixed_fraction_of_vault: Decimal
    maximum_fraction_of_vault: Decimal
    maximum_absolute_correlation: Decimal
    maximum_drawdown_fraction: Decimal
    maximum_volatility_fraction: Decimal
    minimum_liquidity_score_0_1: Decimal
    maximum_transaction_cost_r: Decimal
    martingale_allowed: bool = False
    automatic_method_selection: bool = False
    canonical_notional_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "sizing policy identity")
        if self.schema_version != POSITION_SIZING_SCHEMA_VERSION:
            raise ValueError("unsupported sizing policy schema")
        if self.engine_version != POSITION_SIZING_ENGINE_VERSION:
            raise ValueError("unsupported sizing policy engine")
        if not self.policy_version.strip():
            raise ValueError("sizing policy_version must be non-empty")
        for value, label in (
            (self.fixed_fraction_of_vault, "fixed fraction"),
            (self.maximum_fraction_of_vault, "maximum vault fraction"),
            (self.maximum_absolute_correlation, "maximum absolute correlation"),
            (self.maximum_drawdown_fraction, "maximum drawdown fraction"),
            (self.maximum_volatility_fraction, "maximum volatility fraction"),
            (self.minimum_liquidity_score_0_1, "minimum liquidity score"),
        ):
            _require_unit_interval(value, label)
        if self.fixed_fraction_of_vault <= 0:
            raise ValueError("fixed fraction must be positive")
        if self.maximum_fraction_of_vault <= 0:
            raise ValueError("maximum vault fraction must be positive")
        if self.fixed_fraction_of_vault > self.maximum_fraction_of_vault:
            raise ValueError("fixed fraction cannot exceed maximum vault fraction")
        if (
            self.maximum_transaction_cost_r.is_nan()
            or self.maximum_transaction_cost_r.is_infinite()
            or self.maximum_transaction_cost_r < 0
        ):
            raise ValueError("maximum transaction cost R must be finite and non-negative")
        if self.martingale_allowed:
            raise ValueError("martingale remains forbidden")
        if (
            self.automatic_method_selection
            or self.canonical_notional_authority
            or self.production_authority
        ):
            raise ValueError(
                "Slice1 sizing has no automatic selection/canonical/production authority"
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("sizing policy identity mismatch")


@dataclass(frozen=True, slots=True)
class PositionSizingRiskContext:
    context_identity: str
    schema_version: str
    engine_version: str
    vault_id: PaperVaultId
    asset: str
    as_of_ms: int
    allocator_assessment_identity: str
    allocator_candidate_identity: str
    expected_win_r: Decimal
    expected_loss_r: Decimal
    transaction_cost_r: Decimal
    absolute_correlation_0_1: Decimal
    current_drawdown_fraction: Decimal
    volatility_fraction: Decimal
    liquidity_score_0_1: Decimal
    source_evidence_identities: tuple[str, ...]
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.context_identity, "sizing context identity")
        _require_sha256(
            self.allocator_assessment_identity,
            "sizing allocator assessment identity",
        )
        _require_sha256(
            self.allocator_candidate_identity,
            "sizing allocator candidate identity",
        )
        if self.schema_version != POSITION_SIZING_SCHEMA_VERSION:
            raise ValueError("unsupported sizing context schema")
        if self.engine_version != POSITION_SIZING_ENGINE_VERSION:
            raise ValueError("unsupported sizing context engine")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("sizing context asset must be non-empty uppercase")
        if self.as_of_ms < 0:
            raise ValueError("sizing context as_of_ms must be non-negative")
        for value, label in (
            (self.expected_win_r, "expected win R"),
            (self.expected_loss_r, "expected loss R"),
        ):
            if value.is_nan() or value.is_infinite() or value <= 0:
                raise ValueError(f"{label} must be finite and positive")
        if (
            self.transaction_cost_r.is_nan()
            or self.transaction_cost_r.is_infinite()
            or self.transaction_cost_r < 0
        ):
            raise ValueError("transaction cost R must be finite and non-negative")
        for value, label in (
            (self.absolute_correlation_0_1, "absolute correlation"),
            (self.current_drawdown_fraction, "current drawdown fraction"),
            (self.volatility_fraction, "volatility fraction"),
            (self.liquidity_score_0_1, "liquidity score"),
        ):
            _require_unit_interval(value, label)
        _require_identity_tuple(
            self.source_evidence_identities,
            "sizing context source evidence",
        )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.context_identity != canonical_sha256(_context_payload(self)):
            raise ValueError("sizing context identity mismatch")


@dataclass(frozen=True, slots=True)
class SizingMethodResult:
    result_identity: str
    method: SizingMethod
    status: SizingMethodStatus
    fraction_of_vault: Decimal | None
    hypothetical_notional_usdt: Decimal | None
    canonical_notional_usdt: None
    reason_codes: tuple[str, ...]
    uses_calibrated_probability: bool
    calibration_authorization_identity: str | None
    probability_0_1: Decimal | None
    expected_edge_r: Decimal | None
    kelly_raw_fraction: Decimal | None
    semantic: str = POSITION_SIZING_SEMANTIC
    winner_selected: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.result_identity, "sizing method result identity")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("sizing method reason codes must be unique and sorted")
        if not self.reason_codes:
            raise ValueError("sizing method result requires reason code")
        if self.status is SizingMethodStatus.AVAILABLE_SHADOW:
            if self.fraction_of_vault is None or self.hypothetical_notional_usdt is None:
                raise ValueError("available shadow sizing requires fraction and notional")
            if self.fraction_of_vault <= 0 or self.fraction_of_vault > 1:
                raise ValueError("available sizing fraction must be inside (0,1]")
            if self.hypothetical_notional_usdt <= 0:
                raise ValueError("available hypothetical notional must be positive")
        else:
            if self.fraction_of_vault is not None:
                raise ValueError("disabled/hold sizing cannot carry fraction")
            if self.hypothetical_notional_usdt is not None:
                raise ValueError("disabled/hold sizing cannot carry notional")
        if self.canonical_notional_usdt is not None:
            raise ValueError("Slice1 cannot produce canonical notional")
        if self.uses_calibrated_probability:
            if (
                self.calibration_authorization_identity is None
                or self.probability_0_1 is None
            ):
                raise ValueError("calibrated sizing requires authorization and probability")
            _require_sha256(
                self.calibration_authorization_identity,
                "sizing calibration authorization identity",
            )
            _require_unit_interval(self.probability_0_1, "sizing probability")
        else:
            if self.calibration_authorization_identity is not None:
                raise ValueError("uncalibrated sizing cannot carry calibration identity")
            if self.probability_0_1 is not None:
                raise ValueError("uncalibrated sizing cannot carry probability")
            if self.expected_edge_r is not None or self.kelly_raw_fraction is not None:
                raise ValueError("uncalibrated sizing cannot carry edge/Kelly values")
        if self.semantic != POSITION_SIZING_SEMANTIC:
            raise ValueError("sizing result semantic mismatch")
        if self.winner_selected or self.production_authority:
            raise ValueError("sizing result cannot select winner or gain production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.result_identity != canonical_sha256(_method_result_payload(self)):
            raise ValueError("sizing method result identity mismatch")


@dataclass(frozen=True, slots=True)
class PositionSizingAssessment:
    assessment_identity: str
    schema_version: str
    engine_version: str
    policy_identity: str
    context_identity: str
    vault_id: PaperVaultId
    allocator_candidate_identity: str
    allocator_vault_starting_budget_usdt: Decimal
    result_identities: tuple[str, ...]
    results: tuple[SizingMethodResult, ...]
    calibrated_probability_available: bool
    selected_method: None = None
    selected_fraction_of_vault: None = None
    canonical_notional_usdt: None = None
    automatic_method_selection: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.assessment_identity, "sizing assessment identity"),
            (self.policy_identity, "sizing assessment policy identity"),
            (self.context_identity, "sizing assessment context identity"),
            (self.allocator_candidate_identity, "sizing candidate identity"),
        ):
            _require_sha256(identity, label)
        if self.schema_version != POSITION_SIZING_SCHEMA_VERSION:
            raise ValueError("unsupported sizing assessment schema")
        if self.engine_version != POSITION_SIZING_ENGINE_VERSION:
            raise ValueError("unsupported sizing assessment engine")
        if self.allocator_vault_starting_budget_usdt <= 0:
            raise ValueError("sizing vault starting budget must be positive")
        expected_methods = tuple(sorted(SizingMethod, key=lambda item: item.value))
        if tuple(item.method for item in self.results) != expected_methods:
            raise ValueError("sizing assessment requires all methods in canonical order")
        if tuple(sorted(item.result_identity for item in self.results)) != (
            self.result_identities
        ):
            raise ValueError("sizing assessment result identities mismatch")
        if (
            self.selected_method is not None
            or self.selected_fraction_of_vault is not None
            or self.canonical_notional_usdt is not None
            or self.automatic_method_selection
            or self.production_authority
        ):
            raise ValueError("Slice1 assessment cannot select or canonicalize sizing")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.assessment_identity != canonical_sha256(_assessment_payload(self)):
            raise ValueError("sizing assessment identity mismatch")


def build_position_sizing_policy(
    *,
    policy_version: str,
    fixed_fraction_of_vault: Decimal,
    maximum_fraction_of_vault: Decimal,
    maximum_absolute_correlation: Decimal,
    maximum_drawdown_fraction: Decimal,
    maximum_volatility_fraction: Decimal,
    minimum_liquidity_score_0_1: Decimal,
    maximum_transaction_cost_r: Decimal,
) -> PositionSizingPolicy:
    payload = {
        "automatic_method_selection": False,
        "canonical_notional_authority": False,
        "engine_version": POSITION_SIZING_ENGINE_VERSION,
        "fixed_fraction_of_vault": fixed_fraction_of_vault,
        "martingale_allowed": False,
        "maximum_absolute_correlation": maximum_absolute_correlation,
        "maximum_drawdown_fraction": maximum_drawdown_fraction,
        "maximum_fraction_of_vault": maximum_fraction_of_vault,
        "maximum_transaction_cost_r": maximum_transaction_cost_r,
        "maximum_volatility_fraction": maximum_volatility_fraction,
        "minimum_liquidity_score_0_1": minimum_liquidity_score_0_1,
        "policy_version": policy_version,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": POSITION_SIZING_SCHEMA_VERSION,
    }
    return PositionSizingPolicy(
        policy_identity=canonical_sha256(payload),
        schema_version=POSITION_SIZING_SCHEMA_VERSION,
        engine_version=POSITION_SIZING_ENGINE_VERSION,
        policy_version=policy_version,
        fixed_fraction_of_vault=fixed_fraction_of_vault,
        maximum_fraction_of_vault=maximum_fraction_of_vault,
        maximum_absolute_correlation=maximum_absolute_correlation,
        maximum_drawdown_fraction=maximum_drawdown_fraction,
        maximum_volatility_fraction=maximum_volatility_fraction,
        minimum_liquidity_score_0_1=minimum_liquidity_score_0_1,
        maximum_transaction_cost_r=maximum_transaction_cost_r,
    )


def build_position_sizing_risk_context(
    *,
    vault_id: PaperVaultId,
    asset: str,
    as_of_ms: int,
    allocator_assessment_identity: str,
    allocator_candidate_identity: str,
    expected_win_r: Decimal,
    expected_loss_r: Decimal,
    transaction_cost_r: Decimal,
    absolute_correlation_0_1: Decimal,
    current_drawdown_fraction: Decimal,
    volatility_fraction: Decimal,
    liquidity_score_0_1: Decimal,
    source_evidence_identities: tuple[str, ...],
) -> PositionSizingRiskContext:
    sources = tuple(sorted(set(source_evidence_identities)))
    payload = {
        "absolute_correlation_0_1": absolute_correlation_0_1,
        "allocator_assessment_identity": allocator_assessment_identity,
        "allocator_candidate_identity": allocator_candidate_identity,
        "as_of_ms": as_of_ms,
        "asset": asset,
        "current_drawdown_fraction": current_drawdown_fraction,
        "engine_version": POSITION_SIZING_ENGINE_VERSION,
        "expected_loss_r": expected_loss_r,
        "expected_win_r": expected_win_r,
        "liquidity_score_0_1": liquidity_score_0_1,
        "real_capital": REAL_CAPITAL,
        "schema_version": POSITION_SIZING_SCHEMA_VERSION,
        "source_evidence_identities": sources,
        "transaction_cost_r": transaction_cost_r,
        "vault_id": vault_id,
        "volatility_fraction": volatility_fraction,
    }
    return PositionSizingRiskContext(
        context_identity=canonical_sha256(payload),
        schema_version=POSITION_SIZING_SCHEMA_VERSION,
        engine_version=POSITION_SIZING_ENGINE_VERSION,
        vault_id=vault_id,
        asset=asset,
        as_of_ms=as_of_ms,
        allocator_assessment_identity=allocator_assessment_identity,
        allocator_candidate_identity=allocator_candidate_identity,
        expected_win_r=expected_win_r,
        expected_loss_r=expected_loss_r,
        transaction_cost_r=transaction_cost_r,
        absolute_correlation_0_1=absolute_correlation_0_1,
        current_drawdown_fraction=current_drawdown_fraction,
        volatility_fraction=volatility_fraction,
        liquidity_score_0_1=liquidity_score_0_1,
        source_evidence_identities=sources,
    )


def evaluate_position_sizing_intelligence(
    *,
    policy: PositionSizingPolicy,
    vault: VaultCapitalEnvelope,
    context: PositionSizingRiskContext,
    calibrated_probability: CalibratedProbabilityEvidence | None = None,
) -> PositionSizingAssessment:
    _validate_lineage(vault=vault, context=context, probability=calibrated_probability)
    risk_reasons = _risk_gate_reasons(policy, context)

    probability_value: Decimal | None = None
    expected_edge: Decimal | None = None
    kelly_raw: Decimal | None = None
    if calibrated_probability is not None:
        probability_value = calibrated_probability.probability_0_1
        net_win = context.expected_win_r - context.transaction_cost_r
        net_loss = context.expected_loss_r + context.transaction_cost_r
        if net_win <= 0:
            expected_edge = -net_loss
            kelly_raw = Decimal(0)
        else:
            expected_edge = (
                probability_value * net_win
                - (Decimal(1) - probability_value) * net_loss
            )
            payoff_ratio = net_win / net_loss
            kelly_raw = (
                probability_value
                - (Decimal(1) - probability_value) / payoff_ratio
            )
            if kelly_raw < 0:
                kelly_raw = Decimal(0)
        expected_edge = _q_edge(expected_edge)
        kelly_raw = _q_fraction(kelly_raw)

    results = tuple(
        _method_result(
            method=method,
            policy=policy,
            vault=vault,
            context=context,
            risk_reasons=risk_reasons,
            calibrated_probability=calibrated_probability,
            probability_value=probability_value,
            expected_edge=expected_edge,
            kelly_raw=kelly_raw,
        )
        for method in sorted(SizingMethod, key=lambda item: item.value)
    )
    result_ids = tuple(sorted(item.result_identity for item in results))
    payload = {
        "allocator_candidate_identity": context.allocator_candidate_identity,
        "allocator_vault_starting_budget_usdt": vault.starting_budget_usdt,
        "automatic_method_selection": False,
        "calibrated_probability_available": calibrated_probability is not None,
        "canonical_notional_usdt": None,
        "context_identity": context.context_identity,
        "engine_version": POSITION_SIZING_ENGINE_VERSION,
        "policy_identity": policy.policy_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "result_identities": result_ids,
        "results": results,
        "schema_version": POSITION_SIZING_SCHEMA_VERSION,
        "selected_fraction_of_vault": None,
        "selected_method": None,
        "vault_id": context.vault_id,
    }
    return PositionSizingAssessment(
        assessment_identity=canonical_sha256(payload),
        schema_version=POSITION_SIZING_SCHEMA_VERSION,
        engine_version=POSITION_SIZING_ENGINE_VERSION,
        policy_identity=policy.policy_identity,
        context_identity=context.context_identity,
        vault_id=context.vault_id,
        allocator_candidate_identity=context.allocator_candidate_identity,
        allocator_vault_starting_budget_usdt=vault.starting_budget_usdt,
        result_identities=result_ids,
        results=results,
        calibrated_probability_available=calibrated_probability is not None,
    )


def _method_result(
    *,
    method: SizingMethod,
    policy: PositionSizingPolicy,
    vault: VaultCapitalEnvelope,
    context: PositionSizingRiskContext,
    risk_reasons: tuple[str, ...],
    calibrated_probability: CalibratedProbabilityEvidence | None,
    probability_value: Decimal | None,
    expected_edge: Decimal | None,
    kelly_raw: Decimal | None,
) -> SizingMethodResult:
    uses_probability = method is not SizingMethod.FIXED_FRACTIONAL
    authorization_identity = (
        None
        if not uses_probability or calibrated_probability is None
        else calibrated_probability.authorization_identity
    )
    probability = probability_value if uses_probability else None
    method_edge = expected_edge if uses_probability else None
    method_kelly = kelly_raw if uses_probability else None

    if vault.eligibility_state is not VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE:
        return _disabled_result(
            method=method,
            status=SizingMethodStatus.HOLD_ALLOCATOR_NOT_ELIGIBLE,
            reasons=("allocator_vault_not_eligible",),
            uses_probability=uses_probability and calibrated_probability is not None,
            authorization_identity=authorization_identity,
            probability=probability,
            expected_edge=method_edge,
            kelly_raw=method_kelly,
        )
    if risk_reasons:
        return _disabled_result(
            method=method,
            status=SizingMethodStatus.HOLD_RISK_GATE,
            reasons=risk_reasons,
            uses_probability=uses_probability and calibrated_probability is not None,
            authorization_identity=authorization_identity,
            probability=probability,
            expected_edge=method_edge,
            kelly_raw=method_kelly,
        )
    if uses_probability and calibrated_probability is None:
        return _disabled_result(
            method=method,
            status=SizingMethodStatus.DISABLED_NO_CALIBRATED_PROBABILITY,
            reasons=("r19_calibrated_probability_required",),
            uses_probability=False,
            authorization_identity=None,
            probability=None,
            expected_edge=None,
            kelly_raw=None,
        )
    if uses_probability and (
        expected_edge is None or kelly_raw is None or expected_edge <= 0 or kelly_raw <= 0
    ):
        return _disabled_result(
            method=method,
            status=SizingMethodStatus.HOLD_NON_POSITIVE_CALIBRATED_EDGE,
            reasons=("calibrated_expected_edge_not_positive",),
            uses_probability=True,
            authorization_identity=authorization_identity,
            probability=probability,
            expected_edge=method_edge,
            kelly_raw=method_kelly,
        )

    if method is SizingMethod.FIXED_FRACTIONAL:
        fraction = policy.fixed_fraction_of_vault
        reasons = ("fixed_fractional_shadow_baseline",)
        uses_probability = False
        authorization_identity = None
        probability = None
        method_edge = None
        method_kelly = None
    else:
        assert kelly_raw is not None
        multiplier = {
            SizingMethod.KELLY_FULL: Decimal(1),
            SizingMethod.KELLY_HALF: Decimal("0.5"),
            SizingMethod.KELLY_QUARTER: Decimal("0.25"),
        }[method]
        fraction = kelly_raw * multiplier
        if fraction > policy.maximum_fraction_of_vault:
            fraction = policy.maximum_fraction_of_vault
        reasons = (f"{method.value}_shadow_only",)

    fraction = _q_fraction(fraction)
    notional = _q_notional(vault.starting_budget_usdt * fraction)
    payload = {
        "calibration_authorization_identity": authorization_identity,
        "canonical_notional_usdt": None,
        "expected_edge_r": method_edge,
        "fraction_of_vault": fraction,
        "hypothetical_notional_usdt": notional,
        "kelly_raw_fraction": method_kelly,
        "method": method,
        "probability_0_1": probability,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reason_codes": reasons,
        "semantic": POSITION_SIZING_SEMANTIC,
        "status": SizingMethodStatus.AVAILABLE_SHADOW,
        "uses_calibrated_probability": uses_probability,
        "winner_selected": False,
    }
    return SizingMethodResult(
        result_identity=canonical_sha256(payload),
        method=method,
        status=SizingMethodStatus.AVAILABLE_SHADOW,
        fraction_of_vault=fraction,
        hypothetical_notional_usdt=notional,
        canonical_notional_usdt=None,
        reason_codes=reasons,
        uses_calibrated_probability=uses_probability,
        calibration_authorization_identity=authorization_identity,
        probability_0_1=probability,
        expected_edge_r=method_edge,
        kelly_raw_fraction=method_kelly,
    )


def _disabled_result(
    *,
    method: SizingMethod,
    status: SizingMethodStatus,
    reasons: tuple[str, ...],
    uses_probability: bool,
    authorization_identity: str | None,
    probability: Decimal | None,
    expected_edge: Decimal | None,
    kelly_raw: Decimal | None,
) -> SizingMethodResult:
    ordered_reasons = tuple(sorted(set(reasons)))
    payload = {
        "calibration_authorization_identity": authorization_identity,
        "canonical_notional_usdt": None,
        "expected_edge_r": expected_edge,
        "fraction_of_vault": None,
        "hypothetical_notional_usdt": None,
        "kelly_raw_fraction": kelly_raw,
        "method": method,
        "probability_0_1": probability,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reason_codes": ordered_reasons,
        "semantic": POSITION_SIZING_SEMANTIC,
        "status": status,
        "uses_calibrated_probability": uses_probability,
        "winner_selected": False,
    }
    return SizingMethodResult(
        result_identity=canonical_sha256(payload),
        method=method,
        status=status,
        fraction_of_vault=None,
        hypothetical_notional_usdt=None,
        canonical_notional_usdt=None,
        reason_codes=ordered_reasons,
        uses_calibrated_probability=uses_probability,
        calibration_authorization_identity=authorization_identity,
        probability_0_1=probability,
        expected_edge_r=expected_edge,
        kelly_raw_fraction=kelly_raw,
    )


def _validate_lineage(
    *,
    vault: VaultCapitalEnvelope,
    context: PositionSizingRiskContext,
    probability: CalibratedProbabilityEvidence | None,
) -> None:
    if vault.vault_id is not context.vault_id:
        raise ValueError("sizing vault/context id mismatch")
    if vault.candidate_identity != context.allocator_candidate_identity:
        raise ValueError("sizing allocator candidate lineage mismatch")
    if context.as_of_ms < 0:
        raise ValueError("sizing context time invalid")
    if probability is not None:
        if probability.probability_status is not R19ProbabilityStatus.CALIBRATED:
            raise ValueError("Kelly requires R19 CALIBRATED probability")
        if probability.issued_at_ms > context.as_of_ms:
            raise ValueError("sizing probability is from the future")
        if probability.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")


def _risk_gate_reasons(
    policy: PositionSizingPolicy,
    context: PositionSizingRiskContext,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    if context.absolute_correlation_0_1 > policy.maximum_absolute_correlation:
        reasons.add("correlation_limit_breached")
    if context.current_drawdown_fraction > policy.maximum_drawdown_fraction:
        reasons.add("drawdown_limit_breached")
    if context.volatility_fraction > policy.maximum_volatility_fraction:
        reasons.add("volatility_limit_breached")
    if context.liquidity_score_0_1 < policy.minimum_liquidity_score_0_1:
        reasons.add("liquidity_floor_breached")
    if context.transaction_cost_r > policy.maximum_transaction_cost_r:
        reasons.add("transaction_cost_limit_breached")
    return tuple(sorted(reasons))


def _policy_payload(policy: PositionSizingPolicy) -> dict[str, object]:
    return {
        "automatic_method_selection": policy.automatic_method_selection,
        "canonical_notional_authority": policy.canonical_notional_authority,
        "engine_version": policy.engine_version,
        "fixed_fraction_of_vault": policy.fixed_fraction_of_vault,
        "martingale_allowed": policy.martingale_allowed,
        "maximum_absolute_correlation": policy.maximum_absolute_correlation,
        "maximum_drawdown_fraction": policy.maximum_drawdown_fraction,
        "maximum_fraction_of_vault": policy.maximum_fraction_of_vault,
        "maximum_transaction_cost_r": policy.maximum_transaction_cost_r,
        "maximum_volatility_fraction": policy.maximum_volatility_fraction,
        "minimum_liquidity_score_0_1": policy.minimum_liquidity_score_0_1,
        "policy_version": policy.policy_version,
        "production_authority": policy.production_authority,
        "real_capital": policy.real_capital,
        "schema_version": policy.schema_version,
    }


def _context_payload(context: PositionSizingRiskContext) -> dict[str, object]:
    return {
        "absolute_correlation_0_1": context.absolute_correlation_0_1,
        "allocator_assessment_identity": context.allocator_assessment_identity,
        "allocator_candidate_identity": context.allocator_candidate_identity,
        "as_of_ms": context.as_of_ms,
        "asset": context.asset,
        "current_drawdown_fraction": context.current_drawdown_fraction,
        "engine_version": context.engine_version,
        "expected_loss_r": context.expected_loss_r,
        "expected_win_r": context.expected_win_r,
        "liquidity_score_0_1": context.liquidity_score_0_1,
        "real_capital": context.real_capital,
        "schema_version": context.schema_version,
        "source_evidence_identities": context.source_evidence_identities,
        "transaction_cost_r": context.transaction_cost_r,
        "vault_id": context.vault_id,
        "volatility_fraction": context.volatility_fraction,
    }


def _method_result_payload(result: SizingMethodResult) -> dict[str, object]:
    return {
        "calibration_authorization_identity": (
            result.calibration_authorization_identity
        ),
        "canonical_notional_usdt": result.canonical_notional_usdt,
        "expected_edge_r": result.expected_edge_r,
        "fraction_of_vault": result.fraction_of_vault,
        "hypothetical_notional_usdt": result.hypothetical_notional_usdt,
        "kelly_raw_fraction": result.kelly_raw_fraction,
        "method": result.method,
        "probability_0_1": result.probability_0_1,
        "production_authority": result.production_authority,
        "real_capital": result.real_capital,
        "reason_codes": result.reason_codes,
        "semantic": result.semantic,
        "status": result.status,
        "uses_calibrated_probability": result.uses_calibrated_probability,
        "winner_selected": result.winner_selected,
    }


def _assessment_payload(assessment: PositionSizingAssessment) -> dict[str, object]:
    return {
        "allocator_candidate_identity": assessment.allocator_candidate_identity,
        "allocator_vault_starting_budget_usdt": (
            assessment.allocator_vault_starting_budget_usdt
        ),
        "automatic_method_selection": assessment.automatic_method_selection,
        "calibrated_probability_available": (
            assessment.calibrated_probability_available
        ),
        "canonical_notional_usdt": assessment.canonical_notional_usdt,
        "context_identity": assessment.context_identity,
        "engine_version": assessment.engine_version,
        "policy_identity": assessment.policy_identity,
        "production_authority": assessment.production_authority,
        "real_capital": assessment.real_capital,
        "result_identities": assessment.result_identities,
        "results": assessment.results,
        "schema_version": assessment.schema_version,
        "selected_fraction_of_vault": assessment.selected_fraction_of_vault,
        "selected_method": assessment.selected_method,
        "vault_id": assessment.vault_id,
    }


def _q_fraction(value: Decimal) -> Decimal:
    return value.quantize(_FRACTION_QUANTUM, rounding=ROUND_HALF_DOWN)


def _q_notional(value: Decimal) -> Decimal:
    return value.quantize(_NOTIONAL_QUANTUM, rounding=ROUND_HALF_DOWN)


def _q_edge(value: Decimal) -> Decimal:
    return value.quantize(_EDGE_QUANTUM, rounding=ROUND_HALF_DOWN)


def _require_unit_interval(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite() or value < 0 or value > 1:
        raise ValueError(f"{label} must be inside [0,1]")


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
