from __future__ import annotations

from pathlib import Path

import pytest

from crypto_signal.data.market_tape_hotcold import (
    MarketTapeHotColdDecision,
    MarketTapeHotColdPolicy,
    archive_before_ms,
    evaluate_archive_headroom,
    evaluate_hotcold_capacity,
    measure_hotcold_capacity,
)

HOUR_MS = 60 * 60 * 1000


def _policy(**overrides: int) -> MarketTapeHotColdPolicy:
    values = {
        "hot_retention_ms": 24 * HOUR_MS,
        "late_arrival_grace_ms": 2 * HOUR_MS,
        "partition_ms": HOUR_MS,
        "hot_emergency_max_bytes": 25_000,
        "cold_max_bytes": 600_000,
        "min_free_bytes": 250_000,
        "max_archive_partitions_per_cycle": 6,
    }
    values.update(overrides)
    return MarketTapeHotColdPolicy(**values)


def test_archive_cutoff_keeps_24h_hot_plus_2h_grace_and_aligns_hour() -> None:
    now_ms = 100 * HOUR_MS + 37 * 60 * 1000

    assert archive_before_ms(now_ms=now_ms, policy=_policy()) == 74 * HOUR_MS


def test_archive_cutoff_never_goes_negative() -> None:
    assert archive_before_ms(now_ms=HOUR_MS, policy=_policy()) == 0


@pytest.mark.parametrize(
    ("hot_bytes", "cold_bytes", "free_bytes", "expected"),
    [
        (24_999, 599_999, 250_001, MarketTapeHotColdDecision.COLLECT),
        (25_000, 0, 999_999, MarketTapeHotColdDecision.HOT_CAP_REACHED),
        (0, 600_000, 999_999, MarketTapeHotColdDecision.COLD_CAP_REACHED),
        (
            25_000,
            600_000,
            250_000,
            MarketTapeHotColdDecision.FREE_SPACE_RESERVE_REACHED,
        ),
    ],
)
def test_hotcold_capacity_is_fail_closed(
    hot_bytes: int,
    cold_bytes: int,
    free_bytes: int,
    expected: MarketTapeHotColdDecision,
) -> None:
    snapshot = evaluate_hotcold_capacity(
        hot_bytes=hot_bytes,
        cold_bytes=cold_bytes,
        free_bytes=free_bytes,
        policy=_policy(),
    )

    assert snapshot.decision is expected
    assert snapshot.can_collect is (expected is MarketTapeHotColdDecision.COLLECT)


def test_measurement_separates_hot_and_cold_bytes(tmp_path: Path) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    hot.mkdir()
    cold.mkdir()
    (hot / "a.sqlite3").write_bytes(b"x" * 100)
    (hot / "a.sqlite3-wal").write_bytes(b"x" * 50)
    (cold / "hour.parquet").write_bytes(b"x" * 200)

    snapshot = measure_hotcold_capacity(
        hot_dir=hot,
        cold_dir=cold,
        volume_path=tmp_path,
        policy=_policy(
            hot_emergency_max_bytes=1_000_000,
            cold_max_bytes=1_000_000,
            min_free_bytes=1,
        ),
    )

    assert snapshot.hot_bytes == 150
    assert snapshot.cold_bytes == 200
    assert snapshot.can_collect is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hot_retention_ms": 0},
        {"late_arrival_grace_ms": -1},
        {"partition_ms": 0},
        {"hot_emergency_max_bytes": 0},
        {"cold_max_bytes": 0},
        {"min_free_bytes": 0},
        {"max_archive_partitions_per_cycle": 0},
        {"hot_retention_ms": 25 * HOUR_MS + 1},
        {"late_arrival_grace_ms": HOUR_MS + 1},
    ],
)
def test_hotcold_policy_validation(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        _policy(**kwargs)


def test_archive_headroom_is_more_conservative_than_current_capacity() -> None:
    policy = _policy(
        hot_emergency_max_bytes=100,
        cold_max_bytes=1_000,
        min_free_bytes=250,
    )
    current = evaluate_hotcold_capacity(
        hot_bytes=100,
        cold_bytes=850,
        free_bytes=351,
        policy=policy,
    )
    assert current.decision is MarketTapeHotColdDecision.HOT_CAP_REACHED

    synthetic_collectable = type(current)(
        hot_bytes=99,
        cold_bytes=850,
        free_bytes=351,
        decision=MarketTapeHotColdDecision.COLLECT,
    )
    assert (
        evaluate_archive_headroom(
            snapshot=synthetic_collectable,
            policy=policy,
        )
        is MarketTapeHotColdDecision.FREE_SPACE_RESERVE_REACHED
    )


def test_archive_headroom_blocks_cold_cap_before_duplicate_write() -> None:
    policy = _policy(
        hot_emergency_max_bytes=1_000,
        cold_max_bytes=1_000,
        min_free_bytes=1,
    )
    snapshot = evaluate_hotcold_capacity(
        hot_bytes=100,
        cold_bytes=901,
        free_bytes=10_000,
        policy=policy,
    )
    assert snapshot.can_collect is True
    assert (
        evaluate_archive_headroom(snapshot=snapshot, policy=policy)
        is MarketTapeHotColdDecision.COLD_CAP_REACHED
    )
