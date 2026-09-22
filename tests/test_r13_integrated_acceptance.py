from __future__ import annotations

import pytest

from ops import r13_integrated_acceptance as r13


def _health() -> dict[str, object]:
    return {
        "status": "ok",
        "read_only": True,
        "real_capital": 0,
        "ledger_present": True,
        "alert_outbox_present": True,
    }


def _intelligence() -> dict[str, object]:
    engines = [
        {
            "engine_id": f"engine-{index}",
            "production_contribution": 0,
            "production_authority": False,
        }
        for index in range(21)
    ]
    return {
        "status": "ready",
        "read_only": True,
        "real_capital": 0,
        "production_active_engine_count": 0,
        "probability_status": "not_calibrated",
        "accepted_engine_count": len(engines),
        "engines": engines,
    }


def test_health_contract_is_read_only_real_capital_zero() -> None:
    r13.verify_health(_health())
    bad = _health()
    bad["real_capital"] = 1
    with pytest.raises(RuntimeError, match="REAL_CAPITAL"):
        r13.verify_health(bad)


def test_intelligence_contract_rejects_production_contribution() -> None:
    r13.verify_intelligence(_intelligence())
    bad = _intelligence()
    bad["production_active_engine_count"] = 1
    with pytest.raises(RuntimeError, match="production contribution"):
        r13.verify_intelligence(bad)


def test_openapi_rejects_write_or_order_authority() -> None:
    r13.verify_openapi({"paths": {"/api/health": {"get": {}}}})
    with pytest.raises(RuntimeError, match="non-read-only"):
        r13.verify_openapi({"paths": {"/api/health": {"get": {}, "post": {}}}})
    with pytest.raises(RuntimeError, match="forbidden API authority"):
        r13.verify_openapi({"paths": {"/api/place-order": {"get": {}}}})


def test_gift_edition_shell_requires_beginner_and_research_markers() -> None:
    html = """
    GIFT EDITION · SADE BAŞLANGIÇ
    <button id="viewModeToggle"></button>
    KISACA
    <section id="intelligenceSection"></section>
    İSTİHBARAT LABORATUVARI
    """
    r13.verify_shell(html)
    with pytest.raises(RuntimeError, match="marker missing"):
        r13.verify_shell("GIFT EDITION · SADE BAŞLANGIÇ")


def test_paper_mission_requires_closed_write_gate() -> None:
    payload = {
        "status": "ready",
        "read_only": True,
        "real_capital": 0,
        "trade_policy": "NOT_ACTIVATED",
        "snapshot": {
            "trade_policy": "NOT_ACTIVATED",
            "real_capital": 0,
            "benchmarks": {"results": [{}, {}, {}]},
        },
    }
    r13.verify_paper_mission(payload)
    payload["trade_policy"] = "ACTIVE"
    with pytest.raises(RuntimeError, match="write gate"):
        r13.verify_paper_mission(payload)
