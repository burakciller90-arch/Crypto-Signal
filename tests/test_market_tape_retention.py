from __future__ import annotations

from pathlib import Path

import pytest

from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_retention import (
    MarketTapeRetentionPolicy,
    active_generation_bytes,
    enforce_generation_retention,
    list_sealed_generations,
    reclaim_for_capacity,
    seal_active_generation,
    verify_sealed_generation,
)
from crypto_signal.data.market_tape_runtime import MarketTapeCapacityPolicy
from crypto_signal.data.raw_market_tape import RawMarketTapeStore


def _initialize_active(tape_dir: Path) -> None:
    MarketTapeStore(tape_dir / "market_tape.sqlite3").initialize()
    RawMarketTapeStore(tape_dir / "raw_market_tape.sqlite3").initialize()


def test_seal_moves_verified_active_pair_and_writes_manifest(tmp_path: Path) -> None:
    tape_dir = tmp_path / "market_tape"
    tape_dir.mkdir()
    _initialize_active(tape_dir)

    assert active_generation_bytes(tape_dir) > 0

    sealed = seal_active_generation(
        market_tape_dir=tape_dir,
        generation_id="20260922T160000Z",
    )

    assert not (tape_dir / "market_tape.sqlite3").exists()
    assert not (tape_dir / "raw_market_tape.sqlite3").exists()
    assert (sealed.path / "manifest.json").is_file()
    assert verify_sealed_generation(sealed) is True
    assert list_sealed_generations(tape_dir) == (sealed,)


def test_generation_retention_deletes_only_oldest_verified_pairs(
    tmp_path: Path,
) -> None:
    tape_dir = tmp_path / "market_tape"
    tape_dir.mkdir()
    for generation in (
        "20260920T000000Z",
        "20260921T000000Z",
        "20260922T000000Z",
    ):
        _initialize_active(tape_dir)
        seal_active_generation(
            market_tape_dir=tape_dir,
            generation_id=generation,
        )

    removed = enforce_generation_retention(
        market_tape_dir=tape_dir,
        policy=MarketTapeRetentionPolicy(
            active_generation_max_bytes=1,
            max_sealed_generations=2,
            minimum_sealed_generations_under_pressure=1,
        ),
    )

    assert removed == ("20260920T000000Z",)
    assert tuple(
        item.generation_id for item in list_sealed_generations(tape_dir)
    ) == ("20260921T000000Z", "20260922T000000Z")


def test_tampered_generation_fails_closed_before_retention_delete(
    tmp_path: Path,
) -> None:
    tape_dir = tmp_path / "market_tape"
    tape_dir.mkdir()
    for generation in ("20260920T000000Z", "20260921T000000Z"):
        _initialize_active(tape_dir)
        seal_active_generation(
            market_tape_dir=tape_dir,
            generation_id=generation,
        )

    oldest = list_sealed_generations(tape_dir)[0]
    with (oldest.path / "raw_market_tape.sqlite3").open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(ValueError, match="failed verification"):
        enforce_generation_retention(
            market_tape_dir=tape_dir,
            policy=MarketTapeRetentionPolicy(
                active_generation_max_bytes=1,
                max_sealed_generations=1,
                minimum_sealed_generations_under_pressure=0,
            ),
        )

    assert oldest.path.exists()


def test_capacity_pressure_prunes_verified_oldest_until_collectable(
    tmp_path: Path,
) -> None:
    tape_dir = tmp_path / "market_tape"
    tape_dir.mkdir()
    for generation in (
        "20260920T000000Z",
        "20260921T000000Z",
        "20260922T000000Z",
    ):
        _initialize_active(tape_dir)
        seal_active_generation(
            market_tape_dir=tape_dir,
            generation_id=generation,
        )

    generations = list_sealed_generations(tape_dir)
    total = sum(
        sum(
            file.stat().st_size
            for file in generation.path.rglob("*")
            if file.is_file()
        )
        for generation in generations
    )
    oldest_bytes = sum(
        file.stat().st_size
        for file in generations[0].path.rglob("*")
        if file.is_file()
    )

    snapshot, removed = reclaim_for_capacity(
        market_tape_dir=tape_dir,
        volume_path=tmp_path,
        capacity_policy=MarketTapeCapacityPolicy(
            max_tape_bytes=total - oldest_bytes + 1,
            min_free_bytes=1,
            chunk_messages=10,
            guard_sleep_seconds=1,
        ),
        retention_policy=MarketTapeRetentionPolicy(
            active_generation_max_bytes=1,
            max_sealed_generations=3,
            minimum_sealed_generations_under_pressure=1,
        ),
    )

    assert removed == ("20260920T000000Z",)
    assert snapshot.can_collect is True
    assert tuple(
        item.generation_id for item in list_sealed_generations(tape_dir)
    ) == ("20260921T000000Z", "20260922T000000Z")


def test_retention_policy_validation() -> None:
    with pytest.raises(ValueError, match="active generation"):
        MarketTapeRetentionPolicy(active_generation_max_bytes=0)
    with pytest.raises(ValueError, match="max sealed"):
        MarketTapeRetentionPolicy(max_sealed_generations=0)
    with pytest.raises(ValueError, match="minimum sealed"):
        MarketTapeRetentionPolicy(
            max_sealed_generations=1,
            minimum_sealed_generations_under_pressure=2,
        )
