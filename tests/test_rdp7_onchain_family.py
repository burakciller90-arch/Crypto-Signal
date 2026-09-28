from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.adapters.defillama_stablecoins import (
    DefiLlamaStablecoinAssetSnapshot,
    DefiLlamaStablecoinSourceSnapshot,
)
from crypto_signal.data.onchain_capital_flow_store import OnchainCapitalFlowStore
from crypto_signal.data.source_contract import (
    SourceContractStore,
    SourceCoverageState,
    build_source_coverage_event,
)
from crypto_signal.data.stablecoin_source_contract import (
    DEFILLAMA_STABLECOIN_CHANNEL,
    DEFILLAMA_STABLECOIN_PROVIDER,
    DEFILLAMA_STABLECOIN_SOURCE,
    persist_defillama_stablecoin_snapshot,
)
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
)
from crypto_signal.product.intelligence_stream_onchain_family import (
    RDP7_ONCHAIN_PROJECTOR_ID,
    build_onchain_family_snapshots,
)
from crypto_signal.product.intelligence_stream_policy import (
    StreamProjectorImplementationState,
    accepted_stream_projector_registry,
    build_stream_materiality_policy,
)
from crypto_signal.product.intelligence_stream_production_projector import (
    IntelligenceStreamProductionProjector,
)


def _asset(
    symbol: str,
    amount: str,
) -> DefiLlamaStablecoinAssetSnapshot:
    value = Decimal(amount)
    return DefiLlamaStablecoinAssetSnapshot(
        symbol=symbol,
        provider_asset_id=f"{symbol.lower()}-id",
        circulating_pegged_usd=value,
        price_usd=Decimal("1"),
        chain_count=2,
        raw_payload={
            "circulating": {"peggedUSD": amount},
            "id": f"{symbol.lower()}-id",
            "symbol": symbol,
        },
    )


def _persist_snapshot(
    *,
    onchain: OnchainCapitalFlowStore,
    source: SourceContractStore,
    observed_at_ms: int,
    usdc: str,
    usdt: str,
):
    return persist_defillama_stablecoin_snapshot(
        snapshot=DefiLlamaStablecoinSourceSnapshot(
            assets=(
                _asset("USDC", usdc),
                _asset("USDT", usdt),
            ),
            observed_at_ms=observed_at_ms,
        ),
        onchain_store=onchain,
        source_store=source,
    )


def _seed_two_snapshots(
    tmp_path: Path,
) -> tuple[
    Path,
    Path,
    tuple[object, ...],
]:
    onchain_path = tmp_path / "onchain.sqlite3"
    source_path = tmp_path / "source.sqlite3"
    onchain = OnchainCapitalFlowStore(onchain_path)
    source = SourceContractStore(source_path)
    _persist_snapshot(
        onchain=onchain,
        source=source,
        observed_at_ms=1_000_000,
        usdc="100000000",
        usdt="200000000",
    )
    latest = _persist_snapshot(
        onchain=onchain,
        source=source,
        observed_at_ms=1_300_000,
        usdc="101000000",
        usdt="199000000",
    )
    return onchain_path, source_path, tuple(latest)


def test_onchain_family_binds_exact_stablecoin_lineage_without_direction(
    tmp_path: Path,
) -> None:
    onchain_path, source_path, latest = _seed_two_snapshots(tmp_path)

    snapshots = build_onchain_family_snapshots(
        onchain_path,
        source_path,
        symbols=("BTCUSDT", "ETHUSDT"),
        as_of_ms=1_300_100,
    )

    assert tuple(item.symbol for item in snapshots) == (
        "BTCUSDT",
        "ETHUSDT",
    )
    latest_ids = {
        value
        for item in latest
        for value in (
            item.raw_identity,
            item.envelope_identity,
            item.coverage_event_identity,
            item.observation_identity,
        )
    }
    for snapshot in snapshots:
        components = {
            item.name: item.value
            for item in snapshot.state_components
        }
        assert snapshot.family is ConfluenceFamily.ONCHAIN
        assert snapshot.projector_id == RDP7_ONCHAIN_PROJECTOR_ID
        assert snapshot.direction is None
        assert snapshot.source_quality == "measured"
        assert snapshot.state_label == "stablecoin_context_measured"
        assert latest_ids.issubset(set(snapshot.evidence_identities))
        assert "source_raw_payload" in snapshot.evidence_domains
        assert "source_envelope" in snapshot.evidence_domains
        assert "source_coverage" in snapshot.evidence_domains
        assert components["exchange_flow_status"] == "unavailable"
        assert components["large_transfer_status"] == "unavailable"
        assert components["wallet_cohort_status"] == "unavailable"
        assert components["stablecoin_bridge_status"] == "unavailable"
        assert components["usdc_source_coverage_status"] == "observed"
        assert components["usdt_source_coverage_status"] == "observed"
        assert components["usdc_supply_delta"] == "1000000"
        assert components["usdt_supply_delta"] == "-1000000"
        assert "stablecoin_supply_context_not_directional" in (
            snapshot.uncertainty_flags
        )
        encoded = " ".join(
            value
            for _, value in (
                (item.name, item.value)
                for item in snapshot.state_components
            )
        ).lower()
        assert "bullish" not in encoded
        assert "bearish" not in encoded


def test_onchain_family_fails_closed_when_coverage_becomes_unavailable(
    tmp_path: Path,
) -> None:
    onchain_path, source_path, _ = _seed_two_snapshots(tmp_path)
    source = SourceContractStore(source_path)
    capability = source.capability(
        source.latest_envelope_at(
            provider=DEFILLAMA_STABLECOIN_PROVIDER,
            source=DEFILLAMA_STABLECOIN_SOURCE,
            channel=DEFILLAMA_STABLECOIN_CHANNEL,
            symbol="USDT",
            as_of_ms=1_300_100,
        ).capability_identity
    )
    assert capability is not None
    previous = source.latest_coverage(
        provider=DEFILLAMA_STABLECOIN_PROVIDER,
        source=DEFILLAMA_STABLECOIN_SOURCE,
        channel=DEFILLAMA_STABLECOIN_CHANNEL,
        symbol="USDT",
    )
    assert previous is not None
    unavailable = build_source_coverage_event(
        capability=capability,
        symbol="USDT",
        state=SourceCoverageState.UNAVAILABLE,
        observed_at_ms=1_300_200,
        previous=previous,
        source_envelope_identity=None,
        gap_event_identity=None,
        reason_codes=("provider_unavailable",),
    )
    source.append_coverage(unavailable)

    snapshots = build_onchain_family_snapshots(
        onchain_path,
        source_path,
        symbols=("BTCUSDT",),
        as_of_ms=1_300_300,
    )
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    components = {
        item.name: item.value
        for item in snapshot.state_components
    }
    assert snapshot.direction is None
    assert snapshot.source_quality == "partial"
    assert snapshot.state_label == "stablecoin_context_partial"
    assert components["usdt_source_coverage_status"] == "unavailable"
    assert components["usdt_stablecoin_status"] == "unavailable"
    assert "usdt_supply_delta" not in components
    assert unavailable.coverage_event_identity in snapshot.evidence_identities
    assert "usdt_stablecoin_source_lineage_unavailable" in (
        snapshot.uncertainty_flags
    )


def test_onchain_family_is_pit_safe_and_ignores_future_snapshot(
    tmp_path: Path,
) -> None:
    onchain_path, source_path, latest = _seed_two_snapshots(tmp_path)
    onchain = OnchainCapitalFlowStore(onchain_path)
    source = SourceContractStore(source_path)
    future = _persist_snapshot(
        onchain=onchain,
        source=source,
        observed_at_ms=1_600_000,
        usdc="110000000",
        usdt="210000000",
    )

    snapshot = build_onchain_family_snapshots(
        onchain_path,
        source_path,
        symbols=("BTCUSDT",),
        as_of_ms=1_300_100,
    )[0]
    accepted_latest = {
        value
        for item in latest
        for value in (
            item.raw_identity,
            item.envelope_identity,
            item.coverage_event_identity,
            item.observation_identity,
        )
    }
    future_ids = {
        value
        for item in future
        for value in (
            item.raw_identity,
            item.envelope_identity,
            item.coverage_event_identity,
            item.observation_identity,
        )
    }
    assert accepted_latest.issubset(set(snapshot.evidence_identities))
    assert future_ids.isdisjoint(set(snapshot.evidence_identities))


def test_onchain_family_missing_stores_do_not_create_truth(
    tmp_path: Path,
) -> None:
    onchain_path = tmp_path / "missing-onchain.sqlite3"
    source_path = tmp_path / "missing-source.sqlite3"

    snapshots = build_onchain_family_snapshots(
        onchain_path,
        source_path,
        symbols=("BTCUSDT",),
        as_of_ms=1_000,
    )

    assert snapshots == ()
    assert not onchain_path.exists()
    assert not source_path.exists()


def test_onchain_projector_is_implemented_but_smart_money_research_stays_deferred(
    tmp_path: Path,
) -> None:
    registry = {
        item.projector_id: item
        for item in accepted_stream_projector_registry()
    }
    assert registry["onchain_change"].implementation_state is (
        StreamProjectorImplementationState.IMPLEMENTED
    )
    assert registry["m5_smart_money_research"].implementation_state is (
        StreamProjectorImplementationState.RESEARCH_ONLY
    )
    policy = build_stream_materiality_policy()
    assert any(
        item.subtype == "onchain_material_change"
        for item in policy.rules
    )

    onchain_path, source_path, _ = _seed_two_snapshots(tmp_path)
    snapshot = build_onchain_family_snapshots(
        onchain_path,
        source_path,
        symbols=("BTCUSDT",),
        as_of_ms=1_300_100,
    )[0]
    stream_path = tmp_path / "stream.sqlite3"
    IntelligenceStreamForwardRuntime(stream_path).ensure_activated(
        activated_at_ms=1_300_000
    )
    result = IntelligenceStreamProductionProjector(
        stream_path
    ).project_family(
        snapshot,
        activated_at_ms=1_300_000,
    )
    assert result.narrative_identity is not None
    assert result.real_capital == 0
