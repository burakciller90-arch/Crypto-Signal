from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.models import MethodologyKind
from crypto_signal.data.models import DataSource
from crypto_signal.data.onchain import (
    BitcoinBlockRecord,
    BitcoinNetwork,
    build_bitcoin_block_record,
    build_bitcoin_block_window_observation,
)
from crypto_signal.intelligence.onchain_network import (
    ONCHAIN_NETWORK_ENGINE_VERSION,
    ONCHAIN_NETWORK_FREEZE_SCHEMA_VERSION,
    BlockCadenceState,
    BlockUtilizationState,
    OnchainNetworkConfig,
    OnchainNetworkLabel,
    analyze_onchain_network,
    build_onchain_network_evidence_freeze,
)


def _hash(height: int) -> str:
    return f"{height:064x}"


def _blocks(
    *,
    tip_height: int = 1_000,
    count: int = 10,
    interval_ms: int = 600_000,
    weight_units: int = 2_400_000,
    bad_link: bool = False,
) -> tuple[BitcoinBlockRecord, ...]:
    newest_header_ms = 2_000_000_000
    rows: list[BitcoinBlockRecord] = []
    for offset in range(count):
        height = tip_height - offset
        header_ms = newest_header_ms - offset * interval_ms
        previous_hash = (
            "f" * 64 if bad_link and offset == 0 else _hash(height - 1)
        )
        rows.append(
            build_bitcoin_block_record(
                block_hash=_hash(height),
                height=height,
                header_timestamp_ms=header_ms,
                median_time_ms=header_ms - 300_000,
                tx_count=2_000,
                size_bytes=1_500_000,
                weight_units=weight_units,
                difficulty=Decimal("123456.789"),
                previous_block_hash=previous_hash,
            )
        )
    return tuple(rows)


def _observation(
    *,
    observed_at_ms: int = 3_000_000_000,
    tip_height: int = 1_000,
    count: int = 10,
    interval_ms: int = 600_000,
    weight_units: int = 2_400_000,
    bad_link: bool = False,
):
    blocks = _blocks(
        tip_height=tip_height,
        count=count,
        interval_ms=interval_ms,
        weight_units=weight_units,
        bad_link=bad_link,
    )
    return build_bitcoin_block_window_observation(
        network=BitcoinNetwork.MAINNET,
        observed_at_ms=observed_at_ms,
        tip_height=blocks[0].height,
        tip_hash=blocks[0].block_hash,
        blocks=blocks,
        source=DataSource.REST,
        adapter_version="onchain-engine-test/1",
    )


def _config(**overrides):
    payload = {
        "lookback_blocks": 8,
        "minimum_blocks": 6,
        "max_snapshot_age_ms": 1_200_000,
        "fast_interval_ratio": Decimal("0.75"),
        "slow_interval_ratio": Decimal("1.25"),
        "high_weight_utilization": Decimal("0.80"),
        "low_weight_utilization": Decimal("0.40"),
    }
    payload.update(overrides)
    return OnchainNetworkConfig(**payload)


def test_high_activity_is_deterministic_and_frozen() -> None:
    observation = _observation(interval_ms=300_000, weight_units=3_600_000)
    config = _config()

    first = build_onchain_network_evidence_freeze(
        (observation,),
        as_of_ms=observation.observed_at_ms,
        config=config,
    )
    second = build_onchain_network_evidence_freeze(
        (observation,),
        as_of_ms=observation.observed_at_ms,
        config=config,
    )

    assert first == second
    assert first.schema_version == ONCHAIN_NETWORK_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == ONCHAIN_NETWORK_ENGINE_VERSION
    assert first.analysis.label is OnchainNetworkLabel.HIGH_ACTIVITY
    assert first.analysis.cadence_state is BlockCadenceState.FAST
    assert first.analysis.utilization_state is BlockUtilizationState.HIGH
    assert first.analysis.metrics is not None
    assert first.analysis.metrics.block_count == 8
    assert first.analysis.metrics.height_span == 7
    assert first.analysis.metrics.average_block_interval_seconds == Decimal(300)
    assert first.analysis.metrics.interval_ratio_to_target == Decimal("0.5")
    assert first.analysis.metrics.average_weight_utilization == Decimal("0.9")
    assert first.analysis.uncertainty_flags == ()
    assert len(first.freeze_identity) == 64
    assert len(first.analysis.evidence_identity) == 64


def test_low_activity_and_normal_context_are_bounded() -> None:
    low = analyze_onchain_network(
        (_observation(interval_ms=900_000, weight_units=1_000_000),),
        as_of_ms=3_000_000_000,
        config=_config(),
    )
    normal = analyze_onchain_network(
        (_observation(interval_ms=600_000, weight_units=2_400_000),),
        as_of_ms=3_000_000_000,
        config=_config(),
    )

    assert low.label is OnchainNetworkLabel.LOW_ACTIVITY
    assert low.cadence_state is BlockCadenceState.SLOW
    assert low.utilization_state is BlockUtilizationState.LOW
    assert normal.label is OnchainNetworkLabel.NORMAL
    assert normal.cadence_state is BlockCadenceState.NORMAL
    assert normal.utilization_state is BlockUtilizationState.NORMAL


def test_cadence_utilization_disagreement_is_mixed() -> None:
    result = analyze_onchain_network(
        (_observation(interval_ms=300_000, weight_units=1_000_000),),
        as_of_ms=3_000_000_000,
        config=_config(),
    )

    assert result.label is OnchainNetworkLabel.MIXED
    assert result.cadence_state is BlockCadenceState.FAST
    assert result.utilization_state is BlockUtilizationState.LOW
    assert "cadence_utilization_disagreement" in result.uncertainty_flags


def test_stale_or_insufficient_or_broken_chain_is_unresolved() -> None:
    fresh_at = 3_000_000_000
    stale = analyze_onchain_network(
        (_observation(observed_at_ms=fresh_at),),
        as_of_ms=fresh_at + 1_200_001,
        config=_config(),
    )
    insufficient = analyze_onchain_network(
        (_observation(count=5),),
        as_of_ms=fresh_at,
        config=_config(),
    )
    broken = analyze_onchain_network(
        (_observation(bad_link=True),),
        as_of_ms=fresh_at,
        config=_config(),
    )

    assert stale.label is OnchainNetworkLabel.UNRESOLVED
    assert "stale_onchain_snapshot" in stale.uncertainty_flags
    assert insufficient.label is OnchainNetworkLabel.UNRESOLVED
    assert "insufficient_block_history" in insufficient.uncertainty_flags
    assert broken.label is OnchainNetworkLabel.UNRESOLVED
    assert "noncontiguous_block_chain" in broken.uncertainty_flags


def test_future_observation_cannot_change_historical_freeze() -> None:
    baseline = _observation(observed_at_ms=3_000_000_000)
    future = _observation(
        observed_at_ms=3_000_100_000,
        tip_height=1_001,
        interval_ms=300_000,
        weight_units=3_600_000,
    )
    as_of_ms = 3_000_050_000

    first = build_onchain_network_evidence_freeze(
        (baseline,),
        as_of_ms=as_of_ms,
        config=_config(),
    )
    with_future = build_onchain_network_evidence_freeze(
        (baseline, future),
        as_of_ms=as_of_ms,
        config=_config(),
    )

    assert with_future == first
    assert with_future.observation == baseline


def test_no_safe_observation_is_unresolved_without_fabricated_metrics() -> None:
    future = _observation(observed_at_ms=3_000_100_000)

    result = analyze_onchain_network(
        (future,),
        as_of_ms=3_000_000_000,
        config=_config(),
    )

    assert result.label is OnchainNetworkLabel.UNRESOLVED
    assert result.metrics is None
    assert result.observed_at_ms is None
    assert result.uncertainty_flags == (
        "onchain_observation_unavailable_at_as_of",
    )


def test_duplicate_observation_and_identity_tampering_fail_closed() -> None:
    observation = _observation()

    with pytest.raises(ValueError, match="duplicate"):
        analyze_onchain_network(
            (observation, observation),
            as_of_ms=observation.observed_at_ms,
            config=_config(),
        )

    freeze = build_onchain_network_evidence_freeze(
        (observation,),
        as_of_ms=observation.observed_at_ms,
        config=_config(),
    )
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_invalid_config_fails_closed() -> None:
    with pytest.raises(ValueError, match="block counts"):
        OnchainNetworkConfig(lookback_blocks=5, minimum_blocks=6)

    with pytest.raises(ValueError, match="low utilization"):
        OnchainNetworkConfig(
            low_weight_utilization=Decimal("0.9"),
            high_weight_utilization=Decimal("0.8"),
        )


def test_stage8_onchain_is_observation_only_ablation_zero() -> None:
    assert set(MethodologyKind) == {
        MethodologyKind.PRICE_ACTION,
        MethodologyKind.HARMONIC,
        MethodologyKind.ELLIOTT,
    }

    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/crypto_signal/confluence/models.py",
        "src/crypto_signal/confluence/adapters.py",
        "src/crypto_signal/ledger/bundle.py",
        "src/crypto_signal/signals/models.py",
        "src/crypto_signal/paper/mission_control.py",
    ):
        source = (root / relative).read_text()
        assert "crypto_signal.intelligence.onchain_network" not in source
