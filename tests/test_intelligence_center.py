from __future__ import annotations

import hashlib
import inspect
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.product import intelligence_center
from crypto_signal.product.intelligence_center import (
    accepted_intelligence_catalog,
    build_intelligence_center_payload,
)
from crypto_signal.product.web import create_app
from research.alpha_factory.learning_memory import (
    LearningChangeKind,
    LearningEvidenceClass,
    LearningMemoryStore,
    LearningOutcomeState,
    LearningRelationKind,
    LearningUncertaintyState,
    build_learning_lineage_link,
    build_learning_memory_record,
    build_learning_redundancy_link,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _seed_learning_memory(path: Path) -> None:
    first = build_learning_memory_record(
        evidence_class=LearningEvidenceClass.INTELLIGENCE_ENGINE,
        method_id="trend_momentum",
        method_version="trend-momentum-v1/1",
        asset="BTCUSDT",
        timeframe="4h",
        regime="trend",
        observed_from_ms=100,
        observed_to_ms=200,
        outcome_state=LearningOutcomeState.SUCCESS,
        evidence_identities=(_sha("trend-evidence"),),
        uncertainty_state=LearningUncertaintyState.STABLE_UNDER_ACCEPTED_TESTS,
        uncertainty_evidence_identities=(_sha("trend-uncertainty"),),
    )
    second = build_learning_memory_record(
        evidence_class=LearningEvidenceClass.ALPHA_FACTORY,
        method_id="bounded_ml",
        method_version="alpha-factory-bounded-ml-baseline-v1/1",
        asset="BTCUSDT",
        timeframe="4h",
        regime="transition",
        observed_from_ms=200,
        observed_to_ms=300,
        outcome_state=LearningOutcomeState.FAILURE,
        evidence_identities=(_sha("ml-evidence"),),
        uncertainty_state=LearningUncertaintyState.EVIDENCE_LIMITED,
        uncertainty_evidence_identities=(_sha("ml-uncertainty"),),
    )
    relation = build_learning_redundancy_link(
        first.record_identity,
        second.record_identity,
        relation=LearningRelationKind.OVERLAPPING,
        basis_evidence_identity=_sha("overlap-basis"),
    )
    lineage = build_learning_lineage_link(
        first.record_identity,
        second.record_identity,
        change_kind=LearningChangeKind.MODEL_VERSION,
        change_identity=_sha("model-change"),
    )
    store = LearningMemoryStore(path)
    store.initialize()
    store.append_record(first)
    store.append_record(second)
    store.append_redundancy_link(relation)
    store.append_lineage_link(lineage)
    store.capture_snapshot(built_at_ms=350)


def test_accepted_catalog_is_read_only_and_zero_contribution() -> None:
    catalog = accepted_intelligence_catalog()

    assert len(catalog) >= 20
    assert {item["group"] for item in catalog} == {
        "market_intelligence",
        "alpha_factory",
        "learning_memory",
        "meta_intelligence",
    }
    assert all(item["acceptance_status"] == "accepted_research_only" for item in catalog)
    assert all(item["production_contribution"] == 0 for item in catalog)
    assert all(item["production_authority"] is False for item in catalog)
    assert all(item["probability_status"] == "not_calibrated" for item in catalog)
    assert all(item["read_only"] is True for item in catalog)
    meta = next(item for item in catalog if item["engine_id"] == "meta_intelligence_shadow")
    assert meta["group"] == "meta_intelligence"
    assert meta["engine_version"] == "meta-intelligence-shadow-v1/1"
    assert meta["source_module"] == "src/crypto_signal/intelligence/meta_intelligence.py"
    assert meta["production_contribution"] == 0
    assert meta["production_authority"] is False


def test_intelligence_center_without_runtime_memory_is_explicit() -> None:
    payload = build_intelligence_center_payload(None, observed_at_ms=1_000)

    assert payload["status"] == "ready"
    assert payload["read_only"] is True
    assert payload["real_capital"] == 0
    assert payload["production_active_engine_count"] == 0
    assert payload["probability_status"] == "not_calibrated"
    assert payload["learning_memory"]["status"] == "not_configured"
    assert payload["learning_memory"]["record_count"] == 0
    assert payload["learning_memory"]["production_contribution"] == 0


def test_web_api_exposes_catalog_without_creating_memory(tmp_path: Path) -> None:
    missing_ledger = tmp_path / "missing-signals.sqlite3"
    client = TestClient(create_app(missing_ledger))

    response = client.get("/api/intelligence-center?observed_at_ms=1000")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["accepted_engine_count"] == len(body["engines"])
    assert body["learning_memory"]["reason"] == "learning_memory_path_not_configured"
    assert client.post("/api/intelligence-center").status_code == 405
    assert not missing_ledger.exists()


def test_learning_memory_is_read_without_mutating_sqlite(tmp_path: Path) -> None:
    missing_ledger = tmp_path / "missing-signals.sqlite3"
    memory_path = tmp_path / "learning-memory.sqlite3"
    _seed_learning_memory(memory_path)
    before = memory_path.stat()

    client = TestClient(
        create_app(
            missing_ledger,
            learning_memory_path=memory_path,
        )
    )
    response = client.get("/api/intelligence-center?observed_at_ms=1000")
    after = memory_path.stat()

    assert response.status_code == 200
    memory = response.json()["learning_memory"]
    assert memory["status"] == "ready"
    assert memory["record_count"] == 2
    assert memory["relation_count"] == 1
    assert memory["lineage_count"] == 1
    assert memory["latest_observed_to_ms"] == 300
    assert memory["latest_age_ms"] == 700
    assert memory["outcome_counts"] == [["failure", 1], ["success", 1]]
    assert memory["winner_selected"] is False
    assert memory["production_weight_changed"] is False
    assert memory["production_contribution"] == 0
    assert memory["production_authority"] is False
    assert memory["read_only"] is True
    assert memory["real_capital"] == 0
    assert before.st_size == after.st_size
    assert before.st_mtime_ns == after.st_mtime_ns
    assert not missing_ledger.exists()


def test_invalid_learning_memory_authority_fails_closed(tmp_path: Path) -> None:
    memory_path = tmp_path / "bad-learning.sqlite3"
    store = LearningMemoryStore(memory_path)
    store.initialize()

    payload = {
        "automatic_promotion": False,
        "asset": "BTCUSDT",
        "engine_version": "alpha-factory-learning-memory-v1/1",
        "evidence_class": "alpha_factory",
        "evidence_identities": [_sha("bad-evidence")],
        "explicit_cost_r_total": None,
        "gross_r_total": None,
        "method_id": "tampered",
        "method_version": "v1",
        "net_r_total": None,
        "observed_from_ms": 1,
        "observed_to_ms": 2,
        "outcome_state": "mixed",
        "production_authority": False,
        "production_contribution": 1,
        "real_capital": 0,
        "regime": "unknown",
        "schema_version": "alpha-factory-learning-memory-schema-v1/1",
        "timeframe": "4h",
        "uncertainty_evidence_identities": [],
        "uncertainty_state": "not_assessed",
    }
    identity = canonical_sha256(payload)
    with sqlite3.connect(memory_path) as connection:
        connection.execute(
            "INSERT INTO learning_memory_records(record_identity, payload) VALUES(?, ?)",
            (identity, canonical_json(payload)),
        )

    result = build_intelligence_center_payload(memory_path, observed_at_ms=10)
    memory = result["learning_memory"]

    assert memory["status"] == "invalid_evidence"
    assert memory["reason"] == "learning_memory_evidence_invalid"
    assert memory["record_count"] == 0
    assert memory["production_contribution"] == 0
    assert memory["production_authority"] is False


def test_product_projection_does_not_import_or_execute_research_engines() -> None:
    source = inspect.getsource(intelligence_center).lower()

    assert "from research" not in source
    assert "import research" not in source
    assert "place_order" not in source
    assert "submit_order" not in source
    assert '"production_contribution": 0' in source
    assert intelligence_center.REAL_CAPITAL == 0
