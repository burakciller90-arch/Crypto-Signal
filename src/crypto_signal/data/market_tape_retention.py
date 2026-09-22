from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_signal.data.market_tape_runtime import (
    DEFAULT_MARKET_TAPE_CAPACITY_POLICY,
    MarketTapeCapacityPolicy,
    MarketTapeCapacitySnapshot,
    measure_market_tape_capacity,
)

_GIB = 1024**3
_NORMALIZED_DB = "market_tape.sqlite3"
_RAW_DB = "raw_market_tape.sqlite3"
_ARCHIVE_DIR = "archive"
_MANIFEST = "manifest.json"
_TRANSIENT_SUFFIXES = ("-wal", "-shm")


@dataclass(frozen=True, slots=True)
class MarketTapeRetentionPolicy:
    active_generation_max_bytes: int = 25 * _GIB
    max_sealed_generations: int = 10
    minimum_sealed_generations_under_pressure: int = 1

    def __post_init__(self) -> None:
        if self.active_generation_max_bytes <= 0:
            raise ValueError("active generation max bytes must be positive")
        if self.max_sealed_generations <= 0:
            raise ValueError("max sealed generations must be positive")
        if not (
            0
            <= self.minimum_sealed_generations_under_pressure
            <= self.max_sealed_generations
        ):
            raise ValueError(
                "minimum sealed generations under pressure must be inside "
                "[0,max_sealed_generations]"
            )


DEFAULT_MARKET_TAPE_RETENTION_POLICY = MarketTapeRetentionPolicy()


@dataclass(frozen=True, slots=True)
class SealedMarketTapeGeneration:
    generation_id: str
    path: Path
    normalized_sha256: str
    raw_sha256: str
    normalized_bytes: int
    raw_bytes: int

    def __post_init__(self) -> None:
        if not self.generation_id or "/" in self.generation_id:
            raise ValueError("invalid Market Tape generation id")
        for value in (self.normalized_sha256, self.raw_sha256):
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError("sealed Market Tape hash must be SHA256")
        if self.normalized_bytes <= 0 or self.raw_bytes <= 0:
            raise ValueError("sealed Market Tape files must be non-empty")


def active_generation_bytes(market_tape_dir: Path) -> int:
    return sum(
        path.stat().st_size
        for name in (_NORMALIZED_DB, _RAW_DB)
        for path in _active_file_family(market_tape_dir / name)
        if path.exists() and path.is_file()
    )


def seal_active_generation(
    *,
    market_tape_dir: Path,
    generation_id: str | None = None,
) -> SealedMarketTapeGeneration:
    normalized = market_tape_dir / _NORMALIZED_DB
    raw = market_tape_dir / _RAW_DB
    if not normalized.is_file() or not raw.is_file():
        raise ValueError("both active Market Tape databases are required to seal")

    _checkpoint_and_verify(normalized)
    _checkpoint_and_verify(raw)
    _require_no_live_wal(normalized)
    _require_no_live_wal(raw)

    generation = generation_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not generation or "/" in generation:
        raise ValueError("invalid Market Tape generation id")

    archive_root = market_tape_dir / _ARCHIVE_DIR
    destination = archive_root / generation
    if destination.exists():
        raise ValueError("Market Tape generation already exists")
    destination.mkdir(parents=True)

    normalized_meta = _database_metadata(normalized, raw=False)
    raw_meta = _database_metadata(raw, raw=True)

    archived_normalized = destination / _NORMALIZED_DB
    archived_raw = destination / _RAW_DB
    moved_normalized = False
    moved_raw = False
    try:
        os.replace(normalized, archived_normalized)
        moved_normalized = True
        os.replace(raw, archived_raw)
        moved_raw = True

        normalized_hash = _sha256_file(archived_normalized)
        raw_hash = _sha256_file(archived_raw)
        manifest = {
            "schema_version": "market-tape-sealed-generation-v1/1",
            "generation_id": generation,
            "sealed_at_utc": datetime.now(UTC).isoformat(),
            "normalized": {
                **normalized_meta,
                "filename": _NORMALIZED_DB,
                "sha256": normalized_hash,
                "bytes": archived_normalized.stat().st_size,
            },
            "raw": {
                **raw_meta,
                "filename": _RAW_DB,
                "sha256": raw_hash,
                "bytes": archived_raw.stat().st_size,
            },
        }
        _write_manifest_atomic(destination / _MANIFEST, manifest)
    except Exception:
        if moved_raw and archived_raw.exists() and not raw.exists():
            os.replace(archived_raw, raw)
        if (
            moved_normalized
            and archived_normalized.exists()
            and not normalized.exists()
        ):
            os.replace(archived_normalized, normalized)
        shutil.rmtree(destination, ignore_errors=True)
        raise

    return SealedMarketTapeGeneration(
        generation_id=generation,
        path=destination,
        normalized_sha256=normalized_hash,
        raw_sha256=raw_hash,
        normalized_bytes=archived_normalized.stat().st_size,
        raw_bytes=archived_raw.stat().st_size,
    )


def list_sealed_generations(
    market_tape_dir: Path,
) -> tuple[SealedMarketTapeGeneration, ...]:
    archive_root = market_tape_dir / _ARCHIVE_DIR
    if not archive_root.exists():
        return ()
    if not archive_root.is_dir():
        raise ValueError("Market Tape archive path must be a directory")

    generations = tuple(
        _generation_from_manifest(path)
        for path in sorted(archive_root.iterdir())
        if path.is_dir()
    )
    ids = [item.generation_id for item in generations]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate sealed Market Tape generation id")
    return generations


def enforce_generation_retention(
    *,
    market_tape_dir: Path,
    policy: MarketTapeRetentionPolicy = DEFAULT_MARKET_TAPE_RETENTION_POLICY,
) -> tuple[str, ...]:
    generations = list(list_sealed_generations(market_tape_dir))
    removed: list[str] = []
    while len(generations) > policy.max_sealed_generations:
        oldest = generations.pop(0)
        _delete_verified_generation(oldest)
        removed.append(oldest.generation_id)
    return tuple(removed)


def reclaim_for_capacity(
    *,
    market_tape_dir: Path,
    volume_path: Path,
    capacity_policy: MarketTapeCapacityPolicy = (
        DEFAULT_MARKET_TAPE_CAPACITY_POLICY
    ),
    retention_policy: MarketTapeRetentionPolicy = (
        DEFAULT_MARKET_TAPE_RETENTION_POLICY
    ),
) -> tuple[MarketTapeCapacitySnapshot, tuple[str, ...]]:
    snapshot = measure_market_tape_capacity(
        market_tape_dir=market_tape_dir,
        volume_path=volume_path,
        policy=capacity_policy,
    )
    generations = list(list_sealed_generations(market_tape_dir))
    removed: list[str] = []

    while (
        not snapshot.can_collect
        and len(generations)
        > retention_policy.minimum_sealed_generations_under_pressure
    ):
        oldest = generations.pop(0)
        _delete_verified_generation(oldest)
        removed.append(oldest.generation_id)
        snapshot = measure_market_tape_capacity(
            market_tape_dir=market_tape_dir,
            volume_path=volume_path,
            policy=capacity_policy,
        )
    return snapshot, tuple(removed)


def verify_sealed_generation(generation: SealedMarketTapeGeneration) -> bool:
    normalized = generation.path / _NORMALIZED_DB
    raw = generation.path / _RAW_DB
    return (
        normalized.is_file()
        and raw.is_file()
        and normalized.stat().st_size == generation.normalized_bytes
        and raw.stat().st_size == generation.raw_bytes
        and _sha256_file(normalized) == generation.normalized_sha256
        and _sha256_file(raw) == generation.raw_sha256
        and _quick_check(normalized)
        and _quick_check(raw)
    )


def _delete_verified_generation(generation: SealedMarketTapeGeneration) -> None:
    if not verify_sealed_generation(generation):
        raise ValueError(
            f"sealed Market Tape generation failed verification: "
            f"{generation.generation_id}"
        )
    shutil.rmtree(generation.path)


def _generation_from_manifest(path: Path) -> SealedMarketTapeGeneration:
    manifest_path = path / _MANIFEST
    if not manifest_path.is_file():
        raise ValueError(f"sealed Market Tape manifest missing: {path.name}")
    payload = json.loads(manifest_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("sealed Market Tape manifest must be an object")
    if payload.get("schema_version") != "market-tape-sealed-generation-v1/1":
        raise ValueError("unsupported sealed Market Tape manifest schema")
    if payload.get("generation_id") != path.name:
        raise ValueError("sealed Market Tape manifest generation mismatch")
    normalized = _mapping(payload.get("normalized"))
    raw = _mapping(payload.get("raw"))
    if normalized.get("filename") != _NORMALIZED_DB:
        raise ValueError("sealed normalized Market Tape filename mismatch")
    if raw.get("filename") != _RAW_DB:
        raise ValueError("sealed raw Market Tape filename mismatch")
    return SealedMarketTapeGeneration(
        generation_id=path.name,
        path=path,
        normalized_sha256=str(normalized["sha256"]),
        raw_sha256=str(raw["sha256"]),
        normalized_bytes=int(normalized["bytes"]),
        raw_bytes=int(raw["bytes"]),
    )


def _checkpoint_and_verify(path: Path) -> None:
    connection = sqlite3.connect(path, timeout=30.0)
    try:
        row = connection.execute("PRAGMA quick_check").fetchone()
        if row is None or str(row[0]) != "ok":
            raise ValueError(f"Market Tape quick_check failed before seal: {path}")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        row = connection.execute("PRAGMA quick_check").fetchone()
        if row is None or str(row[0]) != "ok":
            raise ValueError(f"Market Tape quick_check failed after checkpoint: {path}")
    finally:
        connection.close()


def _require_no_live_wal(path: Path) -> None:
    for suffix in _TRANSIENT_SUFFIXES:
        transient = Path(f"{path}{suffix}")
        if not transient.exists():
            continue
        if transient.stat().st_size:
            raise ValueError(
                f"Market Tape transient file still active during seal: {transient}"
            )
        transient.unlink()


def _database_metadata(path: Path, *, raw: bool) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10.0)
    try:
        connection.execute("PRAGMA query_only=ON")
        if raw:
            count, first_event, last_event = connection.execute(
                """
                SELECT COUNT(*), MIN(event_at_ms), MAX(event_at_ms)
                FROM raw_market_events
                """
            ).fetchone()
            return {
                "rows": int(count),
                "first_event_at_ms": (
                    None if first_event is None else int(first_event)
                ),
                "last_event_at_ms": (
                    None if last_event is None else int(last_event)
                ),
            }

        orderbooks = int(
            connection.execute(
                "SELECT COUNT(*) FROM market_tape_orderbooks"
            ).fetchone()[0]
        )
        trades = int(
            connection.execute(
                "SELECT COUNT(*) FROM market_tape_trades"
            ).fetchone()[0]
        )
        derivatives = int(
            connection.execute(
                "SELECT COUNT(*) FROM market_tape_derivatives"
            ).fetchone()[0]
        )
        first_event, last_event = connection.execute(
            """
            SELECT MIN(event_at_ms), MAX(event_at_ms)
            FROM (
                SELECT event_at_ms FROM market_tape_orderbooks
                UNION ALL
                SELECT event_at_ms FROM market_tape_trades
                UNION ALL
                SELECT event_at_ms FROM market_tape_derivatives
            )
            """
        ).fetchone()
        return {
            "orderbook_rows": orderbooks,
            "trade_rows": trades,
            "derivatives_rows": derivatives,
            "rows": orderbooks + trades + derivatives,
            "first_event_at_ms": (
                None if first_event is None else int(first_event)
            ),
            "last_event_at_ms": (
                None if last_event is None else int(last_event)
            ),
        }
    finally:
        connection.close()


def _quick_check(path: Path) -> bool:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10.0)
    try:
        row = connection.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]) == "ok"
    finally:
        connection.close()


def _active_file_family(path: Path) -> tuple[Path, ...]:
    return (
        path,
        Path(f"{path}-wal"),
        Path(f"{path}-shm"),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest_atomic(path: Path, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("sealed Market Tape manifest field must be an object")
    return value
