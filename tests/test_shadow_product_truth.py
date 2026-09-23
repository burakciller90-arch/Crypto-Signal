from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from test_dashboard_web import seed_ledger
from test_r22_intent_preview import (
    _activation,
    _fixed_selection,
    _market_reference,
    _sizing,
)

from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.r22_intent_preview import build_r22_intent_preview
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.product.web import create_app


def _persist_reviewed_preview(tmp_path: Path) -> Path:
    issuance, sizing = _sizing(tmp_path)
    _, selection = _fixed_selection(sizing)
    preview = build_r22_intent_preview(
        issuance,
        sizing,
        _activation(),
        vault_id=PaperVaultId.CORE,
        previewed_at_ms=sizing.sized_at_ms + 2,
        reviewed_selection=selection,
        market_reference=_market_reference(issuance),
        quantity=Decimal("0.10"),
        reason_codes=("r25_slice11_product_truth",),
    )
    path = tmp_path / "product.shadow-intent.sqlite3"
    R25ShadowIntentJournal(path).append(preview)
    return path


def test_shadow_decision_api_missing_runtime_stays_explicit_and_creates_nothing(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "signals.sqlite3"
    seed_ledger(signal_path)
    missing = tmp_path / "missing.shadow-intent.sqlite3"
    client = TestClient(
        create_app(
            signal_path,
            shadow_intent_journal_path=missing,
        )
    )

    response = client.get("/api/shadow-decision/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "reason": "shadow_intent_runtime_not_configured",
        "journal_integrity_status": "NOT_PERSISTED",
        "restart_replay_runtime_status": "NOT_MEASURED",
        "capital_science_runtime_status": "NOT_PERSISTED",
        "canonical_epoch2_mutation": "NOT_AUTHORIZED",
        "latest": [],
        "read_only": True,
        "real_capital": 0,
    }
    assert client.post("/api/shadow-decision/status").status_code == 405
    assert not missing.exists()


def test_shadow_decision_api_exposes_only_verified_persisted_runtime_truth(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "signals.sqlite3"
    seed_ledger(signal_path)
    journal_path = _persist_reviewed_preview(tmp_path)
    before = journal_path.read_bytes()

    client = TestClient(
        create_app(
            signal_path,
            shadow_intent_journal_path=journal_path,
        )
    )
    response = client.get("/api/shadow-decision/status?limit=10")
    after = journal_path.read_bytes()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["journal"]["record_count"] == 1
    assert body["journal"]["quick_check_ok"] is True
    assert body["journal"]["read_only_verified"] is True
    assert body["journal_integrity_status"] == "VERIFIED"
    assert body["sizing_lineage_status"] == "REFERENCED_BY_PREVIEW"
    assert body["reviewed_preview_status"] == "1_REVIEWED"
    assert body["restart_replay_runtime_status"] == "NOT_MEASURED"
    assert body["capital_science_runtime_status"] == "NOT_PERSISTED"
    assert body["canonical_epoch2_mutation"] == "NOT_AUTHORIZED"
    assert body["read_only"] is True
    assert body["real_capital"] == 0

    latest = body["latest"]
    assert len(latest) == 1
    assert latest[0]["vault_id"] == "CORE"
    assert latest[0]["action"] == "BUY"
    assert latest[0]["review_selection_identity"]
    assert latest[0]["market_reference_identity"]
    assert latest[0]["sizing_bridge_identity"]
    assert latest[0]["integrity_verified"] is True
    assert latest[0]["canonical_epoch2_write_authority"] is False
    assert latest[0]["production_authority"] is False
    assert latest[0]["real_capital"] == 0
    assert after == before


def test_shadow_decision_api_fails_closed_on_wrong_database_shape(
    tmp_path: Path,
) -> None:
    import sqlite3

    signal_path = tmp_path / "signals.sqlite3"
    seed_ledger(signal_path)
    wrong = tmp_path / "wrong.shadow-intent.sqlite3"
    with sqlite3.connect(wrong) as db:
        db.execute("CREATE TABLE canonical_epoch2_accounting (id TEXT)")

    client = TestClient(
        create_app(
            signal_path,
            shadow_intent_journal_path=wrong,
        )
    )
    response = client.get("/api/shadow-decision/status")

    assert response.status_code == 500
    assert "non-shadow tables" in response.json()["detail"]


def test_galactech_system_truth_names_shadow_runtime_without_overclaiming(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "signals.sqlite3"
    seed_ledger(signal_path)
    client = TestClient(create_app(signal_path))

    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")

    assert preview.status_code == 200
    assert script.status_code == 200

    html = preview.text
    js = script.text

    assert 'id="systemShadowJournal"' in html
    assert 'id="systemShadowPreview"' in html
    assert 'id="systemShadowReplay"' in html
    assert 'id="shadowDecisionRail"' in html
    assert "R25 / SHADOW DECISION RAIL" in html
    assert "NO CANONICAL MUTATION" in html
    assert "CI acceptance" in html

    assert 'shadowDecision: "/api/shadow-decision/status?limit=20"' in js
    assert "const shadowDecision = state.shadowDecision || {};" in js
    assert '"systemShadowJournal"' in js
    assert '"systemShadowPreview"' in js
    assert '"systemShadowReplay"' in js
    assert '"CAPITAL SCIENCE"' in js
    assert '"SIZING LINEAGE"' in js
    assert '"RESTART / REPLAY"' in js
    assert '"CANONICAL EPOCH 2"' in js
    assert '"NOT MEASURED"' in js
    assert '"NOT PERSISTED"' in js
    assert '"NOT AUTHORIZED"' in js
