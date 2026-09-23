from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_decision_ledger import _forecast, _proof

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.product.decision_proof import build_live_intelligence_feed_event
from crypto_signal.product.web import create_app


def _seed_decision_evidence(path: Path):
    forecast = _forecast()
    proof = _proof(forecast)
    event = build_live_intelligence_feed_event(proof, forecast)
    ledger = ImmutableDecisionEvidenceLedger(path)
    ledger.append_forecast(forecast)
    ledger.append_proof(proof)
    ledger.append_feed_event(event)
    return forecast, proof, event


def test_product_exposes_persisted_decision_proof_and_feed_read_only(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "missing-signals.sqlite3"
    decision_path = tmp_path / "decision-evidence.sqlite3"
    forecast, proof, event = _seed_decision_evidence(decision_path)
    before = decision_path.read_bytes()

    client = TestClient(
        create_app(
            signal_path,
            decision_evidence_path=decision_path,
        )
    )

    health = client.get("/api/health")
    status = client.get("/api/decision-evidence/status")
    detail = client.get(f"/api/decision-proof/{forecast.signal_freeze_identity}")
    feed = client.get("/api/intelligence-feed?limit=20")

    assert health.status_code == 200
    assert health.json()["decision_evidence_present"] is True
    assert health.json()["read_only"] is True
    assert health.json()["real_capital"] == 0

    assert status.status_code == 200
    status_body = status.json()
    assert status_body["status"] == "ready"
    assert status_body["snapshot"]["forecast_count"] == 1
    assert status_body["snapshot"]["proof_count"] == 1
    assert status_body["snapshot"]["resolution_count"] == 0
    assert status_body["snapshot"]["feed_event_count"] == 1
    assert status_body["read_only"] is True
    assert status_body["real_capital"] == 0

    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["status"] == "ready"
    assert detail_body["proof"]["proof_identity"] == proof.proof_identity
    assert detail_body["proof"]["forecast_identity"] == forecast.forecast_identity
    assert detail_body["proof"]["signal_freeze_identity"] == (
        forecast.signal_freeze_identity
    )
    assert detail_body["proof"]["probability_status"] == "not_calibrated"
    assert detail_body["proof"]["production_authority"] is False
    assert detail_body["read_only"] is True
    assert detail_body["real_capital"] == 0

    assert feed.status_code == 200
    feed_body = feed.json()
    assert feed_body["status"] == "ready"
    assert len(feed_body["events"]) == 1
    assert feed_body["events"][0]["event_identity"] == event.event_identity
    assert feed_body["events"][0]["proof_identity"] == proof.proof_identity
    assert feed_body["events"][0]["production_authority"] is False
    assert feed_body["read_only"] is True
    assert feed_body["real_capital"] == 0

    assert client.post("/api/intelligence-feed").status_code == 405
    assert client.post(
        f"/api/decision-proof/{forecast.signal_freeze_identity}"
    ).status_code == 405
    assert decision_path.read_bytes() == before
    assert not signal_path.exists()


def test_product_decision_evidence_missing_runtime_fails_closed(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "missing-signals.sqlite3"
    decision_path = tmp_path / "missing-decision-evidence.sqlite3"
    client = TestClient(
        create_app(
            signal_path,
            decision_evidence_path=decision_path,
        )
    )

    identity = "f" * 64
    detail = client.get(f"/api/decision-proof/{identity}")
    feed = client.get("/api/intelligence-feed")
    status = client.get("/api/decision-evidence/status")

    assert detail.json() == {
        "status": "unavailable",
        "reason": "decision_evidence_runtime_not_configured",
        "read_only": True,
        "real_capital": 0,
    }
    assert feed.json() == {
        "status": "unavailable",
        "reason": "decision_evidence_runtime_not_configured",
        "events": [],
        "read_only": True,
        "real_capital": 0,
    }
    assert status.json() == {
        "status": "unavailable",
        "reason": "decision_evidence_runtime_not_configured",
        "read_only": True,
        "real_capital": 0,
    }
    assert not decision_path.exists()
    assert not signal_path.exists()


def test_galactech_binds_only_persisted_r20_5_evidence_domains(
    tmp_path: Path,
) -> None:
    decision_path = tmp_path / "decision-evidence.sqlite3"
    _seed_decision_evidence(decision_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            decision_evidence_path=decision_path,
        )
    )

    html = client.get("/galactech").text
    js = client.get("/galactech-static/app.js").text

    assert 'id="systemDecisionLedger"' in html
    assert 'id="systemLiveFeed"' in html
    assert "DECISION PROOF LEDGER" in html
    assert "LIVE INTELLIGENCE FEED" in html
    assert "Persisted R20/R20.5 Decision Proof" in html

    assert 'decisionProof: (identity)' in js
    assert 'decisionStatus: "/api/decision-evidence/status"' in js
    assert 'liveFeed: "/api/intelligence-feed?limit=100"' in js
    assert "function renderDecisionProofExtension(payload)" in js
    assert "async function loadSelectedDecisionProof" in js
    assert 'LIQ: ["liquidity_map", "liquidation_map"]' in js
    assert 'FLOW: ["order_book", "order_flow_cvd"]' in js
    assert 'DERIV: ["derivatives"]' in js
    assert 'ONCHAIN: ["onchain"]' in js
    assert "No exact R20.5 Decision Proof is persisted" in js
    assert "does not synthesize a layer from unrelated evidence" in js
    assert "private reasoning" in js.lower()
