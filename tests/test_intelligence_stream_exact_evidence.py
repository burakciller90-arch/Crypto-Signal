from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from test_immutable_ledger import build_bundle, candles
from test_rdp4_rich_market_tape_family import AS_OF_MS, _seed
from test_rdp5_derivatives_dynamics_family import (
    AS_OF_MS as DERIVATIVES_AS_OF_MS,
)
from test_rdp5_derivatives_dynamics_family import (
    _history as derivatives_history,
)

from crypto_signal.data.event_risk import (
    EventCategory,
    EventSourceQuality,
    build_event_calendar_coverage,
    build_structured_event_observation,
    event_calendar_coverage_payload,
    structured_event_payload,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.microstructure import OrderBookLevel, build_orderbook_snapshot
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.store import CandleStore
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.ledger.store import ImmutableSignalLedger
from crypto_signal.product.intelligence_stream_exact_evidence import (
    IntelligenceStreamExactEvidenceReadModel,
)
from crypto_signal.product.intelligence_stream_family import (
    StreamFamilySnapshot,
    StreamTrustDomain,
    build_family_snapshot,
)
from crypto_signal.product.intelligence_stream_family_sources import (
    build_geometry_family_snapshot,
    build_market_tape_family_snapshots,
)
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
)
from crypto_signal.product.intelligence_stream_models import (
    StreamCategory,
    StreamImportance,
)
from crypto_signal.product.intelligence_stream_production_projector import (
    IntelligenceStreamProductionProjector,
)
from crypto_signal.product.web import create_app


def _project_family(
    stream_path: Path,
    *,
    projector_id: str,
    snapshot: StreamFamilySnapshot,
) -> str:
    IntelligenceStreamForwardRuntime(stream_path).ensure_activated(
        activated_at_ms=1
    )
    projector = IntelligenceStreamProductionProjector(stream_path)
    projector.ensure_family_activation(projector_id, activated_at_ms=1)
    result = projector.project_family(snapshot, activated_at_ms=1)
    assert result.narrative_identity is not None
    return result.narrative_identity


def _resolution(payload: dict[str, object], domain: str) -> dict[str, object]:
    items = payload["resolutions"]
    assert isinstance(items, (list, tuple))
    found = next(
        item
        for item in items
        if isinstance(item, dict) and item.get("domain") == domain
    )
    return found


def test_geometry_exact_coordinates_are_ready_without_fake_chart(
    tmp_path: Path,
) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    evidence_identity = canonical_sha256({"evidence": "geometry"})
    source_identity = canonical_sha256({"source": "geometry"})
    snapshot = build_family_snapshot(
        projector_id="market_geometry_change",
        family=ConfluenceFamily.GEOMETRY,
        category=StreamCategory.MARKET,
        subtype="geometry_material_change",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=source_identity,
        source_scope="test:spot:signal_geometry",
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe="4h",
        event_at_ms=2_000,
        source_as_of_ms=1_900,
        evidence_identities=(evidence_identity,),
        evidence_domains=("frozen_chart", "geometry"),
        state_label="watch:long:geometry",
        state_components=(
            ("entry_zone_high", "101"),
            ("entry_zone_low", "99"),
            ("invalidation_price", "95"),
            ("target_01_target_1_price", "110"),
        ),
        direction="long",
        source_quality="exact_immutable_signal_freeze",
    )
    narrative_identity = _project_family(
        stream_path,
        projector_id="market_geometry_change",
        snapshot=snapshot,
    )

    payload = IntelligenceStreamExactEvidenceReadModel(
        stream_ledger_path=stream_path,
    ).read_for_narrative(narrative_identity)
    assert payload is not None
    assert _resolution(payload, "geometry")["resolution_state"] == "READY_EXACT"
    assert (
        _resolution(payload, "frozen_chart")["resolution_state"]
        == "IDENTITY_ONLY_EXACT"
    )
    references = payload["reference_resolutions"]
    assert isinstance(references, (list, tuple))
    assert references[0]["resolution_state"] == "IDENTITY_ONLY_EXACT"
    assert payload["current_data_substitution"] is False


def test_orderbook_identity_resolves_to_exact_persisted_object(
    tmp_path: Path,
) -> None:
    market_tape_path = tmp_path / "market_tape.sqlite3"
    stream_path = tmp_path / "stream.sqlite3"
    event_at_ms = 10_000
    snapshot = build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms,
        response_time_ms=event_at_ms,
        ingested_at_ms=event_at_ms,
        update_id=7,
        sequence=11,
        bids=(
            OrderBookLevel(price=Decimal(100), size=Decimal(2)),
            OrderBookLevel(price=Decimal(99), size=Decimal(3)),
        ),
        asks=(
            OrderBookLevel(price=Decimal(101), size=Decimal(4)),
            OrderBookLevel(price=Decimal(102), size=Decimal(5)),
        ),
        source=DataSource.REST,
        adapter_version="test-orderbook/1",
    )
    store = MarketTapeStore(market_tape_path)
    store.initialize()
    store.append_orderbook(snapshot)

    synthetic_identity = canonical_sha256({"evidence": "liquidity-analysis"})
    source_identity = canonical_sha256({"source": "liquidity"})
    family = build_family_snapshot(
        projector_id="liquidity_change",
        family=ConfluenceFamily.LIQUIDITY,
        category=StreamCategory.INTELLIGENCE,
        subtype="liquidity_material_change",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=source_identity,
        source_scope="bybit:spot:market_tape_liquidity",
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe="microstructure",
        event_at_ms=10_100,
        source_as_of_ms=10_100,
        evidence_identities=(snapshot.snapshot_identity, synthetic_identity),
        evidence_domains=("liquidity", "order_book"),
        state_label="measured:none",
        state_components=(
            ("liquidity_take_candidate", "none"),
            ("source_quality", "measured"),
            ("status", "measured"),
        ),
        direction=None,
        source_quality="measured",
    )
    narrative_identity = _project_family(
        stream_path,
        projector_id="liquidity_change",
        snapshot=family,
    )

    resolver = IntelligenceStreamExactEvidenceReadModel(
        stream_ledger_path=stream_path,
        market_tape_path=market_tape_path,
    )
    payload = resolver.read_for_narrative(narrative_identity)
    assert payload is not None
    assert _resolution(payload, "order_book")["resolution_state"] == "READY_EXACT"
    assert _resolution(payload, "liquidity")["resolution_state"] == "READY_EXACT"

    references = {
        item["evidence_identity"]: item
        for item in payload["reference_resolutions"]
    }
    assert references[snapshot.snapshot_identity]["resolution_state"] == "READY_EXACT"
    assert (
        references[synthetic_identity]["resolution_state"]
        == "IDENTITY_ONLY_EXACT"
    )

    exact = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=snapshot.snapshot_identity,
    )
    assert exact is not None
    assert exact["resolution_state"] == "READY_EXACT"
    assert exact["object_kind"] == "market_tape_orderbook"
    exact_object = exact["exact_object"]
    assert isinstance(exact_object, dict)
    assert exact_object["snapshot_identity"] == snapshot.snapshot_identity
    assert len(exact_object["bids"]) == 2
    assert len(exact_object["asks"]) == 2


def _event_source_path(tmp_path: Path, *, base_ms: int) -> tuple[Path, str, str]:
    path = tmp_path / "event_source.sqlite3"
    coverage = build_event_calendar_coverage(
        coverage_start_ms=base_ms - 3_600_000,
        coverage_end_ms=base_ms + 3_600_000,
        categories=(EventCategory.INFLATION,),
        source_provider="fred.test",
        source_quality=EventSourceQuality.SECONDARY_AGGREGATOR,
        source=DataSource.REST,
        observed_at_ms=base_ms - 100,
        adapter_version="test-calendar/1",
    )
    event = build_structured_event_observation(
        provider_event_id="cpi-test",
        title="CPI test",
        category=EventCategory.INFLATION,
        scheduled_at_ms=base_ms + 1_000,
        affected_assets=(),
        source_provider="fred.test",
        source_quality=EventSourceQuality.SECONDARY_AGGREGATOR,
        source=DataSource.REST,
        source_timestamp_ms=base_ms - 200,
        ingested_at_ms=base_ms - 100,
        adapter_version="test-calendar/1",
    )
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE event_calendar_coverages (
                coverage_identity TEXT PRIMARY KEY,
                source_provider TEXT NOT NULL,
                observed_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE structured_event_observations (
                event_identity TEXT PRIMARY KEY,
                provider_event_id TEXT NOT NULL,
                source_provider TEXT NOT NULL,
                scheduled_at_ms INTEGER NOT NULL,
                ingested_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO event_calendar_coverages VALUES (?, ?, ?, ?)",
            (
                coverage.coverage_identity,
                coverage.source_provider,
                coverage.observed_at_ms,
                canonical_json(event_calendar_coverage_payload(coverage)),
            ),
        )
        connection.execute(
            "INSERT INTO structured_event_observations VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.event_identity,
                event.provider_event_id,
                event.source_provider,
                event.scheduled_at_ms,
                event.ingested_at_ms,
                canonical_json(structured_event_payload(event)),
            ),
        )
    return path, coverage.coverage_identity, event.event_identity


def test_event_risk_resolves_exact_event_and_temporal_records(
    tmp_path: Path,
) -> None:
    base_ms = 20_000_000
    event_path, coverage_identity, event_identity = _event_source_path(
        tmp_path,
        base_ms=base_ms,
    )
    stream_path = tmp_path / "stream.sqlite3"
    source_identity = canonical_sha256({"source": "event-risk"})
    synthetic_freeze = canonical_sha256({"freeze": "event-risk"})
    family = build_family_snapshot(
        projector_id="event_risk_change",
        family=StreamTrustDomain.EVENT_RISK,
        category=StreamCategory.RISK,
        subtype="event_risk_change",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=source_identity,
        source_scope="fred.test:inflation:event_risk",
        asset="GLOBAL_RISK",
        symbol="GLOBAL_RISK",
        market="GLOBAL",
        timeframe="event_window",
        event_at_ms=base_ms,
        source_as_of_ms=base_ms,
        evidence_identities=(
            coverage_identity,
            event_identity,
            synthetic_freeze,
        ),
        evidence_domains=("event_calendar", "event_risk"),
        state_label="pre_event_caution",
        state_components=(
            ("coverage_provider", "fred.test"),
            ("nearest_event_identity", event_identity),
            ("nearest_event_scheduled_at_ms", str(base_ms + 1_000)),
            ("risk_state", "pre_event_caution"),
        ),
        direction=None,
        source_quality="secondary_aggregator",
    )
    narrative_identity = _project_family(
        stream_path,
        projector_id="event_risk_change",
        snapshot=family,
    )

    payload = IntelligenceStreamExactEvidenceReadModel(
        stream_ledger_path=stream_path,
        event_source_runtime_path=event_path,
    ).read_for_narrative(narrative_identity)
    assert payload is not None
    assert _resolution(payload, "event_calendar")["resolution_state"] == "READY_EXACT"
    assert _resolution(payload, "event_risk")["resolution_state"] == "READY_EXACT"

    references = {
        item["evidence_identity"]: item
        for item in payload["reference_resolutions"]
    }
    assert references[coverage_identity]["resolution_state"] == "READY_EXACT"
    assert references[event_identity]["resolution_state"] == "READY_EXACT"
    assert references[synthetic_freeze]["resolution_state"] == "IDENTITY_ONLY_EXACT"


def test_exact_evidence_api_and_ui_contract(
    tmp_path: Path,
) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    evidence_identity = canonical_sha256({"evidence": "api"})
    source_identity = canonical_sha256({"source": "api"})
    snapshot = build_family_snapshot(
        projector_id="derivatives_change",
        family=ConfluenceFamily.DERIVATIVES,
        category=StreamCategory.INTELLIGENCE,
        subtype="derivatives_material_change",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=source_identity,
        source_scope="bybit:linear_perpetual:market_tape_derivatives",
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe="15m",
        event_at_ms=4_000,
        source_as_of_ms=3_900,
        evidence_identities=(evidence_identity,),
        evidence_domains=("derivatives",),
        state_label="balanced",
        state_components=(
            ("basis_state", "neutral"),
            ("funding_state", "neutral"),
            ("open_interest_state", "flat"),
        ),
        direction=None,
        source_quality="measured",
    )
    narrative_identity = _project_family(
        stream_path,
        projector_id="derivatives_change",
        snapshot=snapshot,
    )

    client = TestClient(
        create_app(
            ledger_path=tmp_path / "missing-ledger.sqlite3",
            stream_ledger_path=stream_path,
            product_root="stream",
        )
    )
    response = client.get(
        f"/api/stream/messages/{narrative_identity}/evidence"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["evidence"]["resolution_counts"] == {
        "READY_EXACT": 0,
        "IDENTITY_ONLY_EXACT": 1,
        "UNAVAILABLE_EXPLICIT": 0,
    }
    assert body["evidence"]["current_data_substitution"] is False

    root = Path(__file__).resolve().parents[1]
    evidence_js = (
        root / "src" / "crypto_signal" / "product" / "stream" / "evidence.js"
    ).read_text(encoding="utf-8")
    visual_js = (
        root / "src" / "crypto_signal" / "product" / "stream" / "visual_proof.js"
    ).read_text(encoding="utf-8")
    for state in (
        "READY_EXACT",
        "IDENTITY_ONLY_EXACT",
        "UNAVAILABLE_EXPLICIT",
    ):
        assert state in evidence_js
        assert state in visual_js
    assert "/evidence" in evidence_js
    assert "current data ile ikame yapılmadı" in evidence_js.lower()

def test_unregistered_derived_domain_cannot_become_ready_from_raw_source(
    tmp_path: Path,
) -> None:
    market_tape_path = tmp_path / "market_tape.sqlite3"
    stream_path = tmp_path / "stream.sqlite3"
    event_at_ms = 30_000
    snapshot = build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms,
        response_time_ms=event_at_ms,
        ingested_at_ms=event_at_ms,
        update_id=17,
        sequence=21,
        bids=(OrderBookLevel(price=Decimal(100), size=Decimal(2)),),
        asks=(OrderBookLevel(price=Decimal(101), size=Decimal(3)),),
        source=DataSource.REST,
        adapter_version="rdp10-fail-closed/1",
    )
    store = MarketTapeStore(market_tape_path)
    store.initialize()
    store.append_orderbook(snapshot)

    derived_identity = canonical_sha256(
        {"evidence": "liquidity-structure-freeze"}
    )
    source_identity = canonical_sha256(
        {"source": "rdp10-liquidity-structure"}
    )
    family = build_family_snapshot(
        projector_id="liquidity_change",
        family=ConfluenceFamily.LIQUIDITY,
        category=StreamCategory.INTELLIGENCE,
        subtype="liquidity_material_change",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=source_identity,
        source_scope="bybit:spot:market_tape_liquidity",
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe="microstructure",
        event_at_ms=event_at_ms,
        source_as_of_ms=event_at_ms,
        evidence_identities=tuple(
            sorted((derived_identity, snapshot.snapshot_identity))
        ),
        evidence_domains=("liquidity_structure",),
        state_label="measured:none",
        state_components=(("persistent_pool_count", "1"),),
        direction=None,
        source_quality="measured",
    )
    narrative_identity = _project_family(
        stream_path,
        projector_id="liquidity_change",
        snapshot=family,
    )

    payload = IntelligenceStreamExactEvidenceReadModel(
        stream_ledger_path=stream_path,
        market_tape_path=market_tape_path,
    ).read_for_narrative(narrative_identity)
    assert payload is not None

    resolution = _resolution(payload, "liquidity_structure")
    assert resolution["resolution_state"] == "IDENTITY_ONLY_EXACT"
    projection = resolution["customer_projection"]
    assert isinstance(projection, dict)
    assert projection["exact_source_objects"] == ()
    assert projection["exact_source_object_count"] == 0
    assert resolution["current_data_substitution"] is False

    references = {
        item["evidence_identity"]: item
        for item in payload["reference_resolutions"]
    }
    assert (
        references[snapshot.snapshot_identity]["resolution_state"]
        == "READY_EXACT"
    )
    assert (
        references[derived_identity]["resolution_state"]
        == "IDENTITY_ONLY_EXACT"
    )
    assert payload["current_data_substitution"] is False

def test_geometry_family_resolves_exact_persisted_full_geometry_proof(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "signal.sqlite3"
    stream_path = tmp_path / "stream.sqlite3"
    bundle = build_bundle(candles())
    ledger = ImmutableSignalLedger(signal_path)
    disposition = ledger.freeze(
        bundle,
        frozen_at_ms=bundle.signal_decision.as_of_ms + 1,
    )
    assert disposition.value == "inserted"

    freeze = ledger.read_freeze_by_signal(
        bundle.signal_decision.freeze_identity
    )
    assert freeze is not None
    proof = ledger.read_geometry_proof_by_signal(
        bundle.signal_decision.freeze_identity
    )
    assert proof is not None

    snapshot = build_geometry_family_snapshot(freeze)
    narrative_identity = _project_family(
        stream_path,
        projector_id="market_geometry_change",
        snapshot=snapshot,
    )

    resolver = IntelligenceStreamExactEvidenceReadModel(
        stream_ledger_path=stream_path,
        signal_ledger_path=signal_path,
    )
    payload = resolver.read_for_narrative(narrative_identity)
    assert payload is not None

    geometry = _resolution(payload, "geometry")
    assert geometry["resolution_state"] == "READY_EXACT"
    assert geometry["reason"] == "exact_persisted_geometry_proof_resolved"
    capabilities = geometry["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["full_geometry_proof"] == "READY_EXACT"
    assert capabilities["methodology_states"] == "READY_EXACT"
    assert capabilities["annotations"] == "READY_EXACT"
    assert capabilities["conflict_flags"] == "READY_EXACT"

    projection = geometry["customer_projection"]
    assert isinstance(projection, dict)
    objects = projection["exact_source_objects"]
    assert isinstance(objects, (list, tuple))
    full = next(
        item
        for item in objects
        if isinstance(item, dict)
        and item.get("proof_identity") == proof.proof_identity
    )
    assert full["bundle_identity"] == bundle.bundle_identity
    assert (
        full["signal_freeze_identity"]
        == bundle.signal_decision.freeze_identity
    )
    assert full["methodology_states"]
    assert isinstance(full["annotations"], list)
    assert "conflict_flags" in full

    references = {
        item["evidence_identity"]: item
        for item in payload["reference_resolutions"]
    }
    assert references[proof.proof_identity]["resolution_state"] == "READY_EXACT"
    assert references[proof.proof_identity]["object_kind"] == "geometry_proof"
    assert payload["current_data_substitution"] is False

    exact = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=proof.proof_identity,
    )
    assert exact is not None
    assert exact["resolution_state"] == "READY_EXACT"
    assert exact["object_kind"] == "geometry_proof"
    exact_object = exact["exact_object"]
    assert isinstance(exact_object, dict)
    assert exact_object["proof_identity"] == proof.proof_identity
    assert exact_object["methodology_states"]
    assert isinstance(exact_object["annotations"], list)
    assert exact["current_data_substitution"] is False

def test_liquidity_derived_proofs_resolve_exact_from_frozen_store(
    tmp_path: Path,
) -> None:
    market_tape_path = tmp_path / "market_tape.sqlite3"
    proof_path = tmp_path / "frozen_proofs.sqlite3"
    stream_path = tmp_path / "stream.sqlite3"
    market_store = MarketTapeStore(market_tape_path)
    _seed(market_store)

    snapshots = build_market_tape_family_snapshots(
        market_tape_path,
        symbols=("BTCUSDT",),
        as_of_ms=AS_OF_MS,
        frozen_proof_store_path=proof_path,
    )
    liquidity = next(
        item
        for item in snapshots
        if item.family is ConfluenceFamily.LIQUIDITY
    )
    narrative_identity = _project_family(
        stream_path,
        projector_id="liquidity_change",
        snapshot=liquidity,
    )

    resolver = IntelligenceStreamExactEvidenceReadModel(
        stream_ledger_path=stream_path,
        market_tape_path=market_tape_path,
        frozen_proof_store_path=proof_path,
    )
    payload = resolver.read_for_narrative(narrative_identity)
    assert payload is not None

    liquidity_resolution = _resolution(payload, "liquidity")
    assert liquidity_resolution["resolution_state"] == "READY_EXACT"
    liquidity_capabilities = liquidity_resolution["capabilities"]
    assert isinstance(liquidity_capabilities, dict)
    assert liquidity_capabilities["dynamics_measurement"] == "READY_EXACT"
    assert (
        liquidity_capabilities["canonical_liquidity_zone_coordinates"]
        == "READY_EXACT"
    )
    assert liquidity_capabilities["sweep_point"] == "READY_EXACT"

    structure = _resolution(payload, "liquidity_structure")
    sweep = _resolution(payload, "liquidity_sweep")
    assert structure["resolution_state"] == "READY_EXACT"
    assert sweep["resolution_state"] == "READY_EXACT"
    assert structure["current_data_substitution"] is False
    assert sweep["current_data_substitution"] is False

    references = tuple(
        item
        for item in payload["reference_resolutions"]
        if isinstance(item, dict)
    )
    structure_ref = next(
        item
        for item in references
        if item.get("object_kind") == "liquidity_structure_freeze"
    )
    sweep_ref = next(
        item
        for item in references
        if item.get("object_kind") == "liquidity_sweep_freeze"
    )
    assert structure_ref["resolution_state"] == "READY_EXACT"
    assert sweep_ref["resolution_state"] == "READY_EXACT"

    exact_structure = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(structure_ref["evidence_identity"]),
    )
    assert exact_structure is not None
    assert exact_structure["object_kind"] == "liquidity_structure_freeze"
    structure_object = exact_structure["exact_object"]
    assert isinstance(structure_object, dict)
    assert structure_object["object_identity"] == structure_ref["evidence_identity"]
    derived_payload = structure_object["payload"]
    assert isinstance(derived_payload, dict)
    assert derived_payload["bid_levels"]
    assert derived_payload["ask_levels"]
    assert structure_object["renderer_contract_version"] == (
        "liquidity-structure-levels-v1/1"
    )
    assert exact_structure["current_data_substitution"] is False

    client = TestClient(
        create_app(
            ledger_path=tmp_path / "missing-ledger.sqlite3",
            stream_ledger_path=stream_path,
            market_tape_path=market_tape_path,
            frozen_proof_store_path=proof_path,
            product_root="stream",
        )
    )
    response = client.get(
        f"/api/stream/messages/{narrative_identity}/evidence"
    )
    assert response.status_code == 200
    api_payload = response.json()["evidence"]
    api_structure = next(
        item
        for item in api_payload["resolutions"]
        if item["domain"] == "liquidity_structure"
    )
    assert api_structure["resolution_state"] == "READY_EXACT"
    assert api_payload["current_data_substitution"] is False

def test_order_flow_derived_proofs_resolve_exact_from_frozen_store(
    tmp_path: Path,
) -> None:
    market_tape_path = tmp_path / "market_tape.sqlite3"
    candle_path = tmp_path / "candles.sqlite3"
    proof_path = tmp_path / "frozen_proofs.sqlite3"
    stream_path = tmp_path / "stream.sqlite3"

    market_store = MarketTapeStore(market_tape_path)
    _seed(market_store)

    candle_store = CandleStore(candle_path)
    candle_store.upsert(
        Candle(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
            open_time_ms=80_000,
            close_time_ms=170_000,
            open=Decimal(100),
            high=Decimal(103),
            low=Decimal(97),
            close=Decimal(101),
            volume=Decimal(10),
            quote_volume=Decimal(1_000),
            trade_count=10,
            is_closed=True,
            source=DataSource.REST,
            source_timestamp_ms=170_001,
            ingested_at_ms=170_002,
            adapter_version="rdp10-d2-test/1",
        )
    )

    snapshots = build_market_tape_family_snapshots(
        market_tape_path,
        symbols=("BTCUSDT",),
        as_of_ms=AS_OF_MS,
        candle_cache_path=candle_path,
        frozen_proof_store_path=proof_path,
    )
    order_flow = next(
        item
        for item in snapshots
        if item.family is ConfluenceFamily.ORDER_FLOW
    )
    narrative_identity = _project_family(
        stream_path,
        projector_id="order_flow_change",
        snapshot=order_flow,
    )

    resolver = IntelligenceStreamExactEvidenceReadModel(
        stream_ledger_path=stream_path,
        market_tape_path=market_tape_path,
        frozen_proof_store_path=proof_path,
    )
    payload = resolver.read_for_narrative(narrative_identity)
    assert payload is not None

    order_flow_resolution = _resolution(payload, "order_flow")
    assert order_flow_resolution["resolution_state"] == "READY_EXACT"
    capabilities = order_flow_resolution["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["microstructure_measurement"] == "READY_EXACT"
    assert capabilities["cvd_series"] == "READY_EXACT"
    assert capabilities["absorption_evidence"] == "READY_EXACT"
    assert capabilities["divergence_relation"] == "READY_EXACT"

    for domain in (
        "temporal_order_flow",
        "window_local_cvd",
        "absorption",
        "price_cvd_divergence",
    ):
        resolution = _resolution(payload, domain)
        assert resolution["resolution_state"] == "READY_EXACT"
        assert resolution["current_data_substitution"] is False

    references = tuple(
        item
        for item in payload["reference_resolutions"]
        if isinstance(item, dict)
    )
    expected_kinds = {
        "order_flow_microstructure_freeze",
        "temporal_order_flow_freeze",
        "absorption_freeze",
        "price_cvd_divergence_freeze",
    }
    ready_kinds = {
        str(item.get("object_kind"))
        for item in references
        if item.get("resolution_state") == "READY_EXACT"
    }
    assert expected_kinds.issubset(ready_kinds)

    divergence_ref = next(
        item
        for item in references
        if item.get("object_kind") == "price_cvd_divergence_freeze"
    )
    exact_divergence = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(divergence_ref["evidence_identity"]),
    )
    assert exact_divergence is not None
    assert exact_divergence["object_kind"] == "price_cvd_divergence_freeze"
    divergence_object = exact_divergence["exact_object"]
    assert isinstance(divergence_object, dict)
    assert (
        divergence_object["object_identity"]
        == divergence_ref["evidence_identity"]
    )
    divergence_payload = divergence_object["payload"]
    assert isinstance(divergence_payload, dict)
    assert divergence_payload["timeframe"] == "15m"
    assert divergence_object["depends_on_evidence_identities"]
    assert exact_divergence["current_data_substitution"] is False

def test_derivatives_core_proofs_resolve_exact_from_frozen_store(
    tmp_path: Path,
) -> None:
    market_tape_path = tmp_path / "market_tape.sqlite3"
    proof_path = tmp_path / "frozen_proofs.sqlite3"
    stream_path = tmp_path / "stream.sqlite3"

    store = MarketTapeStore(market_tape_path)
    for observation in derivatives_history():
        store.append_derivatives(observation)

    snapshots = build_market_tape_family_snapshots(
        market_tape_path,
        symbols=("BTCUSDT",),
        as_of_ms=DERIVATIVES_AS_OF_MS,
        frozen_proof_store_path=proof_path,
    )
    derivatives = next(
        item
        for item in snapshots
        if item.family is ConfluenceFamily.DERIVATIVES
    )
    narrative_identity = _project_family(
        stream_path,
        projector_id="derivatives_change",
        snapshot=derivatives,
    )

    resolver = IntelligenceStreamExactEvidenceReadModel(
        stream_ledger_path=stream_path,
        market_tape_path=market_tape_path,
        frozen_proof_store_path=proof_path,
    )
    payload = resolver.read_for_narrative(narrative_identity)
    assert payload is not None

    derivatives_resolution = _resolution(payload, "derivatives")
    assert derivatives_resolution["resolution_state"] == "READY_EXACT"
    capabilities = derivatives_resolution["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["raw_mark_index_open_interest_funding"] == "READY_EXACT"
    assert capabilities["context_measurement"] == "READY_EXACT"
    assert capabilities["price_oi_funding_dynamics"] == "READY_EXACT"
    assert capabilities["funding_open_interest_basis"] == "READY_EXACT"

    context = _resolution(payload, "derivatives_context")
    dynamics = _resolution(payload, "derivatives_dynamics")
    assert context["resolution_state"] == "READY_EXACT"
    assert dynamics["resolution_state"] == "READY_EXACT"
    assert context["current_data_substitution"] is False
    assert dynamics["current_data_substitution"] is False

    references = tuple(
        item
        for item in payload["reference_resolutions"]
        if isinstance(item, dict)
    )
    context_ref = next(
        item
        for item in references
        if item.get("object_kind") == "derivatives_context_freeze"
    )
    dynamics_ref = next(
        item
        for item in references
        if item.get("object_kind") == "derivatives_dynamics_freeze"
    )
    assert context_ref["resolution_state"] == "READY_EXACT"
    assert dynamics_ref["resolution_state"] == "READY_EXACT"

    exact_dynamics = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(dynamics_ref["evidence_identity"]),
    )
    assert exact_dynamics is not None
    assert exact_dynamics["object_kind"] == "derivatives_dynamics_freeze"
    exact_object = exact_dynamics["exact_object"]
    assert isinstance(exact_object, dict)
    assert exact_object["object_identity"] == dynamics_ref["evidence_identity"]
    derived_payload = exact_object["payload"]
    assert isinstance(derived_payload, dict)
    assert derived_payload["status"] == "measured"
    metrics = derived_payload["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["open_interest_change_fraction"] == "0.1"
    assert metrics["mark_price_change_fraction"] == "0.03"
    assert exact_object["source_object_identities"]
    assert exact_dynamics["current_data_substitution"] is False

