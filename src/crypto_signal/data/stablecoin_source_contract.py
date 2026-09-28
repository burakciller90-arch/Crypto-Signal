from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.data.adapters.defillama_stablecoins import (
    DefiLlamaStablecoinAssetSnapshot,
    DefiLlamaStablecoinsAdapter,
    DefiLlamaStablecoinSourceSnapshot,
)
from crypto_signal.data.models import DataSource
from crypto_signal.data.onchain_capital_flow import (
    StablecoinSourceTimestampSemantic,
    build_stablecoin_supply_observation,
)
from crypto_signal.data.onchain_capital_flow_store import (
    OnchainCapitalFlowStore,
)
from crypto_signal.data.source_contract import (
    SourceCapability,
    SourceContractStore,
    SourceCoverageState,
    SourceSequenceSemantics,
    SourceTransport,
    build_source_capability,
    build_source_coverage_event,
    build_source_envelope,
    build_source_raw_payload,
)

DEFILLAMA_STABLECOIN_PROVIDER = "defillama"
DEFILLAMA_STABLECOIN_SOURCE = "defillama_public_api"
DEFILLAMA_STABLECOIN_CHANNEL = "stablecoin_supply_snapshot"
DEFILLAMA_STABLECOIN_FRESHNESS_BUDGET_MS = 30 * 60 * 1000
DEFILLAMA_STABLECOIN_NETWORK_SCOPE = "all_chains"


@dataclass(frozen=True, slots=True)
class StablecoinSupplySourcePersistence:
    symbol: str
    raw_identity: str
    capability_identity: str
    envelope_identity: str
    coverage_event_identity: str
    observation_identity: str


def build_defillama_stablecoin_capability() -> SourceCapability:
    return build_source_capability(
        provider=DEFILLAMA_STABLECOIN_PROVIDER,
        source=DEFILLAMA_STABLECOIN_SOURCE,
        channel=DEFILLAMA_STABLECOIN_CHANNEL,
        transport=SourceTransport.REST,
        sequence_semantics=SourceSequenceSemantics.NONE,
        supports_provider_event_id=False,
        freshness_budget_ms=DEFILLAMA_STABLECOIN_FRESHNESS_BUDGET_MS,
        symbols=("USDC", "USDT"),
    )


def persist_defillama_stablecoin_snapshot(
    *,
    snapshot: DefiLlamaStablecoinSourceSnapshot,
    onchain_store: OnchainCapitalFlowStore,
    source_store: SourceContractStore,
) -> tuple[StablecoinSupplySourcePersistence, ...]:
    capability = build_defillama_stablecoin_capability()
    results: list[StablecoinSupplySourcePersistence] = []
    for asset in snapshot.assets:
        if asset.symbol not in capability.symbols:
            raise ValueError(
                "DefiLlama stablecoin outside source capability"
            )
        results.append(
            _persist_asset(
                asset=asset,
                snapshot=snapshot,
                capability=capability,
                onchain_store=onchain_store,
                source_store=source_store,
            )
        )
    return tuple(results)


def _persist_asset(
    *,
    asset: DefiLlamaStablecoinAssetSnapshot,
    snapshot: DefiLlamaStablecoinSourceSnapshot,
    capability: SourceCapability,
    onchain_store: OnchainCapitalFlowStore,
    source_store: SourceContractStore,
) -> StablecoinSupplySourcePersistence:
    raw = build_source_raw_payload(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=asset.symbol,
        payload=asset.raw_payload,
    )
    observation = build_stablecoin_supply_observation(
        asset=asset.symbol,
        network_scope=DEFILLAMA_STABLECOIN_NETWORK_SCOPE,
        provider=capability.provider,
        provider_metric_identity="circulating.peggedUSD",
        circulating_amount=asset.circulating_pegged_usd,
        usd_amount=asset.circulating_pegged_usd,
        source=DataSource.REST,
        source_timestamp_ms=snapshot.observed_at_ms,
        observed_at_ms=snapshot.observed_at_ms,
        ingested_at_ms=snapshot.observed_at_ms,
        adapter_version=DefiLlamaStablecoinsAdapter.ADAPTER_VERSION,
        raw_identity=raw.raw_identity,
        source_timestamp_semantic=(
            StablecoinSourceTimestampSemantic.COLLECTOR_RECEIPT
        ),
    )
    envelope = build_source_envelope(
        capability=capability,
        symbol=asset.symbol,
        provider_event_id=None,
        provider_sequence=None,
        event_at_ms=observation.source_timestamp_ms,
        source_timestamp_ms=observation.source_timestamp_ms,
        observed_at_ms=observation.observed_at_ms,
        ingested_at_ms=observation.ingested_at_ms,
        raw_identity=raw.raw_identity,
        normalized_identity=observation.observation_identity,
    )

    onchain_store.append_stablecoin_supply(observation)
    source_store.append_capability(capability)
    source_store.append_raw_payload(raw)
    source_store.append_envelope(envelope)

    previous = source_store.latest_coverage(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=asset.symbol,
    )
    if (
        previous is not None
        and previous.state is SourceCoverageState.OBSERVED
        and previous.source_envelope_identity == envelope.envelope_identity
        and previous.observed_at_ms == observation.ingested_at_ms
    ):
        return StablecoinSupplySourcePersistence(
            symbol=asset.symbol,
            raw_identity=raw.raw_identity,
            capability_identity=capability.capability_identity,
            envelope_identity=envelope.envelope_identity,
            coverage_event_identity=previous.coverage_event_identity,
            observation_identity=observation.observation_identity,
        )

    coverage = build_source_coverage_event(
        capability=capability,
        symbol=asset.symbol,
        state=SourceCoverageState.OBSERVED,
        observed_at_ms=observation.ingested_at_ms,
        previous=previous,
        source_envelope_identity=envelope.envelope_identity,
        gap_event_identity=None,
        reason_codes=("stablecoin_supply_snapshot_observed",),
    )
    source_store.append_coverage(coverage)
    return StablecoinSupplySourcePersistence(
        symbol=asset.symbol,
        raw_identity=raw.raw_identity,
        capability_identity=capability.capability_identity,
        envelope_identity=envelope.envelope_identity,
        coverage_event_identity=coverage.coverage_event_identity,
        observation_identity=observation.observation_identity,
    )
