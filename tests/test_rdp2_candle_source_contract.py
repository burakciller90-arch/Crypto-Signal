from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import cast

import httpx

from crypto_signal.data.adapters.base import (
    CandleSourceSnapshot,
    MarketDataAdapter,
)
from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.candle_source_contract import (
    persist_candle_source_snapshot,
)
from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.data.recovery import backfill_range
from crypto_signal.data.source_contract import (
    SourceContractStore,
    SourceCoverageState,
)
from crypto_signal.data.store import CandleStore, WriteDisposition
from crypto_signal.ledger.live_clock import (
    LiveFreezeStatus,
    freeze_live_provider,
)


def _candle(
    *,
    exchange: Exchange = Exchange.BYBIT,
    open_time_ms: int = 0,
    close: str = "101",
    source_timestamp_ms: int = 1_000_000,
    ingested_at_ms: int = 1_000_001,
    is_closed: bool = True,
) -> Candle:
    return Candle(
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=Decimal(100),
        high=Decimal(110),
        low=Decimal(99),
        close=Decimal(close),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trade_count=100 if exchange is Exchange.BINANCE else None,
        is_closed=is_closed,
        source=DataSource.REST,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version="test-candle-source/1",
    )


def _snapshot(
    *,
    candle: Candle | None = None,
    observed_at_ms: int = 1_000_001,
    source_timestamp_ms: int = 1_000_000,
    provider: str = "bybit",
    source: str = "spot_kline_rest",
) -> CandleSourceSnapshot:
    candles = () if candle is None else (candle,)
    return CandleSourceSnapshot(
        provider=provider,
        source=source,
        channel="rest.kline.15m",
        symbol="BTCUSDT",
        timeframe="15m",
        raw_payload={
            "response": {
                "provider": provider,
                "rows": [str(candle.close)] if candle is not None else [],
                "time": source_timestamp_ms,
            }
        },
        candles=candles,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
    )


def test_persisted_candle_identity_tracks_actual_store_truth(tmp_path) -> None:
    candle_store = CandleStore(tmp_path / "candles.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")

    newer = _candle(
        close="103",
        source_timestamp_ms=3_000,
        ingested_at_ms=3_001,
        is_closed=False,
    )
    first = persist_candle_source_snapshot(
        candle_store=candle_store,
        source_store=source_store,
        snapshot=_snapshot(
            candle=newer,
            observed_at_ms=3_001,
            source_timestamp_ms=3_000,
        ),
    )
    persisted_identity = first.envelopes[0].normalized_identity
    assert persisted_identity is not None
    assert first.count(WriteDisposition.INSERTED) == 1

    stale = _candle(
        close="99",
        source_timestamp_ms=2_000,
        ingested_at_ms=4_001,
        is_closed=False,
    )
    replay = persist_candle_source_snapshot(
        candle_store=candle_store,
        source_store=source_store,
        snapshot=_snapshot(
            candle=stale,
            observed_at_ms=4_001,
            source_timestamp_ms=2_000,
        ),
    )

    assert replay.count(WriteDisposition.IGNORED_STALE) == 1
    assert replay.envelopes[0].normalized_identity == persisted_identity
    loaded = candle_store.list_candles(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
    )
    assert loaded[0].close == Decimal(103)
    assert replay.coverage_event.previous_event_identity == (
        first.coverage_event.coverage_event_identity
    )


def test_empty_candle_response_is_explicit_raw_only_coverage(tmp_path) -> None:
    candle_store = CandleStore(tmp_path / "candles.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    result = persist_candle_source_snapshot(
        candle_store=candle_store,
        source_store=source_store,
        snapshot=_snapshot(
            candle=None,
            observed_at_ms=5_100,
            source_timestamp_ms=5_000,
        ),
    )

    assert result.envelopes[0].normalized_identity is None
    assert result.envelopes[0].source_timestamp_ms == 5_000
    assert result.coverage_event.state is SourceCoverageState.OBSERVED
    assert result.coverage_event.reason_codes == (
        "candle_raw_only_source_observed",
    )
    restored = source_store.raw_payload(result.raw_payload.raw_identity)
    assert restored is not None
    assert json.loads(restored.payload_json)["response"]["rows"] == []


def test_bybit_source_snapshot_retains_exact_provider_response() -> None:
    payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "spot",
            "symbol": "BTCUSDT",
            "list": [
                [
                    "1710000000000",
                    "100",
                    "102",
                    "99",
                    "101",
                    "3",
                    "303",
                ]
            ],
        },
        "time": 1710001000000,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/market/kline"
        return httpx.Response(200, json=payload)

    async def run() -> CandleSourceSnapshot:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BybitSpotAdapter(
                client,
                base_url="https://api.bybit.tr",
            ).fetch_source_candles(
                symbol="BTCUSDT",
                timeframe="15m",
                limit=1,
            )

    snapshot = asyncio.run(run())
    assert snapshot.raw_payload == {"response": payload}
    assert snapshot.source_timestamp_ms == 1710001000000
    assert snapshot.provider == "bybit"
    assert snapshot.source == "spot_kline_rest"
    assert len(snapshot.candles) == 1


def test_binance_global_source_snapshot_keeps_kline_and_time_responses() -> None:
    rows = [
        [
            1710000000000,
            "100",
            "102",
            "99",
            "101",
            "3",
            1710000899999,
            "303",
            42,
            "0",
            "0",
            "0",
        ]
    ]
    time_payload = {"serverTime": 1710001000000}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/time"):
            return httpx.Response(200, json=time_payload)
        return httpx.Response(200, json=rows)

    async def run() -> CandleSourceSnapshot:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BinanceSpotAdapter(client).fetch_source_candles(
                symbol="BTCUSDT",
                timeframe="15m",
                limit=1,
            )

    snapshot = asyncio.run(run())
    assert snapshot.raw_payload == {
        "klines_response": rows,
        "time_response": time_payload,
    }
    assert snapshot.source == "spot_kline_rest_global"
    assert snapshot.source_timestamp_ms == 1710001000000


def test_binance_tr_direct_array_preserves_http_date_source_proof() -> None:
    rows = [
        [
            1710000000000,
            "100",
            "102",
            "99",
            "101",
            "3",
            1710000899999,
            "303",
            42,
            "0",
            "0",
            "0",
        ]
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=rows,
            headers={"Date": "Sat, 09 Mar 2024 16:16:40 GMT"},
        )

    async def run() -> CandleSourceSnapshot:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BinanceSpotAdapter(
                client,
                base_url="https://api.binance.me",
                api_variant="tr_main",
            ).fetch_source_candles(
                symbol="BTCUSDT",
                timeframe="15m",
                limit=1,
            )

    snapshot = asyncio.run(run())
    assert snapshot.raw_payload["response"] == rows
    assert snapshot.raw_payload["http_date"] == (
        "Sat, 09 Mar 2024 16:16:40 GMT"
    )
    assert snapshot.source == "spot_kline_rest_tr_main"
    assert snapshot.source_timestamp_ms == 1710001000000


class _SourceBackfillAdapter:
    async def fetch_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> tuple[Candle, ...]:
        raise AssertionError("legacy fetch path must not be used")

    async def fetch_source_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> CandleSourceSnapshot:
        assert symbol == "BTCUSDT"
        assert timeframe == "15m"
        assert start_ms is not None
        candles = tuple(
            _candle(
                open_time_ms=start_ms + index * 900_000,
                source_timestamp_ms=3_000_000,
                ingested_at_ms=3_000_001,
                is_closed=True,
            )
            for index in range(limit)
        )
        return CandleSourceSnapshot(
            provider="bybit",
            source="spot_kline_rest",
            channel="rest.kline.15m",
            symbol=symbol,
            timeframe=timeframe,
            raw_payload={
                "response": {
                    "start": start_ms,
                    "end": end_ms,
                    "count": len(candles),
                }
            },
            candles=candles,
            source_timestamp_ms=3_000_000,
            observed_at_ms=3_000_001,
        )


def test_source_aware_backfill_persists_lineage_per_page(tmp_path) -> None:
    candle_store = CandleStore(tmp_path / "candles.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    adapter = cast(MarketDataAdapter, _SourceBackfillAdapter())

    report = asyncio.run(
        backfill_range(
            adapter,
            candle_store,
            symbol="BTCUSDT",
            timeframe="15m",
            start_open_ms=0,
            end_open_ms=1_800_000,
            page_limit=2,
            source_store=source_store,
        )
    )

    assert report.complete is True
    assert report.count(WriteDisposition.INSERTED) == 3
    coverage = source_store.latest_coverage(
        provider="bybit",
        source="spot_kline_rest",
        channel="rest.kline.15m",
        symbol="BTCUSDT",
    )
    assert coverage is not None
    assert coverage.state is SourceCoverageState.OBSERVED
    latest = source_store.latest_envelope_at(
        provider="bybit",
        source="spot_kline_rest",
        channel="rest.kline.15m",
        symbol="BTCUSDT",
        as_of_ms=coverage.observed_at_ms,
    )
    assert latest is not None
    assert latest.normalized_identity is not None


class _AlreadyFrozenLedger:
    def has_source_cutoff(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        source_cutoff_open_time_ms: int,
    ) -> bool:
        return True


class _DirectSourceAdapter:
    async def fetch_candles(
        self,
        **_: object,
    ) -> tuple[Candle, ...]:
        raise AssertionError("legacy fetch path must not be used")

    async def fetch_source_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> CandleSourceSnapshot:
        assert symbol == "BTCUSDT"
        assert timeframe == "15m"
        assert limit == 1
        assert start_ms is None
        assert end_ms is None
        candle = _candle(
            source_timestamp_ms=1_000_000,
            ingested_at_ms=1_000_001,
            is_closed=True,
        )
        return _snapshot(
            candle=candle,
            source_timestamp_ms=1_000_000,
            observed_at_ms=1_000_001,
        )


def test_direct_live_freeze_persists_source_before_replay_result(tmp_path) -> None:
    candle_store = CandleStore(tmp_path / "candles.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    result = asyncio.run(
        freeze_live_provider(
            adapter=cast(MarketDataAdapter, _DirectSourceAdapter()),
            ledger=cast(object, _AlreadyFrozenLedger()),
            candle_store=candle_store,
            source_store=source_store,
            symbol="BTCUSDT",
            timeframe="15m",
            limit=1,
            minimum_closed_candles=1,
            now_ms=lambda: 1_000_001,
        )
    )

    assert result.status is LiveFreezeStatus.ALREADY_FROZEN
    coverage = source_store.latest_coverage(
        provider="bybit",
        source="spot_kline_rest",
        channel="rest.kline.15m",
        symbol="BTCUSDT",
    )
    assert coverage is not None


def test_live_clock_wires_default_candle_source_contract() -> None:
    runner = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "run_live_evidence_clock.py"
    ).read_text(encoding="utf-8")
    live_coverage = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "crypto_signal"
        / "ledger"
        / "live_coverage.py"
    ).read_text(encoding="utf-8")
    higher = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "crypto_signal"
        / "ledger"
        / "higher_timeframe.py"
    ).read_text(encoding="utf-8")

    assert "DEFAULT_SOURCE_CONTRACT" in runner
    assert '"--source-contract"' in runner
    assert "source_contract_path=args.source_contract" in runner
    assert "source_store=source_store" in live_coverage
    assert "source_store=source_store" in higher
    assert "REAL_CAPITAL=0" in runner
