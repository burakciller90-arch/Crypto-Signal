from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_shadow_cycle_runtime import _kwargs

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.runtime_replay_observation import (
    R25RuntimeReplayObservationLedger,
    build_runtime_replay_observation,
)
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_cycle_runtime import run_persisted_shadow_cycle
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _first_and_replay(tmp_path: Path):
    journal_path = tmp_path / "runtime.shadow-intent.sqlite3"
    manifest_path = tmp_path / "runtime.shadow-cycle.sqlite3"

    issuance, kwargs = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(journal_path),
    )
    first = run_persisted_shadow_cycle(
        issuance,
        manifest=R25ShadowCycleManifest(manifest_path),
        **kwargs,
    )

    issuance2, kwargs2 = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(journal_path),
    )
    replay = run_persisted_shadow_cycle(
        issuance2,
        manifest=R25ShadowCycleManifest(manifest_path),
        **kwargs2,
    )
    return first, replay


def _observation(tmp_path: Path):
    first, replay = _first_and_replay(tmp_path)
    previewed = first.cycle.preview.previewed_at_ms
    observation = build_runtime_replay_observation(
        first,
        replay,
        runtime_instance_identity=_sha("uid504-runtime-instance"),
        first_observed_at_ms=previewed + 10,
        replay_observed_at_ms=previewed + 20,
    )
    return first, replay, observation


def test_runtime_replay_observation_requires_insert_then_exact_idempotent_replay(
    tmp_path: Path,
) -> None:
    first, replay, observation = _observation(tmp_path)

    assert observation.persisted_cycle_identity == first.persisted_cycle_identity
    assert observation.persisted_cycle_identity == replay.persisted_cycle_identity
    assert observation.cycle_identity == first.cycle.cycle_identity
    assert observation.forecast_identity == first.cycle.forecast_identity
    assert observation.proof_identity == first.cycle.proof_identity
    assert observation.capital_bridge_identity == first.cycle.capital.bridge_identity
    assert observation.sizing_bridge_identity == first.cycle.sizing.bridge_identity
    assert observation.preview_identity == first.cycle.preview.preview_identity
    assert observation.journal_record_identity == (
        first.cycle.journal_append.record.record_identity
    )
    assert observation.manifest_identity == (
        first.manifest_append.record.manifest_identity
    )
    assert observation.restart_replay_verified is True
    assert observation.canonical_epoch2_write_authority is False
    assert observation.production_authority is False
    assert observation.real_capital == 0


def test_runtime_replay_observation_rejects_reversed_sequence(
    tmp_path: Path,
) -> None:
    first, replay = _first_and_replay(tmp_path)
    previewed = first.cycle.preview.previewed_at_ms

    with pytest.raises(
        ValueError,
        match="first persisted cycle must be journal INSERTED",
    ):
        build_runtime_replay_observation(
            replay,
            first,
            runtime_instance_identity=_sha("runtime"),
            first_observed_at_ms=previewed + 10,
            replay_observed_at_ms=previewed + 20,
        )


def test_replay_observation_ledger_is_idempotent_read_only_and_byte_stable(
    tmp_path: Path,
) -> None:
    _, _, observation = _observation(tmp_path)
    path = tmp_path / "verified.shadow-replay.sqlite3"
    ledger = R25RuntimeReplayObservationLedger(path)

    first_insert = ledger.append(observation)
    second_insert = ledger.append(observation)
    before = path.read_bytes()
    status = R25RuntimeReplayObservationLedger(path).verify_read_only()
    latest = R25RuntimeReplayObservationLedger(path).read_latest_for_forecast(
        observation.forecast_identity
    )
    after = path.read_bytes()

    assert first_insert is True
    assert second_insert is False
    assert status.record_count == 1
    assert status.latest_observation_identity == observation.observation_identity
    assert status.quick_check_ok is True
    assert status.read_only_verified is True
    assert latest == observation
    assert after == before


def test_same_runtime_cycle_cannot_be_rewritten_with_different_observation_time(
    tmp_path: Path,
) -> None:
    first, replay, observation = _observation(tmp_path)
    path = tmp_path / "conflict.shadow-replay.sqlite3"
    ledger = R25RuntimeReplayObservationLedger(path)
    ledger.append(observation)

    changed = build_runtime_replay_observation(
        first,
        replay,
        runtime_instance_identity=observation.runtime_instance_identity,
        first_observed_at_ms=observation.first_observed_at_ms + 1,
        replay_observed_at_ms=observation.replay_observed_at_ms + 1,
    )
    with pytest.raises(ValueError, match="identity conflict"):
        ledger.append(changed)

    assert ledger.verify_read_only().record_count == 1


def test_replay_observation_update_delete_are_immutable(tmp_path: Path) -> None:
    _, _, observation = _observation(tmp_path)
    path = tmp_path / "immutable.shadow-replay.sqlite3"
    ledger = R25RuntimeReplayObservationLedger(path)
    ledger.append(observation)

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable R25"):
            db.execute(
                """UPDATE r25_runtime_replay_observations
                SET replay_observed_at_ms = replay_observed_at_ms + 1"""
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable R25"):
            db.execute("DELETE FROM r25_runtime_replay_observations")
        with pytest.raises(sqlite3.IntegrityError, match="immutable R25"):
            db.execute(
                """UPDATE r25_runtime_replay_meta
                SET value = 'tampered' WHERE key = 'semantic'"""
            )

    assert ledger.verify_read_only().record_count == 1


def test_replay_observation_refuses_non_replay_database(tmp_path: Path) -> None:
    path = tmp_path / "wrong.shadow-replay.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE canonical_epoch2_accounting (id TEXT)")

    ledger = R25RuntimeReplayObservationLedger(path)
    with pytest.raises(ValueError, match="non-replay database"):
        ledger.initialize()


def test_replay_observation_requires_isolated_suffix(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must end with"):
        R25RuntimeReplayObservationLedger(tmp_path / "epoch2.sqlite3")


def test_replay_observation_forecast_lookup_is_exact_sha_only(
    tmp_path: Path,
) -> None:
    _, _, observation = _observation(tmp_path)
    path = tmp_path / "lookup.shadow-replay.sqlite3"
    ledger = R25RuntimeReplayObservationLedger(path)
    ledger.append(observation)

    assert ledger.read_latest_for_forecast(_sha("unrelated")) is None
    with pytest.raises(ValueError, match="must be SHA256"):
        ledger.read_latest_for_forecast("BTCUSDT")
