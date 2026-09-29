from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx
import pytest

from crypto_signal.data.adapters.bybit_funding_history import (
    BybitFundingHistoryAdapter,
)
from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.funding_settlements import (
    build_funding_settlement_observation,
)
from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.paper.funding_cost_v2 import (
    PaperFundingCostStatus,
    PaperFundingSide,
    project_paper_funding_cost,
)
from crypto_signal.paper.models import PaperSymbol


def _settlement(
    *,
    funding_rate: str = "0.0001",
    settlement_at_ms: int = 1_000,
    source_timestamp_ms: int = 1_100,
    ingested_at_ms: int = 1_200,
):
    return build_funding_settlement_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        settlement_at_ms=settlement_at_ms,
        funding_rate=Decimal(funding_rate),
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        source=DataSource.REST,
        adapter_version="fp4c-test/1",
    )


def test_settlement_identity_is_deterministic() -> None:
    first = _settlement()
    replay = _settlement()

    assert first == replay
    assert first.settlement_identity == replay.settlement_identity


def test_bybit_funding_history_normalizes_exact_settlements() -> None:
    payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "-0.0002",
                    "fundingRateTimestamp": "1710028800000",
                },
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.0001",
                    "fundingRateTimestamp": "1710000000000",
                },
            ],
        },
        "time": 1710030000000,
    }

    observations = BybitFundingHistoryAdapter().normalize_payload(
        payload=payload,
        symbol="BTCUSDT",
        ingested_at_ms=1710030000100,
    )

    assert [item.settlement_at_ms for item in observations] == [
        1710000000000,
        1710028800000,
    ]
    assert [item.funding_rate for item in observations] == [
        Decimal("0.0001"),
        Decimal("-0.0002"),
    ]
    assert all(item.exchange is Exchange.BYBIT for item in observations)
    assert all(
        item.instrument_type is DerivativesInstrumentType.LINEAR_PERPETUAL
        for item in observations
    )


def test_bybit_funding_history_fetches_public_exact_endpoint() -> None:
    payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.0001",
                    "fundingRateTimestamp": "1710000000000",
                }
            ],
        },
        "time": 1710000000100,
    }
    seen: list[tuple[str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.url.path,
                request.url.params.get("startTime"),
                request.url.params.get("endTime"),
            )
        )
        assert request.url.params["category"] == "linear"
        assert request.url.params["symbol"] == "BTCUSDT"
        assert request.url.params["limit"] == "10"
        assert "X-BAPI-API-KEY" not in request.headers
        return httpx.Response(200, json=payload)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BybitFundingHistoryAdapter(
                client,
                base_url="https://api.bybit.tr/",
            ).fetch_settlements(
                symbol="BTCUSDT",
                start_ms=1709990000000,
                end_ms=1710010000000,
                limit=10,
            )

    observations = asyncio.run(run())

    assert len(observations) == 1
    assert seen == [
        (
            "/v5/market/funding/history",
            "1709990000000",
            "1710010000000",
        )
    ]


def test_bybit_funding_history_rejects_start_without_end() -> None:
    adapter = BybitFundingHistoryAdapter()
    with pytest.raises(ValueError, match="start_ms alone"):
        asyncio.run(
            adapter.fetch_settlements(
                symbol="BTCUSDT",
                start_ms=1,
            )
        )


def test_positive_funding_long_pays_and_short_receives() -> None:
    settlement = _settlement(funding_rate="0.001")
    mark_identity = "a" * 64

    long = project_paper_funding_cost(
        side=PaperFundingSide.LONG,
        symbol=PaperSymbol.BTCUSDT,
        position_quantity=Decimal(2),
        settlement=settlement,
        mark_price=Decimal(100),
        mark_evidence_identity=mark_identity,
        mark_at_ms=settlement.settlement_at_ms,
        evaluation_cutoff_ms=settlement.ingested_at_ms,
    )
    short = project_paper_funding_cost(
        side=PaperFundingSide.SHORT,
        symbol=PaperSymbol.BTCUSDT,
        position_quantity=Decimal(2),
        settlement=settlement,
        mark_price=Decimal(100),
        mark_evidence_identity=mark_identity,
        mark_at_ms=settlement.settlement_at_ms,
        evaluation_cutoff_ms=settlement.ingested_at_ms,
    )

    assert long.status is PaperFundingCostStatus.PROVEN
    assert short.status is PaperFundingCostStatus.PROVEN
    assert long.cash_flow_usdt == Decimal("-0.2")
    assert short.cash_flow_usdt == Decimal("0.2")


def test_negative_funding_reverses_cash_flow_signs() -> None:
    settlement = _settlement(funding_rate="-0.001")
    mark_identity = "b" * 64

    long = project_paper_funding_cost(
        side=PaperFundingSide.LONG,
        symbol=PaperSymbol.BTCUSDT,
        position_quantity=Decimal(1),
        settlement=settlement,
        mark_price=Decimal(100),
        mark_evidence_identity=mark_identity,
        mark_at_ms=settlement.settlement_at_ms,
        evaluation_cutoff_ms=settlement.ingested_at_ms,
    )
    short = project_paper_funding_cost(
        side=PaperFundingSide.SHORT,
        symbol=PaperSymbol.BTCUSDT,
        position_quantity=Decimal(1),
        settlement=settlement,
        mark_price=Decimal(100),
        mark_evidence_identity=mark_identity,
        mark_at_ms=settlement.settlement_at_ms,
        evaluation_cutoff_ms=settlement.ingested_at_ms,
    )

    assert long.cash_flow_usdt == Decimal("0.1")
    assert short.cash_flow_usdt == Decimal("-0.1")


def test_missing_exact_mark_is_not_proven_and_has_no_cash_flow() -> None:
    settlement = _settlement()

    projection = project_paper_funding_cost(
        side=PaperFundingSide.LONG,
        symbol=PaperSymbol.BTCUSDT,
        position_quantity=Decimal(1),
        settlement=settlement,
        mark_price=None,
        mark_evidence_identity=None,
        mark_at_ms=None,
        evaluation_cutoff_ms=settlement.ingested_at_ms,
    )

    assert projection.status is PaperFundingCostStatus.NOT_PROVEN
    assert projection.cash_flow_usdt is None
    assert projection.reason_code == "missing_exact_settlement_mark_evidence"


def test_missing_settlement_is_not_proven() -> None:
    projection = project_paper_funding_cost(
        side=PaperFundingSide.LONG,
        symbol=PaperSymbol.BTCUSDT,
        position_quantity=Decimal(1),
        settlement=None,
        mark_price=None,
        mark_evidence_identity=None,
        mark_at_ms=None,
        evaluation_cutoff_ms=1_000,
    )

    assert projection.status is PaperFundingCostStatus.NOT_PROVEN
    assert projection.cash_flow_usdt is None
    assert projection.reason_code == "missing_exact_settlement_evidence"


def test_future_settlement_evidence_is_rejected() -> None:
    settlement = _settlement(ingested_at_ms=1_500)

    with pytest.raises(ValueError, match="future settlement evidence"):
        project_paper_funding_cost(
            side=PaperFundingSide.LONG,
            symbol=PaperSymbol.BTCUSDT,
            position_quantity=Decimal(1),
            settlement=settlement,
            mark_price=Decimal(100),
            mark_evidence_identity="c" * 64,
            mark_at_ms=settlement.settlement_at_ms,
            evaluation_cutoff_ms=1_400,
        )


def test_funding_projection_exact_replay_is_identity_stable() -> None:
    settlement = _settlement()
    kwargs = {
        "side": PaperFundingSide.LONG,
        "symbol": PaperSymbol.BTCUSDT,
        "position_quantity": Decimal(1),
        "settlement": settlement,
        "mark_price": Decimal(100),
        "mark_evidence_identity": "d" * 64,
        "mark_at_ms": settlement.settlement_at_ms,
        "evaluation_cutoff_ms": settlement.ingested_at_ms,
    }

    first = project_paper_funding_cost(**kwargs)
    replay = project_paper_funding_cost(**kwargs)

    assert replay == first
    assert replay.projection_identity == first.projection_identity
