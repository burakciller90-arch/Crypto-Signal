from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_runtime_replay_observation import _observation, _sha
from test_shadow_cycle_runtime import _kwargs

from crypto_signal.paper.runtime_replay_observation import (
    R25RuntimeReplayObservationLedger,
    build_runtime_replay_observation,
)
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_cycle_runtime import run_persisted_shadow_cycle
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.product.web import create_app


def _persist_exact_observation(tmp_path: Path):
    first, replay, observation = _observation(tmp_path)
    replay_path = tmp_path / "runtime-product.shadow-replay.sqlite3"
    R25RuntimeReplayObservationLedger(replay_path).append(observation)
    manifest_path = tmp_path / "runtime.shadow-cycle.sqlite3"
    return manifest_path, replay_path, first, replay, observation


def test_product_replay_truth_stays_not_measured_without_observation_runtime(
    tmp_path: Path,
) -> None:
    first, _, _ = _observation(tmp_path)
    manifest_path = tmp_path / "runtime.shadow-cycle.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=manifest_path,
        )
    )

    response = client.get(
        "/api/shadow-decision-rail/forecast/"
        f"{first.cycle.forecast_identity}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["restart_replay_runtime_status"] == "NOT_MEASURED"
    assert body["restart_replay_runtime_reason"] == (
        "runtime_replay_observation_not_configured"
    )
    assert body["runtime_replay_observation"] is None


def test_product_replay_truth_is_verified_only_for_exact_persisted_observation(
    tmp_path: Path,
) -> None:
    manifest_path, replay_path, first, _, observation = (
        _persist_exact_observation(tmp_path)
    )
    manifest_before = manifest_path.read_bytes()
    replay_before = replay_path.read_bytes()
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=manifest_path,
            runtime_replay_observation_path=replay_path,
        )
    )

    response = client.get(
        "/api/shadow-decision-rail/forecast/"
        f"{first.cycle.forecast_identity}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["restart_replay_runtime_status"] == "VERIFIED"
    assert body["restart_replay_runtime_reason"] == (
        "exact_runtime_restart_replay_observed"
    )
    assert body["runtime_replay_observation"]["observation_identity"] == (
        observation.observation_identity
    )
    assert body["runtime_replay_observation"]["runtime_instance_identity"] == (
        observation.runtime_instance_identity
    )
    assert body["runtime_replay_observation"]["manifest_identity"] == (
        body["cycle"]["manifest_identity"]
    )
    assert body["runtime_replay_observation"]["journal_record_identity"] == (
        body["cycle"]["journal_record_identity"]
    )
    assert body["runtime_replay_observation"]["restart_replay_verified"] is True
    assert body["canonical_epoch2_mutation"] is False
    assert body["production_authority"] is False
    assert body["real_capital"] == 0
    assert manifest_path.read_bytes() == manifest_before
    assert replay_path.read_bytes() == replay_before


def test_product_replay_truth_missing_observation_file_does_not_create_it(
    tmp_path: Path,
) -> None:
    first, _, _ = _observation(tmp_path)
    manifest_path = tmp_path / "runtime.shadow-cycle.sqlite3"
    missing = tmp_path / "missing.shadow-replay.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=manifest_path,
            runtime_replay_observation_path=missing,
        )
    )

    response = client.get(
        "/api/shadow-decision-rail/forecast/"
        f"{first.cycle.forecast_identity}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["restart_replay_runtime_status"] == "NOT_MEASURED"
    assert body["restart_replay_runtime_reason"] == (
        "runtime_replay_observation_evidence_missing"
    )
    assert body["runtime_replay_observation"] is None
    assert not missing.exists()


def test_product_replay_truth_fails_closed_on_same_forecast_wrong_cycle_lineage(
    tmp_path: Path,
) -> None:
    first, _, _ = _observation(tmp_path)
    baseline_manifest = tmp_path / "runtime.shadow-cycle.sqlite3"

    alt_journal_path = tmp_path / "alt.shadow-intent.sqlite3"
    alt_manifest_path = tmp_path / "alt.shadow-cycle.sqlite3"

    issuance, first_kwargs = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(alt_journal_path),
        shift=50,
    )
    alt_first = run_persisted_shadow_cycle(
        issuance,
        manifest=R25ShadowCycleManifest(alt_manifest_path),
        **first_kwargs,
    )
    issuance2, replay_kwargs = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(alt_journal_path),
        shift=50,
    )
    alt_replay = run_persisted_shadow_cycle(
        issuance2,
        manifest=R25ShadowCycleManifest(alt_manifest_path),
        **replay_kwargs,
    )
    alt_observation = build_runtime_replay_observation(
        alt_first,
        alt_replay,
        runtime_instance_identity=_sha("different-runtime-instance"),
        first_observed_at_ms=alt_first.cycle.preview.previewed_at_ms + 10,
        replay_observed_at_ms=alt_first.cycle.preview.previewed_at_ms + 20,
    )
    assert alt_observation.forecast_identity == first.cycle.forecast_identity
    assert alt_observation.cycle_identity != first.cycle.cycle_identity

    replay_path = tmp_path / "mismatch.shadow-replay.sqlite3"
    R25RuntimeReplayObservationLedger(replay_path).append(alt_observation)

    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_cycle_manifest_path=baseline_manifest,
            runtime_replay_observation_path=replay_path,
        )
    )
    response = client.get(
        "/api/shadow-decision-rail/forecast/"
        f"{first.cycle.forecast_identity}"
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "runtime replay observation does not match exact "
        "persisted shadow cycle lineage"
    )


def test_galactech_evidence_room_labels_runtime_replay_truth_explicitly(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))
    script = client.get("/galactech-static/app.js")

    assert script.status_code == 200
    js = script.text
    assert "payload.restart_replay_runtime_status" in js
    assert '"NOT MEASURED"' in js
    assert '"VERIFIED"' in js
    assert "runtime_instance_identity" in js
    assert "first_observed_at_ms" in js
    assert "replay_observed_at_ms" in js
    assert "Restart/replay:" in js
