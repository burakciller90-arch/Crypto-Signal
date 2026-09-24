from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from test_epoch2_accounting import _activate
from test_runtime_replay_observation import _observation

from crypto_signal.paper.epochs import EPOCH_2_SPEC
from crypto_signal.paper.runtime_replay_observation import (
    R25RuntimeReplayObservationLedger,
)
from crypto_signal.product.web import create_app


def _full_runtime(tmp_path: Path):
    first, _, observation = _observation(tmp_path)
    replay_path = tmp_path / "operational.shadow-replay.sqlite3"
    R25RuntimeReplayObservationLedger(replay_path).append(observation)
    _activate(tmp_path)

    paths = {
        "decision": tmp_path / "decision.sqlite3",
        "journal": tmp_path / "runtime.shadow-intent.sqlite3",
        "manifest": tmp_path / "runtime.shadow-cycle.sqlite3",
        "replay": replay_path,
        "epoch2": tmp_path / EPOCH_2_SPEC.ledger_filename,
    }
    assert all(path.exists() for path in paths.values())
    return first, observation, paths


def test_operational_truth_reconciles_each_runtime_source_without_score(
    tmp_path: Path,
) -> None:
    _, observation, paths = _full_runtime(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}

    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            decision_evidence_path=paths["decision"],
            shadow_intent_journal_path=paths["journal"],
            shadow_cycle_manifest_path=paths["manifest"],
            runtime_replay_observation_path=paths["replay"],
            epoch2_ledger_path=paths["epoch2"],
        )
    )
    response = client.get("/api/r25/operational-truth")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["all_required_runtime_evidence_present"] is True
    assert body["canonical_epoch2_mutation_authorized"] is False
    assert body["production_authority"] is False
    assert body["read_only"] is True
    assert body["real_capital"] == 0

    components = body["components"]
    assert components["decision_evidence"]["status"] == "ready"
    assert components["decision_evidence"]["snapshot"]["forecast_count"] >= 1
    assert components["decision_evidence"]["snapshot"]["proof_count"] >= 1
    assert components["shadow_intent_journal"]["status"] == "ready"
    assert (
        components["shadow_intent_journal"]["snapshot"]["read_only_verified"]
        is True
    )
    assert components["shadow_cycle_manifest"]["status"] == "ready"
    assert (
        components["shadow_cycle_manifest"]["snapshot"]["read_only_verified"]
        is True
    )
    assert components["runtime_replay_observation"]["status"] == "ready"
    assert (
        components["runtime_replay_observation"]["snapshot"][
            "latest_observation_identity"
        ]
        == observation.observation_identity
    )
    assert components["canonical_epoch2"]["status"] == "ready"
    assert components["canonical_epoch2"]["nav_usdt"] == "1000.00"
    assert components["galactech_product"] == {
        "status": "exposed",
        "route": "/galactech",
        "read_only_product_api": True,
    }

    after = {name: path.read_bytes() for name, path in paths.items()}
    assert after == before
    assert client.post("/api/r25/operational-truth").status_code == 405


def test_operational_truth_missing_sources_stay_explicit_and_create_nothing(
    tmp_path: Path,
) -> None:
    paths = {
        "decision": tmp_path / "missing-decision.sqlite3",
        "journal": tmp_path / "missing.shadow-intent.sqlite3",
        "manifest": tmp_path / "missing.shadow-cycle.sqlite3",
        "replay": tmp_path / "missing.shadow-replay.sqlite3",
        "epoch2": tmp_path / "missing-epoch2.sqlite3",
    }
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            decision_evidence_path=paths["decision"],
            shadow_intent_journal_path=paths["journal"],
            shadow_cycle_manifest_path=paths["manifest"],
            runtime_replay_observation_path=paths["replay"],
            epoch2_ledger_path=paths["epoch2"],
        )
    )

    response = client.get("/api/r25/operational-truth")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["all_required_runtime_evidence_present"] is False
    components = body["components"]
    assert components["decision_evidence"] == {
        "status": "unavailable",
        "reason": "decision_evidence_runtime_evidence_missing",
    }
    assert components["shadow_intent_journal"] == {
        "status": "unavailable",
        "reason": "shadow_intent_journal_evidence_missing",
    }
    assert components["shadow_cycle_manifest"] == {
        "status": "unavailable",
        "reason": "shadow_cycle_manifest_evidence_missing",
    }
    assert components["runtime_replay_observation"] == {
        "status": "unavailable",
        "reason": "runtime_replay_observation_evidence_missing",
    }
    assert components["canonical_epoch2"] == {
        "status": "unavailable",
        "reason": "epoch2_runtime_evidence_missing",
    }
    assert components["galactech_product"]["status"] == "exposed"
    assert not any(path.exists() for path in paths.values())


def test_operational_truth_unconfigured_sources_are_not_promoted(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
        )
    )

    body = client.get("/api/r25/operational-truth").json()

    assert body["all_required_runtime_evidence_present"] is False
    assert body["components"]["shadow_intent_journal"]["reason"] == (
        "shadow_intent_journal_runtime_not_configured"
    )
    assert body["components"]["shadow_cycle_manifest"]["reason"] == (
        "shadow_cycle_manifest_runtime_not_configured"
    )
    assert body["components"]["runtime_replay_observation"]["reason"] == (
        "runtime_replay_observation_not_configured"
    )


def test_operational_truth_fails_closed_on_wrong_shadow_database_shape(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "bad.shadow-cycle.sqlite3"
    with sqlite3.connect(bad) as db:
        db.execute("CREATE TABLE canonical_epoch2_accounting (id TEXT)")

    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=bad,
        )
    )
    response = client.get("/api/r25/operational-truth")

    assert response.status_code == 500
    assert "non-shadow tables" in response.json()["detail"]


def test_galactech_system_truth_exposes_component_states_not_a_readiness_score(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))
    html = client.get("/galactech")
    script = client.get("/galactech-static/app.js")

    assert html.status_code == 200
    assert script.status_code == 200

    markup = html.text
    js = script.text
    assert 'id="r25OperationalTruthGrid"' in markup
    assert 'id="r25OperationalTruthTag"' in markup
    assert "R25 / OPERATIONAL TRUTH" in markup
    assert "Runtime evidence reconciliation" in markup
    assert "production readiness değildir" in markup

    assert 'operationalTruth: "/api/r25/operational-truth"' in js
    assert "function renderOperationalTruth()" in js
    assert "DECISION EVIDENCE" in js
    assert "SHADOW INTENT JOURNAL" in js
    assert "SHADOW CYCLE MANIFEST" in js
    assert "RUNTIME REPLAY OBSERVATION" in js
    assert "CANONICAL EPOCH 2" in js
    assert "GALACTECH PRODUCT" in js
    assert "ALL REQUIRED RUNTIME EVIDENCE PRESENT" in js
    assert "PARTIAL RUNTIME EVIDENCE" in js
    assert "PRODUCTION READY" not in markup
    assert "PRODUCTION READY" not in js


def test_operational_truth_delegates_expensive_market_tape_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    market_tape = tmp_path / "market_tape.sqlite3"
    with sqlite3.connect(market_tape) as db:
        db.execute("CREATE TABLE marker (value TEXT)")

    def fail_if_full_market_tape_verification_runs(*args, **kwargs):
        raise ValueError("full_market_tape_verification_called")

    monkeypatch.setattr(
        "crypto_signal.product.web.read_market_tape_runtime_truth",
        fail_if_full_market_tape_verification_runs,
    )
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            market_tape_path=market_tape,
        )
    )

    operational = client.get("/api/r25/operational-truth")
    assert operational.status_code == 200
    component = operational.json()["components"]["market_tape_runtime"]
    assert component == {
        "status": "delegated",
        "reason": (
            "detailed_market_tape_verification_delegated_to_dedicated_endpoint"
        ),
        "verification_endpoint": "/api/market-tape-runtime/status",
        "runtime_evidence_present": True,
        "online_status": "NOT_ASSERTED",
        "read_only": True,
    }

    detailed = client.get(
        "/api/market-tape-runtime/status?observed_at_ms=2000"
    )
    assert detailed.status_code == 500
    assert detailed.json()["detail"] == "full_market_tape_verification_called"
