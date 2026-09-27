from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any

from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.product.intelligence_stream_family import (
    StreamFamilySnapshot,
    StreamTrustDomain,
)
from crypto_signal.product.intelligence_stream_models import REAL_CAPITAL
from crypto_signal.product.intelligence_stream_narrative_ledger import (
    IntelligenceStreamNarrativeLedger,
)

STREAM_SYSTEM_VIEW_SCHEMA_VERSION = "intelligence-stream-system-view-message-v1/1"
STREAM_SYSTEM_VIEW_LEDGER_SCHEMA_VERSION = "intelligence-stream-system-view-ledger-v1/1"
STREAM_SYSTEM_VIEW_COMPOSER_VERSION = "crypto-signal-system-view-composer-v1/1"
STREAM_SYSTEM_VIEW_SCORE_SEMANTIC = (
    "weighted_directional_family_vote_not_probability"
)
STREAM_SYSTEM_VIEW_TIMEFRAME_FALLBACK = "multi_horizon"

_FAMILY_WEIGHTS: dict[ConfluenceFamily, Decimal] = {
    ConfluenceFamily.GEOMETRY: Decimal("0.20"),
    ConfluenceFamily.LIQUIDITY: Decimal("0.25"),
    ConfluenceFamily.ORDER_FLOW: Decimal("0.25"),
    ConfluenceFamily.DERIVATIVES: Decimal("0.15"),
    ConfluenceFamily.ONCHAIN: Decimal("0.15"),
}
_DIRECTION_BULLISH = {"bullish", "buy_pressure"}
_DIRECTION_BEARISH = {"bearish", "sell_pressure"}
_EVENT_RISK_SEVERITY = {
    "clear": 0,
    "post_event_stabilization": 1,
    "pre_event_caution": 2,
    "degraded_data": 3,
    "event_block": 4,
}
_PROVIDER_QUALITY_SEVERITY = {
    "healthy": 0,
    "caution_partial_coverage": 1,
    "degraded_no_overlap": 2,
    "degraded_provider_stale": 3,
    "degraded_provider_unavailable": 4,
}


class StreamSystemViewDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StreamSystemViewResult:
    disposition: StreamSystemViewDisposition
    symbol: str
    narrative_identity: str | None
    semantic_identity: str
    stance: str
    event_at_ms: int
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if not self.symbol.strip() or self.event_at_ms < 0:
            raise ValueError("invalid Stream system-view result")
        _require_sha256(self.semantic_identity, "system-view semantic identity")
        if self.narrative_identity is not None:
            _require_sha256(self.narrative_identity, "system-view narrative identity")
        if self.stance not in {"bullish", "bearish", "watch", "blocked"}:
            raise ValueError("unsupported Stream system-view stance")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("Stream system view cannot grant production/real-capital authority")


class IntelligenceStreamSystemViewRuntime:
    """Append-only presentation aggregation over exact family snapshots.

    This runtime does not issue a forecast, trade decision, probability, or capital action.
    It only composes the current directional evidence tilt from the locked family weights.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        IntelligenceStreamNarrativeLedger(self.path).initialize()
        with sqlite3.connect(self.path, timeout=30.0) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS stream_system_view_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stream_system_view_messages (
                    narrative_identity TEXT PRIMARY KEY,
                    semantic_identity TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS stream_system_view_symbol_time
                ON stream_system_view_messages(symbol, event_at_ms, narrative_identity);
                """
            )
            expected = {
                "composer_version": STREAM_SYSTEM_VIEW_COMPOSER_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": STREAM_SYSTEM_VIEW_LEDGER_SCHEMA_VERSION,
            }
            for key, value in expected.items():
                row = connection.execute(
                    "SELECT value FROM stream_system_view_meta WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO stream_system_view_meta (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise ValueError(f"Stream system-view metadata mismatch for {key}")
            for table in ("stream_system_view_meta", "stream_system_view_messages"):
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'immutable intelligence stream system view'
                            );
                        END
                        """
                    )

    def compose_and_append(
        self,
        *,
        symbol: str,
        event_at_ms: int,
        family_snapshots: tuple[StreamFamilySnapshot, ...],
        trust_snapshots: tuple[StreamFamilySnapshot, ...] = (),
    ) -> StreamSystemViewResult:
        if not symbol.strip() or symbol != symbol.upper() or event_at_ms < 0:
            raise ValueError("invalid Stream system-view market identity")
        self.initialize()

        selected = self._select_family_snapshots(
            symbol=symbol,
            snapshots=family_snapshots,
        )
        event_risk_state = self._worst_trust_state(
            trust_snapshots,
            family=StreamTrustDomain.EVENT_RISK,
            severity=_EVENT_RISK_SEVERITY,
            symbol=None,
        )
        provider_quality_state = self._worst_trust_state(
            trust_snapshots,
            family=StreamTrustDomain.PROVIDER_QUALITY,
            severity=_PROVIDER_QUALITY_SEVERITY,
            symbol=symbol,
        )

        family_rows = tuple(
            self._family_row(
                family=family,
                snapshot=selected.get(family),
            )
            for family in sorted(ConfluenceFamily, key=lambda item: item.value)
        )
        bullish_points = sum(
            (
                Decimal(str(item["weight_points"]))
                for item in family_rows
                if item["state"] == "observed" and item["direction"] == "bullish"
            ),
            Decimal(0),
        )
        bearish_points = sum(
            (
                Decimal(str(item["weight_points"]))
                for item in family_rows
                if item["state"] == "observed" and item["direction"] == "bearish"
            ),
            Decimal(0),
        )
        coverage_points = sum(
            (
                Decimal(str(item["weight_points"]))
                for item in family_rows
                if item["state"] in {"observed", "abstain"}
            ),
            Decimal(0),
        )

        if event_risk_state == "event_block":
            stance = "blocked"
        elif bullish_points > bearish_points:
            stance = "bullish"
        elif bearish_points > bullish_points:
            stance = "bearish"
        else:
            stance = "watch"

        support_points = (
            bullish_points
            if stance == "bullish"
            else bearish_points
            if stance == "bearish"
            else Decimal(0)
        )
        opposition_points = (
            bearish_points
            if stance == "bullish"
            else bullish_points
            if stance == "bearish"
            else max(bullish_points, bearish_points)
        )
        rows_with_score = tuple(
            self._score_family_row(item, stance=stance)
            for item in family_rows
        )

        geometry = selected.get(ConfluenceFamily.GEOMETRY)
        geometry_direction = (
            None if geometry is None else _normalize_direction(geometry.direction)
        )
        geometry_values = (
            self._geometry_values(geometry)
            if geometry is not None
            and stance in {"bullish", "bearish"}
            and geometry_direction == stance
            else {
                "trigger_zone": None,
                "target_zone": None,
                "invalidation_price": None,
            }
        )

        timeframe = (
            geometry.timeframe
            if geometry is not None and geometry.timeframe.strip()
            else STREAM_SYSTEM_VIEW_TIMEFRAME_FALLBACK
        )
        main_contradiction = self._main_contradiction(rows_with_score)
        collapsed = self._collapsed_text(
            symbol=symbol,
            stance=stance,
            geometry_values=geometry_values,
            provider_quality_state=provider_quality_state,
            event_risk_state=event_risk_state,
        )
        simple = self._simple_text(
            collapsed=collapsed,
            family_rows=rows_with_score,
            coverage_points=coverage_points,
            event_risk_state=event_risk_state,
            provider_quality_state=provider_quality_state,
        )

        semantic_payload = {
            "composer_version": STREAM_SYSTEM_VIEW_COMPOSER_VERSION,
            "event_risk_state": event_risk_state,
            "families": tuple(
                {
                    "direction": item["direction"],
                    "family": item["family"],
                    "source_quality": item["source_quality"],
                    "state": item["state"],
                    "state_label": item["state_label"],
                    "timeframe": item["timeframe"],
                }
                for item in rows_with_score
            ),
            "geometry_values": geometry_values,
            "main_contradiction": main_contradiction,
            "provider_quality_state": provider_quality_state,
            "stance": stance,
            "symbol": symbol,
            "timeframe": timeframe,
        }
        semantic_identity = canonical_sha256(semantic_payload)
        previous = self._latest_for_symbol(symbol)
        if previous is not None and previous["semantic_identity"] == semantic_identity:
            return StreamSystemViewResult(
                disposition=StreamSystemViewDisposition.UNCHANGED,
                symbol=symbol,
                narrative_identity=str(previous["narrative_identity"]),
                semantic_identity=semantic_identity,
                stance=stance,
                event_at_ms=event_at_ms,
            )

        analytical_view = {
            "schema_version": "intelligence-stream-system-view-analytical-v1/1",
            "stance": {
                "effective_stance": stance,
                "support_score_0_100": _decimal_text(support_points),
                "opposition_score_0_100": _decimal_text(opposition_points),
            },
            "main_contradiction": (
                None
                if main_contradiction is None
                else {
                    "family": main_contradiction["family"],
                    "opposition_points": main_contradiction["opposition_points"],
                }
            ),
            "uncertainty": {
                "probability_status": "not_calibrated",
                "event_risk_state": event_risk_state,
                "provider_quality_state": provider_quality_state,
            },
        }
        fact_bundle = {
            "schema_version": "intelligence-stream-system-view-fact-v1/1",
            "symbol": symbol,
            "timeframe": timeframe,
            "confluence_support_score_0_100": _decimal_text(support_points),
            "confluence_opposition_score_0_100": _decimal_text(opposition_points),
            "evidence_coverage_0_100": _decimal_text(coverage_points),
            "probability_status": "not_calibrated",
            "score_semantic": STREAM_SYSTEM_VIEW_SCORE_SEMANTIC,
            "event_context_state": event_risk_state,
            "provider_quality_state": provider_quality_state,
            "trigger_zone": geometry_values["trigger_zone"],
            "target_zone": geometry_values["target_zone"],
            "invalidation_price": geometry_values["invalidation_price"],
            "family_contributions": rows_with_score,
        }
        payload_without_identity = {
            "analytical_view": analytical_view,
            "category": "intelligence",
            "composer_version": STREAM_SYSTEM_VIEW_COMPOSER_VERSION,
            "event_at_ms": event_at_ms,
            "fact_bundle": fact_bundle,
            "importance": "important" if stance != "watch" else "routine",
            "production_authority": False,
            "read_only": True,
            "real_capital": REAL_CAPITAL,
            "schema_version": STREAM_SYSTEM_VIEW_SCHEMA_VERSION,
            "semantic_identity": semantic_identity,
            "source_kind": "deterministic",
            "state": stance,
            "subtype": "system_view_updated",
            "symbol": symbol,
            "text": {
                "collapsed_text": collapsed,
                "simple_text": simple,
                "technical_text": (
                    "Bu mesaj beş family'nin exact persisted durumlarının sabit "
                    "20/25/25/15/15 ağırlıklı sunum birleşimidir. Forecast veya "
                    "kalibre edilmiş olasılık değildir."
                ),
                "intelligence_text": simple,
                "decision_text": (
                    "Bu system view yeni işlem/forecast authority üretmez; gerçek "
                    "Decision issuance yalnız kendi canonical hattından gelebilir."
                ),
                "capital_text": "REAL_CAPITAL=0.",
            },
            "timeframe": timeframe,
        }
        narrative_identity = canonical_sha256(payload_without_identity)
        payload = {
            "narrative_identity": narrative_identity,
            **payload_without_identity,
        }
        encoded = canonical_json(payload)

        with sqlite3.connect(self.path, timeout=30.0) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM stream_system_view_messages
                WHERE narrative_identity = ?
                """,
                (narrative_identity,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == encoded
                    and str(existing[1]) == sha256_text(encoded)
                ):
                    connection.rollback()
                    return StreamSystemViewResult(
                        disposition=StreamSystemViewDisposition.UNCHANGED,
                        symbol=symbol,
                        narrative_identity=narrative_identity,
                        semantic_identity=semantic_identity,
                        stance=stance,
                        event_at_ms=event_at_ms,
                    )
                raise ValueError("immutable Stream system-view replay conflict")
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
                    narrative_identity,
                    semantic_identity,
                    symbol,
                    timeframe,
                    event_at_ms,
                    encoded,
                    sha256_text(encoded),
                ),
            )
            connection.commit()

        return StreamSystemViewResult(
            disposition=StreamSystemViewDisposition.INSERTED,
            symbol=symbol,
            narrative_identity=narrative_identity,
            semantic_identity=semantic_identity,
            stance=stance,
            event_at_ms=event_at_ms,
        )

    def _select_family_snapshots(
        self,
        *,
        symbol: str,
        snapshots: tuple[StreamFamilySnapshot, ...],
    ) -> dict[ConfluenceFamily, StreamFamilySnapshot]:
        selected: dict[ConfluenceFamily, StreamFamilySnapshot] = {}
        for family in ConfluenceFamily:
            candidates = [
                item
                for item in snapshots
                if item.symbol == symbol and item.family is family
            ]
            if not candidates:
                continue
            candidates.sort(
                key=lambda item: (
                    1 if item.source_scope.startswith("bybit:") else 0,
                    item.event_at_ms,
                    item.source_event_identity,
                ),
                reverse=True,
            )
            selected[family] = candidates[0]
        return selected

    def _family_row(
        self,
        *,
        family: ConfluenceFamily,
        snapshot: StreamFamilySnapshot | None,
    ) -> dict[str, Any]:
        weight = _FAMILY_WEIGHTS[family]
        source_narrative_identity = (
            None
            if snapshot is None
            else self._family_narrative_identity_for_snapshot(snapshot)
        )
        if snapshot is None:
            return {
                "direction": None,
                "evidence_domains": (),
                "family": family.value,
                "material_conflict_count": 0,
                "opposition_points": "0.00",
                "prior_weight": _decimal_text(weight),
                "source_evidence_identities": (),
                "source_narrative_identity": source_narrative_identity,
                "source_quality": "unavailable",
                "state": "no_evidence",
                "state_label": "unavailable",
                "support_points": "0.00",
                "timeframe": None,
                "weight_points": _decimal_text(weight * Decimal(100)),
            }
        direction = _normalize_direction(snapshot.direction)
        state = (
            "abstain"
            if snapshot.source_quality.lower() in {"unresolved", "unavailable"}
            else "observed"
        )
        return {
            "direction": direction,
            "evidence_domains": snapshot.evidence_domains,
            "family": family.value,
            "material_conflict_count": 0,
            "opposition_points": "0.00",
            "prior_weight": _decimal_text(weight),
            "source_evidence_identities": snapshot.evidence_identities,
            "source_narrative_identity": source_narrative_identity,
            "source_quality": snapshot.source_quality,
            "state": state,
            "state_label": snapshot.state_label,
            "support_points": "0.00",
            "timeframe": snapshot.timeframe,
            "weight_points": _decimal_text(weight * Decimal(100)),
        }

    def _score_family_row(
        self,
        row: dict[str, Any],
        *,
        stance: str,
    ) -> dict[str, Any]:
        result = dict(row)
        if row["state"] != "observed" or stance not in {"bullish", "bearish"}:
            return result
        direction = row["direction"]
        weight_points = Decimal(str(row["weight_points"]))
        if direction == stance:
            result["support_points"] = _decimal_text(weight_points)
        elif direction in {"bullish", "bearish"}:
            result["opposition_points"] = _decimal_text(weight_points)
        return result

    def _geometry_values(
        self,
        snapshot: StreamFamilySnapshot,
    ) -> dict[str, Any]:
        components = {item.name: item.value for item in snapshot.state_components}
        try:
            low = Decimal(components["entry_zone_low"])
            high = Decimal(components["entry_zone_high"])
            invalidation = Decimal(components["invalidation_price"])
        except (KeyError, ValueError):
            return {
                "trigger_zone": None,
                "target_zone": None,
                "invalidation_price": None,
            }
        target_keys = sorted(
            key
            for key in components
            if key.startswith("target_") and key.endswith("_price")
        )
        if not target_keys:
            return {
                "trigger_zone": None,
                "target_zone": None,
                "invalidation_price": None,
            }
        try:
            target = Decimal(components[target_keys[0]])
        except ValueError:
            return {
                "trigger_zone": None,
                "target_zone": None,
                "invalidation_price": None,
            }
        return {
            "trigger_zone": {
                "low": _decimal_text(low),
                "high": _decimal_text(high),
            },
            "target_zone": {
                "low": _decimal_text(target),
                "high": _decimal_text(target),
            },
            "invalidation_price": _decimal_text(invalidation),
        }

    def _main_contradiction(
        self,
        rows: tuple[dict[str, Any], ...],
    ) -> dict[str, str] | None:
        candidates = [
            item
            for item in rows
            if Decimal(str(item["opposition_points"])) > 0
        ]
        if not candidates:
            return None
        selected = max(
            candidates,
            key=lambda item: (
                Decimal(str(item["opposition_points"])),
                str(item["family"]),
            ),
        )
        return {
            "family": str(selected["family"]),
            "opposition_points": str(selected["opposition_points"]),
        }

    def _collapsed_text(
        self,
        *,
        symbol: str,
        stance: str,
        geometry_values: dict[str, Any],
        provider_quality_state: str | None,
        event_risk_state: str | None,
    ) -> str:
        asset = _asset_label(symbol)
        if stance == "blocked":
            return (
                f"Yakın dönem olay riski nedeniyle {asset} için yeni yön görüşünü "
                "blokluyorum; risk penceresi temizlenmeden teyit vermiyorum."
            )
        if stance == "watch":
            base = (
                f"{asset} için kanıtlar şu an ortak bir yön teyidi vermiyor; "
                "yeni netleşme bekliyorum."
            )
        else:
            direction = "yükseliş" if stance == "bullish" else "düşüş"
            trigger = geometry_values.get("trigger_zone")
            target = geometry_values.get("target_zone")
            invalidation = geometry_values.get("invalidation_price")
            if (
                isinstance(trigger, dict)
                and isinstance(target, dict)
                and invalidation is not None
            ):
                base = (
                    f"{asset} için kanıt dengesi {direction} yönüne eğiliyor. "
                    f"{_zone_text(trigger)} tetik bölgesi korunursa "
                    f"{_zone_text(target)} hedefi izleniyor; "
                    f"{_price_text(invalidation)} bu görünümün geçersizlik sınırı."
                )
            else:
                base = (
                    f"{asset} için kanıt dengesi {direction} yönüne eğiliyor; "
                    "exact tetik/hedef koşulu olmadığı için fiyat hedefi vermiyorum."
                )
        if provider_quality_state and provider_quality_state != "healthy":
            return (
                base
                + " Veri güveni tam olmadığı için bu görünümün teyit gücü azaltıldı."
            )
        if event_risk_state in {
            "pre_event_caution",
            "post_event_stabilization",
            "degraded_data",
        }:
            return base + " Olay riski nedeniyle ek temkin uyguluyorum."
        return base

    def _simple_text(
        self,
        *,
        collapsed: str,
        family_rows: tuple[dict[str, Any], ...],
        coverage_points: Decimal,
        event_risk_state: str | None,
        provider_quality_state: str | None,
    ) -> str:
        available = sum(
            1 for item in family_rows if item["state"] in {"observed", "abstain"}
        )
        return (
            f"{collapsed} Beş kanıt ailesinin {available}/5'i ölçülebilir; "
            f"ağırlıklı kapsam {_decimal_text(coverage_points)}/100. "
            "Bu skor olasılık değildir. "
            f"Event Risk: {event_risk_state or 'ölçülmedi'}; "
            f"veri güveni: {provider_quality_state or 'ölçülmedi'}."
        )

    def _worst_trust_state(
        self,
        snapshots: tuple[StreamFamilySnapshot, ...],
        *,
        family: StreamTrustDomain,
        severity: dict[str, int],
        symbol: str | None,
    ) -> str | None:
        candidates = [
            item.state_label
            for item in snapshots
            if item.family == family
            and (symbol is None or item.symbol in {symbol, "CRYPTO"})
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda value: (severity.get(value, 99), value))

    def _family_narrative_identity_for_snapshot(
        self,
        snapshot: StreamFamilySnapshot,
    ) -> str | None:
        with self._connect_ro() as connection:
            row = connection.execute(
                """
                SELECT n.narrative_identity
                FROM stream_narrative_messages AS n
                JOIN stream_narrative_plans AS p
                  ON p.plan_identity = n.plan_identity
                JOIN stream_fact_bundles AS f
                  ON f.fact_bundle_identity = p.fact_bundle_identity
                WHERE json_extract(f.payload_json, '$.family') = ?
                  AND json_extract(f.payload_json, '$.symbol') = ?
                  AND json_extract(f.payload_json, '$.source_event_identity') = ?
                ORDER BY n.event_at_ms DESC, n.narrative_identity DESC
                LIMIT 1
                """,
                (
                    snapshot.family.value,
                    snapshot.symbol,
                    snapshot.source_event_identity,
                ),
            ).fetchone()
        if row is None:
            return None
        identity = str(row[0])
        _require_sha256(identity, "system-view source family narrative")
        return identity

    def _latest_for_symbol(self, symbol: str) -> dict[str, Any] | None:
        with self._connect_ro() as connection:
            row = connection.execute(
                """
                SELECT narrative_identity, semantic_identity, event_at_ms
                FROM stream_system_view_messages
                WHERE symbol = ?
                ORDER BY event_at_ms DESC, narrative_identity DESC
                LIMIT 1
                """,
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        return {
            "narrative_identity": str(row[0]),
            "semantic_identity": str(row[1]),
            "event_at_ms": int(str(row[2])),
        }

    def _connect_ro(self) -> sqlite3.Connection:
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=10.0)
        connection.execute("PRAGMA query_only=ON")
        return connection


def verified_system_view_record(
    *,
    narrative_identity: str,
    event_at_ms: int,
    payload_json: str,
    expected_digest: str,
) -> dict[str, Any]:
    _require_sha256(narrative_identity, "system-view narrative identity")
    if sha256_text(payload_json) != expected_digest:
        raise ValueError("Stream system-view persisted payload digest mismatch")
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("Stream system-view payload must be an object")
    if payload.get("schema_version") != STREAM_SYSTEM_VIEW_SCHEMA_VERSION:
        raise ValueError("unsupported Stream system-view schema")
    if payload.get("narrative_identity") != narrative_identity:
        raise ValueError("Stream system-view narrative identity mismatch")
    if int(payload.get("event_at_ms", -1)) != event_at_ms:
        raise ValueError("Stream system-view event time mismatch")
    if payload.get("production_authority") is not False:
        raise ValueError("Stream system view cannot grant production authority")
    if int(payload.get("real_capital", -1)) != REAL_CAPITAL:
        raise ValueError("Stream system view REAL_CAPITAL mismatch")
    semantic_identity = payload.get("semantic_identity")
    if not isinstance(semantic_identity, str):
        raise TypeError("Stream system-view semantic identity missing")
    _require_sha256(semantic_identity, "system-view semantic identity")
    return payload


def _normalize_direction(value: str | None) -> str | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in _DIRECTION_BULLISH:
        return "bullish"
    if lowered in _DIRECTION_BEARISH:
        return "bearish"
    return None


def _asset_label(symbol: str) -> str:
    labels = {
        "BTCUSDT": "Bitcoin",
        "ETHUSDT": "Ethereum",
        "SOLUSDT": "Solana",
    }
    return labels.get(symbol, symbol)


def _zone_text(zone: dict[str, Any]) -> str:
    low = zone.get("low")
    high = zone.get("high")
    if low == high:
        return _price_text(low)
    return f"{_price_text(low)}–{_price_text(high)}"


def _price_text(value: Any) -> str:
    try:
        decimal = Decimal(str(value))
    except InvalidOperation:
        return "—"
    if decimal == decimal.to_integral():
        return f"${decimal:,.0f}"
    return f"${decimal:,.2f}"


def _decimal_text(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
