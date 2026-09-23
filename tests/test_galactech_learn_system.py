from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_dashboard_web import seed_ledger
from test_epoch2_accounting import _activate

from crypto_signal.paper.epochs import EPOCH_2_SPEC
from crypto_signal.product.web import create_app


def test_galactech_learn_renders_full_deterministic_catalog(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "signals.sqlite3"
    signal_id = seed_ledger(ledger)
    _activate(tmp_path)
    epoch2 = tmp_path / EPOCH_2_SPEC.ledger_filename
    client = TestClient(create_app(ledger, epoch2_ledger_path=epoch2))

    education = client.get("/api/education")
    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")
    style = client.get("/galactech-static/app.css")
    detail = client.get(f"/api/signals/{signal_id}")

    assert education.status_code == 200
    assert preview.status_code == 200
    assert script.status_code == 200
    assert style.status_code == 200
    assert detail.status_code == 200

    body = education.json()
    assert body["status"] == "ready"
    assert body["real_capital"] == 0
    assert len(body["lessons"]) == 15
    by_id = {item["concept_id"]: item for item in body["lessons"]}
    for concept in (
        "cvd",
        "absorption",
        "invalidation",
        "abstain",
        "agreement_vs_probability",
        "calibration",
        "paper_trading",
    ):
        assert concept in by_id
        assert by_id[concept]["title_tr"]
        assert by_id[concept]["beginner_tr"]
        assert by_id[concept]["why_it_matters_tr"]
    assert "olasılık" in by_id["agreement_vs_probability"]["beginner_tr"].lower()
    assert "REAL_CAPITAL=0" in by_id["paper_trading"]["beginner_tr"]

    html = preview.text
    js = script.text
    css = style.text
    assert 'data-ui-version="galactech-v1.1-polish"' in html
    assert 'id="learnSearchInput"' in html
    assert 'data-learn-concept="cvd"' in html
    assert 'data-learn-concept="absorption"' in html
    assert 'data-learn-concept="abstain"' in html
    assert "Teach the evidence · never invent certainty" in html

    assert "function lessonMatchesQuery(lesson, query)" in js
    assert "function lessonMarkup(lesson)" in js
    assert "function renderEducation()" in js
    assert "function contextualLessonIds(detail)" in js
    assert 'ids.add("abstain")' in js
    assert 'ids.add("invalidation")' in js
    assert 'ids.add("cvd")' in js
    assert 'ids.add("absorption")' in js
    assert 'ids.add("liquidity_sweep")' in js
    assert "Deterministic catalog · no generated market claim" in js
    assert "NEDEN ÖNEMLİ?" in js
    assert "PRO / teknik açıklamayı aç" in js

    assert ".learn-toolbar" in css
    assert ".learn-grid-rich" in css
    assert ".learn-advanced" in css
    assert ".learn-card-foot" in css


def test_galactech_system_never_upgrades_unexposed_runtime_health(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "signals.sqlite3"
    seed_ledger(ledger)
    client = TestClient(create_app(ledger))

    health = client.get("/api/health")
    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")

    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["ledger_present"] is True
    assert body["read_only"] is True
    assert body["real_capital"] == 0

    html = preview.text
    js = script.text

    assert 'id="systemTruthTag"' in html
    assert 'id="systemEpoch2"' in html
    assert 'id="systemArchive"' in html
    assert 'id="systemMarketEvidence"' in html
    assert 'id="systemIntelligence"' in html
    assert 'id="systemDecisionLedger"' in html
    assert 'id="systemLiveFeed"' in html
    assert 'id="systemPerformance"' in html
    assert 'id="systemEducation"' in html
    assert 'id="systemAlerts"' in html
    assert "API READY, Market Tape ONLINE demek değildir." in html
    assert "MARKET TAPE RUNTIME" in html
    assert "COLD ARCHIVE" in html
    assert "EVENT SOURCE RUNTIME" in html
    assert html.count("NOT EXPOSED") >= 2
    assert html.count("NOT MEASURED") >= 2
    assert "REAL CAPITAL" in html
    assert "DISABLED" in html
    assert "READ ONLY" in html

    assert "function setSystemValue(id, value, kind = \"neutral\")" in js
    assert "function renderSystem()" in js
    assert 'health.alert_outbox_present ? "PRESENT" : "NOT PRESENT"' in js
    assert 'archive.outcome_schema_available ? "AVAILABLE" : "SIGNALS ONLY"' in js
    assert "observed provider/context freezes" in js
    assert "TRUTH · PRODUCT EVIDENCE READY" in js
    assert '"systemDecisionLedger"' in js
    assert '"systemLiveFeed"' in js
    assert '"systemMarketTape"' in js
    assert '"systemColdArchive"' in js
    assert "ONLINE NOT ASSERTED" in js
    assert "process NOT MEASURED" in js
