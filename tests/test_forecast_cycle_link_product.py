from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_shadow_replay_orchestrator import _run

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.product.web import create_app


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _manifest_with_cycle(tmp_path: Path):
    intent_path = tmp_path / "forecast-cycle.shadow-intent.sqlite3"
    _, cycle = _run(
        tmp_path,
        R25ShadowIntentJournal(intent_path),
    )
    manifest_path = tmp_path / "forecast-cycle.shadow-cycle.sqlite3"
    manifest = R25ShadowCycleManifest(manifest_path)
    append = manifest.append(cycle)
    return manifest_path, cycle, append


def test_manifest_exact_forecast_lookup_returns_full_cycle_lineage(
    tmp_path: Path,
) -> None:
    path, cycle, append = _manifest_with_cycle(tmp_path)

    record = R25ShadowCycleManifest(path).read_latest_for_forecast(
        cycle.forecast_identity
    )

    assert record is not None
    assert record == append.record
    assert record.cycle_identity == cycle.cycle_identity
    assert record.forecast_identity == cycle.forecast_identity
    assert record.proof_identity == cycle.proof_identity
    assert record.capital_bridge_identity == cycle.capital.bridge_identity
    assert record.sizing_bridge_identity == cycle.sizing.bridge_identity
    assert record.review_selection_identity == (
        cycle.reviewed_selection.selection_identity
    )
    assert record.preview_identity == cycle.preview.preview_identity
    assert record.journal_record_identity == (
        cycle.journal_append.record.record_identity
    )


def test_manifest_forecast_lookup_never_matches_unrelated_identity(
    tmp_path: Path,
) -> None:
    path, _, _ = _manifest_with_cycle(tmp_path)

    assert (
        R25ShadowCycleManifest(path).read_latest_for_forecast(
            _sha("unrelated-forecast")
        )
        is None
    )


def test_manifest_forecast_lookup_rejects_non_sha(tmp_path: Path) -> None:
    path, _, _ = _manifest_with_cycle(tmp_path)
    with pytest.raises(ValueError, match="must be SHA256"):
        R25ShadowCycleManifest(path).read_latest_for_forecast("BTCUSDT")


def test_product_exact_forecast_cycle_endpoint_is_read_only_and_byte_stable(
    tmp_path: Path,
) -> None:
    path, cycle, append = _manifest_with_cycle(tmp_path)
    before = path.read_bytes()
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=path,
        )
    )

    response = client.get(
        "/api/shadow-decision-rail/forecast/"
        f"{cycle.forecast_identity}"
    )
    after = path.read_bytes()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["semantic"] == "EXACT_PERSISTED_CYCLE_IDENTITY_ONLY"
    assert body["forecast_identity"] == cycle.forecast_identity
    assert body["cycle"]["manifest_identity"] == (
        append.record.manifest_identity
    )
    assert body["cycle"]["capital_bridge_identity"] == (
        cycle.capital.bridge_identity
    )
    assert body["cycle"]["sizing_bridge_identity"] == (
        cycle.sizing.bridge_identity
    )
    assert body["cycle"]["preview_identity"] == cycle.preview.preview_identity
    assert body["explicit_review_present"] is True
    assert body["journal_record_referenced"] is True
    assert body["journal_runtime_verified_here"] is False
    assert body["canonical_epoch2_mutation"] is False
    assert body["production_authority"] is False
    assert body["read_only"] is True
    assert body["real_capital"] == 0
    assert after == before
    assert client.post(
        "/api/shadow-decision-rail/forecast/"
        f"{cycle.forecast_identity}"
    ).status_code == 405


def test_product_cycle_endpoint_empty_is_exact_not_heuristic(
    tmp_path: Path,
) -> None:
    path, _, _ = _manifest_with_cycle(tmp_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=path,
        )
    )
    unrelated = _sha("same-market-but-not-same-forecast")

    response = client.get(
        f"/api/shadow-decision-rail/forecast/{unrelated}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "empty",
        "reason": "no_exact_persisted_shadow_cycle_for_forecast",
        "forecast_identity": unrelated,
        "semantic": "EXACT_PERSISTED_CYCLE_IDENTITY_ONLY",
        "read_only": True,
        "real_capital": 0,
    }


def test_product_cycle_endpoint_missing_runtime_creates_nothing(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.shadow-cycle.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=missing,
        )
    )
    forecast = _sha("forecast")

    response = client.get(
        f"/api/shadow-decision-rail/forecast/{forecast}"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason"] == "shadow_cycle_manifest_evidence_missing"
    assert not missing.exists()


def test_product_cycle_endpoint_rejects_non_sha_before_runtime_lookup(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=(
                tmp_path / "missing.shadow-cycle.sqlite3"
            ),
        )
    )

    response = client.get(
        "/api/shadow-decision-rail/forecast/BTCUSDT"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "forecast_identity must be lowercase SHA256"
    )


def test_galactech_evidence_room_uses_exact_cycle_manifest_link(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))

    script = client.get("/galactech-static/app.js")

    assert script.status_code == 200
    js = script.text
    assert "shadowForecastCycle: (identity) =>" in js
    assert "/api/shadow-decision-rail/forecast/" in js
    assert "function renderShadowCycleExtension(payload)" in js
    assert "R25 SERMAYE KARARI SOY AĞACI" in js
    assert "SERMAYE BİLİMİ" in js
    assert "POZİSYON BOYUTU" in js
    assert "DENEME GÜNLÜĞÜ REFERANSI" in js
    assert "DÖNGÜ MANİFESTOSU" in js
    assert "sembol, yakın zaman, yön veya benzerlik tahminiyle kayıt eşleştirmez" in js
    assert "kanonik Epoch 2 NAV değişikliği" in js
    assert "Yalnız exact kalıcı forecast_identity eşleşmesi kullanılır." in js
