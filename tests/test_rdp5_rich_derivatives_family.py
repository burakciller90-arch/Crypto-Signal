from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.liquidation_runtime import (
    LiquidationConnectionRuntimeStore,
    LiquidationConnectionState,
    build_liquidation_connection_coverage,
)
from crypto_signal.data.liquidations import (
    LiquidatedPositionSide,
    build_liquidation_observation,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_collector_runtime import (
    MarketTapeCollectorRuntimeStore,
    build_collector_instance,
)
from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.product.intelligence_stream_family_sources import (
    build_market_tape_family_snapshots,
)

AS_OF_MS = 2_000_000
CONNECTION_AS_OF_MS = AS_OF_MS - 1_000
SYMBOL = "BTCUSDT"


def _derivative(
    *,
    index: int,
    event_at_ms: int,
    open_interest: str,
    mark_price: str,
    funding_rate: str,
):
    return build_derivatives_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=SYMBOL,
        event_at_ms=event_at_ms,
        funding_rate=Decimal(funding_rate),
        open_interest=Decimal(open_interest),
        mark_price=Decimal(mark_price),
        index_price=Decimal("100"),
        funding_interval_hours=8,
        source=DataSource.REST,
        source_timestamp_ms=event_at_ms + 1,
        ingested_at_ms=event_at_ms + 2,
        adapter_version=f"rdp5-rich-derivatives-test/{index}",
    )


def _seed_derivatives(store: MarketTapeStore) -> None:
    rows = (
        (1, CONNECTION_AS_OF_MS - 240_000, "100", "100.00", "0.00008"),
        (2, CONNECTION_AS_OF_MS - 180_000, "100.5", "100.02", "0.00009"),
        (3, CONNECTION_AS_OF_MS - 120_000, "101", "100.04", "0.00010"),
        (4, CONNECTION_AS_OF_MS - 60_000, "101.5", "100.06", "0.00009"),
        (5, CONNECTION_AS_OF_MS - 10_000, "102", "100.08", "0.00010"),
    )
    for index, event_at_ms, oi, mark, funding in rows:
        store.append_derivatives(
            _derivative(
                index=index,
                event_at_ms=event_at_ms,
                open_interest=oi,
                mark_price=mark,
                funding_rate=funding,
            )
        )


def _runtime(
    path,
    *,
    state: LiquidationConnectionState = LiquidationConnectionState.CONNECTED,
    last_liquidation_ingestion_ms: int | None = None,
) -> None:
    runtime = MarketTapeCollectorRuntimeStore(path)
    instance = build_collector_instance(
        provider="bybit",
        source="liquidation_stream",
        symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        started_at_ms=CONNECTION_AS_OF_MS - 21 * 60_000,
        process_id=50401,
        runtime_nonce="rdp5-rich-derivatives",
    )
    runtime.append_instance(instance)

    connection = LiquidationConnectionRuntimeStore(path)
    if state is LiquidationConnectionState.CONNECTED:
        connected_since_ms = CONNECTION_AS_OF_MS - 20 * 60_000
        reason_codes = (
            "subscription_confirmed",
            "transport_activity_fresh",
        )
    else:
        connected_since_ms = None
        reason_codes = ("transport_disconnected",)
    connection.append(
        build_liquidation_connection_coverage(
            instance_identity=instance.instance_identity,
            sequence_no=1,
            state=state,
            observed_at_ms=CONNECTION_AS_OF_MS,
            connected_since_ms=connected_since_ms,
            last_transport_activity_ms=CONNECTION_AS_OF_MS - 1_000,
            last_liquidation_ingestion_ms=last_liquidation_ingestion_ms,
            symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
            reason_codes=reason_codes,
        )
    )


def _derivatives_snapshot(market_path, runtime_path):
    snapshots = build_market_tape_family_snapshots(
        market_path,
        symbols=(SYMBOL,),
        as_of_ms=AS_OF_MS,
        liquidation_runtime_path=runtime_path,
    )
    return next(
        item
        for item in snapshots
        if item.family is ConfluenceFamily.DERIVATIVES
    )


def _components(snapshot) -> dict[str, str]:
    return {
        item.name: item.value
        for item in snapshot.state_components
    }


def test_connected_zero_event_window_is_measured_without_market_tape_coverage(
    tmp_path,
) -> None:
    market_path = tmp_path / "market_tape.sqlite3"
    runtime_path = tmp_path / "liquidation_collector_runtime.sqlite3"
    store = MarketTapeStore(market_path)
    _seed_derivatives(store)
    _runtime(runtime_path)

    before = store.counts()
    snapshot = _derivatives_snapshot(market_path, runtime_path)
    after = store.counts()
    components = _components(snapshot)

    assert before.liquidations == 0
    assert before.liquidation_coverage == 0
    assert after.liquidations == 0
    assert after.liquidation_coverage == 0
    assert components["dynamics_status"] == "measured"
    assert components["liquidation_connection_state"] == "connected"
    assert components["liquidation_heatmap_status"] == "measured"
    assert components["liquidation_observed_state"] == "none_observed"
    assert components["liquidation_event_count"] == "0"
    assert components["liquidation_risk_zone_status"] == "not_estimated"
    assert components["crowding_status"] == "measured"
    assert components["crowding_label"] == "balanced"
    assert {
        "derivatives",
        "derivatives_context",
        "derivatives_dynamics",
        "derivatives_crowding",
        "liquidation_transport_coverage",
        "observed_liquidation_heatmap",
    }.issubset(set(snapshot.evidence_domains))
    assert snapshot.direction is None
    assert snapshot.source_as_of_ms == CONNECTION_AS_OF_MS


def test_observed_liquidation_enters_heatmap_and_crowding_without_direction(
    tmp_path,
) -> None:
    market_path = tmp_path / "market_tape.sqlite3"
    runtime_path = tmp_path / "liquidation_collector_runtime.sqlite3"
    store = MarketTapeStore(market_path)
    _seed_derivatives(store)
    event_at_ms = CONNECTION_AS_OF_MS - 30_000
    event = build_liquidation_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=SYMBOL,
        liquidated_position_side=LiquidatedPositionSide.LONG,
        size=Decimal("2"),
        bankruptcy_price=Decimal("99.8"),
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms + 10,
        ingested_at_ms=event_at_ms + 20,
        source_row_index=0,
        source=DataSource.WEBSOCKET,
        adapter_version="rdp5-rich-derivatives-liquidation-test/1",
    )
    store.append_liquidation(event)
    _runtime(
        runtime_path,
        last_liquidation_ingestion_ms=event.ingested_at_ms,
    )

    snapshot = _derivatives_snapshot(market_path, runtime_path)
    components = _components(snapshot)

    assert components["liquidation_heatmap_status"] == "measured"
    assert components["liquidation_observed_state"] == "observed"
    assert components["liquidation_event_count"] == "1"
    assert components["crowding_status"] == "measured"
    assert event.liquidation_identity in snapshot.evidence_identities
    assert snapshot.direction is None
    assert store.counts().liquidation_coverage == 0


def test_disconnected_runtime_fails_closed_without_heatmap_or_crowding(
    tmp_path,
) -> None:
    market_path = tmp_path / "market_tape.sqlite3"
    runtime_path = tmp_path / "liquidation_collector_runtime.sqlite3"
    store = MarketTapeStore(market_path)
    _seed_derivatives(store)
    _runtime(
        runtime_path,
        state=LiquidationConnectionState.DISCONNECTED,
    )

    snapshot = _derivatives_snapshot(market_path, runtime_path)
    components = _components(snapshot)

    assert components["dynamics_status"] == "measured"
    assert components["liquidation_connection_state"] == "disconnected"
    assert "liquidation_heatmap_status" not in components
    assert "crowding_status" not in components
    assert "observed_liquidation_heatmap" not in snapshot.evidence_domains
    assert "derivatives_crowding" not in snapshot.evidence_domains
    assert (
        "liquidation_transport_window_unavailable"
        in snapshot.uncertainty_flags
    )
    assert snapshot.direction is None


def test_rdp5_rich_derivatives_source_never_claims_future_liquidation_map(
) -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "crypto_signal"
        / "product"
        / "intelligence_stream_family_sources.py"
    ).read_text(encoding="utf-8").lower()
    assert "future liquidation target" not in text
    assert "predicted liquidation" not in text
    assert "dealer liquidation map" not in text
    assert "liquidation_risk_zone_status" in text
