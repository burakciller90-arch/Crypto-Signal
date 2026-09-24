from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crypto_signal.data.market_tape_collector_runtime import (
    MarketTapeCollectorRuntimeStore,
    build_collector_heartbeat,
    build_collector_instance,
)
from crypto_signal.product.market_tape_runtime import (
    read_cold_archive_runtime_truth,
    read_market_tape_collector_runtime_truth,
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


def _seed_collector_runtime(
    path: Path,
    *,
    heartbeat_at_ms: int = 1_900,
    ingestion_at_ms: int | None = 1_850,
) -> None:
    store = MarketTapeCollectorRuntimeStore(path)
    instance = build_collector_instance(
        provider="bybit",
        source="market_tape_stream",
        symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        started_at_ms=1_000,
        process_id=321,
        runtime_nonce="test-runtime",
    )
    store.append_instance(instance)
    heartbeat = build_collector_heartbeat(
        instance_identity=instance.instance_identity,
        sequence_no=1,
        observed_at_ms=heartbeat_at_ms,
        last_successful_ingestion_ms=ingestion_at_ms,
        observed_messages_total=12 if ingestion_at_ms is not None else 0,
        normalized_rows_total=8 if ingestion_at_ms is not None else 0,
        raw_rows_total=12 if ingestion_at_ms is not None else 0,
    )
    store.append_heartbeat(heartbeat)


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


def test_market_tape_live_reader_uses_snapshot_bound_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    _seed_market_tape(path)
    monkeypatch.setattr(
        "crypto_signal.product.market_tape_runtime.time.time_ns",
        lambda: 2_000_000_000,
    )

    snapshot = read_market_tape_runtime_truth(
        path,
        observed_at_ms=None,
    )

    assert snapshot.latest_event_at_ms == 1_020
    assert snapshot.latest_event_age_ms == 980


def test_collector_live_reader_uses_snapshot_bound_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "collector_runtime.sqlite3"
    _seed_collector_runtime(path)
    monkeypatch.setattr(
        "crypto_signal.product.market_tape_runtime.time.time_ns",
        lambda: 2_000_000_000,
    )

    snapshot = read_market_tape_collector_runtime_truth(
        path,
        observed_at_ms=None,
        heartbeat_freshness_ms=500,
    )

    assert snapshot is not None
    assert snapshot.heartbeat_age_ms == 100
    assert snapshot.ingestion_age_ms == 150
    assert snapshot.process_evidence_status == "HEARTBEAT_FRESH"


def test_market_tape_explicit_historical_boundary_still_fails_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    _seed_market_tape(path)

    with pytest.raises(ValueError, match="future evidence"):
        read_market_tape_runtime_truth(
            path,
            observed_at_ms=1_000,
        )


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


def test_collector_runtime_reader_separates_heartbeat_and_ingestion_truth(
    tmp_path: Path,
) -> None:
    path = tmp_path / "collector_runtime.sqlite3"
    _seed_collector_runtime(path)
    before = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }

    fresh = read_market_tape_collector_runtime_truth(
        path,
        observed_at_ms=2_000,
        heartbeat_freshness_ms=500,
    )
    stale = read_market_tape_collector_runtime_truth(
        path,
        observed_at_ms=3_000,
        heartbeat_freshness_ms=500,
    )

    assert fresh is not None
    assert fresh.provider == "bybit"
    assert fresh.source == "market_tape_stream"
    assert fresh.symbols == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    assert fresh.process_evidence_status == "HEARTBEAT_FRESH"
    assert fresh.heartbeat_age_ms == 100
    assert fresh.last_successful_ingestion_ms == 1_850
    assert fresh.ingestion_age_ms == 150
    assert fresh.observed_messages_total == 12
    assert fresh.read_only_verified is True
    assert fresh.production_authority is False
    assert fresh.real_capital == 0

    assert stale is not None
    assert stale.process_evidence_status == "HEARTBEAT_STALE"
    assert stale.heartbeat_age_ms == 1_100
    assert stale.ingestion_age_ms == 1_150

    after = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }
    assert after == before


def test_collector_runtime_reader_preserves_no_ingestion_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "collector_runtime.sqlite3"
    _seed_collector_runtime(path, ingestion_at_ms=None)

    snapshot = read_market_tape_collector_runtime_truth(
        path,
        observed_at_ms=2_000,
    )

    assert snapshot is not None
    assert snapshot.process_evidence_status == "HEARTBEAT_FRESH"
    assert snapshot.last_successful_ingestion_ms is None
    assert snapshot.ingestion_age_ms is None
    assert snapshot.observed_messages_total == 0


def test_market_tape_endpoint_exposes_heartbeat_without_online_claim(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market_tape.sqlite3"
    collector_path = tmp_path / "collector_runtime.sqlite3"
    _seed_market_tape(market_path)
    _seed_collector_runtime(collector_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            market_tape_path=market_path,
            market_tape_collector_runtime_path=collector_path,
        )
    )

    body = client.get(
        "/api/market-tape-runtime/status?observed_at_ms=2000"
    ).json()

    assert body["status"] == "ready"
    assert body["collection_process_status"] == "HEARTBEAT_FRESH"
    assert body["collector_runtime"]["heartbeat_age_ms"] == 100
    assert body["collector_runtime"]["ingestion_age_ms"] == 150
    assert body["collector_runtime_reason"] is None
    assert body["online_status"] == "NOT_ASSERTED"
    assert body["read_only"] is True
    assert body["real_capital"] == 0


def test_market_tape_endpoint_marks_missing_collector_evidence_without_online_claim(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market_tape.sqlite3"
    collector_path = tmp_path / "missing-collector.sqlite3"
    _seed_market_tape(market_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            market_tape_path=market_path,
            market_tape_collector_runtime_path=collector_path,
        )
    )

    body = client.get(
        "/api/market-tape-runtime/status?observed_at_ms=2000"
    ).json()

    assert body["status"] == "ready"
    assert body["collection_process_status"] == "RUNTIME_EVIDENCE_MISSING"
    assert body["collector_runtime"] is None
    assert body["collector_runtime_reason"] == "collector_runtime_evidence_missing"
    assert body["online_status"] == "NOT_ASSERTED"


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


def test_market_tape_endpoint_default_now_is_reader_snapshot_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    _seed_market_tape(path, event_at_ms=1_780)
    monkeypatch.setattr(
        "crypto_signal.product.web.time.time_ns",
        lambda: 1_500_000_000,
    )
    monkeypatch.setattr(
        "crypto_signal.product.market_tape_runtime.time.time_ns",
        lambda: 2_000_000_000,
    )
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            market_tape_path=path,
        )
    )

    response = client.get("/api/market-tape-runtime/status")

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["latest_event_at_ms"] == 1_800
    assert body["snapshot"]["latest_event_age_ms"] == 200
    assert body["online_status"] == "NOT_ASSERTED"
    assert body["read_only"] is True
    assert body["real_capital"] == 0


def test_market_tape_endpoint_explicit_observation_remains_fail_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    _seed_market_tape(path, event_at_ms=1_780)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            market_tape_path=path,
        )
    )

    response = client.get(
        "/api/market-tape-runtime/status?observed_at_ms=1500"
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Market Tape contains future evidence at observation time"
    )


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
    monkeypatch,
) -> None:
    root = tmp_path / "cold"
    partition = _seed_cold_archive(root)
    monkeypatch.setattr(
        "crypto_signal.product.market_tape_runtime.importlib.util.find_spec",
        lambda name: None,
    )
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
    assert "collection_process_status" in js
    assert "HEARTBEAT_FRESH" in js
    assert "heartbeat age" in js
    assert "ingestion age" in js
    assert "canonical-row replay" in js
    assert "canonical_row_digest_replay" in js
    assert "replayed partitions" in js
    assert 'loadEndpoint("marketTapeStatus", API.marketTapeStatus)' in js
    assert 'loadEndpoint("coldArchiveStatus", API.coldArchiveStatus)' in js
