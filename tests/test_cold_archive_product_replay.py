from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from crypto_signal.product.market_tape_runtime import (
    read_cold_archive_runtime_truth,
)
from crypto_signal.product.web import create_app


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_rows_sha256(rows: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(
            (
                json.dumps(
                    row,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            ).encode()
        )
    return digest.hexdigest()


def _seed_partition(root: Path, *, index: int) -> Path:
    start = index * 3_600_000
    end = start + 3_600_000
    partition = root / f"partition={index:02d}"
    partition.mkdir(parents=True)

    row: dict[str, object] = {
        "event_identity": hashlib.sha256(
            f"raw-{index}".encode()
        ).hexdigest(),
        "exchange": "bybit",
        "channel": "publicTrade.BTCUSDT",
        "symbol": "BTCUSDT",
        "event_kind": "trade_batch",
        "source_timestamp_ms": start + 1_010,
        "event_at_ms": start + 1_000,
        "ingested_at_ms": start + 1_020,
        "sequence": index + 1,
        "update_id": 0,
        "payload_json": json.dumps(
            {"partition": index},
            sort_keys=True,
            separators=(",", ":"),
        ),
    }
    raw_path = partition / "raw.parquet"
    pq.write_table(pa.Table.from_pylist([row]), raw_path)
    raw_bytes = raw_path.read_bytes()
    empty_digest = hashlib.sha256(b"").hexdigest()

    manifest = {
        "schema_version": "market-tape-cold-parquet-v1/1",
        "partition_id": f"test-{index}",
        "window_start_ms": start,
        "window_end_ms": end,
        "compression": "zstd",
        "tables": {
            "raw": {
                "rows": 1,
                "filename": "raw.parquet",
                "bytes": len(raw_bytes),
                "file_sha256": _sha256_bytes(raw_bytes),
                "canonical_sha256": _canonical_rows_sha256([row]),
                "identity_column": "event_identity",
                "time_column": "event_at_ms",
            },
            "orderbooks": {
                "rows": 0,
                "filename": None,
                "bytes": 0,
                "file_sha256": None,
                "canonical_sha256": empty_digest,
                "identity_column": "snapshot_identity",
                "time_column": "event_at_ms",
            },
            "trades": {
                "rows": 0,
                "filename": None,
                "bytes": 0,
                "file_sha256": None,
                "canonical_sha256": empty_digest,
                "identity_column": "trade_identity",
                "time_column": "event_at_ms",
            },
            "derivatives": {
                "rows": 0,
                "filename": None,
                "bytes": 0,
                "file_sha256": None,
                "canonical_sha256": empty_digest,
                "identity_column": "observation_identity",
                "time_column": "event_at_ms",
            },
        },
    }
    (partition / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )
    return partition


def _all_file_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_cold_archive_product_replays_latest_partitions_when_pyarrow_exists(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cold"
    for index in range(3):
        _seed_partition(root, index=index)
    before = _all_file_bytes(root)

    snapshot = read_cold_archive_runtime_truth(
        root,
        verify_limit=3,
        canonical_replay_limit=2,
    )

    assert snapshot.partition_count == 3
    assert snapshot.verified_partition_count == 3
    assert snapshot.canonical_row_digest_replay == "VERIFIED"
    assert snapshot.canonical_replay_verified_partition_count == 2
    assert (
        snapshot.canonical_replay_scope
        == "LATEST_2_OF_3_FILE_VERIFIED_PARTITIONS_CANONICAL_ROW_SHA256"
    )
    assert snapshot.integrity_scope == "ALL_PARTITIONS_FILE_SHA256"
    assert snapshot.read_only_verified is True
    assert snapshot.production_authority is False
    assert snapshot.real_capital == 0
    assert _all_file_bytes(root) == before


def test_cold_archive_replay_limit_is_bounded_by_file_verified_scope(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cold"
    for index in range(3):
        _seed_partition(root, index=index)

    snapshot = read_cold_archive_runtime_truth(
        root,
        verify_limit=1,
        canonical_replay_limit=20,
    )

    assert snapshot.verified_partition_count == 1
    assert snapshot.canonical_row_digest_replay == "VERIFIED"
    assert snapshot.canonical_replay_verified_partition_count == 1
    assert (
        snapshot.canonical_replay_scope
        == "ALL_FILE_VERIFIED_PARTITIONS_CANONICAL_ROW_SHA256"
    )
    assert (
        snapshot.integrity_scope
        == "LATEST_1_OF_3_PARTITIONS_FILE_SHA256"
    )


def test_cold_archive_product_fails_closed_on_canonical_digest_tamper(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cold"
    for index in range(3):
        _seed_partition(root, index=index)
    latest = root / "partition=02" / "manifest.json"
    manifest = json.loads(latest.read_text(encoding="utf-8"))
    manifest["tables"]["raw"]["canonical_sha256"] = "0" * 64
    latest.write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="canonical digest mismatch"):
        read_cold_archive_runtime_truth(
            root,
            verify_limit=3,
            canonical_replay_limit=2,
        )


def test_cold_archive_endpoint_exposes_verified_canonical_replay(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cold"
    for index in range(3):
        _seed_partition(root, index=index)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            cold_archive_path=root,
        )
    )

    body = client.get(
        "/api/cold-archive/status"
        "?verify_limit=3&canonical_replay_limit=2"
    ).json()

    assert body["status"] == "ready"
    assert body["canonical_row_digest_replay"] == "VERIFIED"
    assert body["canonical_replay_verified_partition_count"] == 2
    assert (
        body["canonical_replay_scope"]
        == "LATEST_2_OF_3_FILE_VERIFIED_PARTITIONS_CANONICAL_ROW_SHA256"
    )
    assert body["snapshot"]["canonical_row_digest_replay"] == "VERIFIED"
    assert body["archive_process_status"] == "NOT_MEASURED"
    assert body["read_only"] is True
    assert body["real_capital"] == 0
