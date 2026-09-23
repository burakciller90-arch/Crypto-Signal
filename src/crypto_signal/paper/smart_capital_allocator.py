from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceMatrixResolution,
    ConfluenceMatrixSnapshot,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epochs import (
    EPOCH_2_SPEC,
    PaperVaultId,
)

SMART_CAPITAL_ALLOCATOR_ENGINE_VERSION = "smart-capital-allocator-v1-slice1/1"
SMART_CAPITAL_ALLOCATOR_SCHEMA_VERSION = "smart-capital-allocator-v1/1"
SMART_CAPITAL_POLICY_VERSION = "smart-capital-policy-v1.1-locked/1"
REAL_CAPITAL = 0


class VaultEligibilityState(StrEnum):
    ELIGIBLE_RESEARCH_ENVELOPE = "eligible_research_envelope"
    HOLD_CASH = "hold_cash"


class VaultMetricsStatus(StrEnum):
    NOT_ACTIVATED = "not_activated"


@dataclass(frozen=True, slots=True)
class TacticalMicrostructureEvidence:
    evidence_identity: str
    asset: str
    timeframe: str
    as_of_ms: int
    liquidity_evidence_identity: str
    order_flow_evidence_identity: str
    market_quality_evidence_identity: str
    cvd_available: bool
    absorption_evidence_available: bool
    liquidity_sweep_evidence_available: bool
    evidence_complete: bool

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "tactical evidence identity")
        for identity, label in (
            (self.liquidity_evidence_identity, "tactical liquidity evidence"),
            (self.order_flow_evidence_identity, "tactical order-flow evidence"),
            (self.market_quality_evidence_identity, "tactical market-quality evidence"),
        ):
            _require_sha256(identity, label)
        _require_asset(self.asset, "tactical asset")
        if self.timeframe not in {"1m", "5m"}:
            raise ValueError("tactical evidence timeframe must be 1m or 5m")
        if self.as_of_ms < 0:
            raise ValueError("tactical evidence as_of_ms must be non-negative")
        if self.evidence_complete and not (
            self.cvd_available
            and self.absorption_evidence_available
            and self.liquidity_sweep_evidence_available
        ):
            raise ValueError(
                "complete tactical evidence requires CVD, absorption and liquidity sweep"
            )
        if self.evidence_identity != canonical_sha256(
            _tactical_evidence_payload(self)
        ):
            raise ValueError("tactical evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class OpportunityRecoveryEvidence:
    evidence_identity: str
    asset: str
    as_of_ms: int
    spread_stabilization_identity: str
    liquidity_recovery_identity: str
    price_discovery_identity: str
    feed_quality_identity: str
    spread_stabilized: bool
    liquidity_recovered: bool
    price_discovery_stable: bool
    feed_quality_healthy: bool

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "recovery evidence identity")
        for identity, label in (
            (self.spread_stabilization_identity, "spread stabilization evidence"),
            (self.liquidity_recovery_identity, "liquidity recovery evidence"),
            (self.price_discovery_identity, "price discovery evidence"),
            (self.feed_quality_identity, "feed quality evidence"),
        ):
            _require_sha256(identity, label)
        _require_asset(self.asset, "recovery asset")
        if self.as_of_ms < 0:
            raise ValueError("recovery evidence as_of_ms must be non-negative")
        if self.evidence_identity != canonical_sha256(_recovery_payload(self)):
            raise ValueError("recovery evidence identity mismatch")

    @property
    def complete_recovery(self) -> bool:
        return (
            self.spread_stabilized
            and self.liquidity_recovered
            and self.price_discovery_stable
            and self.feed_quality_healthy
        )


@dataclass(frozen=True, slots=True)
class SmartCapitalCandidate:
    candidate_identity: str
    asset: str
    as_of_ms: int
    confluence: ConfluenceMatrixSnapshot | None
    event_risk: CircuitBreakerAnalysis
    tactical_microstructure: TacticalMicrostructureEvidence | None
    opportunity_recovery: OpportunityRecoveryEvidence | None
    source_evidence_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.candidate_identity, "capital candidate identity")
        _require_asset(self.asset, "capital candidate asset")
        if self.as_of_ms < 0:
            raise ValueError("capital candidate as_of_ms must be non-negative")
        _require_identity_tuple(
            self.source_evidence_identities,
            "capital candidate source evidence",
        )
        if not _event_asset_matches_market(
            market_asset=self.asset,
            event_asset=self.event_risk.asset,
        ):
            raise ValueError("capital candidate event-risk asset mismatch")
        if self.event_risk.as_of_ms != self.as_of_ms:
            raise ValueError("capital candidate event-risk as_of mismatch")
        if self.confluence is not None:
            if self.confluence.asset != self.asset:
                raise ValueError("capital candidate confluence asset mismatch")
            if self.confluence.as_of_ms != self.as_of_ms:
                raise ValueError("capital candidate confluence as_of mismatch")
        if self.tactical_microstructure is not None:
            if self.tactical_microstructure.asset != self.asset:
                raise ValueError("capital candidate tactical asset mismatch")
            if self.tactical_microstructure.as_of_ms != self.as_of_ms:
                raise ValueError("capital candidate tactical as_of mismatch")
        if self.opportunity_recovery is not None:
            if self.opportunity_recovery.asset != self.asset:
                raise ValueError("capital candidate recovery asset mismatch")
            if self.opportunity_recovery.as_of_ms != self.as_of_ms:
                raise ValueError("capital candidate recovery as_of mismatch")

        expected_sources = {
            self.event_risk.evidence_identity,
        }
        if self.confluence is not None:
            expected_sources.add(self.confluence.snapshot_identity)
        if self.tactical_microstructure is not None:
            expected_sources.add(self.tactical_microstructure.evidence_identity)
        if self.opportunity_recovery is not None:
            expected_sources.add(self.opportunity_recovery.evidence_identity)
        if tuple(sorted(expected_sources)) != self.source_evidence_identities:
            raise ValueError("capital candidate source evidence lineage mismatch")
        if self.candidate_identity != canonical_sha256(_candidate_payload(self)):
            raise ValueError("capital candidate identity mismatch")


@dataclass(frozen=True, slots=True)
class VaultCapitalEnvelope:
    vault_id: PaperVaultId
    starting_budget_usdt: Decimal
    eligibility_state: VaultEligibilityState
    reason_codes: tuple[str, ...]
    candidate_identity: str
    event_risk_identity: str
    confluence_identity: str | None
    tactical_evidence_identity: str | None
    recovery_evidence_identity: str | None
    sizing_required_before_any_trade: bool
    recommended_notional_usdt: None = None
    current_cash_usdt: None = None
    current_nav_usdt: None = None
    current_exposure_usdt: None = None
    current_pnl_usdt: None = None
    current_drawdown_fraction: None = None
    current_cost_usdt: None = None
    current_turnover_fraction: None = None
    metrics_status: VaultMetricsStatus = VaultMetricsStatus.NOT_ACTIVATED
    cross_vault_borrowing_allowed: bool = False
    forced_deployment: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.starting_budget_usdt <= Decimal(0):
            raise ValueError("vault starting budget must be positive")
        _require_sha256(self.candidate_identity, "vault candidate identity")
        _require_sha256(self.event_risk_identity, "vault event-risk identity")
        for identity, label in (
            (self.confluence_identity, "vault confluence identity"),
            (self.tactical_evidence_identity, "vault tactical evidence identity"),
            (self.recovery_evidence_identity, "vault recovery evidence identity"),
        ):
            if identity is not None:
                _require_sha256(identity, label)
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("vault reason codes must be unique and sorted")
        if not self.reason_codes:
            raise ValueError("vault decision requires at least one reason code")
        if (
            self.eligibility_state
            is VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE
            and not self.sizing_required_before_any_trade
        ):
            raise ValueError("eligible vault must still require Phase 11 sizing")
        if self.recommended_notional_usdt is not None:
            raise ValueError("Smart Capital Allocator Slice1 cannot size notional")
        live_metrics = (
            self.current_cash_usdt,
            self.current_nav_usdt,
            self.current_exposure_usdt,
            self.current_pnl_usdt,
            self.current_drawdown_fraction,
            self.current_cost_usdt,
            self.current_turnover_fraction,
        )
        if any(value is not None for value in live_metrics):
            raise ValueError("pre-activation vault envelope cannot invent live metrics")
        if self.metrics_status is not VaultMetricsStatus.NOT_ACTIVATED:
            raise ValueError("Slice1 vault metrics must remain NOT_ACTIVATED")
        if self.cross_vault_borrowing_allowed or self.forced_deployment:
            raise ValueError("cross-vault borrowing and forced deployment are forbidden")
        if self.production_authority:
            raise ValueError("Smart Capital Allocator Slice1 has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")


@dataclass(frozen=True, slots=True)
class SmartCapitalAllocationAssessment:
    assessment_identity: str
    engine_version: str
    schema_version: str
    policy_version: str
    epoch_id: str
    epoch_identity: str
    candidate_identity: str
    assessed_at_ms: int
    vaults: tuple[VaultCapitalEnvelope, ...]
    consolidated_starting_cash_usdt: Decimal
    current_consolidated_nav_usdt: None = None
    current_metrics_status: VaultMetricsStatus = VaultMetricsStatus.NOT_ACTIVATED
    automatic_trade_authority: bool = False
    automatic_sizing_authority: bool = False
    cross_vault_transfer_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.assessment_identity, "capital assessment identity")
        _require_sha256(self.epoch_identity, "capital epoch identity")
        _require_sha256(self.candidate_identity, "capital assessment candidate identity")
        if self.engine_version != SMART_CAPITAL_ALLOCATOR_ENGINE_VERSION:
            raise ValueError("unsupported Smart Capital Allocator engine")
        if self.schema_version != SMART_CAPITAL_ALLOCATOR_SCHEMA_VERSION:
            raise ValueError("unsupported Smart Capital Allocator schema")
        if self.policy_version != SMART_CAPITAL_POLICY_VERSION:
            raise ValueError("unsupported Smart Capital Allocator policy")
        if self.epoch_id != EPOCH_2_SPEC.epoch_id:
            raise ValueError("Smart Capital Allocator must bind Epoch 2")
        if self.epoch_identity != EPOCH_2_SPEC.epoch_identity:
            raise ValueError("Smart Capital Allocator Epoch 2 identity mismatch")
        if self.assessed_at_ms < 0:
            raise ValueError("capital assessment time must be non-negative")
        expected_ids = tuple(sorted(PaperVaultId, key=lambda item: item.value))
        actual_ids = tuple(item.vault_id for item in self.vaults)
        if actual_ids != expected_ids:
            raise ValueError("capital assessment requires canonical three-vault order")
        allocations = {
            item.vault_id: item.starting_cash_usdt
            for item in EPOCH_2_SPEC.vault_allocations
        }
        for vault in self.vaults:
            if vault.starting_budget_usdt != allocations[vault.vault_id]:
                raise ValueError("vault envelope budget does not match Epoch 2 contract")
            if vault.candidate_identity != self.candidate_identity:
                raise ValueError("vault envelope candidate lineage mismatch")
        if self.consolidated_starting_cash_usdt != EPOCH_2_SPEC.starting_cash_usdt:
            raise ValueError("consolidated starting cash must remain 1000 USDT")
        if self.current_consolidated_nav_usdt is not None:
            raise ValueError("Slice1 cannot invent current consolidated NAV")
        if self.current_metrics_status is not VaultMetricsStatus.NOT_ACTIVATED:
            raise ValueError("Slice1 consolidated metrics must remain NOT_ACTIVATED")
        if (
            self.automatic_trade_authority
            or self.automatic_sizing_authority
            or self.cross_vault_transfer_authority
            or self.production_authority
        ):
            raise ValueError("Slice1 has no trade/sizing/transfer/production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.assessment_identity != canonical_sha256(
            _assessment_payload(self)
        ):
            raise ValueError("capital assessment identity mismatch")


def build_tactical_microstructure_evidence(
    *,
    asset: str,
    timeframe: str,
    as_of_ms: int,
    liquidity_evidence_identity: str,
    order_flow_evidence_identity: str,
    market_quality_evidence_identity: str,
    cvd_available: bool,
    absorption_evidence_available: bool,
    liquidity_sweep_evidence_available: bool,
    evidence_complete: bool,
) -> TacticalMicrostructureEvidence:
    payload = {
        "absorption_evidence_available": absorption_evidence_available,
        "as_of_ms": as_of_ms,
        "asset": asset,
        "cvd_available": cvd_available,
        "evidence_complete": evidence_complete,
        "liquidity_evidence_identity": liquidity_evidence_identity,
        "liquidity_sweep_evidence_available": liquidity_sweep_evidence_available,
        "market_quality_evidence_identity": market_quality_evidence_identity,
        "order_flow_evidence_identity": order_flow_evidence_identity,
        "timeframe": timeframe,
    }
    return TacticalMicrostructureEvidence(
        evidence_identity=canonical_sha256(payload),
        asset=asset,
        timeframe=timeframe,
        as_of_ms=as_of_ms,
        liquidity_evidence_identity=liquidity_evidence_identity,
        order_flow_evidence_identity=order_flow_evidence_identity,
        market_quality_evidence_identity=market_quality_evidence_identity,
        cvd_available=cvd_available,
        absorption_evidence_available=absorption_evidence_available,
        liquidity_sweep_evidence_available=liquidity_sweep_evidence_available,
        evidence_complete=evidence_complete,
    )


def build_opportunity_recovery_evidence(
    *,
    asset: str,
    as_of_ms: int,
    spread_stabilization_identity: str,
    liquidity_recovery_identity: str,
    price_discovery_identity: str,
    feed_quality_identity: str,
    spread_stabilized: bool,
    liquidity_recovered: bool,
    price_discovery_stable: bool,
    feed_quality_healthy: bool,
) -> OpportunityRecoveryEvidence:
    payload = {
        "as_of_ms": as_of_ms,
        "asset": asset,
        "feed_quality_healthy": feed_quality_healthy,
        "feed_quality_identity": feed_quality_identity,
        "liquidity_recovered": liquidity_recovered,
        "liquidity_recovery_identity": liquidity_recovery_identity,
        "price_discovery_identity": price_discovery_identity,
        "price_discovery_stable": price_discovery_stable,
        "spread_stabilization_identity": spread_stabilization_identity,
        "spread_stabilized": spread_stabilized,
    }
    return OpportunityRecoveryEvidence(
        evidence_identity=canonical_sha256(payload),
        asset=asset,
        as_of_ms=as_of_ms,
        spread_stabilization_identity=spread_stabilization_identity,
        liquidity_recovery_identity=liquidity_recovery_identity,
        price_discovery_identity=price_discovery_identity,
        feed_quality_identity=feed_quality_identity,
        spread_stabilized=spread_stabilized,
        liquidity_recovered=liquidity_recovered,
        price_discovery_stable=price_discovery_stable,
        feed_quality_healthy=feed_quality_healthy,
    )


def build_smart_capital_candidate(
    *,
    asset: str,
    as_of_ms: int,
    event_risk: CircuitBreakerAnalysis,
    confluence: ConfluenceMatrixSnapshot | None = None,
    tactical_microstructure: TacticalMicrostructureEvidence | None = None,
    opportunity_recovery: OpportunityRecoveryEvidence | None = None,
) -> SmartCapitalCandidate:
    source_ids = {event_risk.evidence_identity}
    if confluence is not None:
        source_ids.add(confluence.snapshot_identity)
    if tactical_microstructure is not None:
        source_ids.add(tactical_microstructure.evidence_identity)
    if opportunity_recovery is not None:
        source_ids.add(opportunity_recovery.evidence_identity)
    ordered = tuple(sorted(source_ids))
    payload = {
        "as_of_ms": as_of_ms,
        "asset": asset,
        "confluence_identity": (
            None if confluence is None else confluence.snapshot_identity
        ),
        "event_risk_identity": event_risk.evidence_identity,
        "opportunity_recovery_identity": (
            None
            if opportunity_recovery is None
            else opportunity_recovery.evidence_identity
        ),
        "source_evidence_identities": ordered,
        "tactical_microstructure_identity": (
            None
            if tactical_microstructure is None
            else tactical_microstructure.evidence_identity
        ),
    }
    return SmartCapitalCandidate(
        candidate_identity=canonical_sha256(payload),
        asset=asset,
        as_of_ms=as_of_ms,
        confluence=confluence,
        event_risk=event_risk,
        tactical_microstructure=tactical_microstructure,
        opportunity_recovery=opportunity_recovery,
        source_evidence_identities=ordered,
    )


def assess_smart_capital_candidate(
    candidate: SmartCapitalCandidate,
    *,
    assessed_at_ms: int,
) -> SmartCapitalAllocationAssessment:
    if assessed_at_ms < candidate.as_of_ms:
        raise ValueError("capital assessment cannot predate candidate evidence")
    budgets = {
        item.vault_id: item.starting_cash_usdt
        for item in EPOCH_2_SPEC.vault_allocations
    }

    core_state, core_reasons = _core_eligibility(candidate)
    tactical_state, tactical_reasons = _tactical_eligibility(candidate)
    reserve_state, reserve_reasons = _reserve_eligibility(candidate)

    confluence_identity = (
        None
        if candidate.confluence is None
        else candidate.confluence.snapshot_identity
    )
    tactical_identity = (
        None
        if candidate.tactical_microstructure is None
        else candidate.tactical_microstructure.evidence_identity
    )
    recovery_identity = (
        None
        if candidate.opportunity_recovery is None
        else candidate.opportunity_recovery.evidence_identity
    )
    vaults = tuple(
        sorted(
            (
                VaultCapitalEnvelope(
                    vault_id=PaperVaultId.CORE,
                    starting_budget_usdt=budgets[PaperVaultId.CORE],
                    eligibility_state=core_state,
                    reason_codes=core_reasons,
                    candidate_identity=candidate.candidate_identity,
                    event_risk_identity=candidate.event_risk.evidence_identity,
                    confluence_identity=confluence_identity,
                    tactical_evidence_identity=tactical_identity,
                    recovery_evidence_identity=recovery_identity,
                    sizing_required_before_any_trade=(
                        core_state
                        is VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE
                    ),
                ),
                VaultCapitalEnvelope(
                    vault_id=PaperVaultId.TACTICAL,
                    starting_budget_usdt=budgets[PaperVaultId.TACTICAL],
                    eligibility_state=tactical_state,
                    reason_codes=tactical_reasons,
                    candidate_identity=candidate.candidate_identity,
                    event_risk_identity=candidate.event_risk.evidence_identity,
                    confluence_identity=confluence_identity,
                    tactical_evidence_identity=tactical_identity,
                    recovery_evidence_identity=recovery_identity,
                    sizing_required_before_any_trade=(
                        tactical_state
                        is VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE
                    ),
                ),
                VaultCapitalEnvelope(
                    vault_id=PaperVaultId.OPPORTUNITY_RESERVE,
                    starting_budget_usdt=budgets[PaperVaultId.OPPORTUNITY_RESERVE],
                    eligibility_state=reserve_state,
                    reason_codes=reserve_reasons,
                    candidate_identity=candidate.candidate_identity,
                    event_risk_identity=candidate.event_risk.evidence_identity,
                    confluence_identity=confluence_identity,
                    tactical_evidence_identity=tactical_identity,
                    recovery_evidence_identity=recovery_identity,
                    sizing_required_before_any_trade=(
                        reserve_state
                        is VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE
                    ),
                ),
            ),
            key=lambda item: item.vault_id.value,
        )
    )
    payload = {
        "assessed_at_ms": assessed_at_ms,
        "automatic_sizing_authority": False,
        "automatic_trade_authority": False,
        "candidate_identity": candidate.candidate_identity,
        "consolidated_starting_cash_usdt": EPOCH_2_SPEC.starting_cash_usdt,
        "cross_vault_transfer_authority": False,
        "current_consolidated_nav_usdt": None,
        "current_metrics_status": VaultMetricsStatus.NOT_ACTIVATED,
        "engine_version": SMART_CAPITAL_ALLOCATOR_ENGINE_VERSION,
        "epoch_id": EPOCH_2_SPEC.epoch_id,
        "epoch_identity": EPOCH_2_SPEC.epoch_identity,
        "policy_version": SMART_CAPITAL_POLICY_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": SMART_CAPITAL_ALLOCATOR_SCHEMA_VERSION,
        "vaults": vaults,
    }
    return SmartCapitalAllocationAssessment(
        assessment_identity=canonical_sha256(payload),
        engine_version=SMART_CAPITAL_ALLOCATOR_ENGINE_VERSION,
        schema_version=SMART_CAPITAL_ALLOCATOR_SCHEMA_VERSION,
        policy_version=SMART_CAPITAL_POLICY_VERSION,
        epoch_id=EPOCH_2_SPEC.epoch_id,
        epoch_identity=EPOCH_2_SPEC.epoch_identity,
        candidate_identity=candidate.candidate_identity,
        assessed_at_ms=assessed_at_ms,
        vaults=vaults,
        consolidated_starting_cash_usdt=EPOCH_2_SPEC.starting_cash_usdt,
    )


def _event_clear(candidate: SmartCapitalCandidate) -> bool:
    return candidate.event_risk.state is CircuitBreakerState.CLEAR


def _core_eligibility(
    candidate: SmartCapitalCandidate,
) -> tuple[VaultEligibilityState, tuple[str, ...]]:
    reasons: set[str] = set()
    if not _event_clear(candidate):
        reasons.add(f"event_risk_not_clear:{candidate.event_risk.state.value}")
    confluence = candidate.confluence
    if confluence is None:
        reasons.add("confluence_unavailable")
    else:
        if confluence.resolution is not ConfluenceMatrixResolution.MEASURED:
            reasons.add(f"confluence_not_measured:{confluence.resolution.value}")
        if confluence.evidence_coverage_0_100 != Decimal(100):
            reasons.add("confluence_not_full_coverage")
        if confluence.opposition_score_0_100 != Decimal(0):
            reasons.add("confluence_has_opposition")
        if confluence.material_conflict_identities:
            reasons.add("confluence_has_material_conflict")
        if confluence.evidence_quality_0_1 is None:
            reasons.add("confluence_quality_unavailable")
        if confluence.freshness_0_1 is None:
            reasons.add("confluence_freshness_unavailable")
    if reasons:
        return VaultEligibilityState.HOLD_CASH, tuple(sorted(reasons))
    return (
        VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE,
        ("core_complete_low_conflict_event_clear",),
    )


def _tactical_eligibility(
    candidate: SmartCapitalCandidate,
) -> tuple[VaultEligibilityState, tuple[str, ...]]:
    reasons: set[str] = set()
    if not _event_clear(candidate):
        reasons.add(f"event_risk_not_clear:{candidate.event_risk.state.value}")
    tactical = candidate.tactical_microstructure
    if tactical is None:
        reasons.add("tactical_microstructure_unavailable")
    else:
        if tactical.timeframe not in {"1m", "5m"}:
            reasons.add("tactical_timeframe_not_short_horizon")
        if not tactical.evidence_complete:
            reasons.add("tactical_evidence_incomplete")
        if not tactical.cvd_available:
            reasons.add("cvd_unavailable")
        if not tactical.absorption_evidence_available:
            reasons.add("absorption_evidence_unavailable")
        if not tactical.liquidity_sweep_evidence_available:
            reasons.add("liquidity_sweep_evidence_unavailable")
    if reasons:
        return VaultEligibilityState.HOLD_CASH, tuple(sorted(reasons))
    return (
        VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE,
        ("tactical_microstructure_complete_event_clear",),
    )


def _reserve_eligibility(
    candidate: SmartCapitalCandidate,
) -> tuple[VaultEligibilityState, tuple[str, ...]]:
    reasons: set[str] = set()
    if not _event_clear(candidate):
        reasons.add(f"event_risk_not_clear:{candidate.event_risk.state.value}")
    recovery = candidate.opportunity_recovery
    if recovery is None:
        reasons.add("recovery_evidence_unavailable")
    else:
        if not recovery.spread_stabilized:
            reasons.add("spread_not_stabilized")
        if not recovery.liquidity_recovered:
            reasons.add("liquidity_not_recovered")
        if not recovery.price_discovery_stable:
            reasons.add("price_discovery_not_stable")
        if not recovery.feed_quality_healthy:
            reasons.add("feed_quality_not_healthy")
    if reasons:
        return VaultEligibilityState.HOLD_CASH, tuple(sorted(reasons))
    return (
        VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE,
        ("recovery_stabilized_event_clear",),
    )


def _tactical_evidence_payload(
    evidence: TacticalMicrostructureEvidence,
) -> dict[str, object]:
    return {
        "absorption_evidence_available": evidence.absorption_evidence_available,
        "as_of_ms": evidence.as_of_ms,
        "asset": evidence.asset,
        "cvd_available": evidence.cvd_available,
        "evidence_complete": evidence.evidence_complete,
        "liquidity_evidence_identity": evidence.liquidity_evidence_identity,
        "liquidity_sweep_evidence_available": (
            evidence.liquidity_sweep_evidence_available
        ),
        "market_quality_evidence_identity": evidence.market_quality_evidence_identity,
        "order_flow_evidence_identity": evidence.order_flow_evidence_identity,
        "timeframe": evidence.timeframe,
    }


def _recovery_payload(
    evidence: OpportunityRecoveryEvidence,
) -> dict[str, object]:
    return {
        "as_of_ms": evidence.as_of_ms,
        "asset": evidence.asset,
        "feed_quality_healthy": evidence.feed_quality_healthy,
        "feed_quality_identity": evidence.feed_quality_identity,
        "liquidity_recovered": evidence.liquidity_recovered,
        "liquidity_recovery_identity": evidence.liquidity_recovery_identity,
        "price_discovery_identity": evidence.price_discovery_identity,
        "price_discovery_stable": evidence.price_discovery_stable,
        "spread_stabilization_identity": evidence.spread_stabilization_identity,
        "spread_stabilized": evidence.spread_stabilized,
    }


def _candidate_payload(candidate: SmartCapitalCandidate) -> dict[str, object]:
    return {
        "as_of_ms": candidate.as_of_ms,
        "asset": candidate.asset,
        "confluence_identity": (
            None
            if candidate.confluence is None
            else candidate.confluence.snapshot_identity
        ),
        "event_risk_identity": candidate.event_risk.evidence_identity,
        "opportunity_recovery_identity": (
            None
            if candidate.opportunity_recovery is None
            else candidate.opportunity_recovery.evidence_identity
        ),
        "source_evidence_identities": candidate.source_evidence_identities,
        "tactical_microstructure_identity": (
            None
            if candidate.tactical_microstructure is None
            else candidate.tactical_microstructure.evidence_identity
        ),
    }


def _vault_payload(vault: VaultCapitalEnvelope) -> dict[str, object]:
    return {
        "candidate_identity": vault.candidate_identity,
        "confluence_identity": vault.confluence_identity,
        "cross_vault_borrowing_allowed": vault.cross_vault_borrowing_allowed,
        "current_cash_usdt": vault.current_cash_usdt,
        "current_cost_usdt": vault.current_cost_usdt,
        "current_drawdown_fraction": vault.current_drawdown_fraction,
        "current_exposure_usdt": vault.current_exposure_usdt,
        "current_nav_usdt": vault.current_nav_usdt,
        "current_pnl_usdt": vault.current_pnl_usdt,
        "current_turnover_fraction": vault.current_turnover_fraction,
        "eligibility_state": vault.eligibility_state,
        "event_risk_identity": vault.event_risk_identity,
        "forced_deployment": vault.forced_deployment,
        "metrics_status": vault.metrics_status,
        "production_authority": vault.production_authority,
        "real_capital": vault.real_capital,
        "reason_codes": vault.reason_codes,
        "recommended_notional_usdt": vault.recommended_notional_usdt,
        "recovery_evidence_identity": vault.recovery_evidence_identity,
        "sizing_required_before_any_trade": vault.sizing_required_before_any_trade,
        "starting_budget_usdt": vault.starting_budget_usdt,
        "tactical_evidence_identity": vault.tactical_evidence_identity,
        "vault_id": vault.vault_id,
    }


def _assessment_payload(
    assessment: SmartCapitalAllocationAssessment,
) -> dict[str, object]:
    return {
        "assessed_at_ms": assessment.assessed_at_ms,
        "automatic_sizing_authority": assessment.automatic_sizing_authority,
        "automatic_trade_authority": assessment.automatic_trade_authority,
        "candidate_identity": assessment.candidate_identity,
        "consolidated_starting_cash_usdt": assessment.consolidated_starting_cash_usdt,
        "cross_vault_transfer_authority": assessment.cross_vault_transfer_authority,
        "current_consolidated_nav_usdt": assessment.current_consolidated_nav_usdt,
        "current_metrics_status": assessment.current_metrics_status,
        "engine_version": assessment.engine_version,
        "epoch_id": assessment.epoch_id,
        "epoch_identity": assessment.epoch_identity,
        "policy_version": assessment.policy_version,
        "production_authority": assessment.production_authority,
        "real_capital": assessment.real_capital,
        "schema_version": assessment.schema_version,
        "vaults": assessment.vaults,
    }


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _event_asset_matches_market(*, market_asset: str, event_asset: str) -> bool:
    """Allow exact market symbol or its locked USDT base asset.

    Event Risk is asset-scoped (for example BTC) while M6/paper capital is
    market-scoped (for example BTCUSDT). This is an explicit compatibility
    rule, not a fuzzy prefix match.
    """
    return event_asset == market_asset or market_asset == f"{event_asset}USDT"


def _require_asset(value: str, label: str) -> None:
    if not value or value != value.upper():
        raise ValueError(f"{label} must be non-empty uppercase")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
