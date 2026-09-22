from __future__ import annotations

from pathlib import Path

import pytest

from crypto_signal.data.market_tape_runtime import (
    MarketTapeCapacityDecision,
    MarketTapeCapacityPolicy,
    evaluate_market_tape_capacity,
    measure_market_tape_capacity,
)


def _policy(**overrides: int) -> MarketTapeCapacityPolicy:
    payload = {
        "max_tape_bytes": 1_000,
        "min_free_bytes": 2_000,
        "chunk_messages": 100,
        "guard_sleep_seconds": 30,
    }
    payload.update(overrides)
    return MarketTapeCapacityPolicy(**payload)


def test_capacity_allows_collection_below_both_guards() -> None:
    snapshot = evaluate_market_tape_capacity(
        tape_bytes=900,
        free_bytes=2_001,
        policy=_policy(),
    )

    assert snapshot.can_collect is True
    assert snapshot.decision is MarketTapeCapacityDecision.COLLECT


@pytest.mark.parametrize("tape_bytes", [1_000, 1_001])
def test_capacity_stops_at_or_above_hard_tape_cap(tape_bytes: int) -> None:
    snapshot = evaluate_market_tape_capacity(
        tape_bytes=tape_bytes,
        free_bytes=5_000,
        policy=_policy(),
    )

    assert snapshot.can_collect is False
    assert snapshot.decision is MarketTapeCapacityDecision.TAPE_CAP_REACHED


@pytest.mark.parametrize("free_bytes", [0, 1_999, 2_000])
def test_capacity_stops_at_or_below_free_space_reserve(free_bytes: int) -> None:
    snapshot = evaluate_market_tape_capacity(
        tape_bytes=100,
        free_bytes=free_bytes,
        policy=_policy(),
    )

    assert snapshot.can_collect is False
    assert snapshot.decision is MarketTapeCapacityDecision.FREE_SPACE_RESERVE_REACHED


def test_free_space_guard_has_precedence_when_both_limits_are_hit() -> None:
    snapshot = evaluate_market_tape_capacity(
        tape_bytes=1_500,
        free_bytes=1_000,
        policy=_policy(),
    )

    assert snapshot.decision is MarketTapeCapacityDecision.FREE_SPACE_RESERVE_REACHED


def test_measurement_counts_sqlite_wal_and_other_runtime_files(
    tmp_path: Path,
) -> None:
    tape_dir = tmp_path / "market_tape"
    tape_dir.mkdir()
    (tape_dir / "market_tape.sqlite3").write_bytes(b"x" * 100)
    (tape_dir / "market_tape.sqlite3-wal").write_bytes(b"x" * 200)
    (tape_dir / "raw_market_tape.sqlite3").write_bytes(b"x" * 300)
    (tape_dir / "market_tape_stream.lock").write_bytes(b"")

    snapshot = measure_market_tape_capacity(
        market_tape_dir=tape_dir,
        volume_path=tmp_path,
        policy=_policy(max_tape_bytes=1_000_000, min_free_bytes=1),
    )

    assert snapshot.tape_bytes == 600
    assert snapshot.can_collect is True


def test_policy_validation_fails_closed() -> None:
    with pytest.raises(ValueError, match="max_tape_bytes"):
        MarketTapeCapacityPolicy(max_tape_bytes=0)

    with pytest.raises(ValueError, match="min_free_bytes"):
        MarketTapeCapacityPolicy(min_free_bytes=0)

    with pytest.raises(ValueError, match="chunk_messages"):
        MarketTapeCapacityPolicy(chunk_messages=0)

    with pytest.raises(ValueError, match="guard_sleep_seconds"):
        MarketTapeCapacityPolicy(guard_sleep_seconds=0)


def test_capacity_rejects_negative_observations() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        evaluate_market_tape_capacity(
            tape_bytes=-1,
            free_bytes=1,
            policy=_policy(),
        )
