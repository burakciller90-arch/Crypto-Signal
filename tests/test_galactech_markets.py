from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_dashboard_web import seed_ledger

from crypto_signal.product.web import create_app


def test_galactech_markets_workspace_binds_exact_provider_freeze(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "signals.sqlite3"
    signal_id = seed_ledger(ledger)
    client = TestClient(create_app(ledger))

    radar = client.get("/api/market-radar")
    cockpit = client.get("/api/assets/BTCUSDT/15m?recent_limit=30")
    detail = client.get(f"/api/signals/{signal_id}")
    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")
    style = client.get("/galactech-static/app.css")

    assert radar.status_code == 200
    assert cockpit.status_code == 200
    assert detail.status_code == 200
    assert preview.status_code == 200
    assert script.status_code == 200
    assert style.status_code == 200

    radar_body = radar.json()
    cockpit_body = cockpit.json()
    detail_body = detail.json()

    assert radar_body["status"] == "ready"
    assert radar_body["items"][0]["latest"]["signal_freeze_identity"] == signal_id

    assert cockpit_body["status"] == "ready"
    assert cockpit_body["symbol"] == "BTCUSDT"
    assert cockpit_body["timeframe"] == "15m"
    assert cockpit_body["latest_by_provider"][0]["signal_freeze_identity"] == signal_id
    assert cockpit_body["recent_signals"][0]["signal_freeze_identity"] == signal_id

    assert detail_body["status"] == "ready"
    assert detail_body["signal"]["signal_freeze_identity"] == signal_id

    html = preview.text
    js = script.text
    css = style.text

    assert 'data-ui-version="galactech-v2-intelligence-first-tr"' in html
    assert 'id="marketSymbolSelect"' in html
    assert 'id="marketTimeframeSelect"' in html
    assert 'id="marketFrozenChart"' in html
    assert 'id="marketLayerSurface"' in html
    assert 'id="marketProviderList"' in html
    assert 'id="marketRecentTape"' in html
    assert "SAHTE UZLAŞI YOK" in html
    for layer in ("PA", "LIQ", "FLOW", "DERIV", "ONCHAIN"):
        assert f'data-layer="{layer}"' in html

    assert "assetCockpit: (symbol, timeframe)" in js
    assert "function availableMarketContexts()" in js
    assert "async function initializeMarketWorkspace" in js
    assert "function syncMarketSelectionFromControls(reload)" in js
    assert "async function loadMarketSelection()" in js
    assert "async function selectMarketProvider(identity)" in js
    assert "function renderMarketProviderList()" in js
    assert "function renderMarketRecentTape()" in js
    assert "function renderMarketLayerSurface()" in js
    assert "function renderMarketWorkspace()" in js
    assert "FİYAT HAREKETİ / DONDURULMUŞ SİNYAL KANITI" in js
    assert "R20.5 KARAR KANITI" in js
    assert "KALICI KANIT YOK" in js
    assert "Bu değiştirilemez sinyal için exact R20.5 Karar Kanıtı yok" in js
    assert "sentetik geçersizlik yok" in js
    assert 'loadEndpoint("radar", API.radar)' in js
    assert 'data-market-provider-id="' in js
    assert 'data-evidence-id="' in js

    assert ".market-selector-bar" in css
    assert ".market-workspace-grid" in css
    assert ".market-provider-card.is-active" in css
    assert ".market-layer-unavailable" in css
    assert ".market-pa-grid" in css
    assert ".market-secondary-grid" in css

    assert client.post("/api/assets/BTCUSDT/15m").status_code == 405


def test_galactech_markets_decision_proof_layers_fail_closed_when_unpersisted(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))

    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")

    assert preview.status_code == 200
    assert script.status_code == 200
    assert not (tmp_path / "missing.sqlite3").exists()

    js = script.text
    assert 'LIQ: "Likidite / Likidasyon"' in js
    assert 'FLOW: "Emir Akışı / CVD"' in js
    assert 'DERIV: "Türevler / Açık Pozisyon / Fonlama / Baz"' in js
    assert 'ONCHAIN: "Zincir Üstü"' in js
    assert 'LIQ: ["liquidity_map", "liquidation_map"]' in js
    assert 'FLOW: ["order_book", "order_flow_cvd"]' in js
    assert 'DERIV: ["derivatives"]' in js
    assert 'ONCHAIN: ["onchain"]' in js
    assert "Bu değiştirilemez sinyal için exact R20.5 Karar Kanıtı yok" in js
    assert "Sentetik grafik katmanı üretilmez" in js
