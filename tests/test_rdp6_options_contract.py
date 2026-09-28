from __future__ import annotations

from dataclasses import fields
from decimal import Decimal

import pytest

from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.data.options import (
    OptionContractQuote,
    OptionType,
    build_option_contract_quote,
    build_option_instrument_metadata_identity,
    build_option_instrument_spec,
    build_option_surface_observation,
)

SOURCE_MS = 1_800_000_000_000
OBSERVED_MS = SOURCE_MS + 20
INGESTED_MS = SOURCE_MS + 40
EXPIRY_MS = SOURCE_MS + 7 * 24 * 60 * 60 * 1000
ADAPTER = "rdp6-options-test/1"


def _instrument(
    *,
    symbol: str,
    option_type: OptionType,
    strike: str,
    expiry_at_ms: int = EXPIRY_MS,
):
    return build_option_instrument_spec(
        exchange=Exchange.BYBIT,
        symbol=symbol,
        base_asset="BTC",
        quote_asset="USDT",
        settle_asset="USDT",
        option_type=option_type,
        strike=Decimal(strike),
        expiry_at_ms=expiry_at_ms,
        status="Trading",
        source_timestamp_ms=SOURCE_MS,
        observed_at_ms=OBSERVED_MS,
        ingested_at_ms=INGESTED_MS,
        source=DataSource.REST,
        adapter_version=ADAPTER,
    )


def _quote(
    instrument,
    *,
    mark_iv: str | None = "0.55",
    delta: str | None = "0.25",
    open_interest: str | None = "125.5",
):
    def dec(value: str | None) -> Decimal | None:
        return None if value is None else Decimal(value)

    return build_option_contract_quote(
        instrument=instrument,
        mark_iv=dec(mark_iv),
        bid_iv=Decimal("0.54") if mark_iv is not None else None,
        ask_iv=Decimal("0.56") if mark_iv is not None else None,
        mark_price=Decimal("0.031"),
        index_price=Decimal(70000),
        underlying_price=Decimal(70100),
        delta=dec(delta),
        gamma=Decimal("0.00001"),
        vega=Decimal("41.2"),
        theta=Decimal("-18.7"),
        open_interest=dec(open_interest),
        volume_24h=Decimal("12.5"),
        turnover_24h=Decimal(271500),
    )


def test_surface_identity_is_deterministic_and_order_independent() -> None:
    call = _instrument(
        symbol="BTC-27MAR27-70000-C-USDT",
        option_type=OptionType.CALL,
        strike="70000",
    )
    put = _instrument(
        symbol="BTC-27MAR27-70000-P-USDT",
        option_type=OptionType.PUT,
        strike="70000",
    )
    call_quote = _quote(call)
    put_quote = _quote(put, delta="-0.25")

    first = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_asset="BTC",
        source_timestamp_ms=SOURCE_MS + 100,
        observed_at_ms=OBSERVED_MS + 100,
        ingested_at_ms=INGESTED_MS + 100,
        source=DataSource.REST,
        adapter_version=ADAPTER,
        instrument_specs=(call, put),
        quotes=(call_quote, put_quote),
    )
    second = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_asset="BTC",
        source_timestamp_ms=SOURCE_MS + 100,
        observed_at_ms=OBSERVED_MS + 100,
        ingested_at_ms=INGESTED_MS + 100,
        source=DataSource.REST,
        adapter_version=ADAPTER,
        instrument_specs=(put, call),
        quotes=(put_quote, call_quote),
    )

    assert first == second
    assert first.surface_identity == second.surface_identity
    assert first.instrument_metadata_identity == second.instrument_metadata_identity
    assert tuple(item.symbol for item in first.quotes) == (
        "BTC-27MAR27-70000-C-USDT",
        "BTC-27MAR27-70000-P-USDT",
    )


def test_market_measurement_change_changes_quote_and_surface_identity() -> None:
    instrument = _instrument(
        symbol="BTC-27MAR27-70000-C-USDT",
        option_type=OptionType.CALL,
        strike="70000",
    )
    first_quote = _quote(instrument, mark_iv="0.55")
    second_quote = _quote(instrument, mark_iv="0.57")
    assert first_quote.quote_identity != second_quote.quote_identity

    first = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_asset="BTC",
        source_timestamp_ms=SOURCE_MS + 100,
        observed_at_ms=OBSERVED_MS + 100,
        ingested_at_ms=INGESTED_MS + 100,
        source=DataSource.REST,
        adapter_version=ADAPTER,
        instrument_specs=(instrument,),
        quotes=(first_quote,),
    )
    second = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_asset="BTC",
        source_timestamp_ms=SOURCE_MS + 100,
        observed_at_ms=OBSERVED_MS + 100,
        ingested_at_ms=INGESTED_MS + 100,
        source=DataSource.REST,
        adapter_version=ADAPTER,
        instrument_specs=(instrument,),
        quotes=(second_quote,),
    )
    assert first.surface_identity != second.surface_identity


def test_missing_optional_quote_measurements_remain_none() -> None:
    instrument = _instrument(
        symbol="BTC-27MAR27-65000-P-USDT",
        option_type=OptionType.PUT,
        strike="65000",
    )
    quote = build_option_contract_quote(
        instrument=instrument,
        mark_iv=None,
        bid_iv=None,
        ask_iv=None,
        mark_price=None,
        index_price=None,
        underlying_price=None,
        delta=None,
        gamma=None,
        vega=None,
        theta=None,
        open_interest=None,
        volume_24h=None,
        turnover_24h=None,
    )

    assert quote.mark_iv is None
    assert quote.open_interest is None
    assert quote.volume_24h is None

    surface = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_asset="BTC",
        source_timestamp_ms=SOURCE_MS + 100,
        observed_at_ms=OBSERVED_MS + 100,
        ingested_at_ms=INGESTED_MS + 100,
        source=DataSource.REST,
        adapter_version=ADAPTER,
        instrument_specs=(instrument,),
        quotes=(quote,),
    )
    assert surface.quotes == (quote,)


def test_instrument_metadata_identity_is_order_independent() -> None:
    first = _instrument(
        symbol="BTC-27MAR27-70000-C-USDT",
        option_type=OptionType.CALL,
        strike="70000",
    )
    second = _instrument(
        symbol="BTC-27MAR27-70000-P-USDT",
        option_type=OptionType.PUT,
        strike="70000",
    )
    assert build_option_instrument_metadata_identity(
        exchange=Exchange.BYBIT,
        base_asset="BTC",
        instrument_specs=(first, second),
    ) == build_option_instrument_metadata_identity(
        exchange=Exchange.BYBIT,
        base_asset="BTC",
        instrument_specs=(second, first),
    )


def test_surface_requires_exact_instrument_metadata_for_every_quote() -> None:
    call = _instrument(
        symbol="BTC-27MAR27-70000-C-USDT",
        option_type=OptionType.CALL,
        strike="70000",
    )
    put = _instrument(
        symbol="BTC-27MAR27-70000-P-USDT",
        option_type=OptionType.PUT,
        strike="70000",
    )

    with pytest.raises(
        ValueError,
        match="missing exact instrument metadata",
    ):
        build_option_surface_observation(
            exchange=Exchange.BYBIT,
            base_asset="BTC",
            source_timestamp_ms=SOURCE_MS + 100,
            observed_at_ms=OBSERVED_MS + 100,
            ingested_at_ms=INGESTED_MS + 100,
            source=DataSource.REST,
            adapter_version=ADAPTER,
            instrument_specs=(call,),
            quotes=(_quote(put, delta="-0.25"),),
        )


def test_empty_observed_quote_surface_is_explicit_not_fabricated() -> None:
    instrument = _instrument(
        symbol="BTC-27MAR27-70000-C-USDT",
        option_type=OptionType.CALL,
        strike="70000",
    )
    surface = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_asset="BTC",
        source_timestamp_ms=SOURCE_MS + 100,
        observed_at_ms=OBSERVED_MS + 100,
        ingested_at_ms=INGESTED_MS + 100,
        source=DataSource.REST,
        adapter_version=ADAPTER,
        instrument_specs=(instrument,),
        quotes=(),
    )
    assert surface.quotes == ()


def test_contract_rejects_invalid_numeric_and_timestamp_truth() -> None:
    with pytest.raises(ValueError, match="option strike must be positive"):
        _instrument(
            symbol="BTC-27MAR27-0-C-USDT",
            option_type=OptionType.CALL,
            strike="0",
        )

    instrument = _instrument(
        symbol="BTC-27MAR27-70000-C-USDT",
        option_type=OptionType.CALL,
        strike="70000",
    )
    with pytest.raises(ValueError, match="option delta"):
        _quote(instrument, delta="1.01")
    with pytest.raises(ValueError, match="open_interest cannot be negative"):
        _quote(instrument, open_interest="-1")
    with pytest.raises(ValueError, match="mark_iv must be finite"):
        _quote(instrument, mark_iv="NaN")

    with pytest.raises(
        ValueError,
        match="observation cannot postdate ingestion",
    ):
        build_option_instrument_spec(
            exchange=Exchange.BYBIT,
            symbol="BTC-27MAR27-70000-C-USDT",
            base_asset="BTC",
            quote_asset="USDT",
            settle_asset="USDT",
            option_type=OptionType.CALL,
            strike=Decimal(70000),
            expiry_at_ms=EXPIRY_MS,
            status="Trading",
            source_timestamp_ms=SOURCE_MS,
            observed_at_ms=INGESTED_MS + 1,
            ingested_at_ms=INGESTED_MS,
            source=DataSource.REST,
            adapter_version=ADAPTER,
        )


def test_contract_contains_no_direction_or_dealer_position_claims() -> None:
    quote_fields = {item.name for item in fields(OptionContractQuote)}
    forbidden = {
        "direction",
        "dealer_gamma",
        "dealer_position",
        "max_pain",
        "bullish",
        "bearish",
    }
    assert quote_fields.isdisjoint(forbidden)
