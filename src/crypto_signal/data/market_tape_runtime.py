from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_GIB = 1024**3


class MarketTapeCapacityDecision(StrEnum):
    COLLECT = "collect"
    TAPE_CAP_REACHED = "tape_cap_reached"
    FREE_SPACE_RESERVE_REACHED = "free_space_reserve_reached"


@dataclass(frozen=True, slots=True)
class MarketTapeCapacityPolicy:
    max_tape_bytes: int = 100 * _GIB
    min_free_bytes: int = 200 * _GIB
    chunk_messages: int = 100_000
    guard_sleep_seconds: int = 300

    def __post_init__(self) -> None:
        if self.max_tape_bytes <= 0:
            raise ValueError("Market Tape max_tape_bytes must be positive")
        if self.min_free_bytes <= 0:
            raise ValueError("Market Tape min_free_bytes must be positive")
        if self.chunk_messages <= 0:
            raise ValueError("Market Tape chunk_messages must be positive")
        if self.guard_sleep_seconds <= 0:
            raise ValueError("Market Tape guard_sleep_seconds must be positive")


DEFAULT_MARKET_TAPE_CAPACITY_POLICY = MarketTapeCapacityPolicy()


@dataclass(frozen=True, slots=True)
class MarketTapeCapacitySnapshot:
    tape_bytes: int
    free_bytes: int
    decision: MarketTapeCapacityDecision

    def __post_init__(self) -> None:
        if self.tape_bytes < 0:
            raise ValueError("Market Tape tape_bytes cannot be negative")
        if self.free_bytes < 0:
            raise ValueError("Market Tape free_bytes cannot be negative")

    @property
    def can_collect(self) -> bool:
        return self.decision is MarketTapeCapacityDecision.COLLECT


def evaluate_market_tape_capacity(
    *,
    tape_bytes: int,
    free_bytes: int,
    policy: MarketTapeCapacityPolicy = DEFAULT_MARKET_TAPE_CAPACITY_POLICY,
) -> MarketTapeCapacitySnapshot:
    if tape_bytes < 0 or free_bytes < 0:
        raise ValueError("Market Tape capacity inputs cannot be negative")

    if free_bytes <= policy.min_free_bytes:
        decision = MarketTapeCapacityDecision.FREE_SPACE_RESERVE_REACHED
    elif tape_bytes >= policy.max_tape_bytes:
        decision = MarketTapeCapacityDecision.TAPE_CAP_REACHED
    else:
        decision = MarketTapeCapacityDecision.COLLECT

    return MarketTapeCapacitySnapshot(
        tape_bytes=tape_bytes,
        free_bytes=free_bytes,
        decision=decision,
    )


def measure_market_tape_capacity(
    *,
    market_tape_dir: Path,
    volume_path: Path,
    policy: MarketTapeCapacityPolicy = DEFAULT_MARKET_TAPE_CAPACITY_POLICY,
) -> MarketTapeCapacitySnapshot:
    tape_bytes = _directory_file_bytes(market_tape_dir)
    free_bytes = shutil.disk_usage(volume_path).free
    return evaluate_market_tape_capacity(
        tape_bytes=tape_bytes,
        free_bytes=free_bytes,
        policy=policy,
    )


def _directory_file_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if not path.is_dir():
        raise ValueError("Market Tape runtime path must be a directory")
    return sum(
        item.stat().st_size
        for item in path.iterdir()
        if item.is_file()
    )
