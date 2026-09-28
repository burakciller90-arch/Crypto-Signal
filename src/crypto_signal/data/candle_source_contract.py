from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from crypto_signal.data.adapters.base import CandleSourceSnapshot
from crypto_signal.data.models import Candle
from crypto_signal.data.source_contract import (
    SourceCapability,
    SourceContractStore,
    SourceCoverageEvent,
    SourceCoverageState,
    SourceEnvelope,
    SourceRawPayload,
    SourceSequenceSemantics,
    SourceTransport,
    build_source_capability,
    build_source_coverage_event,
    build_source_envelope,
    build_source_raw_payload,
)
from crypto_signal.data.store import CandleStore, WriteDisposition
from crypto_signal.data.timeframes import spec

MIN_CANDLE_FRESHNESS_BUDGET_MS = 30 * 60 * 1000


@dataclass(frozen=True, slots=True)
class CandleSourcePersistence:
    snapshot: CandleSourceSnapshot
    capability: SourceCapability
    raw_payload: SourceRawPayload
    envelopes: tuple[SourceEnvelope, ...]
    coverage_event: SourceCoverageEvent
    dispositions: tuple[tuple[WriteDisposition, int], ...]

    def count(self, disposition: WriteDisposition) -> int:
        return dict(self.dispositions).get(disposition, 0)


def build_candle_source_capability(
    snapshot: CandleSourceSnapshot,
) -> SourceCapability:
    return build_source_capability(
        provider=snapshot.provider,
        source=snapshot.source,
        channel=snapshot.channel,
        transport=SourceTransport.REST,
        sequence_semantics=SourceSequenceSemantics.NONE,
        supports_provider_event_id=False,
        freshness_budget_ms=max(
            MIN_CANDLE_FRESHNESS_BUDGET_MS,
            2 * spec(snapshot.timeframe).duration_ms,
        ),
        symbols=(snapshot.symbol,),
    )


def persist_candle_source_snapshot(
    *,
    candle_store: CandleStore,
    source_store: SourceContractStore,
    snapshot: CandleSourceSnapshot,
) -> CandleSourcePersistence:
    capability = build_candle_source_capability(snapshot)
    source_store.append_capability(capability)

    raw = build_source_raw_payload(
        provider=snapshot.provider,
        source=snapshot.source,
        channel=snapshot.channel,
        symbol=snapshot.symbol,
        payload=snapshot.raw_payload,
    )
    source_store.append_raw_payload(raw)

    counts: Counter[WriteDisposition] = Counter()
    normalized: list[tuple[Candle, str]] = []
    for candle in snapshot.candles:
        counts[candle_store.upsert(candle)] += 1
        identity = candle_store.normalized_identity_for_key(
            exchange=candle.exchange,
            market_type=candle.market_type,
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            open_time_ms=candle.open_time_ms,
        )
        if identity is None:
            raise AssertionError(
                "persisted candle normalized identity unresolved"
            )
        normalized.append((candle, identity))

    previous = source_store.latest_coverage(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=snapshot.symbol,
    )
    event_floor_ms = max(
        (
            candle.close_time_ms
            if candle.is_closed
            else min(
                candle.source_timestamp_ms,
                snapshot.observed_at_ms,
            )
            for candle in snapshot.candles
        ),
        default=min(
            snapshot.source_timestamp_ms,
            snapshot.observed_at_ms,
        ),
    )
    persistence_time = max(
        snapshot.observed_at_ms,
        event_floor_ms,
        (
            0
            if previous is None
            else previous.observed_at_ms + 1
        ),
    )

    envelopes = tuple(
        build_source_envelope(
            capability=capability,
            symbol=snapshot.symbol,
            provider_event_id=None,
            provider_sequence=None,
            event_at_ms=(
                candle.close_time_ms
                if candle.is_closed
                else min(
                    candle.source_timestamp_ms,
                    snapshot.observed_at_ms,
                )
            ),
            source_timestamp_ms=candle.source_timestamp_ms,
            observed_at_ms=snapshot.observed_at_ms,
            ingested_at_ms=persistence_time,
            raw_identity=raw.raw_identity,
            normalized_identity=identity,
        )
        for candle, identity in normalized
    )
    if not envelopes:
        envelopes = (
            build_source_envelope(
                capability=capability,
                symbol=snapshot.symbol,
                provider_event_id=None,
                provider_sequence=None,
                event_at_ms=min(
                    snapshot.source_timestamp_ms,
                    snapshot.observed_at_ms,
                ),
                source_timestamp_ms=snapshot.source_timestamp_ms,
                observed_at_ms=snapshot.observed_at_ms,
                ingested_at_ms=persistence_time,
                raw_identity=raw.raw_identity,
                normalized_identity=None,
            ),
        )

    for envelope in envelopes:
        source_store.append_envelope(envelope)

    latest = max(
        envelopes,
        key=lambda item: (
            item.event_at_ms,
            item.source_timestamp_ms,
            item.envelope_identity,
        ),
    )
    coverage = build_source_coverage_event(
        capability=capability,
        symbol=snapshot.symbol,
        state=SourceCoverageState.OBSERVED,
        observed_at_ms=persistence_time,
        previous=previous,
        source_envelope_identity=latest.envelope_identity,
        reason_codes=(
            ("candle_raw_only_source_observed",)
            if latest.normalized_identity is None
            else ("candle_normalized_source_observed",)
        ),
    )
    source_store.append_coverage(coverage)

    return CandleSourcePersistence(
        snapshot=snapshot,
        capability=capability,
        raw_payload=raw,
        envelopes=envelopes,
        coverage_event=coverage,
        dispositions=tuple(
            sorted(counts.items(), key=lambda item: item[0].value)
        ),
    )
