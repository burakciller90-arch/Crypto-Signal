from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.intelligence.derivatives_dynamics import (
    DerivativesDynamicsConfig,
    DerivativesDynamicsStatus,
    OiPriceState,
    analyze_derivatives_dynamics,
    build_derivatives_dynamics_evidence_freeze,
)


def obs(t: int, *, funding=None, oi=None, mark=None, index=None, ingested=None, symbol="BTCUSDT"):
    return build_derivatives_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=symbol,
        event_at_ms=t,
        funding_rate=funding,
        open_interest=oi,
        mark_price=mark,
        index_price=index,
        funding_interval_hours=8 if funding is not None else None,
        source=DataSource.REST,
        source_timestamp_ms=t,
        ingested_at_ms=t if ingested is None else ingested,
        adapter_version="m4-test/1",
    )


def history():
    return (
        obs(1000, funding=Decimal("-0.0002"), oi=Decimal(100), mark=Decimal(100), index=Decimal(100)),
        obs(2000, funding=Decimal(0), oi=Decimal(104), mark=Decimal(101), index=Decimal("100.5")),
        obs(3000, funding=Decimal("0.0004"), oi=Decimal(110), mark=Decimal(103), index=Decimal(101)),
    )


def test_temporal_state_funding_basis_and_deterministic_freeze() -> None:
    first = build_derivatives_dynamics_evidence_freeze(history(), as_of_ms=3000)
    second = build_derivatives_dynamics_evidence_freeze(tuple(reversed(history())), as_of_ms=3000)
    assert first == second
    assert first.analysis.status is DerivativesDynamicsStatus.MEASURED
    assert first.analysis.oi_price_state is OiPriceState.PRICE_UP_OI_UP
    m = first.analysis.metrics
    assert m is not None
    assert m.latest_funding_bps == Decimal(4)
    assert m.funding_percentile_0_1 == Decimal(1)
    assert m.funding_acceleration_bps == Decimal(4)
    assert m.open_interest_change_fraction == Decimal("0.10")
    assert m.mark_price_change_fraction == Decimal("0.03")
    assert m.latest_basis_bps is not None and m.latest_basis_bps > 0
    assert m.basis_change_bps is not None and m.basis_change_bps > 0
    assert m.available_component_count == 3


def test_price_flat_oi_expanding_and_observed_funding_rank() -> None:
    data = (
        obs(1000, funding=Decimal("0.001"), oi=Decimal(100), mark=Decimal(100), index=Decimal(100)),
        obs(2000, funding=Decimal("0.003"), oi=Decimal(105), mark=Decimal("100.05"), index=Decimal(100)),
        obs(3000, funding=Decimal("0.002"), oi=Decimal(110), mark=Decimal("100.10"), index=Decimal(100)),
    )
    result = analyze_derivatives_dynamics(
        data,
        as_of_ms=3000,
        config=DerivativesDynamicsConfig(),
    )
    assert result.oi_price_state is OiPriceState.PRICE_FLAT_OI_EXPANDING
    assert result.metrics is not None
    assert result.metrics.funding_percentile_0_1 == Decimal(2) / Decimal(3)
    assert result.metrics.funding_acceleration_bps == Decimal(-10)


def test_future_and_late_evidence_do_not_rewrite_historical_freeze() -> None:
    baseline = build_derivatives_dynamics_evidence_freeze(history(), as_of_ms=3000)
    future = obs(3100, funding=Decimal("0.01"), oi=Decimal(1000), mark=Decimal(130), index=Decimal(100))
    late = obs(2500, funding=Decimal("-0.01"), oi=Decimal(1), mark=Decimal(70), index=Decimal(100), ingested=4000)
    changed = build_derivatives_dynamics_evidence_freeze((*history(), future, late), as_of_ms=3000)
    assert changed == baseline
    assert future not in changed.observations
    assert late not in changed.observations


def test_partial_stale_context_and_tampering_fail_closed() -> None:
    partial = analyze_derivatives_dynamics(
        (obs(1000, oi=Decimal(100)), obs(2000, oi=Decimal(110))),
        as_of_ms=2000,
    )
    assert partial.status is DerivativesDynamicsStatus.UNRESOLVED
    assert partial.metrics is None
    assert "insufficient_derivatives_components" in partial.uncertainty_flags

    stale = analyze_derivatives_dynamics(history(), as_of_ms=3000 + 31 * 60_000)
    assert stale.status is DerivativesDynamicsStatus.UNRESOLVED
    assert stale.uncertainty_flags == ("stale_derivatives_observation",)

    freeze = build_derivatives_dynamics_evidence_freeze(history(), as_of_ms=3000)
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_mixed_context_is_rejected() -> None:
    eth = obs(4000, funding=Decimal(0), oi=Decimal(100), mark=Decimal(100), index=Decimal(100), symbol="ETHUSDT")
    with pytest.raises(ValueError, match="context mismatch"):
        analyze_derivatives_dynamics((*history(), eth), as_of_ms=4000)
