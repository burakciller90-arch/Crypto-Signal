from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_intelligence_stream_read_model import _create_read_fixture, _sha

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.ledger.serialization import canonical_json, sha256_text
from crypto_signal.ledger.store import ImmutableSignalLedger
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
)
from crypto_signal.product.intelligence_stream_visual_proof import (
    IntelligenceStreamVisualProofReadModel,
    StreamVisualProofError,
)
from crypto_signal.product.web import create_app


def _create_visual_truth(
    *,
    stream_path: Path,
    signal_path: Path,
    decision_path: Path,
    future_candle: bool = False,
    bad_bundle_digest: bool = False,
) -> str:
    identities = _create_read_fixture(stream_path)
    narrative_identity = identities["btc-issued"]
    detail = IntelligenceStreamReadModel(stream_path).read_message_detail(
        narrative_identity
    )
    assert detail is not None
    fact = detail["fact_bundle"]
    forecast_identity = str(fact["forecast_identity"])
    proof_identity = str(fact["proof_identity"])
    signal_identity = _sha("s10-signal-freeze")

    ImmutableDecisionEvidenceLedger(decision_path).initialize()
    proof_payload = {
        "proof_identity": proof_identity,
        "schema_version": "decision-proof-v1/1",
        "engine_version": "r20.5-decision-proof-live-feed-v1-slice1/1",
        "forecast_identity": forecast_identity,
        "signal_freeze_identity": signal_identity,
        "confluence_identity": _sha("s10-confluence"),
        "event_context_identity": _sha("s10-event"),
        "probability_authorization_identity": None,
        "probability_calibration_evidence_identity": None,
        "asset": "BTC",
        "symbol": "BTCUSDT",
        "timeframe": "4h",
        "issued_at_ms": 1_000,
        "source_as_of_ms": 1_000,
        "signal_state": "active",
        "direction": "bullish",
        "conditional_thesis": "fixture",
        "trigger_zone": {"low": "62000", "high": "62500"},
        "target_zone": {"low": "65000", "high": "66000"},
        "invalidation_price": "60750",
        "horizon_bars": 8,
        "confluence_support_score_0_100": "72",
        "confluence_opposition_score_0_100": "18",
        "probability_status": "not_calibrated",
        "calibrated_probability_0_1": None,
        "event_context_state": "clear",
        "authority": "shadow",
        "freshness_0_1": "0.94",
        "uncertainty_flags": ["probability_not_calibrated"],
        "forecast_source_evidence_identities": [
            _sha("s10-chart-evidence"),
            _sha("s10-methodology-evidence"),
        ],
        "evidence_slices": [
            {
                "slice_identity": _sha("slice-consumed"),
                "schema_version": "decision-proof-v1/1",
                "engine_version": "r20.5-decision-proof-live-feed-v1-slice1/1",
                "domain": "consumed_candles",
                "availability": "available",
                "verdict": "support",
                "evidence_identities": [_sha("s10-chart-evidence")],
                "market_available_at_ms": 880,
                "observed_at_ms": 900,
                "freshness_0_1": "0.98",
                "source_quality": "accepted_source",
                "summary_codes": ["consumed_candles_available"],
            },
            {
                "slice_identity": _sha("slice-frozen"),
                "schema_version": "decision-proof-v1/1",
                "engine_version": "r20.5-decision-proof-live-feed-v1-slice1/1",
                "domain": "frozen_chart",
                "availability": "available",
                "verdict": "support",
                "evidence_identities": [_sha("s10-methodology-evidence")],
                "market_available_at_ms": 880,
                "observed_at_ms": 900,
                "freshness_0_1": "0.98",
                "source_quality": "accepted_source",
                "summary_codes": ["frozen_chart_available"],
            },
            {
                "slice_identity": _sha("slice-orderbook"),
                "schema_version": "decision-proof-v1/1",
                "engine_version": "r20.5-decision-proof-live-feed-v1-slice1/1",
                "domain": "order_book",
                "availability": "available",
                "verdict": "neutral",
                "evidence_identities": [_sha("s10-orderbook")],
                "market_available_at_ms": 850,
                "observed_at_ms": 900,
                "freshness_0_1": "0.9",
                "source_quality": "accepted_source",
                "summary_codes": ["order_book_available"],
            },
            {
                "slice_identity": _sha("slice-cvd"),
                "schema_version": "decision-proof-v1/1",
                "engine_version": "r20.5-decision-proof-live-feed-v1-slice1/1",
                "domain": "order_flow_cvd",
                "availability": "available",
                "verdict": "neutral",
                "evidence_identities": [_sha("s10-cvd")],
                "market_available_at_ms": 850,
                "observed_at_ms": 900,
                "freshness_0_1": "0.9",
                "source_quality": "accepted_source",
                "summary_codes": ["order_flow_cvd_available"],
            },
            {
                "slice_identity": _sha("slice-liquidity"),
                "schema_version": "decision-proof-v1/1",
                "engine_version": "r20.5-decision-proof-live-feed-v1-slice1/1",
                "domain": "liquidity_map",
                "availability": "available",
                "verdict": "support",
                "evidence_identities": [_sha("s10-liquidity")],
                "market_available_at_ms": 850,
                "observed_at_ms": 900,
                "freshness_0_1": "0.9",
                "source_quality": "accepted_source",
                "summary_codes": ["liquidity_map_available"],
            },
            {
                "slice_identity": _sha("slice-onchain"),
                "schema_version": "decision-proof-v1/1",
                "engine_version": "r20.5-decision-proof-live-feed-v1-slice1/1",
                "domain": "onchain",
                "availability": "insufficient",
                "verdict": "insufficient",
                "evidence_identities": [],
                "market_available_at_ms": None,
                "observed_at_ms": None,
                "freshness_0_1": None,
                "source_quality": None,
                "summary_codes": ["onchain_insufficient"],
            },
        ],
        "evidence_summary": {
            "support_count": 3,
            "contradict_count": 0,
            "neutral_count": 2,
            "insufficient_count": 1,
            "available_count": 5,
            "total_domain_count": 6,
        },
        "private_reasoning_exposed": False,
        "read_only": True,
        "production_authority": False,
        "real_capital": 0,
    }
    proof_json = canonical_json(proof_payload)
    connection = sqlite3.connect(decision_path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            """
            INSERT INTO r20_forecasts (
                forecast_identity,
                signal_freeze_identity,
                asset,
                symbol,
                timeframe,
                issued_at_ms,
                source_as_of_ms,
                payload_json,
                payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                forecast_identity,
                signal_identity,
                "BTC",
                "BTCUSDT",
                "4h",
                1_000,
                1_000,
                canonical_json(
                    {
                        "forecast_identity": forecast_identity,
                        "signal_freeze_identity": signal_identity,
                        "production_authority": False,
                        "real_capital": 0,
                    }
                ),
                sha256_text(
                    canonical_json(
                        {
                            "forecast_identity": forecast_identity,
                            "signal_freeze_identity": signal_identity,
                            "production_authority": False,
                            "real_capital": 0,
                        }
                    )
                ),
            ),
        )
        connection.execute(
            """
            INSERT INTO r20_5_decision_proofs (
                proof_identity,
                forecast_identity,
                signal_freeze_identity,
                asset,
                symbol,
                timeframe,
                issued_at_ms,
                payload_json,
                payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proof_identity,
                forecast_identity,
                signal_identity,
                "BTC",
                "BTCUSDT",
                "4h",
                1_000,
                proof_json,
                sha256_text(proof_json),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    ImmutableSignalLedger(signal_path).initialize()
    candle_close = 1_050 if future_candle else 899
    bundle_payload = {
        "schema_version": "decision-freeze-v1/1",
        "source_cutoff_open_time_ms": 800,
        "signal_decision": {
            "freeze_identity": signal_identity,
            "signal_version": "fixture-v1",
            "state": "active",
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "as_of_ms": 1_000,
            "direction": "bullish",
            "setup_type": "fixture",
            "geometry": {
                "source_evidence_id": _sha("s10-geometry"),
                "source_methodology": "price_action",
                "entry_zone": {"low": "62000", "high": "62500"},
                "entry_reference_price": "62250",
                "entry_reference_model": "zone_midpoint_reference_not_execution",
                "invalidation_price": "60750",
                "invalidation_trigger": "touch_or_cross",
                "targets": [
                    {
                        "label": "target_1",
                        "target_price": "65000",
                        "reference_rr": "2.4",
                    },
                    {
                        "label": "target_2",
                        "target_price": "66000",
                        "reference_rr": "3.2",
                    },
                ],
            },
            "agreement": {},
            "selected_evidence_ids": [],
            "methodology_versions": [],
            "probability_status": "not_calibrated",
            "historical_stats_status": "not_evaluated",
            "uncertainty_flags": [],
            "evidence_summary": [],
        },
        "confluence": {},
        "selected_evidence": [],
        "price_action": {},
        "harmonic": {},
        "elliott": {},
        "candles": [
            {
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "BTCUSDT",
                "timeframe": "4h",
                "open_time_ms": 100,
                "close_time_ms": 199,
                "open": "61000",
                "high": "61800",
                "low": "60800",
                "close": "61600",
                "volume": "12",
                "quote_volume": "736000",
                "trade_count": 100,
                "is_closed": True,
                "source": "rest_api",
                "source_timestamp_ms": 190,
                "ingested_at_ms": 195,
                "adapter_version": "fixture",
            },
            {
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "BTCUSDT",
                "timeframe": "4h",
                "open_time_ms": 800,
                "close_time_ms": candle_close,
                "open": "61600",
                "high": "62800",
                "low": "61400",
                "close": "62400",
                "volume": "15",
                "quote_volume": "930000",
                "trade_count": 120,
                "is_closed": True,
                "source": "rest_api",
                "source_timestamp_ms": 890,
                "ingested_at_ms": 900,
                "adapter_version": "fixture",
            },
        ],
    }
    bundle_json = canonical_json(bundle_payload)
    bundle_identity = (
        _sha("bad-bundle-digest")
        if bad_bundle_digest
        else sha256_text(bundle_json)
    )
    connection = sqlite3.connect(signal_path)
    try:
        connection.execute(
            """
            INSERT INTO signal_freezes (
                bundle_identity,
                signal_freeze_identity,
                exchange,
                market_type,
                symbol,
                timeframe,
                as_of_ms,
                source_cutoff_open_time_ms,
                signal_state,
                direction,
                bundle_json,
                frozen_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bundle_identity,
                signal_identity,
                "binance",
                "spot",
                "BTCUSDT",
                "4h",
                1_000,
                800,
                "active",
                "bullish",
                bundle_json,
                1_000,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return narrative_identity


def test_visual_proof_reads_only_frozen_bundle_and_exact_lineage(tmp_path: Path) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    signal_path = tmp_path / "signal.sqlite3"
    decision_path = tmp_path / "decision.sqlite3"
    narrative_identity = _create_visual_truth(
        stream_path=stream_path,
        signal_path=signal_path,
        decision_path=decision_path,
    )

    payload = IntelligenceStreamVisualProofReadModel(
        stream_ledger_path=stream_path,
        signal_ledger_path=signal_path,
        decision_evidence_path=decision_path,
    ).read_for_narrative(narrative_identity)

    assert payload is not None
    assert payload["status"] == "ready"
    assert payload["visual_kind"] == "frozen_ohlc"
    assert payload["read_only"] is True
    assert payload["production_authority"] is False
    assert payload["real_capital"] == 0
    assert payload["provenance"]["current_data_substitution"] is False
    assert payload["provenance"]["exact_persisted"] is True
    assert len(payload["candles"]) == 2
    assert payload["candles"][-1]["open_time_ms"] == 800
    assert len(payload["annotations"]) == 4
    assert {item["kind"] for item in payload["annotations"]} == {
        "entry_zone",
        "invalidation",
        "target",
    }
    assert all(item["annotation_identity"] for item in payload["annotations"])
    domains = {item["domain"]: item for item in payload["domain_evidence"]}
    assert domains["frozen_chart"]["visual_state"] == "resolved_frozen_bundle"
    assert domains["consumed_candles"]["visual_state"] == "resolved_frozen_bundle"
    assert domains["order_book"]["visual_state"] == "identity_only"
    assert domains["order_flow_cvd"]["visual_state"] == "identity_only"
    assert domains["liquidity_map"]["visual_state"] == "identity_only"
    assert domains["onchain"]["visual_state"] == "unavailable"
    assert len(payload["score_components"]["family_contributions"]) == 5


def test_visual_proof_fails_closed_on_bundle_digest_mismatch(tmp_path: Path) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    signal_path = tmp_path / "signal.sqlite3"
    decision_path = tmp_path / "decision.sqlite3"
    narrative_identity = _create_visual_truth(
        stream_path=stream_path,
        signal_path=signal_path,
        decision_path=decision_path,
        bad_bundle_digest=True,
    )

    with pytest.raises(StreamVisualProofError, match="bundle digest mismatch"):
        IntelligenceStreamVisualProofReadModel(
            stream_ledger_path=stream_path,
            signal_ledger_path=signal_path,
            decision_evidence_path=decision_path,
        ).read_for_narrative(narrative_identity)


def test_visual_proof_rejects_future_candle_even_with_valid_bundle_hash(
    tmp_path: Path,
) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    signal_path = tmp_path / "signal.sqlite3"
    decision_path = tmp_path / "decision.sqlite3"
    narrative_identity = _create_visual_truth(
        stream_path=stream_path,
        signal_path=signal_path,
        decision_path=decision_path,
        future_candle=True,
    )

    with pytest.raises(StreamVisualProofError, match="future information"):
        IntelligenceStreamVisualProofReadModel(
            stream_ledger_path=stream_path,
            signal_ledger_path=signal_path,
            decision_evidence_path=decision_path,
        ).read_for_narrative(narrative_identity)


def test_visual_proof_api_requires_persisted_runtime_and_uses_no_candle_cache(
    tmp_path: Path,
) -> None:
    stream_path = tmp_path / "stream.sqlite3"
    signal_path = tmp_path / "signal.sqlite3"
    decision_path = tmp_path / "decision.sqlite3"
    narrative_identity = _create_visual_truth(
        stream_path=stream_path,
        signal_path=signal_path,
        decision_path=decision_path,
    )

    client = TestClient(
        create_app(
            signal_path,
            stream_ledger_path=stream_path,
            decision_evidence_path=decision_path,
        )
    )
    response = client.get(
        f"/api/stream/messages/{narrative_identity}/visual-proof"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["visual_proof"]["provenance"]["candle_source"] == (
        "immutable_signal_freeze_bundle"
    )
    assert payload["visual_proof"]["provenance"]["current_data_substitution"] is False
    assert payload["real_capital"] == 0

    unavailable_client = TestClient(
        create_app(signal_path, stream_ledger_path=stream_path)
    )
    unavailable = unavailable_client.get(
        f"/api/stream/messages/{narrative_identity}/visual-proof"
    )
    assert unavailable.status_code == 200
    assert unavailable.json()["status"] == "unavailable"
    assert unavailable.json()["reason"] == (
        "decision_evidence_runtime_not_configured"
    )
