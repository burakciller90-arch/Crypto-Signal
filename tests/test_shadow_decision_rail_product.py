from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from test_shadow_intent_journal import _buy_preview

from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.product.web import create_app


def _journal(tmp_path: Path) -> Path:
    path = tmp_path / "product.shadow-intent.sqlite3"
    _, _, preview = _buy_preview(tmp_path)
    R25ShadowIntentJournal(path).append(preview)
    return path


def test_shadow_decision_rail_endpoint_is_read_only_and_truthful(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    before_status = R25ShadowIntentJournal(journal).verify_read_only()
    with sqlite3.connect(f"{journal.resolve().as_uri()}?mode=ro", uri=True) as db:
        before_rows = db.execute(
            """SELECT record_identity, preview_identity, vault_id, event_at_ms,
            previous_record_identity, payload_json
            FROM r25_shadow_intent_records
            ORDER BY vault_id, event_at_ms, record_identity"""
        ).fetchall()
        before_tables = db.execute(
            """SELECT name, sql FROM sqlite_master
            WHERE type IN ('table', 'trigger') ORDER BY name"""
        ).fetchall()
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_intent_journal_path=journal,
        )
    )

    health = client.get("/api/health")
    response = client.get("/api/shadow-decision-rail/status")

    assert health.status_code == 200
    assert "shadow_intent_journal_present" not in health.json()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["semantic"] == "SHADOW_RESEARCH_ONLY"
    assert body["snapshot"]["record_count"] == 1
    assert body["snapshot"]["quick_check_ok"] is True
    assert body["snapshot"]["read_only_verified"] is True
    assert body["snapshot"]["canonical_epoch2_write_authority"] is False
    assert body["canonical_epoch2_mutation"] is False
    assert body["production_authority"] is False
    assert body["read_only"] is True
    assert body["real_capital"] == 0

    after_status = R25ShadowIntentJournal(journal).verify_read_only()
    with sqlite3.connect(f"{journal.resolve().as_uri()}?mode=ro", uri=True) as db:
        after_rows = db.execute(
            """SELECT record_identity, preview_identity, vault_id, event_at_ms,
            previous_record_identity, payload_json
            FROM r25_shadow_intent_records
            ORDER BY vault_id, event_at_ms, record_identity"""
        ).fetchall()
        after_tables = db.execute(
            """SELECT name, sql FROM sqlite_master
            WHERE type IN ('table', 'trigger') ORDER BY name"""
        ).fetchall()
    assert after_status == before_status
    assert after_rows == before_rows
    assert after_tables == before_tables


def test_shadow_decision_rail_unconfigured_does_not_create_runtime_file(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))

    response = client.get("/api/shadow-decision-rail/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "reason": "shadow_intent_journal_runtime_not_configured",
        "semantic": "SHADOW_RESEARCH_ONLY",
        "canonical_epoch2_mutation": False,
        "production_authority": False,
        "read_only": True,
        "real_capital": 0,
    }
    assert not list(tmp_path.glob("*.shadow-intent.sqlite3"))


def test_shadow_decision_rail_missing_explicit_path_remains_unavailable(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.shadow-intent.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_intent_journal_path=missing,
        )
    )

    response = client.get("/api/shadow-decision-rail/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "shadow_intent_journal_evidence_missing"
    assert body["journal_filename"] == missing.name
    assert body["canonical_epoch2_mutation"] is False
    assert body["real_capital"] == 0
    assert not missing.exists()


def test_shadow_decision_rail_fails_closed_on_non_shadow_database(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wrong.shadow-intent.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE canonical_epoch2_accounting (id TEXT)")
    with sqlite3.connect(path) as db:
        before_tables = db.execute(
            """SELECT name, sql FROM sqlite_master
            WHERE type = 'table' ORDER BY name"""
        ).fetchall()
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_intent_journal_path=path,
        )
    )

    response = client.get("/api/shadow-decision-rail/status")

    assert response.status_code == 500
    assert "non-shadow tables" in response.json()["detail"]
    with sqlite3.connect(path) as db:
        after_tables = db.execute(
            """SELECT name, sql FROM sqlite_master
            WHERE type = 'table' ORDER BY name"""
        ).fetchall()
    assert after_tables == before_tables


def test_galactech_exposes_shadow_rail_without_live_trade_claims(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_intent_journal_path=journal,
        )
    )

    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")

    assert preview.status_code == 200
    assert script.status_code == 200
    html = preview.text
    js = script.text

    assert 'id="shadowRailOverview"' in html
    assert 'id="systemShadowRail"' in html
    assert 'id="systemShadowRailNote"' in html
    assert "SHADOW DECISION RAIL" in html
    assert "no canonical writes" in html

    assert 'shadowRail: "/api/shadow-decision-rail/status"' in js
    assert "function renderShadowDecisionRail()" in js
    assert 'loadEndpoint("shadowRail", API.shadowRail)' in js
    assert '"systemShadowRail"' in js
    assert "SHADOW / RESEARCH ONLY" in js
    assert "CANONICAL EPOCH 2 mutation" not in js
    assert "Canonical Epoch 2 mutation" in js
    assert "not a fill, not canonical NAV mutation, not live trading" in js
