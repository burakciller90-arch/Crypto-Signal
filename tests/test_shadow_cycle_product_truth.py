from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from test_shadow_cycle_runtime import _kwargs

from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_cycle_runtime import run_persisted_shadow_cycle
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.product.web import create_app


def _runtime_cycle(tmp_path: Path) -> tuple[Path, Path, object]:
    journal_path = tmp_path / "product.shadow-intent.sqlite3"
    manifest_path = tmp_path / "product.shadow-cycle.sqlite3"
    issuance, kwargs = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(journal_path),
    )
    result = run_persisted_shadow_cycle(
        issuance,
        manifest=R25ShadowCycleManifest(manifest_path),
        **kwargs,
    )
    return journal_path, manifest_path, result


def test_shadow_cycle_status_unconfigured_is_explicit_and_creates_nothing(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))

    response = client.get("/api/shadow-cycle/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "reason": "shadow_cycle_manifest_runtime_not_configured",
        "semantic": "SHADOW_RESEARCH_ONLY",
        "restart_replay_runtime_status": "NOT_MEASURED",
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

    response = client.get("/api/shadow-cycle/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "shadow_cycle_manifest_evidence_missing"
    assert body["manifest_filename"] == missing.name
    assert body["restart_replay_runtime_status"] == "NOT_MEASURED"
    assert body["canonical_epoch2_mutation"] is False
    assert body["production_authority"] is False
    assert body["real_capital"] == 0
    assert not missing.exists()


def test_shadow_cycle_status_exposes_exact_manifest_lineage_without_mutation(
    tmp_path: Path,
) -> None:
    journal_path, manifest_path, result = _runtime_cycle(tmp_path)
    manifest_before = manifest_path.read_bytes()
    journal_before = journal_path.read_bytes()
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_intent_journal_path=journal_path,
            shadow_cycle_manifest_path=manifest_path,
        )
    )

    response = client.get("/api/shadow-cycle/status?limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["semantic"] == "SHADOW_RESEARCH_ONLY"
    assert body["lineage_status"] == "PERSISTED_BY_IMMUTABLE_MANIFEST"
    assert body["restart_replay_runtime_status"] == "NOT_MEASURED"
    assert body["canonical_epoch2_mutation"] is False
    assert body["production_authority"] is False
    assert body["read_only"] is True
    assert body["real_capital"] == 0
    assert body["snapshot"]["record_count"] == 1
    assert body["snapshot"]["quick_check_ok"] is True
    assert body["snapshot"]["read_only_verified"] is True

    latest = body["latest"]
    assert len(latest) == 1
    record = latest[0]
    assert record["manifest_identity"] == (
        result.manifest_append.record.manifest_identity
    )
    assert record["cycle_identity"] == result.cycle.cycle_identity
    assert record["forecast_identity"] == result.cycle.forecast_identity
    assert record["proof_identity"] == result.cycle.proof_identity
    assert record["capital_bridge_identity"] == (
        result.cycle.capital.bridge_identity
    )
    assert record["sizing_bridge_identity"] == (
        result.cycle.sizing.bridge_identity
    )
    assert record["review_selection_identity"] == (
        result.cycle.reviewed_selection.selection_identity
    )
    assert record["preview_identity"] == result.cycle.preview.preview_identity
    assert record["journal_record_identity"] == (
        result.cycle.journal_append.record.record_identity
    )
    assert record["canonical_epoch2_write_authority"] is False
    assert record["production_authority"] is False
    assert record["real_capital"] == 0

    assert manifest_path.read_bytes() == manifest_before
    assert journal_path.read_bytes() == journal_before


def test_shadow_cycle_status_fails_closed_on_non_manifest_database(
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
    response = client.get("/api/shadow-cycle/status")

    assert response.status_code == 500
    assert "non-shadow tables" in response.json()["detail"]


def test_galactech_distinguishes_integrity_from_runtime_restart_replay(
    tmp_path: Path,
) -> None:
    journal_path, manifest_path, _ = _runtime_cycle(tmp_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_intent_journal_path=journal_path,
            shadow_cycle_manifest_path=manifest_path,
        )
    )

    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")

    assert preview.status_code == 200
    assert script.status_code == 200
    js = script.text
    assert 'shadowCycle: "/api/shadow-cycle/status?limit=20"' in js
    assert 'loadEndpoint("shadowCycle", API.shadowCycle)' in js
    assert "Immutable runtime lineage" in js
    assert "Capital Science" in js
    assert "Position Sizing" in js
    assert "Cycle Manifest" in js
    assert "JOURNAL INTEGRITY" not in js
    assert "INTEGRITY VERIFIED" in js
    assert "Restart / replay runtime" in js
    assert "NOT MEASURED" in js
    assert "REPLAY · VERIFIED" not in js
    assert "read-only replay verified" not in js
