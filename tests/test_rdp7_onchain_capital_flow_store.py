from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.exchange_flows import build_exchange_flow_observation
from crypto_signal.data.large_transfers import (
    TransferClusterRole,
    build_large_transfer_observation,
)
from crypto_signal.data.models import DataSource
from crypto_signal.data.onchain_capital_flow import (
    OnchainEventCoverageState,
    build_onchain_event_coverage,
    build_stablecoin_supply_observation,
)
from crypto_signal.data.onchain_capital_flow_store import (
    OnchainCapitalFlowStore,
)
from crypto_signal.data.wallet_cohorts import (
    build_wallet_cohort_admission,
    build_wallet_cohort_forward_observation,
)


def _sha(character: str) -> str:
    return character * 64


def _stablecoin(
    *,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    amount: str,
):
    return build_stablecoin_supply_observation(
        asset="USDT",
        network_scope="all_chains",
        provider="defillama",
        provider_metric_identity="stablecoins/circulating",
        circulating_amount=Decimal(amount),
        usd_amount=Decimal(amount),
        source=DataSource.REST,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version="rdp7-store-test/1",
        raw_identity=_sha("1"),
        source_envelope_identity=_sha("2"),
    )


def _exchange_flow(
    *,
    window_start_ms: int,
    window_end_ms: int,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    inflow: str,
    outflow: str,
):
    return build_exchange_flow_observation(
        asset="BTC",
        exchange_scope="all_supported_exchanges",
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        inflow_amount=Decimal(inflow),
        outflow_amount=Decimal(outflow),
        source_provider="provider-x",
        attribution_method="provider-labelled-v1",
        source=DataSource.REST,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version="rdp7-store-test/1",
    )


def _coverage(
    *,
    start_ms: int,
    end_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    state: OnchainEventCoverageState = OnchainEventCoverageState.COMPLETE,
):
    observed = state in {
        OnchainEventCoverageState.COMPLETE,
        OnchainEventCoverageState.PARTIAL,
    }
    return build_onchain_event_coverage(
        provider="provider-x",
        source="public_rest",
        channel="large_transfer_window",
        asset="BTC",
        network="bitcoin",
        event_kind="large_transfer",
        coverage_start_ms=start_ms,
        coverage_end_ms=end_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        state=state,
        source_envelope_identity=_sha("3") if observed else None,
        raw_identity=_sha("4") if observed else None,
        reason_codes=(
            ("provider_window_complete",)
            if state is OnchainEventCoverageState.COMPLETE
            else ("provider_gap",)
        ),
    )


def test_store_append_replay_counts_and_quick_check(tmp_path: Path) -> None:
    store = OnchainCapitalFlowStore(tmp_path / "onchain.sqlite3")
    stablecoin = _stablecoin(
        source_timestamp_ms=1_000,
        observed_at_ms=1_100,
        ingested_at_ms=1_200,
        amount="100",
    )
    exchange = _exchange_flow(
        window_start_ms=1_000,
        window_end_ms=2_000,
        source_timestamp_ms=2_100,
        ingested_at_ms=2_200,
        inflow="10",
        outflow="8",
    )

    assert store.append_stablecoin_supply(stablecoin) is True
    assert store.append_stablecoin_supply(stablecoin) is False
    assert store.append_exchange_flow(exchange) is True
    assert store.append_exchange_flow(exchange) is False

    counts = store.counts()
    assert counts.stablecoin_supply_observations == 1
    assert counts.exchange_flow_observations == 1
    assert counts.total == 2
    assert store.quick_check() is True


def test_store_conflicting_duplicate_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "onchain.sqlite3"
    store = OnchainCapitalFlowStore(path)
    observation = _stablecoin(
        source_timestamp_ms=1_000,
        observed_at_ms=1_100,
        ingested_at_ms=1_200,
        amount="100",
    )
    store.initialize()

    with sqlite3.connect(path) as db:
        db.execute(
            """
            INSERT INTO stablecoin_supply_observations(
                observation_identity, asset, network_scope, provider,
                source_timestamp_ms, observed_at_ms, ingested_at_ms,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.observation_identity,
                "USDT",
                "all_chains",
                "defillama",
                1_000,
                1_100,
                1_200,
                "{}",
            ),
        )

    with pytest.raises(ValueError, match="identity conflict"):
        store.append_stablecoin_supply(observation)


def test_stablecoin_as_of_never_reads_future_ingestion(tmp_path: Path) -> None:
    store = OnchainCapitalFlowStore(tmp_path / "onchain.sqlite3")
    old = _stablecoin(
        source_timestamp_ms=1_000,
        observed_at_ms=1_100,
        ingested_at_ms=1_200,
        amount="100",
    )
    late = _stablecoin(
        source_timestamp_ms=1_500,
        observed_at_ms=1_600,
        ingested_at_ms=5_000,
        amount="200",
    )
    store.append_stablecoin_supply(old)
    store.append_stablecoin_supply(late)

    assert (
        store.latest_stablecoin_supply_as_of(
            asset="USDT",
            network_scope="all_chains",
            provider="defillama",
            as_of_ms=2_000,
        )
        == old
    )
    assert (
        store.latest_stablecoin_supply_as_of(
            asset="USDT",
            network_scope="all_chains",
            provider="defillama",
            as_of_ms=6_000,
        )
        == late
    )
    assert store.stablecoin_supply_history_as_of(
        asset="USDT",
        network_scope="all_chains",
        provider="defillama",
        as_of_ms=6_000,
        limit=2,
    ) == (old, late)


def test_exchange_flow_as_of_never_uses_future_ingestion(tmp_path: Path) -> None:
    store = OnchainCapitalFlowStore(tmp_path / "onchain.sqlite3")
    old = _exchange_flow(
        window_start_ms=1_000,
        window_end_ms=2_000,
        source_timestamp_ms=2_100,
        ingested_at_ms=2_200,
        inflow="10",
        outflow="8",
    )
    late = _exchange_flow(
        window_start_ms=2_000,
        window_end_ms=3_000,
        source_timestamp_ms=3_100,
        ingested_at_ms=9_000,
        inflow="30",
        outflow="10",
    )
    store.append_exchange_flow(old)
    store.append_exchange_flow(late)

    assert (
        store.latest_exchange_flow_as_of(
            asset="BTC",
            exchange_scope="all_supported_exchanges",
            as_of_ms=4_000,
        )
        == old
    )
    assert (
        store.latest_exchange_flow_as_of(
            asset="BTC",
            exchange_scope="all_supported_exchanges",
            as_of_ms=10_000,
        )
        == late
    )


def test_empty_transfer_result_is_not_zero_without_complete_coverage(
    tmp_path: Path,
) -> None:
    store = OnchainCapitalFlowStore(tmp_path / "onchain.sqlite3")
    store.initialize()

    assert store.large_transfers_as_of(
        asset="BTC",
        network="bitcoin",
        start_ms=1_000,
        end_ms=2_000,
        as_of_ms=3_000,
    ) == ()
    assert (
        store.latest_event_coverage_as_of(
            event_kind="large_transfer",
            asset="BTC",
            network="bitcoin",
            as_of_ms=3_000,
        )
        is None
    )

    complete = _coverage(
        start_ms=1_000,
        end_ms=2_000,
        observed_at_ms=2_100,
        ingested_at_ms=2_200,
    )
    store.append_event_coverage(complete)
    replay = store.latest_event_coverage_as_of(
        event_kind="large_transfer",
        asset="BTC",
        network="bitcoin",
        as_of_ms=3_000,
    )
    assert replay == complete
    assert replay is not None
    assert replay.can_assert_zero_events is True


def test_large_transfer_replay_is_pit_safe(tmp_path: Path) -> None:
    store = OnchainCapitalFlowStore(tmp_path / "onchain.sqlite3")
    visible = build_large_transfer_observation(
        asset="BTC",
        network="bitcoin",
        provider_transfer_id="transfer-1",
        source_cluster_id="cluster-a",
        destination_cluster_id="cluster-b",
        source_role=TransferClusterRole.PROVIDER_KNOWN,
        destination_role=TransferClusterRole.EXCHANGE,
        amount=Decimal("12.5"),
        event_at_ms=1_500,
        source_timestamp_ms=1_600,
        ingested_at_ms=1_700,
        source_provider="provider-x",
        attribution_method="labels-v1",
        source=DataSource.REST,
        adapter_version="rdp7-store-test/1",
    )
    late = build_large_transfer_observation(
        asset="BTC",
        network="bitcoin",
        provider_transfer_id="transfer-2",
        source_cluster_id="cluster-c",
        destination_cluster_id="cluster-d",
        source_role=TransferClusterRole.PROVIDER_KNOWN,
        destination_role=TransferClusterRole.EXCHANGE,
        amount=Decimal("7"),
        event_at_ms=1_800,
        source_timestamp_ms=1_900,
        ingested_at_ms=5_000,
        source_provider="provider-x",
        attribution_method="labels-v1",
        source=DataSource.REST,
        adapter_version="rdp7-store-test/1",
    )
    store.append_large_transfer(visible)
    store.append_large_transfer(late)

    assert store.large_transfers_as_of(
        asset="BTC",
        network="bitcoin",
        start_ms=1_000,
        end_ms=2_000,
        as_of_ms=2_500,
    ) == (visible,)
    assert store.large_transfers_as_of(
        asset="BTC",
        network="bitcoin",
        start_ms=1_000,
        end_ms=2_000,
        as_of_ms=6_000,
    ) == (visible, late)


def test_wallet_cohort_forward_requires_stored_prior_admission(
    tmp_path: Path,
) -> None:
    store = OnchainCapitalFlowStore(tmp_path / "onchain.sqlite3")
    admission = build_wallet_cohort_admission(
        cohort_id="cohort-1",
        cluster_id="cluster-1",
        asset="BTC",
        network="bitcoin",
        admitted_at_ms=2_000,
        basis_available_at_ms=1_900,
        source_provider="provider-x",
        attribution_method="labels-v1",
        admission_rule_version="rule-v1",
        basis_evidence_identities=(_sha("a"),),
        source=DataSource.REST,
    )
    valid = build_wallet_cohort_forward_observation(
        admission_identity=admission.admission_identity,
        cohort_id="cohort-1",
        cluster_id="cluster-1",
        asset="BTC",
        network="bitcoin",
        measurement_start_ms=2_100,
        measurement_end_ms=3_000,
        metric_name="net_flow",
        metric_value=Decimal("5"),
        source_provider="provider-x",
        source=DataSource.REST,
        source_timestamp_ms=3_100,
        ingested_at_ms=3_200,
        adapter_version="rdp7-store-test/1",
    )

    with pytest.raises(ValueError, match="requires stored admission"):
        store.append_wallet_cohort_forward(valid)

    assert store.append_wallet_cohort_admission(admission) is True
    assert store.append_wallet_cohort_forward(valid) is True
    assert store.wallet_cohort_admission(admission.admission_identity) == admission
    assert store.wallet_cohort_forward_as_of(
        admission_identity=admission.admission_identity,
        as_of_ms=4_000,
    ) == (valid,)


def test_wallet_cohort_forward_cannot_predate_admission(tmp_path: Path) -> None:
    store = OnchainCapitalFlowStore(tmp_path / "onchain.sqlite3")
    admission = build_wallet_cohort_admission(
        cohort_id="cohort-1",
        cluster_id="cluster-1",
        asset="BTC",
        network="bitcoin",
        admitted_at_ms=2_000,
        basis_available_at_ms=1_900,
        source_provider="provider-x",
        attribution_method="labels-v1",
        admission_rule_version="rule-v1",
        basis_evidence_identities=(_sha("b"),),
        source=DataSource.REST,
    )
    store.append_wallet_cohort_admission(admission)
    invalid = build_wallet_cohort_forward_observation(
        admission_identity=admission.admission_identity,
        cohort_id="cohort-1",
        cluster_id="cluster-1",
        asset="BTC",
        network="bitcoin",
        measurement_start_ms=1_900,
        measurement_end_ms=2_500,
        metric_name="net_flow",
        metric_value=Decimal("1"),
        source_provider="provider-x",
        source=DataSource.REST,
        source_timestamp_ms=2_600,
        ingested_at_ms=2_700,
        adapter_version="rdp7-store-test/1",
    )

    with pytest.raises(ValueError, match="cannot predate admission"):
        store.append_wallet_cohort_forward(invalid)


def test_store_tables_are_physically_immutable(tmp_path: Path) -> None:
    path = tmp_path / "onchain.sqlite3"
    store = OnchainCapitalFlowStore(path)
    observation = _stablecoin(
        source_timestamp_ms=1_000,
        observed_at_ms=1_100,
        ingested_at_ms=1_200,
        amount="100",
    )
    store.append_stablecoin_supply(observation)

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                """
                UPDATE stablecoin_supply_observations
                SET provider='tampered'
                WHERE observation_identity=?
                """,
                (observation.observation_identity,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                """
                DELETE FROM stablecoin_supply_observations
                WHERE observation_identity=?
                """,
                (observation.observation_identity,),
            )
