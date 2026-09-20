from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.confluence.models import ScoreSemantic
from crypto_signal.product.web import create_app
from crypto_signal.signals.models import ProbabilityStatus


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def seed_ledger(path: Path) -> str:
    signal_id = digest("signal")
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
        connection.execute(
            """
            CREATE TABLE outcome_evaluations (
                evidence_class TEXT NOT NULL
            )
            """
        )
        payload = json.dumps(
            {
                "signal_decision": {
                    "state": "watch",
                    "direction": "bullish",
                    "setup_type": "confluence_watch",
                    "agreement": {
                        "confluence_score": "33.33",
                        "score_semantic": (
                            ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY.value
                        ),
                    },
                    "probability_status": ProbabilityStatus.NOT_CALIBRATED.value,
                    "uncertainty_flags": ["partial_methodology_coverage"],
                }
            },
            sort_keys=True,
            separators=(",", ":"),
        )
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
                digest("bundle"),
                signal_id,
                "bybit",
                "spot",
                "BTCUSDT",
                "15m",
                1_000,
                900,
                "watch",
                "bullish",
                payload,
                1_100,
            ),
        )
    return signal_id


def test_health_and_static_shell_without_ledger(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    client = TestClient(create_app(missing))

    health = client.get("/api/health")
    index = client.get("/")

    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "product_version": "dashboard-v1-slice2/1",
        "real_capital": 0,
        "ledger_present": False,
        "read_only": True,
    }
    assert index.status_code == 200
    assert "Mission Control" in index.text
    assert "Confluence ≠ probability" in index.text
    assert not missing.exists()


def test_command_center_json_preserves_truth_labels(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    seed_ledger(path)
    client = TestClient(create_app(path))

    response = client.get("/api/command-center")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["freeze_count"] == 1
    card = body["recent_signals"][0]
    assert card["state"] == "watch"
    assert card["direction"] == "bullish"
    assert card["confluence_score"] == "33.33"
    assert (
        card["confluence_score_semantic"]
        == "agreement_index_not_probability"
    )
    assert card["probability_status"] == "not_calibrated"
    assert card["evidence_class_status"] == "not_explicit_at_freeze_level"


def test_read_only_api_surfaces_share_same_frozen_signal(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    signal_id = seed_ledger(path)
    client = TestClient(create_app(path))

    radar = client.get("/api/market-radar")
    asset = client.get("/api/assets/BTCUSDT/15m")
    archive = client.get("/api/signals?limit=10&offset=0")
    detail = client.get(f"/api/signals/{signal_id}")

    assert radar.status_code == 200
    assert radar.json()["items"][0]["latest"]["signal_freeze_identity"] == signal_id
    assert asset.status_code == 200
    assert asset.json()["latest_by_provider"][0]["signal_freeze_identity"] == signal_id
    assert archive.status_code == 200
    assert archive.json()["signals"][0]["signal_freeze_identity"] == signal_id
    assert detail.status_code == 200
    assert detail.json()["signal"]["signal_freeze_identity"] == signal_id


def test_empty_performance_is_not_zero_win_rate(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    seed_ledger(path)
    client = TestClient(create_app(path))

    response = client.get("/api/performance")

    assert response.status_code == 200
    assert response.json() == {
        "status": "empty",
        "outcome_snapshot_count": 0,
        "evidence_class_counts": [],
    }


def test_api_has_no_post_command_surface(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    seed_ledger(path)
    client = TestClient(create_app(path))

    assert client.post("/api/command-center").status_code == 405
    assert client.post("/api/signals").status_code == 405


def test_invalid_signal_identity_is_rejected_as_bad_request(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    seed_ledger(path)
    client = TestClient(create_app(path))

    response = client.get("/api/signals/not-a-sha")

    assert response.status_code == 400
