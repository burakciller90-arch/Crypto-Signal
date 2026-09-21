from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.models import DataSource, Exchange


def _observation(**overrides):
    payload = {
        "exchange": Exchange.BYBIT,
        "instrument_type": DerivativesInstrumentType.LINEAR_PERPETUAL,
        "symbol": "BTCUSDT",
        "event_at_ms": 1_000,
        "funding_rate": Decimal("0.0001"),
        "open_interest": Decimal(100),
        "mark_price": Decimal(101),
        "index_price": Decimal(100),
        "funding_interval_hours": 8,
        "source": DataSource.REST,
        "source_timestamp_ms": 1_000,
        "ingested_at_ms": 1_000,
        "adapter_version": "test/1",
    }
    payload.update(overrides)
    return build_derivatives_observation(**payload)


def test_derivatives_observation_identity_is_deterministic() -> None:
    first = _observation()
    second = _observation()

    assert first == second
    assert len(first.observation_identity) == 64
    assert first.instrument_type is DerivativesInstrumentType.LINEAR_PERPETUAL


def test_derivatives_observation_identity_tampering_fails_closed() -> None:
    observation = _observation()

    with pytest.raises(ValueError, match="identity mismatch"):
        replace(observation, observation_identity="f" * 64)


def test_mark_and_index_must_appear_together() -> None:
    with pytest.raises(ValueError, match="must appear together"):
        _observation(index_price=None)


def test_negative_open_interest_is_rejected() -> None:
    with pytest.raises(ValueError, match="open_interest cannot be negative"):
        _observation(open_interest=Decimal(-1))


def test_observation_requires_real_measurement() -> None:
    with pytest.raises(ValueError, match="at least one measurement"):
        _observation(
            funding_rate=None,
            open_interest=None,
            mark_price=None,
            index_price=None,
            funding_interval_hours=None,
        )


def test_event_cannot_postdate_source_timestamp() -> None:
    with pytest.raises(ValueError, match="cannot postdate"):
        _observation(event_at_ms=2_000, source_timestamp_ms=1_000)
