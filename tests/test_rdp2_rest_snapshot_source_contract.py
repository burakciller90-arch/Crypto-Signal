from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import httpx

from crypto_signal.data.adapters.bybit_derivatives import (
    BybitLinearDerivativesAdapter,
    BybitLinearDerivativesSourceSnapshot,
)
from crypto_signal.data.adapters.bybit_microstructure import (
    BybitSpotMicrostructureAdapter,
    BybitSpotMicrostructureSourceSnapshot,
)
from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_collection import (
    collect_bybit_market_tape_snapshot_with_source_contract,
)
from crypto_signal.data.market_tape_rest_source_contract import (
    REST_OPEN_INTEREST_CHANNEL,
    REST_RECENT_TRADE_CHANNEL,
    REST_TICKER_CHANNEL,
    persist_bybit_rest_market_tape_snapshot,
    register_bybit_rest_market_tape_capabilities,
)
from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.data.source_contract import (
    SourceContractStore,
    SourceCoverageState,
    build_source_raw_payload,
)


def _book_payload(*, response_time_ms: int = 1_020) -> dict[str, object]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "s": "BTCUSDT",
            "b": [["100", "2"]],
            "a": [["101", "3"]],
            "ts": 1_010,
            "u": 10,
            "seq": 20,
            "cts": 1_000,
        },
        "retExtInfo": {},
        "time": response_time_ms,
    }


def _trade_payload(
    *,
    response_time_ms: int = 1_020,
    empty: bool = False,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    if not empty:
        rows = [
            {
                "execId": "trade-1",
                "symbol": "BTCUSDT",
                "price": "100.5",
                "size": "0.4",
                "side": "Buy",
                "time": "1001",
                "isBlockTrade": False,
                "isRPITrade": False,
                "seq": "30",
            },
            {
                "execId": "trade-2",
                "symbol": "BTCUSDT",
                "price": "100.4",
                "size": "0.2",
                "side": "Sell",
                "time": "1002",
                "isBlockTrade": False,
                "isRPITrade": False,
                "seq": "31",
            },
        ]
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "spot",
            "list": rows,
        },
        "retExtInfo": {},
        "time": response_time_ms,
    }


def _oi_payload(
    *,
    response_time_ms: int = 2_050,
    empty: bool = False,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    if not empty:
        rows = [
            {"openInterest": "1000", "timestamp": "1800"},
            {"openInterest": "1100", "timestamp": "1900"},
        ]
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "symbol": "BTCUSDT",
            "list": rows,
        },
        "time": response_time_ms,
    }


def _ticker_payload(
    *,
    response_time_ms: int = 2_050,
) -> dict[str, object]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "markPrice": "101",
                    "indexPrice": "100",
                    "openInterest": "1150",
                    "fundingRate": "0.0008",
                    "fundingIntervalHour": "8",
                }
            ],
        },
        "time": response_time_ms,
    }


def _micro_source(
    *,
    observed_at_ms: int = 1_030,
    empty_trades: bool = False,
) -> BybitSpotMicrostructureSourceSnapshot:
    book = build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_at_ms=1_000,
        source_timestamp_ms=1_010,
        response_time_ms=1_020,
        ingested_at_ms=observed_at_ms,
        update_id=10,
        sequence=20,
        bids=(OrderBookLevel(Decimal(100), Decimal(2)),),
        asks=(OrderBookLevel(Decimal(101), Decimal(3)),),
        source=DataSource.REST,
        adapter_version="test-rest-micro/1",
    )
    trades = ()
    if not empty_trades:
        trades = (
            build_public_trade_observation(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol="BTCUSDT",
                exec_id="trade-1",
                sequence=30,
                aggressor_side=AggressorSide.BUY,
                price=Decimal("100.5"),
                size=Decimal("0.4"),
                event_at_ms=1_001,
                source_timestamp_ms=1_020,
                ingested_at_ms=observed_at_ms,
                is_block_trade=False,
                is_rpi_trade=False,
                source=DataSource.REST,
                adapter_version="test-rest-micro/1",
            ),
            build_public_trade_observation(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol="BTCUSDT",
                exec_id="trade-2",
                sequence=31,
                aggressor_side=AggressorSide.SELL,
                price=Decimal("100.4"),
                size=Decimal("0.2"),
                event_at_ms=1_002,
                source_timestamp_ms=1_020,
                ingested_at_ms=observed_at_ms,
                is_block_trade=False,
                is_rpi_trade=False,
                source=DataSource.REST,
                adapter_version="test-rest-micro/1",
            ),
        )
    return BybitSpotMicrostructureSourceSnapshot(
        orderbook_payload=_book_payload(),
        trade_payload=_trade_payload(empty=empty_trades),
        orderbook=book,
        trades=trades,
        observed_at_ms=observed_at_ms,
    )


def _derivatives_source(
    *,
    observed_at_ms: int = 2_060,
    empty_oi: bool = False,
) -> BybitLinearDerivativesSourceSnapshot:
    oi = ()
    if not empty_oi:
        oi = (
            build_derivatives_observation(
                exchange=Exchange.BYBIT,
                instrument_type=(
                    DerivativesInstrumentType.LINEAR_PERPETUAL
                ),
                symbol="BTCUSDT",
                event_at_ms=1_800,
                funding_rate=None,
                open_interest=Decimal(1000),
                mark_price=None,
                index_price=None,
                funding_interval_hours=None,
                source=DataSource.REST,
                source_timestamp_ms=2_050,
                ingested_at_ms=observed_at_ms,
                adapter_version="test-rest-derivatives/1",
            ),
            build_derivatives_observation(
                exchange=Exchange.BYBIT,
                instrument_type=(
                    DerivativesInstrumentType.LINEAR_PERPETUAL
                ),
                symbol="BTCUSDT",
                event_at_ms=1_900,
                funding_rate=None,
                open_interest=Decimal(1100),
                mark_price=None,
                index_price=None,
                funding_interval_hours=None,
                source=DataSource.REST,
                source_timestamp_ms=2_050,
                ingested_at_ms=observed_at_ms,
                adapter_version="test-rest-derivatives/1",
            ),
        )
    ticker = build_derivatives_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        event_at_ms=2_050,
        funding_rate=Decimal("0.0008"),
        open_interest=Decimal(1150),
        mark_price=Decimal(101),
        index_price=Decimal(100),
        funding_interval_hours=8,
        source=DataSource.REST,
        source_timestamp_ms=2_050,
        ingested_at_ms=observed_at_ms,
        adapter_version="test-rest-derivatives/1",
    )
    return BybitLinearDerivativesSourceSnapshot(
        open_interest_payload=_oi_payload(empty=empty_oi),
        ticker_payload=_ticker_payload(),
        open_interest_observations=oi,
        ticker_observation=ticker,
        observed_at_ms=observed_at_ms,
    )


def _stores(tmp_path):
    return (
        MarketTapeStore(tmp_path / "market.sqlite3"),
        SourceContractStore(tmp_path / "source.sqlite3"),
    )


def test_source_raw_payload_is_canonical_inspectable_and_idempotent(
    tmp_path,
) -> None:
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    raw = build_source_raw_payload(
        provider="bybit",
        source="market_tape_snapshot",
        channel=REST_TICKER_CHANNEL,
        symbol="BTCUSDT",
        payload=_ticker_payload(),
    )

    source_store.append_raw_payload(raw)
    source_store.append_raw_payload(raw)
    restored = source_store.raw_payload(raw.raw_identity)

    assert restored == raw
    assert restored is not None
    assert json.loads(restored.payload_json) == _ticker_payload()
    assert restored.production_authority is False
    assert restored.real_capital == 0
    assert source_store.quick_check() is True


def test_rest_snapshot_maps_four_raw_surfaces_to_persisted_truth(
    tmp_path,
) -> None:
    market_store, source_store = _stores(tmp_path)
    capabilities = register_bybit_rest_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
    )

    result = persist_bybit_rest_market_tape_snapshot(
        market_store=market_store,
        source_store=source_store,
        capabilities=capabilities,
        microstructure=_micro_source(),
        derivatives=_derivatives_source(),
        symbol="BTCUSDT",
    )

    assert result.inserted_total == 6
    assert result.trade_inserted == 2
    assert result.derivatives_inserted == 3
    assert len(result.source_writes) == 4
    assert result.source_envelope_count == 6
    assert result.source_coverage_count == 4

    book, trades, oi, ticker = result.source_writes
    assert len(book.envelopes) == 1
    assert len(trades.envelopes) == 2
    assert len(oi.envelopes) == 2
    assert len(ticker.envelopes) == 1

    assert all(
        source_store.raw_payload(item.raw_payload.raw_identity)
        == item.raw_payload
        for item in result.source_writes
    )
    assert {item.provider_event_id for item in oi.envelopes} == {None}
    assert {item.provider_sequence for item in oi.envelopes} == {None}
    assert ticker.envelopes[0].provider_event_id is None
    assert ticker.envelopes[0].provider_sequence is None
    assert all(
        item.coverage_event.state is SourceCoverageState.OBSERVED
        for item in result.source_writes
    )


def test_rest_replay_reuses_normalized_identities_actually_in_market_tape(
    tmp_path,
) -> None:
    market_store, source_store = _stores(tmp_path)
    capabilities = register_bybit_rest_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
    )
    first = persist_bybit_rest_market_tape_snapshot(
        market_store=market_store,
        source_store=source_store,
        capabilities=capabilities,
        microstructure=_micro_source(observed_at_ms=3_000),
        derivatives=_derivatives_source(observed_at_ms=3_100),
        symbol="BTCUSDT",
    )
    replay = persist_bybit_rest_market_tape_snapshot(
        market_store=market_store,
        source_store=source_store,
        capabilities=capabilities,
        microstructure=_micro_source(observed_at_ms=4_000),
        derivatives=_derivatives_source(observed_at_ms=4_100),
        symbol="BTCUSDT",
    )

    assert replay.inserted_total == 0
    assert replay.trade_unchanged == 2
    assert replay.derivatives_unchanged == 3
    assert market_store.counts().total == 6

    first_normalized = tuple(
        tuple(item.normalized_identity for item in write.envelopes)
        for write in first.source_writes
    )
    replay_normalized = tuple(
        tuple(item.normalized_identity for item in write.envelopes)
        for write in replay.source_writes
    )
    assert replay_normalized == first_normalized
    assert replay.source_writes[0].envelopes[0].envelope_identity != (
        first.source_writes[0].envelopes[0].envelope_identity
    )


def test_empty_successful_rest_rows_remain_explicit_raw_only_evidence(
    tmp_path,
) -> None:
    market_store, source_store = _stores(tmp_path)
    capabilities = register_bybit_rest_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
    )
    result = persist_bybit_rest_market_tape_snapshot(
        market_store=market_store,
        source_store=source_store,
        capabilities=capabilities,
        microstructure=_micro_source(empty_trades=True),
        derivatives=_derivatives_source(empty_oi=True),
        symbol="BTCUSDT",
    )

    recent = result.source_writes[1]
    open_interest = result.source_writes[2]
    assert recent.coverage_event.reason_codes == (
        "rest_raw_only_source_observed",
    )
    assert open_interest.coverage_event.reason_codes == (
        "rest_raw_only_source_observed",
    )
    assert recent.envelopes[0].normalized_identity is None
    assert recent.envelopes[0].provider_event_id is None
    assert open_interest.envelopes[0].normalized_identity is None
    assert source_store.raw_payload(
        recent.raw_payload.raw_identity
    ) is not None
    assert source_store.raw_payload(
        open_interest.raw_payload.raw_identity
    ) is not None


def test_rest_coverage_remains_monotonic_when_local_observation_clock_regresses(
    tmp_path,
) -> None:
    market_store, source_store = _stores(tmp_path)
    capabilities = register_bybit_rest_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
    )
    first = persist_bybit_rest_market_tape_snapshot(
        market_store=market_store,
        source_store=source_store,
        capabilities=capabilities,
        microstructure=_micro_source(observed_at_ms=5_000),
        derivatives=_derivatives_source(observed_at_ms=5_100),
        symbol="BTCUSDT",
    )
    second = persist_bybit_rest_market_tape_snapshot(
        market_store=market_store,
        source_store=source_store,
        capabilities=capabilities,
        microstructure=_micro_source(observed_at_ms=4_000),
        derivatives=_derivatives_source(observed_at_ms=4_100),
        symbol="BTCUSDT",
    )

    for earlier, later in zip(
        first.source_writes,
        second.source_writes,
        strict=True,
    ):
        assert later.coverage_event.observed_at_ms > (
            earlier.coverage_event.observed_at_ms
        )
        assert later.coverage_event.previous_event_identity == (
            earlier.coverage_event.coverage_event_identity
        )
        assert all(
            envelope.observed_at_ms < envelope.ingested_at_ms
            for envelope in later.envelopes
        )


class _FakeMicrostructureSourceAdapter:
    async def fetch_source_snapshot(
        self,
        *,
        symbol: str,
        book_depth: int = 25,
        trade_limit: int = 60,
    ) -> BybitSpotMicrostructureSourceSnapshot:
        assert symbol == "BTCUSDT"
        assert book_depth == 50
        assert trade_limit == 60
        return _micro_source()


class _FakeDerivativesSourceAdapter:
    async def fetch_source_snapshot(
        self,
        *,
        symbol: str,
        oi_interval: str = "15min",
        oi_limit: int = 8,
        end_ms: int | None = None,
    ) -> BybitLinearDerivativesSourceSnapshot:
        assert symbol == "BTCUSDT"
        assert oi_interval == "15min"
        assert oi_limit == 16
        assert end_ms is None
        return _derivatives_source()


def test_source_aware_snapshot_collection_preserves_existing_single_collector(
    tmp_path,
) -> None:
    market_store, source_store = _stores(tmp_path)
    capabilities = register_bybit_rest_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
    )
    result = asyncio.run(
        collect_bybit_market_tape_snapshot_with_source_contract(
            store=market_store,
            source_store=source_store,
            source_capabilities=capabilities,
            microstructure_adapter=_FakeMicrostructureSourceAdapter(),
            derivatives_adapter=_FakeDerivativesSourceAdapter(),
            symbol="BTCUSDT",
            book_depth=50,
            trade_limit=60,
            oi_interval="15min",
            oi_limit=16,
        )
    )

    assert result.inserted_total == 6
    assert result.source_coverage_count == 4
    assert market_store.quick_check() is True
    assert source_store.quick_check() is True


def test_actual_rest_adapters_expose_exact_raw_payloads() -> None:
    def micro_handler(request: httpx.Request) -> httpx.Response:
        payload = (
            _book_payload()
            if request.url.path.endswith("/orderbook")
            else _trade_payload()
        )
        return httpx.Response(200, json=payload)

    async def fetch_micro():
        transport = httpx.MockTransport(micro_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BybitSpotMicrostructureAdapter(
                client
            ).fetch_source_snapshot(
                symbol="BTCUSDT",
                book_depth=1,
                trade_limit=2,
            )

    micro = asyncio.run(fetch_micro())
    assert micro.orderbook_payload == _book_payload()
    assert micro.trade_payload == _trade_payload()
    assert len(micro.trades) == 2

    def derivatives_handler(request: httpx.Request) -> httpx.Response:
        payload = (
            _oi_payload()
            if request.url.path.endswith("/open-interest")
            else _ticker_payload()
        )
        return httpx.Response(200, json=payload)

    async def fetch_derivatives():
        transport = httpx.MockTransport(derivatives_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BybitLinearDerivativesAdapter(
                client
            ).fetch_source_snapshot(
                symbol="BTCUSDT",
                oi_interval="15min",
                oi_limit=2,
            )

    derivatives = asyncio.run(fetch_derivatives())
    assert derivatives.open_interest_payload == _oi_payload()
    assert derivatives.ticker_payload == _ticker_payload()
    assert len(derivatives.open_interest_observations) == 2


def test_snapshot_runner_wires_canonical_source_contract() -> None:
    runner = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "run_market_tape_snapshot.py"
    ).read_text(encoding="utf-8")

    assert "DEFAULT_SOURCE_CONTRACT_DB" in runner
    assert "--source-contract-db" in runner
    assert "collect_bybit_market_tape_snapshot_with_source_contract(" in runner
    assert "register_bybit_rest_market_tape_capabilities(" in runner
    assert "cycle_source_envelopes=" in runner
    assert "cycle_source_coverage=" in runner
    assert "SOURCE_CONTRACT_INTEGRITY_DELEGATED=YES" in runner
    assert "source_store.quick_check()" not in runner
    assert "FULL_DB_INTEGRITY_DELEGATED=YES" in runner
    assert "REAL_CAPITAL=0" in runner


def test_derivatives_channels_are_distinct_and_queryable(tmp_path) -> None:
    market_store, source_store = _stores(tmp_path)
    capabilities = register_bybit_rest_market_tape_capabilities(
        store=source_store,
        symbols=("BTCUSDT",),
    )
    persist_bybit_rest_market_tape_snapshot(
        market_store=market_store,
        source_store=source_store,
        capabilities=capabilities,
        microstructure=_micro_source(),
        derivatives=_derivatives_source(),
        symbol="BTCUSDT",
    )

    oi = source_store.latest_coverage(
        provider="bybit",
        source="market_tape_snapshot",
        channel=REST_OPEN_INTEREST_CHANNEL,
        symbol="BTCUSDT",
    )
    ticker = source_store.latest_coverage(
        provider="bybit",
        source="market_tape_snapshot",
        channel=REST_TICKER_CHANNEL,
        symbol="BTCUSDT",
    )
    trades = source_store.latest_coverage(
        provider="bybit",
        source="market_tape_snapshot",
        channel=REST_RECENT_TRADE_CHANNEL,
        symbol="BTCUSDT",
    )

    assert oi is not None
    assert ticker is not None
    assert trades is not None
    assert oi.coverage_event_identity != ticker.coverage_event_identity
    assert oi.coverage_event_identity != trades.coverage_event_identity
