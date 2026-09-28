from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
import test_rdp5_liquidation_heatmap_crowding_family as liquidation_family
import test_rdp6_options_derivatives_family as options_family
import test_rdp7_onchain_family as onchain_family
from fastapi.testclient import TestClient
from test_immutable_ledger import build_bundle, candles
from test_provider_divergence import _candle as provider_candle
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
from crypto_signal.data.provider_divergence import (
    ProviderDivergenceStore,
    build_provider_divergence_snapshot,
)
from crypto_signal.data.store import CandleStore
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.ledger.store import ImmutableSignalLedger
from crypto_signal.product.intelligence_stream_exact_evidence import (
    IntelligenceStreamExactEvidenceReadModel,
    StreamExactEvidenceError,
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
from crypto_signal.product.intelligence_stream_onchain_family import (
    build_onchain_family_snapshots,
)
from crypto_signal.product.intelligence_stream_production_projector import (
    IntelligenceStreamProductionProjector,
)
from crypto_signal.product.intelligence_stream_trust_sources import (
    build_provider_quality_stream_snapshots,
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

def test_liquidation_heatmap_and_crowding_resolve_exact_from_frozen_store(
    tmp_path: Path,
) -> None:
    market_tape_path = tmp_path / "market_tape.sqlite3"
    proof_path = tmp_path / "frozen_proofs.sqlite3"
    stream_path = tmp_path / "stream.sqlite3"

    store = MarketTapeStore(market_tape_path)
    liquidation_family._seed_derivatives(store)
    event = liquidation_family._liquidation()
    coverage = liquidation_family._coverage(
        start_ms=(
            liquidation_family.AS_OF_MS
            - liquidation_family.LOOKBACK_MS
        )
    )
    store.append_liquidation(event)
    store.append_liquidation_coverage(coverage)

    snapshots = build_market_tape_family_snapshots(
        market_tape_path,
        symbols=(liquidation_family.SYMBOL,),
        as_of_ms=liquidation_family.AS_OF_MS,
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

    top = _resolution(payload, "derivatives")
    assert top["resolution_state"] == "READY_EXACT"
    top_capabilities = top["capabilities"]
    assert isinstance(top_capabilities, dict)
    assert top_capabilities["observed_liquidation_heatmap"] == "READY_EXACT"
    assert top_capabilities["crowding_context"] == "READY_EXACT"

    for domain in (
        "observed_liquidation_events",
        "liquidation_event_coverage",
        "observed_liquidation_heatmap",
        "derivatives_crowding",
    ):
        resolution = _resolution(payload, domain)
        assert resolution["resolution_state"] == "READY_EXACT"
        assert resolution["current_data_substitution"] is False

    refs = tuple(
        item
        for item in payload["reference_resolutions"]
        if isinstance(item, dict)
    )
    by_kind = {
        str(item.get("object_kind")): item
        for item in refs
        if item.get("object_kind") is not None
    }
    for kind in (
        "market_tape_liquidation",
        "market_tape_liquidation_coverage",
        "liquidation_heatmap_freeze",
        "derivatives_crowding_freeze",
    ):
        assert by_kind[kind]["resolution_state"] == "READY_EXACT"

    coverage_exact = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=coverage.coverage_identity,
    )
    assert coverage_exact is not None
    assert (
        coverage_exact["object_kind"]
        == "market_tape_liquidation_coverage"
    )
    coverage_object = coverage_exact["exact_object"]
    assert isinstance(coverage_object, dict)
    assert (
        coverage_object["observed_at_ms"]
        == liquidation_family.AS_OF_MS
    )
    assert coverage_object["coverage_end_ms"] == liquidation_family.AS_OF_MS

    event_exact = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=event.liquidation_identity,
    )
    assert event_exact is not None
    assert event_exact["object_kind"] == "market_tape_liquidation"

    heatmap_ref = by_kind["liquidation_heatmap_freeze"]
    heatmap_exact = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(heatmap_ref["evidence_identity"]),
    )
    assert heatmap_exact is not None
    heatmap_object = heatmap_exact["exact_object"]
    assert isinstance(heatmap_object, dict)
    heatmap_payload = heatmap_object["payload"]
    assert isinstance(heatmap_payload, dict)
    assert heatmap_payload["status"] == "measured"
    assert heatmap_payload["observed_state"] == "observed"
    assert (
        heatmap_payload["estimated_leverage_concentration_status"]
        == "not_estimated"
    )
    assert heatmap_payload["liquidation_risk_zone_status"] == "not_estimated"
    assert coverage.coverage_identity in heatmap_object[
        "source_object_identities"
    ]
    assert event.liquidation_identity in heatmap_object[
        "source_object_identities"
    ]

    crowding_ref = by_kind["derivatives_crowding_freeze"]
    crowding_exact = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(crowding_ref["evidence_identity"]),
    )
    assert crowding_exact is not None
    crowding_object = crowding_exact["exact_object"]
    assert isinstance(crowding_object, dict)
    assert heatmap_ref["evidence_identity"] in crowding_object[
        "depends_on_evidence_identities"
    ]
    assert crowding_exact["current_data_substitution"] is False
    assert payload["current_data_substitution"] is False

def test_options_proofs_resolve_exact_from_frozen_store(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market.sqlite3"
    options_path = tmp_path / "options.sqlite3"
    proof_path = tmp_path / "frozen_proofs.sqlite3"
    stream_path = tmp_path / "stream.sqlite3"

    options_family._seed_derivatives(
        market_path,
        symbol=options_family.BTC_SYMBOL,
    )
    options_family._seed_options(options_path)

    snapshots = build_market_tape_family_snapshots(
        market_path,
        symbols=(options_family.BTC_SYMBOL,),
        as_of_ms=options_family.AS_OF_MS,
        options_surface_path=options_path,
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
        market_tape_path=market_path,
        frozen_proof_store_path=proof_path,
        options_surface_path=options_path,
    )
    payload = resolver.read_for_narrative(narrative_identity)
    assert payload is not None

    options_surface = _resolution(payload, "options_surface")
    options_volatility = _resolution(payload, "options_volatility")
    assert options_surface["resolution_state"] == "READY_EXACT"
    assert options_volatility["resolution_state"] == "READY_EXACT"
    assert options_surface["current_data_substitution"] is False
    assert options_volatility["current_data_substitution"] is False

    surface_capabilities = options_surface["capabilities"]
    assert isinstance(surface_capabilities, dict)
    assert surface_capabilities["surface_snapshot"] == "READY_EXACT"
    assert (
        surface_capabilities["instrument_metadata_lineage"]
        == "READY_EXACT"
    )
    assert surface_capabilities["contract_quote_lineage"] == "READY_EXACT"

    volatility_capabilities = options_volatility["capabilities"]
    assert isinstance(volatility_capabilities, dict)
    assert volatility_capabilities["atm_iv_term_structure"] == "READY_EXACT"
    assert volatility_capabilities["risk_reversal_25d"] == "READY_EXACT"
    assert volatility_capabilities["open_interest_by_expiry"] == "READY_EXACT"
    assert volatility_capabilities["volume_by_expiry"] == "READY_EXACT"
    assert volatility_capabilities["expiry_concentration"] == "READY_EXACT"
    assert volatility_capabilities["dealer_gamma_position"] == (
        "UNAVAILABLE_EXPLICIT"
    )
    assert volatility_capabilities["max_pain"] == "UNAVAILABLE_EXPLICIT"

    references = tuple(
        item
        for item in payload["reference_resolutions"]
        if isinstance(item, dict)
    )
    surface_ref = next(
        item
        for item in references
        if item.get("object_kind") == "options_surface_observation"
    )
    metadata_ref = next(
        item
        for item in references
        if item.get("object_kind") == "options_instrument_metadata"
    )
    quote_refs = tuple(
        item
        for item in references
        if item.get("object_kind") == "options_contract_quote"
    )
    volatility_ref = next(
        item
        for item in references
        if item.get("object_kind") == "options_volatility_freeze"
    )
    assert surface_ref["resolution_state"] == "READY_EXACT"
    assert metadata_ref["resolution_state"] == "READY_EXACT"
    assert len(quote_refs) == 8
    assert all(
        item["resolution_state"] == "READY_EXACT"
        for item in quote_refs
    )
    assert volatility_ref["resolution_state"] == "READY_EXACT"

    exact_surface = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(surface_ref["evidence_identity"]),
    )
    assert exact_surface is not None
    surface_payload = exact_surface["exact_object"]
    assert isinstance(surface_payload, dict)
    contracts = surface_payload["contracts"]
    assert isinstance(contracts, list)
    assert len(contracts) == 8
    assert surface_payload["source_timestamp_ms"] == (
        options_family.AS_OF_MS - 100
    )
    assert surface_payload["observed_at_ms"] == (
        options_family.AS_OF_MS - 80
    )

    exact_metadata = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(metadata_ref["evidence_identity"]),
    )
    assert exact_metadata is not None
    metadata_payload = exact_metadata["exact_object"]
    assert isinstance(metadata_payload, dict)
    assert metadata_payload["metadata_identity"] == (
        surface_payload["instrument_metadata_identity"]
    )
    instrument_specs = metadata_payload["instrument_specs"]
    assert isinstance(instrument_specs, list)
    assert len(instrument_specs) == 8

    exact_quote = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(quote_refs[0]["evidence_identity"]),
    )
    assert exact_quote is not None
    quote_payload = exact_quote["exact_object"]
    assert isinstance(quote_payload, dict)
    assert quote_payload["quote_identity"] == quote_refs[0]["evidence_identity"]
    assert exact_quote["current_data_substitution"] is False

    exact_volatility = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(volatility_ref["evidence_identity"]),
    )
    assert exact_volatility is not None
    volatility_object = exact_volatility["exact_object"]
    assert isinstance(volatility_object, dict)
    proof_payload = volatility_object["payload"]
    assert isinstance(proof_payload, dict)
    analysis = proof_payload["analysis"]
    assert isinstance(analysis, dict)
    assert analysis["status"] == "measured"
    metrics = analysis["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["front_atm_iv"] == "0.51"
    assert metrics["next_atm_iv"] == "0.56"
    assert volatility_object["depends_on_evidence_identities"]
    assert exact_volatility["current_data_substitution"] is False

def test_onchain_stablecoin_proofs_resolve_exact_from_canonical_sources(
    tmp_path: Path,
) -> None:
    onchain_path, source_path, latest = onchain_family._seed_two_snapshots(
        tmp_path
    )
    proof_path = tmp_path / "frozen_proofs.sqlite3"
    stream_path = tmp_path / "stream.sqlite3"

    snapshot = build_onchain_family_snapshots(
        onchain_path,
        source_path,
        symbols=("BTCUSDT",),
        as_of_ms=1_300_100,
        frozen_proof_store_path=proof_path,
    )[0]
    narrative_identity = _project_family(
        stream_path,
        projector_id="onchain_change",
        snapshot=snapshot,
    )

    resolver = IntelligenceStreamExactEvidenceReadModel(
        stream_ledger_path=stream_path,
        frozen_proof_store_path=proof_path,
        onchain_capital_flow_path=onchain_path,
        onchain_source_contract_path=source_path,
    )
    payload = resolver.read_for_narrative(narrative_identity)
    assert payload is not None
    assert payload["current_data_substitution"] is False

    for domain in (
        "onchain",
        "stablecoin_capital_flow",
        "stablecoin_supply",
        "source_raw_payload",
        "source_envelope",
        "source_coverage",
    ):
        resolution = _resolution(payload, domain)
        assert resolution["resolution_state"] == "READY_EXACT"
        assert resolution["current_data_substitution"] is False

    onchain = _resolution(payload, "onchain")
    capabilities = onchain["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["stablecoin_capital_flow_freeze"] == "READY_EXACT"
    assert capabilities["normalized_supply_observations"] == "READY_EXACT"
    assert capabilities["source_lineage"] == "READY_EXACT"
    assert capabilities["exchange_flow"] == "UNAVAILABLE_EXPLICIT"
    assert capabilities["large_transfer"] == "UNAVAILABLE_EXPLICIT"
    assert capabilities["wallet_cohort"] == "UNAVAILABLE_EXPLICIT"
    assert capabilities["stablecoin_bridge"] == "UNAVAILABLE_EXPLICIT"
    assert capabilities["directional_inference"] == "UNAVAILABLE_EXPLICIT"

    references = tuple(
        item
        for item in payload["reference_resolutions"]
        if isinstance(item, dict)
    )
    kinds = {
        str(item.get("object_kind"))
        for item in references
        if item.get("object_kind") is not None
    }
    assert "stablecoin_capital_flow_freeze" in kinds
    assert "stablecoin_supply_observation" in kinds
    assert "source_raw_payload" in kinds
    assert "source_envelope" in kinds
    assert "source_coverage" in kinds

    freeze_ref = next(
        item
        for item in references
        if item.get("object_kind") == "stablecoin_capital_flow_freeze"
    )
    exact_freeze = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(freeze_ref["evidence_identity"]),
    )
    assert exact_freeze is not None
    freeze_object = exact_freeze["exact_object"]
    assert isinstance(freeze_object, dict)
    freeze_payload = freeze_object["payload"]
    assert isinstance(freeze_payload, dict)
    assert freeze_payload["analysis"]["status"] == "measured"
    assert freeze_payload["observations"]
    assert exact_freeze["current_data_substitution"] is False

    latest_ids = {
        value
        for item in latest
        for value in (
            item.raw_identity,
            item.envelope_identity,
            item.coverage_event_identity,
            item.observation_identity,
        )
    }
    ready_ids = {
        str(item["evidence_identity"])
        for item in references
        if item.get("resolution_state") == "READY_EXACT"
    }
    assert latest_ids.issubset(ready_ids)

    raw_ref = next(
        item
        for item in references
        if item.get("object_kind") == "source_raw_payload"
    )
    exact_raw = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(raw_ref["evidence_identity"]),
    )
    assert exact_raw is not None
    raw_object = exact_raw["exact_object"]
    assert isinstance(raw_object, dict)
    assert isinstance(raw_object["payload"], dict)

    envelope_ref = next(
        item
        for item in references
        if item.get("object_kind") == "source_envelope"
    )
    exact_envelope = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(envelope_ref["evidence_identity"]),
    )
    assert exact_envelope is not None
    envelope_object = exact_envelope["exact_object"]
    assert isinstance(envelope_object, dict)
    assert envelope_object["normalized_identity"] in ready_ids

    coverage_ref = next(
        item
        for item in references
        if item.get("object_kind") == "source_coverage"
    )
    exact_coverage = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=str(coverage_ref["evidence_identity"]),
    )
    assert exact_coverage is not None
    coverage_object = exact_coverage["exact_object"]
    assert isinstance(coverage_object, dict)
    assert coverage_object["state"] == "observed"
    assert snapshot.direction is None

def test_provider_quality_resolves_exact_divergence_and_rejects_future_source(
    tmp_path: Path,
) -> None:
    divergence_path = tmp_path / "provider_divergence.sqlite3"
    stream_path = tmp_path / "stream.sqlite3"

    binance = (
        provider_candle(Exchange.BINANCE, 0, "100.1"),
        provider_candle(Exchange.BINANCE, 900_000, "100.8"),
        provider_candle(Exchange.BINANCE, 1_800_000, "102.2"),
    )
    bybit = (
        provider_candle(Exchange.BYBIT, 0, "100"),
        provider_candle(Exchange.BYBIT, 900_000, "101"),
        provider_candle(Exchange.BYBIT, 1_800_000, "102"),
    )
    divergence = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=2_800_000,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=binance,
        right_candles=bybit,
        lookback_limit=96,
    )
    ProviderDivergenceStore(divergence_path).append(divergence)

    family = build_provider_quality_stream_snapshots(
        divergence_path,
        evaluated_at_ms=2_900_000,
    )[0]
    narrative_identity = _project_family(
        stream_path,
        projector_id="provider_quality_change",
        snapshot=family,
    )
    resolver = IntelligenceStreamExactEvidenceReadModel(
        stream_ledger_path=stream_path,
        provider_divergence_path=divergence_path,
    )
    payload = resolver.read_for_narrative(narrative_identity)
    assert payload is not None
    assert payload["current_data_substitution"] is False

    for domain in ("provider_divergence", "data_quality"):
        resolution = _resolution(payload, domain)
        assert resolution["resolution_state"] == "READY_EXACT"
        assert resolution["current_data_substitution"] is False
        projection = resolution["customer_projection"]
        assert isinstance(projection, dict)
        assert projection["source_scope"] == family.source_scope
        assert projection["source_as_of_ms"] == divergence.observed_at_ms
        assert projection["source_quality"] == family.source_quality
        assert tuple(projection["uncertainty_flags"]) == family.uncertainty_flags

    references = {
        item["evidence_identity"]: item
        for item in payload["reference_resolutions"]
    }
    assert (
        references[divergence.snapshot_identity]["resolution_state"]
        == "READY_EXACT"
    )
    assert (
        references[divergence.snapshot_identity]["object_kind"]
        == "provider_divergence_snapshot"
    )

    exact = resolver.read_reference(
        narrative_identity=narrative_identity,
        evidence_identity=divergence.snapshot_identity,
    )
    assert exact is not None
    assert exact["object_kind"] == "provider_divergence_snapshot"
    exact_object = exact["exact_object"]
    assert isinstance(exact_object, dict)
    assert exact_object["observed_at_ms"] == divergence.observed_at_ms
    assert exact_object["left_exchange"] == Exchange.BINANCE.value
    assert exact_object["right_exchange"] == Exchange.BYBIT.value
    assert exact_object["grid_state"] == divergence.grid_state.value
    assert exact["current_data_substitution"] is False

    future_bound_family = replace(
        family,
        source_as_of_ms=divergence.observed_at_ms - 1,
    )
    future_stream_path = tmp_path / "future_stream.sqlite3"
    future_narrative_identity = _project_family(
        future_stream_path,
        projector_id="provider_quality_change",
        snapshot=future_bound_family,
    )
    with pytest.raises(
        StreamExactEvidenceError,
        match="provider_divergence_snapshot contains future evidence: observed_at_ms",
    ):
        IntelligenceStreamExactEvidenceReadModel(
            stream_ledger_path=future_stream_path,
            provider_divergence_path=divergence_path,
        ).read_for_narrative(future_narrative_identity)

