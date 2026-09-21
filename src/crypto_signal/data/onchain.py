from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_sha256


class BitcoinNetwork(StrEnum):
    MAINNET = "bitcoin_mainnet"


@dataclass(frozen=True, slots=True)
class BitcoinBlockRecord:
    record_identity: str
    block_hash: str
    height: int
    header_timestamp_ms: int
    median_time_ms: int
    tx_count: int
    size_bytes: int
    weight_units: int
    difficulty: Decimal
    previous_block_hash: str

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "bitcoin block record identity")
        _require_sha256(self.block_hash, "bitcoin block hash")
        _require_sha256(self.previous_block_hash, "bitcoin previous block hash")
        if self.height < 0:
            raise ValueError("bitcoin block height must be non-negative")
        if self.header_timestamp_ms < 0 or self.median_time_ms < 0:
            raise ValueError("bitcoin block timestamps must be non-negative")
        if self.median_time_ms >= self.header_timestamp_ms:
            raise ValueError("bitcoin block median time must predate header time")
        if self.tx_count <= 0:
            raise ValueError("bitcoin block must contain at least one transaction")
        if self.size_bytes <= 0:
            raise ValueError("bitcoin block size must be positive")
        if not 0 < self.weight_units <= 4_000_000:
            raise ValueError("bitcoin block weight must be inside (0, 4000000]")
        if (
            self.difficulty.is_nan()
            or self.difficulty.is_infinite()
            or self.difficulty <= Decimal(0)
        ):
            raise ValueError("bitcoin block difficulty must be finite and positive")
        if self.record_identity != canonical_sha256(bitcoin_block_payload(self)):
            raise ValueError("bitcoin block record identity mismatch")


@dataclass(frozen=True, slots=True)
class BitcoinBlockWindowObservation:
    observation_identity: str
    network: BitcoinNetwork
    observed_at_ms: int
    tip_height: int
    tip_hash: str
    blocks: tuple[BitcoinBlockRecord, ...]
    source: DataSource
    adapter_version: str
    temporal_semantic: str = "ingestion_time_snapshot"

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "bitcoin window observation identity")
        _require_sha256(self.tip_hash, "bitcoin tip hash")
        if self.observed_at_ms < 0:
            raise ValueError("bitcoin window observed_at_ms must be non-negative")
        if self.tip_height < 0:
            raise ValueError("bitcoin tip height must be non-negative")
        if self.temporal_semantic != "ingestion_time_snapshot":
            raise ValueError("unsupported bitcoin observation temporal semantic")
        if not self.blocks:
            raise ValueError("bitcoin block window cannot be empty")
        if len(self.blocks) > 10:
            raise ValueError("bitcoin block window cannot exceed ten blocks")
        if self.blocks[0].height != self.tip_height:
            raise ValueError("bitcoin block window must start at the declared tip")
        if self.blocks[0].block_hash != self.tip_hash:
            raise ValueError("bitcoin block window tip hash mismatch")
        if any(
            left.height <= right.height
            for left, right in zip(self.blocks, self.blocks[1:], strict=False)
        ):
            raise ValueError("bitcoin block window must be strictly height-descending")
        if not self.adapter_version.strip():
            raise ValueError("bitcoin adapter_version must be non-empty")
        if self.observation_identity != canonical_sha256(
            bitcoin_window_payload(self)
        ):
            raise ValueError("bitcoin block window observation identity mismatch")


def build_bitcoin_block_record(
    *,
    block_hash: str,
    height: int,
    header_timestamp_ms: int,
    median_time_ms: int,
    tx_count: int,
    size_bytes: int,
    weight_units: int,
    difficulty: Decimal,
    previous_block_hash: str,
) -> BitcoinBlockRecord:
    payload = {
        "block_hash": block_hash,
        "difficulty": difficulty,
        "header_timestamp_ms": header_timestamp_ms,
        "height": height,
        "median_time_ms": median_time_ms,
        "previous_block_hash": previous_block_hash,
        "size_bytes": size_bytes,
        "tx_count": tx_count,
        "weight_units": weight_units,
    }
    return BitcoinBlockRecord(
        record_identity=canonical_sha256(payload),
        block_hash=block_hash,
        height=height,
        header_timestamp_ms=header_timestamp_ms,
        median_time_ms=median_time_ms,
        tx_count=tx_count,
        size_bytes=size_bytes,
        weight_units=weight_units,
        difficulty=difficulty,
        previous_block_hash=previous_block_hash,
    )


def build_bitcoin_block_window_observation(
    *,
    network: BitcoinNetwork,
    observed_at_ms: int,
    tip_height: int,
    tip_hash: str,
    blocks: tuple[BitcoinBlockRecord, ...],
    source: DataSource,
    adapter_version: str,
) -> BitcoinBlockWindowObservation:
    payload = {
        "adapter_version": adapter_version,
        "block_identities": [item.record_identity for item in blocks],
        "network": network,
        "observed_at_ms": observed_at_ms,
        "source": source,
        "temporal_semantic": "ingestion_time_snapshot",
        "tip_hash": tip_hash,
        "tip_height": tip_height,
    }
    return BitcoinBlockWindowObservation(
        observation_identity=canonical_sha256(payload),
        network=network,
        observed_at_ms=observed_at_ms,
        tip_height=tip_height,
        tip_hash=tip_hash,
        blocks=blocks,
        source=source,
        adapter_version=adapter_version,
    )


def bitcoin_block_payload(block: BitcoinBlockRecord) -> dict[str, object]:
    return {
        "block_hash": block.block_hash,
        "difficulty": block.difficulty,
        "header_timestamp_ms": block.header_timestamp_ms,
        "height": block.height,
        "median_time_ms": block.median_time_ms,
        "previous_block_hash": block.previous_block_hash,
        "size_bytes": block.size_bytes,
        "tx_count": block.tx_count,
        "weight_units": block.weight_units,
    }


def bitcoin_window_payload(
    observation: BitcoinBlockWindowObservation,
) -> dict[str, object]:
    return {
        "adapter_version": observation.adapter_version,
        "block_identities": [item.record_identity for item in observation.blocks],
        "network": observation.network,
        "observed_at_ms": observation.observed_at_ms,
        "source": observation.source,
        "temporal_semantic": observation.temporal_semantic,
        "tip_hash": observation.tip_hash,
        "tip_height": observation.tip_height,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
