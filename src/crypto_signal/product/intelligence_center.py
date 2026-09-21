"""Read-only Intelligence Center projection for accepted research evidence.

This product module never executes research engines and never changes production
weights.  It exposes an accepted capability catalog and, when explicitly
configured, reads the append-only Learning Memory SQLite store in read-only mode.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

from crypto_signal.ledger.serialization import canonical_sha256

REAL_CAPITAL = 0
INTELLIGENCE_CENTER_VERSION = "read-only-intelligence-center-v1/1"


_ACCEPTED_ENGINES: tuple[dict[str, object], ...] = (
    {
        "engine_id": "regime",
        "group": "market_intelligence",
        "title_tr": "Rejim",
        "engine_version": "regime-labeling-v1/1",
        "source_module": "src/crypto_signal/intelligence/regime.py",
        "what_it_says_tr": "Piyasa koşulunu sürdürme, geçiş veya belirsizlik bağlamıyla etiketler.",
        "why_it_matters_tr": "Aynı sinyalin farklı piyasa rejimlerinde aynı anlamı taşımadığını görünür kılar.",
    },
    {
        "engine_id": "trend_momentum",
        "group": "market_intelligence",
        "title_tr": "Trend / Momentum",
        "engine_version": "trend-momentum-v1/1",
        "source_module": "src/crypto_signal/intelligence/trend_momentum.py",
        "what_it_says_tr": "Trend ve momentum bağlamını bağımsız araştırma kanıtı olarak ölçer.",
        "why_it_matters_tr": "Yönlü yapıların güçlü mü zayıf mı olduğunu ana metodolojiden ayrı izlemeyi sağlar.",
    },
    {
        "engine_id": "mean_reversion",
        "group": "market_intelligence",
        "title_tr": "Ortalamaya Dönüş",
        "engine_version": "mean-reversion-v1/1",
        "source_module": "src/crypto_signal/intelligence/mean_reversion.py",
        "what_it_says_tr": "Fiyatın yerel dengeye göre aşırılaşma ve geri dönüş bağlamını ölçer.",
        "why_it_matters_tr": "Trend kanıtıyla çelişebilen ters-yönlü bağlamı ayrı tutar.",
    },
    {
        "engine_id": "breakout_volatility",
        "group": "market_intelligence",
        "title_tr": "Kırılım / Volatilite",
        "engine_version": "breakout-volatility-v1/1",
        "source_module": "src/crypto_signal/intelligence/breakout_volatility.py",
        "what_it_says_tr": "Kırılım ve volatilite genişleme/daralma bağlamını betimler.",
        "why_it_matters_tr": "Hareketin yapısal kırılım mı yoksa gürültü mü olabileceğini ayrı kanıt olarak gösterir.",
    },
    {
        "engine_id": "derivatives",
        "group": "market_intelligence",
        "title_tr": "Türevler / Kaldıraç",
        "engine_version": "bounded-derivatives-context-v1/1",
        "source_module": "src/crypto_signal/intelligence/derivatives_context.py",
        "what_it_says_tr": "Türev piyasa ve kaldıraç bağlamını sınırlı araştırma kanıtı olarak taşır.",
        "why_it_matters_tr": "Spot fiyat hareketinin kaldıraçlı pozisyonlanma ile desteklenip desteklenmediğini sorgular.",
    },
    {
        "engine_id": "order_flow",
        "group": "market_intelligence",
        "title_tr": "Order Flow / Mikro Yapı",
        "engine_version": "order-flow-microstructure-v1/1",
        "source_module": "src/crypto_signal/intelligence/order_flow_microstructure.py",
        "what_it_says_tr": "Emir akışı ve mikro yapı bağlamını ayrı bir gözlem katmanı olarak raporlar.",
        "why_it_matters_tr": "Fiyatın arkasındaki kısa vadeli piyasa davranışını ana sinyalden ayırır.",
    },
    {
        "engine_id": "onchain",
        "group": "market_intelligence",
        "title_tr": "On-chain / Ağ",
        "engine_version": "bitcoin-onchain-network-v1/1",
        "source_module": "src/crypto_signal/intelligence/onchain_network.py",
        "what_it_says_tr": "Ağ ve on-chain kanıtını fiyat grafiğinden bağımsız bağlam olarak sunar.",
        "why_it_matters_tr": "Fiyat dışındaki ağ aktivitesinin destekleyici, çelişkili veya eksik olmasını görünür kılar.",
    },
    {
        "engine_id": "sentiment_attention",
        "group": "market_intelligence",
        "title_tr": "Duyarlılık / İlgi",
        "engine_version": "bounded-sentiment-attention-v1/1",
        "source_module": "src/crypto_signal/intelligence/sentiment_attention.py",
        "what_it_says_tr": "Duyarlılık ve dikkat sinyallerini bounded araştırma bağlamı olarak toplar.",
        "why_it_matters_tr": "Kalabalık davranışının fiyat kanıtıyla aynı yönde mi karşı yönde mi olduğunu ayrı gösterir.",
    },
    {
        "engine_id": "cross_market",
        "group": "market_intelligence",
        "title_tr": "Çapraz Piyasa",
        "engine_version": "cross-market-context-v1/1",
        "source_module": "src/crypto_signal/intelligence/cross_market_context.py",
        "what_it_says_tr": "Diğer piyasa bağlamlarının kripto gözlemiyle ilişkisini betimler.",
        "why_it_matters_tr": "Tek bir varlık grafiğine aşırı güvenmeyi azaltan bağımsız bağlam sağlar.",
    },
    {
        "engine_id": "alpha_symbolic",
        "group": "alpha_factory",
        "title_tr": "Alpha Factory · Sembolik Kurallar",
        "engine_version": "alpha-factory-symbolic-rule-v1/1",
        "source_module": "research/alpha_factory/symbolic_rules.py",
        "what_it_says_tr": "Önceden sınırlandırılmış sembolik araştırma hipotezlerini üretir ve değerlendirir.",
        "why_it_matters_tr": "Yeni fikirleri üretim motoruna dokunmadan, tekrarlanabilir biçimde test eder.",
    },
    {
        "engine_id": "alpha_tree",
        "group": "alpha_factory",
        "title_tr": "Alpha Factory · Ağaç Modelleri",
        "engine_version": "alpha-factory-tree-model-v1/1",
        "source_module": "research/alpha_factory/tree_models.py",
        "what_it_says_tr": "Sınırlı ağaç tabanlı challenger kanıtını araştırma alanında değerlendirir.",
        "why_it_matters_tr": "Doğrusal olmayan etkileşimleri üretime yetki vermeden test etmeyi sağlar.",
    },
    {
        "engine_id": "alpha_cluster",
        "group": "alpha_factory",
        "title_tr": "Alpha Factory · Rejim Kümeleme",
        "engine_version": "alpha-factory-clustering-regime-v1/1",
        "source_module": "research/alpha_factory/clustering_regime.py",
        "what_it_says_tr": "Sonuçları kullanmadan bounded rejim kümeleri oluşturur ve OOS kanıtını betimler.",
        "why_it_matters_tr": "Piyasa davranışındaki farklı bağlamların sonuçlarla karıştırılmadan incelenmesini sağlar.",
    },
    {
        "engine_id": "alpha_interactions",
        "group": "alpha_factory",
        "title_tr": "Alpha Factory · Özellik Etkileşimleri",
        "engine_version": "alpha-factory-feature-interaction-v1/1",
        "source_module": "research/alpha_factory/feature_interactions.py",
        "what_it_says_tr": "Önceden sınırlandırılmış özellik çiftlerinin birlikte taşıdığı kanıtı değerlendirir.",
        "why_it_matters_tr": "Tekil göstergelerin gizleyebileceği kombinasyon etkilerini kontrollü biçimde araştırır.",
    },
    {
        "engine_id": "alpha_evolution",
        "group": "alpha_factory",
        "title_tr": "Alpha Factory · Evrimsel Arama",
        "engine_version": "alpha-factory-evolutionary-search-v1/1",
        "source_module": "research/alpha_factory/evolutionary_search.py",
        "what_it_says_tr": "Deterministik ve bütçesi sınırlı hipotez araması yapar.",
        "why_it_matters_tr": "Geniş fikir uzayını sınırsız optimizasyona dönüşmeden taramayı sağlar.",
    },
    {
        "engine_id": "ml_baseline",
        "group": "alpha_factory",
        "title_tr": "Bounded ML · Baseline",
        "engine_version": "alpha-factory-bounded-ml-baseline-v1/1",
        "source_module": "research/alpha_factory/ml_baseline.py",
        "what_it_says_tr": "Deterministik bounded ML baseline kanıtını yalnız research alanında üretir.",
        "why_it_matters_tr": "ML katkısını klasik araştırma zincirinden ayrı ve yeniden üretilebilir biçimde ölçer.",
    },
    {
        "engine_id": "ml_walk_forward",
        "group": "alpha_factory",
        "title_tr": "Bounded ML · Walk-forward",
        "engine_version": "alpha-factory-ml-walk-forward-v1/1",
        "source_module": "research/alpha_factory/ml_walk_forward.py",
        "what_it_says_tr": "Kronolojik train/OOS fold kanıtını ileri-yürüyen değerlendirmeyle bağlar.",
        "why_it_matters_tr": "Tek bir backtest sonucunun genellenebilirlik gibi sunulmasını engeller.",
    },
    {
        "engine_id": "ml_family_cost_stress",
        "group": "alpha_factory",
        "title_tr": "Bounded ML · Maliyet Stresi",
        "engine_version": "alpha-factory-ml-family-cost-stress-v1/1",
        "source_module": "research/alpha_factory/ml_family_cost_stress.py",
        "what_it_says_tr": "İki accepted ML ailesini aynı sabit maliyet/slippage gridinde stresler.",
        "why_it_matters_tr": "Brüt performansın işlem maliyetleri altında ne kadar kırılgan olduğunu görünür kılar.",
    },
    {
        "engine_id": "ml_family_robustness",
        "group": "alpha_factory",
        "title_tr": "Bounded ML · Robustness / Ablation",
        "engine_version": "alpha-factory-ml-family-robustness-v1/1",
        "source_module": "research/alpha_factory/ml_family_robustness_ablation.py",
        "what_it_says_tr": "Feature, fold ve rejim duyarlılığını refit etmeden ölçer.",
        "why_it_matters_tr": "Bir model ailesinin tek özelliğe veya tek döneme aşırı bağımlılığını ortaya çıkarır.",
    },
    {
        "engine_id": "ml_untouched_forward",
        "group": "alpha_factory",
        "title_tr": "Bounded ML · Untouched-forward",
        "engine_version": "alpha-factory-ml-family-untouched-forward-v1/1",
        "source_module": "research/alpha_factory/ml_family_untouched_forward.py",
        "what_it_says_tr": "Önceden dondurulmuş model sınırını dokunulmamış forward pencerede betimleyici olarak değerlendirir.",
        "why_it_matters_tr": "Retrospektif refit ve kısmi-forward performans sızıntısını engeller.",
    },
    {
        "engine_id": "ml_promotion_dossier",
        "group": "alpha_factory",
        "title_tr": "Bounded ML · Promotion Dossier",
        "engine_version": "alpha-factory-ml-promotion-dossier-v1/1",
        "source_module": "research/alpha_factory/ml_promotion_dossier.py",
        "what_it_says_tr": "Tam bilimsel evidence zincirini tek immutable dossier kimliğinde bağlar.",
        "why_it_matters_tr": "Makine kanıtının otomatik biçimde üretim yetkisine dönüşmesini engeller.",
    },
    {
        "engine_id": "learning_memory",
        "group": "learning_memory",
        "title_tr": "Learning Memory",
        "engine_version": "alpha-factory-learning-memory-v1/1",
        "source_module": "research/alpha_factory/learning_memory.py",
        "what_it_says_tr": "Başarı, başarısızlık, abstention, no-evidence ve not-yet-evaluable kanıtı eşit biçimde saklar.",
        "why_it_matters_tr": "Sistemin geçmişten öğrenmesini sağlarken üretim ağırlıklarını sessizce değiştirmesini engeller.",
    },
)


def accepted_intelligence_catalog() -> tuple[dict[str, object], ...]:
    """Return a detached deterministic projection of accepted research surfaces."""
    return tuple(
        {
            **item,
            "acceptance_status": "accepted_research_only",
            "evidence_state": "accepted_contract",
            "runtime_evidence_status": "not_exposed_as_live_feed",
            "freshness_status": "accepted_contract_not_live",
            "probability_status": "not_calibrated",
            "production_contribution": 0,
            "production_authority": False,
            "read_only": True,
        }
        for item in _ACCEPTED_ENGINES
    )


def build_intelligence_center_payload(
    learning_memory_path: Path | None,
    *,
    observed_at_ms: int,
) -> dict[str, object]:
    if observed_at_ms < 0:
        raise ValueError("observed_at_ms must be non-negative")
    catalog = accepted_intelligence_catalog()
    memory = _read_learning_memory(
        learning_memory_path,
        observed_at_ms=observed_at_ms,
    )
    return {
        "status": "ready",
        "version": INTELLIGENCE_CENTER_VERSION,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "probability_status": "not_calibrated",
        "production_policy": "research_zero_contribution",
        "accepted_engine_count": len(catalog),
        "production_active_engine_count": 0,
        "engines": catalog,
        "learning_memory": memory,
    }


def _read_learning_memory(
    path: Path | None,
    *,
    observed_at_ms: int,
) -> dict[str, object]:
    if path is None:
        return _empty_memory("not_configured", "learning_memory_path_not_configured")
    selected = path.expanduser()
    if not selected.exists():
        return _empty_memory("missing", "learning_memory_file_missing")
    if not selected.is_file():
        return _empty_memory("invalid_evidence", "learning_memory_path_not_file")

    try:
        uri = f"file:{quote(str(selected.resolve()), safe='/')}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            required = {
                "learning_memory_records",
                "learning_memory_relations",
                "learning_memory_lineage",
                "learning_memory_snapshots",
            }
            if not required.issubset(tables):
                return _empty_memory(
                    "invalid_evidence",
                    "learning_memory_schema_incomplete",
                )

            record_rows = connection.execute(
                """
                SELECT record_identity, payload
                FROM learning_memory_records
                ORDER BY record_identity
                """
            ).fetchall()
            relation_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM learning_memory_relations"
                ).fetchone()[0]
            )
            lineage_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM learning_memory_lineage"
                ).fetchone()[0]
            )
            snapshot_row = connection.execute(
                """
                SELECT snapshot_identity, built_at_ms, payload
                FROM learning_memory_snapshots
                ORDER BY built_at_ms DESC, snapshot_identity DESC
                LIMIT 1
                """
            ).fetchone()
    except (OSError, sqlite3.Error, ValueError) as exc:
        return _empty_memory(
            "invalid_evidence",
            "learning_memory_read_failed",
            detail=type(exc).__name__,
        )

    records: list[dict[str, Any]] = []
    try:
        for identity, raw_payload in record_rows:
            payload = _load_object(raw_payload)
            if str(identity) != canonical_sha256(payload):
                raise ValueError("learning record identity mismatch")
            _validate_record(payload)
            records.append({"record_identity": str(identity), **payload})
        latest_snapshot = _validate_snapshot(snapshot_row)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return _empty_memory(
            "invalid_evidence",
            "learning_memory_evidence_invalid",
            detail=str(exc),
        )

    outcome_counts = Counter(str(item["outcome_state"]) for item in records)
    uncertainty_counts = Counter(
        str(item["uncertainty_state"]) for item in records
    )
    evidence_class_counts = Counter(
        str(item["evidence_class"]) for item in records
    )
    latest_observed_to_ms = max(
        (int(item["observed_to_ms"]) for item in records),
        default=None,
    )
    if latest_observed_to_ms is None:
        freshness_status = "no_records"
        latest_age_ms: int | None = None
    elif latest_observed_to_ms <= observed_at_ms:
        freshness_status = "historical_evidence"
        latest_age_ms = observed_at_ms - latest_observed_to_ms
    else:
        freshness_status = "clock_or_synthetic_evidence"
        latest_age_ms = None

    recent = sorted(
        records,
        key=lambda item: (
            int(item["observed_to_ms"]),
            str(item["record_identity"]),
        ),
        reverse=True,
    )[:12]
    recent_payload = [
        {
            "record_identity": item["record_identity"],
            "evidence_class": item["evidence_class"],
            "method_id": item["method_id"],
            "method_version": item["method_version"],
            "asset": item["asset"],
            "timeframe": item["timeframe"],
            "regime": item["regime"],
            "observed_from_ms": item["observed_from_ms"],
            "observed_to_ms": item["observed_to_ms"],
            "outcome_state": item["outcome_state"],
            "uncertainty_state": item["uncertainty_state"],
            "evidence_identities": item["evidence_identities"],
            "gross_r_total": item.get("gross_r_total"),
            "explicit_cost_r_total": item.get("explicit_cost_r_total"),
            "net_r_total": item.get("net_r_total"),
            "production_contribution": 0,
        }
        for item in recent
    ]
    return {
        "status": "ready",
        "reason": None,
        "record_count": len(records),
        "relation_count": relation_count,
        "lineage_count": lineage_count,
        "snapshot_count": 0 if latest_snapshot is None else 1,
        "latest_snapshot": latest_snapshot,
        "latest_observed_to_ms": latest_observed_to_ms,
        "latest_age_ms": latest_age_ms,
        "freshness_status": freshness_status,
        "outcome_counts": tuple(sorted(outcome_counts.items())),
        "uncertainty_counts": tuple(sorted(uncertainty_counts.items())),
        "evidence_class_counts": tuple(sorted(evidence_class_counts.items())),
        "recent_records": recent_payload,
        "winner_selected": False,
        "production_weight_changed": False,
        "production_contribution": 0,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
    }


def _validate_record(payload: dict[str, Any]) -> None:
    required_text = (
        "schema_version",
        "engine_version",
        "evidence_class",
        "method_id",
        "method_version",
        "asset",
        "timeframe",
        "regime",
        "outcome_state",
        "uncertainty_state",
    )
    for key in required_text:
        if not isinstance(payload.get(key), str) or not str(payload[key]).strip():
            raise ValueError(f"learning record {key} invalid")
    for key in ("observed_from_ms", "observed_to_ms", "production_contribution", "real_capital"):
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"learning record {key} invalid")
    if int(payload["observed_to_ms"]) < int(payload["observed_from_ms"]):
        raise ValueError("learning record chronology invalid")
    for key in ("evidence_identities", "uncertainty_evidence_identities"):
        values = payload.get(key)
        if not isinstance(values, list) or not all(
            isinstance(item, str) and _is_sha256(item) for item in values
        ):
            raise ValueError(f"learning record {key} invalid")
    if int(payload["production_contribution"]) != 0:
        raise ValueError("learning record production contribution must remain 0")
    if payload.get("production_authority") is not False:
        raise ValueError("learning record production authority must remain false")
    if payload.get("automatic_promotion") is not False:
        raise ValueError("learning record automatic promotion must remain false")
    if int(payload["real_capital"]) != REAL_CAPITAL:
        raise ValueError("learning record REAL_CAPITAL must remain 0")


def _validate_snapshot(
    row: tuple[object, object, object] | None,
) -> dict[str, object] | None:
    if row is None:
        return None
    identity, built_at_ms, raw_payload = row
    payload = _load_object(raw_payload)
    if str(identity) != canonical_sha256(payload):
        raise ValueError("learning snapshot identity mismatch")
    if payload.get("production_weighting_authority") is not False:
        raise ValueError("learning snapshot weighting authority must remain false")
    if payload.get("champion_write_authority") is not False:
        raise ValueError("learning snapshot champion authority must remain false")
    if payload.get("deploy_authority") is not False:
        raise ValueError("learning snapshot deploy authority must remain false")
    if int(payload.get("real_capital", -1)) != REAL_CAPITAL:
        raise ValueError("learning snapshot REAL_CAPITAL must remain 0")
    return {
        "snapshot_identity": str(identity),
        "built_at_ms": int(built_at_ms),
        "parent_snapshot_identity": payload.get("parent_snapshot_identity"),
        "record_count": len(payload.get("record_identities", [])),
        "relation_count": len(payload.get("redundancy_link_identities", [])),
        "lineage_count": len(payload.get("lineage_link_identities", [])),
        "production_weighting_authority": False,
        "champion_write_authority": False,
        "deploy_authority": False,
        "real_capital": REAL_CAPITAL,
    }


def _empty_memory(
    status: str,
    reason: str,
    *,
    detail: str | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "reason": reason,
        "detail": detail,
        "record_count": 0,
        "relation_count": 0,
        "lineage_count": 0,
        "snapshot_count": 0,
        "latest_snapshot": None,
        "latest_observed_to_ms": None,
        "latest_age_ms": None,
        "freshness_status": "unavailable",
        "outcome_counts": (),
        "uncertainty_counts": (),
        "evidence_class_counts": (),
        "recent_records": (),
        "winner_selected": False,
        "production_weight_changed": False,
        "production_contribution": 0,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
    }


def _load_object(raw_payload: object) -> dict[str, Any]:
    if not isinstance(raw_payload, str):
        raise TypeError("learning payload must be text")
    value = json.loads(raw_payload)
    if not isinstance(value, dict):
        raise TypeError("learning payload must be object")
    return value


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
