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
    monkeypatch.setattr(f9, "incoming_live_probe", forbidden_probe)
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

    browser_calls = []

    def good_probe(**kwargs):
        browser_calls.append(kwargs)
        assert "incoming_wait_seconds" not in kwargs
        return {
            "identity": "c" * 64,
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

    incoming_calls = []

    def good_incoming(**kwargs):
        incoming_calls.append(kwargs)
        assert "item" not in kwargs
        assert kwargs["base_url"] == "http://127.0.0.1:48700"
        return {
            "required": True,
            "sse_ready": True,
            "observed": True,
            "unread_affordance": True,
            "fresh_identities": ["f" * 64],
        }

    monkeypatch.setattr(f9, "browser_probe", good_probe)
    monkeypatch.setattr(f9, "incoming_live_probe", good_incoming)
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
    assert len(browser_calls) == 2
    assert len(incoming_calls) == 1
    assert incoming_calls[0]["wait_seconds"] == 1
    assert report["incoming_live"]["sse_ready"] is True
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
            "checks": {
                "product_root": True,
                "ten_second_comprehension": False,
            },
        }

    def no_incoming(**kwargs):
        return {
            "required": True,
            "sse_ready": True,
            "observed": False,
            "unread_affordance": False,
            "fresh_identities": [],
        }

    monkeypatch.setattr(f9, "browser_probe", incomplete_probe)
    monkeypatch.setattr(f9, "incoming_live_probe", no_incoming)
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
                {
                    "ids": ["a" * 64],
                    "unreadAffordance": False,
                    "count": "",
                }
                if self.calls == 1
                else {
                    "ids": ["a" * 64, "b" * 64],
                    "unreadAffordance": True,
                    "count": "1",
                    "transport": "SSE CANLI",
                    "label": "CANLI",
                }
            )
            return {"result": {"value": value}}

    monkeypatch.setattr(f9.time, "sleep", lambda seconds: None)
    result = f9._observe_incoming(FakeSession(), 1)

    assert result["observed"] is True
    assert result["unread_affordance"] is True
    assert result["fresh_identities"] == ["b" * 64]
    assert result["unread_count"] == "1"


def test_live_root_wait_requires_real_sse_state() -> None:
    expression = f9._wait_live_root()

    assert "params.get('message')" in expression
    assert "params.get('fixture')" in expression
    assert "transport==='SSE CANLI'" in expression
    assert "label==='CANLI'" in expression


def test_incoming_probe_contract_is_separate_from_exact_message_probe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    market = _message("9" * 64, "market")
    risk = _message("8" * 64, "system")
    monkeypatch.setattr(
        f9,
        "inventory",
        lambda base_url: {
            "health": {"read_only": True, "real_capital": 0},
            "message_count": 2,
            "categories": ["market", "system"],
            "primary": market,
            "degraded": risk,
            "capital": None,
        },
    )

    exact_calls = []

    def exact_probe(**kwargs):
        exact_calls.append(kwargs)
        assert kwargs["item"] is market
        assert "incoming_wait_seconds" not in kwargs
        return {
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
            }
        }

    live_calls = []

    def live_probe(**kwargs):
        live_calls.append(kwargs)
        assert kwargs["wait_seconds"] == 7
        assert kwargs["screenshot"].name == "f9-live-incoming.png"
        return {
            "required": True,
            "sse_ready": True,
            "observed": True,
            "unread_affordance": True,
            "fresh_identities": ["7" * 64],
        }

    monkeypatch.setattr(f9, "browser_probe", exact_probe)
    monkeypatch.setattr(f9, "incoming_live_probe", live_probe)

    report = f9.run(
        argparse.Namespace(
            browser=tmp_path / "chromium",
            base_url="http://127.0.0.1:48700",
            output=tmp_path / "report.json",
            require_complete=True,
            require_capital=False,
            require_incoming=True,
            incoming_wait_seconds=7,
        )
    )

    assert len(exact_calls) == 2
    assert len(live_calls) == 1
    assert report["incoming_live"]["observed"] is True
    assert report["open_requirements"] == []


def test_genuine_replay_plan_uses_exact_real_page_cursor(monkeypatch) -> None:
    newest = _message("1" * 64, "market")
    newest["event_at_ms"] = 200
    older = _message("0" * 64, "system")
    older["event_at_ms"] = 100

    def fake_get(base_url, path, params=None):
        assert base_url == "http://127.0.0.1:48700"
        assert path == "/api/stream/messages"
        assert params == {"limit": 2}
        return {
            "status": "ready",
            "page": {
                "items": [newest, older],
                "order": "newest_to_oldest",
                "newest_cursor": "cursor-new",
                "oldest_cursor": "cursor-old",
            },
            "read_only": True,
            "real_capital": 0,
        }

    monkeypatch.setattr(f9, "_get_json", fake_get)
    plan = f9.genuine_replay_plan("http://127.0.0.1:48700")

    assert plan == {
        "candidate_identity": "1" * 64,
        "candidate_event_at_ms": 200,
        "older_identity": "0" * 64,
        "after_cursor": "cursor-old",
    }


def test_genuine_replay_plan_fails_closed_without_two_real_messages(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        f9,
        "_get_json",
        lambda base_url, path, params=None: {
            "page": {
                "items": [_message("1" * 64, "market")],
                "order": "newest_to_oldest",
                "oldest_cursor": "cursor-only",
            }
        },
    )

    assert f9.genuine_replay_plan("http://127.0.0.1:48700") is None


def test_genuine_replay_expression_uses_product_sse_without_server_write() -> None:
    expression = f9._genuine_replay_expression(
        candidate_identity="a" * 64,
        after_cursor="exact-real-cursor",
    )

    assert "connectLive()" in expression
    assert "state.newestCursor=after" in expression
    assert "state.ids.delete(id)" in expression
    assert "newMessageButton" in expression
    assert "SSE CANLI" in expression
    assert "fetch(" not in expression
    assert "XMLHttpRequest" not in expression
    assert "POST" not in expression
