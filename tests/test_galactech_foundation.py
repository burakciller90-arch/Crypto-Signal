from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.product.web import create_app


def test_galactech_preview_is_isolated_truthful_and_accessible(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    client = TestClient(create_app(missing))

    legacy = client.get("/")
    preview = client.get("/galactech")
    css = client.get("/galactech-static/app.css")
    js = client.get("/galactech-static/app.js")

    assert legacy.status_code == 200
    assert preview.status_code == 200
    assert css.status_code == 200
    assert js.status_code == 200

    # Foundation is parallel until the explicit production UI cutover.
    assert 'data-ui-version="galactech-command-center-v1"' in legacy.text
    assert 'data-ui-version="galactech-v1.1-performance"' in preview.text

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
        assert f'class="nav-label">{section}</span>' in preview.text

    assert 'class="skip-link"' in preview.text
    assert 'aria-current="page"' in preview.text
    assert 'aria-live="polite"' in preview.text
    assert 'id="coldBoot"' in preview.text
    assert "REAL CAPITAL" in preview.text
    assert "REAL_CAPITAL=0" in preview.text
    assert "No fake LIVE · no fake latency · no fake probability" in preview.text
    assert "MARKET TAPE" in preview.text
    assert "NOT EXPOSED" in preview.text
    assert "LATENCY" in preview.text
    assert "NOT MEASURED" in preview.text
    assert "Bloomberg" not in preview.text  # design thesis is not a fake runtime claim

    assert "--bg-0: #06080c" in css.text
    assert "--cyan: #45d7ff" in css.text
    assert "--emerald: #4ee8a4" in css.text
    assert "--crimson: #ff5f8f" in css.text
    assert "--amber: #ffc761" in css.text
    assert "@media (prefers-reduced-motion: reduce)" in css.text
    assert ":focus-visible" in css.text
    assert "@media (max-width: 580px)" in css.text

    assert "function prefersReducedMotion()" in js.text
    assert 'health: "/api/health"' in js.text
    assert 'command: "/api/command-center?recent_limit=12"' in js.text
    assert 'radar: "/api/market-radar"' in js.text
    assert 'epoch: "/api/paper/epoch-contract"' in js.text
    assert 'paper: "/api/paper/mission-control"' in js.text
    assert 'epoch2State: "/api/paper/epoch2-state"' in js.text
    assert 'archive: "/api/archive/proof-wall?limit=500&offset=0"' in js.text
    assert 'education: "/api/education"' in js.text
    assert 'intelligence: "/api/intelligence-center"' in js.text
    assert "API · AUTHORITY MISMATCH" in js.text
    assert "NOT VERIFIED" in js.text
    assert "UNAVAILABLE" in js.text
    assert "Boş liste sıfır başarı ya da sıfır risk anlamına gelmez." in js.text
    assert "Bu, piyasanın risksiz olduğu anlamına gelmez" in js.text
    assert "document.visibilityState" in js.text
    assert "30_000" in js.text
    assert 'id="evidenceDialog"' in preview.text
    assert "Immutable Decision Evidence" in preview.text
    assert "function renderEvidenceRoom(detail)" in js.text
    assert "function frozenChartMarkup(detail)" in js.text


def test_galactech_preview_does_not_expand_product_authority(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    client = TestClient(create_app(missing))

    health = client.get("/api/health").json()
    preview = client.get("/galactech")

    assert health["real_capital"] == 0
    assert health["read_only"] is True
    assert "READ ONLY" in preview.text
    assert "no order path" in preview.text
    assert client.post("/galactech").status_code == 405
    assert not missing.exists()
