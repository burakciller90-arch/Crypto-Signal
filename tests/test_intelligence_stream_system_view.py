from __future__ import annotations

import sqlite3
from dataclasses import replace

from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_family import (
    IntelligenceStreamFamilyRuntime,
    StreamTrustDomain,
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
    StreamMessageQuery,
)
from crypto_signal.product.intelligence_stream_system_view import (
    IntelligenceStreamSystemViewRuntime,
    StreamSystemViewDisposition,
)


def _sha(label: str) -> str:
    return canonical_sha256({"label": label})


def _geometry(*, direction: str = "bullish", suffix: str = "1"):
    return build_family_snapshot(
        projector_id="market_geometry_change",
        family=ConfluenceFamily.GEOMETRY,
        category=StreamCategory.MARKET,
        subtype="geometry_material_change",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=_sha(f"geometry-source-{suffix}"),
        source_scope="bybit:spot:signal_geometry",
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe="15m",
        event_at_ms=2_000,
        source_as_of_ms=1_990,
        evidence_identities=(_sha(f"geometry-evidence-{suffix}"),),
        evidence_domains=("frozen_chart", "geometry"),
        state_label=f"active:{direction}:geometry",
        state_components=(
            ("direction", direction),
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
        direction=direction,
        source_quality="exact_immutable_signal_freeze",
    )


def _market_family(
    family: ConfluenceFamily,
    *,
    direction: str | None,
    state_label: str,
    suffix: str,
    timeframe: str,
    source_quality: str = "measured",
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
        source_event_identity=_sha(f"{family.value}-source-{suffix}"),
        source_scope=f"bybit:spot:{family.value}",
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe=timeframe,
        event_at_ms=2_100,
        source_as_of_ms=2_100,
        evidence_identities=(_sha(f"{family.value}-evidence-{suffix}"),),
        evidence_domains=(domain,),
        state_label=state_label,
        state_components=(("label", state_label),),
        direction=direction,
        source_quality=source_quality,
    )


def _trust(
    family: StreamTrustDomain,
    *,
    state_label: str,
    suffix: str,
):
    category = (
        StreamCategory.RISK
        if family is StreamTrustDomain.EVENT_RISK
        else StreamCategory.SYSTEM
    )
    subtype = (
        "event_risk_block"
        if state_label == "event_block"
        else "event_risk_change"
        if family is StreamTrustDomain.EVENT_RISK
        else "provider_quality_change"
    )
    symbol = "CRYPTO" if family is StreamTrustDomain.EVENT_RISK else "BTCUSDT"
    return build_family_snapshot(
        projector_id=(
            "event_risk_change"
            if family is StreamTrustDomain.EVENT_RISK
            else "provider_quality_change"
        ),
        family=family,
        category=category,
        subtype=subtype,
        importance=StreamImportance.IMPORTANT,
        source_event_identity=_sha(f"{family.value}-source-{suffix}"),
        source_scope=f"fixture:{family.value}",
        asset="CRYPTO" if symbol == "CRYPTO" else "BTC",
        symbol=symbol,
        market="GLOBAL" if symbol == "CRYPTO" else symbol,
        timeframe="event_window" if symbol == "CRYPTO" else "15m",
        event_at_ms=2_100,
        source_as_of_ms=2_100,
        evidence_identities=(_sha(f"{family.value}-evidence-{suffix}"),),
        evidence_domains=(family.value,),
        state_label=state_label,
        state_components=(("state", state_label),),
        direction=None,
        source_quality="good",
    )


def _base_snapshots(*, order_flow_direction: str = "buy_pressure", suffix: str = "1"):
    return (
        _geometry(suffix=suffix),
        _market_family(
            ConfluenceFamily.LIQUIDITY,
            direction=None,
            state_label="measured:none",
            suffix=suffix,
            timeframe="microstructure",
        ),
        _market_family(
            ConfluenceFamily.ORDER_FLOW,
            direction=order_flow_direction,
            state_label=order_flow_direction,
            suffix=suffix,
            timeframe="microstructure",
        ),
        _market_family(
            ConfluenceFamily.DERIVATIVES,
            direction=None,
            state_label="balanced",
            suffix=suffix,
            timeframe="15m",
        ),
    )


def test_system_view_composes_weighted_customer_surface_without_probability(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    runtime = IntelligenceStreamSystemViewRuntime(path)
    result = runtime.compose_and_append(
        symbol="BTCUSDT",
        event_at_ms=3_000,
        family_snapshots=_base_snapshots(),
        trust_snapshots=(
            _trust(StreamTrustDomain.PROVIDER_QUALITY, state_label="healthy", suffix="1"),
            _trust(StreamTrustDomain.EVENT_RISK, state_label="clear", suffix="1"),
        ),
    )

    assert result.disposition is StreamSystemViewDisposition.INSERTED
    assert result.stance == "bullish"
    reader = IntelligenceStreamReadModel(path)
    page = reader.read_messages(StreamMessageQuery(limit=20, primary_surface=True))
    assert [item["narrative_identity"] for item in page.items] == [
        result.narrative_identity
    ]
    record = page.items[0]
    assert record["subtype"] == "system_view_updated"
    assert "Bitcoin için kanıt dengesi yükseliş yönüne eğiliyor." in (
        record["text"]["collapsed_text"]
    )
    assert "$100–$102" in record["text"]["collapsed_text"]
    assert "$108" in record["text"]["collapsed_text"]
    assert "$95" in record["text"]["collapsed_text"]
    assert "olasılık" not in record["text"]["collapsed_text"].casefold()

    detail = reader.read_message_detail(result.narrative_identity or "")
    assert detail is not None
    fact = detail["fact_bundle"]
    analytical = detail["analytical_view"]
    assert analytical["stance"]["effective_stance"] == "bullish"
    assert fact["confluence_support_score_0_100"] == "45.00"
    assert fact["confluence_opposition_score_0_100"] == "0.00"
    assert fact["evidence_coverage_0_100"] == "85.00"
    assert fact["probability_status"] == "not_calibrated"
    rows = {item["family"]: item for item in fact["family_contributions"]}
    assert rows["geometry_pa_elliott_harmonic"]["support_points"] == "20.00"
    assert rows["order_flow_absorption"]["support_points"] == "25.00"
    assert rows["onchain_smart_money"]["state"] == "no_evidence"
    assert rows["onchain_smart_money"]["prior_weight"] == "0.15"
    assert fact["trigger_zone"] == {"low": "100.00", "high": "102.00"}
    assert fact["target_zone"] == {"low": "108.00", "high": "108.00"}
    assert fact["invalidation_price"] == "95.00"


def test_system_view_is_semantically_idempotent_and_flips_only_on_family_state(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    runtime = IntelligenceStreamSystemViewRuntime(path)
    first = runtime.compose_and_append(
        symbol="BTCUSDT",
        event_at_ms=3_000,
        family_snapshots=_base_snapshots(suffix="1"),
    )
    replay = runtime.compose_and_append(
        symbol="BTCUSDT",
        event_at_ms=4_000,
        family_snapshots=_base_snapshots(suffix="2"),
    )
    assert replay.disposition is StreamSystemViewDisposition.UNCHANGED
    assert replay.narrative_identity == first.narrative_identity

    bearish = runtime.compose_and_append(
        symbol="BTCUSDT",
        event_at_ms=5_000,
        family_snapshots=_base_snapshots(
            order_flow_direction="sell_pressure",
            suffix="3",
        ),
    )
    assert bearish.disposition is StreamSystemViewDisposition.INSERTED
    assert bearish.stance == "bearish"

    detail = IntelligenceStreamReadModel(path).read_message_detail(
        bearish.narrative_identity or ""
    )
    assert detail is not None
    fact = detail["fact_bundle"]
    assert fact["confluence_support_score_0_100"] == "25.00"
    assert fact["confluence_opposition_score_0_100"] == "20.00"
    assert fact["trigger_zone"] is None
    assert fact["target_zone"] is None
    assert fact["invalidation_price"] is None
    assert "exact tetik/hedef koşulu olmadığı için" in (
        detail["narrative"]["text"]["collapsed_text"]
    )


def test_system_view_event_risk_blocks_direction_without_changing_family_score(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    runtime = IntelligenceStreamSystemViewRuntime(path)
    blocked = runtime.compose_and_append(
        symbol="BTCUSDT",
        event_at_ms=6_000,
        family_snapshots=_base_snapshots(),
        trust_snapshots=(
            _trust(
                StreamTrustDomain.EVENT_RISK,
                state_label="event_block",
                suffix="block",
            ),
        ),
    )
    assert blocked.stance == "blocked"
    detail = IntelligenceStreamReadModel(path).read_message_detail(
        blocked.narrative_identity or ""
    )
    assert detail is not None
    assert detail["analytical_view"]["stance"]["effective_stance"] == "blocked"
    assert detail["fact_bundle"]["confluence_support_score_0_100"] == "0.00"
    assert detail["fact_bundle"]["evidence_coverage_0_100"] == "85.00"
    assert "blokluyorum" in detail["narrative"]["text"]["collapsed_text"]
    assert detail["narrative"]["production_authority"] is False
    assert detail["narrative"]["real_capital"] == 0


def test_system_view_family_proof_identity_matches_exact_selected_snapshot(
    tmp_path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    IntelligenceStreamForwardRuntime(path).ensure_activated(activated_at_ms=1_000)
    family_runtime = IntelligenceStreamFamilyRuntime(path)

    selected = _market_family(
        ConfluenceFamily.LIQUIDITY,
        direction=None,
        state_label="measured:none",
        suffix="selected-bybit",
        timeframe="microstructure",
    )
    selected = replace(
        selected,
        source_scope="bybit:spot:liquidity",
        event_at_ms=2_100,
        source_as_of_ms=2_100,
    )
    newer_but_lower_priority = _market_family(
        ConfluenceFamily.LIQUIDITY,
        direction=None,
        state_label="measured:bid_side_liquidity_take_candidate",
        suffix="newer-fixture",
        timeframe="microstructure",
    )
    newer_but_lower_priority = replace(
        newer_but_lower_priority,
        source_scope="fixture:liquidity",
        event_at_ms=2_200,
        source_as_of_ms=2_200,
    )

    selected_result = family_runtime.project(
        selected,
        activated_at_ms=1_000,
    )
    newer_result = family_runtime.project(
        newer_but_lower_priority,
        activated_at_ms=1_000,
    )
    assert selected_result.narrative_identity is not None
    assert newer_result.narrative_identity is not None
    assert selected_result.narrative_identity != newer_result.narrative_identity

    system_runtime = IntelligenceStreamSystemViewRuntime(path)
    system_result = system_runtime.compose_and_append(
        symbol="BTCUSDT",
        event_at_ms=3_000,
        family_snapshots=(selected, newer_but_lower_priority),
    )
    assert system_result.narrative_identity is not None

    detail = IntelligenceStreamReadModel(path).read_message_detail(
        system_result.narrative_identity
    )
    assert detail is not None
    rows = {
        item["family"]: item
        for item in detail["fact_bundle"]["family_contributions"]
    }
    liquidity = rows["liquidity"]
    assert liquidity["source_narrative_identity"] == (
        selected_result.narrative_identity
    )
    assert liquidity["source_narrative_identity"] != newer_result.narrative_identity
    assert tuple(liquidity["source_evidence_identities"]) == (
        selected.evidence_identities
    )


def test_system_view_ledger_is_append_only(tmp_path) -> None:
    path = tmp_path / "stream.sqlite3"
    runtime = IntelligenceStreamSystemViewRuntime(path)
    result = runtime.compose_and_append(
        symbol="BTCUSDT",
        event_at_ms=3_000,
        family_snapshots=_base_snapshots(),
    )
    assert result.narrative_identity is not None
    with sqlite3.connect(path) as connection:
        try:
            connection.execute(
                "UPDATE stream_system_view_messages SET symbol='ETHUSDT'"
            )
        except sqlite3.DatabaseError as exc:
            assert "immutable intelligence stream system view" in str(exc)
        else:
            raise AssertionError("system-view ledger allowed mutation")
