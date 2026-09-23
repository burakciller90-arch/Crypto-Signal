from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_shadow_intent_journal import _buy_preview

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.product.web import create_app


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _journal_with_preview(tmp_path: Path):
    path = tmp_path / "forecast-link.shadow-intent.sqlite3"
    issuance, _, preview = _buy_preview(tmp_path)
    journal = R25ShadowIntentJournal(path)
    append = journal.append(preview)
    return path, issuance, preview, append


def test_journal_exact_forecast_lookup_returns_persisted_identity_lineage(
    tmp_path: Path,
) -> None:
    path, issuance, preview, append = _journal_with_preview(tmp_path)

    link = R25ShadowIntentJournal(path).read_latest_for_forecast(
        issuance.forecast.forecast_identity
    )

    assert link is not None
    assert link.record_identity == append.record.record_identity
    assert link.preview_identity == preview.preview_identity
    assert link.forecast_identity == issuance.forecast.forecast_identity
    assert link.proof_identity == issuance.proof.proof_identity
    assert link.sizing_bridge_identity == preview.sizing_bridge_identity
    assert link.sizing_vault_result_identity == (
        preview.sizing_vault_result_identity
    )
    assert link.review_selection_identity == preview.review_selection_identity
    assert link.market_reference_identity == preview.market_reference_identity
    assert link.decision_identity == preview.decision.record_identity
    assert link.intent_identity == preview.intent.intent_identity
    assert link.read_only_verified is True
    assert link.canonical_epoch2_write_authority is False
    assert link.production_authority is False
    assert link.real_capital == 0


def test_forecast_lookup_never_matches_by_symbol_or_time_proximity(
    tmp_path: Path,
) -> None:
    path, _, _, _ = _journal_with_preview(tmp_path)

    link = R25ShadowIntentJournal(path).read_latest_for_forecast(
        _sha("different-forecast-same-market-hypothetical")
    )

    assert link is None


def test_product_forecast_link_endpoint_is_exact_read_only_truth(
    tmp_path: Path,
) -> None:
    path, issuance, preview, append = _journal_with_preview(tmp_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_intent_journal_path=path,
        )
    )

    response = client.get(
        "/api/shadow-decision-rail/forecast/"
        f"{issuance.forecast.forecast_identity}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["semantic"] == "EXACT_PERSISTED_IDENTITY_ONLY"
    assert body["forecast_identity"] == issuance.forecast.forecast_identity
    assert body["link"]["record_identity"] == append.record.record_identity
    assert body["link"]["preview_identity"] == preview.preview_identity
    assert body["link"]["proof_identity"] == issuance.proof.proof_identity
    assert body["explicit_review_present"] is True
    assert body["decision_preview_present"] is True
    assert body["canonical_epoch2_mutation"] is False
    assert body["production_authority"] is False
    assert body["read_only"] is True
    assert body["real_capital"] == 0


def test_product_forecast_link_returns_empty_for_unrelated_identity(
    tmp_path: Path,
) -> None:
    path, _, _, _ = _journal_with_preview(tmp_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_intent_journal_path=path,
        )
    )
    unrelated = _sha("unrelated-forecast")

    response = client.get(
        f"/api/shadow-decision-rail/forecast/{unrelated}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "empty",
        "reason": "no_exact_persisted_shadow_preview_for_forecast",
        "forecast_identity": unrelated,
        "semantic": "EXACT_PERSISTED_IDENTITY_ONLY",
        "read_only": True,
        "real_capital": 0,
    }


def test_product_forecast_link_rejects_non_sha_lookup(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_intent_journal_path=(
                tmp_path / "missing.shadow-intent.sqlite3"
            ),
        )
    )

    response = client.get(
        "/api/shadow-decision-rail/forecast/BTCUSDT"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "forecast_identity must be lowercase SHA256"
    )


def test_galactech_evidence_room_uses_exact_forecast_shadow_endpoint(
    tmp_path: Path,
) -> None:
    path, _, _, _ = _journal_with_preview(tmp_path)
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            shadow_intent_journal_path=path,
        )
    )

    script = client.get("/galactech-static/app.js")

    assert script.status_code == 200
    js = script.text
    assert "shadowForecast: (identity) =>" in js
    assert "/api/shadow-decision-rail/forecast/" in js
    assert "function renderShadowForecastLink(payload)" in js
    assert "EXACT IDENTITY LINK" in js
    assert "does not match by symbol, timestamp proximity, or heuristic" in js
    assert "Exact persisted forecast_identity match only" in js
    assert "not a fill" in js
    assert "canonical NAV mutation" in js
    assert "live trade" in js
