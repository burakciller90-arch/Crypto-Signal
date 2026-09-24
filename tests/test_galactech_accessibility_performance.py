from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.product.web import create_app


def test_galactech_polish_preserves_accessible_semantics_and_truth(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))

    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")
    style = client.get("/galactech-static/app.css")

    assert preview.status_code == 200
    assert script.status_code == 200
    assert style.status_code == 200

    html = preview.text
    js = script.text
    css = style.text

    assert 'data-ui-version="galactech-v2-intelligence-first-tr"' in html
    assert 'id="mainContent" class="main-content" tabindex="-1" aria-busy="true"' in html
    assert 'id="routeAnnouncer"' in html
    assert 'id="runtimeAnnouncer"' in html
    assert 'aria-live="polite"' in html
    assert 'aria-controls="view-command"' in html
    assert 'aria-controls="view-markets"' in html
    assert 'aria-controls="view-intelligence"' in html
    assert 'aria-controls="view-capital"' in html
    assert 'aria-controls="view-archive"' in html
    assert 'aria-controls="view-performance"' in html
    assert 'aria-controls="view-learn"' in html
    assert 'aria-controls="view-system"' in html
    assert 'aria-controls="learnGrid"' in html
    assert 'aria-describedby="evidenceDialogSubtitle"' in html
    assert 'data-filter="all" aria-pressed="true"' in html
    assert 'data-filter="loser" aria-pressed="false"' in html

    assert "const ROUTE_LABELS = Object.freeze" in js
    assert "function setMainBusy(isBusy, announcement = \"\")" in js
    assert "function announceRoute(route)" in js
    assert "ROUTE_LABELS[route] ? route : \"command\"" in js
    assert 'event.key === "ArrowDown"' in js
    assert 'event.key === "ArrowRight"' in js
    assert 'event.key === "ArrowUp"' in js
    assert 'event.key === "ArrowLeft"' in js
    assert 'event.key === "Home"' in js
    assert 'event.key === "End"' in js
    assert 'item.setAttribute("aria-pressed", String(active))' in js
    assert "async function refreshRuntime(reason = \"timer\")" in js
    assert "state.runtimeRefreshInFlight" in js
    assert 'document.visibilityState !== "visible"' in js
    assert 'document.addEventListener("visibilitychange"' in js
    assert 'void refreshRuntime("visibility")' in js
    assert 'behavior: prefersReducedMotion() ? "auto" : "smooth"' in js

    assert ".sr-only" in css
    assert "select:focus-visible" in css
    assert "input:focus-visible" in css
    assert "summary:focus-visible" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "@media (prefers-contrast: more)" in css
    assert "@media (forced-colors: active)" in css
    assert "@media (prefers-reduced-transparency: reduce)" in css
    assert "font-variant-numeric: tabular-nums" in css
    assert "content-visibility: auto" in css
    assert "contain-intrinsic-size:" in css

    assert "REAL_CAPITAL=0" in html
    assert "Bilmediğini biliyor." in html
    assert client.post("/galactech").status_code == 405


def test_galactech_static_budget_stays_bounded(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))

    html = client.get("/galactech").content
    js = client.get("/galactech-static/app.js").content
    css = client.get("/galactech-static/app.css").content

    # Coarse no-build bundle budgets: catch accidental asset explosions before cutover.
    assert len(html) < 50_000
    assert len(js) < 160_000
    assert len(css) < 90_000

    text = html.decode("utf-8")
    assert "<img" not in text
    assert "http://" not in text
    assert "https://" not in text
