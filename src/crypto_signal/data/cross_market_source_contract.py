from __future__ import annotations

import base64
from dataclasses import dataclass

from crypto_signal.data.cross_market import (
    CrossMarketSeries,
    CrossMarketWindowObservation,
)
from crypto_signal.data.cross_market_runtime_store import CrossMarketRuntimeStore
from crypto_signal.data.source_contract import (
    SourceCapability,
    SourceContractStore,
    SourceCoverageEvent,
    SourceCoverageState,
    SourceSequenceSemantics,
    SourceTransport,
    build_source_capability,
    build_source_coverage_event,
    build_source_envelope,
    build_source_raw_payload,
)

CROSS_MARKET_SOURCE_SNAPSHOT_VERSION = "cross-market-source-snapshot-v1/1"
CROSS_MARKET_SOURCE_FRESHNESS_BUDGET_MS = 36 * 60 * 60_000
_DAY_MS = 24 * 60 * 60 * 1000

CBOE_VIX_PROVIDER = "cboe.com"
CBOE_VIX_SOURCE = "vix_history_csv"
CBOE_VIX_CHANNEL = "daily_history"
CBOE_VIX_SYMBOL = "VIX"

TREASURY_10Y_PROVIDER = "home.treasury.gov"
TREASURY_10Y_SOURCE = "treasury_yield_xml"
TREASURY_10Y_CHANNEL = "daily_history"
TREASURY_10Y_SYMBOL = "US10Y"


@dataclass(frozen=True, slots=True)
class CrossMarketSourceSnapshot:
    provider: str
    source: str
    channel: str
    symbol: str
    requested_url: str
    response_url: str
    http_status: int
    content_type: str
    payload_bytes: bytes
    observation: CrossMarketWindowObservation
    schema_version: str = CROSS_MARKET_SOURCE_SNAPSHOT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CROSS_MARKET_SOURCE_SNAPSHOT_VERSION:
            raise ValueError("unsupported cross-market source snapshot schema")
        if not all(
            value.strip()
            for value in (
                self.provider,
                self.source,
                self.channel,
                self.symbol,
                self.requested_url,
                self.response_url,
                self.content_type,
            )
        ):
            raise ValueError("cross-market source metadata must be non-empty")
        if self.symbol != self.symbol.upper():
            raise ValueError("cross-market source symbol must be uppercase")
        if self.http_status != 200:
            raise ValueError("accepted cross-market source snapshot requires HTTP 200")
        if not self.payload_bytes:
            raise ValueError("cross-market source snapshot requires exact response bytes")
        expected = source_context_for_series(self.observation.series)
        if (
            self.provider,
            self.source,
            self.channel,
            self.symbol,
        ) != expected:
            raise ValueError("cross-market source/observation context mismatch")

    def raw_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "requested_url": self.requested_url,
            "response_url": self.response_url,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "payload_base64": base64.b64encode(self.payload_bytes).decode("ascii"),
            "timestamp_semantic": "collector_receipt_time",
        }


@dataclass(frozen=True, slots=True)
class PersistedCrossMarketSourceSnapshot:
    observation_identity: str
    raw_identity: str
    capability_identity: str
    envelope_identity: str
    coverage_event_identity: str
    inserted_observation: bool


def source_context_for_series(
    series: CrossMarketSeries,
) -> tuple[str, str, str, str]:
    if series is CrossMarketSeries.CBOE_VIX_CLOSE:
        return (
            CBOE_VIX_PROVIDER,
            CBOE_VIX_SOURCE,
            CBOE_VIX_CHANNEL,
            CBOE_VIX_SYMBOL,
        )
    if series is CrossMarketSeries.US_TREASURY_10Y_YIELD:
        return (
            TREASURY_10Y_PROVIDER,
            TREASURY_10Y_SOURCE,
            TREASURY_10Y_CHANNEL,
            TREASURY_10Y_SYMBOL,
        )
    raise ValueError("unsupported cross-market source series")


def build_cross_market_source_capability(
    series: CrossMarketSeries,
) -> SourceCapability:
    provider, source, channel, symbol = source_context_for_series(series)
    return build_source_capability(
        provider=provider,
        source=source,
        channel=channel,
        transport=SourceTransport.REST,
        sequence_semantics=SourceSequenceSemantics.NONE,
        supports_provider_event_id=False,
        freshness_budget_ms=CROSS_MARKET_SOURCE_FRESHNESS_BUDGET_MS,
        symbols=(symbol,),
    )


def persist_cross_market_source_snapshot(
    *,
    snapshot: CrossMarketSourceSnapshot,
    runtime_store: CrossMarketRuntimeStore,
    source_store: SourceContractStore,
) -> PersistedCrossMarketSourceSnapshot:
    capability = build_cross_market_source_capability(
        snapshot.observation.series
    )
    source_store.append_capability(capability)
    raw = build_source_raw_payload(
        provider=snapshot.provider,
        source=snapshot.source,
        channel=snapshot.channel,
        symbol=snapshot.symbol,
        payload=snapshot.raw_payload(),
    )
    source_store.append_raw_payload(raw)

    inserted = runtime_store.append_observation(snapshot.observation)
    observed_at_ms = snapshot.observation.observed_at_ms
    event_at_ms = snapshot.observation.records[-1].day_start_ms + _DAY_MS
    envelope = build_source_envelope(
        capability=capability,
        symbol=snapshot.symbol,
        provider_event_id=None,
        provider_sequence=None,
        event_at_ms=event_at_ms,
        source_timestamp_ms=observed_at_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=observed_at_ms,
        raw_identity=raw.raw_identity,
        normalized_identity=snapshot.observation.observation_identity,
    )
    source_store.append_envelope(envelope)

    previous = source_store.latest_coverage(
        provider=snapshot.provider,
        source=snapshot.source,
        channel=snapshot.channel,
        symbol=snapshot.symbol,
    )
    coverage = build_source_coverage_event(
        capability=capability,
        symbol=snapshot.symbol,
        state=SourceCoverageState.OBSERVED,
        observed_at_ms=observed_at_ms,
        previous=previous,
        source_envelope_identity=envelope.envelope_identity,
        reason_codes=("official_daily_history_snapshot_observed",),
    )
    source_store.append_coverage(coverage)
    return PersistedCrossMarketSourceSnapshot(
        observation_identity=snapshot.observation.observation_identity,
        raw_identity=raw.raw_identity,
        capability_identity=capability.capability_identity,
        envelope_identity=envelope.envelope_identity,
        coverage_event_identity=coverage.coverage_event_identity,
        inserted_observation=inserted,
    )


def persist_cross_market_unavailable(
    *,
    series: CrossMarketSeries,
    observed_at_ms: int,
    reason_code: str,
    source_store: SourceContractStore,
) -> SourceCoverageEvent:
    if observed_at_ms < 0:
        raise ValueError("cross-market unavailable time cannot be negative")
    if not reason_code.strip():
        raise ValueError("cross-market unavailable reason is required")
    provider, source, channel, symbol = source_context_for_series(series)
    capability = build_cross_market_source_capability(series)
    source_store.append_capability(capability)
    previous = source_store.latest_coverage(
        provider=provider,
        source=source,
        channel=channel,
        symbol=symbol,
    )
    coverage = build_source_coverage_event(
        capability=capability,
        symbol=symbol,
        state=SourceCoverageState.UNAVAILABLE,
        observed_at_ms=observed_at_ms,
        previous=previous,
        source_envelope_identity=None,
        reason_codes=(reason_code,),
    )
    source_store.append_coverage(coverage)
    return coverage
