from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.outcomes.models import EvidenceClass

WC2_POLICY_SCHEMA_VERSION = "wc2-untouched-forward-policy-v1/1"
WC2_POLICY_ENGINE_VERSION = "wc2-review-readiness-v1/1"
WC2_REQUIRED_ASSETS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
WC2_MIN_TOTAL_DECISIVE_N = 300
WC2_MIN_DECISIVE_PER_ASSET = 75
WC2_MIN_QUALIFYING_REGIMES = 3
WC2_MIN_DECISIVE_PER_REGIME = 50
WC2_MIN_CALENDAR_DAYS = 120
_MILLISECONDS_PER_DAY = 86_400_000
REAL_CAPITAL = 0


class WC2ReviewStatus(StrEnum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REVIEW_ELIGIBLE = "review_eligible"


@dataclass(frozen=True, slots=True)
class WC2UntouchedForwardPolicy:
    policy_identity: str
    preregistered_at_ms: int
    collection_start_ms: int
    evidence_class: EvidenceClass
    required_assets: tuple[str, ...]
    minimum_total_decisive_n: int
    minimum_decisive_per_asset: int
    minimum_qualifying_regimes: int
    minimum_decisive_per_regime: int
    minimum_calendar_days: int
    require_paper_decision_for_every_forecast: bool
    require_simulated_execution_for_every_trade: bool
    require_explicit_cost_evidence_for_every_trade: bool
    require_loss_retention: bool
    require_abstain_retention: bool
    require_invalidation_retention: bool
    require_unresolved_retention: bool
    automatic_promotion: bool = False
    performance_thresholds_included: bool = False
    schema_version: str = WC2_POLICY_SCHEMA_VERSION
    engine_version: str = WC2_POLICY_ENGINE_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "WC2 policy")
        if self.preregistered_at_ms < 0 or self.collection_start_ms < 0:
            raise ValueError("WC2 policy timestamps cannot be negative")
        if self.preregistered_at_ms >= self.collection_start_ms:
            raise ValueError(
                "WC2 policy must be preregistered before collection starts"
            )
        if self.evidence_class is not EvidenceClass.LIVE_UNTOUCHED_FORWARD:
            raise ValueError("WC2 policy accepts LIVE_UNTOUCHED_FORWARD only")
        if self.required_assets != tuple(sorted(set(self.required_assets))):
            raise ValueError("WC2 required assets must be sorted and unique")
        if self.required_assets != tuple(sorted(WC2_REQUIRED_ASSETS)):
            raise ValueError("WC2 required asset scope is locked to BTC/ETH/SOL")
        for value in (
            self.minimum_total_decisive_n,
            self.minimum_decisive_per_asset,
            self.minimum_qualifying_regimes,
            self.minimum_decisive_per_regime,
            self.minimum_calendar_days,
        ):
            if value <= 0:
                raise ValueError("WC2 review thresholds must be positive")
        if (
            self.minimum_total_decisive_n != WC2_MIN_TOTAL_DECISIVE_N
            or self.minimum_decisive_per_asset != WC2_MIN_DECISIVE_PER_ASSET
            or self.minimum_qualifying_regimes != WC2_MIN_QUALIFYING_REGIMES
            or self.minimum_decisive_per_regime
            != WC2_MIN_DECISIVE_PER_REGIME
            or self.minimum_calendar_days != WC2_MIN_CALENDAR_DAYS
        ):
            raise ValueError("WC2 v1 review thresholds are immutable")
        required_truths = (
            self.require_paper_decision_for_every_forecast,
            self.require_simulated_execution_for_every_trade,
            self.require_explicit_cost_evidence_for_every_trade,
            self.require_loss_retention,
            self.require_abstain_retention,
            self.require_invalidation_retention,
            self.require_unresolved_retention,
        )
        if not all(required_truths):
            raise ValueError("WC2 policy cannot weaken evidence retention")
        if self.automatic_promotion:
            raise ValueError("WC2 review eligibility cannot auto-promote")
        if self.performance_thresholds_included:
            raise ValueError(
                "WC2 policy cannot preregister a profitability winner threshold"
            )
        if self.schema_version != WC2_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 policy schema")
        if self.engine_version != WC2_POLICY_ENGINE_VERSION:
            raise ValueError("unsupported WC2 policy engine")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 policy cannot grant production authority")
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("WC2 policy identity mismatch")


@dataclass(frozen=True, slots=True)
class WC2CohortReadinessEvidence:
    evidence_identity: str
    policy_identity: str
    observed_at_ms: int
    collection_start_ms: int
    collection_end_ms: int
    evidence_class: EvidenceClass
    total_forecast_n: int
    resolved_forecast_n: int
    decisive_n: int
    paper_decision_n: int
    trade_decision_n: int
    simulated_execution_n: int
    explicit_cost_evidence_trade_n: int
    asset_decisive_counts: tuple[tuple[str, int], ...]
    regime_decisive_counts: tuple[tuple[str, int], ...]
    loss_retention_complete: bool
    abstain_retention_complete: bool
    invalidation_retention_complete: bool
    unresolved_retention_complete: bool
    source_evidence_identities: tuple[str, ...]
    schema_version: str = WC2_POLICY_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "WC2 cohort readiness evidence")
        _require_sha256(self.policy_identity, "WC2 cohort policy")
        if min(
            self.observed_at_ms,
            self.collection_start_ms,
            self.collection_end_ms,
        ) < 0:
            raise ValueError("WC2 cohort timestamps cannot be negative")
        if self.collection_end_ms < self.collection_start_ms:
            raise ValueError("WC2 cohort end cannot predate start")
        if self.observed_at_ms < self.collection_end_ms:
            raise ValueError("WC2 cohort observation cannot predate cohort end")
        if self.evidence_class is not EvidenceClass.LIVE_UNTOUCHED_FORWARD:
            raise ValueError("WC2 cohort must remain LIVE_UNTOUCHED_FORWARD")
        counts = (
            self.total_forecast_n,
            self.resolved_forecast_n,
            self.decisive_n,
            self.paper_decision_n,
            self.trade_decision_n,
            self.simulated_execution_n,
            self.explicit_cost_evidence_trade_n,
        )
        if min(counts) < 0:
            raise ValueError("WC2 cohort counts cannot be negative")
        if self.resolved_forecast_n > self.total_forecast_n:
            raise ValueError("WC2 resolved count exceeds forecasts")
        if self.decisive_n > self.resolved_forecast_n:
            raise ValueError("WC2 decisive count exceeds resolved forecasts")
        if self.paper_decision_n > self.total_forecast_n:
            raise ValueError("WC2 paper decision count exceeds forecasts")
        if self.trade_decision_n > self.paper_decision_n:
            raise ValueError("WC2 trade count exceeds paper decisions")
        if self.simulated_execution_n > self.trade_decision_n:
            raise ValueError("WC2 simulated fills exceed trade decisions")
        if self.explicit_cost_evidence_trade_n > self.simulated_execution_n:
            raise ValueError("WC2 cost evidence exceeds simulated executions")
        _validate_count_pairs(
            self.asset_decisive_counts,
            label="WC2 asset decisive counts",
        )
        if tuple(name for name, _ in self.asset_decisive_counts) != tuple(
            sorted(WC2_REQUIRED_ASSETS)
        ):
            raise ValueError(
                "WC2 asset decisive counts must cover BTC/ETH/SOL only"
            )
        _validate_count_pairs(
            self.regime_decisive_counts,
            label="WC2 regime decisive counts",
        )
        if sum(value for _, value in self.asset_decisive_counts) != self.decisive_n:
            raise ValueError(
                "WC2 asset decisive counts must equal decisive total"
            )
        if self.source_evidence_identities != tuple(
            sorted(set(self.source_evidence_identities))
        ):
            raise ValueError("WC2 source evidence identities must be canonical")
        if not self.source_evidence_identities:
            raise ValueError("WC2 cohort readiness requires source evidence")
        for identity in self.source_evidence_identities:
            _require_sha256(identity, "WC2 cohort source evidence")
        if self.schema_version != WC2_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 cohort schema")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 cohort evidence cannot grant authority")
        if self.evidence_identity != canonical_sha256(
            _cohort_evidence_payload(self)
        ):
            raise ValueError("WC2 cohort readiness evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class WC2ReviewReadiness:
    readiness_identity: str
    policy_identity: str
    evidence_identity: str
    status: WC2ReviewStatus
    reason_codes: tuple[str, ...]
    qualifying_regime_count: int
    calendar_duration_days: int
    semantic: str = "eligible_for_wc3_review_not_edge_or_profitability_claim"
    automatic_promotion: bool = False
    schema_version: str = WC2_POLICY_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.readiness_identity, "WC2 readiness"),
            (self.policy_identity, "WC2 readiness policy"),
            (self.evidence_identity, "WC2 readiness evidence"),
        ):
            _require_sha256(value, label)
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("WC2 readiness reasons must be canonical")
        if self.status is WC2ReviewStatus.REVIEW_ELIGIBLE:
            if self.reason_codes:
                raise ValueError("eligible WC2 review cannot retain blockers")
        elif not self.reason_codes:
            raise ValueError("insufficient WC2 review requires blockers")
        if self.qualifying_regime_count < 0 or self.calendar_duration_days < 0:
            raise ValueError("WC2 readiness coverage cannot be negative")
        if self.semantic != (
            "eligible_for_wc3_review_not_edge_or_profitability_claim"
        ):
            raise ValueError("WC2 readiness semantic mismatch")
        if self.automatic_promotion:
            raise ValueError("WC2 readiness cannot auto-promote")
        if self.schema_version != WC2_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 readiness schema")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 readiness cannot grant authority")
        if self.readiness_identity != canonical_sha256(
            _readiness_payload(self)
        ):
            raise ValueError("WC2 readiness identity mismatch")


def build_wc2_untouched_forward_policy(
    *,
    preregistered_at_ms: int,
    collection_start_ms: int,
) -> WC2UntouchedForwardPolicy:
    values = {
        "preregistered_at_ms": preregistered_at_ms,
        "collection_start_ms": collection_start_ms,
        "evidence_class": EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        "required_assets": tuple(sorted(WC2_REQUIRED_ASSETS)),
        "minimum_total_decisive_n": WC2_MIN_TOTAL_DECISIVE_N,
        "minimum_decisive_per_asset": WC2_MIN_DECISIVE_PER_ASSET,
        "minimum_qualifying_regimes": WC2_MIN_QUALIFYING_REGIMES,
        "minimum_decisive_per_regime": WC2_MIN_DECISIVE_PER_REGIME,
        "minimum_calendar_days": WC2_MIN_CALENDAR_DAYS,
        "require_paper_decision_for_every_forecast": True,
        "require_simulated_execution_for_every_trade": True,
        "require_explicit_cost_evidence_for_every_trade": True,
        "require_loss_retention": True,
        "require_abstain_retention": True,
        "require_invalidation_retention": True,
        "require_unresolved_retention": True,
        "automatic_promotion": False,
        "performance_thresholds_included": False,
        "schema_version": WC2_POLICY_SCHEMA_VERSION,
        "engine_version": WC2_POLICY_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return WC2UntouchedForwardPolicy(
        policy_identity=canonical_sha256(values),
        **values,
    )


def build_wc2_cohort_readiness_evidence(
    *,
    policy: WC2UntouchedForwardPolicy,
    observed_at_ms: int,
    collection_start_ms: int,
    collection_end_ms: int,
    total_forecast_n: int,
    resolved_forecast_n: int,
    decisive_n: int,
    paper_decision_n: int,
    trade_decision_n: int,
    simulated_execution_n: int,
    explicit_cost_evidence_trade_n: int,
    asset_decisive_counts: tuple[tuple[str, int], ...],
    regime_decisive_counts: tuple[tuple[str, int], ...],
    loss_retention_complete: bool,
    abstain_retention_complete: bool,
    invalidation_retention_complete: bool,
    unresolved_retention_complete: bool,
    source_evidence_identities: tuple[str, ...],
) -> WC2CohortReadinessEvidence:
    if collection_start_ms < policy.collection_start_ms:
        raise ValueError("WC2 cohort cannot predate preregistered collection start")
    values = {
        "policy_identity": policy.policy_identity,
        "observed_at_ms": observed_at_ms,
        "collection_start_ms": collection_start_ms,
        "collection_end_ms": collection_end_ms,
        "evidence_class": EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        "total_forecast_n": total_forecast_n,
        "resolved_forecast_n": resolved_forecast_n,
        "decisive_n": decisive_n,
        "paper_decision_n": paper_decision_n,
        "trade_decision_n": trade_decision_n,
        "simulated_execution_n": simulated_execution_n,
        "explicit_cost_evidence_trade_n": explicit_cost_evidence_trade_n,
        "asset_decisive_counts": tuple(sorted(asset_decisive_counts)),
        "regime_decisive_counts": tuple(sorted(regime_decisive_counts)),
        "loss_retention_complete": loss_retention_complete,
        "abstain_retention_complete": abstain_retention_complete,
        "invalidation_retention_complete": invalidation_retention_complete,
        "unresolved_retention_complete": unresolved_retention_complete,
        "source_evidence_identities": tuple(
            sorted(set(source_evidence_identities))
        ),
        "schema_version": WC2_POLICY_SCHEMA_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return WC2CohortReadinessEvidence(
        evidence_identity=canonical_sha256(values),
        **values,
    )


def evaluate_wc2_review_readiness(
    policy: WC2UntouchedForwardPolicy,
    evidence: WC2CohortReadinessEvidence,
) -> WC2ReviewReadiness:
    if evidence.policy_identity != policy.policy_identity:
        raise ValueError("WC2 cohort evidence references another policy")
    if evidence.collection_start_ms < policy.collection_start_ms:
        raise ValueError("WC2 cohort evidence predates policy collection start")

    reasons: set[str] = set()
    duration_ms = evidence.collection_end_ms - evidence.collection_start_ms
    calendar_days = duration_ms // _MILLISECONDS_PER_DAY
    if duration_ms < policy.minimum_calendar_days * _MILLISECONDS_PER_DAY:
        reasons.add("calendar_duration_below_minimum")
    if evidence.decisive_n < policy.minimum_total_decisive_n:
        reasons.add("decisive_sample_below_minimum")

    asset_counts = dict(evidence.asset_decisive_counts)
    for asset in policy.required_assets:
        if asset_counts.get(asset, 0) < policy.minimum_decisive_per_asset:
            reasons.add(f"asset_{asset}_decisive_support_below_minimum")

    qualifying_regimes = sum(
        count >= policy.minimum_decisive_per_regime
        for _, count in evidence.regime_decisive_counts
    )
    if qualifying_regimes < policy.minimum_qualifying_regimes:
        reasons.add("qualifying_regime_support_below_minimum")

    if (
        policy.require_paper_decision_for_every_forecast
        and evidence.paper_decision_n != evidence.total_forecast_n
    ):
        reasons.add("paper_decision_lineage_incomplete")
    if (
        policy.require_simulated_execution_for_every_trade
        and evidence.simulated_execution_n != evidence.trade_decision_n
    ):
        reasons.add("simulated_execution_lineage_incomplete")
    if (
        policy.require_explicit_cost_evidence_for_every_trade
        and evidence.explicit_cost_evidence_trade_n
        != evidence.trade_decision_n
    ):
        reasons.add("execution_cost_evidence_incomplete")
    if policy.require_loss_retention and not evidence.loss_retention_complete:
        reasons.add("loss_retention_incomplete")
    if (
        policy.require_abstain_retention
        and not evidence.abstain_retention_complete
    ):
        reasons.add("abstain_retention_incomplete")
    if (
        policy.require_invalidation_retention
        and not evidence.invalidation_retention_complete
    ):
        reasons.add("invalidation_retention_incomplete")
    if (
        policy.require_unresolved_retention
        and not evidence.unresolved_retention_complete
    ):
        reasons.add("unresolved_retention_incomplete")

    ordered_reasons = tuple(sorted(reasons))
    status = (
        WC2ReviewStatus.REVIEW_ELIGIBLE
        if not ordered_reasons
        else WC2ReviewStatus.INSUFFICIENT_EVIDENCE
    )
    values = {
        "policy_identity": policy.policy_identity,
        "evidence_identity": evidence.evidence_identity,
        "status": status,
        "reason_codes": ordered_reasons,
        "qualifying_regime_count": qualifying_regimes,
        "calendar_duration_days": calendar_days,
        "semantic": "eligible_for_wc3_review_not_edge_or_profitability_claim",
        "automatic_promotion": False,
        "schema_version": WC2_POLICY_SCHEMA_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return WC2ReviewReadiness(
        readiness_identity=canonical_sha256(values),
        **values,
    )


class WC2PolicyStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS wc2_forward_policies (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_identity TEXT UNIQUE NOT NULL,
                    preregistered_at_ms INTEGER NOT NULL,
                    collection_start_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS wc2_forward_policy_no_update
                BEFORE UPDATE ON wc2_forward_policies
                BEGIN
                    SELECT RAISE(ABORT, 'WC2 policy registry is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS wc2_forward_policy_no_delete
                BEFORE DELETE ON wc2_forward_policies
                BEGIN
                    SELECT RAISE(ABORT, 'WC2 policy registry is append-only');
                END;
                """
            )

    def append(self, policy: WC2UntouchedForwardPolicy) -> bool:
        self.initialize()
        payload = canonical_json(_policy_payload(policy))
        with sqlite3.connect(self.path) as db:
            existing = db.execute(
                "SELECT payload_json FROM wc2_forward_policies "
                "WHERE policy_identity=?",
                (policy.policy_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload:
                    raise ValueError("WC2 policy identity conflict")
                return False
            previous = db.execute(
                """
                SELECT collection_start_ms
                FROM wc2_forward_policies
                ORDER BY sequence_id DESC
                LIMIT 1
                """
            ).fetchone()
            if previous is not None and policy.collection_start_ms <= int(
                previous[0]
            ):
                raise ValueError(
                    "new WC2 policy must start after prior policy cohort"
                )
            db.execute(
                """
                INSERT INTO wc2_forward_policies(
                    policy_identity,
                    preregistered_at_ms,
                    collection_start_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    policy.policy_identity,
                    policy.preregistered_at_ms,
                    policy.collection_start_ms,
                    payload,
                ),
            )
        return True

    def count(self) -> int:
        if not self.path.is_file():
            return 0
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT COUNT(*) FROM wc2_forward_policies"
            ).fetchone()
        return 0 if row is None else int(row[0])

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        with sqlite3.connect(self.path) as db:
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]).lower() == "ok"


def _validate_count_pairs(
    values: tuple[tuple[str, int], ...],
    *,
    label: str,
) -> None:
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} must be sorted")
    names = tuple(name for name, _ in values)
    if len(set(names)) != len(names):
        raise ValueError(f"{label} must be unique")
    for name, count in values:
        if not name.strip() or count < 0:
            raise ValueError(f"{label} contains invalid entry")


def _policy_payload(
    policy: WC2UntouchedForwardPolicy,
) -> dict[str, object]:
    return {
        "preregistered_at_ms": policy.preregistered_at_ms,
        "collection_start_ms": policy.collection_start_ms,
        "evidence_class": policy.evidence_class,
        "required_assets": policy.required_assets,
        "minimum_total_decisive_n": policy.minimum_total_decisive_n,
        "minimum_decisive_per_asset": policy.minimum_decisive_per_asset,
        "minimum_qualifying_regimes": policy.minimum_qualifying_regimes,
        "minimum_decisive_per_regime": policy.minimum_decisive_per_regime,
        "minimum_calendar_days": policy.minimum_calendar_days,
        "require_paper_decision_for_every_forecast": (
            policy.require_paper_decision_for_every_forecast
        ),
        "require_simulated_execution_for_every_trade": (
            policy.require_simulated_execution_for_every_trade
        ),
        "require_explicit_cost_evidence_for_every_trade": (
            policy.require_explicit_cost_evidence_for_every_trade
        ),
        "require_loss_retention": policy.require_loss_retention,
        "require_abstain_retention": policy.require_abstain_retention,
        "require_invalidation_retention": policy.require_invalidation_retention,
        "require_unresolved_retention": policy.require_unresolved_retention,
        "automatic_promotion": policy.automatic_promotion,
        "performance_thresholds_included": (
            policy.performance_thresholds_included
        ),
        "schema_version": policy.schema_version,
        "engine_version": policy.engine_version,
        "production_authority": policy.production_authority,
        "real_capital": policy.real_capital,
    }


def _cohort_evidence_payload(
    evidence: WC2CohortReadinessEvidence,
) -> dict[str, object]:
    return {
        "policy_identity": evidence.policy_identity,
        "observed_at_ms": evidence.observed_at_ms,
        "collection_start_ms": evidence.collection_start_ms,
        "collection_end_ms": evidence.collection_end_ms,
        "evidence_class": evidence.evidence_class,
        "total_forecast_n": evidence.total_forecast_n,
        "resolved_forecast_n": evidence.resolved_forecast_n,
        "decisive_n": evidence.decisive_n,
        "paper_decision_n": evidence.paper_decision_n,
        "trade_decision_n": evidence.trade_decision_n,
        "simulated_execution_n": evidence.simulated_execution_n,
        "explicit_cost_evidence_trade_n": (
            evidence.explicit_cost_evidence_trade_n
        ),
        "asset_decisive_counts": evidence.asset_decisive_counts,
        "regime_decisive_counts": evidence.regime_decisive_counts,
        "loss_retention_complete": evidence.loss_retention_complete,
        "abstain_retention_complete": evidence.abstain_retention_complete,
        "invalidation_retention_complete": (
            evidence.invalidation_retention_complete
        ),
        "unresolved_retention_complete": evidence.unresolved_retention_complete,
        "source_evidence_identities": evidence.source_evidence_identities,
        "schema_version": evidence.schema_version,
        "production_authority": evidence.production_authority,
        "real_capital": evidence.real_capital,
    }


def _readiness_payload(
    readiness: WC2ReviewReadiness,
) -> dict[str, object]:
    return {
        "policy_identity": readiness.policy_identity,
        "evidence_identity": readiness.evidence_identity,
        "status": readiness.status,
        "reason_codes": readiness.reason_codes,
        "qualifying_regime_count": readiness.qualifying_regime_count,
        "calendar_duration_days": readiness.calendar_duration_days,
        "semantic": readiness.semantic,
        "automatic_promotion": readiness.automatic_promotion,
        "schema_version": readiness.schema_version,
        "production_authority": readiness.production_authority,
        "real_capital": readiness.real_capital,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
