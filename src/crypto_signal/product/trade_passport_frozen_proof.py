from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crypto_signal.product.final_product_read_model import (
    FinalProductReadError,
    FinalProductReadModel,
    TradePassportView,
)
from crypto_signal.product.intelligence_stream_exact_evidence import (
    IntelligenceStreamExactEvidenceReadModel,
    StreamExactEvidenceError,
)
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamReadModelError,
)
from crypto_signal.product.intelligence_stream_visual_proof import (
    IntelligenceStreamVisualProofReadModel,
    StreamVisualProofError,
)

TRADE_PASSPORT_FROZEN_PROOF_SCHEMA_VERSION = "trade-passport-frozen-proof-v1/2"
REAL_CAPITAL = 0


class TradePassportFrozenProofError(ValueError):
    """Raised when immutable Trade Passport proof lineage cannot be trusted."""


@dataclass(frozen=True, slots=True)
class TradePassportFrozenProofAudit:
    narrative_identity: str
    narrative_event_at_ms: int
    forecast_identity: str
    proof_identity: str
    signal_freeze_identity: str
    decision_freeze_bundle_identity: str | None
    event_as_of_ms: int | None
    proof_frozen_at_ms: int | None


@dataclass(frozen=True, slots=True)
class TradePassportFrozenProofView:
    availability_label: str
    frozen_market_story_label: str
    exact_evidence_label: str
    source_as_of_ms: int | None
    issued_at_ms: int | None
    chart_candle_count: int
    annotation_count: int
    family_proof_count: int
    evidence_domain_count: int
    current_data_substitution: bool
    audit: TradePassportFrozenProofAudit | None = None
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = TRADE_PASSPORT_FROZEN_PROOF_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class _ResolvedNarrative:
    narrative_identity: str
    event_at_ms: int


class TradePassportFrozenProofReadModel:
    """Read-only FP6 bridge from immutable R22 lifecycle to accepted S10/RDP10 proof."""

    def __init__(
        self,
        *,
        stream_ledger_path: Path,
        epoch2_path: Path,
        decision_evidence_path: Path,
        signal_ledger_path: Path,
        market_tape_path: Path | None = None,
        event_source_runtime_path: Path | None = None,
        provider_divergence_path: Path | None = None,
        frozen_proof_store_path: Path | None = None,
        options_surface_path: Path | None = None,
        onchain_capital_flow_path: Path | None = None,
        onchain_source_contract_path: Path | None = None,
    ) -> None:
        self.stream_ledger_path = stream_ledger_path
        self.epoch2_path = epoch2_path
        self.decision_evidence_path = decision_evidence_path
        self.signal_ledger_path = signal_ledger_path
        self.market_tape_path = market_tape_path
        self.event_source_runtime_path = event_source_runtime_path
        self.provider_divergence_path = provider_divergence_path
        self.frozen_proof_store_path = frozen_proof_store_path
        self.options_surface_path = options_surface_path
        self.onchain_capital_flow_path = onchain_capital_flow_path
        self.onchain_source_contract_path = onchain_source_contract_path

    def read_for_bundle(
        self,
        bundle_identity: str,
        *,
        include_audit: bool = False,
    ) -> TradePassportFrozenProofView:
        try:
            passport = FinalProductReadModel(
                stream_ledger_path=self.stream_ledger_path,
                epoch2_path=self.epoch2_path,
                decision_evidence_path=self.decision_evidence_path,
                signal_ledger_path=self.signal_ledger_path,
            ).trade_passport(
                bundle_identity=bundle_identity,
                include_audit=True,
            )
        except FinalProductReadError as exc:
            raise TradePassportFrozenProofError(str(exc)) from exc
        return self.read_for_passport(passport, include_audit=include_audit)

    def read_for_passport(
        self,
        passport: TradePassportView,
        *,
        include_audit: bool = False,
    ) -> TradePassportFrozenProofView:
        audit = passport.audit
        if audit is None:
            return _unavailable("Trade Passport audit lineage kullanılamıyor")
        return self.read_for_lineage(
            forecast_identity=audit.forecast_identity,
            proof_identity=audit.proof_identity,
            signal_freeze_identity=audit.signal_freeze_identity,
            as_of_ms=passport.filled_at_ms,
            include_audit=include_audit,
        )

    def read_for_lineage(
        self,
        *,
        forecast_identity: str,
        proof_identity: str,
        signal_freeze_identity: str,
        as_of_ms: int | None = None,
        include_audit: bool = False,
    ) -> TradePassportFrozenProofView:
        _require_sha256(forecast_identity, "Trade Passport forecast identity")
        _require_sha256(proof_identity, "Trade Passport proof identity")
        _require_sha256(signal_freeze_identity, "Trade Passport signal freeze identity")
        event_as_of_ms = _optional_non_negative_int(as_of_ms)

        if not self.stream_ledger_path.is_file():
            return _unavailable("Dondurulmuş Stream kanıtı kullanılamıyor")
        if not self.decision_evidence_path.is_file():
            return _unavailable("Karar kanıtı kullanılamıyor")
        if not self.signal_ledger_path.is_file():
            return _unavailable("Dondurulmuş sinyal kanıtı kullanılamıyor")

        resolved = self._resolve_exact_narrative(
            forecast_identity=forecast_identity,
            proof_identity=proof_identity,
            signal_freeze_identity=signal_freeze_identity,
            as_of_ms=event_as_of_ms,
        )
        if resolved is None:
            return _unavailable("Bu işlem için exact tarihsel Stream kanıtı bulunamadı")

        visual = self._read_visual(resolved.narrative_identity)
        if visual is None:
            return _unavailable("Bu işlem için dondurulmuş Market Story bulunamadı")

        lineage = _mapping(visual.get("lineage"), "frozen visual proof lineage")
        if lineage.get("forecast_identity") != forecast_identity:
            raise TradePassportFrozenProofError(
                "Trade Passport forecast / frozen proof lineage mismatch"
            )
        if lineage.get("proof_identity") != proof_identity:
            raise TradePassportFrozenProofError(
                "Trade Passport decision proof / frozen proof lineage mismatch"
            )
        if lineage.get("signal_freeze_identity") != signal_freeze_identity:
            raise TradePassportFrozenProofError(
                "Trade Passport signal freeze / frozen proof lineage mismatch"
            )

        provenance = _mapping(
            visual.get("provenance"),
            "frozen visual proof provenance",
        )
        if provenance.get("current_data_substitution") is not False:
            raise TradePassportFrozenProofError(
                "Trade Passport historical proof attempted current-data substitution"
            )
        if visual.get("read_only") is not True or visual.get("real_capital") != REAL_CAPITAL:
            raise TradePassportFrozenProofError(
                "Trade Passport frozen proof authority boundary mismatch"
            )

        source_as_of_ms = _optional_non_negative_int(provenance.get("source_as_of_ms"))
        issued_at_ms = _optional_non_negative_int(provenance.get("issued_at_ms"))
        frozen_at_ms = _optional_non_negative_int(provenance.get("frozen_at_ms"))
        if event_as_of_ms is not None:
            _require_not_after(
                resolved.event_at_ms,
                event_as_of_ms,
                "Stream narrative",
            )
            if source_as_of_ms is not None:
                _require_not_after(
                    source_as_of_ms,
                    event_as_of_ms,
                    "proof source-as-of",
                )
            if issued_at_ms is not None:
                _require_not_after(
                    issued_at_ms,
                    event_as_of_ms,
                    "proof issued-at",
                )
            if frozen_at_ms is not None:
                _require_not_after(
                    frozen_at_ms,
                    event_as_of_ms,
                    "signal freeze",
                )

        try:
            exact = IntelligenceStreamExactEvidenceReadModel(
                stream_ledger_path=self.stream_ledger_path,
                signal_ledger_path=self.signal_ledger_path,
                decision_evidence_path=self.decision_evidence_path,
                market_tape_path=self.market_tape_path,
                event_source_runtime_path=self.event_source_runtime_path,
                provider_divergence_path=self.provider_divergence_path,
                frozen_proof_store_path=self.frozen_proof_store_path,
                options_surface_path=self.options_surface_path,
                onchain_capital_flow_path=self.onchain_capital_flow_path,
                onchain_source_contract_path=self.onchain_source_contract_path,
            ).read_for_narrative(resolved.narrative_identity)
        except StreamExactEvidenceError as exc:
            raise TradePassportFrozenProofError(str(exc)) from exc

        exact_label = (
            "Exact aile/source kanıtı doğrulandı"
            if exact is not None
            else "Exact aile/source kanıtı kullanılamıyor"
        )
        score_components = _mapping(
            visual.get("score_components"),
            "frozen visual proof score components",
        )
        family_contributions = score_components.get("family_contributions")
        if not isinstance(family_contributions, (list, tuple)):
            raise TradePassportFrozenProofError(
                "Trade Passport frozen family proof list is invalid"
            )
        domain_evidence = visual.get("domain_evidence")
        if not isinstance(domain_evidence, (list, tuple)):
            raise TradePassportFrozenProofError(
                "Trade Passport frozen evidence-domain list is invalid"
            )
        candles = visual.get("candles")
        annotations = visual.get("annotations")
        if not isinstance(candles, (list, tuple)):
            raise TradePassportFrozenProofError(
                "Trade Passport frozen candle list is invalid"
            )
        if not isinstance(annotations, (list, tuple)):
            raise TradePassportFrozenProofError(
                "Trade Passport frozen annotation list is invalid"
            )

        decision_freeze_bundle_identity = lineage.get("decision_freeze_bundle_identity")
        if decision_freeze_bundle_identity is not None:
            _require_sha256(
                str(decision_freeze_bundle_identity),
                "Trade Passport decision freeze bundle identity",
            )

        audit_view = None
        if include_audit:
            audit_view = TradePassportFrozenProofAudit(
                narrative_identity=resolved.narrative_identity,
                narrative_event_at_ms=resolved.event_at_ms,
                forecast_identity=forecast_identity,
                proof_identity=proof_identity,
                signal_freeze_identity=signal_freeze_identity,
                decision_freeze_bundle_identity=(
                    None
                    if decision_freeze_bundle_identity is None
                    else str(decision_freeze_bundle_identity)
                ),
                event_as_of_ms=event_as_of_ms,
                proof_frozen_at_ms=frozen_at_ms,
            )

        return TradePassportFrozenProofView(
            availability_label="Doğrulanmış tarihsel kanıt",
            frozen_market_story_label="Dondurulmuş Market Story doğrulandı",
            exact_evidence_label=exact_label,
            source_as_of_ms=source_as_of_ms,
            issued_at_ms=issued_at_ms,
            chart_candle_count=len(candles),
            annotation_count=len(annotations),
            family_proof_count=len(family_contributions),
            evidence_domain_count=len(domain_evidence),
            current_data_substitution=False,
            audit=audit_view,
        )

    def _resolve_exact_narrative(
        self,
        *,
        forecast_identity: str,
        proof_identity: str,
        signal_freeze_identity: str,
        as_of_ms: int | None,
    ) -> _ResolvedNarrative | None:
        uri = f"{self.stream_ledger_path.resolve().as_uri()}?mode=ro"
        parameters: list[object] = [forecast_identity, proof_identity]
        time_clause = ""
        if as_of_ms is not None:
            time_clause = " AND n.event_at_ms <= ?"
            parameters.append(as_of_ms)
        try:
            with sqlite3.connect(uri, uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                required = {
                    "stream_narrative_messages",
                    "stream_narrative_plans",
                    "stream_fact_bundles",
                }
                if not required.issubset(tables):
                    return None
                rows = connection.execute(
                    f"""
                    SELECT n.narrative_identity, n.event_at_ms
                    FROM stream_narrative_messages AS n
                    JOIN stream_narrative_plans AS p
                      ON p.plan_identity = n.plan_identity
                    JOIN stream_fact_bundles AS f
                      ON f.fact_bundle_identity = p.fact_bundle_identity
                    WHERE json_extract(f.payload_json, '$.forecast_identity') = ?
                      AND json_extract(f.payload_json, '$.proof_identity') = ?
                      {time_clause}
                    ORDER BY n.event_at_ms ASC, n.narrative_identity ASC
                    """,
                    tuple(parameters),
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise TradePassportFrozenProofError(
                "Trade Passport Stream lineage cannot be read safely"
            ) from exc

        verified: list[_ResolvedNarrative] = []
        reader = IntelligenceStreamReadModel(self.stream_ledger_path)
        for row in rows:
            narrative_identity = str(row[0])
            event_at_ms = _row_non_negative_int(row[1], "Stream narrative event time")
            try:
                detail = reader.read_message_detail(narrative_identity)
            except StreamReadModelError as exc:
                raise TradePassportFrozenProofError(str(exc)) from exc
            if detail is None:
                raise TradePassportFrozenProofError(
                    "Trade Passport Stream narrative disappeared during verified read"
                )
            narrative = _mapping(
                detail.get("narrative"),
                "Trade Passport Stream narrative",
            )
            if _optional_non_negative_int(narrative.get("event_at_ms")) != event_at_ms:
                raise TradePassportFrozenProofError(
                    "Trade Passport Stream narrative event time mismatch"
                )
            fact = _mapping(
                detail.get("fact_bundle"),
                "Trade Passport Stream fact bundle",
            )
            if (
                fact.get("forecast_identity") != forecast_identity
                or fact.get("proof_identity") != proof_identity
            ):
                continue

            visual = self._read_visual(narrative_identity)
            if visual is None or visual.get("status") != "ready":
                continue
            lineage = _mapping(
                visual.get("lineage"),
                "Trade Passport candidate visual lineage",
            )
            if (
                lineage.get("forecast_identity") == forecast_identity
                and lineage.get("proof_identity") == proof_identity
                and lineage.get("signal_freeze_identity") == signal_freeze_identity
            ):
                verified.append(
                    _ResolvedNarrative(
                        narrative_identity=narrative_identity,
                        event_at_ms=event_at_ms,
                    )
                )

        if not verified:
            return None
        latest_event_at_ms = max(item.event_at_ms for item in verified)
        latest = tuple(
            item for item in verified if item.event_at_ms == latest_event_at_ms
        )
        unique = tuple(
            dict.fromkeys(item.narrative_identity for item in latest)
        )
        if len(unique) != 1:
            raise TradePassportFrozenProofError(
                "Trade Passport exact lineage has competing narratives at the same event time"
            )
        _require_sha256(unique[0], "Trade Passport Stream narrative identity")
        return _ResolvedNarrative(
            narrative_identity=unique[0],
            event_at_ms=latest_event_at_ms,
        )

    def _read_visual(self, narrative_identity: str) -> dict[str, Any] | None:
        try:
            return IntelligenceStreamVisualProofReadModel(
                stream_ledger_path=self.stream_ledger_path,
                signal_ledger_path=self.signal_ledger_path,
                decision_evidence_path=self.decision_evidence_path,
            ).read_for_narrative(narrative_identity)
        except StreamVisualProofError as exc:
            raise TradePassportFrozenProofError(str(exc)) from exc


def _unavailable(label: str) -> TradePassportFrozenProofView:
    return TradePassportFrozenProofView(
        availability_label=label,
        frozen_market_story_label="Dondurulmuş Market Story kullanılamıyor",
        exact_evidence_label="Exact aile/source kanıtı kullanılamıyor",
        source_as_of_ms=None,
        issued_at_ms=None,
        chart_candle_count=0,
        annotation_count=0,
        family_proof_count=0,
        evidence_domain_count=0,
        current_data_substitution=False,
    )


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TradePassportFrozenProofError(f"{label} is invalid")
    return value


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TradePassportFrozenProofError("proof timestamp cannot be boolean")
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise TradePassportFrozenProofError("proof timestamp is invalid") from exc
    if parsed < 0:
        raise TradePassportFrozenProofError("proof timestamp cannot be negative")
    return parsed


def _row_non_negative_int(value: Any, label: str) -> int:
    parsed = _optional_non_negative_int(value)
    if parsed is None:
        raise TradePassportFrozenProofError(f"{label} is missing")
    return parsed


def _require_not_after(value: int, as_of_ms: int, label: str) -> None:
    if value > as_of_ms:
        raise TradePassportFrozenProofError(
            f"Trade Passport {label} is newer than lifecycle event"
        )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise TradePassportFrozenProofError(f"{label} must be SHA256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise TradePassportFrozenProofError(f"{label} must be SHA256") from exc
