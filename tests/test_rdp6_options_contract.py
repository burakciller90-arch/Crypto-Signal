from __future__ import annotations

import json
from dataclasses import fields, replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.data.options import (
    OptionContractQuote,
    OptionInstrumentSpec,
    OptionSurfaceObservation,
    OptionType,
    build_option_contract_quote,
    build_option_instrument_spec,
    build_option_surface_observation,
)
from crypto_signal.ledger.serialization import canonical_sha256

SOURCE_TS = 1_760_000_000_200
OBSERVED_TS = SOURCE_TS + 10
INGESTED_TS = OBSERVED_TS + 5
EXPIRY_TS = 1_774_598_400_000
ADAPTER = "rdp6-options-contract-test/1"
FIXTURES = Path(__file__).parent / "fixtures" / "rdp6"


def _instrument(
    *,
    symbol: str = "BTC-27MAR26-70000-C-USDT",
    base_coin: str = "BTC",
    option_type: OptionType = OptionType.CALL,
    strike: Decimal = Decimal(70000),
) -> OptionInstrumentSpec:
    return build_option_instrument_spec(
        exchange=Exchange.BYBIT,
        symbol=symbol,
        base_coin=base_coin,
        quote_coin="USDT",
        settle_coin="USDT",
        option_type=option_type,
        strike=strike,
        expiry_at_ms=EXPIRY_TS,
        status="Trading",
        source=DataSource.REST,
        source_timestamp_ms=SOURCE_TS - 100,
        observed_at_ms=OBSERVED_TS - 100,
        ingested_at_ms=INGESTED_TS - 100,
        adapter_version=ADAPTER,
    )


def _quote(
    instrument: OptionInstrumentSpec,
    *,
    source_timestamp_ms: int = SOURCE_TS,
    observed_at_ms: int = OBSERVED_TS,
    ingested_at_ms: int = INGESTED_TS,
    bid_iv: Decimal | None = Decimal("0.52"),
) -> OptionContractQuote:
    return build_option_contract_quote(
        instrument=instrument,
        mark_iv=Decimal("0.53"),
        bid_iv=bid_iv,
        ask_iv=Decimal("0.54"),
        mark_price=Decimal(5200),
        index_price=Decimal(70050),
        underlying_price=Decimal(70110),
        delta=(
            Decimal("0.51")
            if instrument.option_type is OptionType.CALL
            else Decimal("-0.49")
        ),
        gamma=Decimal("0.00008"),
        vega=Decimal("122.4"),
        theta=Decimal("-18.2"),
        open_interest=Decimal("125.5"),
        volume_24h=Decimal("31.2"),
        turnover_24h=Decimal(1825000),
        source=DataSource.REST,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=ADAPTER,
    )


def _metadata_identity() -> str:
    return canonical_sha256(
        {
            "provider": "bybit",
            "channel": "option_instruments",
            "base_coin": "BTC",
            "source_timestamp_ms": SOURCE_TS - 100,
        }
    )


def test_option_instrument_identity_is_deterministic_and_immutable() -> None:
    first = _instrument()
    second = _instrument()

    assert first == second
    assert first.instrument_identity == second.instrument_identity

    with pytest.raises(ValueError, match="identity mismatch"):
        replace(first, status="Delivering")


def test_option_contract_rejects_invalid_context_and_measurements() -> None:
    with pytest.raises(ValueError, match="symbol must be non-empty uppercase"):
        _instrument(symbol="btc-27mar26-70000-c-usdt")

    with pytest.raises(ValueError, match="strike must be finite and positive"):
        _instrument(strike=Decimal(0))

    instrument = _instrument()
    with pytest.raises(ValueError, match="delta must be inside"):
        build_option_contract_quote(
            instrument=instrument,
            mark_iv=Decimal("0.53"),
            bid_iv=None,
            ask_iv=None,
            mark_price=None,
            index_price=None,
            underlying_price=None,
            delta=Decimal("1.01"),
            gamma=None,
            vega=None,
            theta=None,
            open_interest=None,
            volume_24h=None,
            turnover_24h=None,
            source=DataSource.REST,
            source_timestamp_ms=SOURCE_TS,
            observed_at_ms=OBSERVED_TS,
            ingested_at_ms=INGESTED_TS,
            adapter_version=ADAPTER,
        )

    with pytest.raises(ValueError, match="open_interest cannot be negative"):
        build_option_contract_quote(
            instrument=instrument,
            mark_iv=Decimal("0.53"),
            bid_iv=None,
            ask_iv=None,
            mark_price=None,
            index_price=None,
            underlying_price=None,
            delta=None,
            gamma=None,
            vega=None,
            theta=None,
            open_interest=Decimal(-1),
            volume_24h=None,
            turnover_24h=None,
            source=DataSource.REST,
            source_timestamp_ms=SOURCE_TS,
            observed_at_ms=OBSERVED_TS,
            ingested_at_ms=INGESTED_TS,
            adapter_version=ADAPTER,
        )


def test_option_quote_preserves_missing_provider_fields_as_none() -> None:
    quote = _quote(_instrument(), bid_iv=None)

    assert quote.bid_iv is None
    assert quote.ask_iv == Decimal("0.54")
    assert quote.mark_iv == Decimal("0.53")


def test_surface_identity_is_order_independent_but_snapshot_coherent() -> None:
    call_instrument = _instrument()
    put_instrument = _instrument(
        symbol="BTC-27MAR26-70000-P-USDT",
        option_type=OptionType.PUT,
    )
    call = _quote(call_instrument)
    put = _quote(put_instrument)

    first = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_coin="BTC",
        instrument_metadata_identity=_metadata_identity(),
        contracts=(put, call),
        source=DataSource.REST,
        source_timestamp_ms=SOURCE_TS,
        observed_at_ms=OBSERVED_TS,
        ingested_at_ms=INGESTED_TS,
        adapter_version=ADAPTER,
    )
    second = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_coin="BTC",
        instrument_metadata_identity=_metadata_identity(),
        contracts=(call, put),
        source=DataSource.REST,
        source_timestamp_ms=SOURCE_TS,
        observed_at_ms=OBSERVED_TS,
        ingested_at_ms=INGESTED_TS,
        adapter_version=ADAPTER,
    )

    assert first.surface_identity == second.surface_identity
    assert first.contracts == second.contracts
    assert tuple(item.symbol for item in first.contracts) == (
        "BTC-27MAR26-70000-C-USDT",
        "BTC-27MAR26-70000-P-USDT",
    )

    late = _quote(
        call_instrument,
        observed_at_ms=OBSERVED_TS + 1,
        ingested_at_ms=INGESTED_TS + 1,
    )
    with pytest.raises(ValueError, match="snapshot mismatch"):
        build_option_surface_observation(
            exchange=Exchange.BYBIT,
            base_coin="BTC",
            instrument_metadata_identity=_metadata_identity(),
            contracts=(late,),
            source=DataSource.REST,
            source_timestamp_ms=SOURCE_TS,
            observed_at_ms=OBSERVED_TS,
            ingested_at_ms=INGESTED_TS,
            adapter_version=ADAPTER,
        )


def test_surface_rejects_duplicate_and_noncanonical_manual_state() -> None:
    quote = _quote(_instrument())
    surface = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_coin="BTC",
        instrument_metadata_identity=_metadata_identity(),
        contracts=(quote,),
        source=DataSource.REST,
        source_timestamp_ms=SOURCE_TS,
        observed_at_ms=OBSERVED_TS,
        ingested_at_ms=INGESTED_TS,
        adapter_version=ADAPTER,
    )

    with pytest.raises(ValueError, match="duplicate symbols"):
        build_option_surface_observation(
            exchange=Exchange.BYBIT,
            base_coin="BTC",
            instrument_metadata_identity=_metadata_identity(),
            contracts=(quote, quote),
            source=DataSource.REST,
            source_timestamp_ms=SOURCE_TS,
            observed_at_ms=OBSERVED_TS,
            ingested_at_ms=INGESTED_TS,
            adapter_version=ADAPTER,
        )

    put = _quote(
        _instrument(
            symbol="BTC-27MAR26-70000-P-USDT",
            option_type=OptionType.PUT,
        )
    )
    two_contract_surface = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_coin="BTC",
        instrument_metadata_identity=_metadata_identity(),
        contracts=(quote, put),
        source=DataSource.REST,
        source_timestamp_ms=SOURCE_TS,
        observed_at_ms=OBSERVED_TS,
        ingested_at_ms=INGESTED_TS,
        adapter_version=ADAPTER,
    )
    with pytest.raises(ValueError, match="must be canonical"):
        replace(
            two_contract_surface,
            contracts=tuple(reversed(two_contract_surface.contracts)),
        )

    assert surface.contracts == (quote,)


def test_contracts_do_not_encode_unsupported_directional_claims() -> None:
    names = {
        field.name
        for contract in (
            OptionInstrumentSpec,
            OptionContractQuote,
            OptionSurfaceObservation,
        )
        for field in fields(contract)
    }

    forbidden = {
        "dealer_gamma",
        "dealer_positioning",
        "max_pain",
        "direction",
        "signal",
        "probability",
    }
    assert names.isdisjoint(forbidden)


@pytest.mark.parametrize(
    ("filename", "base_coin"),
    (
        ("bybit_option_instruments_btc.json", "BTC"),
        ("bybit_option_instruments_eth.json", "ETH"),
    ),
)
def test_official_shaped_instrument_fixtures_preserve_provider_fields(
    filename: str,
    base_coin: str,
) -> None:
    payload = json.loads((FIXTURES / filename).read_text())
    assert payload["retCode"] == 0
    assert payload["result"]["category"] == "option"
    rows = payload["result"]["list"]
    assert rows
    assert {row["baseCoin"] for row in rows} == {base_coin}
    assert {row["optionsType"] for row in rows} == {"Call", "Put"}
    assert all(row["deliveryTime"] for row in rows)
    assert all(row["quoteCoin"] and row["settleCoin"] for row in rows)


@pytest.mark.parametrize(
    ("filename", "base_coin"),
    (
        ("bybit_option_tickers_btc.json", "BTC"),
        ("bybit_option_tickers_eth.json", "ETH"),
    ),
)
def test_official_shaped_ticker_fixtures_cover_options_measurements(
    filename: str,
    base_coin: str,
) -> None:
    payload = json.loads((FIXTURES / filename).read_text())
    assert payload["retCode"] == 0
    assert payload["result"]["category"] == "option"
    rows = payload["result"]["list"]
    assert rows
    assert all(row["symbol"].startswith(f"{base_coin}-") for row in rows)
    required = {
        "markIv",
        "bid1Iv",
        "ask1Iv",
        "markPrice",
        "indexPrice",
        "underlyingPrice",
        "openInterest",
        "volume24h",
        "turnover24h",
        "delta",
        "gamma",
        "vega",
        "theta",
    }
    assert all(required <= set(row) for row in rows)

    if base_coin == "ETH":
        assert rows[1]["bid1Iv"] == ""
