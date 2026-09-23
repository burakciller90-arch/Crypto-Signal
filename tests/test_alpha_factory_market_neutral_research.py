from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.models import Exchange
from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory import market_neutral_research
from research.alpha_factory.market_neutral_research import (
    MarketNeutralFamily,
    MarketNeutralStatus,
    NeutralInstrumentType,
    build_market_neutral_candidate,
    build_market_neutral_leg_evidence,
    build_market_neutral_policy,
    build_market_neutral_risk_context,
    evaluate_market_neutral_candidate,
)

AS_OF = 1_000_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _policy(
    *,
    min_edge: str = "5",
    max_counterparty: str = "0.40",
    max_hedge_mismatch: str = "0.05",
    max_funding_stress: str = "25",
):
    return build_market_neutral_policy(
        policy_version="market-neutral-shadow-policy-v1/1",
        max_leg_age_ms=5_000,
        max_leg_skew_ms=1_000,
        max_execution_latency_ms=500,
        max_transfer_delay_ms=30_000,
        max_counterparty_risk_0_1=Decimal(max_counterparty),
        max_hedge_mismatch_fraction=Decimal(max_hedge_mismatch),
        max_funding_change_stress_bps=Decimal(max_funding_stress),
        minimum_net_edge_bps=Decimal(min_edge),
    )


def _leg(
    *,
    exchange: Exchange,
    instrument: NeutralInstrumentType,
    bid: str,
    ask: str,
    observed_at_ms: int = AS_OF - 100,
    market_available_at_ms: int | None = None,
    fee: str = "3",
    slippage: str = "2",
    seed: str,
):
    market_ms = (
        observed_at_ms - 10
        if market_available_at_ms is None
        else market_available_at_ms
    )
    return build_market_neutral_leg_evidence(
        exchange=exchange,
        instrument_type=instrument,
        symbol="BTCUSDT",
        market_available_at_ms=market_ms,
        observed_at_ms=observed_at_ms,
        bid_price=Decimal(bid),
        ask_price=Decimal(ask),
        round_trip_fee_bps=Decimal(fee),
        round_trip_slippage_bps=Decimal(slippage),
        source_evidence_identity=_sha(f"source-{seed}"),
    )


def _risk(
    *,
    latency_ms: int = 100,
    latency_bps: str = "2",
    funding_benefit: str = "0",
    funding_stress: str = "1",
    transfer_required: bool = False,
    transfer_cost: str = "0",
    transfer_delay_ms: int | None = None,
    long_counterparty: str = "0.10",
    short_counterparty: str = "0.10",
    hedge_mismatch: str = "0.01",
):
    return build_market_neutral_risk_context(
        as_of_ms=AS_OF,
        execution_latency_ms=latency_ms,
        latency_penalty_bps=Decimal(latency_bps),
        expected_funding_benefit_bps=Decimal(funding_benefit),
        funding_change_stress_bps=Decimal(funding_stress),
        transfer_required=transfer_required,
        transfer_cost_bps=Decimal(transfer_cost),
        transfer_delay_ms=transfer_delay_ms,
        long_counterparty_risk_0_1=Decimal(long_counterparty),
        short_counterparty_risk_0_1=Decimal(short_counterparty),
        hedge_mismatch_fraction=Decimal(hedge_mismatch),
        source_evidence_identities=(
            _sha("counterparty"),
            _sha("funding"),
            _sha("latency"),
            _sha("transfer"),
        ),
    )


def _candidate(
    *,
    family: MarketNeutralFamily = MarketNeutralFamily.CROSS_EXCHANGE_SPREAD,
    long_leg=None,
    short_leg=None,
    risk=None,
):
    long_leg = long_leg or _leg(
        exchange=Exchange.BINANCE,
        instrument=NeutralInstrumentType.SPOT,
        bid="99.9",
        ask="100",
        seed="long",
    )
    short_leg = short_leg or _leg(
        exchange=Exchange.BYBIT,
        instrument=NeutralInstrumentType.SPOT,
        bid="102",
        ask="102.1",
        seed="short",
    )
    return build_market_neutral_candidate(
        family=family,
        asset="BTCUSDT",
        as_of_ms=AS_OF,
        long_leg=long_leg,
        short_leg=short_leg,
        risk_context=risk or _risk(),
    )


def test_cross_exchange_spread_is_shadow_eligible_only_after_explicit_costs() -> None:
    candidate = _candidate()
    result = evaluate_market_neutral_candidate(_policy(), candidate)

    gross = (Decimal(102) - Decimal(100)) / Decimal(101) * Decimal(10_000)
    expected_net = (
        gross
        - Decimal(6)
        - Decimal(4)
        - Decimal(2)
        - Decimal(1)
    )

    assert result.status is MarketNeutralStatus.ELIGIBLE_SHADOW
    assert result.gross_price_edge_bps == gross
    assert result.total_fee_bps == Decimal(6)
    assert result.total_slippage_bps == Decimal(4)
    assert result.latency_penalty_bps == Decimal(2)
    assert result.funding_change_stress_bps == Decimal(1)
    assert result.expected_funding_benefit_bps == Decimal(0)
    assert result.net_edge_bps == expected_net
    assert result.net_edge_bps > 0
    assert result.hypothetical_notional_usdt is None
    assert result.canonical_capital_mutation is False
    assert result.automatic_promotion is False
    assert result.shadow_only is True
    assert result.risk_free_claim is False
    assert result.production_authority is False
    assert result.real_capital == 0


def test_fees_and_slippage_can_erase_apparent_cross_exchange_edge() -> None:
    long_leg = _leg(
        exchange=Exchange.BINANCE,
        instrument=NeutralInstrumentType.SPOT,
        bid="99.9",
        ask="100",
        fee="60",
        slippage="30",
        seed="expensive-long",
    )
    short_leg = _leg(
        exchange=Exchange.BYBIT,
        instrument=NeutralInstrumentType.SPOT,
        bid="101",
        ask="101.1",
        fee="60",
        slippage="30",
        seed="expensive-short",
    )
    result = evaluate_market_neutral_candidate(
        _policy(),
        _candidate(long_leg=long_leg, short_leg=short_leg),
    )

    assert result.gross_price_edge_bps is not None
    assert result.gross_price_edge_bps > 0
    assert result.net_edge_bps is not None
    assert result.net_edge_bps < 0
    assert result.status is MarketNeutralStatus.HOLD_NO_NET_EDGE


def test_stale_or_unsynchronized_legs_are_not_evaluable() -> None:
    stale_long = _leg(
        exchange=Exchange.BINANCE,
        instrument=NeutralInstrumentType.SPOT,
        bid="99.9",
        ask="100",
        observed_at_ms=AS_OF - 6_000,
        seed="stale",
    )
    stale = evaluate_market_neutral_candidate(
        _policy(),
        _candidate(long_leg=stale_long),
    )
    assert stale.status is MarketNeutralStatus.NOT_EVALUABLE
    assert "long_leg_stale" in stale.reason_codes
    assert stale.net_edge_bps is None

    skewed_short = _leg(
        exchange=Exchange.BYBIT,
        instrument=NeutralInstrumentType.SPOT,
        bid="102",
        ask="102.1",
        observed_at_ms=AS_OF - 100,
        market_available_at_ms=AS_OF - 2_000,
        seed="skewed",
    )
    skewed = evaluate_market_neutral_candidate(
        _policy(),
        _candidate(short_leg=skewed_short),
    )
    assert skewed.status is MarketNeutralStatus.NOT_EVALUABLE
    assert "leg_market_time_skew_exceeds_policy" in skewed.reason_codes


def test_spot_perpetual_funding_capture_counts_funding_but_stresses_change() -> None:
    spot = _leg(
        exchange=Exchange.BINANCE,
        instrument=NeutralInstrumentType.SPOT,
        bid="99.9",
        ask="100",
        fee="1",
        slippage="1",
        seed="spot",
    )
    perp = _leg(
        exchange=Exchange.BINANCE,
        instrument=NeutralInstrumentType.LINEAR_PERPETUAL,
        bid="100",
        ask="100.1",
        fee="1",
        slippage="1",
        seed="perp",
    )
    candidate = _candidate(
        family=MarketNeutralFamily.FUNDING_CAPTURE,
        long_leg=spot,
        short_leg=perp,
        risk=_risk(
            funding_benefit="20",
            funding_stress="3",
            latency_bps="1",
        ),
    )
    result = evaluate_market_neutral_candidate(_policy(), candidate)

    assert result.gross_price_edge_bps == 0
    assert result.expected_funding_benefit_bps == Decimal(20)
    assert result.funding_change_stress_bps == Decimal(3)
    assert result.net_edge_bps == Decimal(12)
    assert result.status is MarketNeutralStatus.ELIGIBLE_SHADOW


def test_funding_change_stress_is_a_separate_risk_veto() -> None:
    spot = _leg(
        exchange=Exchange.BINANCE,
        instrument=NeutralInstrumentType.SPOT,
        bid="99.9",
        ask="100",
        seed="spot-stress",
    )
    perp = _leg(
        exchange=Exchange.BINANCE,
        instrument=NeutralInstrumentType.LINEAR_PERPETUAL,
        bid="102",
        ask="102.1",
        seed="perp-stress",
    )
    result = evaluate_market_neutral_candidate(
        _policy(max_funding_stress="10"),
        _candidate(
            family=MarketNeutralFamily.FUNDING_CAPTURE,
            long_leg=spot,
            short_leg=perp,
            risk=_risk(funding_benefit="40", funding_stress="20"),
        ),
    )

    assert result.status is MarketNeutralStatus.HOLD_RISK_GATE
    assert "funding_change_stress_above_policy_limit" in result.reason_codes


def test_transfer_constraints_fail_closed_without_being_hidden_in_edge() -> None:
    missing_delay = evaluate_market_neutral_candidate(
        _policy(),
        _candidate(
            risk=_risk(
                transfer_required=True,
                transfer_cost="3",
                transfer_delay_ms=None,
            )
        ),
    )
    assert missing_delay.status is MarketNeutralStatus.NOT_EVALUABLE
    assert "transfer_delay_unavailable" in missing_delay.reason_codes

    too_slow = evaluate_market_neutral_candidate(
        _policy(),
        _candidate(
            risk=_risk(
                transfer_required=True,
                transfer_cost="3",
                transfer_delay_ms=31_000,
            )
        ),
    )
    assert too_slow.status is MarketNeutralStatus.HOLD_RISK_GATE
    assert "transfer_delay_above_policy_limit" in too_slow.reason_codes
    assert too_slow.transfer_cost_bps == Decimal(3)


@pytest.mark.parametrize(
    ("risk_kwargs", "reason"),
    [
        ({"latency_ms": 501}, "execution_latency_above_policy_limit"),
        ({"long_counterparty": "0.41"}, "counterparty_risk_above_policy_limit"),
        ({"hedge_mismatch": "0.06"}, "hedge_mismatch_above_policy_limit"),
    ],
)
def test_latency_counterparty_and_hedge_risks_are_explicit_vetoes(
    risk_kwargs: dict[str, object],
    reason: str,
) -> None:
    result = evaluate_market_neutral_candidate(
        _policy(),
        _candidate(risk=_risk(**risk_kwargs)),
    )
    assert result.status is MarketNeutralStatus.HOLD_RISK_GATE
    assert reason in result.reason_codes


def test_family_structure_is_explicit_and_not_silently_coerced() -> None:
    same_venue_long = _leg(
        exchange=Exchange.BINANCE,
        instrument=NeutralInstrumentType.SPOT,
        bid="99",
        ask="100",
        seed="same-venue-long",
    )
    same_venue_short = _leg(
        exchange=Exchange.BINANCE,
        instrument=NeutralInstrumentType.SPOT,
        bid="102",
        ask="103",
        seed="same-venue-short",
    )
    with pytest.raises(ValueError, match="distinct exchanges"):
        _candidate(
            family=MarketNeutralFamily.CROSS_EXCHANGE_SPREAD,
            long_leg=same_venue_long,
            short_leg=same_venue_short,
        )

    with pytest.raises(ValueError, match="one spot and one perpetual"):
        _candidate(
            family=MarketNeutralFamily.SPOT_PERPETUAL_BASIS,
            long_leg=same_venue_long,
            short_leg=same_venue_short,
        )

    with pytest.raises(ValueError, match="perpetual hedge leg"):
        _candidate(
            family=MarketNeutralFamily.DELTA_NEUTRAL,
            long_leg=same_venue_long,
            short_leg=same_venue_short,
        )


def test_future_leg_and_identity_tampering_fail_closed() -> None:
    future = _leg(
        exchange=Exchange.BINANCE,
        instrument=NeutralInstrumentType.SPOT,
        bid="99",
        ask="100",
        observed_at_ms=AS_OF + 1,
        market_available_at_ms=AS_OF,
        seed="future",
    )
    with pytest.raises(ValueError, match="future leg evidence"):
        _candidate(long_leg=future)

    candidate = _candidate()
    result = evaluate_market_neutral_candidate(_policy(), candidate)
    with pytest.raises(ValueError, match="candidate identity mismatch"):
        replace(candidate, candidate_identity="f" * 64)
    with pytest.raises(ValueError, match="assessment identity mismatch"):
        replace(result, net_edge_bps=Decimal("999"))


def test_policy_thresholds_are_versioned_inputs_not_embedded_market_truth() -> None:
    permissive = evaluate_market_neutral_candidate(
        _policy(min_edge="5"),
        _candidate(),
    )
    strict = evaluate_market_neutral_candidate(
        _policy(min_edge="500"),
        _candidate(),
    )

    assert permissive.status is MarketNeutralStatus.ELIGIBLE_SHADOW
    assert strict.status is MarketNeutralStatus.HOLD_NO_NET_EDGE
    assert permissive.net_edge_bps == strict.net_edge_bps


def test_market_neutral_research_has_no_execution_or_canonical_mutation_surface() -> None:
    source = inspect.getsource(market_neutral_research).lower()
    forbidden = (
        "sqlite3",
        "paperfundledger",
        "append_",
        "write_text",
        "write_bytes",
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "simulate_paper_fill",
        "commit_orchestration_bundle",
        "def promote",
        "launchctl",
        "subprocess",
        "risk-free",
        "risk free",
    )
    assert all(token not in source for token in forbidden)
    assert market_neutral_research.REAL_CAPITAL == 0
