from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import learning_memory
from research.alpha_factory.learning_memory import (
    LearningChangeKind,
    LearningEvidenceClass,
    LearningMemoryStore,
    LearningOutcomeState,
    LearningRelationKind,
    LearningUncertaintyState,
    build_learning_lineage_link,
    build_learning_memory_record,
    build_learning_memory_snapshot,
    build_learning_redundancy_link,
    summarize_learning_memory,
)


def _evidence(seed: str) -> str:
    return learning_memory.canonical_sha256({"seed": seed})


def _record(
    *,
    method_id: str,
    version: str,
    outcome: LearningOutcomeState,
    regime: str = "risk_on",
    gross: Decimal | None = None,
    cost: Decimal | None = None,
    net: Decimal | None = None,
):
    return build_learning_memory_record(
        evidence_class=LearningEvidenceClass.ALPHA_FACTORY,
        method_id=method_id,
        method_version=version,
        asset="BTCUSDT",
        timeframe="1h",
        regime=regime,
        observed_from_ms=1000,
        observed_to_ms=2000,
        outcome_state=outcome,
        evidence_identities=(_evidence(f"{method_id}-{version}-{outcome}"),),
        uncertainty_state=LearningUncertaintyState.STABLE_UNDER_ACCEPTED_TESTS,
        uncertainty_evidence_identities=(
            _evidence(f"uncertainty-{method_id}-{version}"),
        ),
        gross_r_total=gross,
        explicit_cost_r_total=cost,
        net_r_total=net,
    )


def test_learning_record_is_deterministic_and_has_zero_authority() -> None:
    first = _record(
        method_id="categorical_count",
        version="v1",
        outcome=LearningOutcomeState.SUCCESS,
        gross=Decimal("1.2"),
        cost=Decimal("0.2"),
        net=Decimal("1.0"),
    )
    second = _record(
        method_id="categorical_count",
        version="v1",
        outcome=LearningOutcomeState.SUCCESS,
        gross=Decimal("1.2"),
        cost=Decimal("0.2"),
        net=Decimal("1.0"),
    )
    assert first == second
    assert first.production_contribution == 0
    assert first.production_authority is False
    assert first.automatic_promotion is False
    assert first.real_capital == 0


def test_success_failure_abstention_and_no_evidence_are_all_retained() -> None:
    records = (
        _record(
            method_id="family_a",
            version="v1",
            outcome=LearningOutcomeState.SUCCESS,
        ),
        _record(
            method_id="family_b",
            version="v1",
            outcome=LearningOutcomeState.FAILURE,
        ),
        _record(
            method_id="family_c",
            version="v1",
            outcome=LearningOutcomeState.ABSTENTION,
        ),
        _record(
            method_id="family_d",
            version="v1",
            outcome=LearningOutcomeState.NO_EVIDENCE,
        ),
    )
    snapshot = build_learning_memory_snapshot(records, built_at_ms=3000)
    summary = summarize_learning_memory(snapshot, records)

    assert len(snapshot.record_identities) == 4
    assert dict(summary.outcome_counts) == {
        "abstention": 1,
        "failure": 1,
        "no_evidence": 1,
        "success": 1,
    }
    assert summary.winner_selected is False
    assert summary.production_weight_changed is False


def test_redundancy_and_lineage_are_explicit_evidence() -> None:
    before = _record(
        method_id="sign_vote",
        version="v1",
        outcome=LearningOutcomeState.MIXED,
    )
    after = _record(
        method_id="sign_vote",
        version="v2",
        outcome=LearningOutcomeState.SUCCESS,
    )
    other = _record(
        method_id="categorical_count",
        version="v1",
        outcome=LearningOutcomeState.SUCCESS,
    )
    relation = build_learning_redundancy_link(
        before.record_identity,
        other.record_identity,
        relation=LearningRelationKind.OVERLAPPING,
        basis_evidence_identity=_evidence("overlap-study"),
    )
    lineage = build_learning_lineage_link(
        before.record_identity,
        after.record_identity,
        change_kind=LearningChangeKind.MODEL_VERSION,
        change_identity=_evidence("model-v1-to-v2"),
    )
    snapshot = build_learning_memory_snapshot(
        (before, after, other),
        (relation,),
        (lineage,),
        built_at_ms=4000,
    )

    assert snapshot.redundancy_link_identities == (relation.link_identity,)
    assert snapshot.lineage_link_identities == (lineage.link_identity,)
    assert snapshot.production_weighting_authority is False
    assert snapshot.champion_write_authority is False
    assert snapshot.deploy_authority is False


def test_append_only_store_persists_failures_and_snapshot_lineage(tmp_path) -> None:
    path = tmp_path / "learning-memory.sqlite3"
    store = LearningMemoryStore(path)
    store.initialize()

    success = _record(
        method_id="family_a",
        version="v1",
        outcome=LearningOutcomeState.SUCCESS,
    )
    failure = _record(
        method_id="family_b",
        version="v1",
        outcome=LearningOutcomeState.FAILURE,
    )
    store.append_record(success)
    store.append_record(failure)
    store.append_record(failure)
    first = store.capture_snapshot(built_at_ms=5000)

    reopened = LearningMemoryStore(path)
    reopened.initialize()
    loaded_records = reopened.list_records()
    assert {item.record_identity for item in loaded_records} == {
        success.record_identity,
        failure.record_identity,
    }
    assert reopened.load_snapshot(first.snapshot_identity) == first

    no_evidence = _record(
        method_id="family_c",
        version="v1",
        outcome=LearningOutcomeState.NO_EVIDENCE,
    )
    reopened.append_record(no_evidence)
    second = reopened.capture_snapshot(
        built_at_ms=6000,
        parent_snapshot_identity=first.snapshot_identity,
    )
    assert second.parent_snapshot_identity == first.snapshot_identity
    assert set(second.record_identities).issuperset(first.record_identities)
    assert len(second.record_identities) == 3
    assert reopened.load_snapshot(first.snapshot_identity) == first


def test_store_persists_redundancy_and_before_after_lineage(tmp_path) -> None:
    store = LearningMemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    before = _record(
        method_id="method_x",
        version="v1",
        outcome=LearningOutcomeState.FAILURE,
    )
    after = _record(
        method_id="method_x",
        version="v2",
        outcome=LearningOutcomeState.MIXED,
    )
    store.append_record(before)
    store.append_record(after)

    relation = build_learning_redundancy_link(
        before.record_identity,
        after.record_identity,
        relation=LearningRelationKind.CONTRADICTORY,
        basis_evidence_identity=_evidence("contradiction"),
    )
    lineage = build_learning_lineage_link(
        before.record_identity,
        after.record_identity,
        change_kind=LearningChangeKind.POLICY_VERSION,
        change_identity=_evidence("policy-change"),
    )
    store.append_redundancy_link(relation)
    store.append_lineage_link(lineage)
    snapshot = store.capture_snapshot(built_at_ms=7000)

    assert store.list_redundancy_links() == (relation,)
    assert store.list_lineage_links() == (lineage,)
    assert snapshot.redundancy_link_identities == (relation.link_identity,)
    assert snapshot.lineage_link_identities == (lineage.link_identity,)


def test_snapshot_rejects_links_to_missing_records() -> None:
    record = _record(
        method_id="method_x",
        version="v1",
        outcome=LearningOutcomeState.SUCCESS,
    )
    missing = _record(
        method_id="method_y",
        version="v1",
        outcome=LearningOutcomeState.FAILURE,
    )
    relation = build_learning_redundancy_link(
        record.record_identity,
        missing.record_identity,
        relation=LearningRelationKind.REDUNDANT,
        basis_evidence_identity=_evidence("redundancy"),
    )
    with pytest.raises(ValueError, match="references missing record"):
        build_learning_memory_snapshot(
            (record,),
            (relation,),
            built_at_ms=8000,
        )


def test_metric_accounting_and_identity_tampering_fail_closed() -> None:
    with pytest.raises(ValueError, match="net-R accounting"):
        _record(
            method_id="bad",
            version="v1",
            outcome=LearningOutcomeState.FAILURE,
            gross=Decimal("1"),
            cost=Decimal("0.2"),
            net=Decimal("0.9"),
        )

    record = _record(
        method_id="good",
        version="v1",
        outcome=LearningOutcomeState.SUCCESS,
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(record, regime="risk_off")


def test_learning_memory_has_no_production_weight_or_promotion_api() -> None:
    source = inspect.getsource(learning_memory).lower()
    forbidden = (
        "crypto_signal.product",
        "crypto_signal.confluence",
        "crypto_signal.signals",
        "place_order",
        "submit_order",
        "def promote",
        "def deploy",
        "def set_weight",
        "def update_weight",
        "delete from",
        "update learning_memory_",
        "import httpx",
        "import requests",
        "import urllib",
        "import socket",
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert learning_memory.REAL_CAPITAL == 0
