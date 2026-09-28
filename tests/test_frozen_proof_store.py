from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.product.frozen_proof_store import (
    FrozenProofConflictError,
    FrozenProofObject,
    FrozenProofStore,
    FrozenProofWriteDisposition,
)


def _identity(label: str) -> str:
    return canonical_sha256({"identity": label})


def _proof() -> FrozenProofObject:
    source_ids = tuple(sorted((_identity("book"), _identity("trades"))))
    dependency_ids = (_identity("liquidity-dynamics"),)
    return FrozenProofObject(
        object_identity=_identity("liquidity-structure-freeze"),
        analysis_identity=_identity("liquidity-structure-analysis"),
        object_kind="liquidity_structure_freeze",
        family="liquidity",
        domains=("liquidity_structure",),
        asset="BTC",
        symbol="BTCUSDT",
        network=None,
        timeframe="microstructure",
        as_of_ms=1_000,
        market_available_at_ms=980,
        observed_at_ms=990,
        source_provider="market_tape",
        source_quality="exact_persisted",
        freshness_state="fresh",
        freshness_age_ms=10,
        uncertainty_flags=(),
        source_object_identities=source_ids,
        depends_on_evidence_identities=dependency_ids,
        payload_json=canonical_json(
            {
                "levels": [
                    {"price": "100.0", "side": "bid"},
                    {"price": "101.0", "side": "ask"},
                ],
                "status": "measured",
            }
        ),
        visualization_json=canonical_json(
            {
                "renderer": "liquidity_levels_v1",
                "levels": ["100.0", "101.0"],
            }
        ),
        renderer_contract_version="liquidity-levels-v1/1",
        persisted_at_ms=1_005,
    )


def test_append_is_exact_idempotent_and_read_only(tmp_path: Path) -> None:
    path = tmp_path / "proofs.sqlite3"
    store = FrozenProofStore(path)
    proof = _proof()

    assert store.append(proof) is FrozenProofWriteDisposition.INSERTED
    assert store.append(proof) is FrozenProofWriteDisposition.UNCHANGED
    assert store.count() == 1
    assert store.read_exact(proof.object_identity) == proof
    assert (
        store.read_by_analysis_identity(
            proof.analysis_identity or "",
            as_of_ms=proof.as_of_ms,
        )
        == proof
    )


def test_same_identity_different_payload_fails_closed(tmp_path: Path) -> None:
    store = FrozenProofStore(tmp_path / "proofs.sqlite3")
    proof = _proof()
    assert store.append(proof) is FrozenProofWriteDisposition.INSERTED

    conflicting = replace(
        proof,
        payload_json=canonical_json({"status": "different"}),
    )
    with pytest.raises(
        FrozenProofConflictError,
        match="identity rebound",
    ):
        store.append(conflicting)

    assert store.read_exact(proof.object_identity) == proof
    assert store.count() == 1


def test_sql_update_and_delete_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "proofs.sqlite3"
    store = FrozenProofStore(path)
    proof = _proof()
    store.append(proof)

    with sqlite3.connect(path) as connection:
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable frozen proof object",
        ):
            connection.execute(
                """
                UPDATE frozen_proof_objects
                SET as_of_ms = as_of_ms + 1
                WHERE object_identity=?
                """,
                (proof.object_identity,),
            )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable frozen proof object",
        ):
            connection.execute(
                "DELETE FROM frozen_proof_objects WHERE object_identity=?",
                (proof.object_identity,),
            )


def test_missing_read_never_initializes_or_backfills(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    store = FrozenProofStore(path)

    assert store.read_exact(_identity("missing")) is None
    assert (
        store.read_by_analysis_identity(
            _identity("missing-analysis"),
            as_of_ms=5_000,
        )
        is None
    )
    assert store.count() == 0
    assert not path.exists()


def test_analysis_lookup_is_point_in_time_bounded(tmp_path: Path) -> None:
    store = FrozenProofStore(tmp_path / "proofs.sqlite3")
    proof = _proof()
    store.append(proof)

    assert (
        store.read_by_analysis_identity(
            proof.analysis_identity or "",
            as_of_ms=proof.as_of_ms - 1,
        )
        is None
    )
    assert (
        store.read_by_analysis_identity(
            proof.analysis_identity or "",
            as_of_ms=proof.as_of_ms,
        )
        == proof
    )


def test_future_source_or_real_capital_authority_is_rejected() -> None:
    proof = _proof()
    with pytest.raises(ValueError, match="future evidence"):
        replace(proof, observed_at_ms=proof.as_of_ms + 1)
    with pytest.raises(ValueError, match="REAL_CAPITAL"):
        replace(proof, real_capital=1)
    with pytest.raises(ValueError, match="production authority"):
        replace(proof, production_authority=True)


def test_noncanonical_payload_is_rejected() -> None:
    proof = _proof()
    with pytest.raises(ValueError, match="canonical JSON"):
        replace(proof, payload_json='{ "status": "measured" }')
