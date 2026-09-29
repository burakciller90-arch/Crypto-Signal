"""FP5-A immutable portfolio-risk envelope.

This layer extends accepted FP3 fixed-fractional risk inputs with current
portfolio, cash and explicit correlation-cluster hard caps. It reuses the
accepted Position Sizing, Event Risk and M6 Confluence owners instead of
redefining their gates. It is pure/read-only and never mutates R21/R22 or
grants order, leverage, Kelly or production authority. REAL_CAPITAL remains 0.
"""

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
from crypto_signal.paper.autopilot_forward_sizing import FP3SizingRiskInputs
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.position_sizing_intelligence import PositionSizingPolicy

FP5_PORTFOLIO_RISK_SCHEMA_VERSION = "paper_portfolio_risk.v2"
FP5_PORTFOLIO_RISK_ENGINE_VERSION = "paper_portfolio_risk_engine.v2"
FP5_PORTFOLIO_RISK_POLICY_VERSION = "paper_portfolio_risk_policy.v2"


class PortfolioRiskStatus(StrEnum):
    DEPLOYABLE = "deployable"
    HOLD_CASH = "hold_cash"
    NOT_PROVEN = "not_proven"


@dataclass(frozen=True, slots=True)
class AssetGrossExposure:
    asset: str
    gross_exposure_usdt: Decimal

    def __post_init__(self) -> None:
        _require_asset(self.asset, "asset exposure")
        _require_non_negative_decimal(
            self.gross_exposure_usdt,
            "gross_exposure_usdt",
        )


@dataclass(frozen=True, slots=True)
class CorrelationCluster:
    cluster_id: str
    members: tuple[str, ...]
    max_gross_exposure_fraction: Decimal

    def __post_init__(self) -> None:
        if not self.cluster_id.strip():
            raise ValueError("cluster_id must be non-empty")
        if not self.members:
            raise ValueError("correlation cluster requires members")
        if self.members != tuple(sorted(set(self.members))):
            raise ValueError("cluster members must be sorted unique")
        for asset in self.members:
            _require_asset(asset, "cluster member")
        _require_positive_unit_fraction(
            self.max_gross_exposure_fraction,
            "max_gross_exposure_fraction",
        )


@dataclass(frozen=True, slots=True)
class ClusterGrossExposure:
    cluster_id: str
    gross_exposure_usdt: Decimal

    def __post_init__(self) -> None:
        if not self.cluster_id.strip():
            raise ValueError("cluster exposure id must be non-empty")
        _require_non_negative_decimal(
            self.gross_exposure_usdt,
            "cluster gross exposure",
        )


@dataclass(frozen=True, slots=True)
class PortfolioRiskPolicyV2:
    policy_identity: str
    schema_version: str
    engine_version: str
    policy_version: str
    maximum_gross_exposure_fraction_of_nav: Decimal
    minimum_cash_reserve_fraction_of_nav: Decimal
    maximum_new_trade_loss_fraction_of_nav: Decimal
    clusters: tuple[CorrelationCluster, ...]
    kelly_enabled: bool = False
    leverage_allowed: bool = False
    borrowing_allowed: bool = False
    forced_deployment: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "portfolio risk policy identity")
        if self.schema_version != FP5_PORTFOLIO_RISK_SCHEMA_VERSION:
            raise ValueError("unsupported FP5 portfolio-risk schema")
        if self.engine_version != FP5_PORTFOLIO_RISK_ENGINE_VERSION:
            raise ValueError("unsupported FP5 portfolio-risk engine")
        if self.policy_version != FP5_PORTFOLIO_RISK_POLICY_VERSION:
            raise ValueError("unsupported FP5 portfolio-risk policy")
        _require_positive_unit_fraction(
            self.maximum_gross_exposure_fraction_of_nav,
            "maximum gross exposure fraction",
        )
        _require_unit_interval(
            self.minimum_cash_reserve_fraction_of_nav,
            "minimum cash reserve fraction",
        )
        _require_positive_unit_fraction(
            self.maximum_new_trade_loss_fraction_of_nav,
            "maximum new trade loss fraction",
        )
        if not self.clusters:
            raise ValueError("portfolio risk policy requires correlation clusters")
        if self.clusters != tuple(sorted(self.clusters, key=lambda item: item.cluster_id)):
            raise ValueError("correlation clusters must be sorted by cluster_id")
        cluster_ids = tuple(item.cluster_id for item in self.clusters)
        if len(set(cluster_ids)) != len(cluster_ids):
            raise ValueError("correlation cluster ids must be unique")
        seen_assets: set[str] = set()
        for cluster in self.clusters:
            overlap = seen_assets.intersection(cluster.members)
            if overlap:
                raise ValueError("asset cannot belong to multiple correlation clusters")
            seen_assets.update(cluster.members)
        if (
            self.kelly_enabled
            or self.leverage_allowed
            or self.borrowing_allowed
            or self.forced_deployment
            or self.production_authority
        ):
            raise ValueError(
                "FP5-A forbids Kelly/leverage/borrowing/forced deployment/production"
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("portfolio risk policy identity mismatch")


@dataclass(frozen=True, slots=True)
class PortfolioRiskSnapshotV2:
    snapshot_identity: str
    schema_version: str
    policy_identity: str
    source_portfolio_identity: str
    as_of_ms: int
    cash_usdt: Decimal
    nav_usdt: Decimal
    asset_exposures: tuple[AssetGrossExposure, ...]
    cluster_exposures: tuple[ClusterGrossExposure, ...]
    unclassified_assets: tuple[str, ...]
    unclassified_exposure_usdt: Decimal
    current_gross_exposure_usdt: Decimal
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.snapshot_identity, "snapshot_identity")
        _require_sha256(self.policy_identity, "policy_identity")
        _require_sha256(self.source_portfolio_identity, "source_portfolio_identity")
        if self.schema_version != FP5_PORTFOLIO_RISK_SCHEMA_VERSION:
            raise ValueError("unsupported FP5 portfolio-risk schema")
        if self.as_of_ms < 0:
            raise ValueError("as_of_ms must be non-negative")
        _require_non_negative_decimal(self.cash_usdt, "cash_usdt")
        _require_positive_decimal(self.nav_usdt, "nav_usdt")
        if self.cash_usdt > self.nav_usdt:
            raise ValueError("cash_usdt cannot exceed nav_usdt")
        assets = tuple(item.asset for item in self.asset_exposures)
        if assets != tuple(sorted(set(assets))):
            raise ValueError("asset exposures must be sorted unique by asset")
        cluster_ids = tuple(item.cluster_id for item in self.cluster_exposures)
        if cluster_ids != tuple(sorted(set(cluster_ids))):
            raise ValueError("cluster exposures must be sorted unique by cluster_id")
        if self.unclassified_assets != tuple(sorted(set(self.unclassified_assets))):
            raise ValueError("unclassified assets must be sorted unique")
        _require_non_negative_decimal(
            self.unclassified_exposure_usdt,
            "unclassified_exposure_usdt",
        )
        _require_non_negative_decimal(
            self.current_gross_exposure_usdt,
            "current_gross_exposure_usdt",
        )
        gross = sum(
            (item.gross_exposure_usdt for item in self.asset_exposures),
            Decimal(0),
        )
        if gross != self.current_gross_exposure_usdt:
            raise ValueError("asset exposure total mismatch")
        clustered = sum(
            (item.gross_exposure_usdt for item in self.cluster_exposures),
            Decimal(0),
        )
        if clustered + self.unclassified_exposure_usdt != gross:
            raise ValueError("cluster exposure coverage mismatch")
        if self.cash_usdt + gross != self.nav_usdt:
            raise ValueError("long-only cash plus gross exposure must equal NAV")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("portfolio risk snapshot identity mismatch")


@dataclass(frozen=True, slots=True)
class PortfolioAllocationAssessmentV2:
    assessment_identity: str
    schema_version: str
    engine_version: str
    policy_identity: str
    sizing_policy_identity: str
    snapshot_identity: str | None
    source_portfolio_identity: str | None
    risk_input_identity: str
    vault_id: PaperVaultId
    event_risk_identity: str
    confluence_identity: str
    candidate_asset: str
    candidate_cluster_id: str | None
    as_of_ms: int
    status: PortfolioRiskStatus
    reason_codes: tuple[str, ...]
    baseline_fixed_fractional_notional_usdt: Decimal | None
    stop_invalidation_fraction: Decimal
    risk_per_notional_fraction: Decimal
    current_gross_exposure_usdt: Decimal | None
    current_cluster_exposure_usdt: Decimal | None
    portfolio_headroom_usdt: Decimal | None
    cluster_headroom_usdt: Decimal | None
    cash_headroom_usdt: Decimal | None
    risk_limited_notional_usdt: Decimal | None
    max_deployable_notional_usdt: Decimal
    kelly_enabled: bool = False
    leverage_allowed: bool = False
    borrowing_allowed: bool = False
    forced_deployment: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        for identity_value, label in (
            (self.assessment_identity, "assessment_identity"),
            (self.policy_identity, "policy_identity"),
            (self.sizing_policy_identity, "sizing_policy_identity"),
            (self.risk_input_identity, "risk_input_identity"),
            (self.event_risk_identity, "event_risk_identity"),
            (self.confluence_identity, "confluence_identity"),
        ):
            _require_sha256(identity_value, label)
        if self.snapshot_identity is not None:
            _require_sha256(self.snapshot_identity, "snapshot_identity")
        if self.source_portfolio_identity is not None:
            _require_sha256(
                self.source_portfolio_identity,
                "source_portfolio_identity",
            )
        if self.schema_version != FP5_PORTFOLIO_RISK_SCHEMA_VERSION:
            raise ValueError("unsupported FP5 assessment schema")
        if self.engine_version != FP5_PORTFOLIO_RISK_ENGINE_VERSION:
            raise ValueError("unsupported FP5 assessment engine")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("FP5 assessment requires canonical vault id")
        _require_asset(self.candidate_asset, "candidate_asset")
        if self.as_of_ms < 0:
            raise ValueError("as_of_ms must be non-negative")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("reason codes must be sorted unique")
        _require_positive_unit_fraction(
            self.stop_invalidation_fraction,
            "stop_invalidation_fraction",
        )
        _require_positive_decimal(
            self.risk_per_notional_fraction,
            "risk_per_notional_fraction",
        )
        _require_non_negative_decimal(
            self.max_deployable_notional_usdt,
            "max_deployable_notional_usdt",
        )
        for decimal_value, decimal_label in (
            (
                self.baseline_fixed_fractional_notional_usdt,
                "baseline_fixed_fractional_notional_usdt",
            ),
            (self.current_gross_exposure_usdt, "current_gross_exposure_usdt"),
            (
                self.current_cluster_exposure_usdt,
                "current_cluster_exposure_usdt",
            ),
            (self.portfolio_headroom_usdt, "portfolio_headroom_usdt"),
            (self.cluster_headroom_usdt, "cluster_headroom_usdt"),
            (self.cash_headroom_usdt, "cash_headroom_usdt"),
            (self.risk_limited_notional_usdt, "risk_limited_notional_usdt"),
        ):
            if decimal_value is not None:
                _require_non_negative_decimal(decimal_value, decimal_label)
        if self.status is PortfolioRiskStatus.NOT_PROVEN:
            if self.max_deployable_notional_usdt != Decimal(0):
                raise ValueError("NOT_PROVEN must expose zero deployable capacity")
            if not self.reason_codes:
                raise ValueError("NOT_PROVEN requires explicit reasons")
        elif self.status is PortfolioRiskStatus.HOLD_CASH:
            if self.snapshot_identity is None or self.source_portfolio_identity is None:
                raise ValueError("HOLD_CASH requires proven portfolio snapshot")
            if self.max_deployable_notional_usdt != Decimal(0):
                raise ValueError("HOLD_CASH must expose zero deployable capacity")
            if not self.reason_codes:
                raise ValueError("HOLD_CASH requires explicit reasons")
        elif self.status is PortfolioRiskStatus.DEPLOYABLE:
            if self.snapshot_identity is None or self.source_portfolio_identity is None:
                raise ValueError("DEPLOYABLE requires proven portfolio snapshot")
            if self.candidate_cluster_id is None:
                raise ValueError("DEPLOYABLE requires candidate cluster")
            if self.reason_codes:
                raise ValueError("DEPLOYABLE cannot carry hold reasons")
            if self.max_deployable_notional_usdt <= Decimal(0):
                raise ValueError("DEPLOYABLE requires positive capacity")
        else:
            raise ValueError("unsupported portfolio risk status")
        if (
            self.kelly_enabled
            or self.leverage_allowed
            or self.borrowing_allowed
            or self.forced_deployment
            or self.production_authority
        ):
            raise ValueError(
                "FP5-A forbids Kelly/leverage/borrowing/forced deployment/production"
            )
        if self.assessment_identity != canonical_sha256(_assessment_payload(self)):
            raise ValueError("portfolio assessment identity mismatch")


def build_portfolio_risk_policy(
    *,
    maximum_gross_exposure_fraction_of_nav: Decimal,
    minimum_cash_reserve_fraction_of_nav: Decimal,
    maximum_new_trade_loss_fraction_of_nav: Decimal,
    clusters: tuple[CorrelationCluster, ...],
) -> PortfolioRiskPolicyV2:
    ordered_clusters = tuple(sorted(clusters, key=lambda item: item.cluster_id))
    payload = {
        "borrowing_allowed": False,
        "clusters": [_cluster_payload(item) for item in ordered_clusters],
        "engine_version": FP5_PORTFOLIO_RISK_ENGINE_VERSION,
        "forced_deployment": False,
        "kelly_enabled": False,
        "leverage_allowed": False,
        "maximum_gross_exposure_fraction_of_nav": (
            maximum_gross_exposure_fraction_of_nav
        ),
        "maximum_new_trade_loss_fraction_of_nav": (
            maximum_new_trade_loss_fraction_of_nav
        ),
        "minimum_cash_reserve_fraction_of_nav": (
            minimum_cash_reserve_fraction_of_nav
        ),
        "policy_version": FP5_PORTFOLIO_RISK_POLICY_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": FP5_PORTFOLIO_RISK_SCHEMA_VERSION,
    }
    return PortfolioRiskPolicyV2(
        policy_identity=canonical_sha256(payload),
        schema_version=FP5_PORTFOLIO_RISK_SCHEMA_VERSION,
        engine_version=FP5_PORTFOLIO_RISK_ENGINE_VERSION,
        policy_version=FP5_PORTFOLIO_RISK_POLICY_VERSION,
        maximum_gross_exposure_fraction_of_nav=(
            maximum_gross_exposure_fraction_of_nav
        ),
        minimum_cash_reserve_fraction_of_nav=(
            minimum_cash_reserve_fraction_of_nav
        ),
        maximum_new_trade_loss_fraction_of_nav=(
            maximum_new_trade_loss_fraction_of_nav
        ),
        clusters=ordered_clusters,
    )


def build_portfolio_risk_snapshot(
    *,
    policy: PortfolioRiskPolicyV2,
    source_portfolio_identity: str,
    as_of_ms: int,
    cash_usdt: Decimal,
    nav_usdt: Decimal,
    asset_exposures: tuple[AssetGrossExposure, ...],
) -> PortfolioRiskSnapshotV2:
    _require_sha256(source_portfolio_identity, "source_portfolio_identity")
    exposures = tuple(sorted(asset_exposures, key=lambda item: item.asset))
    cluster_by_asset = {
        asset: cluster
        for cluster in policy.clusters
        for asset in cluster.members
    }
    cluster_totals = {
        cluster.cluster_id: Decimal(0)
        for cluster in policy.clusters
    }
    unclassified_assets: list[str] = []
    unclassified_exposure = Decimal(0)
    for exposure in exposures:
        cluster = cluster_by_asset.get(exposure.asset)
        if cluster is None and exposure.gross_exposure_usdt > Decimal(0):
            unclassified_assets.append(exposure.asset)
            unclassified_exposure += exposure.gross_exposure_usdt
        elif cluster is not None:
            cluster_totals[cluster.cluster_id] += exposure.gross_exposure_usdt
    cluster_exposures = tuple(
        ClusterGrossExposure(
            cluster_id=cluster.cluster_id,
            gross_exposure_usdt=cluster_totals[cluster.cluster_id],
        )
        for cluster in policy.clusters
    )
    gross = sum(
        (item.gross_exposure_usdt for item in exposures),
        Decimal(0),
    )
    payload = {
        "as_of_ms": as_of_ms,
        "asset_exposures": [_asset_exposure_payload(item) for item in exposures],
        "cash_usdt": cash_usdt,
        "cluster_exposures": [
            _cluster_exposure_payload(item) for item in cluster_exposures
        ],
        "current_gross_exposure_usdt": gross,
        "nav_usdt": nav_usdt,
        "policy_identity": policy.policy_identity,
        "real_capital": REAL_CAPITAL,
        "schema_version": FP5_PORTFOLIO_RISK_SCHEMA_VERSION,
        "source_portfolio_identity": source_portfolio_identity,
        "unclassified_assets": tuple(sorted(unclassified_assets)),
        "unclassified_exposure_usdt": unclassified_exposure,
    }
    return PortfolioRiskSnapshotV2(
        snapshot_identity=canonical_sha256(payload),
        schema_version=FP5_PORTFOLIO_RISK_SCHEMA_VERSION,
        policy_identity=policy.policy_identity,
        source_portfolio_identity=source_portfolio_identity,
        as_of_ms=as_of_ms,
        cash_usdt=cash_usdt,
        nav_usdt=nav_usdt,
        asset_exposures=exposures,
        cluster_exposures=cluster_exposures,
        unclassified_assets=tuple(sorted(unclassified_assets)),
        unclassified_exposure_usdt=unclassified_exposure,
        current_gross_exposure_usdt=gross,
    )


def assess_portfolio_allocation(
    *,
    policy: PortfolioRiskPolicyV2,
    sizing_policy: PositionSizingPolicy,
    snapshot: PortfolioRiskSnapshotV2 | None,
    risk_inputs: FP3SizingRiskInputs,
    event_context: CircuitBreakerAnalysis,
    confluence: ConfluenceMatrixSnapshot,
    base_asset: str,
    stop_invalidation_fraction: Decimal,
) -> PortfolioAllocationAssessmentV2:
    _require_asset(base_asset, "base_asset")
    _require_positive_unit_fraction(
        stop_invalidation_fraction,
        "stop_invalidation_fraction",
    )
    if event_context.asset != base_asset:
        raise ValueError("Event Risk/base asset mismatch")
    if confluence.asset != risk_inputs.asset:
        raise ValueError("Confluence/risk-input market mismatch")
    if event_context.as_of_ms != risk_inputs.as_of_ms:
        raise ValueError("Event Risk/risk-input as-of mismatch")
    if confluence.as_of_ms != risk_inputs.as_of_ms:
        raise ValueError("Confluence/risk-input as-of mismatch")
    if snapshot is not None:
        if snapshot.policy_identity != policy.policy_identity:
            raise ValueError("portfolio snapshot/policy identity mismatch")
        if snapshot.as_of_ms != risk_inputs.as_of_ms:
            raise ValueError("portfolio snapshot/risk-input as-of mismatch")

    risk_per_notional = stop_invalidation_fraction * (
        Decimal(1) + risk_inputs.transaction_cost_r
    )
    _require_positive_decimal(risk_per_notional, "risk_per_notional_fraction")

    if snapshot is None:
        return _assessment(
            policy=policy,
            sizing_policy=sizing_policy,
            snapshot=None,
            risk_inputs=risk_inputs,
            event_context=event_context,
            confluence=confluence,
            candidate_cluster_id=None,
            status=PortfolioRiskStatus.NOT_PROVEN,
            reasons=("portfolio_snapshot_not_proven",),
            stop_invalidation_fraction=stop_invalidation_fraction,
            risk_per_notional_fraction=risk_per_notional,
            baseline=None,
            current_cluster=None,
            portfolio_headroom=None,
            cluster_headroom=None,
            cash_headroom=None,
            risk_limited=None,
            max_deployable=Decimal(0),
        )

    cluster = next(
        (
            item
            for item in policy.clusters
            if risk_inputs.asset in item.members
        ),
        None,
    )
    reasons: set[str] = set()
    not_proven = False
    if snapshot.unclassified_assets:
        reasons.add("portfolio_cluster_coverage_not_proven")
        not_proven = True
    if cluster is None:
        reasons.add("candidate_cluster_not_proven")
        not_proven = True

    reasons.update(_accepted_risk_gate_reasons(sizing_policy, risk_inputs))
    if event_context.state is not CircuitBreakerState.CLEAR:
        reasons.add("event_risk_gate")
    if confluence.resolution is ConfluenceMatrixResolution.CONFLICT:
        reasons.add("conflict_gate")
    elif confluence.resolution is not ConfluenceMatrixResolution.MEASURED:
        reasons.add("confluence_not_measured")

    baseline = snapshot.nav_usdt * sizing_policy.fixed_fraction_of_vault
    portfolio_cap = (
        snapshot.nav_usdt * policy.maximum_gross_exposure_fraction_of_nav
    )
    portfolio_headroom = max(
        portfolio_cap - snapshot.current_gross_exposure_usdt,
        Decimal(0),
    )
    minimum_cash = (
        snapshot.nav_usdt * policy.minimum_cash_reserve_fraction_of_nav
    )
    cash_headroom = max(snapshot.cash_usdt - minimum_cash, Decimal(0))
    risk_budget = (
        snapshot.nav_usdt * policy.maximum_new_trade_loss_fraction_of_nav
    )
    risk_limited = risk_budget / risk_per_notional

    current_cluster: Decimal | None = None
    cluster_headroom: Decimal | None = None
    if cluster is not None:
        current_cluster = next(
            item.gross_exposure_usdt
            for item in snapshot.cluster_exposures
            if item.cluster_id == cluster.cluster_id
        )
        cluster_cap = (
            snapshot.nav_usdt * cluster.max_gross_exposure_fraction
        )
        cluster_headroom = max(cluster_cap - current_cluster, Decimal(0))

    if not not_proven:
        if portfolio_headroom == Decimal(0):
            reasons.add("portfolio_gross_cap")
        if cluster_headroom == Decimal(0):
            reasons.add("cluster_gross_cap")
        if cash_headroom == Decimal(0):
            reasons.add("cash_reserve_gate")

    ordered_reasons = tuple(sorted(reasons))
    if not_proven:
        status = PortfolioRiskStatus.NOT_PROVEN
        max_deployable = Decimal(0)
    elif ordered_reasons:
        status = PortfolioRiskStatus.HOLD_CASH
        max_deployable = Decimal(0)
    else:
        assert cluster_headroom is not None
        max_deployable = min(
            baseline,
            portfolio_headroom,
            cluster_headroom,
            cash_headroom,
            risk_limited,
        )
        if max_deployable <= Decimal(0):
            status = PortfolioRiskStatus.HOLD_CASH
            ordered_reasons = ("no_deployable_capacity",)
            max_deployable = Decimal(0)
        else:
            status = PortfolioRiskStatus.DEPLOYABLE

    return _assessment(
        policy=policy,
        sizing_policy=sizing_policy,
        snapshot=snapshot,
        risk_inputs=risk_inputs,
        event_context=event_context,
        confluence=confluence,
        candidate_cluster_id=None if cluster is None else cluster.cluster_id,
        status=status,
        reasons=ordered_reasons,
        stop_invalidation_fraction=stop_invalidation_fraction,
        risk_per_notional_fraction=risk_per_notional,
        baseline=baseline,
        current_cluster=current_cluster,
        portfolio_headroom=portfolio_headroom,
        cluster_headroom=cluster_headroom,
        cash_headroom=cash_headroom,
        risk_limited=risk_limited,
        max_deployable=max_deployable,
    )


def _accepted_risk_gate_reasons(
    sizing_policy: PositionSizingPolicy,
    risk_inputs: FP3SizingRiskInputs,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    if (
        risk_inputs.absolute_correlation_0_1
        > sizing_policy.maximum_absolute_correlation
    ):
        reasons.add("correlation_limit_breached")
    if (
        risk_inputs.current_drawdown_fraction
        > sizing_policy.maximum_drawdown_fraction
    ):
        reasons.add("drawdown_limit_breached")
    if risk_inputs.volatility_fraction > sizing_policy.maximum_volatility_fraction:
        reasons.add("volatility_limit_breached")
    if (
        risk_inputs.liquidity_score_0_1
        < sizing_policy.minimum_liquidity_score_0_1
    ):
        reasons.add("liquidity_floor_breached")
    if risk_inputs.transaction_cost_r > sizing_policy.maximum_transaction_cost_r:
        reasons.add("transaction_cost_limit_breached")
    return tuple(sorted(reasons))


def _assessment(
    *,
    policy: PortfolioRiskPolicyV2,
    sizing_policy: PositionSizingPolicy,
    snapshot: PortfolioRiskSnapshotV2 | None,
    risk_inputs: FP3SizingRiskInputs,
    event_context: CircuitBreakerAnalysis,
    confluence: ConfluenceMatrixSnapshot,
    candidate_cluster_id: str | None,
    status: PortfolioRiskStatus,
    reasons: tuple[str, ...],
    stop_invalidation_fraction: Decimal,
    risk_per_notional_fraction: Decimal,
    baseline: Decimal | None,
    current_cluster: Decimal | None,
    portfolio_headroom: Decimal | None,
    cluster_headroom: Decimal | None,
    cash_headroom: Decimal | None,
    risk_limited: Decimal | None,
    max_deployable: Decimal,
) -> PortfolioAllocationAssessmentV2:
    ordered = tuple(sorted(set(reasons)))
    payload = {
        "as_of_ms": risk_inputs.as_of_ms,
        "baseline_fixed_fractional_notional_usdt": baseline,
        "borrowing_allowed": False,
        "candidate_asset": risk_inputs.asset,
        "candidate_cluster_id": candidate_cluster_id,
        "cash_headroom_usdt": cash_headroom,
        "cluster_headroom_usdt": cluster_headroom,
        "confluence_identity": confluence.snapshot_identity,
        "current_cluster_exposure_usdt": current_cluster,
        "current_gross_exposure_usdt": (
            None if snapshot is None else snapshot.current_gross_exposure_usdt
        ),
        "engine_version": FP5_PORTFOLIO_RISK_ENGINE_VERSION,
        "event_risk_identity": event_context.evidence_identity,
        "forced_deployment": False,
        "kelly_enabled": False,
        "leverage_allowed": False,
        "max_deployable_notional_usdt": max_deployable,
        "policy_identity": policy.policy_identity,
        "portfolio_headroom_usdt": portfolio_headroom,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reason_codes": ordered,
        "risk_input_identity": risk_inputs.risk_input_identity,
        "risk_limited_notional_usdt": risk_limited,
        "risk_per_notional_fraction": risk_per_notional_fraction,
        "schema_version": FP5_PORTFOLIO_RISK_SCHEMA_VERSION,
        "sizing_policy_identity": sizing_policy.policy_identity,
        "snapshot_identity": None if snapshot is None else snapshot.snapshot_identity,
        "source_portfolio_identity": (
            None if snapshot is None else snapshot.source_portfolio_identity
        ),
        "status": status.value,
        "stop_invalidation_fraction": stop_invalidation_fraction,
        "vault_id": risk_inputs.vault_id.value,
    }
    return PortfolioAllocationAssessmentV2(
        assessment_identity=canonical_sha256(payload),
        schema_version=FP5_PORTFOLIO_RISK_SCHEMA_VERSION,
        engine_version=FP5_PORTFOLIO_RISK_ENGINE_VERSION,
        policy_identity=policy.policy_identity,
        sizing_policy_identity=sizing_policy.policy_identity,
        snapshot_identity=None if snapshot is None else snapshot.snapshot_identity,
        source_portfolio_identity=(
            None if snapshot is None else snapshot.source_portfolio_identity
        ),
        risk_input_identity=risk_inputs.risk_input_identity,
        vault_id=risk_inputs.vault_id,
        event_risk_identity=event_context.evidence_identity,
        confluence_identity=confluence.snapshot_identity,
        candidate_asset=risk_inputs.asset,
        candidate_cluster_id=candidate_cluster_id,
        as_of_ms=risk_inputs.as_of_ms,
        status=status,
        reason_codes=ordered,
        baseline_fixed_fractional_notional_usdt=baseline,
        stop_invalidation_fraction=stop_invalidation_fraction,
        risk_per_notional_fraction=risk_per_notional_fraction,
        current_gross_exposure_usdt=(
            None if snapshot is None else snapshot.current_gross_exposure_usdt
        ),
        current_cluster_exposure_usdt=current_cluster,
        portfolio_headroom_usdt=portfolio_headroom,
        cluster_headroom_usdt=cluster_headroom,
        cash_headroom_usdt=cash_headroom,
        risk_limited_notional_usdt=risk_limited,
        max_deployable_notional_usdt=max_deployable,
    )


def _policy_payload(policy: PortfolioRiskPolicyV2) -> dict[str, object]:
    return {
        "borrowing_allowed": policy.borrowing_allowed,
        "clusters": [_cluster_payload(item) for item in policy.clusters],
        "engine_version": policy.engine_version,
        "forced_deployment": policy.forced_deployment,
        "kelly_enabled": policy.kelly_enabled,
        "leverage_allowed": policy.leverage_allowed,
        "maximum_gross_exposure_fraction_of_nav": (
            policy.maximum_gross_exposure_fraction_of_nav
        ),
        "maximum_new_trade_loss_fraction_of_nav": (
            policy.maximum_new_trade_loss_fraction_of_nav
        ),
        "minimum_cash_reserve_fraction_of_nav": (
            policy.minimum_cash_reserve_fraction_of_nav
        ),
        "policy_version": policy.policy_version,
        "production_authority": policy.production_authority,
        "real_capital": policy.real_capital,
        "schema_version": policy.schema_version,
    }


def _snapshot_payload(snapshot: PortfolioRiskSnapshotV2) -> dict[str, object]:
    return {
        "as_of_ms": snapshot.as_of_ms,
        "asset_exposures": [
            _asset_exposure_payload(item) for item in snapshot.asset_exposures
        ],
        "cash_usdt": snapshot.cash_usdt,
        "cluster_exposures": [
            _cluster_exposure_payload(item) for item in snapshot.cluster_exposures
        ],
        "current_gross_exposure_usdt": snapshot.current_gross_exposure_usdt,
        "nav_usdt": snapshot.nav_usdt,
        "policy_identity": snapshot.policy_identity,
        "real_capital": snapshot.real_capital,
        "schema_version": snapshot.schema_version,
        "source_portfolio_identity": snapshot.source_portfolio_identity,
        "unclassified_assets": snapshot.unclassified_assets,
        "unclassified_exposure_usdt": snapshot.unclassified_exposure_usdt,
    }


def _assessment_payload(
    assessment: PortfolioAllocationAssessmentV2,
) -> dict[str, object]:
    return {
        "as_of_ms": assessment.as_of_ms,
        "baseline_fixed_fractional_notional_usdt": (
            assessment.baseline_fixed_fractional_notional_usdt
        ),
        "borrowing_allowed": assessment.borrowing_allowed,
        "candidate_asset": assessment.candidate_asset,
        "candidate_cluster_id": assessment.candidate_cluster_id,
        "cash_headroom_usdt": assessment.cash_headroom_usdt,
        "cluster_headroom_usdt": assessment.cluster_headroom_usdt,
        "confluence_identity": assessment.confluence_identity,
        "current_cluster_exposure_usdt": (
            assessment.current_cluster_exposure_usdt
        ),
        "current_gross_exposure_usdt": assessment.current_gross_exposure_usdt,
        "engine_version": assessment.engine_version,
        "event_risk_identity": assessment.event_risk_identity,
        "forced_deployment": assessment.forced_deployment,
        "kelly_enabled": assessment.kelly_enabled,
        "leverage_allowed": assessment.leverage_allowed,
        "max_deployable_notional_usdt": assessment.max_deployable_notional_usdt,
        "policy_identity": assessment.policy_identity,
        "portfolio_headroom_usdt": assessment.portfolio_headroom_usdt,
        "production_authority": assessment.production_authority,
        "real_capital": assessment.real_capital,
        "reason_codes": assessment.reason_codes,
        "risk_input_identity": assessment.risk_input_identity,
        "risk_limited_notional_usdt": assessment.risk_limited_notional_usdt,
        "risk_per_notional_fraction": assessment.risk_per_notional_fraction,
        "schema_version": assessment.schema_version,
        "sizing_policy_identity": assessment.sizing_policy_identity,
        "snapshot_identity": assessment.snapshot_identity,
        "source_portfolio_identity": assessment.source_portfolio_identity,
        "status": assessment.status.value,
        "stop_invalidation_fraction": assessment.stop_invalidation_fraction,
        "vault_id": assessment.vault_id.value,
    }


def _cluster_payload(cluster: CorrelationCluster) -> dict[str, object]:
    return {
        "cluster_id": cluster.cluster_id,
        "max_gross_exposure_fraction": cluster.max_gross_exposure_fraction,
        "members": list(cluster.members),
    }


def _asset_exposure_payload(
    exposure: AssetGrossExposure,
) -> dict[str, object]:
    return {
        "asset": exposure.asset,
        "gross_exposure_usdt": exposure.gross_exposure_usdt,
    }


def _cluster_exposure_payload(
    exposure: ClusterGrossExposure,
) -> dict[str, object]:
    return {
        "cluster_id": exposure.cluster_id,
        "gross_exposure_usdt": exposure.gross_exposure_usdt,
    }


def _require_asset(value: str, label: str) -> None:
    if not value or value != value.upper():
        raise ValueError(f"{label} must be non-empty uppercase")


def _require_positive_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite() or value <= Decimal(0):
        raise ValueError(f"{label} must be finite and positive")


def _require_non_negative_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite() or value < Decimal(0):
        raise ValueError(f"{label} must be finite and non-negative")


def _require_unit_interval(value: Decimal, label: str) -> None:
    _require_non_negative_decimal(value, label)
    if value > Decimal(1):
        raise ValueError(f"{label} must be <= 1")


def _require_positive_unit_fraction(value: Decimal, label: str) -> None:
    _require_positive_decimal(value, label)
    if value > Decimal(1):
        raise ValueError(f"{label} must be <= 1")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


__all__ = [
    "FP5_PORTFOLIO_RISK_ENGINE_VERSION",
    "FP5_PORTFOLIO_RISK_POLICY_VERSION",
    "FP5_PORTFOLIO_RISK_SCHEMA_VERSION",
    "AssetGrossExposure",
    "ClusterGrossExposure",
    "CorrelationCluster",
    "PortfolioAllocationAssessmentV2",
    "PortfolioRiskPolicyV2",
    "PortfolioRiskSnapshotV2",
    "PortfolioRiskStatus",
    "assess_portfolio_allocation",
    "build_portfolio_risk_policy",
    "build_portfolio_risk_snapshot",
]
