from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict
from pathlib import Path

from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.product.final_product_read_model import FinalProductReadModel
from crypto_signal.product.intelligence_stream_system_view import (
    STREAM_SYSTEM_VIEW_SCHEMA_VERSION,
)


def _sha(label: str) -> str:
    return canonical_sha256({"label": label})


def _family_rows() -> tuple[dict[str, object], ...]:
    return (
        {
            "direction": "bullish",
            "evidence_domains": ("geometry",),
            "family": "geometry",
            "material_conflict_count": 0,
            "opposition_points": "0.00",
            "prior_weight": "0.20",
            "source_evidence_identities": (_sha("geometry-evidence"),),
            "source_narrative_identity": _sha("geometry-narrative"),
            "source_quality": "fresh",
            "state": "observed",
            "state_label": "geometry_supported",
            "support_points": "20.00",
            "timeframe": "4h",
            "weight_points": "20.00",
        },
        {
            "direction": "bullish",
            "evidence_domains": ("liquidity",),
            "family": "liquidity",
            "material_conflict_count": 0,
            "opposition_points": "0.00",
            "prior_weight": "0.25",
            "source_evidence_identities": (_sha("liquidity-evidence"),),
            "source_narrative_identity": _sha("liquidity-narrative"),
            "source_quality": "fresh",
            "state": "observed",
            "state_label": "liquidity_supported",
            "support_points": "25.00",
            "timeframe": "4h",
            "weight_points": "25.00",
        },
        {
            "direction": "bullish",
            "evidence_domains": ("order_flow",),
            "family": "order_flow",
            "material_conflict_count": 0,
            "opposition_points": "0.00",
            "prior_weight": "0.25",
            "source_evidence_identities": (_sha("flow-evidence"),),
            "source_narrative_identity": _sha("flow-narrative"),
            "source_quality": "fresh",
            "state": "observed",
            "state_label": "flow_supported",
            "support_points": "25.00",
            "timeframe": "4h",
            "weight_points": "25.00",
        },
        {
            "direction": "bearish",
            "evidence_domains": ("derivatives",),
            "family": "derivatives",
            "material_conflict_count": 1,
            "opposition_points": "15.00",
            "prior_weight": "0.15",
            "source_evidence_identities": (_sha("derivatives-evidence"),),
            "source_narrative_identity": _sha("derivatives-narrative"),
            "source_quality": "fresh",
            "state": "observed",
            "state_label": "derivatives_conflict",
            "support_points": "0.00",
            "timeframe": "4h",
            "weight_points": "15.00",
        },
        {
            "direction": None,
            "evidence_domains": (),
            "family": "onchain",
            "material_conflict_count": 0,
            "opposition_points": "0.00",
            "prior_weight": "0.15",
            "source_evidence_identities": (),
            "source_narrative_identity": None,
            "source_quality": "unavailable",
            "state": "no_evidence",
            "state_label": "unavailable",
            "support_points": "0.00",
            "timeframe": None,
            "weight_points": "15.00",
        },
    )


def _payload(*, symbol: str, event_at_ms: int, summary: str) -> dict[str, object]:
    semantic_identity = canonical_sha256(
        {"symbol": symbol, "event_at_ms": event_at_ms, "summary": summary}
    )
    payload_without_identity: dict[str, object] = {
        "analytical_view": {
            "schema_version": "intelligence-stream-system-view-analytical-v1/1",
            "stance": {
                "effective_stance": "bullish",
                "support_score_0_100": "70.00",
                "opposition_score_0_100": "15.00",
            },
            "main_contradiction": {
                "family": "derivatives",
                "opposition_points": "15.00",
            },
            "uncertainty": {
                "probability_status": "not_calibrated",
                "event_risk_state": "caution",
                "provider_quality_state": "healthy",
            },
        },
        "category": "intelligence",
        "composer_version": "test-system-view-composer",
        "event_at_ms": event_at_ms,
        "fact_bundle": {
            "schema_version": "intelligence-stream-system-view-fact-v1/1",
            "symbol": symbol,
            "timeframe": "4h",
            "confluence_support_score_0_100": "70.00",
            "confluence_opposition_score_0_100": "15.00",
            "evidence_coverage_0_100": "85.00",
            "probability_status": "not_calibrated",
            "score_semantic": "weighted_directional_family_vote_not_probability",
            "event_context_state": "caution",
            "provider_quality_state": "healthy",
            "trigger_zone": {"low": "62000", "high": "62500"},
            "target_zone": {"low": "65000", "high": "66000"},
            "invalidation_price": "60800",
            "family_contributions": _family_rows(),
        },
        "importance": "important",
        "production_authority": False,
        "read_only": True,
        "real_capital": 0,
        "schema_version": STREAM_SYSTEM_VIEW_SCHEMA_VERSION,
        "semantic_identity": semantic_identity,
        "source_kind": "deterministic",
        "state": "bullish",
        "subtype": "system_view_updated",
        "symbol": symbol,
        "text": {
            "collapsed_text": summary,
            "simple_text": summary,
            "technical_text": "test",
            "intelligence_text": summary,
            "decision_text": "test",
            "capital_text": "test",
        },
        "timeframe": "4h",
    }
    narrative_identity = canonical_sha256(payload_without_identity)
    return {
        "narrative_identity": narrative_identity,
        **payload_without_identity,
    }


def _create_stream_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE stream_system_view_messages (
                narrative_identity TEXT PRIMARY KEY,
                semantic_identity TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                event_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            )
            """
        )


def _insert(path: Path, payload: dict[str, object]) -> None:
    encoded = canonical_json(payload)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO stream_system_view_messages (
                narrative_identity,
                semantic_identity,
                symbol,
                timeframe,
                event_at_ms,
                payload_json,
                payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["narrative_identity"],
                payload["semantic_identity"],
                payload["symbol"],
                payload["timeframe"],
                payload["event_at_ms"],
                encoded,
                sha256_text(encoded),
            ),
        )


def _all_text(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for key, item in value.items():
            result.extend(_all_text(key))
            result.extend(_all_text(item))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            result.extend(_all_text(item))
        return result
    return []


def test_market_pulse_missing_db_is_explicit_and_non_creating(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    view = FinalProductReadModel(stream_ledger_path=path).market_pulse(
        symbols=("BTCUSDT", "ETHUSDT"),
        observed_at_ms=1000,
    )

    assert view.availability_label == "Veri eksik"
    assert view.items == ()
    assert view.missing_symbols == ("BTCUSDT", "ETHUSDT")
    assert view.real_capital == 0
    assert not path.exists()


def test_market_pulse_is_point_in_time_and_read_only(tmp_path: Path) -> None:
    path = tmp_path / "stream.sqlite3"
    _create_stream_db(path)
    _insert(path, _payload(symbol="BTCUSDT", event_at_ms=1000, summary="eski görünüm"))
    _insert(path, _payload(symbol="BTCUSDT", event_at_ms=2000, summary="yeni görünüm"))
    before = path.read_bytes()

    view = FinalProductReadModel(stream_ledger_path=path).market_pulse(
        symbols=("BTCUSDT",),
        observed_at_ms=1500,
        stale_after_ms=1000,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert len(view.items) == 1
    item = view.items[0]
    assert item.updated_at_ms == 1000
    assert item.summary == "eski görünüm"
    assert item.freshness_label == "Güncel"
    assert item.stance_label == "Yükseliş yönlü destek"
    assert item.support_score_0_100 == "70.00"
    assert item.opposition_score_0_100 == "15.00"
    assert item.evidence_coverage_0_100 == "85.00"
    assert item.probability_label == "Kalibre edilmiş olasılık değil"
    assert item.event_risk_label == "Dikkat"
    assert item.provider_quality_label == "Kaynaklar sağlıklı"
    assert item.audit is None
    assert path.read_bytes() == before
    assert not Path(f"{path}-wal").exists()


def test_market_pulse_customer_projection_hides_identity_and_raw_states(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    _create_stream_db(path)
    _insert(path, _payload(symbol="BTCUSDT", event_at_ms=1000, summary="özet"))

    view = FinalProductReadModel(stream_ledger_path=path).market_pulse(
        symbols=("BTCUSDT",),
        observed_at_ms=1000,
    )
    raw = asdict(view)
    texts = _all_text(raw)

    assert not any(re.fullmatch(r"[0-9a-f]{64}", value) for value in texts)
    forbidden = {
        "not_calibrated",
        "no_evidence",
        "observed",
        "abstain",
        "unavailable",
        "unresolved",
        "system_view_updated",
    }
    assert forbidden.isdisjoint(texts)
    assert tuple(item.family_label for item in view.items[0].families) == (
        "Geometri",
        "Likidite",
        "Emir Akışı",
        "Türevler",
        "On-chain",
    )
    assert view.items[0].families[-1].state_label == "Veri eksik"


def test_market_pulse_audit_mode_preserves_exact_provenance(tmp_path: Path) -> None:
    path = tmp_path / "stream.sqlite3"
    _create_stream_db(path)
    payload = _payload(symbol="BTCUSDT", event_at_ms=1000, summary="özet")
    _insert(path, payload)

    view = FinalProductReadModel(stream_ledger_path=path).market_pulse(
        symbols=("BTCUSDT",),
        observed_at_ms=1000,
        include_audit=True,
    )

    item = view.items[0]
    assert item.audit is not None
    assert item.audit.narrative_identity == payload["narrative_identity"]
    assert item.audit.semantic_identity == payload["semantic_identity"]
    geometry = item.families[0]
    assert geometry.audit is not None
    assert geometry.audit.source_narrative_identity == _sha("geometry-narrative")
    assert geometry.audit.source_evidence_identities == (_sha("geometry-evidence"),)


def test_market_pulse_marks_stale_and_partial_without_fabricating_missing_asset(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    _create_stream_db(path)
    _insert(path, _payload(symbol="BTCUSDT", event_at_ms=1000, summary="özet"))

    view = FinalProductReadModel(stream_ledger_path=path).market_pulse(
        symbols=("BTCUSDT", "ETHUSDT"),
        observed_at_ms=5000,
        stale_after_ms=1000,
    )

    assert view.availability_label == "Kısmi veri"
    assert view.missing_symbols == ("ETHUSDT",)
    assert len(view.items) == 1
    assert view.items[0].freshness_label == "Güncel değil"
