from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.onchain import BitcoinBlockWindowObservation, BitcoinNetwork
from crypto_signal.ledger.serialization import canonical_sha256

ONCHAIN_NETWORK_ENGINE_VERSION = "bitcoin-onchain-network-v1/1"
ONCHAIN_NETWORK_FREEZE_SCHEMA_VERSION = "bitcoin-onchain-network-freeze-v1/1"
_BITCOIN_MAX_BLOCK_WEIGHT = Decimal(4_000_000)
_SECONDS_PER_BLOCK_TARGET = Decimal(600)


class BlockCadenceState(StrEnum):
    FAST = "fast"
    NORMAL = "normal"
    SLOW = "slow"
    UNAVAILABLE = "unavailable"


class BlockUtilizationState(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class OnchainNetworkLabel(StrEnum):
    HIGH_ACTIVITY = "high_activity"
    LOW_ACTIVITY = "low_activity"
    NORMAL = "normal"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class OnchainNetworkConfig:
    lookback_blocks: int = 8
    minimum_blocks: int = 6
    max_snapshot_age_ms: int = 20 * 60_000
    fast_interval_ratio: Decimal = Decimal("0.75")
    slow_interval_ratio: Decimal = Decimal("1.25")
    high_weight_utilization: Decimal = Decimal("0.80")
    low_weight_utilization: Decimal = Decimal("0.40")

    def __post_init__(self) -> None:
        if not 2 <= self.minimum_blocks <= self.lookback_blocks <= 10:
            raise ValueError(
                "on-chain block counts must satisfy 2 <= minimum <= lookback <= 10"
            )
        if self.max_snapshot_age_ms <= 0:
            raise ValueError("on-chain max snapshot age must be positive")
        if not Decimal(0) < self.fast_interval_ratio < Decimal(1):
            raise ValueError("fast interval ratio must be inside (0,1)")
        if self.slow_interval_ratio <= Decimal(1):
            raise ValueError("slow interval ratio must be greater than 1")
        if not Decimal(0) < self.low_weight_utilization < Decimal(1):
            raise ValueError("low weight utilization must be inside (0,1)")
        if not Decimal(0) < self.high_weight_utilization < Decimal(1):
            raise ValueError("high weight utilization must be inside (0,1)")
        if self.low_weight_utilization >= self.high_weight_utilization:
            raise ValueError("low utilization threshold must be below high threshold")


DEFAULT_ONCHAIN_NETWORK_CONFIG = OnchainNetworkConfig()


@dataclass(frozen=True, slots=True)
class OnchainNetworkMetrics:
    block_count: int
    height_span: int
    header_time_span_ms: int
    average_block_interval_seconds: Decimal
    interval_ratio_to_target: Decimal
    average_weight_utilization: Decimal
    average_tx_count: Decimal
    average_size_bytes: Decimal
    latest_difficulty: Decimal

    def __post_init__(self) -> None:
        if self.block_count < 2:
            raise ValueError("on-chain metrics require at least two blocks")
        if self.height_span != self.block_count - 1:
            raise ValueError("on-chain height span must match contiguous block count")
        if self.header_time_span_ms <= 0:
            raise ValueError("on-chain header time span must be positive")
        for label, value in (
            ("average_block_interval_seconds", self.average_block_interval_seconds),
            ("interval_ratio_to_target", self.interval_ratio_to_target),
            ("average_weight_utilization", self.average_weight_utilization),
            ("average_tx_count", self.average_tx_count),
            ("average_size_bytes", self.average_size_bytes),
            ("latest_difficulty", self.latest_difficulty),
        ):
            if (
                value.is_nan()
                or value.is_infinite()
                or value <= Decimal(0)
            ):
                raise ValueError(f"{label} must be finite and positive")
        if self.average_weight_utilization > Decimal(1):
            raise ValueError("average block weight utilization cannot exceed 1")
        if self.interval_ratio_to_target != (
            self.average_block_interval_seconds / _SECONDS_PER_BLOCK_TARGET
        ):
            raise ValueError("on-chain interval ratio mismatch")


@dataclass(frozen=True, slots=True)
class OnchainNetworkAnalysis:
    evidence_identity: str
    engine_version: str
    network: BitcoinNetwork
    as_of_ms: int
    observed_at_ms: int | None
    tip_height: int | None
    tip_hash: str | None
    consumed_block_count: int
    label: OnchainNetworkLabel
    cadence_state: BlockCadenceState
    utilization_state: BlockUtilizationState
    metrics: OnchainNetworkMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "on-chain evidence identity")
        if self.engine_version != ONCHAIN_NETWORK_ENGINE_VERSION:
            raise ValueError("unsupported on-chain engine version")
        if self.as_of_ms < 0:
            raise ValueError("on-chain as_of_ms must be non-negative")
        if self.observed_at_ms is not None:
            if not 0 <= self.observed_at_ms <= self.as_of_ms:
                raise ValueError("on-chain observation must be available by as-of")
        if (self.tip_height is None) != (self.tip_hash is None):
            raise ValueError("on-chain tip height/hash must appear together")
        if self.tip_height is not None and self.tip_height < 0:
            raise ValueError("on-chain tip height must be non-negative")
        if self.tip_hash is not None:
            _require_sha256(self.tip_hash, "on-chain tip hash")
        if self.consumed_block_count < 0:
            raise ValueError("on-chain consumed block count cannot be negative")
        if self.label is OnchainNetworkLabel.UNRESOLVED:
            if self.metrics is not None:
                raise ValueError("unresolved on-chain analysis cannot carry metrics")
            if self.cadence_state is not BlockCadenceState.UNAVAILABLE:
                raise ValueError("unresolved on-chain cadence must be unavailable")
            if self.utilization_state is not BlockUtilizationState.UNAVAILABLE:
                raise ValueError("unresolved on-chain utilization must be unavailable")
            if not self.uncertainty_flags:
                raise ValueError("unresolved on-chain analysis requires uncertainty")
        elif self.metrics is None:
            raise ValueError("resolved on-chain analysis requires metrics")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("on-chain evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class OnchainNetworkEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: OnchainNetworkAnalysis
    observation: BitcoinBlockWindowObservation | None

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "on-chain freeze identity")
        if self.schema_version != ONCHAIN_NETWORK_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported on-chain freeze schema")
        if self.observation is None:
            if self.analysis.observed_at_ms is not None:
                raise ValueError("missing observation cannot have observed_at")
        else:
            if self.analysis.observed_at_ms != self.observation.observed_at_ms:
                raise ValueError("on-chain freeze observation time mismatch")
            if self.analysis.tip_height != self.observation.tip_height:
                raise ValueError("on-chain freeze tip height mismatch")
            if self.analysis.tip_hash != self.observation.tip_hash:
                raise ValueError("on-chain freeze tip hash mismatch")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("on-chain freeze identity mismatch")


def analyze_onchain_network(
    observations: Sequence[BitcoinBlockWindowObservation],
    *,
    as_of_ms: int,
    config: OnchainNetworkConfig = DEFAULT_ONCHAIN_NETWORK_CONFIG,
) -> OnchainNetworkAnalysis:
    return build_onchain_network_evidence_freeze(
        observations,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_onchain_network_evidence_freeze(
    observations: Sequence[BitcoinBlockWindowObservation],
    *,
    as_of_ms: int,
    config: OnchainNetworkConfig = DEFAULT_ONCHAIN_NETWORK_CONFIG,
) -> OnchainNetworkEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("on-chain as_of_ms must be non-negative")
    if not observations:
        analysis = _unresolved(
            as_of_ms=as_of_ms,
            observation=None,
            consumed_block_count=0,
            flags=("onchain_observation_unavailable",),
        )
        return _freeze(analysis=analysis, observation=None)

    if any(item.network is not BitcoinNetwork.MAINNET for item in observations):
        raise ValueError("on-chain v1 supports Bitcoin mainnet only")
    ids = [item.observation_identity for item in observations]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate on-chain observation identity")
    observed_times = [item.observed_at_ms for item in observations]
    if len(observed_times) != len(set(observed_times)):
        raise ValueError("on-chain observations require unique observation times")

    safe = tuple(
        sorted(
            (item for item in observations if item.observed_at_ms <= as_of_ms),
            key=lambda item: (item.observed_at_ms, item.observation_identity),
        )
    )
    if not safe:
        analysis = _unresolved(
            as_of_ms=as_of_ms,
            observation=None,
            consumed_block_count=0,
            flags=("onchain_observation_unavailable_at_as_of",),
        )
        return _freeze(analysis=analysis, observation=None)

    observation = safe[-1]
    blocks = observation.blocks[: config.lookback_blocks]
    flags: list[str] = []
    if as_of_ms - observation.observed_at_ms > config.max_snapshot_age_ms:
        flags.append("stale_onchain_snapshot")
    if len(blocks) < config.minimum_blocks:
        flags.append("insufficient_block_history")
    if not _is_contiguous_chain(blocks):
        flags.append("noncontiguous_block_chain")

    blocking = {
        "stale_onchain_snapshot",
        "insufficient_block_history",
        "noncontiguous_block_chain",
    }
    if any(flag in blocking for flag in flags):
        analysis = _unresolved(
            as_of_ms=as_of_ms,
            observation=observation,
            consumed_block_count=len(blocks),
            flags=tuple(flags),
        )
        return _freeze(analysis=analysis, observation=observation)

    newest = blocks[0]
    oldest = blocks[-1]
    header_span_ms = newest.header_timestamp_ms - oldest.header_timestamp_ms
    if header_span_ms <= 0:
        flags.append("nonpositive_block_header_time_span")
        analysis = _unresolved(
            as_of_ms=as_of_ms,
            observation=observation,
            consumed_block_count=len(blocks),
            flags=tuple(flags),
        )
        return _freeze(analysis=analysis, observation=observation)

    if any(
        newer.header_timestamp_ms <= older.header_timestamp_ms
        for newer, older in zip(blocks, blocks[1:], strict=False)
    ):
        flags.append("non_monotonic_block_header_timestamps")

    metrics = _derive_metrics(blocks, header_span_ms=header_span_ms)
    cadence = _cadence(metrics, config=config)
    utilization = _utilization(metrics, config=config)
    if (
        cadence is BlockCadenceState.FAST
        and utilization is BlockUtilizationState.HIGH
    ):
        label = OnchainNetworkLabel.HIGH_ACTIVITY
    elif (
        cadence is BlockCadenceState.SLOW
        and utilization is BlockUtilizationState.LOW
    ):
        label = OnchainNetworkLabel.LOW_ACTIVITY
    elif (
        cadence is BlockCadenceState.NORMAL
        and utilization is BlockUtilizationState.NORMAL
    ):
        label = OnchainNetworkLabel.NORMAL
    else:
        label = OnchainNetworkLabel.MIXED
        flags.append("cadence_utilization_disagreement")

    payload = {
        "as_of_ms": as_of_ms,
        "cadence_state": cadence,
        "consumed_block_count": len(blocks),
        "engine_version": ONCHAIN_NETWORK_ENGINE_VERSION,
        "label": label,
        "metrics": _metrics_payload(metrics),
        "network": BitcoinNetwork.MAINNET,
        "observed_at_ms": observation.observed_at_ms,
        "tip_hash": observation.tip_hash,
        "tip_height": observation.tip_height,
        "uncertainty_flags": tuple(flags),
        "utilization_state": utilization,
    }
    analysis = OnchainNetworkAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=ONCHAIN_NETWORK_ENGINE_VERSION,
        network=BitcoinNetwork.MAINNET,
        as_of_ms=as_of_ms,
        observed_at_ms=observation.observed_at_ms,
        tip_height=observation.tip_height,
        tip_hash=observation.tip_hash,
        consumed_block_count=len(blocks),
        label=label,
        cadence_state=cadence,
        utilization_state=utilization,
        metrics=metrics,
        uncertainty_flags=tuple(flags),
    )
    return _freeze(analysis=analysis, observation=observation)


def _derive_metrics(
    blocks: tuple,
    *,
    header_span_ms: int,
) -> OnchainNetworkMetrics:
    block_count = len(blocks)
    height_span = blocks[0].height - blocks[-1].height
    average_interval_seconds = (
        Decimal(header_span_ms) / Decimal(height_span) / Decimal(1000)
    )
    average_weight_utilization = sum(
        (Decimal(item.weight_units) / _BITCOIN_MAX_BLOCK_WEIGHT for item in blocks),
        start=Decimal(0),
    ) / Decimal(block_count)
    average_tx_count = (
        Decimal(sum(item.tx_count for item in blocks)) / Decimal(block_count)
    )
    average_size_bytes = (
        Decimal(sum(item.size_bytes for item in blocks)) / Decimal(block_count)
    )
    return OnchainNetworkMetrics(
        block_count=block_count,
        height_span=height_span,
        header_time_span_ms=header_span_ms,
        average_block_interval_seconds=average_interval_seconds,
        interval_ratio_to_target=average_interval_seconds / _SECONDS_PER_BLOCK_TARGET,
        average_weight_utilization=average_weight_utilization,
        average_tx_count=average_tx_count,
        average_size_bytes=average_size_bytes,
        latest_difficulty=blocks[0].difficulty,
    )


def _cadence(
    metrics: OnchainNetworkMetrics,
    *,
    config: OnchainNetworkConfig,
) -> BlockCadenceState:
    if metrics.interval_ratio_to_target <= config.fast_interval_ratio:
        return BlockCadenceState.FAST
    if metrics.interval_ratio_to_target >= config.slow_interval_ratio:
        return BlockCadenceState.SLOW
    return BlockCadenceState.NORMAL


def _utilization(
    metrics: OnchainNetworkMetrics,
    *,
    config: OnchainNetworkConfig,
) -> BlockUtilizationState:
    if metrics.average_weight_utilization >= config.high_weight_utilization:
        return BlockUtilizationState.HIGH
    if metrics.average_weight_utilization <= config.low_weight_utilization:
        return BlockUtilizationState.LOW
    return BlockUtilizationState.NORMAL


def _is_contiguous_chain(blocks: tuple) -> bool:
    return all(
        newer.height == older.height + 1
        and newer.previous_block_hash == older.block_hash
        for newer, older in zip(blocks, blocks[1:], strict=False)
    )


def _unresolved(
    *,
    as_of_ms: int,
    observation: BitcoinBlockWindowObservation | None,
    consumed_block_count: int,
    flags: tuple[str, ...],
) -> OnchainNetworkAnalysis:
    payload = {
        "as_of_ms": as_of_ms,
        "cadence_state": BlockCadenceState.UNAVAILABLE,
        "consumed_block_count": consumed_block_count,
        "engine_version": ONCHAIN_NETWORK_ENGINE_VERSION,
        "label": OnchainNetworkLabel.UNRESOLVED,
        "metrics": None,
        "network": BitcoinNetwork.MAINNET,
        "observed_at_ms": (
            None if observation is None else observation.observed_at_ms
        ),
        "tip_hash": None if observation is None else observation.tip_hash,
        "tip_height": None if observation is None else observation.tip_height,
        "uncertainty_flags": flags,
        "utilization_state": BlockUtilizationState.UNAVAILABLE,
    }
    return OnchainNetworkAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=ONCHAIN_NETWORK_ENGINE_VERSION,
        network=BitcoinNetwork.MAINNET,
        as_of_ms=as_of_ms,
        observed_at_ms=None if observation is None else observation.observed_at_ms,
        tip_height=None if observation is None else observation.tip_height,
        tip_hash=None if observation is None else observation.tip_hash,
        consumed_block_count=consumed_block_count,
        label=OnchainNetworkLabel.UNRESOLVED,
        cadence_state=BlockCadenceState.UNAVAILABLE,
        utilization_state=BlockUtilizationState.UNAVAILABLE,
        metrics=None,
        uncertainty_flags=flags,
    )


def _freeze(
    *,
    analysis: OnchainNetworkAnalysis,
    observation: BitcoinBlockWindowObservation | None,
) -> OnchainNetworkEvidenceFreeze:
    payload = {
        "analysis_identity": analysis.evidence_identity,
        "observation_identity": (
            None if observation is None else observation.observation_identity
        ),
        "schema_version": ONCHAIN_NETWORK_FREEZE_SCHEMA_VERSION,
    }
    return OnchainNetworkEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=ONCHAIN_NETWORK_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        observation=observation,
    )


def _metrics_payload(metrics: OnchainNetworkMetrics) -> dict[str, object]:
    return {
        "average_block_interval_seconds": metrics.average_block_interval_seconds,
        "average_size_bytes": metrics.average_size_bytes,
        "average_tx_count": metrics.average_tx_count,
        "average_weight_utilization": metrics.average_weight_utilization,
        "block_count": metrics.block_count,
        "header_time_span_ms": metrics.header_time_span_ms,
        "height_span": metrics.height_span,
        "interval_ratio_to_target": metrics.interval_ratio_to_target,
        "latest_difficulty": metrics.latest_difficulty,
    }


def _analysis_payload(analysis: OnchainNetworkAnalysis) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "cadence_state": analysis.cadence_state,
        "consumed_block_count": analysis.consumed_block_count,
        "engine_version": analysis.engine_version,
        "label": analysis.label,
        "metrics": (
            None if analysis.metrics is None else _metrics_payload(analysis.metrics)
        ),
        "network": analysis.network,
        "observed_at_ms": analysis.observed_at_ms,
        "tip_hash": analysis.tip_hash,
        "tip_height": analysis.tip_height,
        "uncertainty_flags": analysis.uncertainty_flags,
        "utilization_state": analysis.utilization_state,
    }


def _freeze_payload(freeze: OnchainNetworkEvidenceFreeze) -> dict[str, object]:
    return {
        "analysis_identity": freeze.analysis.evidence_identity,
        "observation_identity": (
            None
            if freeze.observation is None
            else freeze.observation.observation_identity
        ),
        "schema_version": freeze.schema_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
