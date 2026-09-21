from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.models import MethodologyKind
from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.intelligence.derivatives_context import (
    DERIVATIVES_CONTEXT_ENGINE_VERSION,
    DERIVATIVES_CONTEXT_FREEZE_SCHEMA_VERSION,
    BasisState,
    DerivativesContextConfig,
    DerivativesContextLabel,
    FundingState,
    OpenInterestState,
    analyze_derivatives_context,
    build_derivatives_context_evidence_freeze,
)


def _observation(
    *,
    event_at_ms: int,
    funding_rate: Decimal | None = None,
    open_interest: Decimal | None = None,
    mark_price: Decimal | None = None,
    index_price: Decimal | None = None,
    exchange: Exchange = Exchange.BYBIT,
    symbol: str = "BTCUSDT",
    source_timestamp_ms: int | None = None,
    ingested_at_ms: int | None = None,
):
    source_ms = (
        event_at_ms if source_timestamp_ms is None else source_timestamp_ms
    )
    ingested_ms = event_at_ms if ingested_at_ms is None else ingested_at_ms
    return build_derivatives_observation(
        exchange=exchange,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=symbol,
        event_at_ms=event_at_ms,
        funding_rate=funding_rate,
        open_interest=open_interest,
        mark_price=mark_price,
        index_price=index_price,
        funding_interval_hours=8 if funding_rate is not None else None,
        source=DataSource.REST,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingested_ms,
        adapter_version="derivatives-context-test/1",
    )


def _crowded_long_observations():
    return (
        _observation(event_at_ms=1_000, open_interest=Decimal(100)),
        _observation(event_at_ms=2_000, open_interest=Decimal(110)),
        _observation(
            event_at_ms=3_000,
            funding_rate=Decimal("0.001"),
            open_interest=Decimal(115),
            mark_price=Decimal(101),
            index_price=Decimal(100),
        ),
    )


def test_crowded_long_is_deterministic_and_frozen() -> None:
    observations = _crowded_long_observations()

    first = build_derivatives_context_evidence_freeze(
        observations,
        as_of_ms=3_000,
    )
    second = build_derivatives_context_evidence_freeze(
        tuple(reversed(observations)),
        as_of_ms=3_000,
    )

    assert first == second
    assert first.schema_version == DERIVATIVES_CONTEXT_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == DERIVATIVES_CONTEXT_ENGINE_VERSION
    assert first.analysis.label is DerivativesContextLabel.CROWDED_LONG
    assert first.analysis.funding_state is FundingState.POSITIVE_EXTREME
    assert first.analysis.open_interest_state is OpenInterestState.RISING
    assert first.analysis.basis_state is BasisState.PREMIUM
    assert first.analysis.metrics is not None
    assert first.analysis.metrics.funding_rate_bps == Decimal(10)
    assert first.analysis.metrics.open_interest_change_fraction == Decimal("0.15")
    assert first.analysis.metrics.basis_bps == Decimal(100)
    assert first.analysis.metrics.available_component_count == 3
    assert first.analysis.uncertainty_flags == ()
    assert len(first.freeze_identity) == 64
    assert len(first.analysis.evidence_identity) == 64


def test_crowded_short_requires_negative_funding_discount_and_rising_oi() -> None:
    observations = (
        _observation(event_at_ms=1_000, open_interest=Decimal(100)),
        _observation(event_at_ms=2_000, open_interest=Decimal(110)),
        _observation(
            event_at_ms=3_000,
            funding_rate=Decimal("-0.001"),
            open_interest=Decimal(115),
            mark_price=Decimal(99),
            index_price=Decimal(100),
        ),
    )

    result = analyze_derivatives_context(observations, as_of_ms=3_000)

    assert result.label is DerivativesContextLabel.CROWDED_SHORT
    assert result.funding_state is FundingState.NEGATIVE_EXTREME
    assert result.open_interest_state is OpenInterestState.RISING
    assert result.basis_state is BasisState.DISCOUNT


def test_falling_open_interest_is_deleveraging() -> None:
    observations = (
        _observation(event_at_ms=1_000, open_interest=Decimal(100)),
        _observation(
            event_at_ms=2_000,
            funding_rate=Decimal(0),
            open_interest=Decimal(90),
            mark_price=Decimal(100),
            index_price=Decimal(100),
        ),
    )

    result = analyze_derivatives_context(observations, as_of_ms=2_000)

    assert result.label is DerivativesContextLabel.DELEVERAGING
    assert result.open_interest_state is OpenInterestState.FALLING


def test_rising_oi_without_crowding_alignment_is_leverage_buildup() -> None:
    observations = (
        _observation(event_at_ms=1_000, open_interest=Decimal(100)),
        _observation(
            event_at_ms=2_000,
            funding_rate=Decimal(0),
            open_interest=Decimal(110),
            mark_price=Decimal(100),
            index_price=Decimal(100),
        ),
    )

    result = analyze_derivatives_context(observations, as_of_ms=2_000)

    assert result.label is DerivativesContextLabel.LEVERAGE_BUILDUP
    assert result.funding_state is FundingState.NEUTRAL
    assert result.open_interest_state is OpenInterestState.RISING
    assert result.basis_state is BasisState.NEUTRAL


def test_small_oi_change_neutral_funding_and_basis_is_balanced() -> None:
    observations = (
        _observation(event_at_ms=1_000, open_interest=Decimal(100)),
        _observation(
            event_at_ms=2_000,
            funding_rate=Decimal("0.0001"),
            open_interest=Decimal(102),
            mark_price=Decimal("100.1"),
            index_price=Decimal(100),
        ),
    )

    result = analyze_derivatives_context(observations, as_of_ms=2_000)

    assert result.label is DerivativesContextLabel.BALANCED
    assert result.funding_state is FundingState.NEUTRAL
    assert result.open_interest_state is OpenInterestState.STABLE
    assert result.basis_state is BasisState.NEUTRAL


def test_partial_two_component_context_is_mixed_with_uncertainty() -> None:
    observations = (
        _observation(
            event_at_ms=2_000,
            funding_rate=Decimal("0.001"),
            mark_price=Decimal(101),
            index_price=Decimal(100),
        ),
    )

    result = analyze_derivatives_context(observations, as_of_ms=2_000)

    assert result.label is DerivativesContextLabel.MIXED
    assert result.metrics is not None
    assert result.metrics.available_component_count == 2
    assert result.open_interest_state is OpenInterestState.UNAVAILABLE
    assert "open_interest_trend_unavailable" in result.uncertainty_flags
    assert (
        "component_disagreement_or_incomplete_alignment"
        in result.uncertainty_flags
    )


def test_one_component_is_unresolved_without_fabricated_metrics() -> None:
    observations = (
        _observation(
            event_at_ms=2_000,
            funding_rate=Decimal("0.001"),
        ),
    )

    result = analyze_derivatives_context(observations, as_of_ms=2_000)

    assert result.label is DerivativesContextLabel.UNRESOLVED
    assert result.metrics is None
    assert result.funding_state is FundingState.UNAVAILABLE
    assert result.open_interest_state is OpenInterestState.UNAVAILABLE
    assert result.basis_state is BasisState.UNAVAILABLE
    assert "insufficient_derivatives_components" in result.uncertainty_flags


def test_stale_context_is_unresolved() -> None:
    observations = _crowded_long_observations()
    stale_as_of = 3_000 + 31 * 60_000

    result = analyze_derivatives_context(
        observations,
        as_of_ms=stale_as_of,
    )

    assert result.label is DerivativesContextLabel.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("stale_derivatives_observation",)


def test_future_or_late_ingested_observation_cannot_change_pit_freeze() -> None:
    observations = _crowded_long_observations()
    baseline = build_derivatives_context_evidence_freeze(
        observations,
        as_of_ms=3_000,
    )
    late = _observation(
        event_at_ms=2_500,
        funding_rate=Decimal("-0.01"),
        open_interest=Decimal(1_000),
        mark_price=Decimal(80),
        index_price=Decimal(100),
        source_timestamp_ms=2_500,
        ingested_at_ms=4_000,
    )

    with_late = build_derivatives_context_evidence_freeze(
        (*observations, late),
        as_of_ms=3_000,
    )

    assert with_late == baseline
    assert late not in with_late.observations


def test_freeze_and_analysis_identity_tampering_fail_closed() -> None:
    freeze = build_derivatives_context_evidence_freeze(
        _crowded_long_observations(),
        as_of_ms=3_000,
    )

    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)

    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_mixed_context_is_rejected() -> None:
    observations = (
        _observation(event_at_ms=1_000, open_interest=Decimal(100)),
        _observation(
            event_at_ms=2_000,
            open_interest=Decimal(110),
            exchange=Exchange.BINANCE,
        ),
    )

    with pytest.raises(ValueError, match="context mismatch"):
        analyze_derivatives_context(observations, as_of_ms=2_000)


def test_invalid_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="minimum_components"):
        DerivativesContextConfig(minimum_components=4)


def test_stage8_derivatives_context_is_observation_only_ablation_zero() -> None:
    assert set(MethodologyKind) == {
        MethodologyKind.PRICE_ACTION,
        MethodologyKind.HARMONIC,
        MethodologyKind.ELLIOTT,
    }

    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/crypto_signal/confluence/models.py",
        "src/crypto_signal/confluence/adapters.py",
        "src/crypto_signal/ledger/bundle.py",
        "src/crypto_signal/signals/models.py",
    ):
        source = (root / relative).read_text()
        assert "crypto_signal.intelligence.derivatives_context" not in source
