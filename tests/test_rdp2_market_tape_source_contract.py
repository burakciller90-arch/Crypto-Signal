from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitMicrostructureWireEvent,
    BybitSpotMicrostructureStream,
    BybitSpotOrderBookState,
    parse_bybit_public_trade_payload,
)
from crypto_signal.data.market_data_gap_ledger import build_gap_observed
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_source_contract import (
    MARKET_TAPE_FRESHNESS_BUDGET_MS,
    persist_bybit_wire_source_contract,
    persist_open_gap_coverage,
    register_bybit_market_tape_capabilities,
)
from crypto_signal.data.market_tape_wire_collection import persist_bybit_wire_stream
from crypto_signal.data.models import Exchange
from crypto_signal.data.raw_market_tape import RawMarketEvent, RawMarketTapeStore
from crypto_signal.data.source_contract import (
    SourceContractStore,
    SourceCoverageState,
    SourceFreshnessState,
    assess_source_freshness,
)

ADAPTER_VERSION = BybitSpotMicrostructureStream.ADAPTER_VERSION


def _book_payload(
    *,
    kind: str,
    ts: int,
    cts: int,
    update_id: int,
    sequence: int,
    bids: list[list[str]],
    asks: list[list[str]],
) -> dict[str, object]:
    return {
        "topic": "orderbook.50.BTCUSDT",
        "type": kind,
        "ts": ts,
        "cts": cts,
        "data": {
            "s": "BTCUSDT",
            "b": bids,
            "a": asks,
            "u": update_id,
            "seq": sequence,
        },
    }


def _book_wire_event(
    *,
    state: BybitSpotOrderBookState,
    payload: dict[str, object],
    ingested_at_ms: int,
) -> BybitMicrostructureWireEvent:
    snapshot = state.apply_payload(payload, ingested_at_ms=ingested_at_ms)
    data = payload["data"]
    assert isinstance(data, dict)
    return BybitMicrostructureWireEvent(
        symbol="BTCUSDT",
        channel="orderbook.50",
        event_kind=str(payload["type"]),
        source_timestamp_ms=int(payload["ts"]),
        event_at_ms=int(payload["cts"]),
        ingested_at_ms=ingested_at_ms,
        sequence=int(data["seq"]),
        update_id=int(data["u"]),
        raw_payload=payload,
        orderbook=snapshot,
    )


def _trade_payload() -> dict[str, object]:
    return {
        "topic": "publicTrade.BTCUSDT",
        "type": "snapshot",
        "ts": 2_510,
        "data": [
            {
                "T": 2_501,
                "s": "BTCUSDT",
                "S": "Buy",
                "v": "0.25",
                "p": "100.5",
                "i": "trade-1",
                "BT": False,
                "RPI": False,
                "seq": 100,
            },
            {
                "T": 2_502,
                "s": "BTCUSDT",
                "S": "Sell",
                "v": "0.10",
                "p": "100.4",
                "i": "trade-2",
                "BT": False,
                "RPI": False,
                "seq": 100,
            },
        ],
    }


def _trade_wire_event(*, ingested_at_ms: int = 2_520) -> BybitMicrostructureWireEvent:
    payload = _trade_payload()
    trades = parse_bybit_public_trade_payload(
        payload,
        expected_symbol="BTCUSDT",
        adapter_version=ADAPTER_VERSION,
        ingested_at_ms=ingested_at_ms,
    )
    return BybitMicrostructureWireEvent(
        symbol="BTCUSDT",
        channel="publicTrade",
        event_kind="trade_batch",
        source_timestamp_ms=2_510,
        event_at_ms=2_502,
        ingested_at_ms=ingested_at_ms,
        sequence=100,
        update_id=0,
        raw_payload=payload,
        trades=trades,
    )


def _append_raw(
    raw_store: RawMarketTapeStore,
    wire: BybitMicrostructureWireEvent,
) -> RawMarketEvent:
    _, raw = raw_store.append(
        exchange=Exchange.BYBIT,
        channel=wire.channel,
        symbol=wire.symbol,
        event_kind=wire.event_kind,
        source_timestamp_ms=wire.source_timestamp_ms,
        event_at_ms=wire.event_at_ms,
        ingested_at_ms=wire.ingested_at_ms,
        sequence=wire.sequence,
        update_id=wire.update_id,
        payload=wire.raw_payload,
    )
    return raw


def test_bybit_source_capabilities_lock_live_microstructure_contract(tmp_path) -> None:
    store = SourceContractStore(tmp_path / "source_contract.sqlite3")
    capabilities = register_bybit_market_tape_capabilities(
        store=store,
        symbols=("SOLUSDT", "BTCUSDT", "ETHUSDT"),
        depth=50,
    )

    assert capabilities.orderbook.channel == "orderbook.50"
    assert capabilities.trades.channel == "publicTrade"
    assert capabilities.orderbook.freshness_budget_ms == (
        MARKET_TAPE_FRESHNESS_BUDGET_MS
    )
    assert capabilities.trades.freshness_budget_ms == 10_000
    assert capabilities.orderbook.symbols == (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
    )
    assert store.capability(capabilities.orderbook.capability_identity) == (
        capabilities.orderbook
    )


def test_orderbook_source_contract_preserves_raw_to_normalized_lineage(
    tmp_path,
) -> None:
    raw_store = RawMarketTapeStore(tmp_path / "raw.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    capabilities = register_bybit_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
        depth=50,
    )
    state = BybitSpotOrderBookState(
        symbol="BTCUSDT",
        depth=50,
        adapter_version=ADAPTER_VERSION,
    )
    wire = _book_wire_event(
        state=state,
        payload=_book_payload(
            kind="snapshot",
            ts=1_010,
            cts=1_009,
            update_id=10,
            sequence=20,
            bids=[["100", "2"], ["99", "3"]],
            asks=[["101", "2"], ["102", "3"]],
        ),
        ingested_at_ms=1_020,
    )
    raw = _append_raw(raw_store, wire)

    write = persist_bybit_wire_source_contract(
        store=source_store,
        capabilities=capabilities,
        wire_event=wire,
        raw_event=raw,
        orderbook_normalized_persisted=True,
        coverage_observed_at_ms=1_025,
    )

    assert write.envelope_count == 1
    envelope = write.envelopes[0]
    assert envelope.raw_identity == raw.event_identity
    assert envelope.normalized_identity == wire.orderbook.snapshot_identity
    assert envelope.provider_event_id == "10"
    assert envelope.provider_sequence == 20
    assert envelope.observed_at_ms == 1_020
    assert envelope.ingested_at_ms == 1_025
    assert write.coverage_event is not None
    assert write.coverage_event.state is SourceCoverageState.OBSERVED
    assert write.coverage_event.source_envelope_identity == envelope.envelope_identity
    assert write.coverage_event.reason_codes == (
        "normalized_source_evidence_observed",
    )

    fresh = assess_source_freshness(
        capability=capabilities.orderbook,
        envelope=envelope,
        as_of_ms=2_000,
    )
    assert fresh.state is SourceFreshnessState.FRESH


def test_orderbook_cadence_skip_is_explicit_not_fake_normalized_truth(
    tmp_path,
) -> None:
    raw_store = RawMarketTapeStore(tmp_path / "raw.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    capabilities = register_bybit_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
        depth=50,
    )
    state = BybitSpotOrderBookState(
        symbol="BTCUSDT",
        depth=50,
        adapter_version=ADAPTER_VERSION,
    )
    first = _book_wire_event(
        state=state,
        payload=_book_payload(
            kind="snapshot",
            ts=1_010,
            cts=1_009,
            update_id=10,
            sequence=20,
            bids=[["100", "2"]],
            asks=[["101", "2"]],
        ),
        ingested_at_ms=1_020,
    )
    first_raw = _append_raw(raw_store, first)
    persist_bybit_wire_source_contract(
        store=source_store,
        capabilities=capabilities,
        wire_event=first,
        raw_event=first_raw,
        orderbook_normalized_persisted=True,
        coverage_observed_at_ms=1_025,
    )

    skipped = _book_wire_event(
        state=state,
        payload=_book_payload(
            kind="delta",
            ts=1_210,
            cts=1_209,
            update_id=11,
            sequence=21,
            bids=[["100", "2.5"]],
            asks=[],
        ),
        ingested_at_ms=1_220,
    )
    skipped_raw = _append_raw(raw_store, skipped)
    write = persist_bybit_wire_source_contract(
        store=source_store,
        capabilities=capabilities,
        wire_event=skipped,
        raw_event=skipped_raw,
        orderbook_normalized_persisted=False,
        coverage_observed_at_ms=1_230,
    )

    assert write.envelopes[0].raw_identity == skipped_raw.event_identity
    assert write.envelopes[0].normalized_identity is None
    assert write.coverage_event is not None
    assert write.coverage_event.reason_codes == (
        "raw_evidence_observed_normalization_skipped_by_cadence",
    )


def test_trade_batch_maps_one_raw_event_to_each_exact_normalized_trade(
    tmp_path,
) -> None:
    raw_store = RawMarketTapeStore(tmp_path / "raw.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    capabilities = register_bybit_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
        depth=50,
    )
    wire = _trade_wire_event()
    raw = _append_raw(raw_store, wire)

    write = persist_bybit_wire_source_contract(
        store=source_store,
        capabilities=capabilities,
        wire_event=wire,
        raw_event=raw,
        orderbook_normalized_persisted=False,
        coverage_observed_at_ms=2_530,
    )

    assert write.envelope_count == 2
    assert {item.raw_identity for item in write.envelopes} == {
        raw.event_identity
    }
    assert {item.provider_event_id for item in write.envelopes} == {
        "trade-1",
        "trade-2",
    }
    assert {item.normalized_identity for item in write.envelopes} == {
        trade.trade_identity for trade in wire.trades
    }
    assert write.coverage_event is not None
    latest = max(write.envelopes, key=lambda item: item.event_at_ms)
    assert write.coverage_event.source_envelope_identity == latest.envelope_identity


def test_reobserved_raw_payload_keeps_same_raw_sha_but_new_pit_envelope(
    tmp_path,
) -> None:
    raw_store = RawMarketTapeStore(tmp_path / "raw.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    capabilities = register_bybit_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
        depth=50,
    )
    first_wire = _trade_wire_event(ingested_at_ms=2_520)
    first_raw = _append_raw(raw_store, first_wire)
    first = persist_bybit_wire_source_contract(
        store=source_store,
        capabilities=capabilities,
        wire_event=first_wire,
        raw_event=first_raw,
        orderbook_normalized_persisted=False,
        coverage_observed_at_ms=2_530,
    )

    replay_wire = _trade_wire_event(ingested_at_ms=3_520)
    replay_raw = _append_raw(raw_store, replay_wire)
    replay = persist_bybit_wire_source_contract(
        store=source_store,
        capabilities=capabilities,
        wire_event=replay_wire,
        raw_event=replay_raw,
        orderbook_normalized_persisted=False,
        coverage_observed_at_ms=3_530,
    )

    assert replay_raw.event_identity == first_raw.event_identity
    assert replay.envelopes[0].raw_identity == first.envelopes[0].raw_identity
    assert replay.envelopes[0].envelope_identity != first.envelopes[0].envelope_identity
    assert (
        source_store.latest_envelope_at(
            provider="bybit",
            source="market_tape_stream",
            channel="publicTrade",
            symbol="BTCUSDT",
            as_of_ms=3_000,
        ).envelope_identity
        == max(first.envelopes, key=lambda item: item.event_at_ms).envelope_identity
    )


def test_coverage_uses_monotonic_persistence_time_when_receipt_clock_regresses(
    tmp_path,
) -> None:
    raw_store = RawMarketTapeStore(tmp_path / "raw.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    capabilities = register_bybit_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
        depth=50,
    )
    state = BybitSpotOrderBookState(
        symbol="BTCUSDT",
        depth=50,
        adapter_version=ADAPTER_VERSION,
    )
    first = _book_wire_event(
        state=state,
        payload=_book_payload(
            kind="snapshot",
            ts=2_010,
            cts=2_009,
            update_id=20,
            sequence=30,
            bids=[["100", "2"]],
            asks=[["101", "2"]],
        ),
        ingested_at_ms=2_020,
    )
    first_raw = _append_raw(raw_store, first)
    first_write = persist_bybit_wire_source_contract(
        store=source_store,
        capabilities=capabilities,
        wire_event=first,
        raw_event=first_raw,
        orderbook_normalized_persisted=True,
        coverage_observed_at_ms=3_000,
    )
    assert first_write.envelopes[0].ingested_at_ms == 3_000

    regressed = _book_wire_event(
        state=state,
        payload=_book_payload(
            kind="delta",
            ts=2_210,
            cts=2_209,
            update_id=21,
            sequence=31,
            bids=[["100", "2.5"]],
            asks=[],
        ),
        ingested_at_ms=2_015,
    )
    regressed_raw = _append_raw(raw_store, regressed)
    write = persist_bybit_wire_source_contract(
        store=source_store,
        capabilities=capabilities,
        wire_event=regressed,
        raw_event=regressed_raw,
        orderbook_normalized_persisted=False,
        coverage_observed_at_ms=3_100,
    )

    assert write.envelopes[0].observed_at_ms == 2_015
    assert write.envelopes[0].ingested_at_ms == 3_100
    assert write.coverage_event is not None
    assert write.coverage_event.previous_event_identity == (
        first_write.coverage_event.coverage_event_identity
    )
    assert (
        source_store.latest_envelope_at(
            provider="bybit",
            source="market_tape_stream",
            channel="orderbook.50",
            symbol="BTCUSDT",
            as_of_ms=3_050,
        ).envelope_identity
        == first_write.envelopes[0].envelope_identity
    )


def test_gap_coverage_reuses_exact_gap_ledger_identity_and_recovers_to_observed(
    tmp_path,
) -> None:
    raw_store = RawMarketTapeStore(tmp_path / "raw.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    capabilities = register_bybit_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
        depth=50,
    )
    wire = _trade_wire_event(ingested_at_ms=2_520)
    raw = _append_raw(raw_store, wire)
    observed = persist_bybit_wire_source_contract(
        store=source_store,
        capabilities=capabilities,
        wire_event=wire,
        raw_event=raw,
        orderbook_normalized_persisted=False,
        coverage_observed_at_ms=2_530,
    )
    assert observed.coverage_event is not None

    gap = build_gap_observed(
        provider="bybit",
        source="market_tape_stream",
        channel="publicTrade",
        symbol="BTCUSDT",
        expectation_value=300,
        last_successful_ingestion_ms=2_530,
        observed_at_ms=2_900,
        source_evidence_identities=(raw.event_identity,),
    )
    gaps = persist_open_gap_coverage(
        store=source_store,
        capabilities=capabilities,
        gaps=(gap,),
        observed_at_ms=2_900,
    )
    assert len(gaps) == 1
    assert gaps[0].state is SourceCoverageState.GAP
    assert gaps[0].gap_event_identity == gap.event_identity

    repeated = persist_open_gap_coverage(
        store=source_store,
        capabilities=capabilities,
        gaps=(gap,),
        observed_at_ms=3_000,
    )
    assert repeated == ()

    replay_wire = _trade_wire_event(ingested_at_ms=3_100)
    replay_raw = _append_raw(raw_store, replay_wire)
    recovered = persist_bybit_wire_source_contract(
        store=source_store,
        capabilities=capabilities,
        wire_event=replay_wire,
        raw_event=replay_raw,
        orderbook_normalized_persisted=False,
        coverage_observed_at_ms=3_110,
    )
    assert recovered.coverage_event is not None
    assert recovered.coverage_event.state is SourceCoverageState.OBSERVED
    assert recovered.coverage_event.previous_event_identity == gaps[0].coverage_event_identity


async def _integration_events() -> AsyncIterator[BybitMicrostructureWireEvent]:
    state = BybitSpotOrderBookState(
        symbol="BTCUSDT",
        depth=50,
        adapter_version=ADAPTER_VERSION,
    )
    for payload, ingested in (
        (
            _book_payload(
                kind="snapshot",
                ts=1_010,
                cts=1_009,
                update_id=10,
                sequence=20,
                bids=[["100", "2"]],
                asks=[["101", "2"]],
            ),
            1_020,
        ),
        (
            _book_payload(
                kind="delta",
                ts=1_210,
                cts=1_209,
                update_id=11,
                sequence=21,
                bids=[["100", "2.5"]],
                asks=[],
            ),
            1_220,
        ),
    ):
        yield _book_wire_event(
            state=state,
            payload=payload,
            ingested_at_ms=ingested,
        )
    yield _trade_wire_event(ingested_at_ms=2_520)


@pytest.mark.asyncio
async def test_wire_collection_callback_runs_after_raw_and_normalized_persistence(
    tmp_path,
) -> None:
    market_store = MarketTapeStore(tmp_path / "market.sqlite3")
    raw_store = RawMarketTapeStore(tmp_path / "raw.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    capabilities = register_bybit_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
        depth=50,
    )
    writes: list[int] = []

    def source_callback(
        event: BybitMicrostructureWireEvent,
        raw_event: RawMarketEvent,
        orderbook_normalized_persisted: bool,
    ) -> None:
        assert raw_store.count() > 0
        write = persist_bybit_wire_source_contract(
            store=source_store,
            capabilities=capabilities,
            wire_event=event,
            raw_event=raw_event,
            orderbook_normalized_persisted=orderbook_normalized_persisted,
            coverage_observed_at_ms=event.ingested_at_ms,
        )
        writes.append(write.envelope_count)

    result = await persist_bybit_wire_stream(
        store=market_store,
        raw_store=raw_store,
        events=_integration_events(),
        orderbook_snapshot_interval_ms=1_000,
        persisted_wire_callback=source_callback,
    )

    assert result.observed_messages == 3
    assert writes == [1, 1, 2]
    assert market_store.counts().orderbooks == 1
    assert market_store.counts().trades == 2
    assert raw_store.count() == 3
    assert source_store.quick_check() is True
    assert (
        source_store.coverage_at(
            provider="bybit",
            source="market_tape_stream",
            channel="publicTrade",
            symbol="BTCUSDT",
            as_of_ms=3_000,
        ).state
        is SourceCoverageState.OBSERVED
    )
