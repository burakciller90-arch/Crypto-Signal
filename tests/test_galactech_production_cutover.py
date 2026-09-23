from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.product.web import create_app


def test_latest_main_galactech_root_cutover_preserves_legacy_rollback(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.sqlite3"
    client = TestClient(create_app(missing))

    root = client.get("/")
    alias = client.get("/galactech")
    legacy = client.get("/legacy")
    galactech_js = client.get("/galactech-static/app.js")
    legacy_js = client.get("/static/app.js")

    assert root.status_code == 200
    assert alias.status_code == 200
    assert legacy.status_code == 200
    assert galactech_js.status_code == 200
    assert legacy_js.status_code == 200

    assert root.content == alias.content
    assert 'data-ui-version="galactech-v1.1-polish"' in root.text
    assert 'data-ui-version="galactech-command-center-v1"' in legacy.text
    assert "/galactech-static/app.js" in root.text
    assert "/static/app.js" in legacy.text

    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["read_only"] is True
    assert health["real_capital"] == 0

    # Latest-main R25 / Slice16 customer truth must survive the cutover.
    assert "R25 / OPERATIONAL TRUTH" in root.text
    assert 'id="systemMarketTape"' in root.text
    assert 'id="systemColdArchive"' in root.text
    assert "EVENT SOURCE RUNTIME" in root.text
    assert "REAL_CAPITAL=0" in root.text
    assert "no order path" in root.text

    assert client.post("/").status_code == 405
    assert client.post("/galactech").status_code == 405
    assert client.post("/legacy").status_code == 405
    assert not missing.exists()


def test_cutover_candidate_keeps_all_eight_locked_primary_routes(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))
    root = client.get("/").text

    for route in (
        "command",
        "markets",
        "intelligence",
        "capital",
        "archive",
        "performance",
        "learn",
        "system",
    ):
        assert f'data-route="{route}"' in root
        assert f'data-route-view="{route}"' in root
        assert f'aria-controls="view-{route}"' in root


def test_cutover_does_not_expand_market_runtime_claims(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))
    root = client.get("/").text
    js = client.get("/galactech-static/app.js").text

    assert "ONLINE NOT ASSERTED" in js
    assert "process NOT MEASURED" in js
    assert "canonical-row replay NOT MEASURED" in js
    assert "EVENT SOURCE RUNTIME" in root
    assert "NOT EXPOSED" in root
