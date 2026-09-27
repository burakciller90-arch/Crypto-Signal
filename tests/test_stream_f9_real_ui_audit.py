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

    market_family = dict(market)
    market_family.pop("category")
    market_family["family"] = "geometry"
    risk_family = dict(risk)
    risk_family.pop("category")
    risk_family["family"] = "event_risk"

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
        category = (params or {}).get("category")
        if category == "market":
            return {"page": {"items": [market_family]}}
        if category == "system":
            return {"page": {"items": [risk_family]}}
        if category in {"intelligence", "risk", "capital"}:
            return {"page": {"items": []}}
        return {"page": {"items": [risk_family, market_family]}}

    monkeypatch.setattr(f9, "_get_json", fake_get)
    result = f9.inventory("http://127.0.0.1:48700")

    primary = result["primary"]
    degraded = result["degraded"]
    assert isinstance(primary, dict)
    assert isinstance(degraded, dict)
    assert primary["narrative_identity"] == "a" * 64
    assert primary["_f9_observed_category"] == "market"
    assert degraded["narrative_identity"] == "b" * 64
    assert degraded["_f9_observed_category"] == "system"
    assert result["categories"] == ["market", "system"]
    assert result["observed_counts"] == {
        "market": 1,
        "intelligence": 0,
        "risk": 0,
        "system": 1,
        "capital": 0,
    }


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


def test_incoming_observation_polls_without_long_cdp_promise(monkeypatch) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.calls = 0

        def command(self, method, params, timeout_seconds=30.0):
            assert method == "Runtime.evaluate"
            self.calls += 1
            value = (
                ["a" * 64]
                if self.calls == 1
                else {
                    "ids": ["a" * 64, "b" * 64],
                    "unreadAffordance": True,
                    "count": "1",
                }
            )
            return {"result": {"value": value}}

    monkeypatch.setattr(f9.time, "sleep", lambda seconds: None)
    result = f9._observe_incoming(FakeSession(), 1)

    assert result["observed"] is True
    assert result["unread_affordance"] is True
    assert result["fresh_identities"] == ["b" * 64]
    assert result["unread_count"] == "1"
