from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pytest
from test_intelligence_stream_read_model import _create_read_fixture

from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.product.final_product_read_model import (
    FinalProductReadError,
    FinalProductReadModel,
)
from crypto_signal.product.intelligence_stream_family import (
    IntelligenceStreamFamilyRuntime,
    build_family_snapshot,
)
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
)
from crypto_signal.product.intelligence_stream_models import (
    StreamCategory,
    StreamImportance,
)
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
)
from crypto_signal.product.intelligence_stream_system_view import (
    STREAM_SYSTEM_VIEW_SCHEMA_VERSION,
    IntelligenceStreamSystemViewRuntime,
)


def _sha(label: str) -> str:
    return canonical_sha256({"label": label})


def _family_rows() -> tuple[dict[str, object], ...]:
    return (
        {
            "direction": "bullish",
            "evidence_domains": ("geometry",),
            "family": "geometry",
            "material_conflict_count": 0,
            "opposition_points": "0.00",
            "prior_weight": "0.20",
            "source_evidence_identities": (_sha("geometry-evidence"),),
            "source_narrative_identity": _sha("geometry-narrative"),
            "source_quality": "fresh",
            "state": "observed",
            "state_label": "geometry_supported",
            "support_points": "20.00",
            "timeframe": "4h",
            "weight_points": "20.00",
        },
        {
            "direction": "bullish",
            "evidence_domains": ("liquidity",),
            "family": "liquidity",
            "material_conflict_count": 0,
            "opposition_points": "0.00",
            "prior_weight": "0.25",
            "source_evidence_identities": (_sha("liquidity-evidence"),),
            "source_narrative_identity": _sha("liquidity-narrative"),
            "source_quality": "fresh",
            "state": "observed",
            "state_label": "liquidity_supported",
            "support_points": "25.00",
            "timeframe": "4h",
            "weight_points": "25.00",
        },
        {
            "direction": "bullish",
            "evidence_domains": ("order_flow",),
            "family": "order_flow",
            "material_conflict_count": 0,
            "opposition_points": "0.00",
            "prior_weight": "0.25",
            "source_evidence_identities": (_sha("flow-evidence"),),
            "source_narrative_identity": _sha("flow-narrative"),
            "source_quality": "fresh",
            "state": "observed",
            "state_label": "flow_supported",
            "support_points": "25.00",
            "timeframe": "4h",
            "weight_points": "25.00",
        },
        {
            "direction": "bearish",
            "evidence_domains": ("derivatives",),
            "family": "derivatives",
            "material_conflict_count": 1,
            "opposition_points": "15.00",
            "prior_weight": "0.15",
            "source_evidence_identities": (_sha("derivatives-evidence"),),
            "source_narrative_identity": _sha("derivatives-narrative"),
            "source_quality": "fresh",
            "state": "observed",
            "state_label": "derivatives_conflict",
            "support_points": "0.00",
            "timeframe": "4h",
            "weight_points": "15.00",
        },
        {
            "direction": None,
            "evidence_domains": (),
            "family": "onchain",
            "material_conflict_count": 0,
            "opposition_points": "0.00",
            "prior_weight": "0.15",
            "source_evidence_identities": (),
            "source_narrative_identity": None,
            "source_quality": "unavailable",
            "state": "no_evidence",
            "state_label": "unavailable",
            "support_points": "0.00",
            "timeframe": None,
            "weight_points": "15.00",
        },
    )


def _payload(*, symbol: str, event_at_ms: int, summary: str) -> dict[str, object]:
    semantic_identity = canonical_sha256(
        {"symbol": symbol, "event_at_ms": event_at_ms, "summary": summary}
    )
    payload_without_identity: dict[str, object] = {
        "analytical_view": {
            "schema_version": "intelligence-stream-system-view-analytical-v1/1",
            "stance": {
                "effective_stance": "bullish",
                "support_score_0_100": "70.00",
                "opposition_score_0_100": "15.00",
            },
            "main_contradiction": {
                "family": "derivatives",
                "opposition_points": "15.00",
            },
            "uncertainty": {
                "probability_status": "not_calibrated",
                "event_risk_state": "caution",
                "provider_quality_state": "healthy",
            },
        },
        "category": "intelligence",
        "composer_version": "test-system-view-composer",
        "event_at_ms": event_at_ms,
        "fact_bundle": {
            "schema_version": "intelligence-stream-system-view-fact-v1/1",
            "symbol": symbol,
            "timeframe": "4h",
            "confluence_support_score_0_100": "70.00",
            "confluence_opposition_score_0_100": "15.00",
            "evidence_coverage_0_100": "85.00",
            "probability_status": "not_calibrated",
            "score_semantic": "weighted_directional_family_vote_not_probability",
            "event_context_state": "caution",
            "provider_quality_state": "healthy",
            "trigger_zone": {"low": "62000", "high": "62500"},
            "target_zone": {"low": "65000", "high": "66000"},
            "invalidation_price": "60800",
            "family_contributions": _family_rows(),
        },
        "importance": "important",
        "production_authority": False,
        "read_only": True,
        "real_capital": 0,
        "schema_version": STREAM_SYSTEM_VIEW_SCHEMA_VERSION,
        "semantic_identity": semantic_identity,
        "source_kind": "deterministic",
        "state": "bullish",
        "subtype": "system_view_updated",
        "symbol": symbol,
        "text": {
            "collapsed_text": summary,
            "simple_text": summary,
            "technical_text": "test",
            "intelligence_text": summary,
            "decision_text": "test",
            "capital_text": "test",
        },
        "timeframe": "4h",
    }
    narrative_identity = canonical_sha256(payload_without_identity)
    return {
        "narrative_identity": narrative_identity,
        **payload_without_identity,
    }


def _create_stream_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE stream_system_view_messages (
                narrative_identity TEXT PRIMARY KEY,
                semantic_identity TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                event_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            )
            """
        )


def _insert(path: Path, payload: dict[str, object]) -> None:
    encoded = canonical_json(payload)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO stream_system_view_messages (
                narrative_identity,
                semantic_identity,
                symbol,
                timeframe,
                event_at_ms,
                payload_json,
                payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["narrative_identity"],
                payload["semantic_identity"],
                payload["symbol"],
                payload["timeframe"],
                payload["event_at_ms"],
                encoded,
                sha256_text(encoded),
            ),
        )


def _all_text(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for key, item in value.items():
            result.extend(_all_text(key))
            result.extend(_all_text(item))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            result.extend(_all_text(item))
        return result
    return []


def test_market_pulse_missing_db_is_explicit_and_non_creating(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    view = FinalProductReadModel(stream_ledger_path=path).market_pulse(
        symbols=("BTCUSDT", "ETHUSDT"),
        observed_at_ms=1000,
    )

    assert view.availability_label == "Veri eksik"
    assert view.items == ()
    assert view.missing_symbols == ("BTCUSDT", "ETHUSDT")
    assert view.real_capital == 0
    assert not path.exists()


def test_market_pulse_is_point_in_time_and_read_only(tmp_path: Path) -> None:
    path = tmp_path / "stream.sqlite3"
    _create_stream_db(path)
    _insert(path, _payload(symbol="BTCUSDT", event_at_ms=1000, summary="eski görünüm"))
    _insert(path, _payload(symbol="BTCUSDT", event_at_ms=2000, summary="yeni görünüm"))
    before = path.read_bytes()

    view = FinalProductReadModel(stream_ledger_path=path).market_pulse(
        symbols=("BTCUSDT",),
        observed_at_ms=1500,
        stale_after_ms=1000,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert len(view.items) == 1
    item = view.items[0]
    assert item.updated_at_ms == 1000
    assert item.summary == "eski görünüm"
    assert item.freshness_label == "Güncel"
    assert item.stance_label == "Yükseliş yönlü destek"
    assert item.support_score_0_100 == "70.00"
    assert item.opposition_score_0_100 == "15.00"
    assert item.evidence_coverage_0_100 == "85.00"
    assert item.probability_label == "Kalibre edilmiş olasılık değil"
    assert item.event_risk_label == "Dikkat"
    assert item.provider_quality_label == "Kaynaklar sağlıklı"
    assert item.audit is None
    assert path.read_bytes() == before
    assert not Path(f"{path}-wal").exists()


def test_market_pulse_customer_projection_hides_identity_and_raw_states(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    _create_stream_db(path)
    _insert(path, _payload(symbol="BTCUSDT", event_at_ms=1000, summary="özet"))

    view = FinalProductReadModel(stream_ledger_path=path).market_pulse(
        symbols=("BTCUSDT",),
        observed_at_ms=1000,
    )
    raw = asdict(view)
    texts = _all_text(raw)

    assert not any(re.fullmatch(r"[0-9a-f]{64}", value) for value in texts)
    forbidden = {
        "not_calibrated",
        "no_evidence",
        "observed",
        "abstain",
        "unavailable",
        "unresolved",
        "system_view_updated",
    }
    assert forbidden.isdisjoint(texts)
    assert tuple(item.family_label for item in view.items[0].families) == (
        "Geometri",
        "Likidite",
        "Emir Akışı",
        "Türevler",
        "On-chain",
    )
    assert view.items[0].families[-1].state_label == "Veri eksik"


def test_market_pulse_audit_mode_preserves_exact_provenance(tmp_path: Path) -> None:
    path = tmp_path / "stream.sqlite3"
    _create_stream_db(path)
    payload = _payload(symbol="BTCUSDT", event_at_ms=1000, summary="özet")
    _insert(path, payload)

    view = FinalProductReadModel(stream_ledger_path=path).market_pulse(
        symbols=("BTCUSDT",),
        observed_at_ms=1000,
        include_audit=True,
    )

    item = view.items[0]
    assert item.audit is not None
    assert item.audit.narrative_identity == payload["narrative_identity"]
    assert item.audit.semantic_identity == payload["semantic_identity"]
    geometry = item.families[0]
    assert geometry.audit is not None
    assert geometry.audit.source_narrative_identity == _sha("geometry-narrative")
    assert geometry.audit.source_evidence_identities == (_sha("geometry-evidence"),)


def test_market_pulse_marks_stale_and_partial_without_fabricating_missing_asset(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    _create_stream_db(path)
    _insert(path, _payload(symbol="BTCUSDT", event_at_ms=1000, summary="özet"))

    view = FinalProductReadModel(stream_ledger_path=path).market_pulse(
        symbols=("BTCUSDT", "ETHUSDT"),
        observed_at_ms=5000,
        stale_after_ms=1000,
    )

    assert view.availability_label == "Kısmi veri"
    assert view.missing_symbols == ("ETHUSDT",)
    assert len(view.items) == 1
    assert view.items[0].freshness_label == "Güncel değil"


def _b1_geometry(*, event_at_ms: int = 2_000, suffix: str = "1"):
    return build_family_snapshot(
        projector_id="market_geometry_change",
        family=ConfluenceFamily.GEOMETRY,
        category=StreamCategory.MARKET,
        subtype="geometry_material_change",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=_sha(f"b1-geometry-source-{suffix}"),
        source_scope="bybit:spot:signal_geometry",
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe="15m",
        event_at_ms=event_at_ms,
        source_as_of_ms=event_at_ms - 10,
        evidence_identities=(_sha(f"b1-geometry-evidence-{suffix}"),),
        evidence_domains=("frozen_chart", "geometry"),
        state_label="active:bullish:geometry",
        state_components=(
            ("direction", "bullish"),
            ("entry_reference_price", "101"),
            ("entry_zone_high", "102"),
            ("entry_zone_low", "100"),
            ("geometry_methodology", "harmonic"),
            ("geometry_present", "yes"),
            ("invalidation_price", "95"),
            ("invalidation_trigger", "close_beyond"),
            ("setup_type", "fixture"),
            ("signal_state", "active"),
            ("target_01_T1_price", "108"),
            ("target_01_T1_rr", "2"),
            ("target_count", "1"),
        ),
        direction="bullish",
        source_quality="exact_immutable_signal_freeze",
    )


def _b1_family(
    family: ConfluenceFamily,
    *,
    event_at_ms: int,
    direction: str | None,
    state_label: str,
    suffix: str,
):
    projector = {
        ConfluenceFamily.LIQUIDITY: "liquidity_change",
        ConfluenceFamily.ORDER_FLOW: "order_flow_change",
        ConfluenceFamily.DERIVATIVES: "derivatives_change",
    }[family]
    subtype = {
        ConfluenceFamily.LIQUIDITY: "liquidity_material_change",
        ConfluenceFamily.ORDER_FLOW: "order_flow_material_change",
        ConfluenceFamily.DERIVATIVES: "derivatives_material_change",
    }[family]
    domain = {
        ConfluenceFamily.LIQUIDITY: "liquidity",
        ConfluenceFamily.ORDER_FLOW: "order_flow",
        ConfluenceFamily.DERIVATIVES: "derivatives",
    }[family]
    return build_family_snapshot(
        projector_id=projector,
        family=family,
        category=StreamCategory.INTELLIGENCE,
        subtype=subtype,
        importance=StreamImportance.IMPORTANT,
        source_event_identity=_sha(f"b1-{family.value}-source-{suffix}"),
        source_scope=f"bybit:spot:{family.value}",
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe="microstructure" if family is not ConfluenceFamily.DERIVATIVES else "15m",
        event_at_ms=event_at_ms,
        source_as_of_ms=event_at_ms - 5,
        evidence_identities=(_sha(f"b1-{family.value}-evidence-{suffix}"),),
        evidence_domains=(domain,),
        state_label=state_label,
        state_components=(("label", state_label),),
        direction=direction,
        source_quality="measured",
        uncertainty_flags=(
            ("fixture_uncertainty",)
            if family is ConfluenceFamily.DERIVATIVES
            else ()
        ),
    )


def _seed_b1_stream(path: Path) -> dict[str, object]:
    IntelligenceStreamForwardRuntime(path).ensure_activated(activated_at_ms=1_000)
    family_runtime = IntelligenceStreamFamilyRuntime(path)
    geometry = _b1_geometry()
    liquidity = _b1_family(
        ConfluenceFamily.LIQUIDITY,
        event_at_ms=2_100,
        direction="bullish",
        state_label="measured:bullish",
        suffix="1",
    )
    order_flow = _b1_family(
        ConfluenceFamily.ORDER_FLOW,
        event_at_ms=2_200,
        direction="bullish",
        state_label="buy_pressure",
        suffix="1",
    )
    derivatives = _b1_family(
        ConfluenceFamily.DERIVATIVES,
        event_at_ms=2_300,
        direction="bearish",
        state_label="funding_crowded",
        suffix="1",
    )
    snapshots = (geometry, liquidity, order_flow, derivatives)
    projected = tuple(
        family_runtime.project(item, activated_at_ms=1_000)
        for item in snapshots
    )
    system = IntelligenceStreamSystemViewRuntime(path).compose_and_append(
        symbol="BTCUSDT",
        event_at_ms=3_000,
        family_snapshots=snapshots,
    )
    return {
        "snapshots": snapshots,
        "projected": projected,
        "system": system,
    }


def test_attention_and_family_summary_missing_db_are_explicit_noncreating(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing-b1.sqlite3"
    model = FinalProductReadModel(stream_ledger_path=path)

    attention = model.attention_situations(observed_at_ms=10_000)
    family = model.five_family_summary(
        symbol="BTCUSDT",
        observed_at_ms=10_000,
    )

    assert attention.availability_label == "Veri eksik"
    assert attention.items == ()
    assert family.availability_label == "Veri eksik"
    assert family.families == ()
    assert not path.exists()


def test_attention_reuses_materiality_and_prioritizes_newer_system_view(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream-b1.sqlite3"
    seeded = _seed_b1_stream(path)
    before = path.read_bytes()
    wal_path = Path(f"{path}-wal")
    wal_before = wal_path.read_bytes() if wal_path.exists() else None

    view = FinalProductReadModel(stream_ledger_path=path).attention_situations(
        observed_at_ms=3_000,
        limit=5,
        include_audit=True,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert view.items
    assert view.items[0].source_label == "System View"
    assert view.items[0].materiality_label == "Güncel sistem görünümü"
    assert view.items[0].updated_at_ms == 3_000
    assert any(
        item.source_label == "Intelligence Stream"
        and item.materiality_label == "Önemli değişim"
        for item in view.items
    )
    assert all(item.importance_label in {"Önemli", "Kritik"} for item in view.items)
    assert view.items[0].audit is not None
    assert view.items[0].audit.narrative_identity == seeded["system"].narrative_identity
    assert path.read_bytes() == before
    assert (wal_path.read_bytes() if wal_path.exists() else None) == wal_before


def test_attention_does_not_promote_routine_system_view(tmp_path: Path) -> None:
    path = tmp_path / "stream-routine.sqlite3"
    IntelligenceStreamForwardRuntime(path).ensure_activated(activated_at_ms=1_000)
    result = IntelligenceStreamSystemViewRuntime(path).compose_and_append(
        symbol="BTCUSDT",
        event_at_ms=2_000,
        family_snapshots=(),
    )
    assert result.stance == "watch"

    view = FinalProductReadModel(stream_ledger_path=path).attention_situations(
        observed_at_ms=2_000,
    )

    assert view.availability_label == "Dikkat gerektiren durum yok"
    assert view.items == ()


def test_five_family_summary_enriches_exact_family_sources_and_keeps_missing_explicit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream-family.sqlite3"
    seeded = _seed_b1_stream(path)
    before = path.read_bytes()
    wal_path = Path(f"{path}-wal")
    wal_before = wal_path.read_bytes() if wal_path.exists() else None

    view = FinalProductReadModel(stream_ledger_path=path).five_family_summary(
        symbol="BTCUSDT",
        observed_at_ms=3_000,
        include_audit=True,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert view.stance_label == "Yükseliş yönlü destek"
    assert tuple(item.family_label for item in view.families) == (
        "Geometri",
        "Likidite",
        "Emir Akışı",
        "Türevler",
        "On-chain",
    )
    geometry = view.families[0]
    assert geometry.source_as_of_ms == 1_990
    assert geometry.freshness_label == "Güncel"
    assert geometry.evidence_domain_labels == (
        "Dondurulmuş grafik",
        "Geometri",
    )
    assert geometry.audit is not None
    assert geometry.audit.source_narrative_identity == (
        seeded["projected"][0].narrative_identity
    )

    derivatives = view.families[3]
    assert derivatives.uncertainty_label == "1 belirsizlik işareti"
    assert derivatives.audit is not None
    assert derivatives.audit.uncertainty_flags == ("fixture_uncertainty",)

    onchain = view.families[4]
    assert onchain.state_label == "Veri eksik"
    assert onchain.source_as_of_ms is None
    assert onchain.freshness_label == "Veri eksik"
    assert onchain.evidence_domain_labels == ()
    assert onchain.audit is None

    assert path.read_bytes() == before
    assert (wal_path.read_bytes() if wal_path.exists() else None) == wal_before


def test_b1_customer_projections_hide_sha_and_internal_materiality_codes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream-customer.sqlite3"
    _seed_b1_stream(path)
    model = FinalProductReadModel(stream_ledger_path=path)

    attention = asdict(
        model.attention_situations(
            observed_at_ms=3_000,
            include_audit=False,
        )
    )
    family = asdict(
        model.five_family_summary(
            symbol="BTCUSDT",
            observed_at_ms=3_000,
            include_audit=False,
        )
    )
    texts = _all_text({"attention": attention, "family": family})

    assert not any(re.fullmatch(r"[0-9a-f]{64}", value) for value in texts)
    forbidden = {
        "material",
        "publish",
        "routine",
        "no_evidence",
        "observed",
        "not_calibrated",
        "geometry_material_change",
        "liquidity_material_change",
        "order_flow_material_change",
        "derivatives_material_change",
        "fixture_uncertainty",
    }
    assert forbidden.isdisjoint(texts)


def test_workspace_missing_db_and_unknown_narrative_are_explicit(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing-workspace.sqlite3"
    model = FinalProductReadModel(stream_ledger_path=missing_path)
    missing = model.workspace_summary(
        narrative_identity=_sha("missing-workspace"),
        observed_at_ms=10_000,
    )

    assert missing.availability_label == "Veri eksik"
    assert not missing_path.exists()

    stream_path = tmp_path / "known-workspace.sqlite3"
    _create_read_fixture(stream_path)
    unknown = FinalProductReadModel(
        stream_ledger_path=stream_path
    ).workspace_summary(
        narrative_identity=_sha("unknown-workspace"),
        observed_at_ms=10_000,
    )
    assert unknown.availability_label == "Mesaj bulunamadı"


def test_workspace_system_view_reuses_exact_conditions_without_probability_inference(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workspace-system.sqlite3"
    seeded = _seed_b1_stream(path)
    system = seeded["system"]
    assert system.narrative_identity is not None
    before = path.read_bytes()
    wal_path = Path(f"{path}-wal")
    wal_before = wal_path.read_bytes() if wal_path.exists() else None

    view = FinalProductReadModel(stream_ledger_path=path).workspace_summary(
        narrative_identity=system.narrative_identity,
        observed_at_ms=3_000,
        include_audit=True,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert view.message_kind_label == "Sistem görünümü"
    assert view.symbol == "BTCUSDT"
    assert view.state_label == "Yükseliş yönlü destek"
    assert view.support_balance_label == "Destek tarafı daha güçlü"
    assert view.trigger_zone == {"low": "100.00", "high": "102.00"}
    assert view.target_zone == {"low": "108.00", "high": "108.00"}
    assert view.invalidation_price == "95.00"
    assert view.probability_label == "Kalibre edilmiş olasılık değil"
    assert view.decision_evidence_label == (
        "Bu görünüm için ayrı karar kanıtı uygulanmaz"
    )
    assert view.audit is not None
    assert view.audit.narrative_identity == system.narrative_identity
    assert path.read_bytes() == before
    assert (wal_path.read_bytes() if wal_path.exists() else None) == wal_before


def test_workspace_family_keeps_decision_conditions_unavailable_and_summarizes_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workspace-family.sqlite3"
    seeded = _seed_b1_stream(path)
    family_narrative = seeded["projected"][0].narrative_identity
    assert family_narrative is not None

    view = FinalProductReadModel(stream_ledger_path=path).workspace_summary(
        narrative_identity=family_narrative,
        observed_at_ms=3_000,
        include_audit=True,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert view.message_kind_label == "Geometri görünümü"
    assert view.direction_label == "Yükseliş"
    assert view.trigger_zone is None
    assert view.target_zone is None
    assert view.invalidation_price is None
    assert view.probability_label == "Bu kanıt ailesi için uygulanmaz"
    assert view.evidence_label in {
        "Doğrulanmış kanıt mevcut",
        "Kanıt kimliği doğrulandı; ayrıntı sınırlı",
    }
    assert view.audit is not None
    assert view.audit.detail_kind == "family"
    assert view.audit.fact_bundle_identity is not None


def test_workspace_decision_uses_stream_fact_and_does_not_create_optional_decision_db(
    tmp_path: Path,
) -> None:
    stream_path = tmp_path / "workspace-decision.sqlite3"
    identities = _create_read_fixture(stream_path)
    decision_path = tmp_path / "missing-decision.sqlite3"
    before = stream_path.read_bytes()

    view = FinalProductReadModel(
        stream_ledger_path=stream_path,
        decision_evidence_path=decision_path,
    ).workspace_summary(
        narrative_identity=identities["btc-issued"],
        observed_at_ms=1_000,
        include_audit=True,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert view.message_kind_label == "Karar görünümü"
    assert view.symbol == "BTCUSDT"
    assert view.direction_label == "Yükseliş"
    assert view.support_balance_label == "Destek tarafı daha güçlü"
    assert view.trigger_zone == {"low": 62000, "high": 62500}
    assert view.target_zone == {"low": 65000, "high": 66000}
    assert view.invalidation_price == "60750.00"
    assert view.probability_label == "Kalibre edilmiş olasılık değil"
    assert view.evidence_label == "Kanıt kimliği doğrulandı; ayrıntı sınırlı"
    assert view.decision_evidence_label == "Ek karar kanıtı kaynağı bağlı değil"
    assert view.audit is not None
    assert view.audit.detail_kind == "decision"
    assert view.audit.forecast_identity is not None
    assert view.audit.proof_identity is not None
    assert not decision_path.exists()
    assert stream_path.read_bytes() == before


def _create_conflicting_decision_evidence_db(
    path: Path,
    *,
    forecast_identity: str,
) -> None:
    proof_payload = {
        "forecast_identity": forecast_identity,
        "proof_identity": _sha("conflicting-proof"),
        "signal_freeze_identity": _sha("conflicting-signal"),
    }
    encoded = canonical_json(proof_payload)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE r20_forecasts (
                forecast_identity TEXT PRIMARY KEY
            );
            CREATE TABLE r20_resolutions (
                forecast_identity TEXT PRIMARY KEY
            );
            CREATE TABLE r20_5_decision_proofs (
                forecast_identity TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );
            CREATE TABLE r20_5_live_feed_events (
                event_identity TEXT PRIMARY KEY
            );
            """
        )
        connection.execute(
            """
            INSERT INTO r20_5_decision_proofs (
                forecast_identity,
                payload_json,
                payload_sha256
            ) VALUES (?, ?, ?)
            """,
            (
                forecast_identity,
                encoded,
                sha256_text(encoded),
            ),
        )


def test_workspace_configured_conflicting_decision_proof_fails_closed(
    tmp_path: Path,
) -> None:
    stream_path = tmp_path / "workspace-conflict.sqlite3"
    identities = _create_read_fixture(stream_path)
    detail = IntelligenceStreamReadModel(stream_path).read_message_detail(
        identities["btc-issued"]
    )
    assert detail is not None
    fact = detail["fact_bundle"]
    assert isinstance(fact, dict)
    forecast_identity = str(fact["forecast_identity"])

    decision_path = tmp_path / "decision-conflict.sqlite3"
    _create_conflicting_decision_evidence_db(
        decision_path,
        forecast_identity=forecast_identity,
    )

    with pytest.raises(
        FinalProductReadError,
        match="Decision Evidence proof lineage mismatch",
    ):
        FinalProductReadModel(
            stream_ledger_path=stream_path,
            decision_evidence_path=decision_path,
        ).workspace_summary(
            narrative_identity=identities["btc-issued"],
            observed_at_ms=1_000,
        )


def test_workspace_customer_projection_hides_sha_and_raw_state_vocabulary(
    tmp_path: Path,
) -> None:
    system_path = tmp_path / "workspace-customer-system.sqlite3"
    seeded = _seed_b1_stream(system_path)
    system = seeded["system"]
    family_narrative = seeded["projected"][0].narrative_identity
    assert system.narrative_identity is not None
    assert family_narrative is not None

    decision_path = tmp_path / "workspace-customer-decision.sqlite3"
    identities = _create_read_fixture(decision_path)

    payloads = (
        asdict(
            FinalProductReadModel(
                stream_ledger_path=system_path
            ).workspace_summary(
                narrative_identity=system.narrative_identity,
                observed_at_ms=3_000,
            )
        ),
        asdict(
            FinalProductReadModel(
                stream_ledger_path=system_path
            ).workspace_summary(
                narrative_identity=family_narrative,
                observed_at_ms=3_000,
            )
        ),
        asdict(
            FinalProductReadModel(
                stream_ledger_path=decision_path
            ).workspace_summary(
                narrative_identity=identities["btc-issued"],
                observed_at_ms=1_000,
            )
        ),
    )
    texts = _all_text(payloads)

    assert not any(re.fullmatch(r"[0-9a-f]{64}", value) for value in texts)
    forbidden = {
        "READY_EXACT",
        "IDENTITY_ONLY_EXACT",
        "UNAVAILABLE_EXPLICIT",
        "not_calibrated",
        "material",
        "publish",
        "fixture_material",
        "probability_not_calibrated",
        "not_bound",
        "geometry_material_change",
    }
    assert forbidden.isdisjoint(texts)
