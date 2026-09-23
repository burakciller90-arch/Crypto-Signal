from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import Exchange
from crypto_signal.ledger.serialization import canonical_sha256

MARKET_NEUTRAL_ENGINE_VERSION = "market-neutral-research-v1-slice1/1"
MARKET_NEUTRAL_SCHEMA_VERSION = "market-neutral-research-v1/1"
MARKET_NEUTRAL_SEMANTIC = "shadow_net_edge_after_explicit_costs_not_risk_free"
REAL_CAPITAL = 0
_BPS = Decimal(10_000)


class MarketNeutralFamily(StrEnum):
    CROSS_EXCHANGE_SPREAD = "cross_exchange_spread"
    SPOT_PERPETUAL_BASIS = "spot_perpetual_basis"
    FUNDING_CAPTURE = "funding_capture"
    DELTA_NEUTRAL = "delta_neutral"


class NeutralInstrumentType(StrEnum):
    SPOT = "spot"
    LINEAR_PERPETUAL = "linear_perpetual"


class MarketNeutralStatus(StrEnum):
    ELIGIBLE_SHADOW = "eligible_shadow"
    HOLD_NO_NET_EDGE = "hold_no_net_edge"
    HOLD_RISK_GATE = "hold_risk_gate"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class MarketNeutralLegEvidence:
    evidence_identity: str
    exchange: Exchange
    instrument_type: NeutralInstrumentType
    symbol: str
    market_available_at_ms: int
    observed_at_ms: int
    bid_price: Decimal
    ask_price: Decimal
    round_trip_fee_bps: Decimal
    round_trip_slippage_bps: Decimal
    source_evidence_identity: str

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "market-neutral leg identity")
        _require_sha256(
            self.source_evidence_identity,
            "market-neutral leg source evidence",
        )
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("market-neutral leg symbol must be non-empty uppercase")
        if min(self.market_available_at_ms, self.observed_at_ms) < 0:
            raise ValueError("market-neutral leg timestamps must be non-negative")
        if self.market_available_at_ms > self.observed_at_ms:
            raise ValueError("market-neutral leg cannot be observed before availability")
        for value, label in (
            (self.bid_price, "bid price"),
            (self.ask_price, "ask price"),
        ):
            _require_positive_decimal(value, label)
        if self.bid_price > self.ask_price:
            raise ValueError("market-neutral leg bid cannot exceed ask")
        for value, label in (
            (self.round_trip_fee_bps, "round-trip fee bps"),
            (self.round_trip_slippage_bps, "round-trip slippage bps"),
        ):
            _require_non_negative_decimal(value, label)
        if self.evidence_identity != canonical_sha256(_leg_payload(self)):
            raise ValueError("market-neutral leg identity mismatch")


@dataclass(frozen=True, slots=True)
class MarketNeutralRiskContext:
    evidence_identity: str
    as_of_ms: int
    execution_latency_ms: int
    latency_penalty_bps: Decimal
    expected_funding_benefit_bps: Decimal
    funding_change_stress_bps: Decimal
    transfer_required: bool
    transfer_cost_bps: Decimal
    transfer_delay_ms: int | None
    long_counterparty_risk_0_1: Decimal
    short_counterparty_risk_0_1: Decimal
    hedge_mismatch_fraction: Decimal
    source_evidence_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "market-neutral risk identity")
        if self.as_of_ms < 0 or self.execution_latency_ms < 0:
            raise ValueError("market-neutral risk timestamps/latency must be non-negative")
        for value, label in (
            (self.latency_penalty_bps, "latency penalty bps"),
            (self.funding_change_stress_bps, "funding change stress bps"),
            (self.transfer_cost_bps, "transfer cost bps"),
        ):
            _require_non_negative_decimal(value, label)
        _require_finite_decimal(
            self.expected_funding_benefit_bps,
            "expected funding benefit bps",
        )
        for value, label in (
            (self.long_counterparty_risk_0_1, "long counterparty risk"),
            (self.short_counterparty_risk_0_1, "short counterparty risk"),
            (self.hedge_mismatch_fraction, "hedge mismatch fraction"),
        ):
            _require_unit_interval(value, label)
        if self.transfer_delay_ms is not None and self.transfer_delay_ms < 0:
            raise ValueError("transfer delay must be non-negative")
        if not self.transfer_required and (
            self.transfer_cost_bps != Decimal(0)
            or self.transfer_delay_ms not in {None, 0}
        ):
            raise ValueError("no-transfer context cannot carry transfer cost/delay")
        _require_identity_tuple(
            self.source_evidence_identities,
            "market-neutral risk source evidence",
        )
        if not self.source_evidence_identities:
            raise ValueError("market-neutral risk context requires source evidence")
        if self.evidence_identity != canonical_sha256(_risk_payload(self)):
            raise ValueError("market-neutral risk identity mismatch")


@dataclass(frozen=True, slots=True)
class MarketNeutralResearchPolicy:
    policy_identity: str
    schema_version: str
    engine_version: str
    policy_version: str
    max_leg_age_ms: int
    max_leg_skew_ms: int
    max_execution_latency_ms: int
    max_transfer_delay_ms: int
    max_counterparty_risk_0_1: Decimal
    max_hedge_mismatch_fraction: Decimal
    max_funding_change_stress_bps: Decimal
    minimum_net_edge_bps: Decimal
    semantic: str = MARKET_NEUTRAL_SEMANTIC
    automatic_promotion: bool = False
    canonical_capital_authority: bool = False
    ledger_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "market-neutral policy identity")
        if self.schema_version != MARKET_NEUTRAL_SCHEMA_VERSION:
            raise ValueError("unsupported market-neutral schema")
        if self.engine_version != MARKET_NEUTRAL_ENGINE_VERSION:
            raise ValueError("unsupported market-neutral engine")
        if not self.policy_version.strip():
            raise ValueError("market-neutral policy version must be non-empty")
        if min(
            self.max_leg_age_ms,
            self.max_leg_skew_ms,
            self.max_execution_latency_ms,
            self.max_transfer_delay_ms,
        ) <= 0:
            raise ValueError("market-neutral timing limits must be positive")
        _require_unit_interval(
            self.max_counterparty_risk_0_1,
            "maximum counterparty risk",
        )
        _require_unit_interval(
            self.max_hedge_mismatch_fraction,
            "maximum hedge mismatch",
        )
        _require_non_negative_decimal(
            self.max_funding_change_stress_bps,
            "maximum funding change stress",
        )
        _require_non_negative_decimal(
            self.minimum_net_edge_bps,
            "minimum net edge",
        )
        if self.semantic != MARKET_NEUTRAL_SEMANTIC:
            raise ValueError("market-neutral semantic mismatch")
        if (
            self.automatic_promotion
            or self.canonical_capital_authority
            or self.ledger_write_authority
            or self.production_authority
        ):
            raise ValueError("market-neutral Slice1 has no canonical mutation authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("market-neutral policy identity mismatch")


@dataclass(frozen=True, slots=True)
class MarketNeutralCandidate:
    candidate_identity: str
    schema_version: str
    engine_version: str
    family: MarketNeutralFamily
    asset: str
    as_of_ms: int
    long_leg: MarketNeutralLegEvidence
    short_leg: MarketNeutralLegEvidence
    risk_context: MarketNeutralRiskContext
    source_evidence_identities: tuple[str, ...]
    semantic: str = MARKET_NEUTRAL_SEMANTIC
    shadow_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.candidate_identity, "market-neutral candidate identity")
        if self.schema_version != MARKET_NEUTRAL_SCHEMA_VERSION:
            raise ValueError("unsupported market-neutral candidate schema")
        if self.engine_version != MARKET_NEUTRAL_ENGINE_VERSION:
            raise ValueError("unsupported market-neutral candidate engine")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("market-neutral asset must be non-empty uppercase")
        if self.long_leg.symbol != self.asset or self.short_leg.symbol != self.asset:
            raise ValueError("market-neutral leg symbols must match candidate asset")
        if self.as_of_ms < 0:
            raise ValueError("market-neutral candidate as_of_ms must be non-negative")
        if self.risk_context.as_of_ms != self.as_of_ms:
            raise ValueError("market-neutral risk as_of mismatch")
        if max(self.long_leg.observed_at_ms, self.short_leg.observed_at_ms) > self.as_of_ms:
            raise ValueError("market-neutral candidate contains future leg evidence")
        _validate_family_structure(self)
        expected = tuple(
            sorted(
                {
                    self.long_leg.evidence_identity,
                    self.short_leg.evidence_identity,
                    self.risk_context.evidence_identity,
                }
            )
        )
        if self.source_evidence_identities != expected:
            raise ValueError("market-neutral candidate evidence lineage mismatch")
        if self.semantic != MARKET_NEUTRAL_SEMANTIC:
            raise ValueError("market-neutral candidate semantic mismatch")
        if not self.shadow_only or self.production_authority:
            raise ValueError("market-neutral candidate must remain shadow-only")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.candidate_identity != canonical_sha256(_candidate_payload(self)):
            raise ValueError("market-neutral candidate identity mismatch")


@dataclass(frozen=True, slots=True)
class MarketNeutralAssessment:
    assessment_identity: str
    schema_version: str
    engine_version: str
    policy_identity: str
    candidate_identity: str
    family: MarketNeutralFamily
    status: MarketNeutralStatus
    reason_codes: tuple[str, ...]
    gross_price_edge_bps: Decimal | None
    expected_funding_benefit_bps: Decimal | None
    total_fee_bps: Decimal | None
    total_slippage_bps: Decimal | None
    latency_penalty_bps: Decimal | None
    funding_change_stress_bps: Decimal | None
    transfer_cost_bps: Decimal | None
    net_edge_bps: Decimal | None
    hypothetical_notional_usdt: None = None
    canonical_capital_mutation: bool = False
    automatic_promotion: bool = False
    shadow_only: bool = True
    risk_free_claim: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.assessment_identity, "market-neutral assessment identity"),
            (self.policy_identity, "market-neutral assessment policy"),
            (self.candidate_identity, "market-neutral assessment candidate"),
        ):
            _require_sha256(identity, label)
        if self.schema_version != MARKET_NEUTRAL_SCHEMA_VERSION:
            raise ValueError("unsupported market-neutral assessment schema")
        if self.engine_version != MARKET_NEUTRAL_ENGINE_VERSION:
            raise ValueError("unsupported market-neutral assessment engine")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("market-neutral reason codes must be unique and sorted")
        if not self.reason_codes:
            raise ValueError("market-neutral assessment requires reason codes")

        metrics = (
            self.gross_price_edge_bps,
            self.expected_funding_benefit_bps,
            self.total_fee_bps,
            self.total_slippage_bps,
            self.latency_penalty_bps,
            self.funding_change_stress_bps,
            self.transfer_cost_bps,
            self.net_edge_bps,
        )
        if self.status is MarketNeutralStatus.NOT_EVALUABLE:
            if any(value is not None for value in metrics):
                raise ValueError("not-evaluable market-neutral result cannot expose edge")
        else:
            if any(value is None for value in metrics):
                raise ValueError("evaluated market-neutral result requires edge decomposition")
        if self.status is MarketNeutralStatus.ELIGIBLE_SHADOW:
            assert self.net_edge_bps is not None
            if self.net_edge_bps <= Decimal(0):
                raise ValueError("eligible market-neutral shadow requires positive net edge")
        if self.hypothetical_notional_usdt is not None:
            raise ValueError("Phase12 Slice1 cannot size capital")
        if (
            self.canonical_capital_mutation
            or self.automatic_promotion
            or not self.shadow_only
            or self.risk_free_claim
            or self.production_authority
        ):
            raise ValueError("market-neutral assessment violates shadow-only boundary")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.assessment_identity != canonical_sha256(_assessment_payload(self)):
            raise ValueError("market-neutral assessment identity mismatch")


def build_market_neutral_leg_evidence(
    *,
    exchange: Exchange,
    instrument_type: NeutralInstrumentType,
    symbol: str,
    market_available_at_ms: int,
    observed_at_ms: int,
    bid_price: Decimal,
    ask_price: Decimal,
    round_trip_fee_bps: Decimal,
    round_trip_slippage_bps: Decimal,
    source_evidence_identity: str,
) -> MarketNeutralLegEvidence:
    payload = {
        "ask_price": ask_price,
        "bid_price": bid_price,
        "exchange": exchange,
        "instrument_type": instrument_type,
        "market_available_at_ms": market_available_at_ms,
        "observed_at_ms": observed_at_ms,
        "round_trip_fee_bps": round_trip_fee_bps,
        "round_trip_slippage_bps": round_trip_slippage_bps,
        "source_evidence_identity": source_evidence_identity,
        "symbol": symbol,
    }
    return MarketNeutralLegEvidence(
        evidence_identity=canonical_sha256(payload),
        exchange=exchange,
        instrument_type=instrument_type,
        symbol=symbol,
        market_available_at_ms=market_available_at_ms,
        observed_at_ms=observed_at_ms,
        bid_price=bid_price,
        ask_price=ask_price,
        round_trip_fee_bps=round_trip_fee_bps,
        round_trip_slippage_bps=round_trip_slippage_bps,
        source_evidence_identity=source_evidence_identity,
    )


def build_market_neutral_risk_context(
    *,
    as_of_ms: int,
    execution_latency_ms: int,
    latency_penalty_bps: Decimal,
    expected_funding_benefit_bps: Decimal,
    funding_change_stress_bps: Decimal,
    transfer_required: bool,
    transfer_cost_bps: Decimal,
    transfer_delay_ms: int | None,
    long_counterparty_risk_0_1: Decimal,
    short_counterparty_risk_0_1: Decimal,
    hedge_mismatch_fraction: Decimal,
    source_evidence_identities: tuple[str, ...],
) -> MarketNeutralRiskContext:
    sources = tuple(sorted(set(source_evidence_identities)))
    payload = {
        "as_of_ms": as_of_ms,
        "execution_latency_ms": execution_latency_ms,
        "expected_funding_benefit_bps": expected_funding_benefit_bps,
        "funding_change_stress_bps": funding_change_stress_bps,
        "hedge_mismatch_fraction": hedge_mismatch_fraction,
        "latency_penalty_bps": latency_penalty_bps,
        "long_counterparty_risk_0_1": long_counterparty_risk_0_1,
        "short_counterparty_risk_0_1": short_counterparty_risk_0_1,
        "source_evidence_identities": sources,
        "transfer_cost_bps": transfer_cost_bps,
        "transfer_delay_ms": transfer_delay_ms,
        "transfer_required": transfer_required,
    }
    return MarketNeutralRiskContext(
        evidence_identity=canonical_sha256(payload),
        as_of_ms=as_of_ms,
        execution_latency_ms=execution_latency_ms,
        latency_penalty_bps=latency_penalty_bps,
        expected_funding_benefit_bps=expected_funding_benefit_bps,
        funding_change_stress_bps=funding_change_stress_bps,
        transfer_required=transfer_required,
        transfer_cost_bps=transfer_cost_bps,
        transfer_delay_ms=transfer_delay_ms,
        long_counterparty_risk_0_1=long_counterparty_risk_0_1,
        short_counterparty_risk_0_1=short_counterparty_risk_0_1,
        hedge_mismatch_fraction=hedge_mismatch_fraction,
        source_evidence_identities=sources,
    )


def build_market_neutral_policy(
    *,
    policy_version: str,
    max_leg_age_ms: int,
    max_leg_skew_ms: int,
    max_execution_latency_ms: int,
    max_transfer_delay_ms: int,
    max_counterparty_risk_0_1: Decimal,
    max_hedge_mismatch_fraction: Decimal,
    max_funding_change_stress_bps: Decimal,
    minimum_net_edge_bps: Decimal,
) -> MarketNeutralResearchPolicy:
    payload = {
        "automatic_promotion": False,
        "canonical_capital_authority": False,
        "engine_version": MARKET_NEUTRAL_ENGINE_VERSION,
        "ledger_write_authority": False,
        "max_counterparty_risk_0_1": max_counterparty_risk_0_1,
        "max_execution_latency_ms": max_execution_latency_ms,
        "max_funding_change_stress_bps": max_funding_change_stress_bps,
        "max_hedge_mismatch_fraction": max_hedge_mismatch_fraction,
        "max_leg_age_ms": max_leg_age_ms,
        "max_leg_skew_ms": max_leg_skew_ms,
        "max_transfer_delay_ms": max_transfer_delay_ms,
        "minimum_net_edge_bps": minimum_net_edge_bps,
        "policy_version": policy_version,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": MARKET_NEUTRAL_SCHEMA_VERSION,
        "semantic": MARKET_NEUTRAL_SEMANTIC,
    }
    return MarketNeutralResearchPolicy(
        policy_identity=canonical_sha256(payload),
        schema_version=MARKET_NEUTRAL_SCHEMA_VERSION,
        engine_version=MARKET_NEUTRAL_ENGINE_VERSION,
        policy_version=policy_version,
        max_leg_age_ms=max_leg_age_ms,
        max_leg_skew_ms=max_leg_skew_ms,
        max_execution_latency_ms=max_execution_latency_ms,
        max_transfer_delay_ms=max_transfer_delay_ms,
        max_counterparty_risk_0_1=max_counterparty_risk_0_1,
        max_hedge_mismatch_fraction=max_hedge_mismatch_fraction,
        max_funding_change_stress_bps=max_funding_change_stress_bps,
        minimum_net_edge_bps=minimum_net_edge_bps,
    )


def build_market_neutral_candidate(
    *,
    family: MarketNeutralFamily,
    asset: str,
    as_of_ms: int,
    long_leg: MarketNeutralLegEvidence,
    short_leg: MarketNeutralLegEvidence,
    risk_context: MarketNeutralRiskContext,
) -> MarketNeutralCandidate:
    sources = tuple(
        sorted(
            {
                long_leg.evidence_identity,
                short_leg.evidence_identity,
                risk_context.evidence_identity,
            }
        )
    )
    payload = {
        "as_of_ms": as_of_ms,
        "asset": asset,
        "engine_version": MARKET_NEUTRAL_ENGINE_VERSION,
        "family": family,
        "long_leg": long_leg,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "risk_context": risk_context,
        "schema_version": MARKET_NEUTRAL_SCHEMA_VERSION,
        "semantic": MARKET_NEUTRAL_SEMANTIC,
        "shadow_only": True,
        "short_leg": short_leg,
        "source_evidence_identities": sources,
    }
    return MarketNeutralCandidate(
        candidate_identity=canonical_sha256(payload),
        schema_version=MARKET_NEUTRAL_SCHEMA_VERSION,
        engine_version=MARKET_NEUTRAL_ENGINE_VERSION,
        family=family,
        asset=asset,
        as_of_ms=as_of_ms,
        long_leg=long_leg,
        short_leg=short_leg,
        risk_context=risk_context,
        source_evidence_identities=sources,
    )


def evaluate_market_neutral_candidate(
    policy: MarketNeutralResearchPolicy,
    candidate: MarketNeutralCandidate,
) -> MarketNeutralAssessment:
    not_evaluable = _not_evaluable_reasons(policy, candidate)
    if not_evaluable:
        return _assessment(
            policy,
            candidate,
            status=MarketNeutralStatus.NOT_EVALUABLE,
            reasons=not_evaluable,
            metrics=None,
        )

    gross_price_edge_bps = _gross_price_edge_bps(candidate)
    risk = candidate.risk_context
    fee_bps = (
        candidate.long_leg.round_trip_fee_bps
        + candidate.short_leg.round_trip_fee_bps
    )
    slippage_bps = (
        candidate.long_leg.round_trip_slippage_bps
        + candidate.short_leg.round_trip_slippage_bps
    )
    transfer_cost_bps = (
        risk.transfer_cost_bps if risk.transfer_required else Decimal(0)
    )
    net_edge_bps = (
        gross_price_edge_bps
        + risk.expected_funding_benefit_bps
        - fee_bps
        - slippage_bps
        - risk.latency_penalty_bps
        - risk.funding_change_stress_bps
        - transfer_cost_bps
    )
    metrics = (
        gross_price_edge_bps,
        risk.expected_funding_benefit_bps,
        fee_bps,
        slippage_bps,
        risk.latency_penalty_bps,
        risk.funding_change_stress_bps,
        transfer_cost_bps,
        net_edge_bps,
    )

    risk_reasons = _risk_gate_reasons(policy, candidate)
    if risk_reasons:
        return _assessment(
            policy,
            candidate,
            status=MarketNeutralStatus.HOLD_RISK_GATE,
            reasons=risk_reasons,
            metrics=metrics,
        )
    if net_edge_bps < policy.minimum_net_edge_bps:
        return _assessment(
            policy,
            candidate,
            status=MarketNeutralStatus.HOLD_NO_NET_EDGE,
            reasons=("net_edge_below_policy_minimum",),
            metrics=metrics,
        )
    return _assessment(
        policy,
        candidate,
        status=MarketNeutralStatus.ELIGIBLE_SHADOW,
        reasons=("positive_net_edge_after_explicit_costs_and_risk_gates",),
        metrics=metrics,
    )


def _not_evaluable_reasons(
    policy: MarketNeutralResearchPolicy,
    candidate: MarketNeutralCandidate,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    for role, leg in (("long", candidate.long_leg), ("short", candidate.short_leg)):
        if candidate.as_of_ms - leg.observed_at_ms > policy.max_leg_age_ms:
            reasons.add(f"{role}_leg_stale")
    if abs(
        candidate.long_leg.market_available_at_ms
        - candidate.short_leg.market_available_at_ms
    ) > policy.max_leg_skew_ms:
        reasons.add("leg_market_time_skew_exceeds_policy")
    risk = candidate.risk_context
    if risk.transfer_required and risk.transfer_delay_ms is None:
        reasons.add("transfer_delay_unavailable")
    return tuple(sorted(reasons))


def _risk_gate_reasons(
    policy: MarketNeutralResearchPolicy,
    candidate: MarketNeutralCandidate,
) -> tuple[str, ...]:
    risk = candidate.risk_context
    reasons: set[str] = set()
    if risk.execution_latency_ms > policy.max_execution_latency_ms:
        reasons.add("execution_latency_above_policy_limit")
    if risk.transfer_required:
        assert risk.transfer_delay_ms is not None
        if risk.transfer_delay_ms > policy.max_transfer_delay_ms:
            reasons.add("transfer_delay_above_policy_limit")
    if (
        risk.long_counterparty_risk_0_1 > policy.max_counterparty_risk_0_1
        or risk.short_counterparty_risk_0_1 > policy.max_counterparty_risk_0_1
    ):
        reasons.add("counterparty_risk_above_policy_limit")
    if risk.hedge_mismatch_fraction > policy.max_hedge_mismatch_fraction:
        reasons.add("hedge_mismatch_above_policy_limit")
    if risk.funding_change_stress_bps > policy.max_funding_change_stress_bps:
        reasons.add("funding_change_stress_above_policy_limit")
    return tuple(sorted(reasons))


def _gross_price_edge_bps(candidate: MarketNeutralCandidate) -> Decimal:
    buy = candidate.long_leg.ask_price
    sell = candidate.short_leg.bid_price
    midpoint = (buy + sell) / Decimal(2)
    return (sell - buy) / midpoint * _BPS


def _assessment(
    policy: MarketNeutralResearchPolicy,
    candidate: MarketNeutralCandidate,
    *,
    status: MarketNeutralStatus,
    reasons: tuple[str, ...],
    metrics: tuple[
        Decimal,
        Decimal,
        Decimal,
        Decimal,
        Decimal,
        Decimal,
        Decimal,
        Decimal,
    ]
    | None,
) -> MarketNeutralAssessment:
    if metrics is None:
        (
            gross_price_edge_bps,
            expected_funding_benefit_bps,
            fee_bps,
            slippage_bps,
            latency_penalty_bps,
            funding_change_stress_bps,
            transfer_cost_bps,
            net_edge_bps,
        ) = (None,) * 8
    else:
        (
            gross_price_edge_bps,
            expected_funding_benefit_bps,
            fee_bps,
            slippage_bps,
            latency_penalty_bps,
            funding_change_stress_bps,
            transfer_cost_bps,
            net_edge_bps,
        ) = metrics
    payload = {
        "assessment_identity": None,
        "automatic_promotion": False,
        "candidate_identity": candidate.candidate_identity,
        "canonical_capital_mutation": False,
        "engine_version": MARKET_NEUTRAL_ENGINE_VERSION,
        "expected_funding_benefit_bps": expected_funding_benefit_bps,
        "family": candidate.family,
        "funding_change_stress_bps": funding_change_stress_bps,
        "gross_price_edge_bps": gross_price_edge_bps,
        "hypothetical_notional_usdt": None,
        "latency_penalty_bps": latency_penalty_bps,
        "net_edge_bps": net_edge_bps,
        "policy_identity": policy.policy_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reason_codes": tuple(sorted(set(reasons))),
        "risk_free_claim": False,
        "schema_version": MARKET_NEUTRAL_SCHEMA_VERSION,
        "shadow_only": True,
        "status": status,
        "total_fee_bps": fee_bps,
        "total_slippage_bps": slippage_bps,
        "transfer_cost_bps": transfer_cost_bps,
    }
    identity_payload = dict(payload)
    identity_payload.pop("assessment_identity")
    return MarketNeutralAssessment(
        assessment_identity=canonical_sha256(identity_payload),
        schema_version=MARKET_NEUTRAL_SCHEMA_VERSION,
        engine_version=MARKET_NEUTRAL_ENGINE_VERSION,
        policy_identity=policy.policy_identity,
        candidate_identity=candidate.candidate_identity,
        family=candidate.family,
        status=status,
        reason_codes=tuple(sorted(set(reasons))),
        gross_price_edge_bps=gross_price_edge_bps,
        expected_funding_benefit_bps=expected_funding_benefit_bps,
        total_fee_bps=fee_bps,
        total_slippage_bps=slippage_bps,
        latency_penalty_bps=latency_penalty_bps,
        funding_change_stress_bps=funding_change_stress_bps,
        transfer_cost_bps=transfer_cost_bps,
        net_edge_bps=net_edge_bps,
    )


def _validate_family_structure(candidate: MarketNeutralCandidate) -> None:
    long_type = candidate.long_leg.instrument_type
    short_type = candidate.short_leg.instrument_type
    types = {long_type, short_type}
    if candidate.family is MarketNeutralFamily.CROSS_EXCHANGE_SPREAD:
        if candidate.long_leg.exchange is candidate.short_leg.exchange:
            raise ValueError("cross-exchange spread requires distinct exchanges")
    elif candidate.family in {
        MarketNeutralFamily.SPOT_PERPETUAL_BASIS,
        MarketNeutralFamily.FUNDING_CAPTURE,
    }:
        if types != {
            NeutralInstrumentType.SPOT,
            NeutralInstrumentType.LINEAR_PERPETUAL,
        }:
            raise ValueError("spot/perpetual family requires one spot and one perpetual")
    elif (
        candidate.family is MarketNeutralFamily.DELTA_NEUTRAL
        and NeutralInstrumentType.LINEAR_PERPETUAL not in types
    ):
        raise ValueError("delta-neutral family requires a perpetual hedge leg")


def _leg_payload(leg: MarketNeutralLegEvidence) -> dict[str, object]:
    return {
        "ask_price": leg.ask_price,
        "bid_price": leg.bid_price,
        "exchange": leg.exchange,
        "instrument_type": leg.instrument_type,
        "market_available_at_ms": leg.market_available_at_ms,
        "observed_at_ms": leg.observed_at_ms,
        "round_trip_fee_bps": leg.round_trip_fee_bps,
        "round_trip_slippage_bps": leg.round_trip_slippage_bps,
        "source_evidence_identity": leg.source_evidence_identity,
        "symbol": leg.symbol,
    }


def _risk_payload(risk: MarketNeutralRiskContext) -> dict[str, object]:
    return {
        "as_of_ms": risk.as_of_ms,
        "execution_latency_ms": risk.execution_latency_ms,
        "expected_funding_benefit_bps": risk.expected_funding_benefit_bps,
        "funding_change_stress_bps": risk.funding_change_stress_bps,
        "hedge_mismatch_fraction": risk.hedge_mismatch_fraction,
        "latency_penalty_bps": risk.latency_penalty_bps,
        "long_counterparty_risk_0_1": risk.long_counterparty_risk_0_1,
        "short_counterparty_risk_0_1": risk.short_counterparty_risk_0_1,
        "source_evidence_identities": risk.source_evidence_identities,
        "transfer_cost_bps": risk.transfer_cost_bps,
        "transfer_delay_ms": risk.transfer_delay_ms,
        "transfer_required": risk.transfer_required,
    }


def _policy_payload(policy: MarketNeutralResearchPolicy) -> dict[str, object]:
    return {
        "automatic_promotion": policy.automatic_promotion,
        "canonical_capital_authority": policy.canonical_capital_authority,
        "engine_version": policy.engine_version,
        "ledger_write_authority": policy.ledger_write_authority,
        "max_counterparty_risk_0_1": policy.max_counterparty_risk_0_1,
        "max_execution_latency_ms": policy.max_execution_latency_ms,
        "max_funding_change_stress_bps": policy.max_funding_change_stress_bps,
        "max_hedge_mismatch_fraction": policy.max_hedge_mismatch_fraction,
        "max_leg_age_ms": policy.max_leg_age_ms,
        "max_leg_skew_ms": policy.max_leg_skew_ms,
        "max_transfer_delay_ms": policy.max_transfer_delay_ms,
        "minimum_net_edge_bps": policy.minimum_net_edge_bps,
        "policy_version": policy.policy_version,
        "production_authority": policy.production_authority,
        "real_capital": policy.real_capital,
        "schema_version": policy.schema_version,
        "semantic": policy.semantic,
    }


def _candidate_payload(candidate: MarketNeutralCandidate) -> dict[str, object]:
    return {
        "as_of_ms": candidate.as_of_ms,
        "asset": candidate.asset,
        "engine_version": candidate.engine_version,
        "family": candidate.family,
        "long_leg": candidate.long_leg,
        "production_authority": candidate.production_authority,
        "real_capital": candidate.real_capital,
        "risk_context": candidate.risk_context,
        "schema_version": candidate.schema_version,
        "semantic": candidate.semantic,
        "shadow_only": candidate.shadow_only,
        "short_leg": candidate.short_leg,
        "source_evidence_identities": candidate.source_evidence_identities,
    }


def _assessment_payload(assessment: MarketNeutralAssessment) -> dict[str, object]:
    return {
        "automatic_promotion": assessment.automatic_promotion,
        "candidate_identity": assessment.candidate_identity,
        "canonical_capital_mutation": assessment.canonical_capital_mutation,
        "engine_version": assessment.engine_version,
        "expected_funding_benefit_bps": assessment.expected_funding_benefit_bps,
        "family": assessment.family,
        "funding_change_stress_bps": assessment.funding_change_stress_bps,
        "gross_price_edge_bps": assessment.gross_price_edge_bps,
        "hypothetical_notional_usdt": assessment.hypothetical_notional_usdt,
        "latency_penalty_bps": assessment.latency_penalty_bps,
        "net_edge_bps": assessment.net_edge_bps,
        "policy_identity": assessment.policy_identity,
        "production_authority": assessment.production_authority,
        "real_capital": assessment.real_capital,
        "reason_codes": assessment.reason_codes,
        "risk_free_claim": assessment.risk_free_claim,
        "schema_version": assessment.schema_version,
        "shadow_only": assessment.shadow_only,
        "status": assessment.status,
        "total_fee_bps": assessment.total_fee_bps,
        "total_slippage_bps": assessment.total_slippage_bps,
        "transfer_cost_bps": assessment.transfer_cost_bps,
    }


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


def _require_finite_decimal(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _require_non_negative_decimal(value: Decimal, label: str) -> None:
    _require_finite_decimal(value, label)
    if value < Decimal(0):
        raise ValueError(f"{label} must be non-negative")


def _require_positive_decimal(value: Decimal, label: str) -> None:
    _require_finite_decimal(value, label)
    if value <= Decimal(0):
        raise ValueError(f"{label} must be positive")


def _require_unit_interval(value: Decimal, label: str) -> None:
    _require_finite_decimal(value, label)
    if value < Decimal(0) or value > Decimal(1):
        raise ValueError(f"{label} must be inside [0,1]")
