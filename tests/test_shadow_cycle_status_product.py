from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from test_shadow_replay_orchestrator import _run

from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.product.web import create_app


def _manifest(tmp_path: Path):
    journal = R25ShadowIntentJournal(
        tmp_path / "status-product.shadow-intent.sqlite3"
    )
    _, cycle = _run(tmp_path, journal)
    path = tmp_path / "status-product.shadow-cycle.sqlite3"
    append = R25ShadowCycleManifest(path).append(cycle)
    return path, cycle, append


def test_shadow_cycle_status_is_read_only_byte_stable_and_truthful(
    tmp_path: Path,
) -> None:
    path, cycle, append = _manifest(tmp_path)
    before = path.read_bytes()
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=path,
        )
    )

    response = client.get("/api/shadow-cycle-manifest/status?limit=10")
    after = path.read_bytes()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["semantic"] == "SHADOW_RESEARCH_ONLY"
    assert body["manifest_filename"] == path.name
    assert body["snapshot"]["record_count"] == 1
    assert body["snapshot"]["quick_check_ok"] is True
    assert body["snapshot"]["read_only_verified"] is True
    assert body["capital_science_lineage"] == "PERSISTED"
    assert body["sizing_lineage"] == "PERSISTED"
    assert body["restart_replay_observation"] == "NOT_PERSISTED"
    assert body["canonical_epoch2_mutation"] is False
    assert body["production_authority"] is False
    assert body["read_only"] is True
    assert body["real_capital"] == 0
    assert len(body["latest"]) == 1

    latest = body["latest"][0]
    assert latest["manifest_identity"] == append.record.manifest_identity
    assert latest["forecast_identity"] == cycle.forecast_identity
    assert latest["proof_identity"] == cycle.proof_identity
    assert latest["capital_bridge_identity"] == cycle.capital.bridge_identity
    assert latest["sizing_bridge_identity"] == cycle.sizing.bridge_identity
    assert latest["preview_identity"] == cycle.preview.preview_identity
    assert latest["journal_record_identity"] == (
        cycle.journal_append.record.record_identity
    )
    assert latest["canonical_epoch2_write_authority"] is False
    assert latest["production_authority"] is False
    assert latest["real_capital"] == 0
    assert after == before
    assert client.post("/api/shadow-cycle-manifest/status").status_code == 405


def test_shadow_cycle_status_unconfigured_creates_nothing(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))

    response = client.get("/api/shadow-cycle-manifest/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "reason": "shadow_cycle_manifest_runtime_not_configured",
        "semantic": "SHADOW_RESEARCH_ONLY",
        "capital_science_lineage": "NOT_PERSISTED",
        "sizing_lineage": "NOT_PERSISTED",
        "restart_replay_observation": "NOT_PERSISTED",
        "canonical_epoch2_mutation": False,
        "production_authority": False,
        "read_only": True,
        "real_capital": 0,
    }
    assert not list(tmp_path.glob("*.shadow-cycle.sqlite3"))


def test_shadow_cycle_status_missing_explicit_path_remains_unavailable(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.shadow-cycle.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=missing,
        )
    )

    response = client.get("/api/shadow-cycle-manifest/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "shadow_cycle_manifest_evidence_missing"
    assert body["manifest_filename"] == missing.name
    assert body["capital_science_lineage"] == "NOT_PERSISTED"
    assert body["sizing_lineage"] == "NOT_PERSISTED"
    assert body["restart_replay_observation"] == "NOT_PERSISTED"
    assert body["canonical_epoch2_mutation"] is False
    assert body["real_capital"] == 0
    assert not missing.exists()


def test_shadow_cycle_status_fails_closed_on_wrong_database(
    tmp_path: Path,
) -> None:
    wrong = tmp_path / "wrong.shadow-cycle.sqlite3"
    with sqlite3.connect(wrong) as db:
        db.execute("CREATE TABLE canonical_epoch2_accounting (id TEXT)")

    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=wrong,
        )
    )
    response = client.get("/api/shadow-cycle-manifest/status")

    assert response.status_code == 500
    assert "non-shadow tables" in response.json()["detail"]


def test_galactech_adds_manifest_status_without_replacing_exact_forecast_link(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))

    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")

    assert preview.status_code == 200
    assert script.status_code == 200

    html = preview.text
    js = script.text

    assert 'id="systemShadowCycle"' in html
    assert 'id="systemShadowCycleNote"' in html
    assert "SHADOW CYCLE MANIFEST" in html
    assert "runtime replay observation separate" in html

    assert (
        'shadowCycleStatus: "/api/shadow-cycle-manifest/status?limit=20"'
        in js
    )
    assert "const cycleData = state.shadowCycleStatus || {};" in js
    assert "Capital Science lineage" in js
    assert "Sizing lineage" in js
    assert "Restart/replay observation" in js
    assert "NOT PERSISTED" in js
    assert "does not prove a deployed restart/replay observation" in js
    assert 'loadEndpoint("shadowCycleStatus", API.shadowCycleStatus)' in js

    # Existing exact forecast -> cycle drill-down must remain intact.
    assert "shadowForecastCycle: (identity) =>" in js
    assert "/api/shadow-decision-rail/forecast/" in js
    assert "function renderShadowCycleExtension(payload)" in js
    assert "R25 CAPITAL DECISION LINEAGE" in js

    # Existing no-live-trade truth contract must remain intact.
    assert "not a fill, not canonical NAV mutation, not live trading" in js
