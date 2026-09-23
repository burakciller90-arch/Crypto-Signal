from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from test_runtime_replay_observation import _observation

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.runtime_replay_observation import (
    R25RuntimeReplayObservationLedger,
)
from crypto_signal.product.web import create_app


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _runtime_truth(tmp_path: Path):
    first, replay, observation = _observation(tmp_path)
    replay_path = tmp_path / "product.shadow-replay.sqlite3"
    ledger = R25RuntimeReplayObservationLedger(replay_path)
    assert ledger.append(observation) is True
    manifest_path = tmp_path / "runtime.shadow-cycle.sqlite3"
    return first, replay, observation, manifest_path, replay_path


def test_runtime_replay_status_is_verified_only_from_persisted_observation(
    tmp_path: Path,
) -> None:
    _, _, observation, manifest_path, replay_path = _runtime_truth(tmp_path)
    manifest_before = manifest_path.read_bytes()
    replay_before = replay_path.read_bytes()

    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=manifest_path,
            runtime_replay_observation_path=replay_path,
        )
    )

    cycle_response = client.get("/api/shadow-cycle-manifest/status")
    replay_response = client.get("/api/runtime-replay-observation/status")

    assert cycle_response.status_code == 200
    cycle_body = cycle_response.json()
    assert cycle_body["status"] == "ready"
    assert cycle_body["capital_science_lineage"] == "PERSISTED"
    assert cycle_body["sizing_lineage"] == "PERSISTED"
    assert cycle_body["restart_replay_observation"] == "NOT_PERSISTED"

    assert replay_response.status_code == 200
    replay_body = replay_response.json()
    assert replay_body["status"] == "ready"
    assert replay_body["semantic"] == "RUNTIME_RESTART_REPLAY_OBSERVATION_ONLY"
    assert replay_body["restart_replay_observation"] == "VERIFIED"
    assert replay_body["snapshot"]["record_count"] == 1
    assert replay_body["snapshot"]["latest_observation_identity"] == (
        observation.observation_identity
    )
    assert replay_body["snapshot"]["quick_check_ok"] is True
    assert replay_body["snapshot"]["read_only_verified"] is True
    assert replay_body["canonical_epoch2_mutation"] is False
    assert replay_body["production_authority"] is False
    assert replay_body["read_only"] is True
    assert replay_body["real_capital"] == 0

    assert manifest_path.read_bytes() == manifest_before
    assert replay_path.read_bytes() == replay_before
    assert client.post("/api/runtime-replay-observation/status").status_code == 405


def test_cycle_manifest_without_replay_observation_never_claims_verified(
    tmp_path: Path,
) -> None:
    _, _, _, manifest_path, _ = _runtime_truth(tmp_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=manifest_path,
        )
    )

    cycle = client.get("/api/shadow-cycle-manifest/status").json()
    replay = client.get("/api/runtime-replay-observation/status").json()

    assert cycle["status"] == "ready"
    assert cycle["restart_replay_observation"] == "NOT_PERSISTED"
    assert replay == {
        "status": "unavailable",
        "reason": "runtime_replay_observation_not_configured",
        "semantic": "RUNTIME_RESTART_REPLAY_OBSERVATION_ONLY",
        "restart_replay_observation": "NOT_PERSISTED",
        "canonical_epoch2_mutation": False,
        "production_authority": False,
        "read_only": True,
        "real_capital": 0,
    }


def test_exact_forecast_replay_endpoint_matches_exact_cycle_lineage(
    tmp_path: Path,
) -> None:
    first, _, observation, manifest_path, replay_path = _runtime_truth(tmp_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=manifest_path,
            runtime_replay_observation_path=replay_path,
        )
    )
    forecast_identity = first.cycle.forecast_identity

    cycle_response = client.get(
        f"/api/shadow-decision-rail/forecast/{forecast_identity}"
    )
    replay_response = client.get(
        f"/api/runtime-replay-observation/forecast/{forecast_identity}"
    )

    assert cycle_response.status_code == 200
    assert replay_response.status_code == 200
    cycle = cycle_response.json()["cycle"]
    replay = replay_response.json()

    assert replay["status"] == "ready"
    assert replay["restart_replay_observation"] == "VERIFIED"
    assert replay["semantic"] == "EXACT_RUNTIME_REPLAY_IDENTITY_ONLY"
    persisted = replay["observation"]
    assert persisted["observation_identity"] == observation.observation_identity
    assert persisted["forecast_identity"] == cycle["forecast_identity"]
    assert persisted["cycle_identity"] == cycle["cycle_identity"]
    assert persisted["manifest_identity"] == cycle["manifest_identity"]
    assert persisted["preview_identity"] == cycle["preview_identity"]
    assert persisted["restart_replay_verified"] is True
    assert persisted["canonical_epoch2_write_authority"] is False
    assert persisted["production_authority"] is False
    assert persisted["real_capital"] == 0


def test_exact_replay_lookup_never_matches_unrelated_forecast(
    tmp_path: Path,
) -> None:
    _, _, _, _, replay_path = _runtime_truth(tmp_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            runtime_replay_observation_path=replay_path,
        )
    )
    unrelated = _sha("unrelated-replay-forecast")

    response = client.get(
        f"/api/runtime-replay-observation/forecast/{unrelated}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "empty",
        "reason": "no_exact_runtime_replay_observation_for_forecast",
        "forecast_identity": unrelated,
        "semantic": "EXACT_RUNTIME_REPLAY_IDENTITY_ONLY",
        "read_only": True,
        "real_capital": 0,
    }


def test_replay_product_missing_path_creates_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.shadow-replay.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            runtime_replay_observation_path=missing,
        )
    )

    response = client.get("/api/runtime-replay-observation/status")

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason"] == (
        "runtime_replay_observation_evidence_missing"
    )
    assert not missing.exists()


def test_replay_product_rejects_non_sha_before_runtime_lookup(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            runtime_replay_observation_path=(
                tmp_path / "missing.shadow-replay.sqlite3"
            ),
        )
    )

    response = client.get(
        "/api/runtime-replay-observation/forecast/BTCUSDT"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "forecast_identity must be lowercase SHA256"
    )


def test_replay_status_fails_closed_on_non_replay_database(
    tmp_path: Path,
) -> None:
    wrong = tmp_path / "wrong.shadow-replay.sqlite3"
    with sqlite3.connect(wrong) as db:
        db.execute("CREATE TABLE canonical_epoch2_accounting (id TEXT)")

    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            runtime_replay_observation_path=wrong,
        )
    )

    response = client.get("/api/runtime-replay-observation/status")

    assert response.status_code == 500
    assert "non-replay" in response.json()["detail"]


def test_galactech_surfaces_replay_only_from_runtime_observation(
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
    assert 'id="systemReplayObservation"' in html
    assert 'id="systemReplayObservationNote"' in html
    assert "RUNTIME REPLAY OBSERVATION" in html

    assert 'replayStatus: "/api/runtime-replay-observation/status"' in js
    assert "replayForecast: (identity) =>" in js
    assert "/api/runtime-replay-observation/forecast/" in js
    assert "RESTART / REPLAY · VERIFIED" in js
    assert "RESTART / REPLAY · NOT PERSISTED" in js
    assert "Hosted acceptance is never upgraded" in js
    assert "observation?.manifest_identity === cycle.manifest_identity" in js
    assert "observation?.preview_identity === cycle.preview_identity" in js
    assert 'loadEndpoint("replayStatus", API.replayStatus)' in js
