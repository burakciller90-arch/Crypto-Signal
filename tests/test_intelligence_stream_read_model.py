from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.product.intelligence_stream_analytical import (
    STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_family import (
    STREAM_FAMILY_NARRATIVE_MESSAGE_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_messages import (
    STREAM_FACT_BUNDLE_SCHEMA_VERSION,
    STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
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
    StreamMessageQuery,
    StreamReadModelError,
    decode_stream_cursor,
    encode_stream_cursor,
)
from crypto_signal.product.intelligence_stream_transport import (
    STREAM_SSE_RETRY_MS,
    cursor_for_stream_record,
    encode_stream_sse_heartbeat,
    encode_stream_sse_retry,
    read_stream_live_batch,
    resolve_stream_resume_cursor,
)
from crypto_signal.product.web import create_app


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _create_read_fixture(path: Path) -> dict[str, str]:
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
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );
            CREATE TABLE stream_fact_bundles (
                fact_bundle_identity TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );
            CREATE TABLE stream_message_inputs (
                message_identity TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
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
            story_identity = _sha(f"{name}-story")
            source_event_identity = _sha(f"{name}-source-event")
            stream_event_identity = _sha(f"{name}-stream-event")
            change_set_identity = _sha(f"{name}-change")

            family_names = (
                "geometry",
                "liquidity",
                "order_flow",
                "derivatives",
                "onchain",
            )
            family_contributions = tuple(
                {
                    "family": family,
                    "state": "observed",
                    "direction": item["stance"],
                    "support_points": 72 - index * 7,
                    "opposition_points": 9 + index * 3,
                    "evidence_quality_0_1": (
                        Decimal("0.91") - Decimal(index) * Decimal("0.06")
                    ),
                    "freshness_0_1": (
                        Decimal("0.95") - Decimal(index) * Decimal("0.05")
                    ),
                    "material_conflict_count": 1 if family == "derivatives" else 0,
                    "source_evidence_identities": (_sha(f"{name}-{family}-evidence"),),
                }
                for index, family in enumerate(family_names)
            )
            fact_without_identity = {
                "stream_event_identity": stream_event_identity,
                "source_event_identity": source_event_identity,
                "story_identity": story_identity,
                "decision_context_identity": _sha(f"{name}-decision-context"),
                "forecast_identity": _sha(f"{name}-forecast"),
                "proof_identity": _sha(f"{name}-proof"),
                "resolution_identity": None,
                "source_outcome_identity": None,
                "asset": str(item["symbol"]).replace("USDT", ""),
                "symbol": item["symbol"],
                "market": item["symbol"],
                "timeframe": item["timeframe"],
                "event_at_ms": item["event_at_ms"],
                "source_as_of_ms": item["event_at_ms"],
                "decision_source_as_of_ms": item["event_at_ms"],
                "decision_state": item["stance"],
                "direction": item["stance"],
                "confluence_support_score_0_100": 72,
                "confluence_opposition_score_0_100": 18,
                "confluence_resolution": "measured",
                "family_contributions": family_contributions,
                "event_context_state": "clear",
                "trigger_zone": {"low": 62000, "high": 62500},
                "target_zone": {"low": 65000, "high": 66000},
                "invalidation_price": 60750,
                "probability_status": "not_calibrated",
                "calibrated_probability_0_1": None,
                "freshness_0_1": Decimal("0.94"),
                "uncertainty_flags": ("probability_not_calibrated",),
                "available_evidence_domains": item["evidence"],
                "evidence_summary": {
                    "available_count": len(item["evidence"]),
                    "missing_count": 0,
                },
                "resolution_state": None,
                "source_outcome_state": None,
                "outcome_evidence_class": None,
                "resolution_reason_codes": (),
                "schema_version": STREAM_FACT_BUNDLE_SCHEMA_VERSION,
                "engine_version": STREAM_ENGINE_VERSION,
                "read_only": True,
                "production_authority": False,
                "real_capital": REAL_CAPITAL,
            }
            fact_identity = canonical_sha256(fact_without_identity)
            fact_payload = {"fact_bundle_identity": fact_identity, **fact_without_identity}

            message_without_identity = {
                "source_event_identity": source_event_identity,
                "stream_event_identity": stream_event_identity,
                "story_identity": story_identity,
                "fact_bundle_identity": fact_identity,
                "category": item["category"],
                "subtype": "fixture",
                "importance": item["importance"],
                "asset": str(item["symbol"]).replace("USDT", ""),
                "symbol": item["symbol"],
                "market": item["symbol"],
                "timeframe": item["timeframe"],
                "event_at_ms": item["event_at_ms"],
                "evidence_reference_identities": tuple(
                    _sha(f"{name}-{domain}-ref") for domain in item["evidence"]
                ),
                "capital_reference_identities": (),
                "schema_version": STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
                "engine_version": STREAM_ENGINE_VERSION,
                "read_only": True,
                "production_authority": False,
                "real_capital": REAL_CAPITAL,
            }
            message_identity = canonical_sha256(message_without_identity)
            message_payload = {"message_identity": message_identity, **message_without_identity}

            analytical_without_identity = {
                "policy_identity": _sha(f"{name}-policy"),
                "policy_version": "fixture-v1",
                "fact_bundle_identity": fact_identity,
                "change_set_identity": change_set_identity,
                "current_state_identity": _sha(f"{name}-state"),
                "source_message_identity": message_identity,
                "story_identity": story_identity,
                "source_event_identity": source_event_identity,
                "stream_event_identity": stream_event_identity,
                "asset": str(item["symbol"]).replace("USDT", ""),
                "symbol": item["symbol"],
                "timeframe": item["timeframe"],
                "event_at_ms": item["event_at_ms"],
                "stance": {
                    "effective_stance": item["stance"],
                    "direction": item["stance"],
                    "decision_state": item["stance"],
                    "stance_key": f"{item['stance']}:{item['stance']}",
                    "strength": "moderate",
                    "support_score_0_100": 72,
                    "opposition_score_0_100": 18,
                    "net_support_points": 54,
                },
                "dominant_support": family_contributions[0],
                "secondary_support": family_contributions[1],
                "main_contradiction": family_contributions[3],
                "uncertainty": {
                    "codes": ("probability_not_calibrated",),
                    "support_evidence_count": 3,
                    "contradict_evidence_count": 1,
                    "neutral_evidence_count": 1,
                    "insufficient_evidence_count": 0,
                    "available_evidence_count": 5,
                    "total_evidence_domain_count": 5,
                    "material_conflict_count": 1,
                    "probability_status": "not_calibrated",
                    "calibrated_probability_0_1": None,
                },
                "changed_codes": ("fixture_change",),
                "changed_families": ("geometry", "liquidity"),
                "next_condition": {
                    "kind": "entry_zone",
                    "state": "watch",
                    "low": 62000,
                    "high": 62500,
                    "price": None,
                    "reason_code": "fixture_entry_zone",
                },
                "invalidation_condition": {
                    "kind": "invalidation_price",
                    "state": "watch",
                    "low": None,
                    "high": None,
                    "price": 60750,
                    "reason_code": "fixture_invalidation",
                },
                "capital_consequence": {
                    "state": "not_bound",
                    "current_reference_identities": (),
                    "added_reference_identities": (),
                    "removed_reference_identities": (),
                },
                "materiality": {
                    "disposition": "publish",
                    "reason_codes": ("fixture_material",),
                },
                "schema_version": STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION,
                "engine_version": STREAM_ENGINE_VERSION,
                "read_only": True,
                "production_authority": False,
                "real_capital": REAL_CAPITAL,
            }
            analytical_identity = canonical_sha256(analytical_without_identity)
            analytical_payload = {
                "analytical_view_identity": analytical_identity,
                **analytical_without_identity,
            }

            payload_without_identity = {
                "plan_identity": plan_identity,
                "analytical_view_identity": analytical_identity,
                "fact_bundle_identity": fact_identity,
                "change_set_identity": change_set_identity,
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
            analytical_json = canonical_json(analytical_payload)
            fact_json = canonical_json(fact_payload)
            message_json = canonical_json(message_payload)
            connection.execute(
                """
                INSERT INTO stream_analytical_views (
                    analytical_view_identity,
                    source_message_identity,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    analytical_identity,
                    message_identity,
                    analytical_json,
                    sha256_text(analytical_json),
                ),
            )
            connection.execute(
                """
                INSERT INTO stream_fact_bundles (
                    fact_bundle_identity, payload_json, payload_sha256
                ) VALUES (?, ?, ?)
                """,
                (
                    fact_identity,
                    fact_json,
                    sha256_text(fact_json),
                ),
            )
            connection.execute(
                """
                INSERT INTO stream_message_inputs (
                    message_identity, payload_json, payload_sha256
                ) VALUES (?, ?, ?)
                """,
                (
                    message_identity,
                    message_json,
                    sha256_text(message_json),
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


def _insert_family_surface_fixture(
    path: Path,
    *,
    source_narrative_identity: str,
    family: str = "order_flow",
    state_label: str = "mixed",
    preserve_narrative_schema: bool = False,
) -> str:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT
                plan_identity,
                analytical_view_identity,
                story_identity,
                source_event_identity,
                stream_event_identity,
                event_at_ms,
                payload_json
            FROM stream_narrative_messages
            WHERE narrative_identity = ?
            """,
            (source_narrative_identity,),
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row[6]))
        assert isinstance(payload, dict)
        payload.pop("narrative_identity", None)
        if not preserve_narrative_schema:
            payload["schema_version"] = STREAM_FAMILY_NARRATIVE_MESSAGE_SCHEMA_VERSION
        payload["source_kind"] = "deterministic"
        payload["family"] = family
        payload["state_label"] = state_label
        family_identity = canonical_sha256(payload)
        encoded = canonical_json({"narrative_identity": family_identity, **payload})
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
                family_identity,
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                str(row[4]),
                int(str(row[5])),
                "deterministic",
                encoded,
                sha256_text(encoded),
            ),
        )
        connection.commit()
    return family_identity


def test_stream_cursor_round_trip_is_exact() -> None:
    from crypto_signal.product.intelligence_stream_read_model import StreamCursor

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
        analytical_json = canonical_json(
            {"stance": {"effective_stance": "watch"}}
        )
        fact_json = canonical_json(
            {"available_evidence_domains": ("frozen_chart",)}
        )
        connection.execute(
            "INSERT INTO stream_analytical_views VALUES (?, ?, ?, ?)",
            (
                raw["analytical_view_identity"],
                None,
                analytical_json,
                sha256_text(analytical_json),
            ),
        )
        connection.execute(
            "INSERT INTO stream_fact_bundles VALUES (?, ?, ?)",
            (
                raw["fact_bundle_identity"],
                fact_json,
                sha256_text(fact_json),
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

    state_filtered = reader.read_messages(
        StreamMessageQuery(limit=20, state="watch")
    )
    stance_filtered = reader.read_messages(
        StreamMessageQuery(limit=20, effective_stance="watch")
    )
    assert [
        item["narrative_identity"] for item in state_filtered.items
    ] == [
        item["narrative_identity"] for item in stance_filtered.items
    ]

    vault_filtered = reader.read_messages(
        StreamMessageQuery(limit=20, vault="CORE")
    )
    assert vault_filtered.items == ()

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


def test_stream_exact_detail_projects_persisted_depth_without_recompute(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(path)
    reader = IntelligenceStreamReadModel(path)

    detail = reader.read_message_detail(identities["btc-issued"])
    assert detail is not None
    assert detail["read_only"] is True
    assert detail["production_authority"] is False
    assert detail["real_capital"] == 0

    narrative = detail["narrative"]
    analytical = detail["analytical_view"]
    fact = detail["fact_bundle"]
    message_input = detail["message_input"]

    assert narrative["narrative_identity"] == identities["btc-issued"]
    assert narrative["fact_bundle_identity"] == fact["fact_bundle_identity"]
    assert (
        narrative["analytical_view_identity"]
        == analytical["analytical_view_identity"]
    )
    assert analytical["fact_bundle_identity"] == fact["fact_bundle_identity"]
    assert fact["proof_identity"]
    assert len(fact["family_contributions"]) == 5
    assert fact["trigger_zone"] == {"high": 62500, "low": 62000}
    assert fact["target_zone"] == {"high": 66000, "low": 65000}
    assert fact["invalidation_price"] == 60750
    assert analytical["next_condition"]["kind"] == "entry_zone"
    assert analytical["capital_consequence"]["state"] == "not_bound"
    assert message_input is not None
    assert message_input["message_identity"] == analytical["source_message_identity"]
    assert reader.read_message_detail(_sha("missing-detail")) is None


def test_stream_exact_detail_fails_closed_on_persisted_tamper(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(path)
    reader = IntelligenceStreamReadModel(path)

    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            """
            SELECT p.fact_bundle_identity
            FROM stream_narrative_messages AS n
            JOIN stream_narrative_plans AS p
              ON p.plan_identity = n.plan_identity
            WHERE n.narrative_identity = ?
            """,
            (identities["btc-issued"],),
        ).fetchone()
        assert row is not None
        connection.execute(
            """
            UPDATE stream_fact_bundles
            SET payload_json = ?
            WHERE fact_bundle_identity = ?
            """,
            ('{"tampered":true}', str(row[0])),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StreamReadModelError, match="persisted payload digest"):
        reader.read_message_detail(identities["btc-issued"])


def test_stream_primary_surface_hides_family_telemetry_without_deleting_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(path)
    family_identity = _insert_family_surface_fixture(
        path,
        source_narrative_identity=identities["btc-flow"],
    )
    reader = IntelligenceStreamReadModel(path)

    all_page = reader.read_messages(StreamMessageQuery(limit=20))
    all_ids = {item["narrative_identity"] for item in all_page.items}
    assert family_identity in all_ids

    primary_page = reader.read_messages(
        StreamMessageQuery(limit=20, primary_surface=True)
    )
    primary_ids = {item["narrative_identity"] for item in primary_page.items}
    assert family_identity not in primary_ids
    assert identities["btc-issued"] in primary_ids
    assert identities["eth-outcome"] in primary_ids
    assert identities["btc-flow"] in primary_ids

    trust_identity = _insert_family_surface_fixture(
        path,
        source_narrative_identity=identities["eth-outcome"],
        family="event_risk",
        state_label="event_block",
    )
    primary_with_trust = reader.read_messages(
        StreamMessageQuery(limit=20, primary_surface=True)
    )
    assert trust_identity in {
        item["narrative_identity"] for item in primary_with_trust.items
    }

    family_record = reader.read_message(family_identity)
    assert family_record is not None
    assert (
        family_record["schema_version"]
        == STREAM_FAMILY_NARRATIVE_MESSAGE_SCHEMA_VERSION
    )


def test_stream_primary_surface_hides_family_even_with_legacy_narrative_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(path)
    family_identity = _insert_family_surface_fixture(
        path,
        source_narrative_identity=identities["btc-flow"],
        family="order_flow_absorption",
        state_label="sell_pressure",
        preserve_narrative_schema=True,
    )
    reader = IntelligenceStreamReadModel(path)

    all_ids = {
        item["narrative_identity"]
        for item in reader.read_messages(StreamMessageQuery(limit=20)).items
    }
    assert family_identity in all_ids

    primary_ids = {
        item["narrative_identity"]
        for item in reader.read_messages(
            StreamMessageQuery(limit=20, primary_surface=True)
        ).items
    }
    assert family_identity not in primary_ids
    assert identities["btc-flow"] in primary_ids


def test_stream_primary_surface_hides_canonical_production_family_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(path)
    canonical_families = (
        "geometry_pa_elliott_harmonic",
        "liquidity",
        "order_flow_absorption",
        "derivatives",
        "onchain_smart_money",
    )
    family_ids = {
        _insert_family_surface_fixture(
            path,
            source_narrative_identity=identities["btc-flow"],
            family=family,
            state_label="mixed",
        )
        for family in canonical_families
    }

    reader = IntelligenceStreamReadModel(path)
    all_ids = {
        item["narrative_identity"]
        for item in reader.read_messages(StreamMessageQuery(limit=20)).items
    }
    assert family_ids <= all_ids

    primary_ids = {
        item["narrative_identity"]
        for item in reader.read_messages(
            StreamMessageQuery(limit=20, primary_surface=True)
        ).items
    }
    assert family_ids.isdisjoint(primary_ids)

    trust_id = _insert_family_surface_fixture(
        path,
        source_narrative_identity=identities["eth-outcome"],
        family="provider_quality",
        state_label="degraded_provider_stale",
    )
    primary_with_trust = {
        item["narrative_identity"]
        for item in reader.read_messages(
            StreamMessageQuery(limit=20, primary_surface=True)
        ).items
    }
    assert trust_id in primary_with_trust



def test_stream_read_model_is_read_only_and_missing_db_is_not_initialized(tmp_path) -> None:
    missing = tmp_path / "missing.sqlite3"
    reader = IntelligenceStreamReadModel(missing)
    with pytest.raises(FileNotFoundError):
        reader.read_messages(StreamMessageQuery())
    assert not missing.exists()


def test_stream_api_primary_surface_hides_family_telemetry(
    tmp_path: Path,
) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(stream_path)
    family_identity = _insert_family_surface_fixture(
        stream_path,
        source_narrative_identity=identities["btc-flow"],
    )
    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=stream_path,
        )
    )

    all_response = client.get(
        "/api/stream/messages",
        params={"limit": 20, "surface": "all"},
    )
    assert all_response.status_code == 200
    all_ids = {
        item["narrative_identity"]
        for item in all_response.json()["page"]["items"]
    }
    assert family_identity in all_ids

    primary = client.get(
        "/api/stream/messages",
        params={"limit": 20, "surface": "primary"},
    )
    assert primary.status_code == 200
    primary_ids = {
        item["narrative_identity"]
        for item in primary.json()["page"]["items"]
    }
    assert family_identity not in primary_ids
    assert identities["btc-issued"] in primary_ids
    assert identities["btc-flow"] in primary_ids


    trust_identity = _insert_family_surface_fixture(
        stream_path,
        source_narrative_identity=identities["eth-outcome"],
        family="provider_quality",
        state_label="degraded_provider_stale",
    )
    primary_after_trust = client.get(
        "/api/stream/messages",
        params={"limit": 20, "surface": "primary"},
    )
    assert trust_identity in {
        item["narrative_identity"]
        for item in primary_after_trust.json()["page"]["items"]
    }


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

    state_filtered = client.get(
        "/api/stream/messages",
        params={"state": "watch"},
    )
    assert state_filtered.status_code == 200
    assert identities["btc-flow"] in {
        item["narrative_identity"]
        for item in state_filtered.json()["page"]["items"]
    }

    vault_filtered = client.get(
        "/api/stream/messages",
        params={"vault": "CORE"},
    )
    assert vault_filtered.status_code == 200
    assert vault_filtered.json()["page"]["items"] == []

    exact = client.get(f"/api/stream/messages/{identities['eth-outcome']}")
    assert exact.status_code == 200
    assert exact.json()["status"] == "ready"
    assert exact.json()["message"]["symbol"] == "ETHUSDT"

    detail = client.get(
        f"/api/stream/messages/{identities['btc-issued']}/detail"
    )
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["status"] == "ready"
    assert detail_payload["detail"]["fact_bundle"]["proof_identity"]
    assert len(detail_payload["detail"]["fact_bundle"]["family_contributions"]) == 5
    assert detail_payload["detail"]["real_capital"] == 0

    invalid = client.get("/api/stream/messages?before=not-a-cursor")
    assert invalid.status_code == 400

    family_identity = _insert_family_surface_fixture(
        stream_path,
        source_narrative_identity=identities["btc-flow"],
    )
    all_surface = client.get(
        "/api/stream/messages",
        params={"limit": 20, "surface": "all"},
    )
    assert all_surface.status_code == 200
    assert family_identity in {
        item["narrative_identity"]
        for item in all_surface.json()["page"]["items"]
    }

    primary = client.get(
        "/api/stream/messages",
        params={"limit": 20, "surface": "primary"},
    )
    assert primary.status_code == 200
    primary_ids = {
        item["narrative_identity"]
        for item in primary.json()["page"]["items"]
    }
    assert family_identity not in primary_ids
    assert identities["btc-issued"] in primary_ids


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


def test_stream_sse_empty_first_connection_catches_first_future_message(tmp_path) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(stream_path)

    connection = sqlite3.connect(stream_path)
    try:
        saved = connection.execute(
            """
            SELECT narrative_identity, plan_identity, analytical_view_identity,
                   story_identity, source_event_identity, stream_event_identity,
                   event_at_ms, source_kind, payload_json, payload_sha256
            FROM stream_narrative_messages
            WHERE narrative_identity = ?
            """,
            (identities["btc-issued"],),
        ).fetchone()
        assert saved is not None
        connection.execute("DELETE FROM stream_narrative_messages")
        connection.commit()
    finally:
        connection.close()

    reader = IntelligenceStreamReadModel(stream_path)
    origin = resolve_stream_resume_cursor(
        reader=reader,
        after=None,
        last_event_id=None,
    )
    assert origin is not None
    decoded_origin = decode_stream_cursor(origin)
    assert decoded_origin.event_at_ms == 0
    assert decoded_origin.narrative_identity == "0" * 64

    connection = sqlite3.connect(stream_path)
    try:
        connection.execute(
            """
            INSERT INTO stream_narrative_messages
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            saved,
        )
        connection.commit()
    finally:
        connection.close()

    batch = read_stream_live_batch(
        reader,
        StreamMessageQuery(limit=200),
        after_cursor=origin,
    )
    assert [event.data["narrative_identity"] for event in batch.events] == [
        identities["btc-issued"]
    ]
    assert batch.next_cursor == batch.events[-1].event_id


def test_stream_sse_transport_helpers_are_deterministic() -> None:
    assert encode_stream_sse_retry() == f"retry: {STREAM_SSE_RETRY_MS}\n\n"
    assert encode_stream_sse_heartbeat(now_ms=1234) == ": heartbeat 1234\n\n"
    with pytest.raises(ValueError, match="heartbeat time"):
        encode_stream_sse_heartbeat(now_ms=-1)


def test_stream_sse_first_connection_tails_without_replaying_history(tmp_path) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    _create_read_fixture(stream_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=stream_path,
        )
    )

    response = client.get("/api/stream/live", params={"follow": "false"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.text == f"retry: {STREAM_SSE_RETRY_MS}\n\n"


def test_stream_sse_after_cursor_catches_up_without_duplicates(tmp_path) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(stream_path)
    reader = IntelligenceStreamReadModel(stream_path)
    eth = reader.read_message(identities["eth-outcome"])
    assert eth is not None
    after = cursor_for_stream_record(eth)

    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=stream_path,
        )
    )
    response = client.get(
        "/api/stream/live",
        params={"after": after, "follow": "false"},
    )
    assert response.status_code == 200
    body = response.text
    assert body.count("event: message\n") == 2
    assert identities["eth-outcome"] not in body
    assert body.count(identities["btc-flow"]) == 1
    assert body.count(identities["sol-issued"]) == 1
    assert body.index(identities["btc-flow"]) < body.index(identities["sol-issued"])


def test_stream_sse_last_event_id_resumes_exactly_after_delivered_message(tmp_path) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(stream_path)
    reader = IntelligenceStreamReadModel(stream_path)
    btc_flow = reader.read_message(identities["btc-flow"])
    assert btc_flow is not None
    last_event_id = cursor_for_stream_record(btc_flow)

    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=stream_path,
        )
    )
    response = client.get(
        "/api/stream/live",
        params={"follow": "false"},
        headers={"Last-Event-ID": last_event_id},
    )
    assert response.status_code == 200
    assert response.text.count("event: message\n") == 1
    assert identities["btc-flow"] not in response.text
    assert response.text.count(identities["sol-issued"]) == 1


def test_stream_sse_reconnect_prefers_newer_resume_boundary(tmp_path) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(stream_path)
    reader = IntelligenceStreamReadModel(stream_path)
    eth = reader.read_message(identities["eth-outcome"])
    btc_flow = reader.read_message(identities["btc-flow"])
    assert eth is not None
    assert btc_flow is not None

    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=stream_path,
        )
    )
    response = client.get(
        "/api/stream/live",
        params={
            "after": cursor_for_stream_record(eth),
            "follow": "false",
        },
        headers={"Last-Event-ID": cursor_for_stream_record(btc_flow)},
    )
    assert response.status_code == 200
    assert identities["btc-flow"] not in response.text
    assert response.text.count(identities["sol-issued"]) == 1

    older_header = client.get(
        "/api/stream/live",
        params={
            "after": cursor_for_stream_record(btc_flow),
            "follow": "false",
        },
        headers={"Last-Event-ID": cursor_for_stream_record(eth)},
    )
    assert older_header.status_code == 200
    assert identities["btc-flow"] not in older_header.text
    assert older_header.text.count(identities["sol-issued"]) == 1


def test_stream_sse_filters_match_polling_contract(tmp_path) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    identities = _create_read_fixture(stream_path)
    reader = IntelligenceStreamReadModel(stream_path)
    issued = reader.read_message(identities["btc-issued"])
    assert issued is not None
    after = cursor_for_stream_record(issued)

    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=stream_path,
        )
    )
    params = {
        "after": after,
        "follow": "false",
        "symbol": "BTCUSDT",
        "timeframe": "4h",
        "evidence_domain": "order_flow_cvd",
        "text": "emir akışı",
    }
    sse = client.get("/api/stream/live", params=params)
    polling = client.get(
        "/api/stream/messages",
        params={key: value for key, value in params.items() if key != "follow"},
    )
    assert sse.status_code == 200
    assert polling.status_code == 200
    assert sse.text.count(identities["btc-flow"]) == 1
    assert [
        item["narrative_identity"]
        for item in polling.json()["page"]["items"]
    ] == [identities["btc-flow"]]


def test_stream_sse_fails_closed_when_runtime_is_missing(tmp_path) -> None:
    missing_stream = tmp_path / "missing-stream.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signal-ledger.sqlite3",
            stream_ledger_path=missing_stream,
        )
    )
    response = client.get("/api/stream/live", params={"follow": "false"})
    assert response.status_code == 503
    assert response.json()["detail"] == "intelligence_stream_runtime_not_configured"
    assert not missing_stream.exists()
