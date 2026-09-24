from __future__ import annotations

import argparse
from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.product.web import create_app
from ops.run_dashboard import resolve_runtime_paths


def test_wc5_galactech_surface_is_truth_bound_and_drills_to_proof(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))
    html = client.get("/galactech").text
    js = client.get("/galactech-static/app.js").text
    css = client.get("/galactech-static/app.css").text

    assert 'id="wc5DecisionBody"' in html
    assert 'id="wc5DecisionTag"' in html
    assert "ŞU ANKİ EYLEM DURUMU" in html
    assert "Kalıcı eylem kanıtı yoksa sistem AL / SAT / NAKİTTE KAL uydurmaz." in html

    assert "wc2Action: (identity)" in js
    assert "async function loadCommandDecisionSurface()" in js
    assert "function renderCommandDecisionSurface()" in js
    assert "function wc5PrimaryEvidence(proof, verdict)" in js
    assert 'actionSnapshot?.status === "PERSISTED_ACTION"' in js
    assert 'persistedAction || "INSUFFICIENT_EVIDENCE"' in js
    assert "AZAMİ KAĞIT / DENEME MARUZİYETİ" in js
    assert "MEVCUT DEĞİL" in js
    assert "cohort niyeti tutar içermiyorsa sistem rakam uydurmaz" in js
    assert "same immutable intent" not in js
    assert "Eski karar geriye dönük değiştirilmez" in js
    assert "different action" not in js
    assert "farklı eylem için yeni kesin öngörü / niyet kanıtı gerekir" in js
    assert "Öncelik sırası öğrenilmiş bir önem puanı değildir" in js
    assert "kanonik kanıt alanlarının deterministik sunum sırasıdır" in js
    assert 'data-evidence-id="' in js
    assert "DONDURULMUŞ KANITI AÇ" in js

    assert ".wc5-decision-surface" in css
    assert ".wc5-decision-grid" in css
    assert ".wc5-proof-button" in css
    assert "@media (max-width: 580px)" in css


def test_wc5_surface_does_not_expand_product_authority(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))

    health = client.get("/api/health").json()
    html = client.get("/galactech").text

    assert health["real_capital"] == 0
    assert health["read_only"] is True
    assert "emir / erişim anahtarı yolu yok" in html
    assert "REAL_CAPITAL=0" in html


def test_dashboard_runtime_resolves_wc2_cohort_from_same_runtime_root() -> None:
    ledger = Path(
        "/Volumes/Crypto-504/Crypto-Signal/Development/"
        "runtime/ledger/live_signal_ledger.sqlite3"
    )
    args = argparse.Namespace(
        ledger=ledger,
        decision_evidence=None,
        epoch2_ledger=None,
        shadow_intent_journal=None,
        shadow_cycle_manifest=None,
        runtime_replay_observation=None,
        market_tape=None,
        market_tape_collector_runtime=None,
        cold_archive=None,
        provider_divergence=None,
        event_source_runtime=None,
        wc2_cohort=None,
    )

    paths = resolve_runtime_paths(args)

    assert paths["wc2_cohort_path"] == (
        ledger.parent.parent / "wc2" / "wc2_untouched_forward.sqlite3"
    )
