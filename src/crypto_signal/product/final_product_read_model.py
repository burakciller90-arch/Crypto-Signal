from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from crypto_signal.product.intelligence_stream_system_view import (
    verified_system_view_record,
)

FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION = "final-product-read-model-v1/1"
DEFAULT_MARKET_PULSE_STALE_AFTER_MS = 15 * 60 * 1000
REAL_CAPITAL = 0

_FAMILY_ORDER = {
    "geometry": 0,
    "liquidity": 1,
    "order_flow": 2,
    "derivatives": 3,
    "onchain": 4,
}
_FAMILY_LABELS = {
    "geometry": "Geometri",
    "liquidity": "Likidite",
    "order_flow": "Emir Akışı",
    "derivatives": "Türevler",
    "onchain": "On-chain",
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
                    event_at_ms=int(row[1]),
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
