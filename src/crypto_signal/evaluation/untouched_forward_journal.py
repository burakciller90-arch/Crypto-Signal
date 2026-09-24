from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_policy import (
    WC2UntouchedForwardPolicy,
)
from crypto_signal.forecast_stream import (
    ForecastResolution,
    ForecastResolutionState,
)
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.outcomes.models import EvidenceClass
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction
from crypto_signal.paper.shadow_cycle_runtime import PersistedShadowCycleResult
from crypto_signal.paper.transaction_tape import PaperTapeFill
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

WC2_COHORT_SCHEMA_VERSION = "wc2-untouched-forward-cohort-v1/1"
WC2_COHORT_ENGINE_VERSION = "wc2-cohort-journal-v1/1"
REAL_CAPITAL = 0

_META_TABLE = "wc2_cohort_meta"
_FORECAST_TABLE = "wc2_cohort_forecasts"
_INTENT_TABLE = "wc2_cohort_intents"
_EXECUTION_TABLE = "wc2_cohort_executions"
_RESOLUTION_TABLE = "wc2_cohort_resolutions"
_ALLOWED_TABLES = {
    _META_TABLE,
    _FORECAST_TABLE,
    _INTENT_TABLE,
    _EXECUTION_TABLE,
    _RESOLUTION_TABLE,
}


class WC2CohortAppendDisposition(StrEnum):
    INSERTED = "INSERTED"
    IDEMPOTENT = "IDEMPOTENT"


@dataclass(frozen=True, slots=True)
class WC2CohortForecast:
    cohort_forecast_identity: str
    policy_identity: str
    forecast_identity: str
    proof_identity: str
    signal_freeze_identity: str
    confluence_identity: str
    event_context_identity: str
    asset: str
    symbol: str
    timeframe: str
    regime: str
    issued_at_ms: int
    indexed_at_ms: int
    source_evidence_identities: tuple[str, ...]
    evidence_class: EvidenceClass = EvidenceClass.LIVE_UNTOUCHED_FORWARD
    schema_version: str = WC2_COHORT_SCHEMA_VERSION
    engine_version: str = WC2_COHORT_ENGINE_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.cohort_forecast_identity, "WC2 cohort forecast record"),
            (self.policy_identity, "WC2 cohort policy"),
            (self.forecast_identity, "WC2 R20 forecast"),
            (self.proof_identity, "WC2 decision proof"),
            (self.signal_freeze_identity, "WC2 signal freeze"),
            (self.confluence_identity, "WC2 confluence"),
            (self.event_context_identity, "WC2 event context"),
        ):
            _require_sha256(value, label)
        if self.evidence_class is not EvidenceClass.LIVE_UNTOUCHED_FORWARD:
            raise ValueError("WC2 cohort forecast must be LIVE_UNTOUCHED_FORWARD")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("WC2 cohort asset must be uppercase")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("WC2 cohort symbol must be uppercase")
        if not self.timeframe.strip() or not self.regime.strip():
            raise ValueError("WC2 cohort timeframe/regime must be non-empty")
        if min(self.issued_at_ms, self.indexed_at_ms) < 0:
            raise ValueError("WC2 cohort forecast times cannot be negative")
        if self.indexed_at_ms < self.issued_at_ms:
            raise ValueError("WC2 cohort index cannot predate forecast issuance")
        _validate_sources(self.source_evidence_identities)
        if self.schema_version != WC2_COHORT_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 cohort schema")
        if self.engine_version != WC2_COHORT_ENGINE_VERSION:
            raise ValueError("unsupported WC2 cohort engine")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 cohort forecast cannot grant authority")
        if self.cohort_forecast_identity != canonical_sha256(
            _forecast_payload(self)
        ):
            raise ValueError("WC2 cohort forecast identity mismatch")


@dataclass(frozen=True, slots=True)
class WC2CohortIntent:
    intent_link_identity: str
    policy_identity: str
    cohort_forecast_identity: str
    forecast_identity: str
    proof_identity: str
    persisted_cycle_identity: str
    manifest_identity: str
    shadow_cycle_identity: str
    preview_identity: str
    shadow_intent_record_identity: str
    paper_intent_identity: str
    vault_id: PaperVaultId
    action: PaperAction
    decided_at_ms: int
    previewed_at_ms: int
    indexed_at_ms: int
    schema_version: str = WC2_COHORT_SCHEMA_VERSION
    engine_version: str = WC2_COHORT_ENGINE_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.intent_link_identity, "WC2 intent link"),
            (self.policy_identity, "WC2 intent policy"),
            (self.cohort_forecast_identity, "WC2 intent cohort forecast"),
            (self.forecast_identity, "WC2 intent forecast"),
            (self.proof_identity, "WC2 intent proof"),
            (self.persisted_cycle_identity, "WC2 persisted cycle"),
            (self.manifest_identity, "WC2 cycle manifest"),
            (self.shadow_cycle_identity, "WC2 shadow cycle"),
            (self.preview_identity, "WC2 intent preview"),
            (self.shadow_intent_record_identity, "WC2 shadow intent record"),
            (self.paper_intent_identity, "WC2 paper intent"),
        ):
            _require_sha256(value, label)
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("WC2 intent requires canonical vault")
        if not isinstance(self.action, PaperAction):
            raise TypeError("WC2 intent requires canonical paper action")
        if min(self.decided_at_ms, self.previewed_at_ms, self.indexed_at_ms) < 0:
            raise ValueError("WC2 intent times cannot be negative")
        if not (
            self.decided_at_ms <= self.previewed_at_ms <= self.indexed_at_ms
        ):
            raise ValueError("WC2 intent chronology is invalid")
        if self.schema_version != WC2_COHORT_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 intent schema")
        if self.engine_version != WC2_COHORT_ENGINE_VERSION:
            raise ValueError("unsupported WC2 intent engine")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 intent cannot grant authority")
        if self.intent_link_identity != canonical_sha256(_intent_payload(self)):
            raise ValueError("WC2 intent link identity mismatch")


@dataclass(frozen=True, slots=True)
class WC2CohortExecution:
    execution_link_identity: str
    policy_identity: str
    cohort_forecast_identity: str
    intent_link_identity: str
    forecast_identity: str
    paper_intent_identity: str
    fill_identity: str
    cost_evidence_identity: str
    action: PaperAction
    filled_at_ms: int
    indexed_at_ms: int
    fee_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    execution_policy_version: str
    venue_reference: str
    mark_evidence_identity: str
    evidence_class: EvidenceClass = EvidenceClass.LIVE_UNTOUCHED_FORWARD
    schema_version: str = WC2_COHORT_SCHEMA_VERSION
    engine_version: str = WC2_COHORT_ENGINE_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.execution_link_identity, "WC2 execution link"),
            (self.policy_identity, "WC2 execution policy"),
            (self.cohort_forecast_identity, "WC2 execution cohort forecast"),
            (self.intent_link_identity, "WC2 execution intent link"),
            (self.forecast_identity, "WC2 execution forecast"),
            (self.paper_intent_identity, "WC2 execution paper intent"),
            (self.fill_identity, "WC2 execution fill"),
            (self.cost_evidence_identity, "WC2 cost evidence"),
            (self.mark_evidence_identity, "WC2 execution mark evidence"),
        ):
            _require_sha256(value, label)
        if self.evidence_class is not EvidenceClass.LIVE_UNTOUCHED_FORWARD:
            raise ValueError("WC2 execution must be LIVE_UNTOUCHED_FORWARD")
        if not isinstance(self.action, PaperAction):
            raise TypeError("WC2 execution requires canonical paper action")
        if self.action is PaperAction.HOLD_CASH:
            raise ValueError("HOLD_CASH cannot create WC2 execution evidence")
        if min(self.filled_at_ms, self.indexed_at_ms) < 0:
            raise ValueError("WC2 execution times cannot be negative")
        if self.indexed_at_ms < self.filled_at_ms:
            raise ValueError("WC2 execution index cannot predate fill")
        for cost in (self.fee_usdt, self.spread_usdt, self.slippage_usdt):
            if (
                not isinstance(cost, Decimal)
                or not cost.is_finite()
                or cost < 0
            ):
                raise ValueError(
                    "WC2 execution costs must be finite non-negative"
                )
        if not self.execution_policy_version.strip():
            raise ValueError("WC2 execution policy version missing")
        if not self.venue_reference.strip():
            raise ValueError("WC2 execution venue reference missing")
        if self.schema_version != WC2_COHORT_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 execution schema")
        if self.engine_version != WC2_COHORT_ENGINE_VERSION:
            raise ValueError("unsupported WC2 execution engine")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 execution cannot grant authority")
        if self.cost_evidence_identity != canonical_sha256(_cost_payload(self)):
            raise ValueError("WC2 execution cost identity mismatch")
        if self.execution_link_identity != canonical_sha256(
            _execution_payload(self)
        ):
            raise ValueError("WC2 execution link identity mismatch")


@dataclass(frozen=True, slots=True)
class WC2CohortResolution:
    resolution_link_identity: str
    policy_identity: str
    cohort_forecast_identity: str
    forecast_identity: str
    resolution_identity: str
    source_outcome_identity: str
    state: ForecastResolutionState
    evaluated_at_ms: int
    indexed_at_ms: int
    evidence_class: EvidenceClass = EvidenceClass.LIVE_UNTOUCHED_FORWARD
    schema_version: str = WC2_COHORT_SCHEMA_VERSION
    engine_version: str = WC2_COHORT_ENGINE_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.resolution_link_identity, "WC2 resolution link"),
            (self.policy_identity, "WC2 resolution policy"),
            (self.cohort_forecast_identity, "WC2 resolution cohort forecast"),
            (self.forecast_identity, "WC2 resolution forecast"),
            (self.resolution_identity, "WC2 R20 resolution"),
            (self.source_outcome_identity, "WC2 source outcome"),
        ):
            _require_sha256(value, label)
        if self.evidence_class is not EvidenceClass.LIVE_UNTOUCHED_FORWARD:
            raise ValueError("WC2 resolution must be LIVE_UNTOUCHED_FORWARD")
        if not isinstance(self.state, ForecastResolutionState):
            raise TypeError("WC2 resolution state must be canonical R20 state")
        if min(self.evaluated_at_ms, self.indexed_at_ms) < 0:
            raise ValueError("WC2 resolution times cannot be negative")
        if self.indexed_at_ms < self.evaluated_at_ms:
            raise ValueError("WC2 resolution index cannot predate evaluation")
        if self.schema_version != WC2_COHORT_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 resolution schema")
        if self.engine_version != WC2_COHORT_ENGINE_VERSION:
            raise ValueError("unsupported WC2 resolution engine")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 resolution cannot grant authority")
        if self.resolution_link_identity != canonical_sha256(
            _resolution_payload(self)
        ):
            raise ValueError("WC2 resolution link identity mismatch")


@dataclass(frozen=True, slots=True)
class WC2CohortJournalStatus:
    forecast_count: int
    intent_count: int
    execution_count: int
    resolution_count: int
    unresolved_forecast_count: int
    quick_check_ok: bool
    read_only_verified: bool
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if min(
            self.forecast_count,
            self.intent_count,
            self.execution_count,
            self.resolution_count,
            self.unresolved_forecast_count,
        ) < 0:
            raise ValueError("WC2 cohort journal counts cannot be negative")
        if self.resolution_count > self.forecast_count:
            raise ValueError("WC2 resolutions cannot exceed forecasts")
        if self.unresolved_forecast_count != (
            self.forecast_count - self.resolution_count
        ):
            raise ValueError("WC2 unresolved forecast count mismatch")
        if not self.quick_check_ok or not self.read_only_verified:
            raise ValueError("WC2 cohort journal must be read-only verified")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 cohort journal status cannot grant authority")


def build_wc2_cohort_forecast(
    *,
    policy: WC2UntouchedForwardPolicy,
    issuance: UnifiedDecisionIssuance,
    indexed_at_ms: int,
) -> WC2CohortForecast:
    forecast = issuance.forecast
    proof = issuance.proof
    if forecast.issued_at_ms < policy.collection_start_ms:
        raise ValueError("WC2 forecast predates preregistered collection start")
    if proof.forecast_identity != forecast.forecast_identity:
        raise ValueError("WC2 forecast/proof lineage mismatch")
    if indexed_at_ms < forecast.issued_at_ms:
        raise ValueError("WC2 cohort index cannot predate forecast issuance")

    sources = tuple(
        sorted(
            {
                *forecast.source_evidence_identities,
                proof.proof_identity,
                forecast.confluence_identity,
                forecast.event_context_identity,
            }
        )
    )
    values = {
        "policy_identity": policy.policy_identity,
        "forecast_identity": forecast.forecast_identity,
        "proof_identity": proof.proof_identity,
        "signal_freeze_identity": forecast.signal_freeze_identity,
        "confluence_identity": forecast.confluence_identity,
        "event_context_identity": forecast.event_context_identity,
        "asset": forecast.asset,
        "symbol": forecast.symbol,
        "timeframe": forecast.timeframe,
        "regime": issuance.confluence.regime,
        "issued_at_ms": forecast.issued_at_ms,
        "indexed_at_ms": indexed_at_ms,
        "source_evidence_identities": sources,
        "evidence_class": EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        "schema_version": WC2_COHORT_SCHEMA_VERSION,
        "engine_version": WC2_COHORT_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return WC2CohortForecast(
        cohort_forecast_identity=canonical_sha256(values),
        policy_identity=policy.policy_identity,
        forecast_identity=forecast.forecast_identity,
        proof_identity=proof.proof_identity,
        signal_freeze_identity=forecast.signal_freeze_identity,
        confluence_identity=forecast.confluence_identity,
        event_context_identity=forecast.event_context_identity,
        asset=forecast.asset,
        symbol=forecast.symbol,
        timeframe=forecast.timeframe,
        regime=issuance.confluence.regime,
        issued_at_ms=forecast.issued_at_ms,
        indexed_at_ms=indexed_at_ms,
        source_evidence_identities=sources,
    )


def build_wc2_cohort_intent(
    cohort_forecast: WC2CohortForecast,
    persisted_cycle: PersistedShadowCycleResult,
    *,
    indexed_at_ms: int,
) -> WC2CohortIntent:
    cycle = persisted_cycle.cycle
    manifest = persisted_cycle.manifest_append.record
    preview = cycle.preview
    if cycle.forecast_identity != cohort_forecast.forecast_identity:
        raise ValueError("WC2 intent shadow cycle/forecast mismatch")
    if cycle.proof_identity != cohort_forecast.proof_identity:
        raise ValueError("WC2 intent shadow cycle/proof mismatch")
    if manifest.forecast_identity != cohort_forecast.forecast_identity:
        raise ValueError("WC2 intent manifest/forecast mismatch")
    if manifest.proof_identity != cohort_forecast.proof_identity:
        raise ValueError("WC2 intent manifest/proof mismatch")
    if preview.preview_identity != manifest.preview_identity:
        raise ValueError("WC2 intent preview/manifest mismatch")
    if (
        cycle.journal_append.record.record_identity
        != manifest.journal_record_identity
    ):
        raise ValueError("WC2 intent journal/manifest mismatch")
    if indexed_at_ms < preview.previewed_at_ms:
        raise ValueError("WC2 intent index cannot predate preview")

    values = {
        "policy_identity": cohort_forecast.policy_identity,
        "cohort_forecast_identity": cohort_forecast.cohort_forecast_identity,
        "forecast_identity": cohort_forecast.forecast_identity,
        "proof_identity": cohort_forecast.proof_identity,
        "persisted_cycle_identity": persisted_cycle.persisted_cycle_identity,
        "manifest_identity": manifest.manifest_identity,
        "shadow_cycle_identity": manifest.cycle_identity,
        "preview_identity": preview.preview_identity,
        "shadow_intent_record_identity": manifest.journal_record_identity,
        "paper_intent_identity": preview.intent.intent_identity,
        "vault_id": manifest.vault_id,
        "action": preview.intent.action,
        "decided_at_ms": preview.intent.decided_at_ms,
        "previewed_at_ms": preview.previewed_at_ms,
        "indexed_at_ms": indexed_at_ms,
        "schema_version": WC2_COHORT_SCHEMA_VERSION,
        "engine_version": WC2_COHORT_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return WC2CohortIntent(
        intent_link_identity=canonical_sha256(values),
        policy_identity=cohort_forecast.policy_identity,
        cohort_forecast_identity=cohort_forecast.cohort_forecast_identity,
        forecast_identity=cohort_forecast.forecast_identity,
        proof_identity=cohort_forecast.proof_identity,
        persisted_cycle_identity=persisted_cycle.persisted_cycle_identity,
        manifest_identity=manifest.manifest_identity,
        shadow_cycle_identity=manifest.cycle_identity,
        preview_identity=preview.preview_identity,
        shadow_intent_record_identity=manifest.journal_record_identity,
        paper_intent_identity=preview.intent.intent_identity,
        vault_id=manifest.vault_id,
        action=preview.intent.action,
        decided_at_ms=preview.intent.decided_at_ms,
        previewed_at_ms=preview.previewed_at_ms,
        indexed_at_ms=indexed_at_ms,
    )


def build_wc2_cohort_execution(
    intent: WC2CohortIntent,
    fill: PaperTapeFill,
    *,
    indexed_at_ms: int,
) -> WC2CohortExecution:
    if intent.action is PaperAction.HOLD_CASH:
        raise ValueError("WC2 HOLD_CASH intent cannot receive execution")
    if fill.intent_identity != intent.paper_intent_identity:
        raise ValueError("WC2 fill does not bind exact paper intent")
    if fill.action is not intent.action:
        raise ValueError("WC2 fill action does not match frozen paper intent")
    if indexed_at_ms < fill.filled_at_ms:
        raise ValueError("WC2 execution index cannot predate fill")
    cost_values = {
        "fee_usdt": fill.fee_usdt,
        "fill_identity": fill.fill_identity,
        "spread_usdt": fill.spread_usdt,
        "slippage_usdt": fill.slippage_usdt,
        "execution_policy_version": fill.execution_policy_version,
        "venue_reference": fill.venue_reference,
    }
    cost_identity = canonical_sha256(cost_values)
    values = {
        "policy_identity": intent.policy_identity,
        "cohort_forecast_identity": intent.cohort_forecast_identity,
        "intent_link_identity": intent.intent_link_identity,
        "forecast_identity": intent.forecast_identity,
        "paper_intent_identity": intent.paper_intent_identity,
        "fill_identity": fill.fill_identity,
        "cost_evidence_identity": cost_identity,
        "action": fill.action,
        "filled_at_ms": fill.filled_at_ms,
        "indexed_at_ms": indexed_at_ms,
        "fee_usdt": fill.fee_usdt,
        "spread_usdt": fill.spread_usdt,
        "slippage_usdt": fill.slippage_usdt,
        "execution_policy_version": fill.execution_policy_version,
        "venue_reference": fill.venue_reference,
        "mark_evidence_identity": fill.mark_evidence_identity,
        "evidence_class": EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        "schema_version": WC2_COHORT_SCHEMA_VERSION,
        "engine_version": WC2_COHORT_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return WC2CohortExecution(
        execution_link_identity=canonical_sha256(values),
        policy_identity=intent.policy_identity,
        cohort_forecast_identity=intent.cohort_forecast_identity,
        intent_link_identity=intent.intent_link_identity,
        forecast_identity=intent.forecast_identity,
        paper_intent_identity=intent.paper_intent_identity,
        fill_identity=fill.fill_identity,
        cost_evidence_identity=cost_identity,
        action=fill.action,
        filled_at_ms=fill.filled_at_ms,
        indexed_at_ms=indexed_at_ms,
        fee_usdt=fill.fee_usdt,
        spread_usdt=fill.spread_usdt,
        slippage_usdt=fill.slippage_usdt,
        execution_policy_version=fill.execution_policy_version,
        venue_reference=fill.venue_reference,
        mark_evidence_identity=fill.mark_evidence_identity,
    )


def build_wc2_cohort_resolution(
    cohort_forecast: WC2CohortForecast,
    resolution: ForecastResolution,
    *,
    indexed_at_ms: int,
) -> WC2CohortResolution:
    if resolution.forecast_identity != cohort_forecast.forecast_identity:
        raise ValueError("WC2 resolution does not bind cohort forecast")
    if resolution.signal_freeze_identity != cohort_forecast.signal_freeze_identity:
        raise ValueError("WC2 resolution does not bind cohort signal")
    if resolution.evidence_class is not EvidenceClass.LIVE_UNTOUCHED_FORWARD:
        raise ValueError("WC2 resolution must be LIVE_UNTOUCHED_FORWARD")
    if resolution.evaluated_at_ms < cohort_forecast.issued_at_ms:
        raise ValueError("WC2 resolution cannot predate forecast issuance")
    if indexed_at_ms < resolution.evaluated_at_ms:
        raise ValueError("WC2 resolution index cannot predate evaluation")

    values = {
        "policy_identity": cohort_forecast.policy_identity,
        "cohort_forecast_identity": cohort_forecast.cohort_forecast_identity,
        "forecast_identity": cohort_forecast.forecast_identity,
        "resolution_identity": resolution.resolution_identity,
        "source_outcome_identity": resolution.source_outcome_identity,
        "state": resolution.state,
        "evaluated_at_ms": resolution.evaluated_at_ms,
        "indexed_at_ms": indexed_at_ms,
        "evidence_class": EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        "schema_version": WC2_COHORT_SCHEMA_VERSION,
        "engine_version": WC2_COHORT_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return WC2CohortResolution(
        resolution_link_identity=canonical_sha256(values),
        policy_identity=cohort_forecast.policy_identity,
        cohort_forecast_identity=cohort_forecast.cohort_forecast_identity,
        forecast_identity=cohort_forecast.forecast_identity,
        resolution_identity=resolution.resolution_identity,
        source_outcome_identity=resolution.source_outcome_identity,
        state=resolution.state,
        evaluated_at_ms=resolution.evaluated_at_ms,
        indexed_at_ms=indexed_at_ms,
    )


class WC2CohortJournal:
    """Append-only index over accepted immutable R20/R22/R25 evidence."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            existing = {
                str(row[0])
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
                ).fetchall()
            }
            unexpected = existing - _ALLOWED_TABLES
            if unexpected:
                raise ValueError(
                    "WC2 cohort journal refuses database with non-WC2 tables"
                )
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )"""
            )
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_FORECAST_TABLE} (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cohort_forecast_identity TEXT UNIQUE NOT NULL,
                    policy_identity TEXT NOT NULL,
                    forecast_identity TEXT UNIQUE NOT NULL,
                    proof_identity TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    issued_at_ms INTEGER NOT NULL,
                    indexed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_INTENT_TABLE} (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_link_identity TEXT UNIQUE NOT NULL,
                    cohort_forecast_identity TEXT NOT NULL,
                    policy_identity TEXT NOT NULL,
                    forecast_identity TEXT NOT NULL,
                    paper_intent_identity TEXT UNIQUE NOT NULL,
                    vault_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    indexed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(forecast_identity, vault_id),
                    FOREIGN KEY (cohort_forecast_identity)
                        REFERENCES {_FORECAST_TABLE}(cohort_forecast_identity)
                )"""
            )
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_EXECUTION_TABLE} (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_link_identity TEXT UNIQUE NOT NULL,
                    cohort_forecast_identity TEXT NOT NULL,
                    intent_link_identity TEXT NOT NULL,
                    forecast_identity TEXT NOT NULL,
                    fill_identity TEXT UNIQUE NOT NULL,
                    indexed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY (cohort_forecast_identity)
                        REFERENCES {_FORECAST_TABLE}(cohort_forecast_identity),
                    FOREIGN KEY (intent_link_identity)
                        REFERENCES {_INTENT_TABLE}(intent_link_identity)
                )"""
            )
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_RESOLUTION_TABLE} (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resolution_link_identity TEXT UNIQUE NOT NULL,
                    cohort_forecast_identity TEXT UNIQUE NOT NULL,
                    forecast_identity TEXT UNIQUE NOT NULL,
                    resolution_identity TEXT UNIQUE NOT NULL,
                    evaluated_at_ms INTEGER NOT NULL,
                    indexed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY (cohort_forecast_identity)
                        REFERENCES {_FORECAST_TABLE}(cohort_forecast_identity)
                )"""
            )
            row = db.execute(
                f"SELECT value FROM {_META_TABLE} WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    f"INSERT INTO {_META_TABLE}(key, value) VALUES (?, ?)",
                    ("schema_version", WC2_COHORT_SCHEMA_VERSION),
                )
            elif str(row[0]) != WC2_COHORT_SCHEMA_VERSION:
                raise ValueError("WC2 cohort journal schema mismatch")

            for table in (
                _META_TABLE,
                _FORECAST_TABLE,
                _INTENT_TABLE,
                _EXECUTION_TABLE,
                _RESOLUTION_TABLE,
            ):
                for action in ("UPDATE", "DELETE"):
                    db.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{action.lower()}
                        BEFORE {action} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'immutable WC2 untouched-forward cohort journal'
                            );
                        END"""
                    )

    def append_forecast(
        self,
        record: WC2CohortForecast,
    ) -> WC2CohortAppendDisposition:
        self.initialize()
        payload = canonical_json(_forecast_payload(record))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            existing = db.execute(
                f"""SELECT cohort_forecast_identity, payload_json
                FROM {_FORECAST_TABLE}
                WHERE forecast_identity=? OR cohort_forecast_identity=?""",
                (
                    record.forecast_identity,
                    record.cohort_forecast_identity,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == record.cohort_forecast_identity
                    and str(existing[1]) == payload
                ):
                    return WC2CohortAppendDisposition.IDEMPOTENT
                raise ValueError("WC2 cohort forecast conflict")
            db.execute(
                f"""INSERT INTO {_FORECAST_TABLE}(
                    cohort_forecast_identity,
                    policy_identity,
                    forecast_identity,
                    proof_identity,
                    symbol,
                    regime,
                    issued_at_ms,
                    indexed_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.cohort_forecast_identity,
                    record.policy_identity,
                    record.forecast_identity,
                    record.proof_identity,
                    record.symbol,
                    record.regime,
                    record.issued_at_ms,
                    record.indexed_at_ms,
                    payload,
                ),
            )
        return WC2CohortAppendDisposition.INSERTED

    def append_intent(
        self,
        record: WC2CohortIntent,
    ) -> WC2CohortAppendDisposition:
        self.initialize()
        payload = canonical_json(_intent_payload(record))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            forecast = db.execute(
                f"""SELECT policy_identity, forecast_identity, proof_identity
                FROM {_FORECAST_TABLE}
                WHERE cohort_forecast_identity=?""",
                (record.cohort_forecast_identity,),
            ).fetchone()
            if forecast is None:
                raise ValueError("WC2 intent references unknown cohort forecast")
            if (
                str(forecast[0]) != record.policy_identity
                or str(forecast[1]) != record.forecast_identity
                or str(forecast[2]) != record.proof_identity
            ):
                raise ValueError("WC2 intent/forecast lineage conflict")

            existing = db.execute(
                f"""SELECT intent_link_identity, payload_json
                FROM {_INTENT_TABLE}
                WHERE paper_intent_identity=?
                   OR intent_link_identity=?
                   OR (forecast_identity=? AND vault_id=?)""",
                (
                    record.paper_intent_identity,
                    record.intent_link_identity,
                    record.forecast_identity,
                    record.vault_id.value,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == record.intent_link_identity
                    and str(existing[1]) == payload
                ):
                    return WC2CohortAppendDisposition.IDEMPOTENT
                raise ValueError("WC2 cohort intent conflict")
            db.execute(
                f"""INSERT INTO {_INTENT_TABLE}(
                    intent_link_identity,
                    cohort_forecast_identity,
                    policy_identity,
                    forecast_identity,
                    paper_intent_identity,
                    vault_id,
                    action,
                    indexed_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.intent_link_identity,
                    record.cohort_forecast_identity,
                    record.policy_identity,
                    record.forecast_identity,
                    record.paper_intent_identity,
                    record.vault_id.value,
                    record.action.value,
                    record.indexed_at_ms,
                    payload,
                ),
            )
        return WC2CohortAppendDisposition.INSERTED

    def append_execution(
        self,
        record: WC2CohortExecution,
    ) -> WC2CohortAppendDisposition:
        self.initialize()
        payload = canonical_json(_execution_payload(record))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            intent = db.execute(
                f"""SELECT policy_identity, forecast_identity,
                           paper_intent_identity, action
                FROM {_INTENT_TABLE}
                WHERE intent_link_identity=?""",
                (record.intent_link_identity,),
            ).fetchone()
            if intent is None:
                raise ValueError("WC2 execution references unknown intent")
            if (
                str(intent[0]) != record.policy_identity
                or str(intent[1]) != record.forecast_identity
                or str(intent[2]) != record.paper_intent_identity
                or str(intent[3]) != record.action.value
            ):
                raise ValueError("WC2 execution/intent lineage conflict")

            existing = db.execute(
                f"""SELECT execution_link_identity, payload_json
                FROM {_EXECUTION_TABLE}
                WHERE fill_identity=? OR execution_link_identity=?""",
                (record.fill_identity, record.execution_link_identity),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == record.execution_link_identity
                    and str(existing[1]) == payload
                ):
                    return WC2CohortAppendDisposition.IDEMPOTENT
                raise ValueError("WC2 cohort execution conflict")
            db.execute(
                f"""INSERT INTO {_EXECUTION_TABLE}(
                    execution_link_identity,
                    cohort_forecast_identity,
                    intent_link_identity,
                    forecast_identity,
                    fill_identity,
                    indexed_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.execution_link_identity,
                    record.cohort_forecast_identity,
                    record.intent_link_identity,
                    record.forecast_identity,
                    record.fill_identity,
                    record.indexed_at_ms,
                    payload,
                ),
            )
        return WC2CohortAppendDisposition.INSERTED

    def append_resolution(
        self,
        record: WC2CohortResolution,
    ) -> WC2CohortAppendDisposition:
        self.initialize()
        payload = canonical_json(_resolution_payload(record))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            forecast = db.execute(
                f"""SELECT policy_identity, forecast_identity, issued_at_ms
                FROM {_FORECAST_TABLE}
                WHERE cohort_forecast_identity=?""",
                (record.cohort_forecast_identity,),
            ).fetchone()
            if forecast is None:
                raise ValueError("WC2 resolution references unknown cohort forecast")
            if (
                str(forecast[0]) != record.policy_identity
                or str(forecast[1]) != record.forecast_identity
            ):
                raise ValueError("WC2 resolution/forecast lineage conflict")
            if record.evaluated_at_ms < int(forecast[2]):
                raise ValueError("WC2 resolution predates persisted forecast")

            existing = db.execute(
                f"""SELECT resolution_link_identity, payload_json
                FROM {_RESOLUTION_TABLE}
                WHERE cohort_forecast_identity=?
                   OR forecast_identity=?
                   OR resolution_identity=?
                   OR resolution_link_identity=?""",
                (
                    record.cohort_forecast_identity,
                    record.forecast_identity,
                    record.resolution_identity,
                    record.resolution_link_identity,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == record.resolution_link_identity
                    and str(existing[1]) == payload
                ):
                    return WC2CohortAppendDisposition.IDEMPOTENT
                raise ValueError("WC2 cohort resolution conflict")
            db.execute(
                f"""INSERT INTO {_RESOLUTION_TABLE}(
                    resolution_link_identity,
                    cohort_forecast_identity,
                    forecast_identity,
                    resolution_identity,
                    evaluated_at_ms,
                    indexed_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.resolution_link_identity,
                    record.cohort_forecast_identity,
                    record.forecast_identity,
                    record.resolution_identity,
                    record.evaluated_at_ms,
                    record.indexed_at_ms,
                    payload,
                ),
            )
        return WC2CohortAppendDisposition.INSERTED

    def verify_read_only(self) -> WC2CohortJournalStatus:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA foreign_keys=ON")
            quick = db.execute("PRAGMA quick_check").fetchone()
            if quick is None or str(quick[0]).lower() != "ok":
                raise ValueError("WC2 cohort journal quick_check failed")
            tables = {
                str(row[0])
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
                ).fetchall()
            }
            if tables != _ALLOWED_TABLES:
                raise ValueError("WC2 cohort journal table boundary mismatch")
            meta = db.execute(
                f"SELECT value FROM {_META_TABLE} WHERE key='schema_version'"
            ).fetchone()
            if meta is None or str(meta[0]) != WC2_COHORT_SCHEMA_VERSION:
                raise ValueError("WC2 cohort journal schema mismatch")
            forecast_count = _table_count(db, _FORECAST_TABLE)
            intent_count = _table_count(db, _INTENT_TABLE)
            execution_count = _table_count(db, _EXECUTION_TABLE)
            resolution_count = _table_count(db, _RESOLUTION_TABLE)

        return WC2CohortJournalStatus(
            forecast_count=forecast_count,
            intent_count=intent_count,
            execution_count=execution_count,
            resolution_count=resolution_count,
            unresolved_forecast_count=forecast_count - resolution_count,
            quick_check_ok=True,
            read_only_verified=True,
        )


def _forecast_payload(record: WC2CohortForecast) -> dict[str, object]:
    return {
        "policy_identity": record.policy_identity,
        "forecast_identity": record.forecast_identity,
        "proof_identity": record.proof_identity,
        "signal_freeze_identity": record.signal_freeze_identity,
        "confluence_identity": record.confluence_identity,
        "event_context_identity": record.event_context_identity,
        "asset": record.asset,
        "symbol": record.symbol,
        "timeframe": record.timeframe,
        "regime": record.regime,
        "issued_at_ms": record.issued_at_ms,
        "indexed_at_ms": record.indexed_at_ms,
        "source_evidence_identities": record.source_evidence_identities,
        "evidence_class": record.evidence_class,
        "schema_version": record.schema_version,
        "engine_version": record.engine_version,
        "production_authority": record.production_authority,
        "real_capital": record.real_capital,
    }


def _intent_payload(record: WC2CohortIntent) -> dict[str, object]:
    return {
        "policy_identity": record.policy_identity,
        "cohort_forecast_identity": record.cohort_forecast_identity,
        "forecast_identity": record.forecast_identity,
        "proof_identity": record.proof_identity,
        "persisted_cycle_identity": record.persisted_cycle_identity,
        "manifest_identity": record.manifest_identity,
        "shadow_cycle_identity": record.shadow_cycle_identity,
        "preview_identity": record.preview_identity,
        "shadow_intent_record_identity": record.shadow_intent_record_identity,
        "paper_intent_identity": record.paper_intent_identity,
        "vault_id": record.vault_id,
        "action": record.action,
        "decided_at_ms": record.decided_at_ms,
        "previewed_at_ms": record.previewed_at_ms,
        "indexed_at_ms": record.indexed_at_ms,
        "schema_version": record.schema_version,
        "engine_version": record.engine_version,
        "production_authority": record.production_authority,
        "real_capital": record.real_capital,
    }


def _cost_payload(record: WC2CohortExecution) -> dict[str, object]:
    return {
        "fee_usdt": record.fee_usdt,
        "fill_identity": record.fill_identity,
        "spread_usdt": record.spread_usdt,
        "slippage_usdt": record.slippage_usdt,
        "execution_policy_version": record.execution_policy_version,
        "venue_reference": record.venue_reference,
    }


def _execution_payload(record: WC2CohortExecution) -> dict[str, object]:
    return {
        "policy_identity": record.policy_identity,
        "cohort_forecast_identity": record.cohort_forecast_identity,
        "intent_link_identity": record.intent_link_identity,
        "forecast_identity": record.forecast_identity,
        "paper_intent_identity": record.paper_intent_identity,
        "fill_identity": record.fill_identity,
        "cost_evidence_identity": record.cost_evidence_identity,
        "action": record.action,
        "filled_at_ms": record.filled_at_ms,
        "indexed_at_ms": record.indexed_at_ms,
        "fee_usdt": record.fee_usdt,
        "spread_usdt": record.spread_usdt,
        "slippage_usdt": record.slippage_usdt,
        "execution_policy_version": record.execution_policy_version,
        "venue_reference": record.venue_reference,
        "mark_evidence_identity": record.mark_evidence_identity,
        "evidence_class": record.evidence_class,
        "schema_version": record.schema_version,
        "engine_version": record.engine_version,
        "production_authority": record.production_authority,
        "real_capital": record.real_capital,
    }


def _resolution_payload(record: WC2CohortResolution) -> dict[str, object]:
    return {
        "policy_identity": record.policy_identity,
        "cohort_forecast_identity": record.cohort_forecast_identity,
        "forecast_identity": record.forecast_identity,
        "resolution_identity": record.resolution_identity,
        "source_outcome_identity": record.source_outcome_identity,
        "state": record.state,
        "evaluated_at_ms": record.evaluated_at_ms,
        "indexed_at_ms": record.indexed_at_ms,
        "evidence_class": record.evidence_class,
        "schema_version": record.schema_version,
        "engine_version": record.engine_version,
        "production_authority": record.production_authority,
        "real_capital": record.real_capital,
    }


def _validate_sources(values: tuple[str, ...]) -> None:
    if values != tuple(sorted(set(values))) or not values:
        raise ValueError("WC2 cohort source evidence must be non-empty canonical")
    for identity in values:
        _require_sha256(identity, "WC2 cohort source evidence")


def _table_count(db: sqlite3.Connection, table: str) -> int:
    row = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if row is None:
        raise ValueError(f"WC2 cohort count failed: {table}")
    return int(row[0])


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
