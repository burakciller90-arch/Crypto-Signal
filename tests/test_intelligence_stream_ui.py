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
    assert 'data-ui-version="crypto-signal-stream-v1-s10"' in preview.text
    assert 'data-ui-version="crypto-signal-stream-v1-s10"' not in root.text


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


def test_stream_s8_expands_supported_depth_inline_and_preserves_anchor() -> None:
    script = (STREAM_DIR / "app.js").read_text(encoding="utf-8")

    assert "/detail" in script
    assert "buildExpandedContent" in script
    assert "preserveMessageAnchor" in script
    assert "toggleMessageExpansion" in script
    assert "SIMPLE" in script
    assert "PRO" in script
    assert "INTELLIGENCE" in script
    assert "DECISION" in script
    assert "TRADE GEOMETRY" in script
    assert "CAPITAL" in script
    assert "PROOF" in script
    assert "family_contributions" in script
    assert "trigger_zone" in script
    assert "target_zone" in script
    assert "invalidation_price" in script
    assert "/api/decision-proof/forecast/" in script


def test_stream_s9_evidence_window_manager_contract() -> None:
    html = (STREAM_DIR / "index.html").read_text(encoding="utf-8")
    script = (STREAM_DIR / "app.js").read_text(encoding="utf-8")
    css = (STREAM_DIR / "app.css").read_text(encoding="utf-8")

    assert 'aria-label="Kanıt pencereleri"' in html
    assert "EVIDENCE_WINDOW_KINDS" in script
    for kind in (
        "liquidity",
        "order_flow",
        "derivatives",
        "onchain",
        "geometry",
        "decision",
        "capital",
        "event_risk",
        "proof",
    ):
        assert kind in script

    assert "openEvidenceWindow" in script
    assert "startEvidenceWindowDrag" in script
    assert "startEvidenceWindowResize" in script
    assert "focusEvidenceWindow" in script
    assert "persistEvidenceWindows" in script
    assert "restoreEvidenceWindows" in script
    assert "localStorage" in script
    assert "window.open(" in script
    assert "/stream-evidence?narrative=" in script
    assert "data-window-action" in script
    assert "pointermove" in script
    assert ".evidence-window-resize" in css
    assert ".evidence-window.is-minimized" in css
    assert ".evidence-window.is-pinned" in css
    assert "pointer-events: auto" in css


def test_stream_s9_detached_evidence_is_exact_identity_and_read_only(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "missing-ledger.sqlite3"))
    response = client.get(
        "/stream-evidence?narrative="
        + "a" * 64
        + "&kind=geometry"
    )
    assert response.status_code == 200
    assert 'data-ui-version="crypto-signal-stream-v1-s10-evidence"' in response.text

    detached = (STREAM_DIR / "evidence.js").read_text(encoding="utf-8")
    assert "/api/stream/messages/" in detached
    assert "/detail" in detached
    assert "/api/decision-proof/forecast/" in detached
    assert "/api/education/" in detached
    assert "REAL_CAPITAL=0" in detached
    assert "/visual-proof" in detached
    assert "immutable karar freeze" in detached


def test_stream_s9_binds_context_education_without_inventing_missing_data() -> None:
    script = (STREAM_DIR / "app.js").read_text(encoding="utf-8")

    assert "liquidity_sweep" in script
    assert '"cvd"' in script
    assert "liquidation_heatmap" in script
    assert "agreement_vs_probability" in script
    assert "paper_trading" in script
    assert "abstain" in script
    assert "calibration" in script
    assert "Bu mesajda neden önemli?" in script
    assert "veri uydurulmadı" in script


def test_stream_s10_frozen_visual_proof_contract() -> None:
    script = (STREAM_DIR / "app.js").read_text(encoding="utf-8")
    renderer = (STREAM_DIR / "visual_proof.js").read_text(encoding="utf-8")
    detached = (STREAM_DIR / "evidence.js").read_text(encoding="utf-8")

    assert "/visual-proof" in script
    assert "hydrateFrozenVisualProof" in script
    assert "renderDetachedFrozenVisualProof" in detached
    assert "frozen_ohlc" in renderer
    assert "frozen-proof-chart" in renderer
    assert "data-candle-identity" in renderer
    assert "data-annotation-identity" in renderer
    assert "data-source-evidence-identity" in renderer
    assert "current_data_substitution" in renderer
    assert "identity_only" in renderer
    assert "resolved_frozen_bundle" in renderer
    assert "SCORE COMPONENTS" in renderer
    assert "Confluence support" in renderer
    assert "Bu skor olasılık değildir." in renderer
    assert "current data ile yeniden üretilmedi" in renderer.lower()


def test_stream_s10_does_not_jump_to_s11_or_s13() -> None:
    html = (STREAM_DIR / "index.html").read_text(encoding="utf-8")
    script = (STREAM_DIR / "app.js").read_text(encoding="utf-8")
    renderer = (STREAM_DIR / "visual_proof.js").read_text(encoding="utf-8")

    assert "S13’te etkinleşecek" in html
    assert "new Audio(" not in script
    assert "AudioContext" not in script
    assert "Notification.requestPermission" not in script
    assert "REAL_CAPITAL=0" not in renderer or "real_capital" in renderer
    assert "execute_order" not in script
    assert "place_order" not in script


def test_stream_preview_static_assets_exist_and_are_light_first() -> None:
    css = (STREAM_DIR / "app.css").read_text(encoding="utf-8")

    assert (STREAM_DIR / "index.html").is_file()
    assert (STREAM_DIR / "app.js").is_file()
    assert (STREAM_DIR / "evidence.html").is_file()
    assert (STREAM_DIR / "evidence.js").is_file()
    assert (STREAM_DIR / "evidence.css").is_file()
    assert (STREAM_DIR / "visual_proof.js").is_file()
    assert "--bg: #f4f8ff" in css
    assert 'color-scheme" content="light"' in (
        STREAM_DIR / "index.html"
    ).read_text(encoding="utf-8")
    assert "@media (max-width: 560px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
