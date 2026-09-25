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
    StreamMessageQuery,
    StreamReadModelError,
    decode_stream_cursor,
    encode_stream_cursor,
)
from crypto_signal.product.intelligence_stream_realtime import (
    IntelligenceStreamRealtime,
    StreamRealtimeConfig,
    cursor_for_stream_record,
    encode_sse_heartbeat,
    encode_sse_message,
    encode_sse_ready,
)
from crypto_signal.product.web import create_app


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _create_read_fixture(
    path: Path,
    *,
    activated_at_ms: int = 500,
) -> dict[str, str]:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE stream_activation (
                activation_identity TEXT PRIMARY KEY,
                activated_at_ms INTEGER NOT NULL UNIQUE
            );
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
        connection.execute(
            """
            INSERT INTO stream_activation (
                activation_identity,
                activated_at_ms
            ) VALUES (?, ?)
            """,
            (_sha("activation"), activated_at_ms),
        )
        identities: dict[str, str] = {}
        rows = (
            {
                "name": "btc-issued",
                "event_at_ms": 1_000,
                "symbol": "BTCUSDT",
                "timeframe": "4h",
                "source_kind": "deterministic",
                "stance": "bullish",
                "category": "decision",
                "importance": "important",
                "evidence": ("frozen_chart", "liquidity_map"),
                "collapsed": "BTCUSDT 4h: Likidite desteği güçlü ve tetik bölgesini izliyorum.",
            },
            {
                "name": "eth-outcome",
                "event_at_ms": 2_000,
                "symbol": "ETHUSDT",
                "timeframe": "1h",
                "source_kind": "deterministic",
                "stance": "resolved",
                "category": "outcome",
                "importance": "important",
                "evidence": ("frozen_chart",),
                "collapsed": "ETHUSDT 1h: Önceki beklentinin sonucu kayda geçti.",
            },
            {
                "name": "btc-flow",
                "event_at_ms": 3_000,
                "symbol": "BTCUSDT",
                "timeframe": "4h",
                "source_kind": "local_rewrite",
                "stance": "watch",
                "category": "decision",
                "importance": "important",
                "evidence": ("order_flow_cvd",),
                "collapsed": "BTCUSDT 4h: Emir akışı teyidi zayıfladı; şimdilik izliyorum.",
            },
            {
                "name": "sol-issued",
                "event_at_ms": 4_000,
                "symbol": "SOLUSDT",
                "timeframe": "15m",
                "source_kind": "deterministic",
                "stance": "bearish",
                "category": "decision",
                "importance": "routine",
                "evidence": ("frozen_chart",),
                "collapsed": "SOLUSDT 15m: Aşağı yönlü görüş önde fakat teyit orta kuvvette.",
            },
        )
        for item in rows:
            name = str(item["name"])
            plan_identity = _sha(f"{name}-plan")
            analytical_identity = _sha(f"{name}-analytical")
            fact_identity = _sha(f"{name}-fact")
            message_identity = _sha(f"{name}-message")
            story_identity = _sha(f"{name}-story")
            source_event_identity = _sha(f"{name}-source-event")
            stream_event_identity = _sha(f"{name}-stream-event")

            payload_without_identity = {
                "plan_identity": plan_identity,
                "analytical_view_identity": analytical_identity,
                "fact_bundle_identity": fact_identity,
                "change_set_identity": _sha(f"{name}-change"),
                "story_identity": story_identity,
                "source_event_identity": source_event_identity,
                "stream_event_identity": stream_event_identity,
                "symbol": item["symbol"],
                "timeframe": item["timeframe"],
                "event_at_ms": item["event_at_ms"],
                "source_kind": item["source_kind"],
                "fallback_reason_codes": (),
                "text": {
                    "collapsed_text": item["collapsed"],
                    "simple_text": item["collapsed"],
                    "technical_text": f"{item['symbol']} teknik kanıt.",
                    "intelligence_text": f"{item['symbol']} intelligence özeti.",
                    "decision_text": f"{item['symbol']} karar özeti.",
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

            connection.execute(
                """
                INSERT INTO stream_narrative_plans (
                    plan_identity, fact_bundle_identity
                ) VALUES (?, ?)
                """,
                (plan_identity, fact_identity),
            )
            connection.execute(
                """
                INSERT INTO stream_analytical_views (
                    analytical_view_identity, source_message_identity, payload_json
                ) VALUES (?, ?, ?)
                """,
                (
                    analytical_identity,
                    message_identity,
                    canonical_json(
                        {
                            "stance": {"effective_stance": item["stance"]},
                        }
                    ),
                ),
            )
            connection.execute(
                """
                INSERT INTO stream_fact_bundles (
                    fact_bundle_identity, payload_json
                ) VALUES (?, ?)
                """,
                (
                    fact_identity,
                    canonical_json(
                        {
                            "available_evidence_domains": item["evidence"],
                        }
                    ),
                ),
            )
            connection.execute(
                """
                INSERT INTO stream_message_inputs (
                    message_identity, payload_json
                ) VALUES (?, ?)
                """,
                (
                    message_identity,
                    canonical_json(
                        {
                            "category": item["category"],
                            "importance": item["importance"],
                        }
                    ),
                ),
            )
            connection.execute(
                """
                INSERT INTO stream_narrative_messages (
                    narrative_identity,
                    plan_identity,
                    analytical_view_identity,
                    story_identity,
                    source_event_identity,
                    stream_event_identity,
                    event_at_ms,
                    source_kind,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    narrative_identity,
                    plan_identity,
                    analytical_identity,
                    story_identity,
                    source_event_identity,
                    stream_event_identity,
                    item["event_at_ms"],
                    item["source_kind"],
                    payload_json,
                    sha256_text(payload_json),
                ),
            )
            identities[name] = narrative_identity
            identities[f"{name}-story"] = story_identity
        connection.commit()
        return identities
    finally:
        connection.close()


def test_stream_cursor_round_trip_is_exact() -> None:
    cursor = StreamCursor(
        event_at_ms=1234,
        narrative_identity=_sha("cursor"),
    )
    encoded = encode_stream_cursor(cursor)
    assert decode_stream_cursor(encoded) == cursor

    with pytest.raises(StreamReadModelError, match="invalid Stream cursor"):
        decode_stream_cursor("not-a-valid-cursor")


def test_stream_history_uses_stable_keyset_cursors(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(path)
    reader = IntelligenceStreamReadModel(path)

    first = reader.read_messages(StreamMessageQuery(limit=2))
    assert first.order == "newest_to_oldest"
    assert [item["narrative_identity"] for item in first.items] == [
        identities["sol-issued"],
        identities["btc-flow"],
    ]
    assert first.has_more is True
    assert first.oldest_cursor is not None

    older = reader.read_messages(
        StreamMessageQuery(
            limit=2,
            before=decode_stream_cursor(first.oldest_cursor),
        )
    )
    assert [item["narrative_identity"] for item in older.items] == [
        identities["eth-outcome"],
        identities["btc-issued"],
    ]
    assert older.has_more is False

    after_eth = encode_stream_cursor(
        decode_stream_cursor(older.newest_cursor or "")
    )
    catch_up = reader.read_messages(
        StreamMessageQuery(
            limit=10,
            after=decode_stream_cursor(after_eth),
        )
    )
    assert catch_up.order == "oldest_to_newest"
    assert [item["narrative_identity"] for item in catch_up.items] == [
        identities["btc-flow"],
        identities["sol-issued"],
    ]


def test_stream_old_history_cursor_does_not_shift_when_new_message_arrives(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(path)
    reader = IntelligenceStreamReadModel(path)
    first = reader.read_messages(StreamMessageQuery(limit=2))
    assert first.oldest_cursor is not None

    connection = sqlite3.connect(path)
    try:
        source = connection.execute(
            """
            SELECT plan_identity, analytical_view_identity, story_identity,
                   source_event_identity, stream_event_identity, source_kind,
                   payload_json
            FROM stream_narrative_messages
            WHERE narrative_identity = ?
            """,
            (identities["sol-issued"],),
        ).fetchone()
        assert source is not None
        raw = json.loads(str(source[6]))
        raw["event_at_ms"] = 5_000
        raw["source_event_identity"] = _sha("new-source")
        raw["stream_event_identity"] = _sha("new-stream")
        raw["story_identity"] = _sha("new-story")
        raw["plan_identity"] = _sha("new-plan")
        raw["analytical_view_identity"] = _sha("new-analytical")
        raw["fact_bundle_identity"] = _sha("new-fact")
        raw.pop("narrative_identity")
        narrative_identity = canonical_sha256(raw)
        payload = {"narrative_identity": narrative_identity, **raw}
        payload_json = canonical_json(payload)
        connection.execute(
            "INSERT INTO stream_narrative_plans VALUES (?, ?)",
            (raw["plan_identity"], raw["fact_bundle_identity"]),
        )
        connection.execute(
            "INSERT INTO stream_analytical_views VALUES (?, ?, ?)",
            (
                raw["analytical_view_identity"],
                None,
                canonical_json({"stance": {"effective_stance": "watch"}}),
            ),
        )
        connection.execute(
            "INSERT INTO stream_fact_bundles VALUES (?, ?)",
            (
                raw["fact_bundle_identity"],
                canonical_json({"available_evidence_domains": ("frozen_chart",)}),
            ),
        )
        connection.execute(
            """
            INSERT INTO stream_narrative_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                narrative_identity,
                raw["plan_identity"],
                raw["analytical_view_identity"],
                raw["story_identity"],
                raw["source_event_identity"],
                raw["stream_event_identity"],
                5_000,
                raw["source_kind"],
                payload_json,
                sha256_text(payload_json),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    older = reader.read_messages(
        StreamMessageQuery(
            limit=10,
            before=decode_stream_cursor(first.oldest_cursor),
        )
    )
    assert [item["narrative_identity"] for item in older.items] == [
        identities["eth-outcome"],
        identities["btc-issued"],
    ]


def test_stream_filters_and_exact_lookup(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(path)
    reader = IntelligenceStreamReadModel(path)

    filtered = reader.read_messages(
        StreamMessageQuery(
            limit=20,
            symbol="BTCUSDT",
            timeframe="4h",
            category="decision",
            importance="important",
            evidence_domain="order_flow_cvd",
            effective_stance="watch",
            source_kind="local_rewrite",
            text="emir akışı",
        )
    )
    assert len(filtered.items) == 1
    assert filtered.items[0]["narrative_identity"] == identities["btc-flow"]

    exact = reader.read_message(identities["eth-outcome"])
    assert exact is not None
    assert exact["symbol"] == "ETHUSDT"
    assert reader.read_message(_sha("missing")) is None

    story = reader.read_messages(
        StreamMessageQuery(
            story_identity=identities["btc-issued-story"],
        )
    )
    assert len(story.items) == 1
    assert story.items[0]["narrative_identity"] == identities["btc-issued"]


def test_stream_read_model_is_read_only_and_missing_db_is_not_initialized(tmp_path) -> None:
    missing = tmp_path / "missing.sqlite3"
    reader = IntelligenceStreamReadModel(missing)
    with pytest.raises(FileNotFoundError):
        reader.read_messages(StreamMessageQuery())
    assert not missing.exists()


def test_stream_api_exposes_cursor_history_search_and_lookup(tmp_path) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(stream_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=stream_path,
        )
    )

    first = client.get("/api/stream/messages?limit=2")
    assert first.status_code == 200
    payload = first.json()
    assert payload["status"] == "ready"
    assert len(payload["page"]["items"]) == 2
    assert payload["page"]["order"] == "newest_to_oldest"
    before = payload["page"]["oldest_cursor"]
    assert isinstance(before, str)

    older = client.get("/api/stream/messages", params={"limit": 10, "before": before})
    assert older.status_code == 200
    assert len(older.json()["page"]["items"]) == 2

    filtered = client.get(
        "/api/stream/messages",
        params={
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "evidence_domain": "order_flow_cvd",
            "text": "emir akışı",
        },
    )
    assert filtered.status_code == 200
    assert [
        item["narrative_identity"]
        for item in filtered.json()["page"]["items"]
    ] == [identities["btc-flow"]]

    exact = client.get(f"/api/stream/messages/{identities['eth-outcome']}")
    assert exact.status_code == 200
    assert exact.json()["status"] == "ready"
    assert exact.json()["message"]["symbol"] == "ETHUSDT"

    invalid = client.get("/api/stream/messages?before=not-a-cursor")
    assert invalid.status_code == 400


def test_stream_api_fails_closed_when_runtime_not_configured(tmp_path) -> None:
    missing_stream = tmp_path / "missing-stream.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=missing_stream,
        )
    )
    response = client.get("/api/stream/messages")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["page"]["items"] == []
    assert not missing_stream.exists()


def test_stream_read_model_enforces_activation_boundary(tmp_path) -> None:
    path = tmp_path / "stream-activation.sqlite3"
    identities = _create_read_fixture(path, activated_at_ms=2_500)
    reader = IntelligenceStreamReadModel(path)

    page = reader.read_messages(StreamMessageQuery(limit=20))
    assert [item["narrative_identity"] for item in page.items] == [
        identities["sol-issued"],
        identities["btc-flow"],
    ]
    assert reader.read_message(identities["eth-outcome"]) is None
    assert reader.activation_boundary_ms() == 2_500


def test_stream_live_session_catches_up_without_duplicates(tmp_path) -> None:
    path = tmp_path / "stream-live.sqlite3"
    identities = _create_read_fixture(path)
    realtime = IntelligenceStreamRealtime(
        path,
        config=StreamRealtimeConfig(
            poll_interval_ms=100,
            heartbeat_ms=1_000,
            retry_ms=500,
            batch_limit=20,
        ),
    )
    resume = encode_stream_cursor(
        StreamCursor(
            event_at_ms=2_000,
            narrative_identity=identities["eth-outcome"],
        )
    )

    batch = realtime.poll_after(resume)
    assert [item["narrative_identity"] for item in batch.items] == [
        identities["btc-flow"],
        identities["sol-issued"],
    ]
    assert decode_stream_cursor(batch.end_cursor).narrative_identity == (
        identities["sol-issued"]
    )

    replay_after_latest = realtime.poll_after(batch.end_cursor)
    assert replay_after_latest.items == ()
    assert replay_after_latest.end_cursor == batch.end_cursor

    resumed = realtime.resolve_start_cursor(batch.end_cursor)
    assert resumed == batch.end_cursor


def test_stream_live_fresh_connection_starts_at_latest_not_history(tmp_path) -> None:
    path = tmp_path / "stream-live-start.sqlite3"
    identities = _create_read_fixture(path)
    realtime = IntelligenceStreamRealtime(path)

    start = realtime.resolve_start_cursor(None)
    assert decode_stream_cursor(start).narrative_identity == identities["sol-issued"]
    assert realtime.poll_after(start).items == ()


def test_stream_live_empty_connection_uses_activation_cursor(tmp_path) -> None:
    path = tmp_path / "stream-live-empty.sqlite3"
    _create_read_fixture(path, activated_at_ms=750)
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM stream_narrative_messages")
        connection.commit()

    realtime = IntelligenceStreamRealtime(path)
    start = decode_stream_cursor(realtime.resolve_start_cursor(None))
    assert start.event_at_ms == 750
    assert start.narrative_identity == "0" * 64


def test_stream_live_rejects_pre_activation_resume_cursor(tmp_path) -> None:
    path = tmp_path / "stream-live-boundary.sqlite3"
    _create_read_fixture(path, activated_at_ms=500)
    realtime = IntelligenceStreamRealtime(path)
    stale = encode_stream_cursor(
        StreamCursor(
            event_at_ms=499,
            narrative_identity=_sha("pre-activation-cursor"),
        )
    )
    with pytest.raises(
        StreamReadModelError,
        match="predates activation boundary",
    ):
        realtime.resolve_start_cursor(stale)


def test_stream_sse_encoding_binds_event_id_to_exact_message(tmp_path) -> None:
    path = tmp_path / "stream-sse.sqlite3"
    identities = _create_read_fixture(path)
    reader = IntelligenceStreamReadModel(path)
    message = reader.read_message(identities["btc-flow"])
    assert message is not None

    cursor = cursor_for_stream_record(message)
    ready = encode_sse_ready(cursor, retry_ms=2_000)
    assert f"id: {cursor}\n" in ready
    assert "event: ready\n" in ready
    assert "retry: 2000\n" in ready

    event = encode_sse_message(message, cursor=cursor)
    assert f"id: {cursor}\n" in event
    assert "event: message\n" in event
    data_line = next(
        line.removeprefix("data: ")
        for line in event.splitlines()
        if line.startswith("data: ")
    )
    payload = json.loads(data_line)
    assert payload["cursor"] == cursor
    assert payload["message"]["narrative_identity"] == identities["btc-flow"]
    assert payload["real_capital"] == 0
    assert encode_sse_heartbeat() == ": heartbeat\n\n"

    wrong_cursor = encode_stream_cursor(
        StreamCursor(
            event_at_ms=message["event_at_ms"],
            narrative_identity=_sha("wrong-sse-message"),
        )
    )
    with pytest.raises(
        StreamReadModelError,
        match="cursor/message identity mismatch",
    ):
        encode_sse_message(message, cursor=wrong_cursor)


def test_stream_live_api_rejects_invalid_or_conflicting_resume_cursor(tmp_path) -> None:
    stream_path = tmp_path / "stream-live-api.sqlite3"
    identities = _create_read_fixture(stream_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=stream_path,
        )
    )

    invalid = client.get("/api/stream/live", params={"after": "not-a-cursor"})
    assert invalid.status_code == 400

    after = encode_stream_cursor(
        StreamCursor(
            event_at_ms=2_000,
            narrative_identity=identities["eth-outcome"],
        )
    )
    different = encode_stream_cursor(
        StreamCursor(
            event_at_ms=3_000,
            narrative_identity=identities["btc-flow"],
        )
    )
    conflict = client.get(
        "/api/stream/live",
        params={"after": after},
        headers={"Last-Event-ID": different},
    )
    assert conflict.status_code == 400


def test_stream_live_api_fails_closed_when_runtime_not_configured(tmp_path) -> None:
    missing_stream = tmp_path / "missing-stream-live.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=missing_stream,
        )
    )
    response = client.get("/api/stream/live")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["transport"] == "sse"
    assert not missing_stream.exists()
