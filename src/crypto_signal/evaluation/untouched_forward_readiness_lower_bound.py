"""Fail-closed WC2 readiness lower-bound probe.

This module intentionally does NOT define which resolution states are
"decisive". The preregistered WC2 policy locks decisive thresholds but the
accepted policy contract does not currently map canonical resolution states to
that term. Post-start invention of such a mapping would change the scientific
protocol.

Instead, this probe uses only necessary upper bounds:
decisive observations cannot exceed resolved observations, per-asset decisive
support cannot exceed per-asset resolved support, and qualifying decisive
regimes cannot exceed regimes whose resolved support already reaches the
preregistered per-regime minimum.

Therefore this probe may prove DEFINITELY_INSUFFICIENT, but it can never claim
REVIEW_ELIGIBLE.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_journal import WC2CohortJournal
from crypto_signal.evaluation.untouched_forward_policy import (
    REAL_CAPITAL,
    WC2_MIN_CALENDAR_DAYS,
    WC2_MIN_DECISIVE_PER_ASSET,
    WC2_MIN_DECISIVE_PER_REGIME,
    WC2_MIN_QUALIFYING_REGIMES,
    WC2_MIN_TOTAL_DECISIVE_N,
    WC2_REQUIRED_ASSETS,
    WC2PolicyStore,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import PaperAction

WC2_LOWER_BOUND_SCHEMA_VERSION = "wc2-readiness-lower-bound-v1/1"
WC2_LOWER_BOUND_ENGINE_VERSION = "wc2-readiness-lower-bound-probe-v1/1"
_MILLISECONDS_PER_DAY = 86_400_000


class WC2LowerBoundStatus(StrEnum):
    DEFINITELY_INSUFFICIENT = "definitely_insufficient"
    FULL_READINESS_EVALUATION_REQUIRED = "full_readiness_evaluation_required"


@dataclass(frozen=True, slots=True)
class WC2ReadinessLowerBound:
    snapshot_identity: str
    schema_version: str
    engine_version: str
    policy_identity: str
    observed_at_ms: int
    collection_start_ms: int
    calendar_duration_days: int
    forecast_n: int
    resolved_n: int
    unresolved_n: int
    paper_decision_covered_forecast_n: int
    trade_intent_n: int
    trade_intent_with_execution_n: int
    resolved_upper_bound_by_asset: tuple[tuple[str, int], ...]
    resolved_upper_bound_by_regime: tuple[tuple[str, int], ...]
    qualifying_regime_upper_bound: int
    guaranteed_reason_codes: tuple[str, ...]
    status: WC2LowerBoundStatus
    decisive_mapping_applied: bool = False
    review_eligible_claimed: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "WC2 lower-bound snapshot")
        _require_sha256(self.policy_identity, "WC2 lower-bound policy")
        if self.schema_version != WC2_LOWER_BOUND_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 lower-bound schema")
        if self.engine_version != WC2_LOWER_BOUND_ENGINE_VERSION:
            raise ValueError("unsupported WC2 lower-bound engine")
        if self.observed_at_ms < self.collection_start_ms:
            raise ValueError("WC2 lower-bound observation predates collection")
        counts = (
            self.calendar_duration_days,
            self.forecast_n,
            self.resolved_n,
            self.unresolved_n,
            self.paper_decision_covered_forecast_n,
            self.trade_intent_n,
            self.trade_intent_with_execution_n,
            self.qualifying_regime_upper_bound,
        )
        if min(counts) < 0:
            raise ValueError("WC2 lower-bound counts cannot be negative")
        if self.resolved_n > self.forecast_n:
            raise ValueError("WC2 lower-bound resolutions exceed forecasts")
        if self.unresolved_n != self.forecast_n - self.resolved_n:
            raise ValueError("WC2 lower-bound unresolved count mismatch")
        if self.paper_decision_covered_forecast_n > self.forecast_n:
            raise ValueError("WC2 lower-bound paper coverage exceeds forecasts")
        if self.trade_intent_with_execution_n > self.trade_intent_n:
            raise ValueError("WC2 lower-bound executions exceed trade intents")
        _validate_count_pairs(
            self.resolved_upper_bound_by_asset,
            label="WC2 resolved upper bound by asset",
        )
        if tuple(name for name, _ in self.resolved_upper_bound_by_asset) != (
            tuple(sorted(WC2_REQUIRED_ASSETS))
        ):
            raise ValueError("WC2 lower-bound asset scope mismatch")
        _validate_count_pairs(
            self.resolved_upper_bound_by_regime,
            label="WC2 resolved upper bound by regime",
        )
        if sum(value for _, value in self.resolved_upper_bound_by_asset) != (
            self.resolved_n
        ):
            raise ValueError("WC2 lower-bound asset counts must equal resolutions")
        if self.guaranteed_reason_codes != tuple(
            sorted(set(self.guaranteed_reason_codes))
        ):
            raise ValueError("WC2 lower-bound reasons must be canonical")
        if self.decisive_mapping_applied:
            raise ValueError("WC2 lower-bound probe cannot define decisive mapping")
        if self.review_eligible_claimed:
            raise ValueError("WC2 lower-bound probe cannot claim REVIEW_ELIGIBLE")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 lower-bound probe cannot grant authority")
        expected_status = (
            WC2LowerBoundStatus.DEFINITELY_INSUFFICIENT
            if self.guaranteed_reason_codes
            else WC2LowerBoundStatus.FULL_READINESS_EVALUATION_REQUIRED
        )
        if self.status is not expected_status:
            raise ValueError("WC2 lower-bound status/reason mismatch")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("WC2 lower-bound snapshot identity mismatch")


def read_wc2_readiness_lower_bound(
    *,
    policy_path: Path,
    cohort_path: Path,
    observed_at_ms: int,
) -> WC2ReadinessLowerBound:
    """Read necessary readiness blockers from accepted append-only WC2 stores."""

    if observed_at_ms < 0:
        raise ValueError("WC2 lower-bound observation time cannot be negative")

    policy = WC2PolicyStore(policy_path).latest()
    if policy is None:
        raise FileNotFoundError("WC2 review policy is not registered")
    if observed_at_ms < policy.collection_start_ms:
        raise ValueError("WC2 lower-bound observation predates policy start")

    status = WC2CohortJournal(cohort_path).verify_read_only()
    if not status.read_only_verified or not status.quick_check_ok:
        raise ValueError("WC2 cohort did not pass read-only verification")

    uri = f"{cohort_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA foreign_keys=ON")

        policy_rows = db.execute(
            """
            SELECT DISTINCT policy_identity
            FROM wc2_cohort_forecasts
            """
        ).fetchall()
        if any(str(row[0]) != policy.policy_identity for row in policy_rows):
            raise ValueError("WC2 cohort contains forecast from another policy")

        covered = _scalar(
            db,
            """
            SELECT COUNT(DISTINCT f.forecast_identity)
            FROM wc2_cohort_forecasts AS f
            JOIN wc2_cohort_intents AS i
              ON i.forecast_identity = f.forecast_identity
            """,
        )
        trade_intent_n = _scalar(
            db,
            """
            SELECT COUNT(*)
            FROM wc2_cohort_intents
            WHERE action != ?
            """,
            (PaperAction.HOLD_CASH.value,),
        )
        trade_with_execution_n = _scalar(
            db,
            """
            SELECT COUNT(DISTINCT i.intent_link_identity)
            FROM wc2_cohort_intents AS i
            JOIN wc2_cohort_executions AS e
              ON e.intent_link_identity = i.intent_link_identity
            WHERE i.action != ?
            """,
            (PaperAction.HOLD_CASH.value,),
        )

        asset_counts_raw = {
            str(row[0]): int(row[1])
            for row in db.execute(
                """
                SELECT f.symbol, COUNT(*)
                FROM wc2_cohort_resolutions AS r
                JOIN wc2_cohort_forecasts AS f
                  ON f.cohort_forecast_identity = r.cohort_forecast_identity
                GROUP BY f.symbol
                """
            ).fetchall()
        }
        asset_counts = tuple(
            (asset, asset_counts_raw.get(asset, 0))
            for asset in sorted(WC2_REQUIRED_ASSETS)
        )

        regime_counts = tuple(
            sorted(
                (
                    str(row[0]),
                    int(row[1]),
                )
                for row in db.execute(
                    """
                    SELECT f.regime, COUNT(*)
                    FROM wc2_cohort_resolutions AS r
                    JOIN wc2_cohort_forecasts AS f
                      ON f.cohort_forecast_identity = r.cohort_forecast_identity
                    GROUP BY f.regime
                    """
                ).fetchall()
            )
        )

    calendar_days = (
        observed_at_ms - policy.collection_start_ms
    ) // _MILLISECONDS_PER_DAY
    qualifying_regime_upper_bound = sum(
        count >= WC2_MIN_DECISIVE_PER_REGIME
        for _, count in regime_counts
    )

    reasons: set[str] = set()
    if observed_at_ms - policy.collection_start_ms < (
        WC2_MIN_CALENDAR_DAYS * _MILLISECONDS_PER_DAY
    ):
        reasons.add("calendar_duration_below_minimum")
    if status.resolution_count < WC2_MIN_TOTAL_DECISIVE_N:
        reasons.add("decisive_sample_below_minimum")
    for asset, resolved_upper_bound in asset_counts:
        if resolved_upper_bound < WC2_MIN_DECISIVE_PER_ASSET:
            reasons.add(f"asset_{asset}_decisive_support_below_minimum")
    if qualifying_regime_upper_bound < WC2_MIN_QUALIFYING_REGIMES:
        reasons.add("qualifying_regime_support_below_minimum")
    if covered != status.forecast_count:
        reasons.add("paper_decision_lineage_incomplete")
    if trade_with_execution_n != trade_intent_n:
        reasons.add("simulated_execution_lineage_incomplete")
        reasons.add("execution_cost_evidence_incomplete")

    reason_codes = tuple(sorted(reasons))
    lower_bound_status = (
        WC2LowerBoundStatus.DEFINITELY_INSUFFICIENT
        if reason_codes
        else WC2LowerBoundStatus.FULL_READINESS_EVALUATION_REQUIRED
    )
    values = {
        "calendar_duration_days": calendar_days,
        "collection_start_ms": policy.collection_start_ms,
        "decisive_mapping_applied": False,
        "engine_version": WC2_LOWER_BOUND_ENGINE_VERSION,
        "forecast_n": status.forecast_count,
        "guaranteed_reason_codes": reason_codes,
        "observed_at_ms": observed_at_ms,
        "paper_decision_covered_forecast_n": covered,
        "policy_identity": policy.policy_identity,
        "production_authority": False,
        "qualifying_regime_upper_bound": qualifying_regime_upper_bound,
        "real_capital": REAL_CAPITAL,
        "resolved_n": status.resolution_count,
        "resolved_upper_bound_by_asset": asset_counts,
        "resolved_upper_bound_by_regime": regime_counts,
        "review_eligible_claimed": False,
        "schema_version": WC2_LOWER_BOUND_SCHEMA_VERSION,
        "status": lower_bound_status,
        "trade_intent_n": trade_intent_n,
        "trade_intent_with_execution_n": trade_with_execution_n,
        "unresolved_n": status.unresolved_forecast_count,
    }
    return WC2ReadinessLowerBound(
        snapshot_identity=canonical_sha256(values),
        schema_version=WC2_LOWER_BOUND_SCHEMA_VERSION,
        engine_version=WC2_LOWER_BOUND_ENGINE_VERSION,
        policy_identity=policy.policy_identity,
        observed_at_ms=observed_at_ms,
        collection_start_ms=policy.collection_start_ms,
        calendar_duration_days=calendar_days,
        forecast_n=status.forecast_count,
        resolved_n=status.resolution_count,
        unresolved_n=status.unresolved_forecast_count,
        paper_decision_covered_forecast_n=covered,
        trade_intent_n=trade_intent_n,
        trade_intent_with_execution_n=trade_with_execution_n,
        resolved_upper_bound_by_asset=asset_counts,
        resolved_upper_bound_by_regime=regime_counts,
        qualifying_regime_upper_bound=qualifying_regime_upper_bound,
        guaranteed_reason_codes=reason_codes,
        status=lower_bound_status,
        decisive_mapping_applied=False,
        review_eligible_claimed=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def _snapshot_payload(
    snapshot: WC2ReadinessLowerBound,
) -> dict[str, object]:
    return {
        "calendar_duration_days": snapshot.calendar_duration_days,
        "collection_start_ms": snapshot.collection_start_ms,
        "decisive_mapping_applied": snapshot.decisive_mapping_applied,
        "engine_version": snapshot.engine_version,
        "forecast_n": snapshot.forecast_n,
        "guaranteed_reason_codes": snapshot.guaranteed_reason_codes,
        "observed_at_ms": snapshot.observed_at_ms,
        "paper_decision_covered_forecast_n": (
            snapshot.paper_decision_covered_forecast_n
        ),
        "policy_identity": snapshot.policy_identity,
        "production_authority": snapshot.production_authority,
        "qualifying_regime_upper_bound": snapshot.qualifying_regime_upper_bound,
        "real_capital": snapshot.real_capital,
        "resolved_n": snapshot.resolved_n,
        "resolved_upper_bound_by_asset": snapshot.resolved_upper_bound_by_asset,
        "resolved_upper_bound_by_regime": snapshot.resolved_upper_bound_by_regime,
        "review_eligible_claimed": snapshot.review_eligible_claimed,
        "schema_version": snapshot.schema_version,
        "status": snapshot.status,
        "trade_intent_n": snapshot.trade_intent_n,
        "trade_intent_with_execution_n": snapshot.trade_intent_with_execution_n,
        "unresolved_n": snapshot.unresolved_n,
    }


def _scalar(
    db: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...] = (),
) -> int:
    row = db.execute(query, parameters).fetchone()
    return 0 if row is None else int(row[0])


def _validate_count_pairs(
    values: tuple[tuple[str, int], ...],
    *,
    label: str,
) -> None:
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} must be sorted")
    names = tuple(name for name, _ in values)
    if len(names) != len(set(names)):
        raise ValueError(f"{label} must be unique")
    for name, count in values:
        if not name.strip() or count < 0:
            raise ValueError(f"{label} contains invalid entry")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
