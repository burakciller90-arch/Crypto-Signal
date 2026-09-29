from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import pytest
from test_epoch2_accounting import _activate as _activate_epoch2
from test_event_source_product import _seed_successes as _seed_event_source_successes
from test_intelligence_stream_read_model import _create_read_fixture

from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.paper.epoch2_accounting import (
    Epoch2CanonicalLedger,
    build_consolidated_epoch2_snapshot,
    build_epoch2_vault_accounting_snapshot,
)
from crypto_signal.paper.epochs import EPOCH_2_SPEC, PaperVaultId
from crypto_signal.paper.models import PaperPosition, PaperSymbol
from crypto_signal.product.final_product_read_model import (
    FinalProductReadError,
    FinalProductReadModel,
)
from crypto_signal.product.intelligence_stream_capital import (
    STREAM_CAPITAL_MESSAGE_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_capital_decisions import (
    STREAM_CAPITAL_DECISION_MESSAGE_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_capital_lifecycle import (
    STREAM_CAPITAL_LIFECYCLE_MESSAGE_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_capital_sizing import (
    STREAM_CAPITAL_SIZING_MESSAGE_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_family import (
    IntelligenceStreamFamilyRuntime,
    build_family_snapshot,
)
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
)
from crypto_signal.product.intelligence_stream_models import (
    STREAM_ENGINE_VERSION,
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
        "production_authority": False,
        "real_capital": 0,
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


def test_event_rail_missing_source_is_explicit_and_noncreating(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "missing-events.sqlite3"
    view = FinalProductReadModel(
        stream_ledger_path=tmp_path / "missing-stream.sqlite3",
        event_source_runtime_path=event_path,
    ).event_rail(
        observed_at_ms=1_000,
        window_start_ms=1_000,
        window_end_ms=5_000,
        categories=("inflation",),
    )

    assert view.availability_label == "Veri eksik"
    assert view.coverage_label == "Takvim kapsamı kullanılamıyor"
    assert view.summary_label == "Planlı olay verisi doğrulanamadı"
    assert view.items == ()
    assert view.coverages == ()
    assert not event_path.exists()


def test_event_rail_projects_verified_calendar_truth_without_risk_inference(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "events.sqlite3"
    _seed_event_source_successes(event_path, fetched_at_ms=900)
    before = event_path.read_bytes()

    view = FinalProductReadModel(
        stream_ledger_path=tmp_path / "missing-stream.sqlite3",
        event_source_runtime_path=event_path,
    ).event_rail(
        observed_at_ms=1_000,
        window_start_ms=1_000,
        window_end_ms=3_000,
        categories=("inflation",),
        include_audit=True,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert view.coverage_label == "Takvim kapsamı doğrulandı"
    assert view.summary_label == "1 planlı olay bulundu"
    assert view.total_matching_events == 1
    assert len(view.items) == 1
    item = view.items[0]
    assert item.title == "Consumer Price Index"
    assert item.category_label == "Enflasyon"
    assert item.temporal_label == "Yaklaşan olay"
    assert item.scope_label == "Global"
    assert item.source_provider == "bls.gov"
    assert item.source_quality_label == "Resmî kaynak"
    assert item.freshness_label == "Güncel kaynak"
    assert item.audit is not None
    assert len(item.audit.event_identity) == 64

    assert len(view.coverages) == 1
    coverage = view.coverages[0]
    assert coverage.category_labels == ("İstihdam", "Enflasyon")
    assert coverage.source_quality_label == "Resmî kaynak"
    assert coverage.freshness_label == "Güncel kaynak"
    assert coverage.audit is not None
    assert len(coverage.audit.coverage_identity) == 64

    assert view.audit is not None
    assert view.audit.raw_coverage_status == "COMPLETE"
    assert view.audit.latest_calendar_fetch_identities
    assert event_path.read_bytes() == before


def test_event_rail_distinguishes_covered_empty_from_uncovered_empty(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "events-empty.sqlite3"
    _seed_event_source_successes(event_path, fetched_at_ms=900)
    model = FinalProductReadModel(
        stream_ledger_path=tmp_path / "missing-stream.sqlite3",
        event_source_runtime_path=event_path,
    )

    covered = model.event_rail(
        observed_at_ms=1_000,
        window_start_ms=3_000,
        window_end_ms=4_000,
        categories=("inflation",),
    )
    uncovered = model.event_rail(
        observed_at_ms=1_000,
        window_start_ms=6_000,
        window_end_ms=7_000,
        categories=("inflation",),
    )

    assert covered.items == ()
    assert covered.coverage_label == "Takvim kapsamı doğrulandı"
    assert covered.summary_label == "Bu kapsamda planlı olay yok"

    assert uncovered.items == ()
    assert uncovered.coverage_label == "Takvim kapsamı eksik"
    assert uncovered.summary_label == "Planlı olay verisi doğrulanamadı"


def test_event_rail_customer_payload_hides_sha_raw_enums_and_database_vocabulary(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "events-customer.sqlite3"
    _seed_event_source_successes(event_path, fetched_at_ms=900)

    payload = asdict(
        FinalProductReadModel(
            stream_ledger_path=tmp_path / "missing-stream.sqlite3",
            event_source_runtime_path=event_path,
        ).event_rail(
            observed_at_ms=1_000,
            window_start_ms=1_000,
            window_end_ms=3_000,
            categories=("inflation",),
            include_audit=False,
        )
    )
    texts = _all_text(payload)

    assert not any(re.fullmatch(r"[0-9a-f]{64}", value) for value in texts)
    forbidden = {
        "COMPLETE",
        "INCOMPLETE",
        "UNAVAILABLE",
        "SOURCE_SCOPED_ONLY",
        "official",
        "primary_provider",
        "secondary_aggregator",
        "unverified",
        "inflation",
        "structured_event_observations",
        "event_source_runtime",
    }
    assert forbidden.isdisjoint(texts)


def _seed_measured_epoch2(tmp_path: Path) -> Path:
    _, _, _, initial = _activate_epoch2(tmp_path)
    epoch2_path = tmp_path / EPOCH_2_SPEC.ledger_filename
    ledger = Epoch2CanonicalLedger(epoch2_path)
    activation = initial.activation
    previous = {item.vault_id: item for item in initial.vault_snapshots}

    core = build_epoch2_vault_accounting_snapshot(
        activation,
        vault_id=PaperVaultId.CORE,
        snapshot_at_ms=2_000,
        cash_usdt=Decimal(500),
        positions=(PaperPosition(PaperSymbol.BTCUSDT, Decimal("1.25")),),
        marked_exposure_usdt=Decimal(110),
        realized_pnl_usdt=Decimal(5),
        unrealized_pnl_usdt=Decimal(5),
        fee_usdt=Decimal(1),
        spread_usdt=Decimal("0.5"),
        slippage_usdt=Decimal("0.5"),
        turnover_notional_usdt=Decimal(200),
        closed_trade_count=1,
        win_count=1,
        loss_count=0,
        breakeven_count=0,
        outcome_distribution=(("WIN", 1),),
        source_record_identities=(_sha("fp1d-core"),),
        previous=previous[PaperVaultId.CORE],
    )
    tactical = build_epoch2_vault_accounting_snapshot(
        activation,
        vault_id=PaperVaultId.TACTICAL,
        snapshot_at_ms=2_000,
        cash_usdt=Decimal(250),
        positions=(PaperPosition(PaperSymbol.ETHUSDT, Decimal("0.5")),),
        marked_exposure_usdt=Decimal(45),
        realized_pnl_usdt=Decimal(-3),
        unrealized_pnl_usdt=Decimal(-2),
        fee_usdt=Decimal("0.4"),
        spread_usdt=Decimal("0.3"),
        slippage_usdt=Decimal("0.3"),
        turnover_notional_usdt=Decimal(100),
        closed_trade_count=1,
        win_count=0,
        loss_count=1,
        breakeven_count=0,
        outcome_distribution=(("LOSS", 1),),
        source_record_identities=(_sha("fp1d-tactical"),),
        previous=previous[PaperVaultId.TACTICAL],
    )
    reserve = build_epoch2_vault_accounting_snapshot(
        activation,
        vault_id=PaperVaultId.OPPORTUNITY_RESERVE,
        snapshot_at_ms=2_000,
        cash_usdt=Decimal(100),
        positions=(),
        marked_exposure_usdt=Decimal(0),
        realized_pnl_usdt=Decimal(0),
        unrealized_pnl_usdt=Decimal(0),
        fee_usdt=Decimal(0),
        spread_usdt=Decimal(0),
        slippage_usdt=Decimal(0),
        turnover_notional_usdt=Decimal(0),
        closed_trade_count=0,
        win_count=0,
        loss_count=0,
        breakeven_count=0,
        outcome_distribution=(),
        source_record_identities=(_sha("fp1d-reserve"),),
        previous=previous[PaperVaultId.OPPORTUNITY_RESERVE],
    )
    for item in (core, tactical, reserve):
        assert ledger.append_vault_snapshot(item) is True
    consolidated = build_consolidated_epoch2_snapshot(
        (core, tactical, reserve),
        previous=initial.consolidated_snapshot,
    )
    assert ledger.append_consolidated_snapshot(consolidated) is True
    return epoch2_path


def test_portfolio_summary_missing_epoch2_is_explicit_and_noncreating(
    tmp_path: Path,
) -> None:
    epoch2_path = tmp_path / "missing-epoch2.sqlite3"
    view = FinalProductReadModel(
        stream_ledger_path=tmp_path / "missing-stream.sqlite3",
        epoch2_path=epoch2_path,
    ).portfolio_summary()

    assert view.availability_label == "Epoch 2 portföy verisi kullanılamıyor"
    assert view.program_label == "Paper Capital · Epoch 2"
    assert view.current_equity_usdt is None
    assert view.vaults == ()
    assert view.real_capital == 0
    assert not epoch2_path.exists()


def test_portfolio_summary_preserves_unmeasured_initial_epoch2_and_read_only_bytes(
    tmp_path: Path,
) -> None:
    _, _, _, _ = _activate_epoch2(tmp_path)
    epoch2_path = tmp_path / EPOCH_2_SPEC.ledger_filename
    before = epoch2_path.read_bytes()

    view = FinalProductReadModel(
        stream_ledger_path=tmp_path / "missing-stream.sqlite3",
        epoch2_path=epoch2_path,
    ).portfolio_summary()

    assert view.availability_label == "Doğrulanmış veri"
    assert view.starting_capital_usdt == "1000.00"
    assert view.current_equity_usdt == "1000.00"
    assert view.cash_usdt == "1000.00"
    assert view.used_capital_usdt == "0.00"
    assert view.total_pnl_usdt == "+0.00"
    assert view.current_drawdown_percent == "0.00%"
    assert view.open_position_count == 0
    assert view.closed_trade_count == 0
    assert view.expectancy_label == "Henüz ölçülmedi"
    assert view.performance_status_label == "Henüz ölçülmedi"
    assert tuple(item.vault_label for item in view.vaults) == (
        "Core",
        "Taktik",
        "Fırsat Rezervi",
    )
    assert epoch2_path.read_bytes() == before


def test_portfolio_summary_projects_measured_epoch2_exactly(
    tmp_path: Path,
) -> None:
    epoch2_path = _seed_measured_epoch2(tmp_path)
    before = epoch2_path.read_bytes()

    view = FinalProductReadModel(
        stream_ledger_path=tmp_path / "missing-stream.sqlite3",
        epoch2_path=epoch2_path,
    ).portfolio_summary(include_audit=True)

    assert view.snapshot_at_ms == 2_000
    assert view.current_equity_usdt == "1005.00"
    assert view.cash_usdt == "850.00"
    assert view.used_capital_usdt == "155.00"
    assert view.realized_pnl_usdt == "+2.00"
    assert view.unrealized_pnl_usdt == "+3.00"
    assert view.total_pnl_usdt == "+5.00"
    assert view.current_drawdown_percent == "0.00%"
    assert view.fee_usdt == "1.40"
    assert view.spread_usdt == "0.80"
    assert view.slippage_usdt == "0.80"
    assert view.turnover_percent == "30.00%"
    assert view.open_position_count == 2
    assert view.closed_trade_count == 2
    assert view.win_count == 1
    assert view.loss_count == 1
    assert view.breakeven_count == 0
    assert view.expectancy_label == "+1.00 / kapalı işlem"
    assert view.performance_status_label == "Ölçülebilir"

    core = view.vaults[0]
    assert core.vault_label == "Core"
    assert core.nav_usdt == "610.00"
    assert core.total_pnl_usdt == "+10.00"
    assert core.open_position_count == 1
    assert core.positions == (
        type(core.positions[0])(symbol="BTCUSDT", quantity="1.25"),
    )
    assert core.audit is not None
    assert len(core.audit.snapshot_identity) == 64

    tactical = view.vaults[1]
    assert tactical.vault_label == "Taktik"
    assert tactical.total_pnl_usdt == "-5.00"
    assert tactical.positions[0].symbol == "ETHUSDT"
    assert tactical.positions[0].quantity == "0.5"

    assert view.audit is not None
    assert len(view.audit.activation_identity) == 64
    assert len(view.audit.consolidated_snapshot_identity) == 64
    assert len(view.audit.vault_snapshot_identities) == 3
    assert epoch2_path.read_bytes() == before


def test_portfolio_summary_corrupt_partial_epoch2_fails_closed(
    tmp_path: Path,
) -> None:
    epoch2_path = tmp_path / "partial-epoch2.sqlite3"
    with sqlite3.connect(epoch2_path) as connection:
        connection.execute(
            "CREATE TABLE r21_epoch2_activation (singleton INTEGER PRIMARY KEY, payload_json TEXT)"
        )

    with pytest.raises(
        FinalProductReadError,
        match="Epoch 2 portföy kaynağı güvenli okunamadı",
    ):
        FinalProductReadModel(
            stream_ledger_path=tmp_path / "missing-stream.sqlite3",
            epoch2_path=epoch2_path,
        ).portfolio_summary()


def test_portfolio_summary_customer_payload_hides_identities_and_raw_metric_enum(
    tmp_path: Path,
) -> None:
    epoch2_path = _seed_measured_epoch2(tmp_path)
    payload = asdict(
        FinalProductReadModel(
            stream_ledger_path=tmp_path / "missing-stream.sqlite3",
            epoch2_path=epoch2_path,
        ).portfolio_summary(include_audit=False)
    )
    texts = _all_text(payload)

    assert not any(re.fullmatch(r"[0-9a-f]{64}", value) for value in texts)
    forbidden = {
        "available",
        "not_yet_measured",
        "r21_vault_snapshots",
        "r21_consolidated_snapshots",
        "paper_fund_epoch2.sqlite3",
        "CORE",
        "TACTICAL",
        "OPPORTUNITY_RESERVE",
    }
    assert forbidden.isdisjoint(texts)


def _capital_fixture_record(
    *,
    label: str,
    schema_version: str,
    subtype: str,
    event_at_ms: int,
    vault_id: str | None,
    headline: str,
    detail: str,
    action: str | None = None,
    disposition: str | None = None,
    source_as_of_ms: int | None = None,
    reason_codes: tuple[str, ...] | None = None,
    extra: dict[str, object] | None = None,
) -> tuple[str, str, str]:
    base: dict[str, object] = {
        "source_event_identity": _sha(f"{label}-source"),
        "stream_event_identity": _sha(f"{label}-stream"),
        "story_identity": _sha(f"{label}-story"),
        "capital_reference_identities": (
            _sha(f"{label}-lineage-a"),
            _sha(f"{label}-lineage-b"),
        ),
        "category": "capital",
        "subtype": subtype,
        "asset": "BTC",
        "symbol": "BTCUSDT",
        "timeframe": "4h",
        "event_at_ms": event_at_ms,
        "text": {
            "collapsed_text": headline,
            "simple_text": detail,
            "technical_text": detail,
            "intelligence_text": detail,
            "decision_text": detail,
            "capital_text": detail,
        },
        "schema_version": schema_version,
        "engine_version": STREAM_ENGINE_VERSION,
        "read_only": True,
        "production_authority": False,
        "real_capital": 0,
    }
    if vault_id is not None:
        base["vault_id"] = vault_id
    if action is not None:
        base["action"] = action
    if disposition is not None:
        base["disposition"] = disposition
    if source_as_of_ms is not None:
        base["source_as_of_ms"] = source_as_of_ms
    if reason_codes is not None:
        base["reason_codes"] = reason_codes
    if extra is not None:
        base.update(extra)

    narrative_identity = canonical_sha256(base)
    payload = {"narrative_identity": narrative_identity, **base}
    payload_json = canonical_json(payload)
    return narrative_identity, payload_json, sha256_text(payload_json)


def _insert_capital_fixture_row(
    connection: sqlite3.Connection,
    *,
    table: str,
    record: tuple[str, str, str],
) -> None:
    narrative_identity, payload_json, payload_sha256 = record
    payload = __import__("json").loads(payload_json)
    statements = {
        "stream_capital_messages": """
            INSERT INTO stream_capital_messages (
                narrative_identity, story_identity, symbol, timeframe,
                event_at_ms, payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        "stream_capital_decision_messages": """
            INSERT INTO stream_capital_decision_messages (
                narrative_identity, story_identity, symbol, timeframe,
                event_at_ms, payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        "stream_capital_sizing_messages": """
            INSERT INTO stream_capital_sizing_messages (
                narrative_identity, story_identity, symbol, timeframe,
                event_at_ms, payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        "stream_capital_lifecycle_messages": """
            INSERT INTO stream_capital_lifecycle_messages (
                narrative_identity, story_identity, symbol, timeframe,
                event_at_ms, payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
    }
    statement = statements.get(table)
    if statement is None:
        raise ValueError("unsupported capital fixture table")
    connection.execute(
        statement,
        (
            narrative_identity,
            payload["story_identity"],
            payload["symbol"],
            payload["timeframe"],
            payload["event_at_ms"],
            payload_json,
            payload_sha256,
        ),
    )


def _seed_capital_movements_stream(tmp_path: Path) -> Path:
    path = tmp_path / "capital-stream.sqlite3"
    _create_read_fixture(path)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE stream_capital_messages (
                narrative_identity TEXT PRIMARY KEY,
                story_identity TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                event_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );
            CREATE TABLE stream_capital_decision_messages (
                narrative_identity TEXT PRIMARY KEY,
                story_identity TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                event_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );
            CREATE TABLE stream_capital_sizing_messages (
                narrative_identity TEXT PRIMARY KEY,
                story_identity TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                event_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );
            CREATE TABLE stream_capital_lifecycle_messages (
                narrative_identity TEXT PRIMARY KEY,
                story_identity TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                event_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );
            """
        )

        _insert_capital_fixture_row(
            connection,
            table="stream_capital_decision_messages",
            record=_capital_fixture_record(
                label="eligible",
                schema_version=STREAM_CAPITAL_DECISION_MESSAGE_SCHEMA_VERSION,
                subtype="capital_eligible",
                event_at_ms=1_100,
                source_as_of_ms=1_050,
                vault_id="CORE",
                disposition="eligible",
                reason_codes=("all_clear",),
                headline="Core sermaye kararı hazır.",
                detail="Core için sanal sermaye değerlendirmesi işleme uygun bulundu.",
                extra={
                    "decision_identity": _sha("eligible-decision"),
                    "allocator_assessment_identity": _sha("eligible-assessment"),
                    "allocator_candidate_identity": _sha("eligible-candidate"),
                    "starting_budget_usdt": "600.00",
                    "event_risk_state": "clear",
                },
            ),
        )
        _insert_capital_fixture_row(
            connection,
            table="stream_capital_sizing_messages",
            record=_capital_fixture_record(
                label="sized",
                schema_version=STREAM_CAPITAL_SIZING_MESSAGE_SCHEMA_VERSION,
                subtype="capital_sized",
                event_at_ms=1_200,
                source_as_of_ms=1_150,
                vault_id="CORE",
                reason_codes=("fixed_fractional",),
                headline="Core pozisyon boyutu hesaplandı.",
                detail="Sanal pozisyon boyutu kanonik risk kurallarıyla belirlendi.",
                extra={
                    "sizing_event_identity": _sha("sized-event"),
                    "selection_identity": _sha("sized-selection"),
                    "eligibility_proof_identity": _sha("sized-eligibility"),
                    "allocator_candidate_identity": _sha("sized-candidate"),
                    "fraction_of_vault": "0.10",
                    "canonical_notional_usdt": "60.00",
                    "current_cash_usdt": "600.00",
                    "current_nav_usdt": "600.00",
                },
            ),
        )
        _insert_capital_fixture_row(
            connection,
            table="stream_capital_messages",
            record=_capital_fixture_record(
                label="buy",
                schema_version=STREAM_CAPITAL_MESSAGE_SCHEMA_VERSION,
                subtype="capital_executed",
                event_at_ms=1_300,
                vault_id="CORE",
                action="BUY",
                headline="Core sanal pozisyonu açıldı.",
                detail="Sanal alım kanonik fill ve maliyet kanıtıyla kaydedildi.",
                extra={
                    "forecast_identity": _sha("buy-forecast"),
                    "proof_identity": _sha("buy-proof"),
                    "bundle_identity": _sha("buy-bundle"),
                    "intent_identity": _sha("buy-intent"),
                    "fill_identity": _sha("buy-fill"),
                    "before_vault_snapshot_identity": _sha("buy-before-vault"),
                    "after_vault_snapshot_identity": _sha("buy-after-vault"),
                    "before_consolidated_snapshot_identity": _sha("buy-before-parent"),
                    "after_consolidated_snapshot_identity": _sha("buy-after-parent"),
                    "quantity": "0.001",
                    "reference_price": "60000.00",
                    "simulated_fill_price": "60010.00",
                    "notional_usdt": "60.01",
                    "cash_before_usdt": "600.00",
                    "cash_after_usdt": "539.93",
                    "vault_nav_before_usdt": "600.00",
                    "vault_nav_after_usdt": "599.99",
                    "consolidated_nav_before_usdt": "1000.00",
                    "consolidated_nav_after_usdt": "999.99",
                    "fee_usdt": "0.06",
                    "spread_usdt": "0.01",
                    "slippage_usdt": "0.01",
                    "outcome_identity": None,
                    "financial_outcome": None,
                    "realized_pnl_delta_usdt": None,
                    "position_quantity_before": None,
                    "position_quantity_after": None,
                },
            ),
        )
        _insert_capital_fixture_row(
            connection,
            table="stream_capital_lifecycle_messages",
            record=_capital_fixture_record(
                label="accounting",
                schema_version=STREAM_CAPITAL_LIFECYCLE_MESSAGE_SCHEMA_VERSION,
                subtype="capital_accounting_updated",
                event_at_ms=1_400,
                source_as_of_ms=1_300,
                vault_id="CORE",
                action="BUY",
                headline="Core portföy hesabı güncellendi.",
                detail="Sanal işlem sonrası nakit ve NAV kanonik muhasebeye işlendi.",
                extra={
                    "lifecycle_identity": _sha("accounting-lifecycle"),
                    "allocator_assessment_identity": None,
                    "allocator_candidate_identity": None,
                    "forecast_identity": _sha("accounting-forecast"),
                    "proof_identity": _sha("accounting-proof"),
                    "decision_context_identity": _sha("accounting-context"),
                    "bundle_identity": _sha("accounting-bundle"),
                    "outcome_identity": None,
                    "financial_outcome": None,
                    "realized_pnl_delta_usdt": None,
                    "position_quantity_before": None,
                    "position_quantity_after": None,
                    "cash_before_usdt": "600.00",
                    "cash_after_usdt": "539.93",
                    "vault_nav_before_usdt": "600.00",
                    "vault_nav_after_usdt": "599.99",
                    "consolidated_nav_before_usdt": "1000.00",
                    "consolidated_nav_after_usdt": "999.99",
                },
            ),
        )
        _insert_capital_fixture_row(
            connection,
            table="stream_capital_decision_messages",
            record=_capital_fixture_record(
                label="blocked",
                schema_version=STREAM_CAPITAL_DECISION_MESSAGE_SCHEMA_VERSION,
                subtype="capital_blocked",
                event_at_ms=1_500,
                source_as_of_ms=1_490,
                vault_id="TACTICAL",
                disposition="blocked",
                reason_codes=("event_risk",),
                headline="Taktik vault işlemi engelledi.",
                detail="Event riski nedeniyle sanal sermaye nakitte korunuyor.",
                extra={
                    "decision_identity": _sha("blocked-decision"),
                    "allocator_assessment_identity": _sha("blocked-assessment"),
                    "allocator_candidate_identity": _sha("blocked-candidate"),
                    "starting_budget_usdt": "300.00",
                    "event_risk_state": "blocked",
                },
            ),
        )
        _insert_capital_fixture_row(
            connection,
            table="stream_capital_lifecycle_messages",
            record=_capital_fixture_record(
                label="outcome",
                schema_version=STREAM_CAPITAL_LIFECYCLE_MESSAGE_SCHEMA_VERSION,
                subtype="capital_outcome",
                event_at_ms=1_600,
                source_as_of_ms=1_550,
                vault_id="CORE",
                action="REDUCE",
                headline="Core sanal pozisyon sonucu kaydedildi.",
                detail="Kısmi azaltmanın gerçekleşen sanal PnL sonucu immutable kayda geçti.",
                extra={
                    "lifecycle_identity": _sha("outcome-lifecycle"),
                    "allocator_assessment_identity": None,
                    "allocator_candidate_identity": None,
                    "forecast_identity": _sha("outcome-forecast"),
                    "proof_identity": _sha("outcome-proof"),
                    "decision_context_identity": _sha("outcome-context"),
                    "bundle_identity": _sha("outcome-bundle"),
                    "outcome_identity": _sha("outcome-identity"),
                    "financial_outcome": "PARTIAL_REDUCTION",
                    "realized_pnl_delta_usdt": "2.50",
                    "position_quantity_before": "0.001",
                    "position_quantity_after": "0.0005",
                    "cash_before_usdt": None,
                    "cash_after_usdt": None,
                    "vault_nav_before_usdt": None,
                    "vault_nav_after_usdt": None,
                    "consolidated_nav_before_usdt": None,
                    "consolidated_nav_after_usdt": None,
                },
            ),
        )
        _insert_capital_fixture_row(
            connection,
            table="stream_capital_lifecycle_messages",
            record=_capital_fixture_record(
                label="candidate",
                schema_version=STREAM_CAPITAL_LIFECYCLE_MESSAGE_SCHEMA_VERSION,
                subtype="capital_candidate",
                event_at_ms=1_700,
                source_as_of_ms=1_650,
                vault_id=None,
                headline="Yeni sanal sermaye adayı değerlendiriliyor.",
                detail="Aday üç vault karar zincirine alındı; henüz sermaye hareketi yok.",
                extra={
                    "lifecycle_identity": _sha("candidate-lifecycle"),
                    "allocator_assessment_identity": _sha("candidate-assessment"),
                    "allocator_candidate_identity": _sha("candidate-candidate"),
                    "forecast_identity": None,
                    "proof_identity": None,
                    "decision_context_identity": None,
                    "bundle_identity": None,
                    "outcome_identity": None,
                    "action": None,
                    "financial_outcome": None,
                    "realized_pnl_delta_usdt": None,
                    "position_quantity_before": None,
                    "position_quantity_after": None,
                    "cash_before_usdt": None,
                    "cash_after_usdt": None,
                    "vault_nav_before_usdt": None,
                    "vault_nav_after_usdt": None,
                    "consolidated_nav_before_usdt": None,
                    "consolidated_nav_after_usdt": None,
                },
            ),
        )
    return path


def test_capital_movements_missing_stream_is_explicit_and_noncreating(
    tmp_path: Path,
) -> None:
    stream_path = tmp_path / "missing-capital-stream.sqlite3"
    view = FinalProductReadModel(
        stream_ledger_path=stream_path,
    ).capital_movements(
        observed_at_ms=2_000,
        from_ms=1_000,
        to_ms=1_900,
    )

    assert view.availability_label == "Sermaye hareketleri verisi kullanılamıyor"
    assert view.items == ()
    assert view.real_capital == 0
    assert not stream_path.exists()


def test_capital_movements_projects_verified_stream_capital_truth(
    tmp_path: Path,
) -> None:
    stream_path = _seed_capital_movements_stream(tmp_path)
    view = FinalProductReadModel(
        stream_ledger_path=stream_path,
    ).capital_movements(
        observed_at_ms=2_000,
        from_ms=1_000,
        to_ms=1_900,
        stale_after_ms=10_000,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert [item.event_at_ms for item in view.items] == [
        1_700,
        1_600,
        1_500,
        1_400,
        1_300,
        1_200,
        1_100,
    ]
    assert [item.action_label for item in view.items] == [
        "Aday sermaye değerlendirmesi",
        "İşlem sonucu kaydedildi",
        "İşlem engellendi",
        "Portföy hesabı güncellendi",
        "Pozisyon açıldı / artırıldı",
        "Pozisyon boyutu belirlendi",
        "İşleme uygun bulundu",
    ]

    candidate = view.items[0]
    assert candidate.vault_label is None
    assert candidate.notional_usdt is None
    assert candidate.quantity is None

    outcome = view.items[1]
    assert outcome.vault_label == "Core"
    assert outcome.outcome_label == "Kısmi azaltma"
    assert outcome.realized_pnl_delta_usdt == "+2.50"

    execution = view.items[4]
    assert execution.quantity == "0.001"
    assert execution.notional_usdt == "60.01"
    assert execution.fee_usdt == "0.06"
    assert execution.source_as_of_ms is None
    assert execution.freshness_label == "Olay zamanı güncel"

    sizing = view.items[5]
    assert sizing.fraction_of_vault_percent == "10.00%"
    assert sizing.notional_usdt == "60.00"
    assert sizing.current_cash_usdt == "600.00"
    assert sizing.current_nav_usdt == "600.00"
    assert sizing.freshness_label == "Güncel"


def test_capital_movements_reuses_vault_time_filter_order_and_preserves_source(
    tmp_path: Path,
) -> None:
    stream_path = _seed_capital_movements_stream(tmp_path)
    before = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }

    view = FinalProductReadModel(
        stream_ledger_path=stream_path,
    ).capital_movements(
        observed_at_ms=2_000,
        from_ms=1_200,
        to_ms=1_400,
        vault="core",
        stale_after_ms=10_000,
    )

    assert view.vault_label == "Core"
    assert [item.event_at_ms for item in view.items] == [1_400, 1_300, 1_200]
    assert all(item.vault_label == "Core" for item in view.items)
    after = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }
    assert after == before


def test_capital_movements_distinguishes_valid_empty_interval(
    tmp_path: Path,
) -> None:
    stream_path = _seed_capital_movements_stream(tmp_path)
    view = FinalProductReadModel(
        stream_ledger_path=stream_path,
    ).capital_movements(
        observed_at_ms=2_500,
        from_ms=2_000,
        to_ms=2_400,
    )

    assert view.availability_label == "Bu aralıkta sermaye hareketi yok"
    assert view.items == ()


def test_capital_movements_customer_payload_hides_raw_identity_vocabulary(
    tmp_path: Path,
) -> None:
    stream_path = _seed_capital_movements_stream(tmp_path)
    model = FinalProductReadModel(stream_ledger_path=stream_path)

    customer = asdict(
        model.capital_movements(
            observed_at_ms=2_000,
            from_ms=1_000,
            to_ms=1_900,
            stale_after_ms=10_000,
            include_audit=False,
        )
    )
    texts = _all_text(customer)
    assert not any(re.fullmatch(r"[0-9a-f]{64}", value) for value in texts)
    forbidden = {
        "capital_candidate",
        "capital_outcome",
        "capital_blocked",
        "capital_accounting_updated",
        "capital_executed",
        "capital_sized",
        "capital_eligible",
        "all_clear",
        "fixed_fractional",
        "event_risk",
        "eligible",
        "blocked",
    }
    assert forbidden.isdisjoint(texts)

    audited = model.capital_movements(
        observed_at_ms=2_000,
        from_ms=1_000,
        to_ms=1_900,
        stale_after_ms=10_000,
        include_audit=True,
    )
    eligible = audited.items[-1]
    assert eligible.audit is not None
    assert eligible.audit.raw_subtype == "capital_eligible"
    assert eligible.audit.raw_disposition == "eligible"
    assert eligible.audit.reason_codes == ("all_clear",)
    assert len(eligible.audit.narrative_identity) == 64
    assert all(len(value) == 64 for value in eligible.audit.lineage_identities)
