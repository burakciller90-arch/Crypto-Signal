"""FP5-A immutable live portfolio-risk envelope.

This slice does not replace FP3 sizing or Smart Capital evidence eligibility.
It consumes caller-supplied accepted portfolio/risk truth and computes only
hard portfolio/cluster/cash capacity plus a fixed-fractional risk budget.
REAL_CAPITAL remains 0; Kelly, leverage and forced deployment remain disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import REAL_CAPITAL

FP5_PORTFOLIO_RISK_SCHEMA_VERSION = "paper_portfolio_risk.v2"
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
        normalized = tuple(sorted(set(self.members)))
        if normalized != self.members:
            raise ValueError("cluster members must be sorted unique")
        for asset in self.members:
            _require_asset(asset, "cluster member")
        _require_unit_interval(
            self.max_gross_exposure_fraction,
            "max_gross_exposure_fraction",
        )
        if self.max_gross_exposure_fraction == Decimal(0):
            raise ValueError("cluster gross cap must be positive")


@dataclass(frozen=True, slots=True)
class PortfolioRiskSnapshotV2:
    snapshot_identity: str
    schema_version: str
    policy_version: str
    as_of_ms: int
    cash_usdt: Decimal
    nav_usdt: Decimal
    current_drawdown_fraction: Decimal
    asset_exposures: tuple[AssetGrossExposure, ...]
    clusters: tuple[CorrelationCluster, ...]
    portfolio_max_gross_exposure_fraction: Decimal
    minimum_cash_reserve_fraction: Decimal
    maximum_drawdown_fraction: Decimal
    fixed_fractional_risk_fraction: Decimal
    source_evidence_identities: tuple[str, ...]
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.snapshot_identity, "snapshot_identity")
        if self.schema_version != FP5_PORTFOLIO_RISK_SCHEMA_VERSION:
            raise ValueError("unsupported FP5 portfolio-risk schema")
        if self.policy_version != FP5_PORTFOLIO_RISK_POLICY_VERSION:
            raise ValueError("unsupported FP5 portfolio-risk policy")
        if self.as_of_ms < 0:
            raise ValueError("as_of_ms must be non-negative")
        _require_non_negative_decimal(self.cash_usdt, "cash_usdt")
        _require_positive_decimal(self.nav_usdt, "nav_usdt")
        if self.cash_usdt > self.nav_usdt:
            raise ValueError("cash_usdt cannot exceed nav_usdt")
        for value, label in (
            (self.current_drawdown_fraction, "current_drawdown_fraction"),
            (
                self.portfolio_max_gross_exposure_fraction,
                "portfolio_max_gross_exposure_fraction",
            ),
            (self.minimum_cash_reserve_fraction, "minimum_cash_reserve_fraction"),
            (self.maximum_drawdown_fraction, "maximum_drawdown_fraction"),
            (self.fixed_fractional_risk_fraction, "fixed_fractional_risk_fraction"),
        ):
            _require_unit_interval(value, label)
        if self.portfolio_max_gross_exposure_fraction == Decimal(0):
            raise ValueError("portfolio gross cap must be positive")
        if self.fixed_fractional_risk_fraction == Decimal(0):
            raise ValueError("fixed fractional risk fraction must be positive")
        exposure_assets = tuple(item.asset for item in self.asset_exposures)
        if exposure_assets != tuple(sorted(set(exposure_assets))):
            raise ValueError("asset exposures must be sorted unique by asset")
        cluster_ids = tuple(item.cluster_id for item in self.clusters)
        if cluster_ids != tuple(sorted(set(cluster_ids))):
            raise ValueError("clusters must be sorted unique by cluster_id")
        if not self.source_evidence_identities:
            raise ValueError("portfolio risk snapshot requires source evidence")
        if self.source_evidence_identities != tuple(
            sorted(set(self.source_evidence_identities))
        ):
            raise ValueError("source evidence identities must be sorted unique")
        for identity in self.source_evidence_identities:
            _require_sha256(identity, "source_evidence_identity")
        if self.snapshot_identity != compute_portfolio_risk_snapshot_identity(
            schema_version=self.schema_version,
            policy_version=self.policy_version,
            as_of_ms=self.as_of_ms,
            cash_usdt=self.cash_usdt,
            nav_usdt=self.nav_usdt,
            current_drawdown_fraction=self.current_drawdown_fraction,
            asset_exposures=self.asset_exposures,
            clusters=self.clusters,
            portfolio_max_gross_exposure_fraction=(
                self.portfolio_max_gross_exposure_fraction
            ),
            minimum_cash_reserve_fraction=self.minimum_cash_reserve_fraction,
            maximum_drawdown_fraction=self.maximum_drawdown_fraction,
            fixed_fractional_risk_fraction=self.fixed_fractional_risk_fraction,
            source_evidence_identities=self.source_evidence_identities,
        ):
            raise ValueError("portfolio risk snapshot identity mismatch")

    @property
    def current_gross_exposure_usdt(self) -> Decimal:
        return sum(
            (item.gross_exposure_usdt for item in self.asset_exposures),
            Decimal(0),
        )


@dataclass(frozen=True, slots=True)
class PortfolioAllocationAssessmentV2:
    assessment_identity: str
    policy_version: str
    status: PortfolioRiskStatus
    snapshot_identity: str | None
    candidate_asset: str
    candidate_cluster_id: str | None
    transaction_cost_fraction: Decimal
    stop_invalidation_fraction: Decimal
    event_risk_clear: bool
    liquidity_eligible: bool
    conflict_clear: bool
    current_gross_exposure_usdt: Decimal | None
    current_cluster_exposure_usdt: Decimal | None
    portfolio_headroom_usdt: Decimal | None
    cluster_headroom_usdt: Decimal | None
    cash_headroom_usdt: Decimal | None
    fixed_fractional_risk_budget_usdt: Decimal | None
    risk_limited_notional_usdt: Decimal | None
    max_deployable_notional_usdt: Decimal
    reason_codes: tuple[str, ...]
    kelly_enabled: bool = False
    leverage_allowed: bool = False
    borrowing_allowed: bool = False
    forced_deployment: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.assessment_identity, "assessment_identity")
        if self.policy_version != FP5_PORTFOLIO_RISK_POLICY_VERSION:
            raise ValueError("unsupported FP5 assessment policy")
        _require_asset(self.candidate_asset, "candidate_asset")
        for value, label in (
            (self.transaction_cost_fraction, "transaction_cost_fraction"),
            (self.stop_invalidation_fraction, "stop_invalidation_fraction"),
        ):
            _require_unit_interval(value, label)
        if self.stop_invalidation_fraction == Decimal(0):
            raise ValueError("stop/invalidation fraction must be positive")
        for value, label in (
            (self.event_risk_clear, "event_risk_clear"),
            (self.liquidity_eligible, "liquidity_eligible"),
            (self.conflict_clear, "conflict_clear"),
        ):
            _require_bool(value, label)
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("reason codes must be sorted unique")
        _require_non_negative_decimal(
            self.max_deployable_notional_usdt,
            "max_deployable_notional_usdt",
        )
        if (
            self.kelly_enabled
            or self.leverage_allowed
            or self.borrowing_allowed
            or self.forced_deployment
        ):
            raise ValueError(
                "FP5-A forbids Kelly, leverage, borrowing and forced deployment"
            )
        if self.status is PortfolioRiskStatus.NOT_PROVEN:
            if self.snapshot_identity is not None:
                raise ValueError("NOT_PROVEN assessment cannot bind snapshot")
            if self.candidate_cluster_id is not None:
                raise ValueError("NOT_PROVEN assessment cannot claim cluster")
            if any(
                value is not None
                for value in (
                    self.current_gross_exposure_usdt,
                    self.current_cluster_exposure_usdt,
                    self.portfolio_headroom_usdt,
                    self.cluster_headroom_usdt,
                    self.cash_headroom_usdt,
                    self.fixed_fractional_risk_budget_usdt,
                    self.risk_limited_notional_usdt,
                )
            ):
                raise ValueError("NOT_PROVEN assessment cannot invent capacity")
            if self.max_deployable_notional_usdt != Decimal(0):
                raise ValueError("NOT_PROVEN assessment must expose zero capacity")
        else:
            if self.snapshot_identity is None:
                raise ValueError("proven assessment requires snapshot identity")
            _require_sha256(self.snapshot_identity, "snapshot_identity")
            if self.candidate_cluster_id is None:
                raise ValueError("proven assessment requires candidate cluster")
            for label, value in (
                ("current_gross_exposure_usdt", self.current_gross_exposure_usdt),
                (
                    "current_cluster_exposure_usdt",
                    self.current_cluster_exposure_usdt,
                ),
                ("portfolio_headroom_usdt", self.portfolio_headroom_usdt),
                ("cluster_headroom_usdt", self.cluster_headroom_usdt),
                ("cash_headroom_usdt", self.cash_headroom_usdt),
                (
                    "fixed_fractional_risk_budget_usdt",
                    self.fixed_fractional_risk_budget_usdt,
                ),
                ("risk_limited_notional_usdt", self.risk_limited_notional_usdt),
            ):
                if value is None:
                    raise ValueError(f"proven assessment requires {label}")
                _require_non_negative_decimal(value, label)
            if self.status is PortfolioRiskStatus.HOLD_CASH:
                if self.max_deployable_notional_usdt != Decimal(0):
                    raise ValueError("HOLD_CASH must expose zero deployable capacity")
            elif self.max_deployable_notional_usdt <= Decimal(0):
                raise ValueError("DEPLOYABLE requires positive deployable capacity")
        if self.assessment_identity != compute_portfolio_assessment_identity(
            policy_version=self.policy_version,
            status=self.status,
            snapshot_identity=self.snapshot_identity,
            candidate_asset=self.candidate_asset,
            candidate_cluster_id=self.candidate_cluster_id,
            transaction_cost_fraction=self.transaction_cost_fraction,
            stop_invalidation_fraction=self.stop_invalidation_fraction,
            event_risk_clear=self.event_risk_clear,
            liquidity_eligible=self.liquidity_eligible,
            conflict_clear=self.conflict_clear,
            current_gross_exposure_usdt=self.current_gross_exposure_usdt,
            current_cluster_exposure_usdt=self.current_cluster_exposure_usdt,
            portfolio_headroom_usdt=self.portfolio_headroom_usdt,
            cluster_headroom_usdt=self.cluster_headroom_usdt,
            cash_headroom_usdt=self.cash_headroom_usdt,
            fixed_fractional_risk_budget_usdt=(
                self.fixed_fractional_risk_budget_usdt
            ),
            risk_limited_notional_usdt=self.risk_limited_notional_usdt,
            max_deployable_notional_usdt=self.max_deployable_notional_usdt,
            reason_codes=self.reason_codes,
        ):
            raise ValueError("portfolio assessment identity mismatch")


def build_portfolio_risk_snapshot(
    *,
    as_of_ms: int,
    cash_usdt: Decimal,
    nav_usdt: Decimal,
    current_drawdown_fraction: Decimal,
    asset_exposures: tuple[AssetGrossExposure, ...],
    clusters: tuple[CorrelationCluster, ...],
    portfolio_max_gross_exposure_fraction: Decimal,
    minimum_cash_reserve_fraction: Decimal,
    maximum_drawdown_fraction: Decimal,
    fixed_fractional_risk_fraction: Decimal,
    source_evidence_identities: tuple[str, ...],
) -> PortfolioRiskSnapshotV2:
    sources = tuple(sorted(set(source_evidence_identities)))
    identity = compute_portfolio_risk_snapshot_identity(
        schema_version=FP5_PORTFOLIO_RISK_SCHEMA_VERSION,
        policy_version=FP5_PORTFOLIO_RISK_POLICY_VERSION,
        as_of_ms=as_of_ms,
        cash_usdt=cash_usdt,
        nav_usdt=nav_usdt,
        current_drawdown_fraction=current_drawdown_fraction,
        asset_exposures=asset_exposures,
        clusters=clusters,
        portfolio_max_gross_exposure_fraction=portfolio_max_gross_exposure_fraction,
        minimum_cash_reserve_fraction=minimum_cash_reserve_fraction,
        maximum_drawdown_fraction=maximum_drawdown_fraction,
        fixed_fractional_risk_fraction=fixed_fractional_risk_fraction,
        source_evidence_identities=sources,
    )
    return PortfolioRiskSnapshotV2(
        snapshot_identity=identity,
        schema_version=FP5_PORTFOLIO_RISK_SCHEMA_VERSION,
        policy_version=FP5_PORTFOLIO_RISK_POLICY_VERSION,
        as_of_ms=as_of_ms,
        cash_usdt=cash_usdt,
        nav_usdt=nav_usdt,
        current_drawdown_fraction=current_drawdown_fraction,
        asset_exposures=asset_exposures,
        clusters=clusters,
        portfolio_max_gross_exposure_fraction=portfolio_max_gross_exposure_fraction,
        minimum_cash_reserve_fraction=minimum_cash_reserve_fraction,
        maximum_drawdown_fraction=maximum_drawdown_fraction,
        fixed_fractional_risk_fraction=fixed_fractional_risk_fraction,
        source_evidence_identities=sources,
        real_capital=REAL_CAPITAL,
    )


def assess_portfolio_allocation(
    *,
    snapshot: PortfolioRiskSnapshotV2 | None,
    candidate_asset: str,
    transaction_cost_fraction: Decimal,
    stop_invalidation_fraction: Decimal,
    event_risk_clear: bool,
    liquidity_eligible: bool,
    conflict_clear: bool,
) -> PortfolioAllocationAssessmentV2:
    _require_asset(candidate_asset, "candidate_asset")
    _require_unit_interval(transaction_cost_fraction, "transaction_cost_fraction")
    _require_unit_interval(stop_invalidation_fraction, "stop_invalidation_fraction")
    for value, label in (
        (event_risk_clear, "event_risk_clear"),
        (liquidity_eligible, "liquidity_eligible"),
        (conflict_clear, "conflict_clear"),
    ):
        _require_bool(value, label)
    if stop_invalidation_fraction == Decimal(0):
        raise ValueError("stop/invalidation fraction must be positive")

    if snapshot is None:
        return _build_not_proven_assessment(
            candidate_asset=candidate_asset,
            transaction_cost_fraction=transaction_cost_fraction,
            stop_invalidation_fraction=stop_invalidation_fraction,
            event_risk_clear=event_risk_clear,
            liquidity_eligible=liquidity_eligible,
            conflict_clear=conflict_clear,
            reason_codes=("portfolio_snapshot_not_proven",),
        )

    matching_clusters = tuple(
        cluster for cluster in snapshot.clusters if candidate_asset in cluster.members
    )
    if len(matching_clusters) != 1:
        return _build_not_proven_assessment(
            candidate_asset=candidate_asset,
            transaction_cost_fraction=transaction_cost_fraction,
            stop_invalidation_fraction=stop_invalidation_fraction,
            event_risk_clear=event_risk_clear,
            liquidity_eligible=liquidity_eligible,
            conflict_clear=conflict_clear,
            reason_codes=("candidate_cluster_not_proven",),
        )
    cluster = matching_clusters[0]

    exposure_by_asset = {
        item.asset: item.gross_exposure_usdt for item in snapshot.asset_exposures
    }
    current_gross = snapshot.current_gross_exposure_usdt
    current_cluster = sum(
        (exposure_by_asset.get(member, Decimal(0)) for member in cluster.members),
        Decimal(0),
    )
    portfolio_cap = (
        snapshot.nav_usdt * snapshot.portfolio_max_gross_exposure_fraction
    )
    cluster_cap = snapshot.nav_usdt * cluster.max_gross_exposure_fraction
    minimum_cash = snapshot.nav_usdt * snapshot.minimum_cash_reserve_fraction
    portfolio_headroom = max(portfolio_cap - current_gross, Decimal(0))
    cluster_headroom = max(cluster_cap - current_cluster, Decimal(0))
    cash_headroom = max(snapshot.cash_usdt - minimum_cash, Decimal(0))
    fixed_risk_budget = snapshot.nav_usdt * snapshot.fixed_fractional_risk_fraction
    risk_fraction = stop_invalidation_fraction + transaction_cost_fraction
    if risk_fraction > Decimal(1):
        raise ValueError("combined stop and transaction-cost fraction must be <= 1")
    risk_limited_notional = fixed_risk_budget / risk_fraction

    reasons: set[str] = set()
    if snapshot.current_drawdown_fraction > snapshot.maximum_drawdown_fraction:
        reasons.add("drawdown_gate")
    if not event_risk_clear:
        reasons.add("event_risk_gate")
    if not liquidity_eligible:
        reasons.add("liquidity_gate")
    if not conflict_clear:
        reasons.add("conflict_gate")
    if portfolio_headroom == Decimal(0):
        reasons.add("portfolio_gross_cap")
    if cluster_headroom == Decimal(0):
        reasons.add("cluster_gross_cap")
    if cash_headroom == Decimal(0):
        reasons.add("cash_reserve_gate")

    max_deployable = min(
        portfolio_headroom,
        cluster_headroom,
        cash_headroom,
        risk_limited_notional,
    )
    status = (
        PortfolioRiskStatus.HOLD_CASH
        if reasons or max_deployable == Decimal(0)
        else PortfolioRiskStatus.DEPLOYABLE
    )
    if status is PortfolioRiskStatus.HOLD_CASH:
        max_deployable = Decimal(0)
        if not reasons:
            reasons.add("no_deployable_capacity")

    return _build_assessment(
        status=status,
        snapshot_identity=snapshot.snapshot_identity,
        candidate_asset=candidate_asset,
        candidate_cluster_id=cluster.cluster_id,
        transaction_cost_fraction=transaction_cost_fraction,
        stop_invalidation_fraction=stop_invalidation_fraction,
        event_risk_clear=event_risk_clear,
        liquidity_eligible=liquidity_eligible,
        conflict_clear=conflict_clear,
        current_gross_exposure_usdt=current_gross,
        current_cluster_exposure_usdt=current_cluster,
        portfolio_headroom_usdt=portfolio_headroom,
        cluster_headroom_usdt=cluster_headroom,
        cash_headroom_usdt=cash_headroom,
        fixed_fractional_risk_budget_usdt=fixed_risk_budget,
        risk_limited_notional_usdt=risk_limited_notional,
        max_deployable_notional_usdt=max_deployable,
        reason_codes=tuple(sorted(reasons)),
    )


def compute_portfolio_risk_snapshot_identity(
    *,
    schema_version: str,
    policy_version: str,
    as_of_ms: int,
    cash_usdt: Decimal,
    nav_usdt: Decimal,
    current_drawdown_fraction: Decimal,
    asset_exposures: tuple[AssetGrossExposure, ...],
    clusters: tuple[CorrelationCluster, ...],
    portfolio_max_gross_exposure_fraction: Decimal,
    minimum_cash_reserve_fraction: Decimal,
    maximum_drawdown_fraction: Decimal,
    fixed_fractional_risk_fraction: Decimal,
    source_evidence_identities: tuple[str, ...],
) -> str:
    return canonical_sha256(
        {
            "as_of_ms": as_of_ms,
            "asset_exposures": [
                {
                    "asset": item.asset,
                    "gross_exposure_usdt": item.gross_exposure_usdt,
                }
                for item in asset_exposures
            ],
            "cash_usdt": cash_usdt,
            "clusters": [
                {
                    "cluster_id": cluster.cluster_id,
                    "max_gross_exposure_fraction": (
                        cluster.max_gross_exposure_fraction
                    ),
                    "members": list(cluster.members),
                }
                for cluster in clusters
            ],
            "current_drawdown_fraction": current_drawdown_fraction,
            "fixed_fractional_risk_fraction": fixed_fractional_risk_fraction,
            "maximum_drawdown_fraction": maximum_drawdown_fraction,
            "minimum_cash_reserve_fraction": minimum_cash_reserve_fraction,
            "nav_usdt": nav_usdt,
            "policy_version": policy_version,
            "portfolio_max_gross_exposure_fraction": (
                portfolio_max_gross_exposure_fraction
            ),
            "schema_version": schema_version,
            "source_evidence_identities": list(source_evidence_identities),
        }
    )


def compute_portfolio_assessment_identity(
    *,
    policy_version: str,
    status: PortfolioRiskStatus,
    snapshot_identity: str | None,
    candidate_asset: str,
    candidate_cluster_id: str | None,
    transaction_cost_fraction: Decimal,
    stop_invalidation_fraction: Decimal,
    event_risk_clear: bool,
    liquidity_eligible: bool,
    conflict_clear: bool,
    current_gross_exposure_usdt: Decimal | None,
    current_cluster_exposure_usdt: Decimal | None,
    portfolio_headroom_usdt: Decimal | None,
    cluster_headroom_usdt: Decimal | None,
    cash_headroom_usdt: Decimal | None,
    fixed_fractional_risk_budget_usdt: Decimal | None,
    risk_limited_notional_usdt: Decimal | None,
    max_deployable_notional_usdt: Decimal,
    reason_codes: tuple[str, ...],
) -> str:
    return canonical_sha256(
        {
            "borrowing_allowed": False,
            "candidate_asset": candidate_asset,
            "candidate_cluster_id": candidate_cluster_id,
            "cash_headroom_usdt": cash_headroom_usdt,
            "cluster_headroom_usdt": cluster_headroom_usdt,
            "conflict_clear": conflict_clear,
            "current_cluster_exposure_usdt": current_cluster_exposure_usdt,
            "current_gross_exposure_usdt": current_gross_exposure_usdt,
            "event_risk_clear": event_risk_clear,
            "fixed_fractional_risk_budget_usdt": (
                fixed_fractional_risk_budget_usdt
            ),
            "forced_deployment": False,
            "kelly_enabled": False,
            "leverage_allowed": False,
            "liquidity_eligible": liquidity_eligible,
            "max_deployable_notional_usdt": max_deployable_notional_usdt,
            "policy_version": policy_version,
            "portfolio_headroom_usdt": portfolio_headroom_usdt,
            "reason_codes": list(reason_codes),
            "risk_limited_notional_usdt": risk_limited_notional_usdt,
            "snapshot_identity": snapshot_identity,
            "status": status.value,
            "stop_invalidation_fraction": stop_invalidation_fraction,
            "transaction_cost_fraction": transaction_cost_fraction,
        }
    )


def _build_not_proven_assessment(
    *,
    candidate_asset: str,
    transaction_cost_fraction: Decimal,
    stop_invalidation_fraction: Decimal,
    event_risk_clear: bool,
    liquidity_eligible: bool,
    conflict_clear: bool,
    reason_codes: tuple[str, ...],
) -> PortfolioAllocationAssessmentV2:
    return _build_assessment(
        status=PortfolioRiskStatus.NOT_PROVEN,
        snapshot_identity=None,
        candidate_asset=candidate_asset,
        candidate_cluster_id=None,
        transaction_cost_fraction=transaction_cost_fraction,
        stop_invalidation_fraction=stop_invalidation_fraction,
        event_risk_clear=event_risk_clear,
        liquidity_eligible=liquidity_eligible,
        conflict_clear=conflict_clear,
        current_gross_exposure_usdt=None,
        current_cluster_exposure_usdt=None,
        portfolio_headroom_usdt=None,
        cluster_headroom_usdt=None,
        cash_headroom_usdt=None,
        fixed_fractional_risk_budget_usdt=None,
        risk_limited_notional_usdt=None,
        max_deployable_notional_usdt=Decimal(0),
        reason_codes=reason_codes,
    )


def _build_assessment(
    *,
    status: PortfolioRiskStatus,
    snapshot_identity: str | None,
    candidate_asset: str,
    candidate_cluster_id: str | None,
    transaction_cost_fraction: Decimal,
    stop_invalidation_fraction: Decimal,
    event_risk_clear: bool,
    liquidity_eligible: bool,
    conflict_clear: bool,
    current_gross_exposure_usdt: Decimal | None,
    current_cluster_exposure_usdt: Decimal | None,
    portfolio_headroom_usdt: Decimal | None,
    cluster_headroom_usdt: Decimal | None,
    cash_headroom_usdt: Decimal | None,
    fixed_fractional_risk_budget_usdt: Decimal | None,
    risk_limited_notional_usdt: Decimal | None,
    max_deployable_notional_usdt: Decimal,
    reason_codes: tuple[str, ...],
) -> PortfolioAllocationAssessmentV2:
    identity = compute_portfolio_assessment_identity(
        policy_version=FP5_PORTFOLIO_RISK_POLICY_VERSION,
        status=status,
        snapshot_identity=snapshot_identity,
        candidate_asset=candidate_asset,
        candidate_cluster_id=candidate_cluster_id,
        transaction_cost_fraction=transaction_cost_fraction,
        stop_invalidation_fraction=stop_invalidation_fraction,
        event_risk_clear=event_risk_clear,
        liquidity_eligible=liquidity_eligible,
        conflict_clear=conflict_clear,
        current_gross_exposure_usdt=current_gross_exposure_usdt,
        current_cluster_exposure_usdt=current_cluster_exposure_usdt,
        portfolio_headroom_usdt=portfolio_headroom_usdt,
        cluster_headroom_usdt=cluster_headroom_usdt,
        cash_headroom_usdt=cash_headroom_usdt,
        fixed_fractional_risk_budget_usdt=fixed_fractional_risk_budget_usdt,
        risk_limited_notional_usdt=risk_limited_notional_usdt,
        max_deployable_notional_usdt=max_deployable_notional_usdt,
        reason_codes=reason_codes,
    )
    return PortfolioAllocationAssessmentV2(
        assessment_identity=identity,
        policy_version=FP5_PORTFOLIO_RISK_POLICY_VERSION,
        status=status,
        snapshot_identity=snapshot_identity,
        candidate_asset=candidate_asset,
        candidate_cluster_id=candidate_cluster_id,
        transaction_cost_fraction=transaction_cost_fraction,
        stop_invalidation_fraction=stop_invalidation_fraction,
        event_risk_clear=event_risk_clear,
        liquidity_eligible=liquidity_eligible,
        conflict_clear=conflict_clear,
        current_gross_exposure_usdt=current_gross_exposure_usdt,
        current_cluster_exposure_usdt=current_cluster_exposure_usdt,
        portfolio_headroom_usdt=portfolio_headroom_usdt,
        cluster_headroom_usdt=cluster_headroom_usdt,
        cash_headroom_usdt=cash_headroom_usdt,
        fixed_fractional_risk_budget_usdt=fixed_fractional_risk_budget_usdt,
        risk_limited_notional_usdt=risk_limited_notional_usdt,
        max_deployable_notional_usdt=max_deployable_notional_usdt,
        reason_codes=reason_codes,
        kelly_enabled=False,
        leverage_allowed=False,
        borrowing_allowed=False,
        forced_deployment=False,
        real_capital=REAL_CAPITAL,
    )


def _require_bool(value: object, label: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be bool")


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


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


__all__ = [
    "FP5_PORTFOLIO_RISK_POLICY_VERSION",
    "FP5_PORTFOLIO_RISK_SCHEMA_VERSION",
    "AssetGrossExposure",
    "CorrelationCluster",
    "PortfolioAllocationAssessmentV2",
    "PortfolioRiskSnapshotV2",
    "PortfolioRiskStatus",
    "assess_portfolio_allocation",
    "build_portfolio_risk_snapshot",
    "compute_portfolio_assessment_identity",
    "compute_portfolio_risk_snapshot_identity",
]
