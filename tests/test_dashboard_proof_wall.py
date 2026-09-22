from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from crypto_signal.confluence.models import ScoreSemantic
from crypto_signal.product.models import ProductDataStatus
from crypto_signal.product.reader import DashboardReader, DashboardReadError
from crypto_signal.signals.models import ProbabilityStatus


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def create_signal_schema(path: Path, *, outcomes: bool) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE signal_freezes (
                bundle_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT NOT NULL UNIQUE,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                as_of_ms INTEGER NOT NULL,
                source_cutoff_open_time_ms INTEGER NOT NULL,
                signal_state TEXT NOT NULL,
                direction TEXT NOT NULL,
                bundle_json TEXT NOT NULL,
                frozen_at_ms INTEGER NOT NULL
            )
            """
        )
        if outcomes:
            connection.execute(
                """
                CREATE TABLE outcome_evaluations (
                    outcome_identity TEXT PRIMARY KEY,
                    signal_freeze_identity TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    evaluated_as_of_ms INTEGER NOT NULL,
                    resolution_status TEXT NOT NULL,
                    outcome_state TEXT,
                    max_holding_bars INTEGER NOT NULL,
                    outcome_json TEXT NOT NULL,
                    appended_at_ms INTEGER NOT NULL
                )
                """
            )


def signal_bundle(*, state: str = "active", direction: str = "bullish") -> str:
    return json.dumps(
        {
            "signal_decision": {
                "state": state,
                "direction": direction,
                "setup_type": "proof_wall_fixture",
                "agreement": {
                    "confluence_score": "66.67",
                    "score_semantic": (
                        ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY.value
                    ),
                },
                "probability_status": ProbabilityStatus.NOT_CALIBRATED.value,
                "uncertainty_flags": [],
            }
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def insert_signal(
    path: Path,
    *,
    seed: str,
    frozen_at_ms: int,
) -> str:
    signal_id = digest(f"signal-{seed}")
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO signal_freezes (
                bundle_identity,
                signal_freeze_identity,
                exchange,
                market_type,
                symbol,
                timeframe,
                as_of_ms,
                source_cutoff_open_time_ms,
                signal_state,
                direction,
                bundle_json,
                frozen_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest(f"bundle-{seed}"),
                signal_id,
                "bybit",
                "spot",
                "BTCUSDT",
                "15m",
                frozen_at_ms - 100,
                frozen_at_ms - 200,
                "active",
                "bullish",
                signal_bundle(),
                frozen_at_ms,
            ),
        )
    return signal_id


def insert_outcome(
    path: Path,
    *,
    signal_id: str,
    seed: str,
    evaluated_as_of_ms: int,
    resolution_status: str,
    outcome_state: str | None,
    evidence_class: str = "walk_forward",
    max_holding_bars: int = 4,
) -> str:
    outcome_id = digest(f"outcome-{seed}")
    payload = {
        "outcome_identity": outcome_id,
        "signal_freeze_identity": signal_id,
        "evidence_class": evidence_class,
        "evaluated_as_of_ms": evaluated_as_of_ms,
        "resolution_status": resolution_status,
        "outcome_state": outcome_state,
        "signal_initial_state": "active",
        "coverage_status": "complete",
        "max_holding_bars": max_holding_bars,
        "expected_bar_count": 1,
        "observed_bar_count": 1,
        "missing_open_times_ms": [],
        "skipped_partial_decision_bucket": True,
        "entry_observed": True,
        "entry_candle_identity": ["bybit", "spot", "BTCUSDT", "15m", 1800],
        "highest_target_index": (
            1 if outcome_state == "success_tp1" else 0
        ),
        "outcome_candle_identity": (
            None
            if outcome_state is None
            else ["bybit", "spot", "BTCUSDT", "15m", 2700]
        ),
        "ambiguity_reason": None,
        "not_evaluable_reason": None,
    }
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO outcome_evaluations (
                outcome_identity,
                signal_freeze_identity,
                evidence_class,
                evaluated_as_of_ms,
                resolution_status,
                outcome_state,
                max_holding_bars,
                outcome_json,
                appended_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome_id,
                signal_id,
                evidence_class,
                evaluated_as_of_ms,
                resolution_status,
                outcome_state,
                max_holding_bars,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                evaluated_as_of_ms + 1,
            ),
        )
    return outcome_id


def test_proof_wall_selects_latest_stored_outcome_snapshot_per_signal(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path, outcomes=True)
    older_signal = insert_signal(path, seed="older", frozen_at_ms=1100)
    newer_signal = insert_signal(path, seed="newer", frozen_at_ms=2100)

    insert_outcome(
        path,
        signal_id=older_signal,
        seed="pending",
        evaluated_as_of_ms=2000,
        resolution_status="pending",
        outcome_state=None,
    )
    latest_id = insert_outcome(
        path,
        signal_id=older_signal,
        seed="success",
        evaluated_as_of_ms=3000,
        resolution_status="resolved",
        outcome_state="success_tp1",
    )

    view = DashboardReader(path).proof_wall(limit=10)

    assert view.status is ProductDataStatus.READY
    assert view.total_count == 2
    assert view.outcome_schema_available is True
    assert [item.signal.signal_freeze_identity for item in view.items] == [
        newer_signal,
        older_signal,
    ]
    assert view.items[0].latest_outcome is None

    outcome = view.items[1].latest_outcome
    assert outcome is not None
    assert outcome.outcome_identity == latest_id
    assert outcome.outcome_state is not None
    assert outcome.outcome_state.value == "success_tp1"
    assert outcome.resolution_status.value == "resolved"
    assert outcome.evidence_class.value == "walk_forward"
    assert outcome.max_holding_bars == 4
    assert outcome.coverage_status.value == "complete"


def test_proof_wall_keeps_issuance_visible_when_outcome_schema_is_absent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path, outcomes=False)
    signal_id = insert_signal(path, seed="no-outcome-schema", frozen_at_ms=1100)

    view = DashboardReader(path).proof_wall(limit=10)

    assert view.status is ProductDataStatus.READY
    assert view.total_count == 1
    assert view.outcome_schema_available is False
    assert view.items[0].signal.signal_freeze_identity == signal_id
    assert view.items[0].latest_outcome is None


def test_proof_wall_fails_closed_on_malformed_latest_outcome(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path, outcomes=True)
    signal_id = insert_signal(path, seed="bad-outcome", frozen_at_ms=1100)
    outcome_id = digest("bad-outcome")
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO outcome_evaluations (
                outcome_identity,
                signal_freeze_identity,
                evidence_class,
                evaluated_as_of_ms,
                resolution_status,
                outcome_state,
                max_holding_bars,
                outcome_json,
                appended_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome_id,
                signal_id,
                "walk_forward",
                2000,
                "resolved",
                "success_tp1",
                4,
                '{"outcome_identity":"broken"}',
                2001,
            ),
        )

    with pytest.raises(DashboardReadError):
        DashboardReader(path).proof_wall(limit=10)
