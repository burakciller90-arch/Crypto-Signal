"""WC2 readiness lower-bound probe acceptance."""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from crypto_signal.evaluation import untouched_forward_readiness_lower_bound
from crypto_signal.evaluation.untouched_forward_journal import WC2CohortJournal
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2_MIN_CALENDAR_DAYS,
    WC2LowerBoundStatus if False else WC2ReviewStatus,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2PolicyStore,
    build_wc2_untouched_forward_policy,
)
from crypto_signal.evaluation.untouched_forward_readiness_lower_bound import (
    WC2LowerBoundStatus,
    read_wc2_readiness_lower_bound,
)

DAY_MS = 86_400_000


def _sha(index: int) -> str:
    return f"{index:064x}"


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    return (
        tmp_path / "wc2_forward_policy.sqlite3",
        tmp_path / "wc2_untouched_forward.sqlite3",
    )


def _seed_policy(policy_path: Path, *, collection_start_ms: int = 2_000):
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=1_000,
        collection_start_ms=collection_start_ms,
    )
    assert WC2PolicyStore(policy_path).append(policy) is True
    return policy


def _seed_cohort(
    cohort_path: Path,
    *,
    policy_identity: str,
    rows: tuple[tuple[str, str, bool, bool], ...],
) -> None:
    """Rows are (symbol, regime, resolved, trade_intent)."""

    WC2CohortJournal(cohort_path).initialize()
    with sqlite3.connect(cohort_path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        for index, (symbol, regime, resolved, trade_intent) in enumerate(
            rows,
            start=1,
        ):
            cohort_identity = _sha(10_000 + index)
            forecast_identity = _sha(20_000 + index)
            proof_identity = _sha(30_000 + index)
            db.execute(
                """
                INSERT INTO wc2_cohort_forecasts(
                    cohort_forecast_identity,
                    policy_identity,
                    forecast_identity,
                    proof_identity,
                    symbol,
                    regime,
                    issued_at_ms,
                    indexed_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cohort_identity,
                    policy_identity,
                    forecast_identity,
                    proof_identity,
                    symbol,
                    regime,
                    3_000 + index,
                    3_000 + index,
                    "{}",
                ),
            )
            intent_identity = _sha(40_000 + index)
            action = "BUY" if trade_intent else "HOLD_CASH"
            db.execute(
                """
                INSERT INTO wc2_cohort_intents(
                    intent_link_identity,
                    cohort_forecast_identity,
                    policy_identity,
                    forecast_identity,
                    paper_intent_identity,
                    vault_id,
                    action,
                    indexed_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent_identity,
                    cohort_identity,
                    policy_identity,
                    forecast_identity,
                    _sha(50_000 + index),
                    "CORE",
                    action,
                    4_000 + index,
                    "{}",
                ),
            )
            if trade_intent and resolved:
                db.execute(
                    """
                    INSERT INTO wc2_cohort_executions(
                        execution_link_identity,
                        cohort_forecast_identity,
                        intent_link_identity,
                        forecast_identity,
                        fill_identity,
                        indexed_at_ms,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _sha(60_000 + index),
                        cohort_identity,
                        intent_identity,
                        forecast_identity,
                        _sha(70_000 + index),
                        5_000 + index,
                        "{}",
                    ),
                )
            if resolved:
                db.execute(
                    """
                    INSERT INTO wc2_cohort_resolutions(
                        resolution_link_identity,
                        cohort_forecast_identity,
                        forecast_identity,
                        resolution_identity,
                        evaluated_at_ms,
                        indexed_at_ms,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _sha(80_000 + index),
                        cohort_identity,
                        forecast_identity,
                        _sha(90_000 + index),
                        6_000 + index,
                        6_000 + index,
                        "{}",
                    ),
                )


def test_lower_bound_proves_insufficient_without_defining_decisive_mapping(
    tmp_path: Path,
) -> None:
    policy_path, cohort_path = _paths(tmp_path)
    policy = _seed_policy(policy_path)
    _seed_cohort(
        cohort_path,
        policy_identity=policy.policy_identity,
        rows=(
            ("BTCUSDT", "range", True, False),
            ("ETHUSDT", "range", True, False),
            ("SOLUSDT", "transition", False, False),
            ("BTCUSDT", "transition", False, False),
            ("ETHUSDT", "range", False, False),
        ),
    )
    policy_before = policy_path.read_bytes()
    cohort_before = cohort_path.read_bytes()

    snapshot = read_wc2_readiness_lower_bound(
        policy_path=policy_path,
        cohort_path=cohort_path,
        observed_at_ms=policy.collection_start_ms + DAY_MS,
    )

    assert snapshot.status is WC2LowerBoundStatus.DEFINITELY_INSUFFICIENT
    assert snapshot.forecast_n == 5
    assert snapshot.resolved_n == 2
    assert snapshot.unresolved_n == 3
    assert snapshot.paper_decision_covered_forecast_n == 5
    assert snapshot.trade_intent_n == 0
    assert snapshot.trade_intent_with_execution_n == 0
    assert snapshot.resolved_upper_bound_by_asset == (
        ("BTCUSDT", 1),
        ("ETHUSDT", 1),
        ("SOLUSDT", 0),
    )
    assert snapshot.qualifying_regime_upper_bound == 0
    assert snapshot.guaranteed_reason_codes == tuple(
        sorted(
            {
                "asset_BTCUSDT_decisive_support_below_minimum",
                "asset_ETHUSDT_decisive_support_below_minimum",
                "asset_SOLUSDT_decisive_support_below_minimum",
                "calendar_duration_below_minimum",
                "decisive_sample_below_minimum",
                "qualifying_regime_support_below_minimum",
            }
        )
    )
    assert snapshot.decisive_mapping_applied is False
    assert snapshot.review_eligible_claimed is False
    assert snapshot.production_authority is False
    assert snapshot.real_capital == 0
    assert policy_path.read_bytes() == policy_before
    assert cohort_path.read_bytes() == cohort_before


def test_lower_bound_detects_missing_trade_execution_as_necessary_blocker(
    tmp_path: Path,
) -> None:
    policy_path, cohort_path = _paths(tmp_path)
    policy = _seed_policy(policy_path)
    _seed_cohort(
        cohort_path,
        policy_identity=policy.policy_identity,
        rows=(("BTCUSDT", "range", False, True),),
    )

    snapshot = read_wc2_readiness_lower_bound(
        policy_path=policy_path,
        cohort_path=cohort_path,
        observed_at_ms=policy.collection_start_ms + DAY_MS,
    )

    assert snapshot.trade_intent_n == 1
    assert snapshot.trade_intent_with_execution_n == 0
    assert "simulated_execution_lineage_incomplete" in (
        snapshot.guaranteed_reason_codes
    )
    assert "execution_cost_evidence_incomplete" in (
        snapshot.guaranteed_reason_codes
    )


def test_lower_bound_never_promotes_when_necessary_upper_bounds_are_met(
    tmp_path: Path,
) -> None:
    policy_path, cohort_path = _paths(tmp_path)
    policy = _seed_policy(policy_path)

    rows = tuple(
        (symbol, regime, True, False)
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        for regime in ("high_vol_trend", "low_vol_range", "transition")
        for _ in range(40)
    )
    assert len(rows) == 360
    _seed_cohort(
        cohort_path,
        policy_identity=policy.policy_identity,
        rows=rows,
    )

    snapshot = read_wc2_readiness_lower_bound(
        policy_path=policy_path,
        cohort_path=cohort_path,
        observed_at_ms=(
            policy.collection_start_ms + WC2_MIN_CALENDAR_DAYS * DAY_MS
        ),
    )

    assert snapshot.resolved_n == 360
    assert snapshot.resolved_upper_bound_by_asset == (
        ("BTCUSDT", 120),
        ("ETHUSDT", 120),
        ("SOLUSDT", 120),
    )
    assert snapshot.qualifying_regime_upper_bound == 3
    assert snapshot.guaranteed_reason_codes == ()
    assert snapshot.status is (
        WC2LowerBoundStatus.FULL_READINESS_EVALUATION_REQUIRED
    )
    assert snapshot.decisive_mapping_applied is False
    assert snapshot.review_eligible_claimed is False


def test_lower_bound_source_has_no_resolution_state_mapping_or_write_surface() -> None:
    source = inspect.getsource(untouched_forward_readiness_lower_bound).lower()
    forbidden = (
        "forecastresolutionstate",
        "hit_target",
        "invalidated",
        "expired",
        "ambiguous",
        "not_evaluable",
        "cancelled",
        "evaluate_wc2_review_readiness",
        "insert into",
        "update ",
        "delete ",
        "write_text",
        "write_bytes",
        "production_authority=true",
    )
    assert all(token not in source for token in forbidden)
    assert "decisive observations cannot exceed resolved observations" in source
    assert untouched_forward_readiness_lower_bound.REAL_CAPITAL == 0
