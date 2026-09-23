from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_epoch2_accounting import _activate

from crypto_signal.paper.epoch2_accounting import read_epoch2_state_read_only
from crypto_signal.paper.epochs import EPOCH_2_SPEC, PaperVaultId
from crypto_signal.product.web import create_app


def test_epoch2_read_only_reader_never_initializes_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / EPOCH_2_SPEC.ledger_filename

    assert read_epoch2_state_read_only(missing) is None
    assert not missing.exists()


def test_epoch2_read_only_reader_preserves_canonical_db_bytes(tmp_path: Path) -> None:
    _, _, _, accepted = _activate(tmp_path)
    path = tmp_path / EPOCH_2_SPEC.ledger_filename
    before = path.read_bytes()

    observed = read_epoch2_state_read_only(path)

    assert observed == accepted
    assert path.read_bytes() == before
    assert observed is not None
    assert observed.activation.real_capital == 0
    assert observed.consolidated_snapshot.nav_usdt == 1000
    assert tuple(item.vault_id for item in observed.vault_snapshots) == (
        PaperVaultId.CORE,
        PaperVaultId.OPPORTUNITY_RESERVE,
        PaperVaultId.TACTICAL,
    )


def test_epoch2_read_only_reader_fails_closed_on_partial_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / EPOCH_2_SPEC.ledger_filename
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE r21_epoch2_activation (
                singleton INTEGER PRIMARY KEY,
                activation_identity TEXT,
                payload_json TEXT,
                activated_at_ms INTEGER
            )
            """
        )

    before = path.read_bytes()
    with pytest.raises(ValueError, match="schema is incomplete"):
        read_epoch2_state_read_only(path)
    assert path.read_bytes() == before


def test_epoch2_product_endpoint_exposes_canonical_truth_read_only(
    tmp_path: Path,
) -> None:
    _activate(tmp_path)
    epoch2 = tmp_path / EPOCH_2_SPEC.ledger_filename
    missing_signal = tmp_path / "missing-signals.sqlite3"
    before = epoch2.read_bytes()
    client = TestClient(
        create_app(
            missing_signal,
            epoch2_ledger_path=epoch2,
        )
    )

    response = client.get("/api/paper/epoch2-state")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["ledger_filename"] == EPOCH_2_SPEC.ledger_filename
    assert body["read_only"] is True
    assert body["real_capital"] == 0
    assert body["activation"]["starting_cash_usdt"] == "1000.00"
    assert body["activation"]["leverage_allowed"] is False
    assert body["activation"]["borrowing_allowed"] is False
    assert body["activation"]["martingale_allowed"] is False
    assert body["consolidated"]["nav_usdt"] == "1000.00"
    assert body["consolidated"]["cash_usdt"] == "1000.00"
    assert body["consolidated"]["marked_exposure_usdt"] == "0"
    assert body["consolidated"]["metrics_status"] == "not_yet_measured"
    assert [item["vault_id"] for item in body["vaults"]] == [
        "CORE",
        "OPPORTUNITY_RESERVE",
        "TACTICAL",
    ]
    assert client.post("/api/paper/epoch2-state").status_code == 405
    assert epoch2.read_bytes() == before
    assert not missing_signal.exists()


def test_epoch2_product_endpoint_is_explicit_when_not_configured(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "signals.sqlite3"))

    response = client.get("/api/paper/epoch2-state")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "reason": "epoch2_runtime_not_configured",
        "read_only": True,
        "real_capital": 0,
    }
