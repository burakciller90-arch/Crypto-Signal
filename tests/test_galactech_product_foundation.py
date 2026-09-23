from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.product.web import create_app


def test_galactech_preview_is_isolated_truthful_read_only_surface(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))

    response = client.get("/galactech")
    css = client.get("/galactech-static/app.css")
    script = client.get("/galactech-static/app.js")

    assert response.status_code == 200
    assert css.status_code == 200
    assert script.status_code == 200
    assert client.post("/galactech").status_code == 405

    html = response.text
    assert "GALACTECH" in html
    assert "// CRYPTO SIGNAL" in html
    assert 'data-ui-version="galactech-v1.1-foundation"' in html
    assert "Mission Control" in html
    assert "Evidence Intelligence" in html
    assert "Capital Center" in html
    assert "Archive / Proof Wall" in html
    assert "Performance & Trust" in html
    assert "Learn From Evidence" in html
    assert "System Truth" in html
    assert "REAL_CAPITAL=0" in html
    assert "REAL CAPITAL · DISABLED" in html
    assert "FRESHNESS · NOT MEASURED" in html
    assert "LATENCY · NOT MEASURED" in html
    assert "No fake LIVE · no fake latency · no fake probability" in html
    for section in (
        "COMMAND",
        "MARKETS",
        "INTELLIGENCE",
        "CAPITAL",
        "ARCHIVE",
        "PERFORMANCE",
        "LEARN",
        "SYSTEM",
    ):
        assert f'class="nav-label">{section}</span>' in html

    css_text = css.text
    assert "#06080c" in css_text.lower()
    assert "--cyan:" in css_text
    assert "--emerald:" in css_text
    assert "--crimson:" in css_text
    assert "--amber:" in css_text
    assert "@media (prefers-reduced-motion: reduce)" in css_text
    assert "@media (max-width: 820px)" in css_text
    assert ":focus-visible" in css_text

    js = script.text
    assert 'health: "/api/health"' in js
    assert 'command: "/api/command-center?recent_limit=12"' in js
    assert 'radar: "/api/market-radar"' in js
    assert 'epoch: "/api/paper/epoch-contract"' in js
    assert 'paper: "/api/paper/mission-control"' in js
    assert 'archive: "/api/archive/proof-wall?limit=60&offset=0"' in js
    assert 'education: "/api/education"' in js
    assert 'intelligence: "/api/intelligence-center"' in js
    assert 'cache: "no-store"' in js
    assert 'document.visibilityState !== "visible"' in js
    assert "function prefersReducedMotion()" in js
    assert "function renderArchive()" in js
    assert "function renderPaper()" in js
    assert "function renderIntelligence()" in js
    assert "NOT MEASURED" in js
    assert "NOT EXPOSED" in js
    assert "Boş liste sıfır başarı ya da sıfır risk anlamına gelmez." in js


def test_galactech_preview_does_not_replace_accepted_root_ui_yet(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))

    root = client.get("/")
    preview = client.get("/galactech")

    assert root.status_code == 200
    assert preview.status_code == 200
    assert 'data-ui-version="galactech-command-center-v1"' in root.text
    assert 'data-ui-version="galactech-v1.1-foundation"' in preview.text
    assert root.text != preview.text
