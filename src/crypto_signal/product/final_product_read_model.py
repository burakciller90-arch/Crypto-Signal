from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamMessageQuery,
    StreamReadModelError,
)
from crypto_signal.product.intelligence_stream_system_view import (
    verified_system_view_record,
)

FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION = "final-product-read-model-v1/1"
DEFAULT_MARKET_PULSE_STALE_AFTER_MS = 15 * 60 * 1000
DEFAULT_ATTENTION_LIMIT = 5
MAX_ATTENTION_LIMIT = 20
_ATTENTION_SCAN_LIMIT = 200
REAL_CAPITAL = 0

_FAMILY_ORDER = {
    "geometry": 0,
    "geometry_pa_elliott_harmonic": 0,
    "liquidity": 1,
    "liquidity_structure": 1,
    "order_flow": 2,
    "order_flow_absorption": 2,
    "derivatives": 3,
    "derivatives_leverage": 3,
    "onchain": 4,
    "onchain_smart_money": 4,
}
_FAMILY_LABELS = {
    "geometry": "Geometri",
    "geometry_pa_elliott_harmonic": "Geometri",
    "liquidity": "Likidite",
    "liquidity_structure": "Likidite",
    "order_flow": "Emir Akışı",
    "order_flow_absorption": "Emir Akışı",
    "derivatives": "Türevler",
    "derivatives_leverage": "Türevler",
    "onchain": "On-chain",
    "onchain_smart_money": "On-chain",
}
_CATEGORY_LABELS = {
    "market": "Piyasa",
    "intelligence": "İstihbarat",
    "decision": "Karar",
    "capital": "Sermaye",
    "risk": "Risk",
    "outcome": "Sonuç",
    "system": "Sistem",
    "routine": "Rutin",
}
_IMPORTANCE_LABELS = {
    "critical": "Kritik",
    "important": "Önemli",
}
_EVIDENCE_DOMAIN_LABELS = {
    "geometry": "Geometri",
    "frozen_chart": "Dondurulmuş grafik",
    "order_book": "Emir defteri",
    "public_trades": "Gerçekleşen işlemler",
    "liquidity": "Likidite",
    "liquidity_structure": "Likidite yapısı",
    "liquidity_sweep": "Likidite süpürmesi",
    "order_flow": "Emir akışı",
    "order_flow_cvd": "Emir akışı / CVD",
    "derivatives": "Türevler",
    "liquidation_map": "Likidasyon haritası",
    "onchain": "On-chain",
    "stablecoin": "Stablecoin akışı",
    "event_context": "Event bağlamı",
    "methodology": "Metodoloji",
}
_STANCE_LABELS = {
    "bullish": "Yükseliş yönlü destek",
    "bearish": "Düşüş yönlü destek",
    "watch": "Karışık / izle",
    "blocked": "Event riski nedeniyle bloklu",
}
_DIRECTION_LABELS = {
    "bullish": "Yükseliş",
    "bearish": "Düşüş",
}
_EVENT_RISK_LABELS = {
    "event_block": "İşlem riski yüksek",
    "caution": "Dikkat",
    "abstain": "Event verisi yetersiz",
    "degraded_data": "Event verisi güncel değil",
    "healthy": "Normal",
}
_PROVIDER_QUALITY_LABELS = {
    "healthy": "Kaynaklar sağlıklı",
    "degraded_provider_stale": "Bir sağlayıcı güncel değil",
    "degraded": "Kaynak kalitesi düştü",
    "unavailable": "Kaynak verisi eksik",
    "unresolved": "Kaynak durumu kararsız",
}


class FinalProductReadError(ValueError):
    """Raised when accepted source truth cannot be projected safely."""


@dataclass(frozen=True, slots=True)
class MarketPulseFamilyAudit:
    source_narrative_identity: str | None
    source_evidence_identities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketPulseFamilyView:
    family: str
    family_label: str
    weight_points: str
    state_label: str
    direction_label: str | None
    relationship_label: str
    source_quality_label: str
    timeframe: str | None
    audit: MarketPulseFamilyAudit | None = None


@dataclass(frozen=True, slots=True)
class MarketPulseAudit:
    narrative_identity: str
    semantic_identity: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class MarketPulseAssetView:
    symbol: str
    timeframe: str
    updated_at_ms: int
    freshness_label: str
    stance_label: str
    support_score_0_100: str
    opposition_score_0_100: str
    evidence_coverage_0_100: str
    probability_label: str
    event_risk_label: str
    provider_quality_label: str
    trigger_zone: dict[str, Any] | None
    target_zone: dict[str, Any] | None
    invalidation_price: str | None
    main_contradiction_label: str | None
    summary: str
    families: tuple[MarketPulseFamilyView, ...]
    audit: MarketPulseAudit | None = None


@dataclass(frozen=True, slots=True)
class MarketPulseView:
    availability_label: str
    observed_at_ms: int
    source_label: str
    items: tuple[MarketPulseAssetView, ...]
    missing_symbols: tuple[str, ...]
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class AttentionAudit:
    narrative_identity: str
    story_identity: str | None
    source_event_identity: str | None
    message_identity: str | None
    materiality_decision_identity: str | None
    materiality_policy_identity: str | None


@dataclass(frozen=True, slots=True)
class AttentionSituationView:
    symbol: str
    timeframe: str
    updated_at_ms: int
    freshness_label: str
    category_label: str
    importance_label: str
    state_label: str | None
    headline: str
    detail: str
    materiality_label: str
    risk_label: str | None
    source_label: str
    audit: AttentionAudit | None = None


@dataclass(frozen=True, slots=True)
class AttentionSituationsView:
    availability_label: str
    observed_at_ms: int
    items: tuple[AttentionSituationView, ...]
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class FamilySummaryAudit:
    source_narrative_identity: str
    fact_bundle_identity: str
    analytical_view_identity: str
    source_evidence_identities: tuple[str, ...]
    raw_state_label: str
    uncertainty_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FamilySummaryItem:
    family_label: str
    state_label: str
    direction_label: str | None
    relationship_label: str
    source_quality_label: str
    source_as_of_ms: int | None
    freshness_label: str
    evidence_domain_labels: tuple[str, ...]
    uncertainty_label: str
    changed_label: str
    timeframe: str | None
    audit: FamilySummaryAudit | None = None


@dataclass(frozen=True, slots=True)
class FiveFamilySummaryView:
    availability_label: str
    symbol: str
    timeframe: str | None
    updated_at_ms: int | None
    stance_label: str | None
    families: tuple[FamilySummaryItem, ...]
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class _AttentionCandidate:
    dedupe_key: tuple[str, ...]
    importance_rank: int
    event_at_ms: int
    narrative_identity: str
    view: AttentionSituationView


class FinalProductReadModel:
    """Customer-safe, read-only projections over already accepted Product truth."""

    def __init__(self, *, stream_ledger_path: Path) -> None:
        self.stream_ledger_path = stream_ledger_path

    def market_pulse(
        self,
        *,
        symbols: tuple[str, ...],
        observed_at_ms: int,
        stale_after_ms: int = DEFAULT_MARKET_PULSE_STALE_AFTER_MS,
        include_audit: bool = False,
    ) -> MarketPulseView:
        if observed_at_ms < 0:
            raise ValueError("market pulse observation time must be non-negative")
        if stale_after_ms <= 0:
            raise ValueError("market pulse stale_after_ms must be positive")
        normalized = _normalize_symbols(symbols)
        if not self.stream_ledger_path.is_file():
            return MarketPulseView(
                availability_label="Veri eksik",
                observed_at_ms=observed_at_ms,
                source_label="Crypto Signal Intelligence Stream",
                items=(),
                missing_symbols=normalized,
            )

        uri = f"{self.stream_ledger_path.resolve().as_uri()}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                if not _table_exists(connection, "stream_system_view_messages"):
                    return MarketPulseView(
                        availability_label="Veri eksik",
                        observed_at_ms=observed_at_ms,
                        source_label="Crypto Signal Intelligence Stream",
                        items=(),
                        missing_symbols=normalized,
                    )
                rows = {
                    symbol: _latest_system_view_row(
                        connection,
                        symbol=symbol,
                        observed_at_ms=observed_at_ms,
                    )
                    for symbol in normalized
                }
        except sqlite3.DatabaseError as exc:
            raise FinalProductReadError(
                "market pulse source database cannot be read safely"
            ) from exc

        items: list[MarketPulseAssetView] = []
        missing: list[str] = []
        for symbol in normalized:
            row = rows[symbol]
            if row is None:
                missing.append(symbol)
                continue
            try:
                payload = verified_system_view_record(
                    narrative_identity=str(row[0]),
                    event_at_ms=_row_non_negative_int(row[1], "system-view event time"),
                    payload_json=str(row[2]),
                    expected_digest=str(row[3]),
                )
                items.append(
                    _market_pulse_asset(
                        payload,
                        observed_at_ms=observed_at_ms,
                        stale_after_ms=stale_after_ms,
                        include_audit=include_audit,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise FinalProductReadError(
                    f"market pulse source for {symbol} is semantically invalid"
                ) from exc

        availability = (
            "Veri eksik"
            if not items
            else "Kısmi veri"
            if missing
            else "Doğrulanmış veri"
        )
        return MarketPulseView(
            availability_label=availability,
            observed_at_ms=observed_at_ms,
            source_label="Crypto Signal Intelligence Stream",
            items=tuple(items),
            missing_symbols=tuple(missing),
        )

    def attention_situations(
        self,
        *,
        observed_at_ms: int,
        limit: int = DEFAULT_ATTENTION_LIMIT,
        stale_after_ms: int = DEFAULT_MARKET_PULSE_STALE_AFTER_MS,
        include_audit: bool = False,
    ) -> AttentionSituationsView:
        if observed_at_ms < 0:
            raise ValueError("attention observation time must be non-negative")
        if limit < 1 or limit > MAX_ATTENTION_LIMIT:
            raise ValueError(
                f"attention limit must be inside 1..{MAX_ATTENTION_LIMIT}"
            )
        if stale_after_ms <= 0:
            raise ValueError("attention stale_after_ms must be positive")
        if not self.stream_ledger_path.is_file():
            return AttentionSituationsView(
                availability_label="Veri eksik",
                observed_at_ms=observed_at_ms,
                items=(),
            )

        reader = IntelligenceStreamReadModel(self.stream_ledger_path)
        try:
            page = reader.read_messages(
                StreamMessageQuery(
                    limit=_ATTENTION_SCAN_LIMIT,
                    to_ms=observed_at_ms,
                )
            )
            candidates: dict[tuple[str, ...], _AttentionCandidate] = {}
            for record in page.items:
                narrative_identity = _required_sha(record, "narrative_identity")
                detail = reader.read_message_detail(narrative_identity)
                if detail is None:
                    raise FinalProductReadError(
                        "attention source disappeared during verified read"
                    )
                candidate = _attention_candidate(
                    detail,
                    observed_at_ms=observed_at_ms,
                    stale_after_ms=stale_after_ms,
                    include_audit=include_audit,
                )
                if candidate is None:
                    continue
                previous = candidates.get(candidate.dedupe_key)
                if previous is None or (
                    candidate.event_at_ms,
                    candidate.narrative_identity,
                ) > (
                    previous.event_at_ms,
                    previous.narrative_identity,
                ):
                    candidates[candidate.dedupe_key] = candidate
        except (StreamReadModelError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, FinalProductReadError):
                raise
            raise FinalProductReadError(
                "attention source cannot be projected safely"
            ) from exc

        ordered = sorted(
            candidates.values(),
            key=lambda item: (
                item.importance_rank,
                item.event_at_ms,
                item.narrative_identity,
            ),
            reverse=True,
        )
        items = tuple(item.view for item in ordered[:limit])
        return AttentionSituationsView(
            availability_label=(
                "Dikkat gerektiren durum yok"
                if not items
                else "Doğrulanmış veri"
            ),
            observed_at_ms=observed_at_ms,
            items=items,
        )

    def five_family_summary(
        self,
        *,
        symbol: str,
        observed_at_ms: int,
        stale_after_ms: int = DEFAULT_MARKET_PULSE_STALE_AFTER_MS,
        include_audit: bool = False,
    ) -> FiveFamilySummaryView:
        if observed_at_ms < 0:
            raise ValueError("family summary observation time must be non-negative")
        if stale_after_ms <= 0:
            raise ValueError("family summary stale_after_ms must be positive")
        normalized = _normalize_symbols((symbol,))[0]
        if not self.stream_ledger_path.is_file():
            return FiveFamilySummaryView(
                availability_label="Veri eksik",
                symbol=normalized,
                timeframe=None,
                updated_at_ms=None,
                stance_label=None,
                families=(),
            )

        try:
            payload = _latest_verified_system_view(
                self.stream_ledger_path,
                symbol=normalized,
                observed_at_ms=observed_at_ms,
            )
            if payload is None:
                return FiveFamilySummaryView(
                    availability_label="Veri eksik",
                    symbol=normalized,
                    timeframe=None,
                    updated_at_ms=None,
                    stance_label=None,
                    families=(),
                )
            fact = _required_mapping(payload, "fact_bundle")
            analytical = _required_mapping(payload, "analytical_view")
            stance = _required_mapping(analytical, "stance")
            raw_stance = _required_text(stance, "effective_stance")
            reader = IntelligenceStreamReadModel(self.stream_ledger_path)
            rows = sorted(
                (
                    _mapping_value(value, "family contribution")
                    for value in _required_sequence(fact, "family_contributions")
                ),
                key=lambda value: (
                    _FAMILY_ORDER.get(str(value.get("family")), 99),
                    str(value.get("family")),
                ),
            )
            families = tuple(
                _enriched_family_summary(
                    row,
                    raw_stance=raw_stance,
                    reader=reader,
                    observed_at_ms=observed_at_ms,
                    stale_after_ms=stale_after_ms,
                    include_audit=include_audit,
                )
                for row in rows
            )
            return FiveFamilySummaryView(
                availability_label="Doğrulanmış veri",
                symbol=normalized,
                timeframe=_required_text(payload, "timeframe"),
                updated_at_ms=_required_int(payload, "event_at_ms"),
                stance_label=_STANCE_LABELS.get(raw_stance, "Karışık / izle"),
                families=families,
            )
        except (
            sqlite3.DatabaseError,
            StreamReadModelError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            if isinstance(exc, FinalProductReadError):
                raise
            raise FinalProductReadError(
                "five-family source cannot be projected safely"
            ) from exc


def _attention_candidate(
    detail: dict[str, Any],
    *,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> _AttentionCandidate | None:
    narrative = _required_mapping(detail, "narrative")
    narrative_identity = _required_sha(narrative, "narrative_identity")
    text = _required_mapping(narrative, "text")
    headline = _required_text(text, "collapsed_text")
    simple_text = _required_text(text, "simple_text")
    event_at_ms = _required_int(narrative, "event_at_ms")
    if event_at_ms > observed_at_ms:
        raise FinalProductReadError("attention source is from the future")

    if "system_view" in detail:
        importance = _required_text(narrative, "importance")
        if importance not in _IMPORTANCE_LABELS:
            return None
        symbol = _required_text(narrative, "symbol")
        timeframe = _required_text(narrative, "timeframe")
        subtype = _required_text(narrative, "subtype")
        analytical = _required_mapping(detail, "analytical_view")
        uncertainty = _required_mapping(analytical, "uncertainty")
        raw_stance = _required_text(narrative, "state")
        audit = (
            AttentionAudit(
                narrative_identity=narrative_identity,
                story_identity=None,
                source_event_identity=None,
                message_identity=None,
                materiality_decision_identity=None,
                materiality_policy_identity=None,
            )
            if include_audit
            else None
        )
        return _AttentionCandidate(
            dedupe_key=("system_view", symbol, timeframe, subtype),
            importance_rank=_attention_importance_rank(importance),
            event_at_ms=event_at_ms,
            narrative_identity=narrative_identity,
            view=AttentionSituationView(
                symbol=symbol,
                timeframe=timeframe,
                updated_at_ms=event_at_ms,
                freshness_label=_freshness_label(
                    observed_at_ms=observed_at_ms,
                    source_as_of_ms=event_at_ms,
                    stale_after_ms=stale_after_ms,
                ),
                category_label=_CATEGORY_LABELS["intelligence"],
                importance_label=_IMPORTANCE_LABELS[importance],
                state_label=_STANCE_LABELS.get(raw_stance, "Karışık / izle"),
                headline=headline,
                detail=simple_text,
                materiality_label="Güncel sistem görünümü",
                risk_label=_event_risk_label(
                    uncertainty.get("event_risk_state")
                ),
                source_label="System View",
                audit=audit,
            ),
        )

    message_input_raw = detail.get("message_input")
    if not isinstance(message_input_raw, dict):
        return None
    message_input = message_input_raw
    if (
        message_input.get("materiality") != "material"
        or message_input.get("publication_disposition") != "publish"
    ):
        return None

    importance = _required_text(message_input, "importance")
    if importance not in _IMPORTANCE_LABELS:
        return None
    category = _required_text(message_input, "category")
    symbol = _required_text(narrative, "symbol")
    timeframe = _required_text(narrative, "timeframe")
    story_identity = _required_sha(narrative, "story_identity")
    source_as_of_ms = _required_int(message_input, "source_as_of_ms")
    analytical = _required_mapping(detail, "analytical_view")
    fact = _required_mapping(detail, "fact_bundle")
    risk_label = (
        _event_risk_label(fact.get("event_context_state"))
        if fact.get("event_context_state") is not None
        else None
    )
    audit = None
    if include_audit:
        audit = AttentionAudit(
            narrative_identity=narrative_identity,
            story_identity=story_identity,
            source_event_identity=_required_sha(
                message_input,
                "source_event_identity",
            ),
            message_identity=_required_sha(message_input, "message_identity"),
            materiality_decision_identity=_required_sha(
                message_input,
                "materiality_decision_identity",
            ),
            materiality_policy_identity=_required_sha(
                message_input,
                "materiality_policy_identity",
            ),
        )
    return _AttentionCandidate(
        dedupe_key=("story", story_identity),
        importance_rank=_attention_importance_rank(importance),
        event_at_ms=event_at_ms,
        narrative_identity=narrative_identity,
        view=AttentionSituationView(
            symbol=symbol,
            timeframe=timeframe,
            updated_at_ms=event_at_ms,
            freshness_label=_freshness_label(
                observed_at_ms=observed_at_ms,
                source_as_of_ms=source_as_of_ms,
                stale_after_ms=stale_after_ms,
            ),
            category_label=_CATEGORY_LABELS.get(category, "İstihbarat"),
            importance_label=_IMPORTANCE_LABELS[importance],
            state_label=_attention_state_label(analytical, fact),
            headline=headline,
            detail=simple_text,
            materiality_label="Önemli değişim",
            risk_label=risk_label,
            source_label="Intelligence Stream",
            audit=audit,
        ),
    )


def _attention_importance_rank(value: str) -> int:
    return 2 if value == "critical" else 1


def _attention_state_label(
    analytical: dict[str, Any],
    fact: dict[str, Any],
) -> str | None:
    stance = analytical.get("stance")
    if isinstance(stance, dict):
        raw = stance.get("effective_stance")
        if isinstance(raw, str):
            return _STANCE_LABELS.get(raw, "Karışık / izle")
    family_state = analytical.get("family_state_label")
    if isinstance(family_state, str):
        if str(fact.get("source_quality", "")).lower() in {
            "unavailable",
            "missing",
        }:
            return "Veri eksik"
        direction = fact.get("direction")
        if isinstance(direction, str) and direction in _DIRECTION_LABELS:
            return f"{_DIRECTION_LABELS[direction]} yönlü aile değişimi"
        return "Aile durumu güncellendi"
    return None


def _latest_verified_system_view(
    path: Path,
    *,
    symbol: str,
    observed_at_ms: int,
) -> dict[str, Any] | None:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        if not _table_exists(connection, "stream_system_view_messages"):
            return None
        row = _latest_system_view_row(
            connection,
            symbol=symbol,
            observed_at_ms=observed_at_ms,
        )
    if row is None:
        return None
    return verified_system_view_record(
        narrative_identity=str(row[0]),
        event_at_ms=_row_non_negative_int(row[1], "system-view event time"),
        payload_json=str(row[2]),
        expected_digest=str(row[3]),
    )


def _enriched_family_summary(
    row: dict[str, Any],
    *,
    raw_stance: str,
    reader: IntelligenceStreamReadModel,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> FamilySummaryItem:
    base = _family_view(
        row,
        raw_stance=raw_stance,
        include_audit=False,
    )
    source_narrative = row.get("source_narrative_identity")
    if source_narrative is None:
        return FamilySummaryItem(
            family_label=base.family_label,
            state_label=base.state_label,
            direction_label=base.direction_label,
            relationship_label=base.relationship_label,
            source_quality_label=base.source_quality_label,
            source_as_of_ms=None,
            freshness_label="Veri eksik",
            evidence_domain_labels=(),
            uncertainty_label="Kaynak kanıtı yok",
            changed_label="Değişim bilgisi yok",
            timeframe=base.timeframe,
            audit=None,
        )

    narrative_identity = _sha_text(
        source_narrative,
        "family source narrative",
    )
    detail = reader.read_message_detail(narrative_identity)
    if detail is None:
        raise FinalProductReadError("family source narrative is missing")
    fact = _required_mapping(detail, "fact_bundle")
    analytical = _required_mapping(detail, "analytical_view")
    source_as_of_ms = _required_int(fact, "source_as_of_ms")
    if source_as_of_ms > observed_at_ms:
        raise FinalProductReadError("family source is from the future")
    domains = _text_sequence(
        fact.get("available_evidence_domains"),
        "family evidence domains",
    )
    uncertainty_flags = _text_sequence(
        fact.get("uncertainty_flags"),
        "family uncertainty flags",
    )
    changed_components = _text_sequence(
        analytical.get("changed_components"),
        "family changed components",
    )
    previous_state = analytical.get("previous_family_state_label")
    changed_label = (
        "İlk kayıt"
        if previous_state is None
        else f"{len(changed_components)} bileşen değişti"
    )
    uncertainty_label = (
        "Belirgin belirsizlik işareti yok"
        if not uncertainty_flags
        else f"{len(uncertainty_flags)} belirsizlik işareti"
    )

    audit = None
    if include_audit:
        audit = FamilySummaryAudit(
            source_narrative_identity=narrative_identity,
            fact_bundle_identity=_required_sha(fact, "fact_bundle_identity"),
            analytical_view_identity=_required_sha(
                analytical,
                "analytical_view_identity",
            ),
            source_evidence_identities=tuple(
                _sha_text(value, "family evidence identity")
                for value in _required_sequence(fact, "evidence_identities")
            ),
            raw_state_label=_required_text(fact, "state_label"),
            uncertainty_flags=uncertainty_flags,
        )
    return FamilySummaryItem(
        family_label=base.family_label,
        state_label=base.state_label,
        direction_label=base.direction_label,
        relationship_label=base.relationship_label,
        source_quality_label=base.source_quality_label,
        source_as_of_ms=source_as_of_ms,
        freshness_label=_freshness_label(
            observed_at_ms=observed_at_ms,
            source_as_of_ms=source_as_of_ms,
            stale_after_ms=stale_after_ms,
        ),
        evidence_domain_labels=tuple(
            _EVIDENCE_DOMAIN_LABELS.get(
                value,
                "Diğer doğrulanmış kanıt",
            )
            for value in domains
        ),
        uncertainty_label=uncertainty_label,
        changed_label=changed_label,
        timeframe=base.timeframe,
        audit=audit,
    )


def _freshness_label(
    *,
    observed_at_ms: int,
    source_as_of_ms: int,
    stale_after_ms: int,
) -> str:
    if source_as_of_ms > observed_at_ms:
        raise ValueError("source as-of cannot be in the future")
    return (
        "Güncel"
        if observed_at_ms - source_as_of_ms <= stale_after_ms
        else "Güncel değil"
    )


def _text_sequence(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{label} must be a sequence")
    result = tuple(str(item) for item in value)
    if any(not item.strip() for item in result):
        raise ValueError(f"{label} cannot contain blank text")
    return result


def _normalize_symbols(symbols: tuple[str, ...]) -> tuple[str, ...]:
    if not symbols:
        raise ValueError("market pulse requires at least one symbol")
    result: list[str] = []
    seen: set[str] = set()
    for value in symbols:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("market pulse symbol must be non-empty")
        if symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
    return tuple(result)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _latest_system_view_row(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    observed_at_ms: int,
) -> tuple[object, ...] | None:
    row = connection.execute(
        """
        SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
        FROM stream_system_view_messages
        WHERE symbol = ?
          AND event_at_ms <= ?
        ORDER BY event_at_ms DESC, narrative_identity DESC
        LIMIT 1
        """,
        (symbol, observed_at_ms),
    ).fetchone()
    return None if row is None else tuple(row)


def _market_pulse_asset(
    payload: dict[str, Any],
    *,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> MarketPulseAssetView:
    symbol = _required_text(payload, "symbol")
    timeframe = _required_text(payload, "timeframe")
    event_at_ms = _required_int(payload, "event_at_ms")
    if event_at_ms > observed_at_ms:
        raise FinalProductReadError("market pulse source is from the future")

    fact = _required_mapping(payload, "fact_bundle")
    analytical = _required_mapping(payload, "analytical_view")
    stance = _required_mapping(analytical, "stance")
    uncertainty = _required_mapping(analytical, "uncertainty")
    raw_stance = _required_text(stance, "effective_stance")
    family_rows = _required_sequence(fact, "family_contributions")
    families = tuple(
        _family_view(
            row,
            raw_stance=raw_stance,
            include_audit=include_audit,
        )
        for row in sorted(
            (_mapping_value(value, "family contribution") for value in family_rows),
            key=lambda value: (
                _FAMILY_ORDER.get(str(value.get("family")), 99),
                str(value.get("family")),
            ),
        )
    )

    contradiction = analytical.get("main_contradiction")
    contradiction_label = _contradiction_label(contradiction)
    text = _required_mapping(payload, "text")
    summary = _required_text(text, "collapsed_text")

    audit = None
    if include_audit:
        audit = MarketPulseAudit(
            narrative_identity=_required_sha(payload, "narrative_identity"),
            semantic_identity=_required_sha(payload, "semantic_identity"),
            schema_version=_required_text(payload, "schema_version"),
        )

    return MarketPulseAssetView(
        symbol=symbol,
        timeframe=timeframe,
        updated_at_ms=event_at_ms,
        freshness_label=(
            "Güncel"
            if observed_at_ms - event_at_ms <= stale_after_ms
            else "Güncel değil"
        ),
        stance_label=_STANCE_LABELS.get(raw_stance, "Karışık / izle"),
        support_score_0_100=_decimal_text(
            stance.get("support_score_0_100"),
            "support score",
        ),
        opposition_score_0_100=_decimal_text(
            stance.get("opposition_score_0_100"),
            "opposition score",
        ),
        evidence_coverage_0_100=_decimal_text(
            fact.get("evidence_coverage_0_100"),
            "evidence coverage",
        ),
        probability_label=(
            "Kalibre edilmiş olasılık değil"
            if uncertainty.get("probability_status") == "not_calibrated"
            else "Olasılık durumu doğrulanmadı"
        ),
        event_risk_label=_event_risk_label(
            uncertainty.get("event_risk_state")
        ),
        provider_quality_label=_provider_quality_label(
            uncertainty.get("provider_quality_state")
        ),
        trigger_zone=_optional_mapping(fact.get("trigger_zone")),
        target_zone=_optional_mapping(fact.get("target_zone")),
        invalidation_price=_optional_decimal_text(
            fact.get("invalidation_price")
        ),
        main_contradiction_label=contradiction_label,
        summary=summary,
        families=families,
        audit=audit,
    )


def _family_view(
    row: dict[str, Any],
    *,
    raw_stance: str,
    include_audit: bool,
) -> MarketPulseFamilyView:
    family = _required_text(row, "family")
    raw_state = str(row.get("state", ""))
    direction = row.get("direction")
    direction_text = direction if isinstance(direction, str) else None
    support = _decimal(row.get("support_points"), "family support")
    opposition = _decimal(row.get("opposition_points"), "family opposition")

    if raw_state == "no_evidence":
        state_label = "Veri eksik"
    elif raw_state == "abstain":
        state_label = "Teyit yetersiz"
    elif raw_state == "observed":
        state_label = "Veri mevcut"
    else:
        state_label = "Durum doğrulanmadı"

    if support > 0:
        relationship = "Destekliyor"
    elif opposition > 0:
        relationship = "Çelişiyor"
    elif raw_state == "observed" and direction_text in {"bullish", "bearish"}:
        relationship = (
            "Destekliyor"
            if direction_text == raw_stance
            else "Karışık"
        )
    elif raw_state == "no_evidence":
        relationship = "Veri eksik"
    else:
        relationship = "Karışık"

    audit = None
    if include_audit:
        source_narrative = row.get("source_narrative_identity")
        if source_narrative is not None:
            source_narrative = _sha_text(
                source_narrative,
                "family source narrative",
            )
        source_ids_raw = row.get("source_evidence_identities", ())
        if not isinstance(source_ids_raw, (list, tuple)):
            raise TypeError("family source evidence identities must be a sequence")
        source_ids = tuple(
            _sha_text(value, "family source evidence")
            for value in source_ids_raw
        )
        audit = MarketPulseFamilyAudit(
            source_narrative_identity=source_narrative,
            source_evidence_identities=source_ids,
        )

    return MarketPulseFamilyView(
        family=family,
        family_label=_FAMILY_LABELS.get(family, family.replace("_", " ").title()),
        weight_points=_decimal_text(row.get("weight_points"), "family weight"),
        state_label=state_label,
        direction_label=(
            None
            if direction_text is None
            else _DIRECTION_LABELS.get(direction_text, "Karışık")
        ),
        relationship_label=relationship,
        source_quality_label=_source_quality_label(row.get("source_quality")),
        timeframe=(
            None
            if row.get("timeframe") is None
            else str(row.get("timeframe"))
        ),
        audit=audit,
    )


def _contradiction_label(value: object) -> str | None:
    if value is None:
        return None
    raw = _mapping_value(value, "main contradiction")
    family = raw.get("family")
    points = raw.get("opposition_points")
    if not isinstance(family, str):
        return "Ana çelişki mevcut"
    label = _FAMILY_LABELS.get(family, family.replace("_", " ").title())
    if points is None:
        return f"{label} çelişiyor"
    return f"{label} çelişiyor ({_decimal_text(points, 'opposition points')} puan)"


def _source_quality_label(value: object) -> str:
    raw = "" if value is None else str(value).strip().lower()
    if raw in {"unavailable", "no_evidence", "missing"}:
        return "Veri eksik"
    if raw in {"stale", "degraded", "degraded_provider_stale"}:
        return "Güncel değil"
    if raw in {"unresolved", "not_evaluable"}:
        return "Kararsız"
    return "Kaynak gözlemlendi"


def _event_risk_label(value: object) -> str:
    if value is None:
        return "Event verisi yok"
    raw = str(value).strip().lower()
    return _EVENT_RISK_LABELS.get(raw, "Event durumu mevcut")


def _provider_quality_label(value: object) -> str:
    if value is None:
        return "Kaynak durumu yok"
    raw = str(value).strip().lower()
    return _PROVIDER_QUALITY_LABELS.get(raw, "Kaynak durumu mevcut")


def _required_mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    return _mapping_value(value.get(key), key)


def _mapping_value(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _optional_mapping(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    return _mapping_value(value, "optional market pulse mapping")


def _required_sequence(
    value: dict[str, Any],
    key: str,
) -> tuple[object, ...]:
    raw = value.get(key)
    if not isinstance(raw, (list, tuple)):
        raise TypeError(f"{key} must be a sequence")
    return tuple(raw)


def _required_text(value: dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw:
        raise TypeError(f"{key} must be non-empty text")
    return raw


def _row_non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{label} must be a non-negative integer")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.isdigit():
        result = int(value)
    else:
        raise TypeError(f"{label} must be a non-negative integer")
    if result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _required_int(value: dict[str, Any], key: str) -> int:
    raw = value.get(key)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise TypeError(f"{key} must be a non-negative integer")
    return raw


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TypeError(f"{label} must be decimal-compatible") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def _decimal_text(value: object, label: str) -> str:
    return f"{_decimal(value, label).quantize(Decimal('0.01')):.2f}"


def _optional_decimal_text(value: object) -> str | None:
    if value is None:
        return None
    return _decimal_text(value, "optional decimal")


def _required_sha(value: dict[str, Any], key: str) -> str:
    return _sha_text(value.get(key), key)


def _sha_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be SHA256 text")
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
    return value
