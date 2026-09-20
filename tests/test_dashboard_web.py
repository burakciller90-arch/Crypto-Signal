from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.confluence.models import ScoreSemantic
from crypto_signal.product import web as product_web
from crypto_signal.product.web import create_app
from crypto_signal.signals.models import ProbabilityStatus


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def seed_ledger(path: Path) -> str:
    signal_id = digest("signal")
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE signal_freezes (
                bundle_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT NOT NULL UNIQUE,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                as_of_ms INTEGER NOT NULL,
                source_cutoff_open_time_ms INTEGER NOT NULL,
                signal_state TEXT NOT NULL,
                direction TEXT NOT NULL,
                bundle_json TEXT NOT NULL,
                frozen_at_ms INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE outcome_evaluations (
                outcome_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT NOT NULL,
                evidence_class TEXT NOT NULL,
                evaluated_as_of_ms INTEGER NOT NULL,
                resolution_status TEXT NOT NULL,
                outcome_state TEXT,
                max_holding_bars INTEGER NOT NULL,
                outcome_json TEXT NOT NULL,
                appended_at_ms INTEGER NOT NULL
            )
            """
        )
        selected = {
            "ambiguity_flags": [],
            "as_of_ms": 1_000,
            "contradiction_flags": [],
            "direction": "bullish",
            "entry_zone": None,
            "evidence_id": "pa:test",
            "evidence_summary": ["current_structure=bullish"],
            "exchange": "bybit",
            "invalidation_price": None,
            "invalidation_trigger": None,
            "key_levels": [{"label": "structure", "price": "100"}],
            "market_available_at_ms": 900,
            "market_type": "spot",
            "methodology": "price_action",
            "methodology_version": "price-action-v1/1",
            "metrics": [{"name": "distance", "unit": "bps", "value": "5"}],
            "observed_at_ms": 950,
            "setup_type": "market_structure",
            "symbol": "BTCUSDT",
            "targets": [],
            "timeframe": "15m",
            "validity": "context",
        }
        payload = json.dumps(
            {
                "schema_version": "decision-freeze-v1/1",
                "source_cutoff_open_time_ms": 900,
                "candles": [
                    {"open_time_ms": 0},
                    {"open_time_ms": 900},
                ],
                "confluence": {
                    "selections": [
                        {
                            "methodology": "price_action",
                            "source_count": 1,
                            "selected": [selected],
                            "latest_market_available_at_ms": 900,
                            "resolved_direction": "bullish",
                            "has_internal_direction_conflict": False,
                        },
                        {
                            "methodology": "harmonic",
                            "source_count": 0,
                            "selected": [],
                            "latest_market_available_at_ms": None,
                            "resolved_direction": "unresolved",
                            "has_internal_direction_conflict": False,
                        },
                        {
                            "methodology": "elliott",
                            "source_count": 0,
                            "selected": [],
                            "latest_market_available_at_ms": None,
                            "resolved_direction": "unresolved",
                            "has_internal_direction_conflict": False,
                        },
                    ]
                },
                "signal_decision": {
                    "state": "watch",
                    "direction": "bullish",
                    "setup_type": "confluence_watch",
                    "geometry": None,
                    "agreement": {
                        "confluence_score": "33.33",
                        "score_semantic": (
                            ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY.value
                        ),
                        "support_method_count": 1,
                        "opposing_method_count": 0,
                        "resolved_method_count": 1,
                        "total_methodology_slots": 3,
                        "pairwise_relations": [
                            {
                                "left": "price_action",
                                "right": "harmonic",
                                "relation": "insufficient",
                                "left_direction": "bullish",
                                "right_direction": "unresolved",
                            }
                        ],
                    },
                    "probability_status": ProbabilityStatus.NOT_CALIBRATED.value,
                    "uncertainty_flags": ["partial_methodology_coverage"],
                    "evidence_summary": [
                        "price_action:market_structure:bullish:context"
                    ],
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        connection.execute(
            """
            INSERT INTO signal_freezes (
                bundle_identity,
                signal_freeze_identity,
                exchange,
                market_type,
                symbol,
                timeframe,
                as_of_ms,
                source_cutoff_open_time_ms,
                signal_state,
                direction,
                bundle_json,
                frozen_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest("bundle"),
                signal_id,
                "bybit",
                "spot",
                "BTCUSDT",
                "15m",
                1_000,
                900,
                "watch",
                "bullish",
                payload,
                1_100,
            ),
        )
    return signal_id


def test_health_and_static_shell_without_ledger(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    client = TestClient(create_app(missing))

    health = client.get("/api/health")
    index = client.get("/")

    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "product_version": "full-version-contextual-evidence/1",
        "real_capital": 0,
        "ledger_present": False,
        "alert_outbox_present": False,
        "read_only": True,
    }
    assert index.status_code == 200
    script = client.get("/static/app.js")
    assert "Piyasa İstihbarat Merkezi" in index.text
    assert "Metodoloji uyumu ≠ olasılık" in index.text
    assert script.status_code == 200
    assert "function frozenChartData(detail)" in script.text
    assert "function renderDecisionExplanation(detail)" in script.text
    assert "Dondurulmuş mum ve kanıt seviyeleri" in script.text
    assert "Neden önemli?" in script.text
    assert "const AUTO_REFRESH_MS = 15_000" in script.text
    assert 'document.addEventListener("visibilitychange"' in script.text
    assert "Canlı · otomatik yenileme" in script.text
    assert "liveStatusChip" in index.text
    assert "lastRefreshChip" in index.text
    assert "BANA ÖĞRET" in index.text
    assert "educationCenter" in index.text
    assert "SANAL PORTFÖY · KARAR MERKEZİ" in index.text
    assert "paperMissionControl" in index.text
    assert "function renderPaperMissionControl(data)" in script.text
    assert "/api/paper/mission-control" in script.text
    assert "Sistem kanıt gelmediğinde işlem uydurmaz." in script.text
    assert "function renderPaperTradePlan(item)" in script.text
    assert "İşlem planı · neden yok?" in script.text
    assert "Hangi kanıt bunu değiştirebilir?" in script.text
    assert "Toplam maliyet bütçesi" in script.text
    assert "Fee tahmini" in script.text
    assert "Spread tahmini" in script.text
    assert "Slippage tahmini" in script.text
    assert "function renderPaperPortfolioPerformanceLab(data)" in script.text
    assert "Henüz kapanmış sanal işlem yok." in script.text
    assert "Bu nedenle win rate" in script.text
    assert "Piyasa maruziyeti" in script.text
    assert "Paper Performans Laboratuvarı" in index.text
    assert 'id="paperPortfolioExposure"' in index.text
    assert 'id="paperPerformanceLab"' in index.text
    assert "SİNYAL / İŞLEM ARŞİVİ" in index.text
    assert 'id="paperTradeArchive"' in index.text
    assert "function renderPaperTradeArchive(data)" in script.text
    assert "Henüz sanal işlem kaydı yok." in script.text
    assert "Bu %0 başarı oranı değildir." in script.text
    assert "SİSTEM SAĞLIĞI" in index.text
    assert 'id="systemHealth"' in index.text
    assert "function renderSystemHealth(health, command, paperMission)" in script.text
    assert "READ-ONLY · SAĞLIKLI" in script.text
    assert "REAL_CAPITAL=" in script.text
    assert "function renderEducation(data)" in script.text
    assert "function contextualLessonIds(detail)" in script.text
    assert "function renderContextTeaching(detail)" in script.text
    assert "function renderEvidenceLegend(detail)" in script.text
    assert "Bu sinyali bana öğret" in script.text
    assert "Neden işlem yapmamalıyız?" in script.text
    assert "uyumu olasılık değildir" in script.text
    assert "Grafikte çizilen dondurulmuş kanıt" in script.text
    assert "daha yeni fiyat verisi geçmiş kararı yeniden yazmaz" in script.text
    assert not missing.exists()


def test_paper_mission_control_is_unavailable_without_explicit_test_runtime(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "signals.sqlite3"
    seed_ledger(signal_path)
    client = TestClient(create_app(signal_path))

    response = client.get("/api/paper/mission-control")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "reason": "paper_runtime_not_configured",
        "trade_policy": "NOT_ACTIVATED",
        "real_capital": 0,
        "read_only": True,
    }
    assert client.post("/api/paper/mission-control").status_code == 405


@dataclass(frozen=True)
class _FakePaperMissionSnapshot:
    snapshot_identity: str
    observed_at_ms: int
    trade_policy: str = "NOT_ACTIVATED"
    real_capital: int = 0


def test_paper_mission_control_get_binds_explicit_read_only_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    signal_path = tmp_path / "signals.sqlite3"
    paper_path = tmp_path / "paper.sqlite3"
    candle_path = tmp_path / "candles.sqlite3"
    seed_ledger(signal_path)
    paper_path.touch()
    candle_path.touch()
    calls: list[dict[str, object]] = []

    def fake_reader(**kwargs):
        calls.append(kwargs)
        return _FakePaperMissionSnapshot(
            snapshot_identity=digest("paper-mission"),
            observed_at_ms=int(kwargs["observed_at_ms"]),
        )

    monkeypatch.setattr(
        product_web,
        "read_paper_mission_control_snapshot",
        fake_reader,
    )
    client = TestClient(
        create_app(
            signal_path,
            paper_ledger_path=paper_path,
            candle_cache_path=candle_path,
        )
    )

    response = client.get("/api/paper/mission-control?observed_at_ms=1234")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "snapshot": {
            "snapshot_identity": digest("paper-mission"),
            "observed_at_ms": 1234,
            "trade_policy": "NOT_ACTIVATED",
            "real_capital": 0,
        },
        "trade_policy": "NOT_ACTIVATED",
        "real_capital": 0,
        "read_only": True,
    }
    assert calls == [
        {
            "paper_ledger_path": paper_path,
            "signal_ledger_path": signal_path,
            "candle_cache_path": candle_path,
            "observed_at_ms": 1234,
            "max_candidates": 100,
        }
    ]
    assert paper_path.stat().st_size == 0
    assert candle_path.stat().st_size == 0


def test_education_api_is_deterministic_and_read_only(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    client = TestClient(create_app(missing))

    catalog = client.get("/api/education")
    bos = client.get("/api/education/bos")
    unknown = client.get("/api/education/not-a-real-concept")

    assert catalog.status_code == 200
    body = catalog.json()
    assert body["status"] == "ready"
    assert body["real_capital"] == 0
    assert len(body["lessons"]) == 10
    assert next(lesson["concept_id"] for lesson in body["lessons"]) == "bos"
    assert bos.status_code == 200
    assert bos.json()["lesson"]["concept_id"] == "bos"
    assert "tek başına alım veya satım emri değildir" in bos.json()["lesson"]["beginner_tr"]
    assert unknown.status_code == 404
    assert client.post("/api/education").status_code == 405
    assert not missing.exists()


def test_command_center_json_preserves_truth_labels(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    seed_ledger(path)
    client = TestClient(create_app(path))

    response = client.get("/api/command-center")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["freeze_count"] == 1
    card = body["recent_signals"][0]
    assert card["state"] == "watch"
    assert card["direction"] == "bullish"
    assert card["confluence_score"] == "33.33"
    assert (
        card["confluence_score_semantic"]
        == "agreement_index_not_probability"
    )
    assert card["probability_status"] == "not_calibrated"
    assert card["evidence_class_status"] == "not_explicit_at_freeze_level"


def test_read_only_api_surfaces_share_same_frozen_signal(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    signal_id = seed_ledger(path)
    client = TestClient(create_app(path))

    radar = client.get("/api/market-radar")
    asset = client.get("/api/assets/BTCUSDT/15m")
    archive = client.get("/api/signals?limit=10&offset=0")
    detail = client.get(f"/api/signals/{signal_id}")
    navigation = client.get("/api/navigation")

    assert radar.status_code == 200
    assert radar.json()["items"][0]["latest"]["signal_freeze_identity"] == signal_id
    assert asset.status_code == 200
    assert asset.json()["latest_by_provider"][0]["signal_freeze_identity"] == signal_id
    assert archive.status_code == 200
    assert archive.json()["signals"][0]["signal_freeze_identity"] == signal_id
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["signal"]["signal_freeze_identity"] == signal_id
    assert detail_body["candle_count"] == 2
    assert len(detail_body["methodologies"]) == 3
    assert len(detail_body["pairwise_relations"]) == 1
    assert detail_body["geometry"] is None
    assert navigation.status_code == 200
    nav_body = navigation.json()
    assert nav_body["status"] == "ready"
    assert nav_body["contexts"] == [
        {
            "exchange": "bybit",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "freeze_count": 1,
            "latest_frozen_at_ms": 1100,
        }
    ]


def test_empty_performance_is_not_zero_win_rate(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    seed_ledger(path)
    client = TestClient(create_app(path))

    response = client.get("/api/performance")

    assert response.status_code == 200
    assert response.json() == {
        "status": "empty",
        "outcome_snapshot_count": 0,
        "evidence_class_counts": [],
        "groups": [],
    }


def test_api_has_no_post_command_surface(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    seed_ledger(path)
    client = TestClient(create_app(path))

    assert client.post("/api/command-center").status_code == 405
    assert client.post("/api/signals").status_code == 405
    assert client.post("/api/paper/mission-control").status_code == 405


def test_invalid_signal_identity_is_rejected_as_bad_request(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    seed_ledger(path)
    client = TestClient(create_app(path))

    response = client.get("/api/signals/not-a-sha")

    assert response.status_code == 400
