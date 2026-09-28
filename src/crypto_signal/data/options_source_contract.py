from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.data.adapters.bybit_options import (
    BybitOptionSurfaceSourceSnapshot,
)
from crypto_signal.data.options_surface_store import OptionsSurfaceStore
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

BYBIT_OPTIONS_PROVIDER = "bybit"
BYBIT_OPTIONS_SOURCE = "bybit_v5_public_rest"
BYBIT_OPTIONS_CHANNEL = "option_surface_snapshot"
BYBIT_OPTIONS_FRESHNESS_BUDGET_MS = 120_000


@dataclass(frozen=True, slots=True)
class OptionSurfaceSourcePersistence:
    raw_identity: str
    capability_identity: str
    envelope_identity: str
    coverage_event_identity: str
    surface_identity: str


def build_bybit_options_capability() -> SourceCapability:
    return build_source_capability(
        provider=BYBIT_OPTIONS_PROVIDER,
        source=BYBIT_OPTIONS_SOURCE,
        channel=BYBIT_OPTIONS_CHANNEL,
        transport=SourceTransport.REST,
        sequence_semantics=SourceSequenceSemantics.NONE,
        supports_provider_event_id=False,
        freshness_budget_ms=BYBIT_OPTIONS_FRESHNESS_BUDGET_MS,
        symbols=("BTC", "ETH"),
    )


def persist_bybit_option_surface_snapshot(
    *,
    snapshot: BybitOptionSurfaceSourceSnapshot,
    options_store: OptionsSurfaceStore,
    source_store: SourceContractStore,
) -> OptionSurfaceSourcePersistence:
    capability = build_bybit_options_capability()
    if snapshot.base_coin not in capability.symbols:
        raise ValueError("option snapshot base coin outside source capability")

    options_store.append_snapshot(
        instrument_specs=snapshot.instrument_specs,
        surface=snapshot.surface,
    )

    raw = build_source_raw_payload(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=snapshot.base_coin,
        payload={
            "instrument_payloads": snapshot.instrument_payloads,
            "ticker_payload": snapshot.ticker_payload,
        },
    )
    envelope = build_source_envelope(
        capability=capability,
        symbol=snapshot.base_coin,
        provider_event_id=None,
        provider_sequence=None,
        event_at_ms=snapshot.surface.source_timestamp_ms,
        source_timestamp_ms=snapshot.surface.source_timestamp_ms,
        observed_at_ms=snapshot.surface.observed_at_ms,
        ingested_at_ms=snapshot.surface.ingested_at_ms,
        raw_identity=raw.raw_identity,
        normalized_identity=snapshot.surface.surface_identity,
    )

    source_store.append_capability(capability)
    source_store.append_raw_payload(raw)
    source_store.append_envelope(envelope)
    previous = source_store.latest_coverage(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=snapshot.base_coin,
    )
    if (
        previous is not None
        and previous.state is SourceCoverageState.OBSERVED
        and previous.source_envelope_identity == envelope.envelope_identity
        and previous.observed_at_ms == snapshot.surface.ingested_at_ms
    ):
        return OptionSurfaceSourcePersistence(
            raw_identity=raw.raw_identity,
            capability_identity=capability.capability_identity,
            envelope_identity=envelope.envelope_identity,
            coverage_event_identity=previous.coverage_event_identity,
            surface_identity=snapshot.surface.surface_identity,
        )

    coverage = build_source_coverage_event(
        capability=capability,
        symbol=snapshot.base_coin,
        state=SourceCoverageState.OBSERVED,
        observed_at_ms=snapshot.surface.ingested_at_ms,
        previous=previous,
        source_envelope_identity=envelope.envelope_identity,
        gap_event_identity=None,
        reason_codes=("option_surface_snapshot_observed",),
    )
    source_store.append_coverage(coverage)

    return OptionSurfaceSourcePersistence(
        raw_identity=raw.raw_identity,
        capability_identity=capability.capability_identity,
        envelope_identity=envelope.envelope_identity,
        coverage_event_identity=coverage.coverage_event_identity,
        surface_identity=snapshot.surface.surface_identity,
    )
