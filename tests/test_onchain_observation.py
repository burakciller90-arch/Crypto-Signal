from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.models import DataSource
from crypto_signal.data.onchain import (
    BitcoinNetwork,
    build_bitcoin_block_record,
    build_bitcoin_block_window_observation,
)


def _hash(height: int) -> str:
    return f"{height:064x}"


def _block(
    height: int,
    *,
    timestamp_ms: int | None = None,
    weight_units: int = 3_000_000,
):
    header_ms = (
        1_000_000 + height * 600_000
        if timestamp_ms is None
        else timestamp_ms
    )
    return build_bitcoin_block_record(
        block_hash=_hash(height),
        height=height,
        header_timestamp_ms=header_ms,
        median_time_ms=header_ms - 300_000,
        tx_count=2_000,
        size_bytes=1_500_000,
        weight_units=weight_units,
        difficulty=Decimal("123456.789"),
        previous_block_hash=_hash(height - 1),
    )


def _window(*, observed_at_ms: int = 900_000_000):
    blocks = tuple(_block(height) for height in range(1_000, 990, -1))
    return build_bitcoin_block_window_observation(
        network=BitcoinNetwork.MAINNET,
        observed_at_ms=observed_at_ms,
        tip_height=blocks[0].height,
        tip_hash=blocks[0].block_hash,
        blocks=blocks,
        source=DataSource.REST,
        adapter_version="onchain-test/1",
    )


def test_block_record_identity_is_deterministic() -> None:
    first = _block(1_000)
    second = _block(1_000)

    assert first == second
    assert first.block_hash == _hash(1_000)
    assert len(first.record_identity) == 64


def test_block_record_identity_tampering_fails_closed() -> None:
    block = _block(1_000)

    with pytest.raises(ValueError, match="identity mismatch"):
        replace(block, record_identity="f" * 64)


def test_block_record_rejects_invalid_network_measurements() -> None:
    block = _block(1_000)

    with pytest.raises(ValueError, match="median time"):
        replace(block, median_time_ms=block.header_timestamp_ms)

    with pytest.raises(ValueError, match="weight"):
        replace(block, weight_units=4_000_001)

    with pytest.raises(ValueError, match="difficulty"):
        replace(block, difficulty=Decimal(0))


def test_window_identity_is_deterministic_and_tip_bound() -> None:
    first = _window()
    second = _window()

    assert first == second
    assert first.temporal_semantic == "ingestion_time_snapshot"
    assert first.tip_height == 1_000
    assert len(first.observation_identity) == 64

    with pytest.raises(ValueError, match="tip hash mismatch"):
        replace(first, tip_hash="f" * 64)


def test_window_requires_descending_blocks_and_bounded_size() -> None:
    blocks = _window().blocks

    with pytest.raises(ValueError, match="strictly height-descending"):
        build_bitcoin_block_window_observation(
            network=BitcoinNetwork.MAINNET,
            observed_at_ms=900_000_000,
            tip_height=blocks[1].height,
            tip_hash=blocks[1].block_hash,
            blocks=(blocks[1], blocks[0]),
            source=DataSource.REST,
            adapter_version="onchain-test/1",
        )

    with pytest.raises(ValueError, match="cannot exceed ten"):
        build_bitcoin_block_window_observation(
            network=BitcoinNetwork.MAINNET,
            observed_at_ms=900_000_000,
            tip_height=1_000,
            tip_hash=_hash(1_000),
            blocks=tuple(_block(height) for height in range(1_000, 989, -1)),
            source=DataSource.REST,
            adapter_version="onchain-test/1",
        )
