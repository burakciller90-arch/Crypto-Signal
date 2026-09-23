from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.exchange_flows import build_exchange_flow_observation
from crypto_signal.data.models import DataSource
from crypto_signal.intelligence.exchange_flow import (
    ExchangeFlowConfig,
    ExchangeFlowLabel,
    ExchangeFlowStatus,
    NetflowDirection,
    analyze_exchange_flow,
    build_exchange_flow_evidence_freeze,
)

_HOUR_MS = 3_600_000
_BASE_END = 100_000_000
_AS_OF = _BASE_END + 100


def _flow(
    index: int,
    *,
    inflow: str,
    outflow: str,
    asset: str = "BTC",
    exchange_scope: str = "all_exchanges",
    source_provider: str = "test-provider",
    attribution_method: str = "provider-labeled-clusters/v1",
    window_end_ms: int | None = None,
    ingested_at_ms: int | None = None,
):
    end_ms = (
        _BASE_END - (4 - index) * _HOUR_MS
        if window_end_ms is None
        else window_end_ms
    )
    start_ms = end_ms - _HOUR_MS
    source_ms = end_ms + 10
    ingest_ms = source_ms + 10 if ingested_at_ms is None else ingested_at_ms
    return build_exchange_flow_observation(
        asset=asset,
        exchange_scope=exchange_scope,
        window_start_ms=start_ms,
        window_end_ms=end_ms,
        inflow_amount=Decimal(inflow),
        outflow_amount=Decimal(outflow),
        source_provider=source_provider,
        attribution_method=attribution_method,
        source=DataSource.AGGREGATED,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingest_ms,
        adapter_version="exchange-flow-test/1",
    )


def _series(
    inflows: tuple[str, ...],
    outflows: tuple[str, ...],
):
    return tuple(
        _flow(index, inflow=inflow, outflow=outflow)
        for index, (inflow, outflow) in enumerate(zip(inflows, outflows, strict=True))
    )


def test_observation_identity_and_flow_arithmetic_are_deterministic() -> None:
    first = _flow(4, inflow="30", outflow="10")
    second = _flow(4, inflow="30", outflow="10")

    assert first == second
    assert first.netflow_amount == Decimal(20)
    assert first.gross_flow_amount == Decimal(40)
    assert first.window_duration_ms == _HOUR_MS
    assert len(first.observation_identity) == 64


def test_inflow_anomaly_is_pit_frozen_context_not_price_direction() -> None:
    observations = _series(
        ("10", "12", "14", "16", "30"),
        ("30", "25", "20", "15", "10"),
    )
    first = build_exchange_flow_evidence_freeze(observations, as_of_ms=_AS_OF)
    second = build_exchange_flow_evidence_freeze(
        tuple(reversed(observations)),
        as_of_ms=_AS_OF,
    )

    assert first == second
    analysis = first.analysis
    assert analysis.status is ExchangeFlowStatus.MEASURED
    assert analysis.label is ExchangeFlowLabel.INFLOW_ANOMALY
    assert analysis.netflow_direction is NetflowDirection.TO_EXCHANGES
    assert analysis.metrics is not None
    assert analysis.metrics.latest_netflow_amount == Decimal(20)
    assert analysis.metrics.inflow_rate_percentile_0_1 == Decimal(1)
    assert analysis.metrics.outflow_rate_percentile_0_1 == Decimal(1) / Decimal(5)
    assert analysis.metrics.netflow_rate_velocity_per_hour == Decimal(19)
    assert "exchange_flow_context_is_not_price_direction" in analysis.uncertainty_flags
    assert len(first.freeze_identity) == 64


def test_outflow_anomaly_is_symmetric_without_sell_claim() -> None:
    analysis = analyze_exchange_flow(
        _series(
            ("30", "25", "20", "15", "10"),
            ("10", "12", "14", "16", "30"),
        ),
        as_of_ms=_AS_OF,
    )

    assert analysis.label is ExchangeFlowLabel.OUTFLOW_ANOMALY
    assert analysis.netflow_direction is NetflowDirection.FROM_EXCHANGES
    assert analysis.metrics is not None
    assert analysis.metrics.latest_netflow_amount == Decimal(-20)
    assert analysis.metrics.outflow_rate_percentile_0_1 == Decimal(1)


def test_balanced_and_simultaneous_extremes_remain_distinct() -> None:
    balanced = analyze_exchange_flow(
        _series(
            ("5", "30", "20", "10", "15"),
            ("6", "28", "19", "11", "15"),
        ),
        as_of_ms=_AS_OF,
    )
    simultaneous = analyze_exchange_flow(
        _series(
            ("10", "12", "14", "16", "30"),
            ("10", "12", "14", "16", "30"),
        ),
        as_of_ms=_AS_OF,
    )

    assert balanced.label is ExchangeFlowLabel.BALANCED
    assert balanced.netflow_direction is NetflowDirection.BALANCED
    assert simultaneous.label is ExchangeFlowLabel.MIXED
    assert (
        "simultaneous_inflow_outflow_extremes"
        in simultaneous.uncertainty_flags
    )


def test_insufficient_or_stale_history_fails_closed() -> None:
    observations = _series(
        ("10", "12", "14", "16", "30"),
        ("30", "25", "20", "15", "10"),
    )
    insufficient = analyze_exchange_flow(
        observations[:4],
        as_of_ms=observations[3].ingested_at_ms,
    )
    stale = analyze_exchange_flow(
        observations,
        as_of_ms=_BASE_END + 7 * _HOUR_MS,
    )

    assert insufficient.status is ExchangeFlowStatus.UNRESOLVED
    assert insufficient.metrics is None
    assert "insufficient_exchange_flow_history" in insufficient.uncertainty_flags
    assert stale.status is ExchangeFlowStatus.UNRESOLVED
    assert stale.metrics is None
    assert "stale_exchange_flow_observation" in stale.uncertainty_flags


def test_future_or_late_ingestion_cannot_rewrite_historical_freeze() -> None:
    observations = _series(
        ("10", "12", "14", "16", "30"),
        ("30", "25", "20", "15", "10"),
    )
    baseline = build_exchange_flow_evidence_freeze(observations, as_of_ms=_AS_OF)
    future = _flow(
        5,
        inflow="999",
        outflow="1",
        window_end_ms=_AS_OF + 1_000,
    )
    late = _flow(
        5,
        inflow="1",
        outflow="999",
        window_end_ms=_BASE_END - _HOUR_MS // 2,
        ingested_at_ms=_AS_OF + 1,
    )
    changed = build_exchange_flow_evidence_freeze(
        (*observations, future, late),
        as_of_ms=_AS_OF,
    )

    assert changed == baseline
    assert future not in changed.observations
    assert late not in changed.observations


def test_no_pit_eligible_observation_is_unresolved_without_metrics() -> None:
    future = _flow(
        5,
        inflow="100",
        outflow="10",
        window_end_ms=_AS_OF + 1_000,
    )
    result = analyze_exchange_flow((future,), as_of_ms=_AS_OF)

    assert result.status is ExchangeFlowStatus.UNRESOLVED
    assert result.label is ExchangeFlowLabel.UNRESOLVED
    assert result.netflow_direction is NetflowDirection.UNAVAILABLE
    assert result.metrics is None
    assert result.consumed_observation_count == 0
    assert result.uncertainty_flags == ("exchange_flow_unavailable_at_as_of",)


def test_context_duplicates_tampering_and_invalid_config_fail_closed() -> None:
    observations = _series(
        ("10", "12", "14", "16", "30"),
        ("30", "25", "20", "15", "10"),
    )
    eth = _flow(5, inflow="5", outflow="5", asset="ETH")
    with pytest.raises(ValueError, match="exact source context"):
        analyze_exchange_flow((*observations, eth), as_of_ms=_AS_OF)

    with pytest.raises(ValueError, match="duplicate exchange-flow observation identity"):
        analyze_exchange_flow(
            (*observations, observations[-1]),
            as_of_ms=_AS_OF,
        )

    same_end = _flow(
        9,
        inflow="31",
        outflow="9",
        window_end_ms=observations[-1].window_end_ms,
    )
    with pytest.raises(ValueError, match="unique window ends"):
        analyze_exchange_flow((*observations, same_end), as_of_ms=_AS_OF)

    freeze = build_exchange_flow_evidence_freeze(observations, as_of_ms=_AS_OF)
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)

    with pytest.raises(ValueError, match="counts"):
        ExchangeFlowConfig(lookback_observations=4, minimum_observations=5)
    with pytest.raises(ValueError, match="anomaly percentile"):
        ExchangeFlowConfig(anomaly_percentile=Decimal("0.50"))
    with pytest.raises(ValueError, match="balanced netflow fraction"):
        ExchangeFlowConfig(balanced_netflow_fraction_of_gross=Decimal(1))
