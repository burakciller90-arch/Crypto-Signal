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
from crypto_signal.intelligence.options_volatility import (
    OptionsTermStructureShape,
    OptionsVolatilityAnalysis,
    OptionsVolatilityMetrics,
    OptionsVolatilityStatus,
    build_options_volatility_evidence_freeze,
)

SOURCE_MS = 1_800_000_000_000
OBSERVED_MS = SOURCE_MS + 20
INGESTED_MS = SOURCE_MS + 40
EXPIRY_1 = SOURCE_MS + 7 * 24 * 60 * 60 * 1000
EXPIRY_2 = SOURCE_MS + 14 * 24 * 60 * 60 * 1000
ADAPTER = "rdp6-options-volatility-test/1"


def _instrument(
    *,
    expiry: int,
    strike: int,
    side: OptionType,
) -> object:
    code = "C" if side is OptionType.CALL else "P"
    symbol = f"BTC-{expiry}-{strike}-{code}-USDT"
    return build_option_instrument_spec(
        exchange=Exchange.BYBIT,
        symbol=symbol,
        base_coin="BTC",
        quote_coin="USDT",
        settle_coin="USDT",
        option_type=side,
        strike=Decimal(strike),
        expiry_at_ms=expiry,
        status="Trading",
        source=DataSource.REST,
        source_timestamp_ms=SOURCE_MS - 100,
        observed_at_ms=OBSERVED_MS - 100,
        ingested_at_ms=INGESTED_MS - 100,
        adapter_version=ADAPTER,
    )


def _quote(
    *,
    expiry: int,
    strike: int,
    side: OptionType,
    delta: str,
    mark_iv: str | None,
    open_interest: str | None,
    volume_24h: str | None,
) -> OptionContractQuote:
    instrument = _instrument(expiry=expiry, strike=strike, side=side)

    def dec(value: str | None) -> Decimal | None:
        return None if value is None else Decimal(value)

    return build_option_contract_quote(
        instrument=instrument,
        mark_iv=dec(mark_iv),
        bid_iv=None,
        ask_iv=None,
        mark_price=Decimal(100),
        index_price=Decimal(70_000),
        underlying_price=Decimal(70_050),
        delta=Decimal(delta),
        gamma=Decimal("0.0001"),
        vega=Decimal("12.5"),
        theta=Decimal("-2.5"),
        open_interest=dec(open_interest),
        volume_24h=dec(volume_24h),
        turnover_24h=None,
        source=DataSource.REST,
        source_timestamp_ms=SOURCE_MS,
        observed_at_ms=OBSERVED_MS,
        ingested_at_ms=INGESTED_MS,
        adapter_version=ADAPTER,
    )


def _full_contracts(
    *,
    missing_oi: bool = False,
    include_25d: bool = True,
) -> tuple[OptionContractQuote, ...]:
    contracts = [
        _quote(
            expiry=EXPIRY_1,
            strike=70_000,
            side=OptionType.CALL,
            delta="0.50",
            mark_iv="0.50",
            open_interest=None if missing_oi else "100",
            volume_24h=None if missing_oi else "10",
        ),
        _quote(
            expiry=EXPIRY_1,
            strike=70_000,
            side=OptionType.PUT,
            delta="-0.50",
            mark_iv="0.52",
            open_interest="80",
            volume_24h="8",
        ),
        _quote(
            expiry=EXPIRY_2,
            strike=70_000,
            side=OptionType.CALL,
            delta="0.50",
            mark_iv="0.54",
            open_interest="120",
            volume_24h="12",
        ),
        _quote(
            expiry=EXPIRY_2,
            strike=70_000,
            side=OptionType.PUT,
            delta="-0.50",
            mark_iv="0.56",
            open_interest="100",
            volume_24h="10",
        ),
    ]
    if include_25d:
        contracts.extend(
            (
                _quote(
                    expiry=EXPIRY_1,
                    strike=75_000,
                    side=OptionType.CALL,
                    delta="0.25",
                    mark_iv="0.48",
                    open_interest="50",
                    volume_24h="5",
                ),
                _quote(
                    expiry=EXPIRY_1,
                    strike=65_000,
                    side=OptionType.PUT,
                    delta="-0.25",
                    mark_iv="0.56",
                    open_interest="70",
                    volume_24h="7",
                ),
                _quote(
                    expiry=EXPIRY_2,
                    strike=75_000,
                    side=OptionType.CALL,
                    delta="0.25",
                    mark_iv="0.52",
                    open_interest="60",
                    volume_24h="6",
                ),
                _quote(
                    expiry=EXPIRY_2,
                    strike=65_000,
                    side=OptionType.PUT,
                    delta="-0.25",
                    mark_iv="0.60",
                    open_interest="80",
                    volume_24h="8",
                ),
            )
        )
    return tuple(contracts)


def _surface(
    contracts: tuple[OptionContractQuote, ...],
):
    instruments = tuple(
        _instrument(
            expiry=item.expiry_at_ms,
            strike=int(item.strike),
            side=item.option_type,
        )
        for item in contracts
    )
    metadata_identity = build_option_instrument_metadata_identity(
        exchange=Exchange.BYBIT,
        base_coin="BTC",
        instrument_specs=instruments,
    )
    return build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_coin="BTC",
        instrument_metadata_identity=metadata_identity,
        contracts=contracts,
        source=DataSource.REST,
        source_timestamp_ms=SOURCE_MS,
        observed_at_ms=OBSERVED_MS,
        ingested_at_ms=INGESTED_MS,
        adapter_version=ADAPTER,
    )


def test_measured_surface_computes_exact_term_rr_and_positioning_context() -> None:
    surface = _surface(_full_contracts())
    freeze = build_options_volatility_evidence_freeze(
        surface,
        as_of_ms=INGESTED_MS + 1_000,
    )
    analysis = freeze.analysis
    metrics = analysis.metrics

    assert analysis.status is OptionsVolatilityStatus.MEASURED
    assert metrics is not None
    assert metrics.measured_atm_expiry_count == 2
    assert metrics.measured_rr_expiry_count == 2
    assert metrics.front_atm_iv == Decimal("0.51")
    assert metrics.next_atm_iv == Decimal("0.55")
    assert metrics.term_structure_iv_change == Decimal("0.04")
    assert (
        metrics.term_structure_shape
        is OptionsTermStructureShape.HIGHER_LATER_IV
    )
    assert metrics.expiries[0].risk_reversal_25d == Decimal("-0.08")
    assert metrics.expiries[1].risk_reversal_25d == Decimal("-0.08")
    assert metrics.put_call_open_interest_ratio == Decimal(1)
    assert metrics.put_call_volume_ratio == Decimal(1)
    assert metrics.total_open_interest == Decimal(660)
    assert metrics.total_volume_24h == Decimal(66)
    assert metrics.top_expiry_at_ms == EXPIRY_2
    assert metrics.top_expiry_open_interest_share == (
        Decimal(360) / Decimal(660)
    )
    assert "options_metrics_are_descriptive_not_directional" in (
        analysis.uncertainty_flags
    )
    assert "dealer_gamma_position_not_inferred" in analysis.uncertainty_flags
    assert "max_pain_not_estimated" in analysis.uncertainty_flags


def test_risk_reversal_sign_is_call_25d_iv_minus_put_25d_iv() -> None:
    analysis = build_options_volatility_evidence_freeze(
        _surface(_full_contracts()),
        as_of_ms=INGESTED_MS + 1_000,
    ).analysis
    metrics = analysis.metrics
    assert metrics is not None
    first = metrics.expiries[0]
    assert first.call_25d_iv == Decimal("0.48")
    assert first.put_25d_iv == Decimal("0.56")
    assert first.risk_reversal_25d == (
        first.call_25d_iv - first.put_25d_iv
    )


def test_missing_25d_pair_stays_partial_instead_of_fabricating_skew() -> None:
    analysis = build_options_volatility_evidence_freeze(
        _surface(_full_contracts(include_25d=False)),
        as_of_ms=INGESTED_MS + 1_000,
    ).analysis

    assert analysis.status is OptionsVolatilityStatus.PARTIAL
    assert analysis.metrics is not None
    assert analysis.metrics.measured_atm_expiry_count == 2
    assert analysis.metrics.measured_rr_expiry_count == 0
    assert all(
        item.risk_reversal_25d is None
        for item in analysis.metrics.expiries
    )
    assert "risk_reversal_25d_unavailable" in analysis.uncertainty_flags


def test_missing_oi_and_volume_never_become_zero_or_partial_ratios() -> None:
    analysis = build_options_volatility_evidence_freeze(
        _surface(_full_contracts(missing_oi=True)),
        as_of_ms=INGESTED_MS + 1_000,
    ).analysis
    metrics = analysis.metrics

    assert metrics is not None
    assert metrics.total_open_interest is None
    assert metrics.total_volume_24h is None
    assert metrics.put_call_open_interest_ratio is None
    assert metrics.put_call_volume_ratio is None
    assert metrics.top_expiry_open_interest_share is None
    assert "open_interest_coverage_incomplete" in analysis.uncertainty_flags
    assert "volume_24h_coverage_incomplete" in analysis.uncertainty_flags


def test_stale_surface_fails_closed_without_metrics() -> None:
    surface = _surface(_full_contracts())
    analysis = build_options_volatility_evidence_freeze(
        surface,
        as_of_ms=SOURCE_MS + 120_001,
    ).analysis

    assert analysis.status is OptionsVolatilityStatus.STALE
    assert analysis.metrics is None
    assert "stale_options_surface" in analysis.uncertainty_flags


def test_future_surface_is_rejected_at_pit_boundary() -> None:
    surface = _surface(_full_contracts())

    with pytest.raises(ValueError, match="future evidence"):
        build_options_volatility_evidence_freeze(
            surface,
            as_of_ms=INGESTED_MS - 1,
        )


def test_surface_without_evaluable_iv_is_not_evaluable() -> None:
    contract = _quote(
        expiry=EXPIRY_1,
        strike=70_000,
        side=OptionType.CALL,
        delta="0.50",
        mark_iv=None,
        open_interest="100",
        volume_24h="10",
    )
    analysis = build_options_volatility_evidence_freeze(
        _surface((contract,)),
        as_of_ms=INGESTED_MS + 1_000,
    ).analysis

    assert analysis.status is OptionsVolatilityStatus.NOT_EVALUABLE
    assert analysis.metrics is None
    assert "no_evaluable_implied_volatility_structure" in (
        analysis.uncertainty_flags
    )


def test_freeze_identity_is_deterministic() -> None:
    surface = _surface(_full_contracts())
    first = build_options_volatility_evidence_freeze(
        surface,
        as_of_ms=INGESTED_MS + 1_000,
    )
    second = build_options_volatility_evidence_freeze(
        surface,
        as_of_ms=INGESTED_MS + 1_000,
    )

    assert first == second
    assert first.freeze_identity == second.freeze_identity


def test_engine_contract_has_no_direction_probability_or_dealer_claim_fields() -> None:
    names = {
        field.name
        for model in (OptionsVolatilityAnalysis, OptionsVolatilityMetrics)
        for field in fields(model)
    }
    forbidden = {
        "direction",
        "probability",
        "dealer_gamma",
        "dealer_positioning",
        "max_pain",
        "signal",
        "trade_command",
    }
    assert names.isdisjoint(forbidden)
