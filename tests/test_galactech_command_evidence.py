from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_dashboard_web import seed_ledger

from crypto_signal.product.web import create_app


def test_galactech_command_and_evidence_room_use_same_exact_signal_freeze(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "signals.sqlite3"
    signal_id = seed_ledger(ledger)
    client = TestClient(create_app(ledger))

    command = client.get("/api/command-center?recent_limit=12")
    detail = client.get(f"/api/signals/{signal_id}")
    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")
    style = client.get("/galactech-static/app.css")

    assert command.status_code == 200
    assert detail.status_code == 200
    assert preview.status_code == 200
    assert script.status_code == 200
    assert style.status_code == 200

    command_body = command.json()
    detail_body = detail.json()
    assert command_body["status"] == "ready"
    assert command_body["freeze_count"] == 1
    assert command_body["recent_signals"][0]["signal_freeze_identity"] == signal_id

    assert detail_body["status"] == "ready"
    assert detail_body["signal"]["signal_freeze_identity"] == signal_id
    assert detail_body["signal"]["probability_status"] == "not_calibrated"
    assert detail_body["signal"]["confluence_score_semantic"] == (
        "agreement_index_not_probability"
    )
    assert detail_body["candle_count"] == 2
    assert detail_body["first_candle_open_time_ms"] == 0
    assert detail_body["last_candle_open_time_ms"] == 900
    assert len(detail_body["methodologies"]) == 3
    assert detail_body["methodologies"][0]["methodology"] == "price_action"
    assert detail_body["methodologies"][0]["selected_count"] == 1
    assert detail_body["pairwise_relations"][0]["relation"] == "insufficient"
    assert detail_body["geometry"] is None
    assert detail_body["evidence_summary"] == [
        "price_action:market_structure:bullish:context"
    ]

    html = preview.text
    js = script.text
    css = style.text
    assert 'data-ui-version="galactech-v1.1-performance"' in html
    assert 'id="evidenceDialog"' in html
    assert 'aria-labelledby="evidenceDialogTitle"' in html
    assert "EVIDENCE ROOM / FROZEN DECISION" in html
    assert "Immutable Decision Evidence" in html
    assert "later market data cannot rewrite it" in html

    assert "signalDetail: (identity)" in js
    assert "function renderEvidenceRoom(detail)" in js
    assert "function frozenChartMarkup(detail)" in js
    assert "function selectedEvidenceMarkup(item)" in js
    assert "function methodEngineMarkup(method)" in js
    assert "function pairwiseMarkup(item)" in js
    assert "function geometryMarkup(geometry)" in js
    assert "async function openEvidenceRoom(identity, trigger)" in js
    assert "function closeEvidenceRoom()" in js
    assert 'data-evidence-id="' in js
    assert "Evidence, not private reasoning" in js
    assert "Reference geometry is evidence, not an order instruction." in js
    assert "no synthetic candles are drawn" in js.lower()
    assert 'trigger.focus({ preventScroll: true })' in js

    assert ".evidence-room::backdrop" in css
    assert ".frozen-chart" in css
    assert ".candle-up" in css
    assert ".candle-down" in css
    assert ".proof-badge-risk" in css

    assert client.post(f"/api/signals/{signal_id}").status_code == 405


def test_galactech_evidence_room_fails_closed_for_unknown_identity(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "signals.sqlite3"
    seed_ledger(ledger)
    client = TestClient(create_app(ledger))

    response = client.get("/api/signals/" + "f" * 64)

    assert response.status_code == 200
    assert response.json() == {
        "status": "empty",
        "signal": None,
        "bundle_json": None,
        "methodologies": [],
        "pairwise_relations": [],
        "geometry": None,
        "evidence_summary": [],
        "candle_count": 0,
        "first_candle_open_time_ms": None,
        "last_candle_open_time_ms": None,
    }
