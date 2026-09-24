from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_dashboard_performance_projection import (
    create_schema,
    insert_outcome,
    insert_signal,
    make_decision,
    make_outcome,
)
from test_epoch2_accounting import _activate

from crypto_signal.outcomes.models import EvidenceClass, OutcomeState
from crypto_signal.paper.epochs import EPOCH_2_SPEC
from crypto_signal.product.web import create_app


def test_galactech_performance_keeps_evidence_classes_separate(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "signals.sqlite3"
    create_schema(ledger)

    retrospective = make_decision("galactech-retro")
    untouched = make_decision("galactech-live")
    insert_signal(ledger, retrospective, seed="galactech-retro")
    insert_signal(ledger, untouched, seed="galactech-live")
    insert_outcome(
        ledger,
        make_outcome(
            retrospective,
            evidence_class=EvidenceClass.RETROSPECTIVE,
            state=OutcomeState.SUCCESS_TP2,
            evaluated_as_of_ms=2_000,
        ),
    )
    insert_outcome(
        ledger,
        make_outcome(
            untouched,
            evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
            state=OutcomeState.FAIL_SL,
            evaluated_as_of_ms=3_000,
        ),
    )

    _activate(tmp_path)
    epoch2 = tmp_path / EPOCH_2_SPEC.ledger_filename
    client = TestClient(create_app(ledger, epoch2_ledger_path=epoch2))

    performance = client.get("/api/performance")
    preview = client.get("/galactech")
    script = client.get("/galactech-static/app.js")
    style = client.get("/galactech-static/app.css")

    assert performance.status_code == 200
    assert preview.status_code == 200
    assert script.status_code == 200
    assert style.status_code == 200

    body = performance.json()
    assert body["status"] == "ready"
    assert body["outcome_snapshot_count"] == 2
    assert {
        item["evidence_class"]: item["count"]
        for item in body["evidence_class_counts"]
    } == {
        "retrospective": 1,
        "live_untouched_forward": 1,
    }
    assert {
        group["evidence_class"]
        for group in body["groups"]
    } == {
        "retrospective",
        "live_untouched_forward",
    }

    html = preview.text
    js = script.text
    css = style.text

    assert 'data-ui-version="galactech-v2-intelligence-first-tr"' in html
    assert 'id="performanceCohorts"' in html
    assert 'id="performancePaper"' in html
    assert 'id="performanceCalibration"' in html
    assert "Geçmiş başarı ≠ kalibre edilmiş olasılık" in html
    assert "geçmiş test ≠ ileri dönem kanıtı" in html
    assert "HENÜZ ÖLÇÜLMEDİ" in html
    assert "SUNULMUYOR" in html
    assert "Karşı-olgusal sonuç kanıtı yok." in html

    assert 'performance: "/api/performance"' in js
    assert "function performanceEvidenceClassLabel(value)" in js
    assert "function performanceSegmentMarkup(segment)" in js
    assert "function performanceGroupMarkup(group)" in js
    assert "function renderPerformanceCohorts()" in js
    assert "function renderPerformancePaper()" in js
    assert "function renderPerformance()" in js
    assert "betimleyici sıklık · olasılık değildir" in js
    assert "Boş performans geçmişi “ölçülmedi” demektir" in js
    assert "Öngörü isabet oranı, kâğıt portföy performansı yerine geçirilmez." in js
    assert 'loadEndpoint("performance", API.performance)' in js

    assert ".performance-summary-grid" in css
    assert ".performance-layout" in css
    assert ".performance-cohort" in css
    assert ".performance-segment-metrics" in css
    assert ".performance-trust-grid" in css

    assert client.post("/api/performance").status_code == 405


def test_galactech_performance_empty_history_is_not_zero_rate(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "signals.sqlite3"
    create_schema(ledger)
    client = TestClient(create_app(ledger))

    performance = client.get("/api/performance")
    script = client.get("/galactech-static/app.js")

    assert performance.status_code == 200
    assert performance.json() == {
        "status": "empty",
        "outcome_snapshot_count": 0,
        "evidence_class_counts": [],
        "groups": [],
    }

    js = script.text
    assert "Boş performans geçmişi “ölçülmedi” demektir; %0 başarı oranı değildir." in js
    assert "historical_success_fraction" in js
    assert "ÖLÇÜLMEDİ" in js
