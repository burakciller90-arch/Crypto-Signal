from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

import crypto_signal.data.adapters.defillama_stablecoins as defillama_module
from crypto_signal.data.adapters.defillama_stablecoins import (
    DefiLlamaStablecoinsAdapter,
)
from crypto_signal.data.onchain_capital_flow import (
    StablecoinSourceTimestampSemantic,
)
from crypto_signal.data.onchain_capital_flow_store import (
    OnchainCapitalFlowStore,
)
from crypto_signal.data.source_contract import (
    SourceContractStore,
    SourceCoverageState,
)
from crypto_signal.data.stablecoin_source_contract import (
    DEFILLAMA_STABLECOIN_CHANNEL,
    DEFILLAMA_STABLECOIN_FRESHNESS_BUDGET_MS,
    DEFILLAMA_STABLECOIN_PROVIDER,
    DEFILLAMA_STABLECOIN_SOURCE,
    build_defillama_stablecoin_capability,
    persist_defillama_stablecoin_snapshot,
)

OBSERVED_MS = 1_790_000_000_000


def _asset(
    *,
    asset_id: int,
    symbol: str,
    circulating: str,
    price: str,
) -> dict[str, object]:
    return {
        "id": asset_id,
        "name": symbol,
        "symbol": symbol,
        "gecko_id": symbol.lower(),
        "pegType": "peggedUSD",
        "pegMechanism": "fiat-backed",
        "priceSource": "defillama",
        "price": price,
        "circulating": {"peggedUSD": circulating},
        "circulatingPrevDay": {"peggedUSD": circulating},
        "circulatingPrevWeek": {"peggedUSD": circulating},
        "circulatingPrevMonth": {"peggedUSD": circulating},
        "chains": ["Ethereum"],
        "chainCirculating": {
            "Ethereum": {
                "current": {"peggedUSD": circulating},
            }
        },
    }


def _payload() -> dict[str, object]:
    return {
        "peggedAssets": [
            _asset(
                asset_id=1,
                symbol="USDT",
                circulating="180000000000.50",
                price="1.0001",
            ),
            _asset(
                asset_id=2,
                symbol="USDC",
                circulating="75000000000.25",
                price="0.9999",
            ),
            {
                "id": 3,
                "symbol": "DAI",
                "circulating": {"peggedUSD": "5000000000"},
                "chainCirculating": {"Ethereum": {}},
            },
        ],
        "chains": ["Ethereum"],
    }


def _fetch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: dict[str, object] | None = None,
):
    selected_payload = _payload() if payload is None else payload
    monkeypatch.setattr(
        defillama_module.time,
        "time_ns",
        lambda: OBSERVED_MS * 1_000_000,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/stablecoins"
        assert request.url.params["includePrices"] == "true"
        assert "Authorization" not in request.headers
        assert request.headers["User-Agent"].startswith("Crypto-Signal/")
        return httpx.Response(200, json=selected_payload)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await DefiLlamaStablecoinsAdapter(
                client=client,
            ).fetch_snapshot()

    return asyncio.run(run())


def test_defillama_adapter_normalizes_public_usdt_usdc_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _fetch(monkeypatch)

    assert snapshot.observed_at_ms == OBSERVED_MS
    assert tuple(item.symbol for item in snapshot.assets) == ("USDC", "USDT")
    usdt = next(item for item in snapshot.assets if item.symbol == "USDT")
    usdc = next(item for item in snapshot.assets if item.symbol == "USDC")
    assert str(usdt.circulating_pegged_usd) == "180000000000.50"
    assert str(usdc.circulating_pegged_usd) == "75000000000.25"
    assert usdt.chain_count == 1
    assert usdt.raw_payload["id"] == 1



def test_defillama_adapter_preserves_json_float_tokens_as_canonical_strings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    assets = payload["peggedAssets"]
    assert isinstance(assets, list)
    usdt = next(
        item
        for item in assets
        if isinstance(item, dict) and item.get("symbol") == "USDT"
    )
    usdt["price"] = 1.0001
    usdt["circulating"] = {"peggedUSD": 180000000000.5}
    usdt["circulatingPrevDay"] = {"peggedUSD": 180000000000.5}
    usdt["chainCirculating"] = {
        "Ethereum": {
            "current": {"peggedUSD": 180000000000.5},
        }
    }

    snapshot = _fetch(monkeypatch, payload=payload)
    normalized = next(
        item for item in snapshot.assets if item.symbol == "USDT"
    )
    assert normalized.raw_payload["price"] == "1.0001"
    circulating = normalized.raw_payload["circulating"]
    assert isinstance(circulating, dict)
    assert circulating["peggedUSD"] == "180000000000.5"

    onchain_store = OnchainCapitalFlowStore(tmp_path / "onchain.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")
    persisted = persist_defillama_stablecoin_snapshot(
        snapshot=snapshot,
        onchain_store=onchain_store,
        source_store=source_store,
    )
    usdt_result = next(item for item in persisted if item.symbol == "USDT")
    raw = source_store.raw_payload(usdt_result.raw_identity)
    assert raw is not None
    decoded = json.loads(raw.payload_json)
    assert decoded["price"] == "1.0001"
    assert decoded["circulating"]["peggedUSD"] == "180000000000.5"
    assert onchain_store.quick_check()
    assert source_store.quick_check()

def test_defillama_adapter_rejects_missing_tracked_asset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    assets = payload["peggedAssets"]
    assert isinstance(assets, list)
    payload["peggedAssets"] = [
        item
        for item in assets
        if not isinstance(item, dict) or item.get("symbol") != "USDC"
    ]

    with pytest.raises(ValueError, match="requires USDT and USDC"):
        _fetch(monkeypatch, payload=payload)


def test_defillama_adapter_rejects_missing_pegged_usd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    assets = payload["peggedAssets"]
    assert isinstance(assets, list)
    usdt = next(
        item
        for item in assets
        if isinstance(item, dict) and item.get("symbol") == "USDT"
    )
    usdt["circulating"] = {}

    with pytest.raises(ValueError, match="requires peggedUSD"):
        _fetch(monkeypatch, payload=payload)


def test_defillama_source_persistence_is_exact_pit_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _fetch(monkeypatch)
    onchain_store = OnchainCapitalFlowStore(tmp_path / "onchain.sqlite3")
    source_store = SourceContractStore(tmp_path / "source.sqlite3")

    first = persist_defillama_stablecoin_snapshot(
        snapshot=snapshot,
        onchain_store=onchain_store,
        source_store=source_store,
    )
    second = persist_defillama_stablecoin_snapshot(
        snapshot=snapshot,
        onchain_store=onchain_store,
        source_store=source_store,
    )

    assert first == second
    assert tuple(item.symbol for item in first) == ("USDC", "USDT")
    assert onchain_store.quick_check()
    assert source_store.quick_check()
    assert onchain_store.counts().stablecoin_supply_observations == 2

    for result in first:
        observation = onchain_store.latest_stablecoin_supply_as_of(
            asset=result.symbol,
            network_scope="all_chains",
            provider=DEFILLAMA_STABLECOIN_PROVIDER,
            as_of_ms=OBSERVED_MS,
        )
        assert observation is not None
        assert observation.observation_identity == result.observation_identity
        assert (
            observation.source_timestamp_semantic
            is StablecoinSourceTimestampSemantic.COLLECTOR_RECEIPT
        )
        assert observation.source_timestamp_ms == OBSERVED_MS
        assert observation.observed_at_ms == OBSERVED_MS
        assert observation.ingested_at_ms == OBSERVED_MS

        envelope = source_store.latest_envelope_at(
            provider=DEFILLAMA_STABLECOIN_PROVIDER,
            source=DEFILLAMA_STABLECOIN_SOURCE,
            channel=DEFILLAMA_STABLECOIN_CHANNEL,
            symbol=result.symbol,
            as_of_ms=OBSERVED_MS,
        )
        assert envelope is not None
        assert envelope.normalized_identity == observation.observation_identity
        assert envelope.raw_identity == observation.raw_identity
        assert envelope.envelope_identity == result.envelope_identity

        raw = source_store.raw_payload(result.raw_identity)
        assert raw is not None
        decoded = json.loads(raw.payload_json)
        assert decoded["symbol"] == result.symbol
        assert decoded["circulating"]["peggedUSD"] is not None

        coverage = source_store.latest_coverage(
            provider=DEFILLAMA_STABLECOIN_PROVIDER,
            source=DEFILLAMA_STABLECOIN_SOURCE,
            channel=DEFILLAMA_STABLECOIN_CHANNEL,
            symbol=result.symbol,
        )
        assert coverage is not None
        assert coverage.state is SourceCoverageState.OBSERVED
        assert coverage.source_envelope_identity == envelope.envelope_identity


def test_defillama_capability_is_public_read_only_collector_freshness() -> None:
    capability = build_defillama_stablecoin_capability()

    assert capability.symbols == ("USDC", "USDT")
    assert (
        capability.freshness_budget_ms
        == DEFILLAMA_STABLECOIN_FRESHNESS_BUDGET_MS
        == 1_800_000
    )
    assert capability.supports_provider_event_id is False
    assert capability.production_authority is False
    assert capability.real_capital == 0
