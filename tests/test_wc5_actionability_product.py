from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crypto_signal.evaluation.untouched_forward_journal import (
    WC2_COHORT_ENGINE_VERSION,
    WC2_COHORT_SCHEMA_VERSION,
)
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.product.wc5_actionability import (
    WC5ActionabilityStatus,
    read_wc5_actionability,
)
from crypto_signal.product.web import create_app


def _sha(char: str) -> str:
    return char * 64


def _seed_wc2_cohort(path: Path, *, actions: tuple[tuple[str, str], ...]) -> str:
    forecast_identity = _sha("1")
    proof_identity = _sha("2")
    policy_identity = _sha("3")
    forecast_payload = {
        "policy_identity": policy_identity,
        "forecast_identity": forecast_identity,
        "proof_identity": proof_identity,
        "signal_freeze_identity": _sha("4"),
        "confluence_identity": _sha("5"),
        "event_context_identity": _sha("6"),
        "asset": "BTC",
        "symbol": "BTCUSDT",
        "timeframe": "4h",
        "regime": "range",
        "issued_at_ms": 1_000,
        "indexed_at_ms": 1_100,
        "source_evidence_identities": [_sha("7")],
        "evidence_class": "LIVE_UNTOUCHED_FORWARD",
        "schema_version": WC2_COHORT_SCHEMA_VERSION,
        "engine_version": WC2_COHORT_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": 0,
    }
    cohort_identity = canonical_sha256(forecast_payload)

    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE wc2_cohort_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE wc2_cohort_forecasts (
                sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                cohort_forecast_identity TEXT UNIQUE NOT NULL,
                policy_identity TEXT NOT NULL,
                forecast_identity TEXT UNIQUE NOT NULL,
                proof_identity TEXT NOT NULL,
                symbol TEXT NOT NULL,
                regime TEXT NOT NULL,
                issued_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE wc2_cohort_intents (
                sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                intent_link_identity TEXT UNIQUE NOT NULL,
                cohort_forecast_identity TEXT NOT NULL,
                policy_identity TEXT NOT NULL,
                forecast_identity TEXT NOT NULL,
                paper_intent_identity TEXT UNIQUE NOT NULL,
                vault_id TEXT NOT NULL,
                action TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )
        db.execute(
            "INSERT INTO wc2_cohort_meta(key, value) VALUES (?, ?)",
            ("schema_version", WC2_COHORT_SCHEMA_VERSION),
        )
        db.execute(
            """INSERT INTO wc2_cohort_forecasts(
                cohort_forecast_identity,
                policy_identity,
                forecast_identity,
                proof_identity,
                symbol,
                regime,
                issued_at_ms,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cohort_identity,
                policy_identity,
                forecast_identity,
                proof_identity,
                "BTCUSDT",
                "range",
                1_000,
                canonical_json(forecast_payload),
            ),
        )

        for index, (vault_id, action) in enumerate(actions, start=1):
            paper_intent_identity = canonical_sha256(
                {"fixture": "paper-intent", "index": index}
            )
            intent_payload = {
                "policy_identity": policy_identity,
                "cohort_forecast_identity": cohort_identity,
                "forecast_identity": forecast_identity,
                "proof_identity": proof_identity,
                "persisted_cycle_identity": canonical_sha256(
                    {"fixture": "persisted-cycle", "index": index}
                ),
                "manifest_identity": canonical_sha256(
                    {"fixture": "manifest", "index": index}
                ),
                "shadow_cycle_identity": canonical_sha256(
                    {"fixture": "shadow-cycle", "index": index}
                ),
                "preview_identity": canonical_sha256(
                    {"fixture": "preview", "index": index}
                ),
                "shadow_intent_record_identity": canonical_sha256(
                    {"fixture": "journal", "index": index}
                ),
                "paper_intent_identity": paper_intent_identity,
                "vault_id": vault_id,
                "action": action,
                "decided_at_ms": 1_200 + index,
                "previewed_at_ms": 1_300 + index,
                "indexed_at_ms": 1_400 + index,
                "schema_version": WC2_COHORT_SCHEMA_VERSION,
                "engine_version": WC2_COHORT_ENGINE_VERSION,
                "production_authority": False,
                "real_capital": 0,
            }
            intent_identity = canonical_sha256(intent_payload)
            db.execute(
                """INSERT INTO wc2_cohort_intents(
                    intent_link_identity,
                    cohort_forecast_identity,
                    policy_identity,
                    forecast_identity,
                    paper_intent_identity,
                    vault_id,
                    action,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    intent_identity,
                    cohort_identity,
                    policy_identity,
                    forecast_identity,
                    paper_intent_identity,
                    vault_id,
                    action,
                    canonical_json(intent_payload),
                ),
            )
    return forecast_identity


def test_wc5_reads_one_exact_persisted_action_without_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2.sqlite3"
    forecast_identity = _seed_wc2_cohort(
        path,
        actions=(("CORE", "HOLD_CASH"),),
    )
    before = path.read_bytes()

    snapshot = read_wc5_actionability(
        path,
        forecast_identity=forecast_identity,
    )

    assert snapshot.status is WC5ActionabilityStatus.PERSISTED_ACTION
    assert snapshot.action == "HOLD_CASH"
    assert snapshot.intent_count == 1
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.regime == "range"
    assert snapshot.vault_id == "CORE"
    assert snapshot.maximum_exposure_status == "NOT_AVAILABLE_FROM_COHORT_INTENT"
    assert snapshot.read_only is True
    assert snapshot.production_authority is False
    assert snapshot.real_capital == 0
    assert path.read_bytes() == before


def test_wc5_keeps_missing_intent_insufficient(tmp_path: Path) -> None:
    path = tmp_path / "wc2.sqlite3"
    forecast_identity = _seed_wc2_cohort(path, actions=())

    snapshot = read_wc5_actionability(
        path,
        forecast_identity=forecast_identity,
    )

    assert snapshot.status is WC5ActionabilityStatus.INSUFFICIENT_EVIDENCE
    assert snapshot.action is None
    assert snapshot.intent_count == 0


def test_wc5_refuses_to_choose_between_multiple_persisted_intents(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2.sqlite3"
    forecast_identity = _seed_wc2_cohort(
        path,
        actions=(("CORE", "HOLD_CASH"), ("TACTICAL", "BUY")),
    )

    snapshot = read_wc5_actionability(
        path,
        forecast_identity=forecast_identity,
    )

    assert snapshot.status is (
        WC5ActionabilityStatus.INSUFFICIENT_EVIDENCE_MULTIPLE_INTENTS
    )
    assert snapshot.action is None
    assert snapshot.intent_count == 2


def test_wc5_fails_closed_on_tampered_intent_payload(tmp_path: Path) -> None:
    path = tmp_path / "wc2.sqlite3"
    forecast_identity = _seed_wc2_cohort(
        path,
        actions=(("CORE", "HOLD_CASH"),),
    )
    with sqlite3.connect(path) as db:
        row = db.execute(
            "SELECT intent_link_identity, payload_json FROM wc2_cohort_intents"
        ).fetchone()
        assert row is not None
        raw = json.loads(str(row[1]))
        raw["action"] = "BUY"
        db.execute(
            "UPDATE wc2_cohort_intents SET payload_json=? WHERE intent_link_identity=?",
            (canonical_json(raw), str(row[0])),
        )

    with pytest.raises(ValueError, match="payload identity mismatch"):
        read_wc5_actionability(path, forecast_identity=forecast_identity)


def test_wc5_action_endpoint_exposes_exact_action_and_no_authority(
    tmp_path: Path,
) -> None:
    cohort = tmp_path / "wc2.sqlite3"
    forecast_identity = _seed_wc2_cohort(
        cohort,
        actions=(("CORE", "HOLD_CASH"),),
    )
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            wc2_cohort_path=cohort,
        )
    )

    response = client.get(f"/api/wc2/action/{forecast_identity}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["semantic"] == "EXACT_PERSISTED_WC2_COHORT_ACTION_ONLY"
    assert body["snapshot"]["status"] == "PERSISTED_ACTION"
    assert body["snapshot"]["action"] == "HOLD_CASH"
    assert body["snapshot"]["maximum_exposure_status"] == (
        "NOT_AVAILABLE_FROM_COHORT_INTENT"
    )
    assert body["read_only"] is True
    assert body["production_authority"] is False
    assert body["real_capital"] == 0
    assert client.post(f"/api/wc2/action/{forecast_identity}").status_code == 405


def test_wc5_action_endpoint_preserves_unavailable_runtime(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            wc2_cohort_path=tmp_path / "missing-wc2.sqlite3",
        )
    )

    body = client.get("/api/wc2/action/" + _sha("a")).json()

    assert body["status"] == "unavailable"
    assert body["reason"] == "wc2_cohort_runtime_evidence_missing"
    assert body["production_authority"] is False
    assert body["real_capital"] == 0
    assert not (tmp_path / "missing-wc2.sqlite3").exists()
