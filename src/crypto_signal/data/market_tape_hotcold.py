from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_GIB = 1024**3
_HOUR_MS = 60 * 60 * 1000


class MarketTapeHotColdDecision(StrEnum):
    COLLECT = "collect"
    HOT_CAP_REACHED = "hot_cap_reached"
    COLD_CAP_REACHED = "cold_cap_reached"
    FREE_SPACE_RESERVE_REACHED = "free_space_reserve_reached"


@dataclass(frozen=True, slots=True)
class MarketTapeHotColdPolicy:
    hot_retention_ms: int = 24 * _HOUR_MS
    late_arrival_grace_ms: int = 2 * _HOUR_MS
    partition_ms: int = _HOUR_MS
    hot_emergency_max_bytes: int = 25 * _GIB
    cold_max_bytes: int = 600 * _GIB
    min_free_bytes: int = 250 * _GIB
    max_archive_partitions_per_cycle: int = 6

    def __post_init__(self) -> None:
        if self.hot_retention_ms <= 0:
            raise ValueError("hot retention must be positive")
        if self.late_arrival_grace_ms < 0:
            raise ValueError("late-arrival grace cannot be negative")
        if self.partition_ms <= 0:
            raise ValueError("cold partition must be positive")
        if self.hot_retention_ms % self.partition_ms:
            raise ValueError("hot retention must align to cold partition size")
        if self.late_arrival_grace_ms % self.partition_ms:
            raise ValueError("late-arrival grace must align to cold partition size")
        if self.hot_emergency_max_bytes <= 0:
            raise ValueError("hot emergency cap must be positive")
        if self.cold_max_bytes <= 0:
            raise ValueError("cold cap must be positive")
        if self.min_free_bytes <= 0:
            raise ValueError("free-space reserve must be positive")
        if self.max_archive_partitions_per_cycle <= 0:
            raise ValueError("max archive partitions per cycle must be positive")


DEFAULT_MARKET_TAPE_HOTCOLD_POLICY = MarketTapeHotColdPolicy()


@dataclass(frozen=True, slots=True)
class MarketTapeHotColdSnapshot:
    hot_bytes: int
    cold_bytes: int
    free_bytes: int
    decision: MarketTapeHotColdDecision

    def __post_init__(self) -> None:
        if min(self.hot_bytes, self.cold_bytes, self.free_bytes) < 0:
            raise ValueError("hot/cold capacity values cannot be negative")

    @property
    def can_collect(self) -> bool:
        return self.decision is MarketTapeHotColdDecision.COLLECT


def archive_before_ms(
    *,
    now_ms: int,
    policy: MarketTapeHotColdPolicy = DEFAULT_MARKET_TAPE_HOTCOLD_POLICY,
) -> int:
    if now_ms < 0:
        raise ValueError("now_ms cannot be negative")
    cutoff = (
        now_ms
        - policy.hot_retention_ms
        - policy.late_arrival_grace_ms
    )
    if cutoff <= 0:
        return 0
    return (cutoff // policy.partition_ms) * policy.partition_ms


def evaluate_hotcold_capacity(
    *,
    hot_bytes: int,
    cold_bytes: int,
    free_bytes: int,
    policy: MarketTapeHotColdPolicy = DEFAULT_MARKET_TAPE_HOTCOLD_POLICY,
) -> MarketTapeHotColdSnapshot:
    if min(hot_bytes, cold_bytes, free_bytes) < 0:
        raise ValueError("hot/cold capacity inputs cannot be negative")

    if free_bytes <= policy.min_free_bytes:
        decision = MarketTapeHotColdDecision.FREE_SPACE_RESERVE_REACHED
    elif cold_bytes >= policy.cold_max_bytes:
        decision = MarketTapeHotColdDecision.COLD_CAP_REACHED
    elif hot_bytes >= policy.hot_emergency_max_bytes:
        decision = MarketTapeHotColdDecision.HOT_CAP_REACHED
    else:
        decision = MarketTapeHotColdDecision.COLLECT

    return MarketTapeHotColdSnapshot(
        hot_bytes=hot_bytes,
        cold_bytes=cold_bytes,
        free_bytes=free_bytes,
        decision=decision,
    )


def measure_hotcold_capacity(
    *,
    hot_dir: Path,
    cold_dir: Path,
    volume_path: Path,
    policy: MarketTapeHotColdPolicy = DEFAULT_MARKET_TAPE_HOTCOLD_POLICY,
) -> MarketTapeHotColdSnapshot:
    return evaluate_hotcold_capacity(
        hot_bytes=directory_file_bytes(hot_dir),
        cold_bytes=directory_file_bytes(cold_dir),
        free_bytes=shutil.disk_usage(volume_path).free,
        policy=policy,
    )


def directory_file_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if not path.is_dir():
        raise ValueError(f"capacity path must be a directory: {path}")
    return sum(
        item.stat().st_size
        for item in path.rglob("*")
        if item.is_file()
    )
