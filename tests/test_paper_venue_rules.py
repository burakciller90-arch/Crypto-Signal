"""Tests for authoritative public Binance spot venue-rule snapshots."""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
from decimal import Decimal

import httpx
import pytest

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.paper import venue_rules as paper_venue_rules
from crypto_signal.paper.execution_input import (
    PAPER_EXECUTION_INPUT_POLICY_VERSION,
    FrozenPaperExecutionInput,
    compute_execution_input_identity,
)
from crypto_signal.paper.ledger import PaperLedgerWriteDisposition
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol
from crypto_signal.paper.venue_rules import (
    PAPER_SIMULATED_COST_POLICY_VERSION,
    PaperVenueRuleError,
    PaperVenueRuleStore,
    build_execution_snapshot_from_venue_rules,
    fetch_binance_spot_venue_rules,
    parse_binance_spot_venue_rules,
)

SOURCE_IDS = ("a" * 64, "b" * 64)


def _payload(
    *,
    symbol: str = "BTCUSDT",
    status: str = "TRADING",
    spot: bool = True,
    min_notional: str = "5",
):
    return {
        "timezone": "UTC",
        "symbols": [
            {
                "symbol": symbol,
                "status": status,
                "baseAsset": symbol.removesuffix("USDT"),
                "quoteAsset": "USDT",
                "isSpotTradingAllowed": spot,
                "orderTypes": ["LIMIT", "MARKET"],
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "minPrice": "0.01",
                        "maxPrice": "1000000",
                        "tickSize": "0.01",
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.00001",
                        "maxQty": "9000",
                        "stepSize": "0.00001",
                    },
                    {
                        "filterType": "NOTIONAL",
                        "minNotional": min_notional,
                        "applyMinToMarket": True,
                        "maxNotional": "100000000",
                    },
                ],
            }
        ],
    }


def _execution_input(
    *,
    observed_at_ms: int = 20_000,
) -> FrozenPaperExecutionInput:
    kwargs = {
        "policy_version": PAPER_EXECUTION_INPUT_POLICY_VERSION,
        "candidate_action": PaperAction.BUY,
        "symbol": PaperSymbol.BTCUSDT,
        "source_freeze_identities": SOURCE_IDS,
        "signal_as_of_ms": 10_000,
        "source_exchange": Exchange.BINANCE,
        "source_market_type": MarketType.SPOT,
        "source_timeframe": "15m",
        "source_candle_open_time_ms": 11_000,
        "source_candle_close_time_ms": 19_000,
        "source_candle_ingested_at_ms": 19_100,
        "source_adapter_version": "binance-spot/1",
        "reference_price": Decimal(100),
        "price_field": "open",
    }
    return FrozenPaperExecutionInput(
        input_identity=compute_execution_input_identity(**kwargs),
        observed_at_ms=observed_at_ms,
        real_capital=REAL_CAPITAL,
        **kwargs,
    )


def test_parse_public_binance_rules_freezes_exact_filters_and_cost_policy() -> None:
    snapshot = parse_binance_spot_venue_rules(
        _payload(),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=15_000,
    )

    assert len(snapshot.snapshot_identity) == 64
    assert snapshot.symbol is PaperSymbol.BTCUSDT
    assert snapshot.quantity_step == Decimal("0.00001")
    assert snapshot.min_quantity == Decimal("0.00001")
    assert snapshot.max_quantity == Decimal("9000")
    assert snapshot.min_notional_usdt == Decimal("5")
    assert snapshot.tick_size == Decimal("0.01")
    assert snapshot.cost_policy_version == PAPER_SIMULATED_COST_POLICY_VERSION
    assert snapshot.fee_rate == Decimal("0.001")
    assert snapshot.spread_rate == Decimal("0.0005")
    assert snapshot.slippage_rate == Decimal("0.0005")
    assert snapshot.real_capital == REAL_CAPITAL == 0


def test_parse_uses_stricter_min_notional_when_both_filter_types_exist() -> None:
    payload = _payload(min_notional="5")
    payload["symbols"][0]["filters"].append(
        {
            "filterType": "MIN_NOTIONAL",
            "minNotional": "10",
            "applyToMarket": True,
        }
    )
    snapshot = parse_binance_spot_venue_rules(
        payload,
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=15_000,
    )
    assert snapshot.min_notional_usdt == Decimal("10")


@pytest.mark.parametrize(
    ("status", "spot", "message"),
    [
        ("HALT", True, "not TRADING"),
        ("TRADING", False, "not explicitly spot"),
    ],
)
def test_parse_fails_closed_on_nontradable_symbol(
    status: str,
    spot: bool,
    message: str,
) -> None:
    with pytest.raises(PaperVenueRuleError, match=message):
        parse_binance_spot_venue_rules(
            _payload(status=status, spot=spot),
            symbol=PaperSymbol.BTCUSDT,
            observed_at_ms=15_000,
        )


def test_fetch_uses_public_exchange_info_without_credentials() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["symbol"] = request.url.params.get("symbol")
        seen["api_key"] = request.headers.get("X-MBX-APIKEY")
        return httpx.Response(200, json=_payload())

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetch_binance_spot_venue_rules(
                symbol=PaperSymbol.BTCUSDT,
                observed_at_ms=15_000,
                client=client,
            )

    snapshot = asyncio.run(run())
    assert snapshot.symbol is PaperSymbol.BTCUSDT
    assert seen == {
        "path": "/api/v3/exchangeInfo",
        "symbol": "BTCUSDT",
        "api_key": None,
    }


def test_immutable_store_reopens_and_selects_latest_not_after_input(tmp_path) -> None:
    store = PaperVenueRuleStore(tmp_path / "paper.sqlite3")
    first = parse_binance_spot_venue_rules(
        _payload(min_notional="5"),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=12_000,
    )
    second = parse_binance_spot_venue_rules(
        _payload(min_notional="10"),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=18_000,
    )
    future = parse_binance_spot_venue_rules(
        _payload(min_notional="20"),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=21_000,
    )

    assert store.append(first) is PaperLedgerWriteDisposition.INSERTED
    assert store.append(first) is PaperLedgerWriteDisposition.UNCHANGED
    assert store.append(second) is PaperLedgerWriteDisposition.INSERTED
    assert store.append(future) is PaperLedgerWriteDisposition.INSERTED

    reopened = PaperVenueRuleStore(store.path)
    selected = reopened.latest_at_or_before(
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=20_000,
    )
    assert selected == second
    assert reopened.list(symbol=PaperSymbol.BTCUSDT) == (first, second, future)


def test_venue_rule_store_is_append_only(tmp_path) -> None:
    store = PaperVenueRuleStore(tmp_path / "paper.sqlite3")
    snapshot = parse_binance_spot_venue_rules(
        _payload(),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=15_000,
    )
    store.append(snapshot)

    with sqlite3.connect(store.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable paper venue-rule"):
            connection.execute(
                """
                UPDATE paper_venue_rule_snapshots
                SET observed_at_ms = 99999
                WHERE snapshot_identity = ?
                """,
                (snapshot.snapshot_identity,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable paper venue-rule"):
            connection.execute(
                """
                DELETE FROM paper_venue_rule_snapshots
                WHERE snapshot_identity = ?
                """,
                (snapshot.snapshot_identity,),
            )


def test_execution_snapshot_is_bound_to_rules_cost_policy_and_input() -> None:
    execution_input = _execution_input(observed_at_ms=20_000)
    rules = parse_binance_spot_venue_rules(
        _payload(),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=19_500,
    )
    snapshot = build_execution_snapshot_from_venue_rules(
        execution_input=execution_input,
        venue_rules=rules,
    )

    assert f"|rules:{rules.snapshot_identity}|" in snapshot.venue_reference
    assert f"|cost:{rules.cost_policy_version}|" in snapshot.venue_reference
    assert snapshot.venue_reference.endswith(execution_input.venue_reference)
    assert snapshot.quantity_step == rules.quantity_step
    assert snapshot.min_quantity == rules.min_quantity
    assert snapshot.min_notional_usdt == rules.min_notional_usdt
    assert snapshot.fee_rate == rules.fee_rate
    assert snapshot.real_capital == REAL_CAPITAL == 0


def test_future_rules_cannot_be_backdated_into_execution_input() -> None:
    execution_input = _execution_input(observed_at_ms=20_000)
    future_rules = parse_binance_spot_venue_rules(
        _payload(),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=20_001,
    )
    with pytest.raises(PaperVenueRuleError, match="no later"):
        build_execution_snapshot_from_venue_rules(
            execution_input=execution_input,
            venue_rules=future_rules,
        )


def test_venue_rule_source_has_no_account_credential_or_real_order_authority() -> None:
    source = inspect.getsource(paper_venue_rules).lower()
    forbidden = (
        "x-mbx-apikey",
        "api_secret",
        "place_order",
        "submit_order",
        "cancel_order",
        "/api/v3/account",
        "/api/v3/order",
        "real_capital=1",
        "ccxt",
        "subprocess",
        "launchctl",
    )
    assert all(token not in source for token in forbidden)
    assert paper_venue_rules.REAL_CAPITAL == REAL_CAPITAL == 0
