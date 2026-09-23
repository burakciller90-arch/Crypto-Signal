from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from test_dashboard_web import digest, seed_ledger

from crypto_signal.product.web import create_app


def _append_success_outcome(path: Path, signal_id: str) -> str:
    outcome_id = digest("archive-success-outcome")
    payload = {
        "outcome_identity": outcome_id,
        "signal_freeze_identity": signal_id,
        "evidence_class": "live_untouched_forward",
        "evaluated_as_of_ms": 2_000,
        "resolution_status": "resolved",
        "outcome_state": "success_tp2",
        "signal_initial_state": "watch",
        "coverage_status": "complete",
        "max_holding_bars": 4,
        "expected_bar_count": 4,
        "observed_bar_count": 4,
        "missing_open_times_ms": [],
        "skipped_partial_decision_bucket": False,
        "entry_observed": True,
        "entry_candle_identity": ["bybit", "spot", "BTCUSDT", "15m", 1_200],
        "highest_target_index": 2,
        "outcome_candle_identity": ["bybit", "spot", "BTCUSDT", "15m", 1_800],
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
                "live_untouched_forward",
                2_000,
                "resolved",
                "success_tp2",
                4,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                2_100,
            ),
        )
    return outcome_id


def test_galactech_archive_pairs_immutable_issuance_with_later_outcome(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "signals.sqlite3"
    signal_id = seed_ledger(ledger)
    outcome_id = _append_success_outcome(ledger, signal_id)
    client = TestClient(create_app(ledger))

    proof = client.get("/api/archive/proof-wall?limit=500&offset=0")
    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")
    style = client.get("/galactech-static/app.css")

    assert proof.status_code == 200
    assert preview.status_code == 200
    assert script.status_code == 200
    assert style.status_code == 200

    body = proof.json()
    assert body["status"] == "ready"
    assert body["total_count"] == 1
    assert body["outcome_schema_available"] is True
    assert len(body["items"]) == 1

    item = body["items"][0]
    assert item["signal"]["signal_freeze_identity"] == signal_id
    assert item["latest_outcome"]["outcome_identity"] == outcome_id
    assert item["latest_outcome"]["evidence_class"] == "live_untouched_forward"
    assert item["latest_outcome"]["resolution_status"] == "resolved"
    assert item["latest_outcome"]["outcome_state"] == "success_tp2"
    assert item["latest_outcome"]["coverage_status"] == "complete"
    assert item["latest_outcome"]["highest_target_index"] == 2

    html = preview.text
    js = script.text
    css = style.text

    assert 'data-ui-version="galactech-v1.1-archive"' in html
    assert 'id="archiveSummary"' in html
    assert 'id="archiveSchemaTag"' in html
    assert "ISSUANCE SNAPSHOT ↔ LATER OUTCOME SNAPSHOT" in html
    assert 'data-filter="winner"' in html
    assert 'data-filter="loser"' in html
    assert 'data-filter="unresolved"' in html

    assert 'archive: "/api/archive/proof-wall?limit=500&offset=0"' in js
    assert "function proofCategory(item)" in js
    assert "function archiveCategoryLabel(category)" in js
    assert "function archiveCategoryClass(category)" in js
    assert "function archiveReason(outcome)" in js
    assert "function updateArchiveSummary(allRows, visibleRows)" in js
    assert "function archiveItemMarkup(item)" in js
    assert "function renderArchive()" in js
    assert 'outcomeState.startsWith("success_tp")' in js
    assert 'outcomeState === "fail_sl"' in js
    assert 'outcomeState === "timeout"' in js
    assert 'outcomeState === "invalidated"' in js
    assert 'outcomeState === "ambiguous"' in js
    assert 'outcomeState === "not_evaluable"' in js
    assert "Missing outcome is not rewritten as failure, success or 0% performance." in js
    assert "Freeze stays immutable after outcome." in js
    assert "not probability" in js

    assert ".archive-summary-grid" in css
    assert ".archive-snapshot-pair" in css
    assert ".archive-snapshot-issuance" in css
    assert ".archive-snapshot-outcome" in css
    assert ".archive-status-winner" in css
    assert ".archive-status-risk" in css
    assert ".archive-status-caution" in css

    assert client.post("/api/archive/proof-wall").status_code == 405


def test_galactech_archive_preserves_unresolved_issuance(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "signals.sqlite3"
    signal_id = seed_ledger(ledger)
    client = TestClient(create_app(ledger))

    proof = client.get("/api/archive/proof-wall?limit=500&offset=0")
    script = client.get("/galactech-static/app.js")

    assert proof.status_code == 200
    item = proof.json()["items"][0]
    assert item["signal"]["signal_freeze_identity"] == signal_id
    assert item["latest_outcome"] is None

    js = script.text
    assert 'if (!outcome) {' in js
    assert 'return "unresolved";' in js
    assert "NO LATER OUTCOME YET" in js
    assert "unresolved ≠ failure" in client.get("/galactech").text
