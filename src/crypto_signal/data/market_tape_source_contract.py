from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitMicrostructureWireEvent,
)
from crypto_signal.data.market_data_gap_ledger import MarketDataGapEvent
from crypto_signal.data.raw_market_tape import RawMarketEvent
from crypto_signal.data.source_contract import (
    SourceCapability,
    SourceContractStore,
    SourceCoverageEvent,
    SourceCoverageState,
    SourceEnvelope,
    SourceSequenceSemantics,
    SourceTransport,
    build_source_capability,
    build_source_coverage_event,
    build_source_envelope,
)

MARKET_TAPE_FRESHNESS_BUDGET_MS = 10_000


@dataclass(frozen=True, slots=True)
class BybitMarketTapeCapabilities:
    orderbook: SourceCapability
    trades: SourceCapability

    def for_channel(self, channel: str) -> SourceCapability:
        if channel == self.orderbook.channel:
            return self.orderbook
        if channel == self.trades.channel:
            return self.trades
        raise ValueError(f"unsupported Bybit Market Tape channel: {channel}")


@dataclass(frozen=True, slots=True)
class MarketTapeSourceContractWrite:
    envelopes: tuple[SourceEnvelope, ...]
    coverage_event: SourceCoverageEvent | None

    @property
    def envelope_count(self) -> int:
        return len(self.envelopes)


def build_bybit_market_tape_capabilities(
    *,
    symbols: tuple[str, ...],
    depth: int,
) -> BybitMarketTapeCapabilities:
    if depth not in {1, 50, 200, 1000}:
        raise ValueError("Bybit source-contract orderbook depth is unsupported")
    canonical_symbols = tuple(sorted(set(symbols)))
    if not canonical_symbols:
        raise ValueError("Bybit source-contract requires symbols")
    if any(not symbol or symbol != symbol.upper() for symbol in canonical_symbols):
        raise ValueError("Bybit source-contract symbols must be uppercase")

    orderbook = build_source_capability(
        provider="bybit",
        source="market_tape_stream",
        channel=f"orderbook.{depth}",
        transport=SourceTransport.WEBSOCKET,
        sequence_semantics=SourceSequenceSemantics.MONOTONIC,
        supports_provider_event_id=True,
        freshness_budget_ms=MARKET_TAPE_FRESHNESS_BUDGET_MS,
        symbols=canonical_symbols,
    )
    trades = build_source_capability(
        provider="bybit",
        source="market_tape_stream",
        channel="publicTrade",
        transport=SourceTransport.WEBSOCKET,
        sequence_semantics=SourceSequenceSemantics.MONOTONIC,
        supports_provider_event_id=True,
        freshness_budget_ms=MARKET_TAPE_FRESHNESS_BUDGET_MS,
        symbols=canonical_symbols,
    )
    return BybitMarketTapeCapabilities(orderbook=orderbook, trades=trades)


def register_bybit_market_tape_capabilities(
    *,
    store: SourceContractStore,
    symbols: tuple[str, ...],
    depth: int,
) -> BybitMarketTapeCapabilities:
    capabilities = build_bybit_market_tape_capabilities(
        symbols=symbols,
        depth=depth,
    )
    store.append_capability(capabilities.orderbook)
    store.append_capability(capabilities.trades)
    return capabilities


def persist_bybit_wire_source_contract(
    *,
    store: SourceContractStore,
    capabilities: BybitMarketTapeCapabilities,
    wire_event: BybitMicrostructureWireEvent,
    raw_event: RawMarketEvent,
    orderbook_normalized_persisted: bool,
) -> MarketTapeSourceContractWrite:
    _require_raw_wire_match(wire_event=wire_event, raw_event=raw_event)
    capability = capabilities.for_channel(wire_event.channel)

    envelopes: list[SourceEnvelope] = []
    if wire_event.orderbook is not None:
        snapshot = wire_event.orderbook
        normalized_identity = (
            snapshot.snapshot_identity
            if orderbook_normalized_persisted
            else None
        )
        envelope = build_source_envelope(
            capability=capability,
            symbol=wire_event.symbol,
            provider_event_id=str(wire_event.update_id),
            provider_sequence=wire_event.sequence,
            event_at_ms=wire_event.event_at_ms,
            source_timestamp_ms=wire_event.source_timestamp_ms,
            observed_at_ms=wire_event.ingested_at_ms,
            ingested_at_ms=wire_event.ingested_at_ms,
            raw_identity=raw_event.event_identity,
            normalized_identity=normalized_identity,
        )
        store.append_envelope(envelope)
        envelopes.append(envelope)
    else:
        if not wire_event.trades:
            raise ValueError("Bybit source-contract event has no normalized evidence")
        for trade in wire_event.trades:
            if (
                trade.symbol != wire_event.symbol
                or trade.source_timestamp_ms != wire_event.source_timestamp_ms
                or trade.ingested_at_ms != wire_event.ingested_at_ms
            ):
                raise ValueError(
                    "Bybit source-contract trade context does not match wire event"
                )
            envelope = build_source_envelope(
                capability=capability,
                symbol=trade.symbol,
                provider_event_id=trade.exec_id,
                provider_sequence=trade.sequence,
                event_at_ms=trade.event_at_ms,
                source_timestamp_ms=trade.source_timestamp_ms,
                observed_at_ms=wire_event.ingested_at_ms,
                ingested_at_ms=wire_event.ingested_at_ms,
                raw_identity=raw_event.event_identity,
                normalized_identity=trade.trade_identity,
            )
            store.append_envelope(envelope)
            envelopes.append(envelope)

    latest = max(
        envelopes,
        key=lambda item: (
            item.event_at_ms,
            item.provider_sequence if item.provider_sequence is not None else -1,
            item.envelope_identity,
        ),
    )
    previous = store.coverage_at(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=wire_event.symbol,
        as_of_ms=wire_event.ingested_at_ms,
    )
    if (
        previous is not None
        and previous.state is SourceCoverageState.OBSERVED
        and previous.source_envelope_identity == latest.envelope_identity
    ):
        return MarketTapeSourceContractWrite(
            envelopes=tuple(envelopes),
            coverage_event=None,
        )

    reason_codes = (
        ("normalized_source_evidence_observed",)
        if latest.normalized_identity is not None
        else ("raw_evidence_observed_normalization_skipped_by_cadence",)
    )
    coverage = build_source_coverage_event(
        capability=capability,
        symbol=wire_event.symbol,
        state=SourceCoverageState.OBSERVED,
        observed_at_ms=wire_event.ingested_at_ms,
        previous=previous,
        source_envelope_identity=latest.envelope_identity,
        reason_codes=reason_codes,
    )
    store.append_coverage(coverage)
    return MarketTapeSourceContractWrite(
        envelopes=tuple(envelopes),
        coverage_event=coverage,
    )


def persist_open_gap_coverage(
    *,
    store: SourceContractStore,
    capabilities: BybitMarketTapeCapabilities,
    gaps: tuple[MarketDataGapEvent, ...],
    observed_at_ms: int,
) -> tuple[SourceCoverageEvent, ...]:
    if observed_at_ms < 0:
        raise ValueError("source-contract gap observation cannot be negative")

    recorded: list[SourceCoverageEvent] = []
    for gap in gaps:
        if gap.provider != "bybit" or gap.source != "market_tape_stream":
            raise ValueError("source-contract gap context is not Bybit Market Tape")
        capability = capabilities.for_channel(gap.channel)
        if gap.symbol not in capability.symbols:
            raise ValueError("source-contract gap symbol outside capability")

        previous = store.coverage_at(
            provider=capability.provider,
            source=capability.source,
            channel=capability.channel,
            symbol=gap.symbol,
            as_of_ms=observed_at_ms,
        )
        if (
            previous is not None
            and previous.state is SourceCoverageState.GAP
            and previous.gap_event_identity == gap.event_identity
        ):
            continue

        coverage = build_source_coverage_event(
            capability=capability,
            symbol=gap.symbol,
            state=SourceCoverageState.GAP,
            observed_at_ms=observed_at_ms,
            previous=previous,
            gap_event_identity=gap.event_identity,
            reason_codes=("market_data_gap_open",),
        )
        store.append_coverage(coverage)
        recorded.append(coverage)
    return tuple(recorded)


def _require_raw_wire_match(
    *,
    wire_event: BybitMicrostructureWireEvent,
    raw_event: RawMarketEvent,
) -> None:
    if raw_event.exchange.value != "bybit":
        raise ValueError("source-contract raw event must be Bybit")
    if (
        raw_event.channel,
        raw_event.symbol,
        raw_event.event_kind,
        raw_event.source_timestamp_ms,
        raw_event.event_at_ms,
        raw_event.sequence,
        raw_event.update_id,
    ) != (
        wire_event.channel,
        wire_event.symbol,
        wire_event.event_kind,
        wire_event.source_timestamp_ms,
        wire_event.event_at_ms,
        wire_event.sequence,
        wire_event.update_id,
    ):
        raise ValueError("source-contract raw/wire event mismatch")
