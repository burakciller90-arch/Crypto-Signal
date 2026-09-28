from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.data.adapters.bybit_derivatives import (
    BybitLinearDerivativesSourceSnapshot,
)
from crypto_signal.data.adapters.bybit_microstructure import (
    BybitSpotMicrostructureSourceSnapshot,
)
from crypto_signal.data.derivatives import DerivativesObservation
from crypto_signal.data.market_tape import (
    MarketTapeStore,
    MarketTapeWriteDisposition,
)
from crypto_signal.data.microstructure import (
    OrderBookSnapshot,
    PublicTradeObservation,
)
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

REST_SNAPSHOT_SOURCE = "market_tape_snapshot"
REST_ORDERBOOK_CHANNEL = "rest.orderbook"
REST_RECENT_TRADE_CHANNEL = "rest.recentTrade"
REST_OPEN_INTEREST_CHANNEL = "rest.openInterest"
REST_TICKER_CHANNEL = "rest.ticker"
REST_MICROSTRUCTURE_FRESHNESS_BUDGET_MS = 90_000
REST_DERIVATIVES_FRESHNESS_BUDGET_MS = 120_000


@dataclass(frozen=True, slots=True)
class BybitRestMarketTapeCapabilities:
    orderbook: SourceCapability
    recent_trade: SourceCapability
    open_interest: SourceCapability
    ticker: SourceCapability

    def all(self) -> tuple[SourceCapability, ...]:
        return (
            self.orderbook,
            self.recent_trade,
            self.open_interest,
            self.ticker,
        )


@dataclass(frozen=True, slots=True)
class RestSourceWrite:
    raw_payload: SourceRawPayload
    envelopes: tuple[SourceEnvelope, ...]
    coverage_event: SourceCoverageEvent

    @property
    def envelope_count(self) -> int:
        return len(self.envelopes)


@dataclass(frozen=True, slots=True)
class BybitRestMarketTapeWriteResult:
    symbol: str
    orderbook_disposition: MarketTapeWriteDisposition
    trade_inserted: int
    trade_unchanged: int
    derivatives_inserted: int
    derivatives_unchanged: int
    source_writes: tuple[RestSourceWrite, ...]

    @property
    def inserted_total(self) -> int:
        return (
            (
                1
                if self.orderbook_disposition
                is MarketTapeWriteDisposition.INSERTED
                else 0
            )
            + self.trade_inserted
            + self.derivatives_inserted
        )

    @property
    def source_envelope_count(self) -> int:
        return sum(item.envelope_count for item in self.source_writes)

    @property
    def source_coverage_count(self) -> int:
        return len(self.source_writes)


def build_bybit_rest_market_tape_capabilities(
    *,
    symbols: tuple[str, ...],
) -> BybitRestMarketTapeCapabilities:
    canonical_symbols = tuple(sorted(set(symbols)))
    if not canonical_symbols:
        raise ValueError("Bybit REST source contract requires symbols")
    if any(
        not symbol or symbol != symbol.upper()
        for symbol in canonical_symbols
    ):
        raise ValueError(
            "Bybit REST source-contract symbols must be uppercase"
        )

    common = {
        "provider": "bybit",
        "source": REST_SNAPSHOT_SOURCE,
        "transport": SourceTransport.REST,
        "symbols": canonical_symbols,
    }
    return BybitRestMarketTapeCapabilities(
        orderbook=build_source_capability(
            **common,
            channel=REST_ORDERBOOK_CHANNEL,
            sequence_semantics=SourceSequenceSemantics.PROVIDER_UPDATE_ID,
            supports_provider_event_id=True,
            freshness_budget_ms=REST_MICROSTRUCTURE_FRESHNESS_BUDGET_MS,
        ),
        recent_trade=build_source_capability(
            **common,
            channel=REST_RECENT_TRADE_CHANNEL,
            sequence_semantics=SourceSequenceSemantics.PROVIDER_EVENT_ID,
            supports_provider_event_id=True,
            freshness_budget_ms=REST_MICROSTRUCTURE_FRESHNESS_BUDGET_MS,
        ),
        open_interest=build_source_capability(
            **common,
            channel=REST_OPEN_INTEREST_CHANNEL,
            sequence_semantics=SourceSequenceSemantics.NONE,
            supports_provider_event_id=False,
            freshness_budget_ms=REST_DERIVATIVES_FRESHNESS_BUDGET_MS,
        ),
        ticker=build_source_capability(
            **common,
            channel=REST_TICKER_CHANNEL,
            sequence_semantics=SourceSequenceSemantics.NONE,
            supports_provider_event_id=False,
            freshness_budget_ms=REST_DERIVATIVES_FRESHNESS_BUDGET_MS,
        ),
    )


def register_bybit_rest_market_tape_capabilities(
    *,
    store: SourceContractStore,
    symbols: tuple[str, ...],
) -> BybitRestMarketTapeCapabilities:
    capabilities = build_bybit_rest_market_tape_capabilities(
        symbols=symbols
    )
    for capability in capabilities.all():
        store.append_capability(capability)
    return capabilities


def persist_bybit_rest_market_tape_snapshot(
    *,
    market_store: MarketTapeStore,
    source_store: SourceContractStore,
    capabilities: BybitRestMarketTapeCapabilities,
    microstructure: BybitSpotMicrostructureSourceSnapshot,
    derivatives: BybitLinearDerivativesSourceSnapshot,
    symbol: str,
) -> BybitRestMarketTapeWriteResult:
    if not symbol or symbol != symbol.upper():
        raise ValueError("Bybit REST Market Tape symbol must be uppercase")
    if symbol not in capabilities.orderbook.symbols:
        raise ValueError("Bybit REST Market Tape symbol outside capability")
    _require_snapshot_context(
        microstructure=microstructure,
        derivatives=derivatives,
        symbol=symbol,
    )

    book_disposition = market_store.append_orderbook(
        microstructure.orderbook
    )
    book_identity = market_store.orderbook_identity_for_provider_update(
        exchange=microstructure.orderbook.exchange,
        market_type=microstructure.orderbook.market_type,
        symbol=symbol,
        update_id=microstructure.orderbook.update_id,
        sequence=microstructure.orderbook.sequence,
    )
    if book_identity is None:
        raise AssertionError("persisted REST orderbook identity unresolved")

    trade_dispositions: list[MarketTapeWriteDisposition] = []
    trade_identities: list[str] = []
    for trade in microstructure.trades:
        disposition = market_store.append_trade(trade)
        trade_dispositions.append(disposition)
        persisted_identity = market_store.trade_identity_for_exec_id(
            exchange=trade.exchange,
            market_type=trade.market_type,
            symbol=trade.symbol,
            exec_id=trade.exec_id,
        )
        if persisted_identity is None:
            raise AssertionError("persisted REST trade identity unresolved")
        trade_identities.append(persisted_identity)

    oi_dispositions: list[MarketTapeWriteDisposition] = []
    oi_identities: list[str] = []
    for observation in derivatives.open_interest_observations:
        disposition = market_store.append_derivatives(observation)
        oi_dispositions.append(disposition)
        persisted_identity = (
            market_store.derivatives_identity_for_semantic_observation(
                observation
            )
        )
        if persisted_identity is None:
            raise AssertionError(
                "persisted REST open-interest identity unresolved"
            )
        oi_identities.append(persisted_identity)

    ticker_disposition = market_store.append_derivatives(
        derivatives.ticker_observation
    )
    ticker_identity = (
        market_store.derivatives_identity_for_semantic_observation(
            derivatives.ticker_observation
        )
    )
    if ticker_identity is None:
        raise AssertionError("persisted REST ticker identity unresolved")

    source_writes = (
        _persist_orderbook_source(
            store=source_store,
            capability=capabilities.orderbook,
            symbol=symbol,
            payload=microstructure.orderbook_payload,
            snapshot=microstructure.orderbook,
            normalized_identity=book_identity,
            observed_at_ms=microstructure.observed_at_ms,
        ),
        _persist_trade_source(
            store=source_store,
            capability=capabilities.recent_trade,
            symbol=symbol,
            payload=microstructure.trade_payload,
            trades=microstructure.trades,
            normalized_identities=tuple(trade_identities),
            observed_at_ms=microstructure.observed_at_ms,
        ),
        _persist_derivatives_source(
            store=source_store,
            capability=capabilities.open_interest,
            symbol=symbol,
            payload=derivatives.open_interest_payload,
            observations=derivatives.open_interest_observations,
            normalized_identities=tuple(oi_identities),
            observed_at_ms=derivatives.observed_at_ms,
        ),
        _persist_derivatives_source(
            store=source_store,
            capability=capabilities.ticker,
            symbol=symbol,
            payload=derivatives.ticker_payload,
            observations=(derivatives.ticker_observation,),
            normalized_identities=(ticker_identity,),
            observed_at_ms=derivatives.observed_at_ms,
        ),
    )
    derivative_dispositions = (
        *oi_dispositions,
        ticker_disposition,
    )
    return BybitRestMarketTapeWriteResult(
        symbol=symbol,
        orderbook_disposition=book_disposition,
        trade_inserted=sum(
            item is MarketTapeWriteDisposition.INSERTED
            for item in trade_dispositions
        ),
        trade_unchanged=sum(
            item is MarketTapeWriteDisposition.UNCHANGED
            for item in trade_dispositions
        ),
        derivatives_inserted=sum(
            item is MarketTapeWriteDisposition.INSERTED
            for item in derivative_dispositions
        ),
        derivatives_unchanged=sum(
            item is MarketTapeWriteDisposition.UNCHANGED
            for item in derivative_dispositions
        ),
        source_writes=source_writes,
    )


def _persist_orderbook_source(
    *,
    store: SourceContractStore,
    capability: SourceCapability,
    symbol: str,
    payload: dict[str, object],
    snapshot: OrderBookSnapshot,
    normalized_identity: str,
    observed_at_ms: int,
) -> RestSourceWrite:
    raw = _persist_raw(
        store=store,
        capability=capability,
        symbol=symbol,
        payload=payload,
    )
    persistence_time = _next_persistence_time(
        store=store,
        capability=capability,
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        event_floor_ms=snapshot.event_at_ms,
    )
    envelope = build_source_envelope(
        capability=capability,
        symbol=symbol,
        provider_event_id=str(snapshot.update_id),
        provider_sequence=snapshot.sequence,
        event_at_ms=snapshot.event_at_ms,
        source_timestamp_ms=snapshot.source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=persistence_time,
        raw_identity=raw.raw_identity,
        normalized_identity=normalized_identity,
    )
    return _persist_observed_coverage(
        store=store,
        capability=capability,
        symbol=symbol,
        raw=raw,
        envelopes=(envelope,),
        persistence_time=persistence_time,
    )


def _persist_trade_source(
    *,
    store: SourceContractStore,
    capability: SourceCapability,
    symbol: str,
    payload: dict[str, object],
    trades: tuple[PublicTradeObservation, ...],
    normalized_identities: tuple[str, ...],
    observed_at_ms: int,
) -> RestSourceWrite:
    if len(trades) != len(normalized_identities):
        raise ValueError(
            "REST recent-trade normalized identity count mismatch"
        )
    raw = _persist_raw(
        store=store,
        capability=capability,
        symbol=symbol,
        payload=payload,
    )
    event_floor = max(
        (trade.event_at_ms for trade in trades),
        default=_payload_time_ms(payload),
    )
    persistence_time = _next_persistence_time(
        store=store,
        capability=capability,
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        event_floor_ms=event_floor,
    )
    envelopes = tuple(
        build_source_envelope(
            capability=capability,
            symbol=symbol,
            provider_event_id=trade.exec_id,
            provider_sequence=trade.sequence,
            event_at_ms=trade.event_at_ms,
            source_timestamp_ms=trade.source_timestamp_ms,
            observed_at_ms=observed_at_ms,
            ingested_at_ms=persistence_time,
            raw_identity=raw.raw_identity,
            normalized_identity=normalized_identity,
        )
        for trade, normalized_identity in zip(
            trades,
            normalized_identities,
            strict=True,
        )
    )
    if not envelopes:
        response_time_ms = _payload_time_ms(payload)
        envelopes = (
            build_source_envelope(
                capability=capability,
                symbol=symbol,
                provider_event_id=None,
                provider_sequence=None,
                event_at_ms=response_time_ms,
                source_timestamp_ms=response_time_ms,
                observed_at_ms=observed_at_ms,
                ingested_at_ms=persistence_time,
                raw_identity=raw.raw_identity,
                normalized_identity=None,
            ),
        )
    return _persist_observed_coverage(
        store=store,
        capability=capability,
        symbol=symbol,
        raw=raw,
        envelopes=envelopes,
        persistence_time=persistence_time,
    )


def _persist_derivatives_source(
    *,
    store: SourceContractStore,
    capability: SourceCapability,
    symbol: str,
    payload: dict[str, object],
    observations: tuple[DerivativesObservation, ...],
    normalized_identities: tuple[str, ...],
    observed_at_ms: int,
) -> RestSourceWrite:
    if len(observations) != len(normalized_identities):
        raise ValueError(
            "REST derivatives normalized identity count mismatch"
        )
    raw = _persist_raw(
        store=store,
        capability=capability,
        symbol=symbol,
        payload=payload,
    )
    event_floor = max(
        (item.event_at_ms for item in observations),
        default=_payload_time_ms(payload),
    )
    persistence_time = _next_persistence_time(
        store=store,
        capability=capability,
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        event_floor_ms=event_floor,
    )
    envelopes = tuple(
        build_source_envelope(
            capability=capability,
            symbol=symbol,
            provider_event_id=None,
            provider_sequence=None,
            event_at_ms=observation.event_at_ms,
            source_timestamp_ms=observation.source_timestamp_ms,
            observed_at_ms=observed_at_ms,
            ingested_at_ms=persistence_time,
            raw_identity=raw.raw_identity,
            normalized_identity=normalized_identity,
        )
        for observation, normalized_identity in zip(
            observations,
            normalized_identities,
            strict=True,
        )
    )
    if not envelopes:
        response_time_ms = _payload_time_ms(payload)
        envelopes = (
            build_source_envelope(
                capability=capability,
                symbol=symbol,
                provider_event_id=None,
                provider_sequence=None,
                event_at_ms=response_time_ms,
                source_timestamp_ms=response_time_ms,
                observed_at_ms=observed_at_ms,
                ingested_at_ms=persistence_time,
                raw_identity=raw.raw_identity,
                normalized_identity=None,
            ),
        )
    return _persist_observed_coverage(
        store=store,
        capability=capability,
        symbol=symbol,
        raw=raw,
        envelopes=envelopes,
        persistence_time=persistence_time,
    )


def _persist_raw(
    *,
    store: SourceContractStore,
    capability: SourceCapability,
    symbol: str,
    payload: dict[str, object],
) -> SourceRawPayload:
    raw = build_source_raw_payload(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=symbol,
        payload=payload,
    )
    store.append_raw_payload(raw)
    return raw


def _persist_observed_coverage(
    *,
    store: SourceContractStore,
    capability: SourceCapability,
    symbol: str,
    raw: SourceRawPayload,
    envelopes: tuple[SourceEnvelope, ...],
    persistence_time: int,
) -> RestSourceWrite:
    if not envelopes:
        raise ValueError("REST source write requires an envelope")
    for envelope in envelopes:
        store.append_envelope(envelope)
    latest = max(
        envelopes,
        key=lambda item: (
            item.event_at_ms,
            item.provider_sequence
            if item.provider_sequence is not None
            else -1,
            item.envelope_identity,
        ),
    )
    previous = store.latest_coverage(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=symbol,
    )
    coverage = build_source_coverage_event(
        capability=capability,
        symbol=symbol,
        state=SourceCoverageState.OBSERVED,
        observed_at_ms=persistence_time,
        previous=previous,
        source_envelope_identity=latest.envelope_identity,
        reason_codes=(
            ("rest_raw_only_source_observed",)
            if latest.normalized_identity is None
            else ("rest_normalized_source_evidence_observed",)
        ),
    )
    store.append_coverage(coverage)
    return RestSourceWrite(
        raw_payload=raw,
        envelopes=envelopes,
        coverage_event=coverage,
    )


def _next_persistence_time(
    *,
    store: SourceContractStore,
    capability: SourceCapability,
    symbol: str,
    observed_at_ms: int,
    event_floor_ms: int,
) -> int:
    if observed_at_ms < 0 or event_floor_ms < 0:
        raise ValueError("REST source times cannot be negative")
    previous = store.latest_coverage(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=symbol,
    )
    previous_floor = (
        0
        if previous is None
        else previous.observed_at_ms + 1
    )
    return max(observed_at_ms, event_floor_ms, previous_floor)


def _payload_time_ms(payload: dict[str, object]) -> int:
    raw = payload.get("time")
    if raw is None:
        raise ValueError("Bybit REST payload is missing response time")
    value = int(str(raw))
    if value < 0:
        raise ValueError("Bybit REST payload response time cannot be negative")
    return value


def _require_snapshot_context(
    *,
    microstructure: BybitSpotMicrostructureSourceSnapshot,
    derivatives: BybitLinearDerivativesSourceSnapshot,
    symbol: str,
) -> None:
    if microstructure.orderbook.symbol != symbol:
        raise ValueError("REST orderbook snapshot symbol mismatch")
    if any(trade.symbol != symbol for trade in microstructure.trades):
        raise ValueError("REST recent-trade snapshot symbol mismatch")
    if any(
        item.symbol != symbol
        for item in derivatives.open_interest_observations
    ):
        raise ValueError("REST open-interest snapshot symbol mismatch")
    if derivatives.ticker_observation.symbol != symbol:
        raise ValueError("REST ticker snapshot symbol mismatch")
