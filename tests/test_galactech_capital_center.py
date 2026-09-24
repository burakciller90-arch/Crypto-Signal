from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_epoch2_accounting import _activate

from crypto_signal.paper.epochs import EPOCH_2_SPEC
from crypto_signal.product.web import create_app


def test_galactech_capital_center_uses_canonical_epoch2_accounting_only(
    tmp_path: Path,
) -> None:
    _activate(tmp_path)
    epoch2 = tmp_path / EPOCH_2_SPEC.ledger_filename
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            epoch2_ledger_path=epoch2,
        )
    )

    state = client.get("/api/paper/epoch2-state")
    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")
    style = client.get("/galactech-static/app.css")

    assert state.status_code == 200
    assert preview.status_code == 200
    assert script.status_code == 200
    assert style.status_code == 200

    body = state.json()
    assert body["status"] == "ready"
    assert body["real_capital"] == 0
    assert body["consolidated"]["nav_usdt"] == "1000.00"
    assert body["consolidated"]["cash_usdt"] == "1000.00"
    assert body["consolidated"]["marked_exposure_usdt"] == "0"
    assert body["consolidated"]["realized_pnl_usdt"] == "0"
    assert body["consolidated"]["unrealized_pnl_usdt"] == "0"
    assert body["consolidated"]["drawdown_fraction"] == "0"
    assert body["consolidated"]["fee_usdt"] == "0"
    assert body["consolidated"]["spread_usdt"] == "0"
    assert body["consolidated"]["slippage_usdt"] == "0"
    assert body["consolidated"]["closed_trade_count"] == 0
    assert body["consolidated"]["metrics_status"] == "not_yet_measured"

    html = preview.text
    js = script.text
    css = style.text
    assert 'data-ui-version="galactech-v2-intelligence-first-tr"' in html
    assert "Kanonik Epoch 2 muhasebesi" in html
    assert 'epoch2State: "/api/paper/epoch2-state"' in js
    assert "function renderVaultCard(vault)" in js
    assert "function renderEpoch()" in js
    assert "function renderPaper()" in js
    assert "Kabul edilmiş Epoch 2 sermaye anayasası" in js
    assert "yapay zekâ çıkarımı veya canlı yatırım tavsiyesi değildir" in js
    assert "kanonik Epoch 2 · değiştirilemez R21 muhasebesi" in js
    assert "Boş geçmiş %0 başarı oranı değildir." in js
    assert "HENÜZ ÖLÇÜLMEDİ" in js
    assert "Yalnız program sözleşmesine bakılarak NAV, kâr/zarar, dağılım veya performans uydurulmaz" in js
    assert 'loadEndpoint("epoch2State", API.epoch2State)' in js

    assert ".capital-hero-card" in css
    assert ".capital-vault-grid" in css
    assert ".capital-cost-row" in css
    assert ".capital-track-record" in css

    assert not (tmp_path / "missing-signals.sqlite3").exists()


def test_galactech_capital_center_does_not_use_legacy_mission_control_for_nav(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))
    state = client.get("/api/paper/epoch2-state")
    script = client.get("/galactech-static/app.js")

    assert state.status_code == 200
    assert state.json() == {
        "status": "unavailable",
        "reason": "epoch2_runtime_not_configured",
        "read_only": True,
        "real_capital": 0,
    }

    js = script.text
    start = js.index("function renderPaper()")
    end = js.index("function proofCategory(", start)
    render_paper = js[start:end]
    assert "state.epoch2State" in render_paper
    assert "state.paper" not in render_paper
    assert "kanonik Epoch 2 kanıtı kullanılamıyor" in render_paper
