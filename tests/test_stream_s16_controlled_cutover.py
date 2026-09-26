from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crypto_signal.product.web import (
    PRODUCT_ROOT_GALACTECH,
    PRODUCT_ROOT_STREAM,
    create_app,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_s16_stream_cutover_makes_stream_exact_product_root_with_galactech_fallback(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.sqlite3"
    client = TestClient(
        create_app(
            missing,
            product_root=PRODUCT_ROOT_STREAM,
        )
    )

    root = client.get("/")
    preview = client.get("/stream-preview")
    fallback = client.get("/galactech")
    legacy = client.get("/legacy")

    assert root.status_code == 200
    assert preview.status_code == 200
    assert fallback.status_code == 200
    assert legacy.status_code == 200

    assert root.content == preview.content
    assert 'data-ui-version="crypto-signal-stream-v1-s14"' in root.text
    assert "/stream-static/app.css" in root.text
    assert "GALACTECH · INTELLIGENCE STREAM" in root.text

    assert 'data-ui-version="galactech-v2-intelligence-first-tr"' in fallback.text
    assert "/galactech-static/app.css" in fallback.text
    assert 'data-ui-version="galactech-command-center-v1"' in legacy.text

    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["product_root"] == PRODUCT_ROOT_STREAM
    assert health["stream_root_active"] is True
    assert health["stream_preview_route"] == "/stream-preview"
    assert health["galactech_fallback_route"] == "/galactech"
    assert health["legacy_route"] == "/legacy"
    assert health["rollback_mode"] == PRODUCT_ROOT_GALACTECH
    assert health["read_only"] is True
    assert health["real_capital"] == 0

    assert client.get("/stream-static/app.js").status_code == 200
    assert client.get("/galactech-static/app.js").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.post("/").status_code == 405
    assert client.post("/galactech").status_code == 405
    assert not missing.exists()


def test_s16_rollback_mode_restores_galactech_root_without_hiding_stream(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.sqlite3"
    client = TestClient(
        create_app(
            missing,
            product_root=PRODUCT_ROOT_GALACTECH,
        )
    )

    root = client.get("/")
    fallback = client.get("/galactech")
    preview = client.get("/stream-preview")

    assert root.content == fallback.content
    assert 'data-ui-version="galactech-v2-intelligence-first-tr"' in root.text
    assert 'data-ui-version="crypto-signal-stream-v1-s14"' in preview.text

    health = client.get("/api/health").json()
    assert health["product_root"] == PRODUCT_ROOT_GALACTECH
    assert health["stream_root_active"] is False
    assert health["real_capital"] == 0
    assert not missing.exists()


def test_s16_product_root_environment_is_explicit_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing.sqlite3"

    monkeypatch.setenv("CRYPTO_SIGNAL_PRODUCT_ROOT", PRODUCT_ROOT_STREAM)
    client = TestClient(create_app(missing))
    assert client.get("/").content == client.get("/stream-preview").content

    monkeypatch.setenv("CRYPTO_SIGNAL_PRODUCT_ROOT", "invalid-root")
    with pytest.raises(ValueError, match="product_root must be one of"):
        create_app(missing)


def test_s16_runtime_launcher_and_launchd_declare_stream_root_with_one_flag_rollback() -> None:
    runner = (REPO_ROOT / "ops" / "run_dashboard.py").read_text(encoding="utf-8")
    plist = (
        REPO_ROOT
        / "ops"
        / "product"
        / "launchd"
        / "com.cryptosignal.dashboard.plist"
    ).read_text(encoding="utf-8")

    assert '"--product-root"' in runner
    assert "default=PRODUCT_ROOT_STREAM" in runner
    assert "use galactech for immediate rollback" in runner
    assert "product_root=args.product_root" in runner

    assert "<string>--product-root</string><string>stream</string>" in plist
    assert "REAL_CAPITAL" not in plist


def test_s16_chromium_acceptance_has_loaded_runner_startup_budget() -> None:
    capture = (
        REPO_ROOT / "ops" / "capture_chromium_viewport.py"
    ).read_text(encoding="utf-8")
    workflow = (
        REPO_ROOT
        / ".github"
        / "workflows"
        / "crypto-stream-s16-controlled-cutover-hosted.yml"
    ).read_text(encoding="utf-8")

    assert "timeout_seconds: float = 30.0" in capture
    assert "Chrome DevTools target unavailable after" in capture
    assert "timeoutMs = 30000" in capture
    assert "timeout_seconds=90.0" in capture
    assert "sleep 45" in workflow
    assert "sleep 8" in workflow
