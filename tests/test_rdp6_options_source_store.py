from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

import crypto_signal.data.adapters.bybit_options as bybit_options_module
from crypto_signal.data.adapters.bybit_options import BybitOptionsAdapter
from crypto_signal.data.models import Exchange
from crypto_signal.data.options import build_option_instrument_metadata_identity
from crypto_signal.data.options_source_contract import (
    BYBIT_OPTIONS_CHANNEL,
    BYBIT_OPTIONS_PROVIDER,
    BYBIT_OPTIONS_SOURCE,
    build_bybit_options_capability,
    persist_bybit_option_surface_snapshot,
)
from crypto_signal.data.options_surface_store import OptionsSurfaceStore
from crypto_signal.data.source_contract import (
    SourceContractStore,
    SourceCoverageState,
)

FIXTURES = Path(__file__).parent / "fixtures" / "rdp6"
OBSERVED_MS = 1_760_000_000_500


def _fixture(name: str) -> dict[str, object]:
    value = json.loads((FIXTURES / name).read_text())
    assert isinstance(value, dict)
    return value


def _handler(
    mutate: Callable[[str, dict[str, object]], None] | None = None,
) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        base_coin = request.url.params.get("baseCoin")
        if base_coin not in {"BTC", "ETH"}:
            return httpx.Response(400, json={"retCode": 10001, "retMsg": "base"})
        suffix = base_coin.lower()
        if request.url.path.endswith("/v5/market/instruments-info"):
            payload = _fixture(f"bybit_option_instruments_{suffix}.json")
            surface = "instruments"
        elif request.url.path.endswith("/v5/market/tickers"):
            payload = _fixture(f"bybit_option_tickers_{suffix}.json")
            surface = "tickers"
        else:
            return httpx.Response(404)
        if mutate is not None:
            mutate(surface, payload)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handle)


def _fetch_snapshot(
    *,
    base_coin: str,
    mutate: Callable[[str, dict[str, object]], None] | None = None,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        bybit_options_module.time,
        "time_ns",
        lambda: OBSERVED_MS * 1_000_000,
    )

    async def run():
        async with httpx.AsyncClient(transport=_handler(mutate)) as client:
            adapter = BybitOptionsAdapter(client=client)
            return await adapter.fetch_source_snapshot(base_coin=base_coin)

    return asyncio.run(run())


@pytest.mark.parametrize("base_coin", ("BTC", "ETH"))
def test_bybit_option_fixtures_normalize_to_exact_surface(
    base_coin: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _fetch_snapshot(
        base_coin=base_coin,
        monkeypatch=monkeypatch,
    )

    assert snapshot.base_coin == base_coin
    assert len(snapshot.instrument_specs) == 2
    assert len(snapshot.surface.contracts) == 2
    assert snapshot.surface.base_coin == base_coin
    assert snapshot.surface.observed_at_ms == OBSERVED_MS
    assert snapshot.surface.ingested_at_ms == OBSERVED_MS
    assert snapshot.surface.instrument_metadata_identity == (
        build_option_instrument_metadata_identity(
            exchange=Exchange.BYBIT,
            base_coin=base_coin,
            instrument_specs=snapshot.instrument_specs,
        )
    )
    assert all(
        quote.instrument_identity
        in {item.instrument_identity for item in snapshot.instrument_specs}
        for quote in snapshot.surface.contracts
    )

    if base_coin == "ETH":
        put = next(
            item
            for item in snapshot.surface.contracts
            if item.option_type.value == "put"
        )
        assert put.bid_iv is None
        assert put.ask_iv is not None


def test_option_surface_persistence_is_pit_safe_and_source_linked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _fetch_snapshot(base_coin="BTC", monkeypatch=monkeypatch)
    options_store = OptionsSurfaceStore(tmp_path / "options.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")

    first = persist_bybit_option_surface_snapshot(
        snapshot=snapshot,
        options_store=options_store,
        source_store=source_store,
    )
    second = persist_bybit_option_surface_snapshot(
        snapshot=snapshot,
        options_store=options_store,
        source_store=source_store,
    )

    assert first == second
    assert options_store.quick_check()
    assert source_store.quick_check()
    assert (
        options_store.latest_surface_as_of(
            exchange=Exchange.BYBIT,
            base_coin="BTC",
            as_of_ms=snapshot.surface.ingested_at_ms - 1,
        )
        is None
    )
    replay = options_store.latest_surface_as_of(
        exchange=Exchange.BYBIT,
        base_coin="BTC",
        as_of_ms=snapshot.surface.ingested_at_ms,
    )
    assert replay == snapshot.surface

    resolved_specs = options_store.instrument_specs_for_metadata(
        snapshot.surface.instrument_metadata_identity
    )
    assert {item.instrument_identity for item in resolved_specs} == {
        item.instrument_identity for item in snapshot.instrument_specs
    }

    envelope = source_store.latest_envelope_at(
        provider=BYBIT_OPTIONS_PROVIDER,
        source=BYBIT_OPTIONS_SOURCE,
        channel=BYBIT_OPTIONS_CHANNEL,
        symbol="BTC",
        as_of_ms=snapshot.surface.ingested_at_ms,
    )
    assert envelope is not None
    assert envelope.normalized_identity == snapshot.surface.surface_identity
    assert envelope.raw_identity == first.raw_identity

    raw = source_store.raw_payload(first.raw_identity)
    assert raw is not None
    raw_payload = json.loads(raw.payload_json)
    assert raw_payload["ticker_payload"] == snapshot.ticker_payload
    assert raw_payload["instrument_payloads"] == list(
        snapshot.instrument_payloads
    )

    coverage = source_store.latest_coverage(
        provider=BYBIT_OPTIONS_PROVIDER,
        source=BYBIT_OPTIONS_SOURCE,
        channel=BYBIT_OPTIONS_CHANNEL,
        symbol="BTC",
    )
    assert coverage is not None
    assert coverage.state is SourceCoverageState.OBSERVED
    assert coverage.source_envelope_identity == envelope.envelope_identity
    assert coverage.coverage_event_identity == first.coverage_event_identity


def test_source_capability_is_base_asset_stable_and_read_only() -> None:
    capability = build_bybit_options_capability()

    assert capability.symbols == ("BTC", "ETH")
    assert capability.freshness_budget_ms == 120_000
    assert capability.supports_provider_event_id is False
    assert capability.production_authority is False
    assert capability.real_capital == 0


def test_empty_ticker_surface_is_not_converted_into_zero_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(surface: str, payload: dict[str, object]) -> None:
        if surface != "tickers":
            return
        result = payload["result"]
        assert isinstance(result, dict)
        result["list"] = []

    with pytest.raises(ValueError, match="ticker surface is empty"):
        _fetch_snapshot(
            base_coin="BTC",
            mutate=mutate,
            monkeypatch=monkeypatch,
        )


def test_ticker_requires_exact_instrument_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(surface: str, payload: dict[str, object]) -> None:
        if surface != "tickers":
            return
        result = payload["result"]
        assert isinstance(result, dict)
        rows = result["list"]
        assert isinstance(rows, list)
        row = rows[0]
        assert isinstance(row, dict)
        row["symbol"] = "BTC-27MAR26-71000-C-USDT"

    with pytest.raises(ValueError, match="missing exact instrument metadata"):
        _fetch_snapshot(
            base_coin="BTC",
            mutate=mutate,
            monkeypatch=monkeypatch,
        )


def test_symbol_option_type_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(surface: str, payload: dict[str, object]) -> None:
        if surface != "instruments":
            return
        result = payload["result"]
        assert isinstance(result, dict)
        rows = result["list"]
        assert isinstance(rows, list)
        row = rows[0]
        assert isinstance(row, dict)
        row["optionsType"] = "Put"

    with pytest.raises(ValueError, match="symbol/type mismatch"):
        _fetch_snapshot(
            base_coin="BTC",
            mutate=mutate,
            monkeypatch=monkeypatch,
        )


def test_adapter_rejects_non_btc_eth_without_network() -> None:
    async def run() -> None:
        adapter = BybitOptionsAdapter()
        with pytest.raises(ValueError, match="BTC or ETH"):
            await adapter.fetch_source_snapshot(base_coin="SOL")

    asyncio.run(run())
