from __future__ import annotations

import sqlite3
from pathlib import Path

from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_family import (
    IntelligenceStreamFamilyRuntime,
    StreamFamilyProjectionDisposition,
    build_family_snapshot,
)
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
)
from crypto_signal.product.intelligence_stream_models import (
    StreamCategory,
    StreamImportance,
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
