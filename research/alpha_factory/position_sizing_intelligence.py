from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epochs import EPOCH_2_SPEC, PaperVaultId
from crypto_signal.paper.smart_capital_allocator import (
    SmartCapitalAllocationAssessment,
    SmartCapitalCandidate,
    VaultEligibilityState,
)
from research.alpha_factory.probability_calibration_gate import (
    CalibratedProbabilityEvidence,
    R19ProbabilityStatus,
)

POSITION_SIZING_ENGINE_VERSION = "position-sizing-intelligence-v1-slice1/1"
POSITION_SIZING_SCHEMA_VERSION = "position-sizing-intelligence-v1/1"
POSITION_SIZING_SEMANTIC = "shadow_research_position_sizing_not_trade_authority"
REAL_CAPITAL = 0


class SizingMethod(StrEnum):
    FIXED_FRACTIONAL = "fixed_fractional"
    FULL_KELLY = "full_kelly"
    HALF_KELLY = "half_kelly"
    QUARTER_KELLY = "quarter_kelly"


class SizingScenarioStatus(StrEnum):
    AVAILABLE_RESEARCH_SCENARIO = "available_research_scenario"
    BLOCKED_VAULT = "blocked_vault"
    BLOCKED_RISK_GATE = "blocked_risk_gate"
    BLOCKED_NO_CALIBRATED_PROBABILITY = "blocked_no_calibrated_probability"


class SizingComparisonStatus(StrEnum):
    EVALUATED = "evaluated"
    HOLD_CASH = "hold_cash"


@dataclass(frozen=True, slots=True)
class PositionSizingPolicy:
    policy_identity: str
    schema_version: str
    engine_version: str
    policy_version: str
    fixed_fractional_risk_fraction: Decimal
    max_risk_fraction: Decimal
    max_notional_fraction: Decimal
    max_drawdown_fraction: Decimal
    max_volatility_fraction: Decimal
    minimum_liquidity_quality_0_1: Decimal
    max_abs_correlation_0_1: Decimal
    max_transaction_cost_fraction: Decimal
    semantic: str = POSITION_SIZING_SEMANTIC
    automatic_method_selection: bool = False
    automatic_promotion: bool = False
    ledger_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "position-sizing policy identity")
        if self.schema_version != POSITION_SIZING_SCHEMA_VERSION:
            raise ValueError("unsupported position-sizing schema")
        if self.engine_version != POSITION_SIZING_ENGINE_VERSION:
            raise ValueError("unsupported position-sizing engine")
        if not self.policy_version.strip():
            raise ValueError("position-sizing policy version must be non-empty")
        for value, label in (
            (self.fixed_fractional_risk_fraction, "fixed fractional risk fraction"),
            (self.max_risk_fraction, "maximum risk fraction"),
            (self.max_notional_fraction, "maximum notional fraction"),
            (self.max_drawdown_fraction, "maximum drawdown fraction"),
            (self.max_volatility_fraction, "maximum volatility fraction"),
            (
                self.minimum_liquidity_quality_0_1,
                "minimum liquidity quality",
            ),
            (self.max_abs_correlation_0_1, "maximum absolute correlation"),
            (
                self.max_transaction_cost_fraction,
                "maximum transaction cost fraction",
            ),
        ):
            _require_unit_interval(value, label)
        if self.fixed_fractional_risk_fraction <= Decimal(0):
            raise ValueError("fixed fractional risk fraction must be positive")
        if self.max_risk_fraction <= Decimal(0):
            raise ValueError("maximum risk fraction must be positive")
        if self.max_notional_fraction <= Decimal(0):
            raise ValueError("maximum notional fraction must be positive")
        if self.fixed_fractional_risk_fraction > self.max_risk_fraction:
            raise ValueError("fixed fractional risk cannot exceed maximum risk")
        if self.max_notional_fraction > Decimal(1):
            raise ValueError("canonical v1.1 sizing cannot permit leverage")
        if self.semantic != POSITION_SIZING_SEMANTIC:
            raise ValueError("position-sizing semantic mismatch")
        if (
            self.automatic_method_selection
            or self.automatic_promotion
            or self.ledger_write_authority
            or self.production_authority
        ):
            raise ValueError(
                "position-sizing Slice1 has no selection/promotion/write authority"
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("position-sizing policy identity mismatch")


@dataclass(frozen=True, slots=True)
class PositionSizingContext:
    context_identity: str
    schema_version: str
    engine_version: str
    allocation_assessment_identity: str
    candidate_identity: str
    vault_id: PaperVaultId
    vault_budget_usdt: Decimal
    asset: str
    timeframe: str
    as_of_ms: int
    required_probability_scope_identity: str
    expected_gain_fraction: Decimal
    expected_loss_fraction: Decimal
    current_drawdown_fraction: Decimal
    volatility_fraction: Decimal
    liquidity_quality_0_1: Decimal
    max_abs_correlation_0_1: Decimal
    transaction_cost_fraction: Decimal
    source_evidence_identities: tuple[str, ...]
    semantic: str = POSITION_SIZING_SEMANTIC
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.context_identity, "position-sizing context identity"),
            (
                self.allocation_assessment_identity,
                "position-sizing allocation assessment identity",
            ),
            (self.candidate_identity, "position-sizing candidate identity"),
            (
                self.required_probability_scope_identity,
                "position-sizing probability scope identity",
            ),
        ):
            _require_sha256(identity, label)
        if self.schema_version != POSITION_SIZING_SCHEMA_VERSION:
            raise ValueError("unsupported position-sizing context schema")
        if self.engine_version != POSITION_SIZING_ENGINE_VERSION:
            raise ValueError("unsupported position-sizing context engine")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("position-sizing vault_id must be PaperVaultId")
        if self.vault_budget_usdt <= Decimal(0):
            raise ValueError("position-sizing vault budget must be positive")
        _require_asset(self.asset)
        if not self.timeframe.strip():
            raise ValueError("position-sizing timeframe must be non-empty")
        if self.as_of_ms < 0:
            raise ValueError("position-sizing as_of_ms must be non-negative")
        for value, label in (
            (self.expected_gain_fraction, "expected gain fraction"),
            (self.expected_loss_fraction, "expected loss fraction"),
        ):
            _require_positive_decimal(value, label)
        for value, label in (
            (self.current_drawdown_fraction, "current drawdown fraction"),
            (self.volatility_fraction, "volatility fraction"),
            (self.liquidity_quality_0_1, "liquidity quality"),
            (self.max_abs_correlation_0_1, "maximum absolute correlation"),
            (self.transaction_cost_fraction, "transaction cost fraction"),
        ):
            _require_unit_interval(value, label)
        _require_identity_tuple(
            self.source_evidence_identities,
            "position-sizing source evidence",
        )
        if not self.source_evidence_identities:
            raise ValueError("position-sizing context requires source evidence")
        if self.semantic != POSITION_SIZING_SEMANTIC:
            raise ValueError("position-sizing context semantic mismatch")
        if self.production_authority:
            raise ValueError("position-sizing context has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.context_identity != canonical_sha256(_context_payload(self)):
            raise ValueError("position-sizing context identity mismatch")


@dataclass(frozen=True, slots=True)
class PositionSizingScenario:
    scenario_identity: str
    engine_version: str
    schema_version: str
    method: SizingMethod
    status: SizingScenarioStatus
    block_reasons: tuple[str, ...]
    context_identity: str
    policy_identity: str
    vault_id: PaperVaultId
    vault_budget_usdt: Decimal
    calibrated_probability_authorization_identity: str | None
    calibration_evidence_identity: str | None
    probability_0_1: Decimal | None
    expected_edge_fraction: Decimal | None
    raw_notional_fraction: Decimal | None
    bounded_notional_fraction: Decimal | None
    implied_risk_fraction: Decimal | None
    risk_budget_usdt: Decimal | None
    notional_usdt: Decimal | None
    no_leverage: bool = True
    shadow_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.scenario_identity, "position-sizing scenario identity")
        _require_sha256(self.context_identity, "position-sizing scenario context")
        _require_sha256(self.policy_identity, "position-sizing scenario policy")
        if self.engine_version != POSITION_SIZING_ENGINE_VERSION:
            raise ValueError("unsupported position-sizing scenario engine")
        if self.schema_version != POSITION_SIZING_SCHEMA_VERSION:
            raise ValueError("unsupported position-sizing scenario schema")
        if tuple(sorted(set(self.block_reasons))) != self.block_reasons:
            raise ValueError("position-sizing block reasons must be unique and sorted")
        if self.vault_budget_usdt <= Decimal(0):
            raise ValueError("position-sizing scenario vault budget must be positive")
        for identity, label in (
            (
                self.calibrated_probability_authorization_identity,
                "position-sizing probability authorization",
            ),
            (
                self.calibration_evidence_identity,
                "position-sizing calibration evidence",
            ),
        ):
            if identity is not None:
                _require_sha256(identity, label)
        if self.probability_0_1 is not None:
            _require_unit_interval(
                self.probability_0_1,
                "position-sizing probability",
            )

        values = (
            self.raw_notional_fraction,
            self.bounded_notional_fraction,
            self.implied_risk_fraction,
            self.risk_budget_usdt,
            self.notional_usdt,
        )
        if self.status is SizingScenarioStatus.AVAILABLE_RESEARCH_SCENARIO:
            if self.block_reasons:
                raise ValueError("available sizing scenario cannot have block reasons")
            if any(value is None for value in values):
                raise ValueError("available sizing scenario requires numeric sizing values")
            assert self.raw_notional_fraction is not None
            assert self.bounded_notional_fraction is not None
            assert self.implied_risk_fraction is not None
            assert self.risk_budget_usdt is not None
            assert self.notional_usdt is not None
            for value, label in (
                (self.raw_notional_fraction, "raw notional fraction"),
                (self.bounded_notional_fraction, "bounded notional fraction"),
                (self.implied_risk_fraction, "implied risk fraction"),
            ):
                if value < Decimal(0):
                    raise ValueError(f"{label} cannot be negative")
            if self.bounded_notional_fraction > Decimal(1):
                raise ValueError("bounded sizing scenario cannot imply leverage")
            if self.risk_budget_usdt < Decimal(0) or self.notional_usdt < Decimal(0):
                raise ValueError("sizing USDT outputs cannot be negative")
            if self.notional_usdt > self.vault_budget_usdt:
                raise ValueError("sizing scenario cannot exceed vault budget")
        else:
            if not self.block_reasons:
                raise ValueError("blocked sizing scenario requires reasons")
            if any(value is not None for value in values):
                raise ValueError("blocked sizing scenario cannot expose sizing values")

        if self.method is not SizingMethod.FIXED_FRACTIONAL:
            if (
                self.status is SizingScenarioStatus.AVAILABLE_RESEARCH_SCENARIO
                and self.calibrated_probability_authorization_identity is None
            ):
                raise ValueError("Kelly sizing requires calibrated probability evidence")
        if not self.no_leverage or not self.shadow_only:
            raise ValueError("Phase11 Slice1 scenarios must be shadow-only and no-leverage")
        if self.production_authority:
            raise ValueError("position-sizing scenario has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.scenario_identity != canonical_sha256(_scenario_payload(self)):
            raise ValueError("position-sizing scenario identity mismatch")


@dataclass(frozen=True, slots=True)
class PositionSizingComparison:
    comparison_identity: str
    engine_version: str
    schema_version: str
    context_identity: str
    policy_identity: str
    status: SizingComparisonStatus
    scenarios: tuple[PositionSizingScenario, ...]
    selected_method: None = None
    automatic_method_selection: bool = False
    automatic_promotion: bool = False
    ledger_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.comparison_identity, "position-sizing comparison identity"),
            (self.context_identity, "position-sizing comparison context"),
            (self.policy_identity, "position-sizing comparison policy"),
        ):
            _require_sha256(identity, label)
        if self.engine_version != POSITION_SIZING_ENGINE_VERSION:
            raise ValueError("unsupported position-sizing comparison engine")
        if self.schema_version != POSITION_SIZING_SCHEMA_VERSION:
            raise ValueError("unsupported position-sizing comparison schema")
        expected_methods = tuple(sorted(SizingMethod, key=lambda item: item.value))
        if tuple(item.method for item in self.scenarios) != expected_methods:
            raise ValueError("position-sizing comparison requires canonical four-method order")
        if self.selected_method is not None:
            raise ValueError("Phase11 Slice1 cannot select a sizing winner")
        if (
            self.automatic_method_selection
            or self.automatic_promotion
            or self.ledger_write_authority
            or self.production_authority
        ):
            raise ValueError("position-sizing comparison has no mutation authority")
        if self.status is SizingComparisonStatus.HOLD_CASH and any(
            item.status is SizingScenarioStatus.AVAILABLE_RESEARCH_SCENARIO
            for item in self.scenarios
        ):
            raise ValueError("HOLD_CASH comparison cannot contain available scenario")
        if self.status is SizingComparisonStatus.EVALUATED and not any(
            item.status is SizingScenarioStatus.AVAILABLE_RESEARCH_SCENARIO
            for item in self.scenarios
        ):
            raise ValueError("evaluated comparison requires at least one available scenario")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.comparison_identity != canonical_sha256(_comparison_payload(self)):
            raise ValueError("position-sizing comparison identity mismatch")


def build_position_sizing_policy(
    *,
    policy_version: str,
    fixed_fractional_risk_fraction: Decimal,
    max_risk_fraction: Decimal,
    max_notional_fraction: Decimal,
    max_drawdown_fraction: Decimal,
    max_volatility_fraction: Decimal,
    minimum_liquidity_quality_0_1: Decimal,
    max_abs_correlation_0_1: Decimal,
    max_transaction_cost_fraction: Decimal,
) -> PositionSizingPolicy:
    payload = {
        "automatic_method_selection": False,
        "automatic_promotion": False,
        "engine_version": POSITION_SIZING_ENGINE_VERSION,
        "fixed_fractional_risk_fraction": fixed_fractional_risk_fraction,
        "ledger_write_authority": False,
        "max_abs_correlation_0_1": max_abs_correlation_0_1,
        "max_drawdown_fraction": max_drawdown_fraction,
        "max_notional_fraction": max_notional_fraction,
        "max_risk_fraction": max_risk_fraction,
        "max_transaction_cost_fraction": max_transaction_cost_fraction,
        "max_volatility_fraction": max_volatility_fraction,
        "minimum_liquidity_quality_0_1": minimum_liquidity_quality_0_1,
        "policy_version": policy_version,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": POSITION_SIZING_SCHEMA_VERSION,
        "semantic": POSITION_SIZING_SEMANTIC,
    }
    return PositionSizingPolicy(
        policy_identity=canonical_sha256(payload),
        schema_version=POSITION_SIZING_SCHEMA_VERSION,
        engine_version=POSITION_SIZING_ENGINE_VERSION,
        policy_version=policy_version,
        fixed_fractional_risk_fraction=fixed_fractional_risk_fraction,
        max_risk_fraction=max_risk_fraction,
        max_notional_fraction=max_notional_fraction,
        max_drawdown_fraction=max_drawdown_fraction,
        max_volatility_fraction=max_volatility_fraction,
        minimum_liquidity_quality_0_1=minimum_liquidity_quality_0_1,
        max_abs_correlation_0_1=max_abs_correlation_0_1,
        max_transaction_cost_fraction=max_transaction_cost_fraction,
    )


def build_position_sizing_context(
    assessment: SmartCapitalAllocationAssessment,
    candidate: SmartCapitalCandidate,
    *,
    vault_id: PaperVaultId,
    timeframe: str,
    as_of_ms: int,
    required_probability_scope_identity: str,
    expected_gain_fraction: Decimal,
    expected_loss_fraction: Decimal,
    current_drawdown_fraction: Decimal,
    volatility_fraction: Decimal,
    liquidity_quality_0_1: Decimal,
    max_abs_correlation_0_1: Decimal,
    transaction_cost_fraction: Decimal,
    risk_evidence_identities: tuple[str, ...],
) -> PositionSizingContext:
    if assessment.epoch_identity != EPOCH_2_SPEC.epoch_identity:
        raise ValueError("position sizing requires accepted Epoch 2 assessment")
    if assessment.candidate_identity != candidate.candidate_identity:
        raise ValueError("position-sizing assessment/candidate lineage mismatch")
    if as_of_ms < max(candidate.as_of_ms, assessment.assessed_at_ms):
        raise ValueError("position-sizing context cannot predate source evidence")
    vault = _vault(assessment, vault_id)
    if vault.candidate_identity != candidate.candidate_identity:
        raise ValueError("position-sizing vault candidate lineage mismatch")
    _require_sha256(
        required_probability_scope_identity,
        "position-sizing required probability scope",
    )
    _require_identity_tuple(
        tuple(sorted(set(risk_evidence_identities))),
        "position-sizing risk evidence",
    )
    if not risk_evidence_identities:
        raise ValueError("position-sizing requires risk evidence identities")
    source_ids = tuple(
        sorted(
            set(candidate.source_evidence_identities)
            | set(risk_evidence_identities)
            | {assessment.assessment_identity}
        )
    )
    payload = {
        "allocation_assessment_identity": assessment.assessment_identity,
        "as_of_ms": as_of_ms,
        "asset": candidate.asset,
        "candidate_identity": candidate.candidate_identity,
        "current_drawdown_fraction": current_drawdown_fraction,
        "engine_version": POSITION_SIZING_ENGINE_VERSION,
        "expected_gain_fraction": expected_gain_fraction,
        "expected_loss_fraction": expected_loss_fraction,
        "liquidity_quality_0_1": liquidity_quality_0_1,
        "max_abs_correlation_0_1": max_abs_correlation_0_1,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "required_probability_scope_identity": required_probability_scope_identity,
        "schema_version": POSITION_SIZING_SCHEMA_VERSION,
        "semantic": POSITION_SIZING_SEMANTIC,
        "source_evidence_identities": source_ids,
        "timeframe": timeframe,
        "transaction_cost_fraction": transaction_cost_fraction,
        "vault_budget_usdt": vault.starting_budget_usdt,
        "vault_id": vault_id,
        "volatility_fraction": volatility_fraction,
    }
    return PositionSizingContext(
        context_identity=canonical_sha256(payload),
        schema_version=POSITION_SIZING_SCHEMA_VERSION,
        engine_version=POSITION_SIZING_ENGINE_VERSION,
        allocation_assessment_identity=assessment.assessment_identity,
        candidate_identity=candidate.candidate_identity,
        vault_id=vault_id,
        vault_budget_usdt=vault.starting_budget_usdt,
        asset=candidate.asset,
        timeframe=timeframe,
        as_of_ms=as_of_ms,
        required_probability_scope_identity=required_probability_scope_identity,
        expected_gain_fraction=expected_gain_fraction,
        expected_loss_fraction=expected_loss_fraction,
        current_drawdown_fraction=current_drawdown_fraction,
        volatility_fraction=volatility_fraction,
        liquidity_quality_0_1=liquidity_quality_0_1,
        max_abs_correlation_0_1=max_abs_correlation_0_1,
        transaction_cost_fraction=transaction_cost_fraction,
        source_evidence_identities=source_ids,
    )


def compare_position_sizing_methods(
    policy: PositionSizingPolicy,
    context: PositionSizingContext,
    assessment: SmartCapitalAllocationAssessment,
    *,
    calibrated_probability: CalibratedProbabilityEvidence | None = None,
) -> PositionSizingComparison:
    if context.allocation_assessment_identity != assessment.assessment_identity:
        raise ValueError("position-sizing context/assessment identity mismatch")
    vault = _vault(assessment, context.vault_id)
    if vault.starting_budget_usdt != context.vault_budget_usdt:
        raise ValueError("position-sizing vault budget lineage mismatch")
    if vault.candidate_identity != context.candidate_identity:
        raise ValueError("position-sizing vault candidate lineage mismatch")

    probability = calibrated_probability
    if probability is not None:
        if probability.probability_status is not R19ProbabilityStatus.CALIBRATED:
            raise ValueError("position-sizing Kelly input must be R19 CALIBRATED")
        if probability.scope_identity != context.required_probability_scope_identity:
            raise ValueError("position-sizing probability scope mismatch")
        if probability.issued_at_ms > context.as_of_ms:
            raise ValueError("position-sizing probability cannot come from the future")
        if probability.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")

    vault_reasons: tuple[str, ...] = ()
    if (
        vault.eligibility_state
        is not VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE
        or not vault.sizing_required_before_any_trade
    ):
        vault_reasons = tuple(
            sorted(
                {
                    "vault_not_eligible_for_sizing",
                    *vault.reason_codes,
                }
            )
        )

    risk_reasons = _risk_gate_reasons(policy, context)
    expected_edge = (
        None
        if probability is None
        else _expected_net_edge(context, probability.probability_0_1)
    )
    if expected_edge is not None and expected_edge <= Decimal(0):
        risk_reasons = tuple(
            sorted({*risk_reasons, "calibrated_expected_edge_not_positive"})
        )

    scenarios = []
    for method in sorted(SizingMethod, key=lambda item: item.value):
        if vault_reasons:
            scenarios.append(
                _blocked_scenario(
                    policy,
                    context,
                    method=method,
                    status=SizingScenarioStatus.BLOCKED_VAULT,
                    reasons=vault_reasons,
                    probability=probability,
                    expected_edge=expected_edge,
                )
            )
            continue
        if risk_reasons:
            scenarios.append(
                _blocked_scenario(
                    policy,
                    context,
                    method=method,
                    status=SizingScenarioStatus.BLOCKED_RISK_GATE,
                    reasons=risk_reasons,
                    probability=probability,
                    expected_edge=expected_edge,
                )
            )
            continue
        if method is not SizingMethod.FIXED_FRACTIONAL and probability is None:
            scenarios.append(
                _blocked_scenario(
                    policy,
                    context,
                    method=method,
                    status=(
                        SizingScenarioStatus.BLOCKED_NO_CALIBRATED_PROBABILITY
                    ),
                    reasons=("r19_calibrated_probability_required",),
                    probability=None,
                    expected_edge=None,
                )
            )
            continue
        scenarios.append(
            _available_scenario(
                policy,
                context,
                method=method,
                probability=probability,
                expected_edge=expected_edge,
            )
        )

    ordered = tuple(scenarios)
    status = (
        SizingComparisonStatus.EVALUATED
        if any(
            item.status is SizingScenarioStatus.AVAILABLE_RESEARCH_SCENARIO
            for item in ordered
        )
        else SizingComparisonStatus.HOLD_CASH
    )
    payload = {
        "automatic_method_selection": False,
        "automatic_promotion": False,
        "context_identity": context.context_identity,
        "engine_version": POSITION_SIZING_ENGINE_VERSION,
        "ledger_write_authority": False,
        "policy_identity": policy.policy_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "scenarios": ordered,
        "schema_version": POSITION_SIZING_SCHEMA_VERSION,
        "selected_method": None,
        "status": status,
    }
    return PositionSizingComparison(
        comparison_identity=canonical_sha256(payload),
        engine_version=POSITION_SIZING_ENGINE_VERSION,
        schema_version=POSITION_SIZING_SCHEMA_VERSION,
        context_identity=context.context_identity,
        policy_identity=policy.policy_identity,
        status=status,
        scenarios=ordered,
    )


def _available_scenario(
    policy: PositionSizingPolicy,
    context: PositionSizingContext,
    *,
    method: SizingMethod,
    probability: CalibratedProbabilityEvidence | None,
    expected_edge: Decimal | None,
) -> PositionSizingScenario:
    loss_with_cost = context.expected_loss_fraction + context.transaction_cost_fraction
    max_by_risk = policy.max_risk_fraction / loss_with_cost

    if method is SizingMethod.FIXED_FRACTIONAL:
        raw_notional_fraction = (
            policy.fixed_fractional_risk_fraction / loss_with_cost
        )
    else:
        assert probability is not None
        net_win = context.expected_gain_fraction - context.transaction_cost_fraction
        loss = loss_with_cost
        edge = _expected_net_edge(context, probability.probability_0_1)
        raw_full_kelly = edge / (net_win * loss)
        multiplier = {
            SizingMethod.FULL_KELLY: Decimal(1),
            SizingMethod.HALF_KELLY: Decimal("0.5"),
            SizingMethod.QUARTER_KELLY: Decimal("0.25"),
        }[method]
        raw_notional_fraction = raw_full_kelly * multiplier

    bounded_notional_fraction = min(
        raw_notional_fraction,
        max_by_risk,
        policy.max_notional_fraction,
        Decimal(1),
    )
    bounded_notional_fraction = max(Decimal(0), bounded_notional_fraction)
    implied_risk_fraction = bounded_notional_fraction * loss_with_cost
    risk_budget_usdt = context.vault_budget_usdt * implied_risk_fraction
    notional_usdt = context.vault_budget_usdt * bounded_notional_fraction
    scenario = PositionSizingScenario(
        scenario_identity="0" * 64,
        engine_version=POSITION_SIZING_ENGINE_VERSION,
        schema_version=POSITION_SIZING_SCHEMA_VERSION,
        method=method,
        status=SizingScenarioStatus.AVAILABLE_RESEARCH_SCENARIO,
        block_reasons=(),
        context_identity=context.context_identity,
        policy_identity=policy.policy_identity,
        vault_id=context.vault_id,
        vault_budget_usdt=context.vault_budget_usdt,
        calibrated_probability_authorization_identity=(
            None if probability is None else probability.authorization_identity
        ),
        calibration_evidence_identity=(
            None if probability is None else probability.calibration_evidence_identity
        ),
        probability_0_1=(
            None if probability is None else probability.probability_0_1
        ),
        expected_edge_fraction=expected_edge,
        raw_notional_fraction=raw_notional_fraction,
        bounded_notional_fraction=bounded_notional_fraction,
        implied_risk_fraction=implied_risk_fraction,
        risk_budget_usdt=risk_budget_usdt,
        notional_usdt=notional_usdt,
    )
    return _with_scenario_identity(scenario)


def _blocked_scenario(
    policy: PositionSizingPolicy,
    context: PositionSizingContext,
    *,
    method: SizingMethod,
    status: SizingScenarioStatus,
    reasons: tuple[str, ...],
    probability: CalibratedProbabilityEvidence | None,
    expected_edge: Decimal | None,
) -> PositionSizingScenario:
    scenario = PositionSizingScenario(
        scenario_identity="0" * 64,
        engine_version=POSITION_SIZING_ENGINE_VERSION,
        schema_version=POSITION_SIZING_SCHEMA_VERSION,
        method=method,
        status=status,
        block_reasons=tuple(sorted(set(reasons))),
        context_identity=context.context_identity,
        policy_identity=policy.policy_identity,
        vault_id=context.vault_id,
        vault_budget_usdt=context.vault_budget_usdt,
        calibrated_probability_authorization_identity=(
            None if probability is None else probability.authorization_identity
        ),
        calibration_evidence_identity=(
            None if probability is None else probability.calibration_evidence_identity
        ),
        probability_0_1=(
            None if probability is None else probability.probability_0_1
        ),
        expected_edge_fraction=expected_edge,
        raw_notional_fraction=None,
        bounded_notional_fraction=None,
        implied_risk_fraction=None,
        risk_budget_usdt=None,
        notional_usdt=None,
    )
    return _with_scenario_identity(scenario)


def _with_scenario_identity(
    scenario: PositionSizingScenario,
) -> PositionSizingScenario:
    return PositionSizingScenario(
        scenario_identity=canonical_sha256(_scenario_payload(scenario)),
        engine_version=scenario.engine_version,
        schema_version=scenario.schema_version,
        method=scenario.method,
        status=scenario.status,
        block_reasons=scenario.block_reasons,
        context_identity=scenario.context_identity,
        policy_identity=scenario.policy_identity,
        vault_id=scenario.vault_id,
        vault_budget_usdt=scenario.vault_budget_usdt,
        calibrated_probability_authorization_identity=(
            scenario.calibrated_probability_authorization_identity
        ),
        calibration_evidence_identity=scenario.calibration_evidence_identity,
        probability_0_1=scenario.probability_0_1,
        expected_edge_fraction=scenario.expected_edge_fraction,
        raw_notional_fraction=scenario.raw_notional_fraction,
        bounded_notional_fraction=scenario.bounded_notional_fraction,
        implied_risk_fraction=scenario.implied_risk_fraction,
        risk_budget_usdt=scenario.risk_budget_usdt,
        notional_usdt=scenario.notional_usdt,
    )


def _risk_gate_reasons(
    policy: PositionSizingPolicy,
    context: PositionSizingContext,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    if context.current_drawdown_fraction > policy.max_drawdown_fraction:
        reasons.add("drawdown_above_policy_limit")
    if context.volatility_fraction > policy.max_volatility_fraction:
        reasons.add("volatility_above_policy_limit")
    if context.liquidity_quality_0_1 < policy.minimum_liquidity_quality_0_1:
        reasons.add("liquidity_quality_below_policy_minimum")
    if context.max_abs_correlation_0_1 > policy.max_abs_correlation_0_1:
        reasons.add("correlation_above_policy_limit")
    if context.transaction_cost_fraction > policy.max_transaction_cost_fraction:
        reasons.add("transaction_cost_above_policy_limit")
    if context.expected_gain_fraction <= context.transaction_cost_fraction:
        reasons.add("expected_gain_not_above_transaction_cost")
    return tuple(sorted(reasons))


def _expected_net_edge(
    context: PositionSizingContext,
    probability_0_1: Decimal,
) -> Decimal:
    _require_unit_interval(probability_0_1, "position-sizing edge probability")
    net_win = context.expected_gain_fraction - context.transaction_cost_fraction
    loss_with_cost = context.expected_loss_fraction + context.transaction_cost_fraction
    return (
        probability_0_1 * net_win
        - (Decimal(1) - probability_0_1) * loss_with_cost
    )


def _vault(
    assessment: SmartCapitalAllocationAssessment,
    vault_id: PaperVaultId,
):
    matches = tuple(item for item in assessment.vaults if item.vault_id is vault_id)
    if len(matches) != 1:
        raise ValueError("position-sizing assessment must contain exact vault")
    return matches[0]


def _policy_payload(policy: PositionSizingPolicy) -> dict[str, object]:
    return {
        "automatic_method_selection": policy.automatic_method_selection,
        "automatic_promotion": policy.automatic_promotion,
        "engine_version": policy.engine_version,
        "fixed_fractional_risk_fraction": policy.fixed_fractional_risk_fraction,
        "ledger_write_authority": policy.ledger_write_authority,
        "max_abs_correlation_0_1": policy.max_abs_correlation_0_1,
        "max_drawdown_fraction": policy.max_drawdown_fraction,
        "max_notional_fraction": policy.max_notional_fraction,
        "max_risk_fraction": policy.max_risk_fraction,
        "max_transaction_cost_fraction": policy.max_transaction_cost_fraction,
        "max_volatility_fraction": policy.max_volatility_fraction,
        "minimum_liquidity_quality_0_1": policy.minimum_liquidity_quality_0_1,
        "policy_version": policy.policy_version,
        "production_authority": policy.production_authority,
        "real_capital": policy.real_capital,
        "schema_version": policy.schema_version,
        "semantic": policy.semantic,
    }


def _context_payload(context: PositionSizingContext) -> dict[str, object]:
    return {
        "allocation_assessment_identity": context.allocation_assessment_identity,
        "as_of_ms": context.as_of_ms,
        "asset": context.asset,
        "candidate_identity": context.candidate_identity,
        "current_drawdown_fraction": context.current_drawdown_fraction,
        "engine_version": context.engine_version,
        "expected_gain_fraction": context.expected_gain_fraction,
        "expected_loss_fraction": context.expected_loss_fraction,
        "liquidity_quality_0_1": context.liquidity_quality_0_1,
        "max_abs_correlation_0_1": context.max_abs_correlation_0_1,
        "production_authority": context.production_authority,
        "real_capital": context.real_capital,
        "required_probability_scope_identity": (
            context.required_probability_scope_identity
        ),
        "schema_version": context.schema_version,
        "semantic": context.semantic,
        "source_evidence_identities": context.source_evidence_identities,
        "timeframe": context.timeframe,
        "transaction_cost_fraction": context.transaction_cost_fraction,
        "vault_budget_usdt": context.vault_budget_usdt,
        "vault_id": context.vault_id,
        "volatility_fraction": context.volatility_fraction,
    }


def _scenario_payload(scenario: PositionSizingScenario) -> dict[str, object]:
    return {
        "block_reasons": scenario.block_reasons,
        "bounded_notional_fraction": scenario.bounded_notional_fraction,
        "calibrated_probability_authorization_identity": (
            scenario.calibrated_probability_authorization_identity
        ),
        "calibration_evidence_identity": scenario.calibration_evidence_identity,
        "context_identity": scenario.context_identity,
        "engine_version": scenario.engine_version,
        "expected_edge_fraction": scenario.expected_edge_fraction,
        "implied_risk_fraction": scenario.implied_risk_fraction,
        "method": scenario.method,
        "no_leverage": scenario.no_leverage,
        "notional_usdt": scenario.notional_usdt,
        "policy_identity": scenario.policy_identity,
        "probability_0_1": scenario.probability_0_1,
        "production_authority": scenario.production_authority,
        "raw_notional_fraction": scenario.raw_notional_fraction,
        "real_capital": scenario.real_capital,
        "risk_budget_usdt": scenario.risk_budget_usdt,
        "schema_version": scenario.schema_version,
        "shadow_only": scenario.shadow_only,
        "status": scenario.status,
        "vault_budget_usdt": scenario.vault_budget_usdt,
        "vault_id": scenario.vault_id,
    }


def _comparison_payload(
    comparison: PositionSizingComparison,
) -> dict[str, object]:
    return {
        "automatic_method_selection": comparison.automatic_method_selection,
        "automatic_promotion": comparison.automatic_promotion,
        "context_identity": comparison.context_identity,
        "engine_version": comparison.engine_version,
        "ledger_write_authority": comparison.ledger_write_authority,
        "policy_identity": comparison.policy_identity,
        "production_authority": comparison.production_authority,
        "real_capital": comparison.real_capital,
        "scenarios": comparison.scenarios,
        "schema_version": comparison.schema_version,
        "selected_method": comparison.selected_method,
        "status": comparison.status,
    }


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


def _require_asset(value: str) -> None:
    if not value or value != value.upper():
        raise ValueError("position-sizing asset must be non-empty uppercase")


def _require_positive_decimal(value: Decimal, label: str) -> None:
    if (
        value.is_nan()
        or value.is_infinite()
        or value <= Decimal(0)
    ):
        raise ValueError(f"{label} must be positive finite Decimal")


def _require_unit_interval(value: Decimal, label: str) -> None:
    if (
        value.is_nan()
        or value.is_infinite()
        or value < Decimal(0)
        or value > Decimal(1)
    ):
        raise ValueError(f"{label} must be inside [0,1]")
