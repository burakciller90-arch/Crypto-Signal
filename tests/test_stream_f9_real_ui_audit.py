from __future__ import annotations

import argparse
from pathlib import Path

import ops.audit_stream_f9_real_ui as f9


def _message(identity: str, category: str) -> dict[str, object]:
    return {
        "narrative_identity": identity,
        "category": category,
        "symbol": "BTCUSDT",
        "timeframe": "4h",
        "importance": "important",
        "text": {"collapsed_text": "BTCUSDT 4h exact production message"},
    }


def test_inventory_selects_current_live_scope_without_fabrication(
    monkeypatch,
) -> None:
    market = _message("a" * 64, "market")
    risk = _message("b" * 64, "system")

    def fake_get(base_url, path, params=None):
        assert base_url == "http://127.0.0.1:48700"
        if path == "/api/health":
            return {
                "status": "ok",
                "product_root": "stream",
                "stream_root_active": True,
                "read_only": True,
                "real_capital": 0,
            }
        assert path == "/api/stream/messages"
        return {"page": {"items": [risk, market]}}

    monkeypatch.setattr(f9, "_get_json", fake_get)
    result = f9.inventory("http://127.0.0.1:48700")

    assert result["primary"] == market
    assert result["degraded"] == risk
    assert result["categories"] == ["market", "system"]


def test_no_real_message_remains_open_without_browser(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        f9,
        "inventory",
        lambda base_url: {
            "health": {"read_only": True, "real_capital": 0},
            "message_count": 0,
            "categories": [],
            "primary": None,
            "degraded": None,
            "capital": None,
        },
    )

    def forbidden_probe(**kwargs):
        raise AssertionError("browser must not run without genuine message")

    monkeypatch.setattr(f9, "browser_probe", forbidden_probe)
    report = f9.run(
        argparse.Namespace(
            browser=tmp_path / "chromium",
            base_url="http://127.0.0.1:48700",
            output=tmp_path / "report.json",
            require_complete=False,
            require_capital=False,
            require_incoming=False,
            incoming_wait_seconds=0,
        )
    )

    assert report["status"] == "OPEN_NO_REAL_MESSAGES"
    assert report["synthetic_activity_used"] is False
    assert report["real_capital"] == 0


def test_current_scope_pass_candidate_keeps_deferred_classes_explicit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    market = _message("c" * 64, "market")
    risk = _message("d" * 64, "risk")
    monkeypatch.setattr(
        f9,
        "inventory",
        lambda base_url: {
            "health": {"read_only": True, "real_capital": 0},
            "message_count": 2,
            "categories": ["market", "risk"],
            "primary": market,
            "degraded": risk,
            "capital": None,
        },
    )

    def good_probe(**kwargs):
        return {
            "identity": "c" * 64,
            "incoming": {
                "required": True,
                "observed": True,
                "unread_affordance": True,
            },
            "checks": {
                "product_root": True,
                "no_fixture": True,
                "no_horizontal_overflow": True,
                "real_message_rendered": True,
                "message_expansion": True,
                "depths": True,
                "evidence_window": True,
                "multiple_evidence_windows": True,
                "detached_proof": True,
                "search_filter": True,
                "empty_state": True,
                "sound_controls": True,
                "ten_second_comprehension": True,
            },
        }

    monkeypatch.setattr(f9, "browser_probe", good_probe)
    report = f9.run(
        argparse.Namespace(
            browser=tmp_path / "chromium",
            base_url="http://127.0.0.1:48700",
            output=tmp_path / "report.json",
            require_complete=True,
            require_capital=False,
            require_incoming=True,
            incoming_wait_seconds=1,
        )
    )

    assert report["status"] == "PASS_CANDIDATE"
    scope = report["scope"]
    assert isinstance(scope, dict)
    assert scope["deferred"] == ["decision", "outcome", "capital_portfolio"]
    assert report["historical_backfill_used"] is False
    assert report["synthetic_activity_used"] is False
    assert report["real_capital"] == 0


def test_missing_current_live_scope_is_reported_not_fabricated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    market = _message("e" * 64, "market")
    monkeypatch.setattr(
        f9,
        "inventory",
        lambda base_url: {
            "health": {"read_only": True, "real_capital": 0},
            "message_count": 1,
            "categories": ["market"],
            "primary": market,
            "degraded": None,
            "capital": None,
        },
    )

    def incomplete_probe(**kwargs):
        return {
            "identity": "e" * 64,
            "incoming": {
                "required": True,
                "observed": False,
                "unread_affordance": False,
            },
            "checks": {
                "product_root": True,
                "ten_second_comprehension": False,
            },
        }

    monkeypatch.setattr(f9, "browser_probe", incomplete_probe)
    report = f9.run(
        argparse.Namespace(
            browser=tmp_path / "chromium",
            base_url="http://127.0.0.1:48700",
            output=tmp_path / "report.json",
            require_complete=False,
            require_capital=False,
            require_incoming=True,
            incoming_wait_seconds=1,
        )
    )

    assert report["status"] == "OPEN"
    open_requirements = set(report["open_requirements"])
    assert "degraded_source_message" in open_requirements
    assert "incoming_live_message" in open_requirements
    assert "desktop:ten_second_comprehension" in open_requirements
    assert "mobile:ten_second_comprehension" in open_requirements
    assert report["synthetic_activity_used"] is False
