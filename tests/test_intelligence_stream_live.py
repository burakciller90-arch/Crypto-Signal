from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.product.intelligence_stream_live import (
    IntelligenceStreamLiveSession,
    resolve_stream_resume_cursor,
    stream_heartbeat_sse,
    stream_message_sse,
    stream_ready_sse,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
)
from crypto_signal.product.intelligence_stream_narrative import (
    STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamCursor,
    decode_stream_cursor,
    encode_stream_cursor,
)
from crypto_signal.product.web import create_app


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _initialize_stream_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE stream_narrative_plans (
                plan_identity TEXT PRIMARY KEY,
                fact_bundle_identity TEXT NOT NULL
            );
            CREATE TABLE stream_analytical_views (
                analytical_view_identity TEXT PRIMARY KEY,
                source_message_identity TEXT,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE stream_fact_bundles (
                fact_bundle_identity TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE stream_message_inputs (
                message_identity TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE stream_narrative_messages (
                narrative_identity TEXT PRIMARY KEY,
                plan_identity TEXT NOT NULL,
                analytical_view_identity TEXT NOT NULL,
                story_identity TEXT NOT NULL,
                source_event_identity TEXT NOT NULL,
                stream_event_identity TEXT NOT NULL,
                event_at_ms INTEGER NOT NULL,
                source_kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def _append_message(
    path: Path,
    *,
    seed: str,
    event_at_ms: int,
    symbol: str = "BTCUSDT",
    collapsed: str | None = None,
) -> str:
    plan_identity = _sha(f"{seed}-plan")
    analytical_identity = _sha(f"{seed}-analytical")
    fact_identity = _sha(f"{seed}-fact")
    message_identity = _sha(f"{seed}-message")
    story_identity = _sha(f"{seed}-story")
    source_event_identity = _sha(f"{seed}-source-event")
    stream_event_identity = _sha(f"{seed}-stream-event")
    payload_without_identity = {
        "plan_identity": plan_identity,
        "analytical_view_identity": analytical_identity,
        "fact_bundle_identity": fact_identity,
        "change_set_identity": _sha(f"{seed}-change"),
        "story_identity": story_identity,
        "source_event_identity": source_event_identity,
        "stream_event_identity": stream_event_identity,
        "symbol": symbol,
        "timeframe": "4h",
        "event_at_ms": event_at_ms,
        "source_kind": "deterministic",
        "fallback_reason_codes": (),
        "text": {
            "collapsed_text": collapsed or f"{symbol} 4h: {seed}.",
            "simple_text": collapsed or f"{symbol} 4h: {seed}.",
            "technical_text": f"{symbol} teknik kanıt.",
            "intelligence_text": f"{symbol} intelligence özeti.",
            "decision_text": f"{symbol} karar özeti.",
            "capital_text": "Bu mesajda yeni sanal sermaye referansı yok.",
        },
        "validation": {
            "valid": True,
            "violation_codes": (),
            "observed_numeric_values": (),
            "validator_version": "crypto-signal-narrative-validator-v1/1",
        },
        "original_text_preserved": True,
        "schema_version": STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION,
        "renderer_version": "crypto-signal-deterministic-tr-v1/1",
        "voice_version": "crypto-signal-turkish-analyst-v1/1",
        "engine_version": STREAM_ENGINE_VERSION,
        "read_only": True,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    narrative_identity = canonical_sha256(payload_without_identity)
    payload = {
        "narrative_identity": narrative_identity,
        **payload_without_identity,
    }
    payload_json = canonical_json(payload)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO stream_narrative_plans VALUES (?, ?)",
            (plan_identity, fact_identity),
        )
        connection.execute(
            "INSERT INTO stream_analytical_views VALUES (?, ?, ?)",
            (
                analytical_identity,
                message_identity,
                canonical_json({"stance": {"effective_stance": "watch"}}),
            ),
        )
        connection.execute(
            "INSERT INTO stream_fact_bundles VALUES (?, ?)",
            (
                fact_identity,
                canonical_json({"available_evidence_domains": ("frozen_chart",)}),
            ),
        )
        connection.execute(
            "INSERT INTO stream_message_inputs VALUES (?, ?)",
            (
                message_identity,
                canonical_json(
                    {
                        "category": "decision",
                        "importance": "important",
                    }
                ),
            ),
        )
        connection.execute(
            """
            INSERT INTO stream_narrative_messages
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                narrative_identity,
                plan_identity,
                analytical_identity,
                story_identity,
                source_event_identity,
                stream_event_identity,
                event_at_ms,
                "deterministic",
                payload_json,
                sha256_text(payload_json),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return narrative_identity


def _cursor(event_at_ms: int, narrative_identity: str) -> str:
    return encode_stream_cursor(
        StreamCursor(
            event_at_ms=event_at_ms,
            narrative_identity=narrative_identity,
        )
    )


def test_stream_live_session_anchors_existing_history_then_emits_only_new(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    _initialize_stream_db(path)
    old_identity = _append_message(path, seed="old", event_at_ms=1_000)
    reader = IntelligenceStreamReadModel(path)
    session = IntelligenceStreamLiveSession(reader)

    anchored = decode_stream_cursor(session.cursor)
    assert anchored.event_at_ms == 1_000
    assert anchored.narrative_identity == old_identity
    assert session.poll().items == ()

    new_identity = _append_message(path, seed="new", event_at_ms=2_000)
    first = session.poll()
    assert [item["narrative_identity"] for item in first.items] == [new_identity]
    assert decode_stream_cursor(first.cursor).narrative_identity == new_identity

    replay = session.poll()
    assert replay.items == ()
    assert replay.cursor == first.cursor


def test_stream_live_session_started_empty_does_not_lose_first_messages(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    _initialize_stream_db(path)
    session = IntelligenceStreamLiveSession(IntelligenceStreamReadModel(path))

    origin = decode_stream_cursor(session.cursor)
    assert origin.event_at_ms == 0
    assert origin.narrative_identity == "0" * 64

    first = _append_message(path, seed="first", event_at_ms=100)
    second = _append_message(path, seed="second", event_at_ms=200)
    poll = session.poll()
    assert [item["narrative_identity"] for item in poll.items] == [first, second]
    assert poll.has_more is False


def test_stream_live_reconnect_catches_up_without_duplicate(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    _initialize_stream_db(path)
    first = _append_message(path, seed="first", event_at_ms=1_000)
    second = _append_message(path, seed="second", event_at_ms=2_000)
    third = _append_message(path, seed="third", event_at_ms=3_000)

    reconnect = IntelligenceStreamLiveSession(
        IntelligenceStreamReadModel(path),
        after=_cursor(1_000, first),
    )
    batch = reconnect.poll(limit=1)
    assert [item["narrative_identity"] for item in batch.items] == [second]
    assert batch.has_more is True

    next_batch = reconnect.poll(limit=1)
    assert [item["narrative_identity"] for item in next_batch.items] == [third]
    assert next_batch.has_more is False

    assert reconnect.poll(limit=10).items == ()


def test_stream_resume_cursor_accepts_header_or_query_and_rejects_disagreement() -> None:
    value = _cursor(1_000, _sha("one"))
    other = _cursor(2_000, _sha("two"))

    assert resolve_stream_resume_cursor(after=value, last_event_id=None) == value
    assert resolve_stream_resume_cursor(after=None, last_event_id=value) == value
    assert resolve_stream_resume_cursor(after=value, last_event_id=value) == value

    with pytest.raises(ValueError, match="resume cursors disagree"):
        resolve_stream_resume_cursor(after=value, last_event_id=other)


def test_stream_sse_frames_keep_exact_cursor_and_payload() -> None:
    identity = _sha("message")
    item = {
        "narrative_identity": identity,
        "event_at_ms": 1_234,
        "symbol": "BTCUSDT",
        "text": {"collapsed_text": "BTCUSDT 4h: yeni mesaj."},
    }
    event, cursor = stream_message_sse(item)
    decoded = decode_stream_cursor(cursor)
    assert decoded.event_at_ms == 1_234
    assert decoded.narrative_identity == identity
    assert f"id: {cursor}\n" in event
    assert "event: message\n" in event
    assert f"data: {canonical_json(item)}\n\n" in event

    ready = stream_ready_sse(cursor)
    assert f"id: {cursor}\n" in ready
    assert "event: ready\n" in ready
    ready_data = next(
        line.removeprefix("data: ")
        for line in ready.splitlines()
        if line.startswith("data: ")
    )
    assert json.loads(ready_data)["cursor"] == cursor
    assert stream_heartbeat_sse().startswith(": crypto-signal-stream-keepalive")


def test_stream_live_api_is_get_only_and_fails_closed_without_runtime(tmp_path) -> None:
    missing = tmp_path / "missing-stream.sqlite3"
    app = create_app(
        tmp_path / "missing-signal-ledger.sqlite3",
        stream_ledger_path=missing,
    )
    client = TestClient(app)

    response = client.get("/api/stream/live")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["real_capital"] == 0
    assert client.post("/api/stream/live").status_code == 405
    assert not missing.exists()

    matching_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/stream/live"
    ]
    assert len(matching_routes) == 1
    assert getattr(matching_routes[0], "methods", set()) == {"GET"}
