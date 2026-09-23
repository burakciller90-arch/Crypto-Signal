from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.product.market_tape_runtime import (
    read_cold_archive_runtime_truth,
    read_market_tape_runtime_truth,
)
from crypto_signal.product.web import create_app


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _seed_market_tape(path: Path, *, event_at_ms: int = 1_000) -> None:
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE market_tape_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE market_tape_orderbooks (
                snapshot_identity TEXT,
                exchange TEXT,
                market_type TEXT,
                symbol TEXT,
                event_at_ms INTEGER,
                source_timestamp_ms INTEGER,
                ingested_at_ms INTEGER,
                update_id INTEGER,
                sequence INTEGER,
                source TEXT,
                adapter_version TEXT,
                payload_json TEXT
            );
            CREATE TABLE market_tape_trades (
                trade_identity TEXT,
                exchange TEXT,
                market_type TEXT,
                symbol TEXT,
                event_at_ms INTEGER,
                source_timestamp_ms INTEGER,
                ingested_at_ms INTEGER,
                exec_id TEXT,
                sequence INTEGER,
                aggressor_side TEXT,
                source TEXT,
                adapter_version TEXT,
                payload_json TEXT
            );
            CREATE TABLE market_tape_derivatives (
                observation_identity TEXT,
                semantic_identity TEXT,
                exchange TEXT,
                instrument_type TEXT,
                symbol TEXT,
                event_at_ms INTEGER,
                source_timestamp_ms INTEGER,
                ingested_at_ms INTEGER,
                source TEXT,
                adapter_version TEXT,
                payload_json TEXT
            );
            CREATE TABLE market_tape_liquidations (
                liquidation_identity TEXT,
                provider_identity TEXT,
                exchange TEXT,
                instrument_type TEXT,
                symbol TEXT,
                event_at_ms INTEGER,
                source_timestamp_ms INTEGER,
                ingested_at_ms INTEGER,
                source_row_index INTEGER,
                liquidated_position_side TEXT,
                source TEXT,
                adapter_version TEXT,
                payload_json TEXT
            );
            CREATE TABLE market_tape_liquidation_coverage (
                coverage_identity TEXT,
                exchange TEXT,
                instrument_type TEXT,
                symbol TEXT,
                coverage_start_ms INTEGER,
                coverage_end_ms INTEGER,
                observed_at_ms INTEGER,
                source TEXT,
                adapter_version TEXT,
                payload_json TEXT
            );
            """
        )
        db.execute(
            "INSERT INTO market_tape_meta(key, value) VALUES (?, ?)",
            ("schema_version", "market-tape-schema-v1/2"),
        )
        db.execute(
            """INSERT INTO market_tape_orderbooks VALUES
            (?, 'bybit', 'spot', 'BTCUSDT', ?, ?, ?, 7, 7,
             'test', 'v1', '{}')""",
            ("a" * 64, event_at_ms, event_at_ms, event_at_ms),
        )
        db.execute(
            """INSERT INTO market_tape_trades VALUES
            (?, 'bybit', 'spot', 'BTCUSDT', ?, ?, ?, 'exec-1', 8,
             'buy', 'test', 'v1', '{}')""",
            ("b" * 64, event_at_ms + 10, event_at_ms + 10, event_at_ms + 10),
        )
        db.execute(
            """INSERT INTO market_tape_derivatives VALUES
            (?, ?, 'bybit', 'linear', 'BTCUSDT', ?, ?, ?,
             'test', 'v1', '{}')""",
            (
                "c" * 64,
                "d" * 64,
                event_at_ms + 20,
                event_at_ms + 20,
                event_at_ms + 20,
            ),
        )


def _seed_cold_archive(root: Path) -> Path:
    partition = root / "year=2026" / "month=09" / "day=23" / "hour=17"
    partition.mkdir(parents=True)
    raw_bytes = b"immutable-parquet-placeholder"
    raw_path = partition / "raw.parquet"
    raw_path.write_bytes(raw_bytes)
    empty_digest = hashlib.sha256(b"").hexdigest()
    manifest = {
        "schema_version": "market-tape-cold-parquet-v1/1",
        "partition_id": "20260923T170000Z",
        "window_start_ms": 1_000,
        "window_end_ms": 4_600_000,
        "compression": "zstd",
        "tables": {
            "raw": {
                "rows": 1,
                "filename": "raw.parquet",
                "bytes": len(raw_bytes),
                "file_sha256": _sha_bytes(raw_bytes),
                "canonical_sha256": "1" * 64,
                "identity_column": "event_identity",
            },
            "orderbooks": {
                "rows": 0,
                "filename": None,
                "bytes": 0,
                "file_sha256": None,
                "canonical_sha256": empty_digest,
                "identity_column": "snapshot_identity",
            },
            "trades": {
                "rows": 0,
                "filename": None,
                "bytes": 0,
                "file_sha256": None,
                "canonical_sha256": empty_digest,
                "identity_column": "trade_identity",
            },
            "derivatives": {
                "rows": 0,
                "filename": None,
                "bytes": 0,
                "file_sha256": None,
                "canonical_sha256": empty_digest,
                "identity_column": "observation_identity",
            },
        },
    }
    (partition / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )
    return partition


def test_market_tape_reader_is_read_only_and_reports_persisted_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    _seed_market_tape(path)
    before = path.read_bytes()

    snapshot = read_market_tape_runtime_truth(
        path,
        observed_at_ms=2_000,
    )

    assert snapshot.schema_version == "market-tape-schema-v1/2"
    assert snapshot.total_rows == 3
    assert dict(snapshot.counts) == {
        "derivatives": 1,
        "liquidation_coverage": 0,
        "liquidations": 0,
        "orderbooks": 1,
        "trades": 1,
    }
    assert snapshot.latest_event_at_ms == 1_020
    assert snapshot.latest_event_age_ms == 980
    assert snapshot.quick_check_ok is True
    assert snapshot.read_only_verified is True
    assert snapshot.collection_process_status == "NOT_MEASURED"
    assert snapshot.production_authority is False
    assert snapshot.real_capital == 0
    assert path.read_bytes() == before


def test_market_tape_reader_fails_closed_on_incomplete_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broken.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE market_tape_meta (key TEXT, value TEXT)")
        db.execute(
            "INSERT INTO market_tape_meta VALUES ('schema_version', ?)",
            ("market-tape-schema-v1/2",),
        )
        db.execute("CREATE TABLE market_tape_orderbooks (event_at_ms INTEGER)")

    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            market_tape_path=path,
        )
    )
    response = client.get(
        "/api/market-tape-runtime/status?observed_at_ms=2000"
    )

    assert response.status_code == 500
    assert "required columns missing" in response.json()["detail"]


def test_market_tape_product_endpoint_never_claims_online(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    _seed_market_tape(path)
    before = path.read_bytes()
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            market_tape_path=path,
        )
    )

    response = client.get(
        "/api/market-tape-runtime/status?observed_at_ms=2000"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["snapshot"]["total_rows"] == 3
    assert body["snapshot"]["latest_event_age_ms"] == 980
    assert body["collection_process_status"] == "NOT_MEASURED"
    assert body["online_status"] == "NOT_ASSERTED"
    assert body["read_only"] is True
    assert body["real_capital"] == 0
    assert path.read_bytes() == before
    assert client.post("/api/market-tape-runtime/status").status_code == 405


def test_market_tape_missing_runtime_creates_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            market_tape_path=missing,
        )
    )

    body = client.get("/api/market-tape-runtime/status").json()

    assert body["status"] == "unavailable"
    assert body["reason"] == "market_tape_runtime_evidence_missing"
    assert body["online_status"] == "NOT_ASSERTED"
    assert not missing.exists()


def test_cold_archive_verifies_manifest_and_file_hash_without_mutation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cold"
    partition = _seed_cold_archive(root)
    before = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }

    snapshot = read_cold_archive_runtime_truth(root, verify_limit=24)

    assert snapshot.partition_count == 1
    assert snapshot.verified_partition_count == 1
    assert snapshot.latest_partition_end_ms == 4_600_000
    assert snapshot.verified_rows == 1
    assert snapshot.integrity_scope == "ALL_PARTITIONS_FILE_SHA256"
    assert snapshot.canonical_row_digest_replay == "NOT_MEASURED"
    assert snapshot.archive_process_status == "NOT_MEASURED"
    assert snapshot.read_only_verified is True
    after = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert (partition / "raw.parquet").is_file()


def test_cold_archive_endpoint_fails_closed_on_tampered_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cold"
    partition = _seed_cold_archive(root)
    with (partition / "raw.parquet").open("ab") as handle:
        handle.write(b"tamper")

    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            cold_archive_path=root,
        )
    )
    response = client.get("/api/cold-archive/status")

    assert response.status_code == 500
    assert (
        "file size mismatch" in response.json()["detail"]
        or "file hash mismatch" in response.json()["detail"]
    )


def test_cold_archive_missing_runtime_creates_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "cold-missing"
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            cold_archive_path=missing,
        )
    )

    body = client.get("/api/cold-archive/status").json()

    assert body["status"] == "unavailable"
    assert body["reason"] == "cold_archive_runtime_evidence_missing"
    assert body["archive_process_status"] == "NOT_MEASURED"
    assert body["canonical_row_digest_replay"] == "NOT_MEASURED"
    assert not missing.exists()


def test_galactech_system_binds_market_data_truth_without_online_claim(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))
    html = client.get("/galactech").text
    js = client.get("/galactech-static/app.js").text

    assert 'id="systemMarketTape"' in html
    assert 'id="systemMarketTapeNote"' in html
    assert 'id="systemColdArchive"' in html
    assert 'id="systemColdArchiveNote"' in html
    assert "EVENT SOURCE RUNTIME" in html
    assert "NOT EXPOSED" in html

    assert 'marketTapeStatus: "/api/market-tape-runtime/status"' in js
    assert 'coldArchiveStatus: "/api/cold-archive/status?verify_limit=24"' in js
    assert '"systemMarketTape"' in js
    assert '"systemColdArchive"' in js
    assert "ONLINE NOT ASSERTED" in js
    assert "process NOT MEASURED" in js
    assert "canonical-row replay NOT MEASURED" in js
    assert 'loadEndpoint("marketTapeStatus", API.marketTapeStatus)' in js
    assert 'loadEndpoint("coldArchiveStatus", API.coldArchiveStatus)' in js
