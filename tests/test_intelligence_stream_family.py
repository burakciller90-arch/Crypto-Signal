from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_wc2_live_source_adapter import _bundle

from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.ledger.bundle import bundle_json
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.ledger.store import (
    FreezeRecord,
    LifecycleRecord,
    lifecycle_evaluation_identity,
)
from crypto_signal.product.intelligence_stream_family import (
    IntelligenceStreamFamilyRuntime,
    StreamFamilyProjectionDisposition,
    build_family_snapshot,
)
from crypto_signal.product.intelligence_stream_family_sources import (
    build_geometry_family_snapshot,
    build_geometry_lifecycle_family_snapshot,
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
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamMessageQuery,
)
from crypto_signal.signals.models import (
    LifecycleEvaluationStatus,
    LifecycleTransitionReason,
    SignalLifecycleEvaluation,
    SignalState,
    SignalStateTransition,
)


def _snapshot(*, source: str, event_at_ms: int, state: str):
    source_identity = canonical_sha256(
        {"source": source, "event_at_ms": event_at_ms, "state": state}
    )
    return build_family_snapshot(
        projector_id="liquidity_change",
        family=ConfluenceFamily.LIQUIDITY,
        category=StreamCategory.INTELLIGENCE,
        subtype="liquidity_material_change",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=source_identity,
        source_scope="bybit:spot:test",
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe="microstructure",
        event_at_ms=event_at_ms,
        source_as_of_ms=event_at_ms,
        evidence_identities=(source_identity,),
        evidence_domains=("liquidity",),
        state_label=state,
        state_components=(
            ("candidate", state),
            ("quality", "good"),
        ),
        direction=None,
        source_quality="good",
    )


def _path(tmp_path: Path) -> Path:
    path = tmp_path / "stream.sqlite3"
    IntelligenceStreamForwardRuntime(path).ensure_activated(activated_at_ms=1_000)
    return path


def test_family_runtime_refuses_pre_activation_backfill(tmp_path: Path) -> None:
    path = _path(tmp_path)
    runtime = IntelligenceStreamFamilyRuntime(path)

    result = runtime.project(
        _snapshot(source="old", event_at_ms=1_900, state="none"),
        activated_at_ms=2_000,
    )

    assert result.disposition is StreamFamilyProjectionDisposition.SKIPPED_BEFORE_ACTIVATION
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM stream_narrative_messages"
        ).fetchone() == (0,)


def test_family_runtime_persists_material_transition_in_canonical_tables(
    tmp_path: Path,
) -> None:
    path = _path(tmp_path)
    runtime = IntelligenceStreamFamilyRuntime(path)

    first = runtime.project(
        _snapshot(source="first", event_at_ms=2_100, state="none"),
        activated_at_ms=2_000,
    )
    silent = runtime.project(
        _snapshot(source="same", event_at_ms=2_200, state="none"),
        activated_at_ms=9_999,
    )
    changed = runtime.project(
        _snapshot(source="changed", event_at_ms=2_300, state="bid_side"),
        activated_at_ms=9_999,
    )

    assert first.disposition is StreamFamilyProjectionDisposition.INSERTED
    assert silent.disposition is StreamFamilyProjectionDisposition.SILENT_UNCHANGED
    assert changed.disposition is StreamFamilyProjectionDisposition.INSERTED
    assert first.activation_identity == silent.activation_identity == changed.activation_identity
    assert first.story_identity == changed.story_identity
    assert first.narrative_identity is not None
    assert changed.narrative_identity is not None

    with sqlite3.connect(path) as connection:
        for table in (
            "stream_source_events",
            "stream_fact_bundles",
            "stream_message_inputs",
            "stream_story_observations",
            "stream_story_states",
            "stream_story_change_sets",
            "stream_analytical_views",
            "stream_narrative_plans",
            "stream_narrative_messages",
        ):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone() == (2,)
        states = connection.execute(
            """
            SELECT json_extract(payload_json, '$.state_label')
            FROM stream_story_states
            ORDER BY event_at_ms
            """
        ).fetchall()
        assert states == [("none",), ("bid_side",)]


def test_family_projector_activation_is_immutable(tmp_path: Path) -> None:
    path = _path(tmp_path)
    runtime = IntelligenceStreamFamilyRuntime(path)

    first = runtime.ensure_projector_activation(
        "liquidity_change",
        activated_at_ms=2_000,
    )
    second = runtime.ensure_projector_activation(
        "liquidity_change",
        activated_at_ms=99_999,
    )

    assert second == first
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT activated_at_ms
            FROM stream_family_projection_boundaries
            WHERE projector_id = 'liquidity_change'
            """
        ).fetchone()
    assert row == (2_000,)


def test_family_messages_flow_through_canonical_read_model(tmp_path: Path) -> None:
    path = _path(tmp_path)
    runtime = IntelligenceStreamFamilyRuntime(path)
    result = runtime.project(
        _snapshot(source="read", event_at_ms=2_100, state="bid_side"),
        activated_at_ms=2_000,
    )
    assert result.narrative_identity is not None

    model = IntelligenceStreamReadModel(path)
    page = model.read_messages(
        StreamMessageQuery(
            category="intelligence",
            evidence_domain="liquidity",
            state="bid_side",
        )
    )
    assert len(page.items) == 1
    assert page.items[0]["narrative_identity"] == result.narrative_identity
    assert page.items[0]["family"] == ConfluenceFamily.LIQUIDITY.value
    assert page.items[0]["text"]["collapsed_text"]

    detail = model.read_message_detail(result.narrative_identity)
    assert detail is not None
    assert detail["narrative"]["narrative_identity"] == result.narrative_identity
    assert detail["analytical_view"]["family_state_label"] == "bid_side"
    assert detail["fact_bundle"]["family"] == ConfluenceFamily.LIQUIDITY.value
    assert detail["message_input"]["category"] == "intelligence"
    assert detail["real_capital"] == 0


def test_family_projection_routes_through_f2_production_backbone(
    tmp_path: Path,
) -> None:
    path = _path(tmp_path)
    result = IntelligenceStreamProductionProjector(path).project_family(
        _snapshot(source="f2-backbone", event_at_ms=2_100, state="none"),
        activated_at_ms=2_000,
    )
    assert result.disposition is StreamFamilyProjectionDisposition.INSERTED
    assert result.projector_id == "liquidity_change"
    assert result.real_capital == 0


def test_family_runtime_rejects_deferred_onchain_projector(tmp_path: Path) -> None:
    path = _path(tmp_path)
    runtime = IntelligenceStreamFamilyRuntime(path)
    source_identity = canonical_sha256({"source": "onchain-deferred"})
    snapshot = build_family_snapshot(
        projector_id="bitcoin_network_context",
        family=ConfluenceFamily.ONCHAIN,
        category=StreamCategory.INTELLIGENCE,
        subtype="bitcoin_network_material_change",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=source_identity,
        source_scope="blockstream:bitcoin:deferred",
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe="network",
        event_at_ms=2_100,
        source_as_of_ms=2_100,
        evidence_identities=(source_identity,),
        evidence_domains=("onchain",),
        state_label="available",
        state_components=(("state", "available"),),
        direction=None,
        source_quality="deferred_source",
    )
    with pytest.raises(ValueError, match="not implemented"):
        runtime.project(snapshot, activated_at_ms=2_000)


def test_family_runtime_replay_returns_unchanged_after_later_transition(
    tmp_path: Path,
) -> None:
    path = _path(tmp_path)
    runtime = IntelligenceStreamFamilyRuntime(path)
    first_snapshot = _snapshot(source="first", event_at_ms=2_100, state="none")
    changed_snapshot = _snapshot(
        source="changed",
        event_at_ms=2_300,
        state="bid_side",
    )

    first = runtime.project(first_snapshot, activated_at_ms=2_000)
    changed = runtime.project(changed_snapshot, activated_at_ms=2_000)
    replay = runtime.project(first_snapshot, activated_at_ms=99_999)

    assert first.disposition is StreamFamilyProjectionDisposition.INSERTED
    assert changed.disposition is StreamFamilyProjectionDisposition.INSERTED
    assert replay.disposition is StreamFamilyProjectionDisposition.UNCHANGED
    assert replay.narrative_identity == first.narrative_identity
    assert replay.stream_event_identity == first.stream_event_identity
    assert replay.story_identity == first.story_identity


def _geometry_freeze() -> tuple[FreezeRecord, object]:
    bundle = _bundle()
    signal = bundle.signal_decision
    freeze = FreezeRecord(
        bundle_identity=bundle.bundle_identity,
        signal_freeze_identity=signal.freeze_identity,
        exchange=signal.exchange.value,
        market_type=signal.market_type.value,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        as_of_ms=signal.as_of_ms,
        source_cutoff_open_time_ms=bundle.candles[-1].open_time_ms,
        signal_state=signal.state.value,
        direction=signal.direction.value,
        frozen_at_ms=signal.as_of_ms + 10,
        bundle_json=bundle_json(bundle),
    )
    return freeze, bundle


def test_geometry_family_fingerprint_binds_exact_coordinates() -> None:
    freeze, bundle = _geometry_freeze()
    signal = bundle.signal_decision
    assert signal.geometry is not None

    snapshot = build_geometry_family_snapshot(freeze)
    components = {item.name: item.value for item in snapshot.state_components}

    assert components["entry_zone_low"] == str(signal.geometry.entry_zone.low)
    assert components["entry_zone_high"] == str(signal.geometry.entry_zone.high)
    assert components["entry_reference_price"] == str(
        signal.geometry.entry_reference_price
    )
    assert components["invalidation_price"] == str(
        signal.geometry.invalidation_price
    )
    for index, target in enumerate(signal.geometry.targets, start=1):
        prefix = f"target_{index:02d}_{target.label}"
        assert components[f"{prefix}_price"] == str(target.target_price)
        assert components[f"{prefix}_rr"] == str(target.reference_rr)


def test_geometry_lifecycle_transition_continues_same_family_story(
    tmp_path: Path,
) -> None:
    freeze, bundle = _geometry_freeze()
    signal = bundle.signal_decision
    assert signal.state is SignalState.ACTIVE

    evaluated_at_ms = freeze.frozen_at_ms + 100
    transition = SignalStateTransition(
        transition_identity=canonical_sha256(
            {
                "signal": signal.freeze_identity,
                "event": "invalidation",
                "evaluated_at_ms": evaluated_at_ms,
            }
        ),
        signal_freeze_identity=signal.freeze_identity,
        from_state=SignalState.ACTIVE,
        to_state=SignalState.INVALIDATED,
        reason=LifecycleTransitionReason.INVALIDATION_TOUCH_OR_CROSS,
        trigger_candle_identity=(
            signal.exchange.value,
            signal.market_type.value,
            signal.symbol,
            signal.timeframe,
            bundle.candles[-1].open_time_ms,
        ),
        market_confirmed_at_ms=evaluated_at_ms - 2,
        observed_at_ms=evaluated_at_ms - 1,
        evaluated_as_of_ms=evaluated_at_ms,
        first_trigger_candle_certain=True,
    )
    evaluation = SignalLifecycleEvaluation(
        signal_freeze_identity=signal.freeze_identity,
        evaluated_as_of_ms=evaluated_at_ms,
        current_state=SignalState.INVALIDATED,
        status=LifecycleEvaluationStatus.COMPLETE,
        missing_open_times_ms=(),
        skipped_partial_decision_bucket=False,
        transition=transition,
    )
    lifecycle = LifecycleRecord(
        evaluation_identity=lifecycle_evaluation_identity(evaluation),
        signal_freeze_identity=signal.freeze_identity,
        evaluated_as_of_ms=evaluated_at_ms,
        current_state=evaluation.current_state.value,
        status=evaluation.status.value,
        appended_at_ms=evaluated_at_ms + 1,
        evaluation_json=canonical_json(evaluation),
    )

    geometry = build_geometry_family_snapshot(freeze)
    invalidation = build_geometry_lifecycle_family_snapshot(freeze, lifecycle)
    assert invalidation is not None
    assert invalidation.subtype == "trigger_transition"
    assert invalidation.state_label.startswith("invalidated:")

    path = _path(tmp_path)
    projector = IntelligenceStreamProductionProjector(path)
    projector.ensure_family_activation(
        "market_geometry_change",
        activated_at_ms=freeze.frozen_at_ms - 1,
    )
    first = projector.project_family(
        geometry,
        activated_at_ms=freeze.frozen_at_ms - 1,
    )
    second = projector.project_family(
        invalidation,
        activated_at_ms=freeze.frozen_at_ms - 1,
    )

    assert first.disposition is StreamFamilyProjectionDisposition.INSERTED
    assert second.disposition is StreamFamilyProjectionDisposition.INSERTED
    assert first.story_identity == second.story_identity
    assert second.narrative_identity is not None
