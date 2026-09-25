from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.product.web import create_app

ROOT = Path(__file__).resolve().parents[1]
STREAM_DIR = ROOT / "src" / "crypto_signal" / "product" / "stream"


def test_stream_preview_is_isolated_from_production_root(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "missing-ledger.sqlite3"))

    root = client.get("/")
    preview = client.get("/stream-preview")

    assert root.status_code == 200
    assert preview.status_code == 200
    assert 'data-ui-version="galactech-v2-intelligence-first-tr"' in root.text
    assert 'data-ui-version="crypto-signal-stream-v1-s7"' in preview.text
    assert 'data-ui-version="crypto-signal-stream-v1-s7"' not in root.text


def test_stream_preview_obeys_one_panel_contract() -> None:
    html = (STREAM_DIR / "index.html").read_text(encoding="utf-8")

    assert "INTELLIGENCE STREAM" in html
    assert "REAL_CAPITAL" in html
    assert "streamViewport" in html
    assert "messageList" in html
    assert "newMessageButton" in html
    assert "discoveryDrawer" in html
    assert "settingsDrawer" in html
    assert "floatingWindowLayer" in html
    assert "GÖRSEL TEST FIXTURE" in html

    for forbidden in (
        'class="sidebar"',
        "VARLIK MERKEZİ",
        "SİNYAL ARŞİVİ",
        "PERFORMANS</",
        "SİSTEM SAĞLIĞI</",
    ):
        assert forbidden not in html


def test_stream_shell_uses_s6_live_and_polling_contracts() -> None:
    script = (STREAM_DIR / "app.js").read_text(encoding="utf-8")

    assert 'messages: "/api/stream/messages"' in script
    assert 'live: "/api/stream/live"' in script
    assert "new EventSource(" in script
    assert "Last-Event-ID" not in script
    assert "pollCatchUp" in script
    assert "loadOlder" in script
    assert "beforeCursor" in script
    assert "newestCursor" in script
    assert "state.unread" in script
    assert "fixture" in script


def test_stream_fixture_mode_is_explicitly_non_live_truth() -> None:
    html = (STREAM_DIR / "index.html").read_text(encoding="utf-8")
    script = (STREAM_DIR / "app.js").read_text(encoding="utf-8")

    assert "CANLI PİYASA GERÇEĞİ DEĞİL" in html
    assert "ui.fixtureBanner.hidden = false" in script
    assert 'if (state.fixture) {' in script
    assert "applyFixture(state.fixture)" in script


def test_stream_s7_does_not_enable_sound_or_message_expansion() -> None:
    html = (STREAM_DIR / "index.html").read_text(encoding="utf-8")
    script = (STREAM_DIR / "app.js").read_text(encoding="utf-8")

    assert "S13’te etkinleşecek" in html
    assert "S8" in html
    assert "new Audio(" not in script
    assert "AudioContext" not in script
    assert "Notification.requestPermission" not in script


def test_stream_preview_static_assets_exist_and_are_light_first() -> None:
    css = (STREAM_DIR / "app.css").read_text(encoding="utf-8")

    assert (STREAM_DIR / "index.html").is_file()
    assert (STREAM_DIR / "app.js").is_file()
    assert "--bg: #f4f8ff" in css
    assert 'color-scheme" content="light"' in (
        STREAM_DIR / "index.html"
    ).read_text(encoding="utf-8")
    assert "@media (max-width: 560px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
