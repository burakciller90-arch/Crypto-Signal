from __future__ import annotations

from decimal import Decimal

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.intelligence.derivatives_context import (
    build_derivatives_context_evidence_freeze,
)
from crypto_signal.intelligence.derivatives_dynamics import (
    DerivativesDynamicsStatus,
    build_derivatives_dynamics_evidence_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_family_sources import (
    build_market_tape_family_snapshots,
)

AS_OF_MS = 200_000


def _observation(
    event_at_ms: int,
    *,
    funding: str | None,
    open_interest: str | None,
    mark: str | None,
    index: str | None,
    ingested_at_ms: int | None = None,
):
    return build_derivatives_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        event_at_ms=event_at_ms,
        funding_rate=None if funding is None else Decimal(funding),
        open_interest=(
            None if open_interest is None else Decimal(open_interest)
        ),
        mark_price=None if mark is None else Decimal(mark),
        index_price=None if index is None else Decimal(index),
        funding_interval_hours=8 if funding is not None else None,
        source=DataSource.REST,
        source_timestamp_ms=event_at_ms,
        ingested_at_ms=(
            event_at_ms if ingested_at_ms is None else ingested_at_ms
        ),
        adapter_version="rdp5-derivatives-dynamics-test/1",
    )


def _history():
    return (
        _observation(
            180_000,
            funding="-0.0002",
            open_interest="100",
            mark="100",
            index="100",
        ),
        _observation(
            190_000,
            funding="0",
            open_interest="104",
            mark="101",
            index="100.5",
        ),
        _observation(
            200_000,
            funding="0.0004",
            open_interest="110",
            mark="103",
            index="101",
        ),
    )


def _derivatives_snapshot(path):
    snapshots = build_market_tape_family_snapshots(
        path,
        symbols=("BTCUSDT",),
        as_of_ms=AS_OF_MS,
    )
    matches = [
        item
        for item in snapshots
        if item.family is ConfluenceFamily.DERIVATIVES
    ]
    assert len(matches) == 1
    return matches[0]


def test_live_derivatives_family_includes_exact_dynamics_freeze(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    for item in _history():
        store.append_derivatives(item)

    snapshot = _derivatives_snapshot(path)
    observations = store.recent_derivatives(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        limit=64,
    )
    context = build_derivatives_context_evidence_freeze(
        observations,
        as_of_ms=AS_OF_MS,
    )
    dynamics = build_derivatives_dynamics_evidence_freeze(
        observations,
        as_of_ms=AS_OF_MS,
    )

    assert dynamics.analysis.status is DerivativesDynamicsStatus.MEASURED
    assert {
        context.freeze_identity,
        context.analysis.evidence_identity,
        dynamics.freeze_identity,
        dynamics.analysis.evidence_identity,
        *(item.observation_identity for item in dynamics.observations),
    }.issubset(set(snapshot.evidence_identities))
    assert {
        "derivatives",
        "derivatives_context",
        "derivatives_dynamics",
    }.issubset(set(snapshot.evidence_domains))
    assert snapshot.source_event_identity == canonical_sha256(
        {
            "as_of_ms": AS_OF_MS,
            "context_freeze_identity": context.freeze_identity,
            "dynamics_freeze_identity": dynamics.freeze_identity,
            "symbol": "BTCUSDT",
            "version": "rdp5-derivatives-dynamics-family-v1/1",
        }
    )
    components = {
        item.name: item.value for item in snapshot.state_components
    }
    assert components["dynamics_status"] == "measured"
    assert components["dynamics_oi_price_state"] == "price_up_oi_up"
    assert Decimal(components["funding_percentile_0_1"]) == Decimal("1")
    assert Decimal(components["funding_acceleration_bps"]) == Decimal("4")
    assert Decimal(components["open_interest_change_fraction"]) == Decimal("0.10")
    assert Decimal(components["mark_price_change_fraction"]) == Decimal("0.03")
    assert snapshot.direction is None
    assert snapshot.source_quality == "measured"


def test_future_and_late_derivatives_do_not_rewrite_family_pit(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    for item in _history():
        store.append_derivatives(item)
    baseline = _derivatives_snapshot(path)

    store.append_derivatives(
        _observation(
            201_000,
            funding="0.02",
            open_interest="1000",
            mark="140",
            index="100",
        )
    )
    store.append_derivatives(
        _observation(
            195_000,
            funding="-0.02",
            open_interest="1",
            mark="70",
            index="100",
            ingested_at_ms=AS_OF_MS + 1,
        )
    )

    assert _derivatives_snapshot(path) == baseline


def test_insufficient_dynamics_fail_closed_without_direction(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    for event_at_ms, funding in (
        (190_000, "0.0001"),
        (200_000, "0.0002"),
    ):
        store.append_derivatives(
            _observation(
                event_at_ms,
                funding=funding,
                open_interest=None,
                mark=None,
                index=None,
            )
        )

    snapshot = _derivatives_snapshot(path)
    components = {
        item.name: item.value for item in snapshot.state_components
    }
    assert components["dynamics_status"] == "unresolved"
    assert components["dynamics_oi_price_state"] == "unavailable"
    assert snapshot.source_quality == "unresolved"
    assert snapshot.direction is None
    assert "insufficient_derivatives_components" in snapshot.uncertainty_flags
