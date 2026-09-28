from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.data.adapters.defillama_stablecoins import (
    DefiLlamaStablecoinAdapter,
    DefiLlamaStablecoinSourceSnapshot,
)
from crypto_signal.data.models import DataSource
from crypto_signal.data.onchain_capital_flow import (
    StablecoinSupplyObservation,
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
DEFILLAMA_STABLECOIN_SOURCE = "defillama_public_rest"
DEFILLAMA_STABLECOIN_CHANNEL = "stablecoin_supply_snapshot"
DEFILLAMA_STABLECOIN_FRESHNESS_BUDGET_MS = 30 * 60 * 1000


@dataclass(frozen=True, slots=True)
class StablecoinSupplySourcePersistence:
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
        symbols=DefiLlamaStablecoinAdapter.SUPPORTED_ASSETS,
    )


def persist_defillama_stablecoin_snapshot(
    *,
    snapshot: DefiLlamaStablecoinSourceSnapshot,
    capital_store: OnchainCapitalFlowStore,
    source_store: SourceContractStore,
) -> tuple[StablecoinSupplyObservation, StablecoinSupplySourcePersistence]:
    capability = build_defillama_stablecoin_capability()
    if snapshot.asset not in capability.symbols:
        raise ValueError(
            "DefiLlama stablecoin snapshot outside source capability"
        )

    raw = build_source_raw_payload(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=snapshot.asset,
        payload={
            "asset_payload": snapshot.asset_payload,
            "provider_asset_id": snapshot.provider_asset_id,
            "provider_timestamp_available": False,
            "source_timestamp_semantic": (
                snapshot.source_timestamp_semantic.value
            ),
        },
    )
    observation = build_stablecoin_supply_observation(
        asset=snapshot.asset,
        network_scope="all_chains",
        provider=capability.provider,
        provider_metric_identity=(
            f"stablecoins/{snapshot.provider_asset_id}/"
            "circulating.peggedUSD"
        ),
        circulating_amount=snapshot.circulating_amount,
        usd_amount=None,
        source=DataSource.REST,
        source_timestamp_ms=snapshot.source_timestamp_ms,
        observed_at_ms=snapshot.observed_at_ms,
        ingested_at_ms=snapshot.ingested_at_ms,
        adapter_version=DefiLlamaStablecoinAdapter.ADAPTER_VERSION,
        raw_identity=raw.raw_identity,
        source_timestamp_semantic=snapshot.source_timestamp_semantic,
    )
    envelope = build_source_envelope(
        capability=capability,
        symbol=snapshot.asset,
        provider_event_id=None,
        provider_sequence=None,
        event_at_ms=snapshot.observed_at_ms,
        source_timestamp_ms=snapshot.source_timestamp_ms,
        observed_at_ms=snapshot.observed_at_ms,
        ingested_at_ms=snapshot.ingested_at_ms,
        raw_identity=raw.raw_identity,
        normalized_identity=observation.observation_identity,
    )

    source_store.append_capability(capability)
    source_store.append_raw_payload(raw)
    source_store.append_envelope(envelope)
    capital_store.append_stablecoin_supply(observation)

    previous = source_store.latest_coverage(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=snapshot.asset,
    )
    if (
        previous is not None
        and previous.state is SourceCoverageState.OBSERVED
        and previous.source_envelope_identity == envelope.envelope_identity
        and previous.observed_at_ms == snapshot.ingested_at_ms
    ):
        return observation, StablecoinSupplySourcePersistence(
            raw_identity=raw.raw_identity,
            capability_identity=capability.capability_identity,
            envelope_identity=envelope.envelope_identity,
            coverage_event_identity=previous.coverage_event_identity,
            observation_identity=observation.observation_identity,
        )

    coverage = build_source_coverage_event(
        capability=capability,
        symbol=snapshot.asset,
        state=SourceCoverageState.OBSERVED,
        observed_at_ms=snapshot.ingested_at_ms,
        previous=previous,
        source_envelope_identity=envelope.envelope_identity,
        gap_event_identity=None,
        reason_codes=(
            "provider_timestamp_unavailable",
            "stablecoin_supply_snapshot_observed",
        ),
    )
    source_store.append_coverage(coverage)
    return observation, StablecoinSupplySourcePersistence(
        raw_identity=raw.raw_identity,
        capability_identity=capability.capability_identity,
        envelope_identity=envelope.envelope_identity,
        coverage_event_identity=coverage.coverage_event_identity,
        observation_identity=observation.observation_identity,
    )
