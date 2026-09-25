"""S11 canonical per-vault capital decisions for Epoch 2.

These records persist the Smart Capital Allocator decision that explains whether
a vault may participate or must remain in cash. They do not mutate accounting,
place orders, or grant production authority. REAL_CAPITAL remains 0.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from urllib.parse import quote

from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerState
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.epoch2_accounting import (
    Epoch2ActivationRecord,
    Epoch2CanonicalLedger,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction
from crypto_signal.paper.smart_capital_allocator import (
    SmartCapitalAllocationAssessment,
    SmartCapitalCandidate,
    VaultEligibilityState,
)
from crypto_signal.paper.transaction_tape import PaperTapeIntent, build_tape_intent
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape

S11_VAULT_DECISION_SCHEMA_VERSION = "stream-s11-vault-decision-v1/1"
S11_VAULT_DECISION_ENGINE_VERSION = "stream-s11-vault-decision-engine-v1/1"
REAL_CAPITAL = 0


class CanonicalVaultDecisionDisposition(StrEnum):
    ELIGIBLE = "eligible"
    HOLD = "hold"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CanonicalVaultDecisionRecord:
    decision_identity: str
    activation_identity: str
    allocator_assessment_identity: str
    allocator_candidate_identity: str
    vault_id: PaperVaultId
    disposition: CanonicalVaultDecisionDisposition
    asset: str
    source_timeframe: str
    candidate_as_of_ms: int
    assessed_at_ms: int
    decided_at_ms: int
    starting_budget_usdt: Decimal
    reason_codes: tuple[str, ...]
    event_risk_identity: str
    event_risk_state: CircuitBreakerState
    confluence_identity: str | None
    tactical_evidence_identity: str | None
    tactical_timeframe: str | None
    recovery_evidence_identity: str | None
    source_evidence_identities: tuple[str, ...]
    schema_version: str = S11_VAULT_DECISION_SCHEMA_VERSION
    engine_version: str = S11_VAULT_DECISION_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.decision_identity, "S11 vault decision"),
            (self.activation_identity, "S11 Epoch2 activation"),
            (self.allocator_assessment_identity, "S11 allocator assessment"),
            (self.allocator_candidate_identity, "S11 allocator candidate"),
            (self.event_risk_identity, "S11 Event Risk"),
        ):
            _require_sha256(identity, label)
        for optional_identity, optional_label in (
            (self.confluence_identity, "S11 confluence"),
            (self.tactical_evidence_identity, "S11 tactical evidence"),
            (self.recovery_evidence_identity, "S11 recovery evidence"),
        ):
            if optional_identity is not None:
                _require_sha256(optional_identity, optional_label)
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("S11 vault decision requires canonical vault")
        if not isinstance(self.disposition, CanonicalVaultDecisionDisposition):
            raise TypeError("S11 vault decision requires canonical disposition")
        if not isinstance(self.event_risk_state, CircuitBreakerState):
            raise TypeError("S11 vault decision requires canonical Event Risk state")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("S11 vault decision asset must be uppercase")
        if not self.source_timeframe.strip():
            raise ValueError("S11 vault decision source timeframe must be non-empty")
        if min(self.candidate_as_of_ms, self.assessed_at_ms, self.decided_at_ms) < 0:
            raise ValueError("S11 vault decision timestamps must be non-negative")
        if not (
            self.candidate_as_of_ms <= self.assessed_at_ms <= self.decided_at_ms
        ):
            raise ValueError("S11 vault decision chronology is invalid")
        if (
            not isinstance(self.starting_budget_usdt, Decimal)
            or not self.starting_budget_usdt.is_finite()
            or self.starting_budget_usdt <= 0
        ):
            raise ValueError("S11 vault decision budget must be finite and positive")
        if not self.reason_codes or self.reason_codes != tuple(
            sorted(set(self.reason_codes))
        ):
            raise ValueError("S11 vault decision reasons must be sorted unique")
        _identity_tuple(self.source_evidence_identities, "S11 vault decision source")
        required_sources = {
            self.event_risk_identity,
            self.allocator_assessment_identity,
            self.allocator_candidate_identity,
        }
        for optional in (
            self.confluence_identity,
            self.tactical_evidence_identity,
            self.recovery_evidence_identity,
        ):
            if optional is not None:
                required_sources.add(optional)
        if not required_sources.issubset(set(self.source_evidence_identities)):
            raise ValueError("S11 vault decision lost exact evidence lineage")
        if self.vault_id is PaperVaultId.TACTICAL:
            if self.tactical_evidence_identity is None:
                raise ValueError("S11 Tactical decision requires tactical evidence")
            if self.tactical_timeframe not in {"1m", "5m"}:
                raise ValueError("S11 Tactical decision requires 1m/5m timeframe")
        elif self.tactical_timeframe is not None:
            raise ValueError("S11 non-Tactical decision cannot carry tactical timeframe")
        if (
            self.vault_id is PaperVaultId.OPPORTUNITY_RESERVE
            and self.recovery_evidence_identity is None
        ):
            raise ValueError("S11 Opportunity decision requires recovery evidence")
        if (
            self.disposition is CanonicalVaultDecisionDisposition.BLOCKED
            and self.event_risk_state is CircuitBreakerState.CLEAR
        ):
            raise ValueError("S11 blocked decision requires non-clear Event Risk")
        if (
            self.disposition is CanonicalVaultDecisionDisposition.ELIGIBLE
            and self.event_risk_state is not CircuitBreakerState.CLEAR
        ):
            raise ValueError("S11 eligible decision requires clear Event Risk")
        if (
            not self.read_only
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("S11 vault decision authority boundary mismatch")
        if self.schema_version != S11_VAULT_DECISION_SCHEMA_VERSION:
            raise ValueError("unsupported S11 vault decision schema")
        if self.engine_version != S11_VAULT_DECISION_ENGINE_VERSION:
            raise ValueError("unsupported S11 vault decision engine")
        if self.decision_identity != canonical_sha256(_decision_payload(self)):
            raise ValueError("S11 vault decision identity mismatch")


@dataclass(frozen=True, slots=True)
class CanonicalHoldCommitResult:
    vault_decision_identity: str
    r22_intent_identity: str
    disposition: CanonicalVaultDecisionDisposition
    decision_inserted: bool
    intent_inserted: bool
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL


class CanonicalVaultDecisionLedger:
    """Append-only allocator-decision evidence stored in the Epoch 2 database."""

    def __init__(self, epoch2_path: Path) -> None:
        self.epoch2_path = epoch2_path

    def initialize(self) -> None:
        Epoch2CanonicalLedger(self.epoch2_path).initialize()
        with closing(sqlite3.connect(self.epoch2_path)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS s11_vault_decisions (
                    decision_identity TEXT PRIMARY KEY,
                    activation_identity TEXT NOT NULL,
                    allocator_assessment_identity TEXT NOT NULL,
                    allocator_candidate_identity TEXT NOT NULL,
                    vault_id TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(allocator_assessment_identity, vault_id)
                )
                """
            )
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                    s11_vault_decisions_immutable_{operation.lower()}
                    BEFORE {operation} ON s11_vault_decisions
                    BEGIN
                        SELECT RAISE(ABORT, 'immutable S11 vault decision ledger');
                    END
                    """
                )

    def append(self, record: CanonicalVaultDecisionRecord) -> bool:
        self.initialize()
        activation = Epoch2CanonicalLedger(self.epoch2_path).read_activation()
        if activation is None:
            raise ValueError("S11 vault decision requires Epoch2 activation")
        if record.activation_identity != activation.activation_identity:
            raise ValueError("S11 vault decision activation mismatch")
        payload = canonical_json(record)
        with closing(sqlite3.connect(self.epoch2_path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT decision_identity, payload_json
                FROM s11_vault_decisions
                WHERE decision_identity = ?
                   OR (
                     allocator_assessment_identity = ?
                     AND vault_id = ?
                   )
                LIMIT 1
                """,
                (
                    record.decision_identity,
                    record.allocator_assessment_identity,
                    record.vault_id.value,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == record.decision_identity
                    and str(existing[1]) == payload
                ):
                    return False
                raise ValueError("immutable S11 vault decision identity conflict")
            latest = connection.execute(
                """
                SELECT event_at_ms, decision_identity
                FROM s11_vault_decisions
                WHERE vault_id = ?
                ORDER BY event_at_ms DESC, decision_identity DESC
                LIMIT 1
                """,
                (record.vault_id.value,),
            ).fetchone()
            if latest is not None and record.decided_at_ms <= int(str(latest[0])):
                raise ValueError("S11 vault decisions cannot backfill or fork time")
            connection.execute(
                """
                INSERT INTO s11_vault_decisions (
                    decision_identity,
                    activation_identity,
                    allocator_assessment_identity,
                    allocator_candidate_identity,
                    vault_id,
                    disposition,
                    event_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.decision_identity,
                    record.activation_identity,
                    record.allocator_assessment_identity,
                    record.allocator_candidate_identity,
                    record.vault_id.value,
                    record.disposition.value,
                    record.decided_at_ms,
                    payload,
                ),
            )
            connection.commit()
        return True

    def read(self, decision_identity: str) -> dict[str, object] | None:
        _require_sha256(decision_identity, "S11 vault decision lookup")
        if not self.epoch2_path.is_file():
            return None
        uri = f"file:{quote(str(self.epoch2_path.resolve()), safe='/')}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            row = connection.execute(
                """
                SELECT event_at_ms, payload_json
                FROM s11_vault_decisions
                WHERE decision_identity = ?
                """,
                (decision_identity,),
            ).fetchone()
        if row is None:
            return None
        raw = json.loads(str(row[1]))
        if not isinstance(raw, dict):
            raise TypeError("S11 stored vault decision must decode to object")
        if raw.get("decision_identity") != decision_identity:
            raise ValueError("S11 stored vault decision identity column mismatch")
        if raw.get("decided_at_ms") != int(str(row[0])):
            raise ValueError("S11 stored vault decision time column mismatch")
        payload = dict(raw)
        payload.pop("decision_identity", None)
        if canonical_sha256(payload) != decision_identity:
            raise ValueError("S11 stored vault decision canonical identity mismatch")
        if raw.get("real_capital") != REAL_CAPITAL:
            raise ValueError("S11 stored vault decision REAL_CAPITAL mismatch")
        if raw.get("production_authority") is not False:
            raise ValueError("S11 stored vault decision authority mismatch")
        return raw


def build_vault_decision(
    activation: Epoch2ActivationRecord,
    candidate: SmartCapitalCandidate,
    assessment: SmartCapitalAllocationAssessment,
    *,
    vault_id: PaperVaultId,
    decided_at_ms: int,
) -> CanonicalVaultDecisionRecord:
    if assessment.candidate_identity != candidate.candidate_identity:
        raise ValueError("S11 vault decision assessment/candidate mismatch")
    if decided_at_ms < max(assessment.assessed_at_ms, activation.activated_at_ms):
        raise ValueError("S11 vault decision predates accepted source truth")
    envelopes = tuple(item for item in assessment.vaults if item.vault_id is vault_id)
    if len(envelopes) != 1:
        raise ValueError("S11 vault decision lacks exact allocator envelope")
    envelope = envelopes[0]
    if envelope.candidate_identity != candidate.candidate_identity:
        raise ValueError("S11 vault decision envelope candidate mismatch")
    if envelope.event_risk_identity != candidate.event_risk.evidence_identity:
        raise ValueError("S11 vault decision Event Risk lineage mismatch")

    if envelope.eligibility_state is VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE:
        disposition = CanonicalVaultDecisionDisposition.ELIGIBLE
    elif candidate.event_risk.state is not CircuitBreakerState.CLEAR:
        disposition = CanonicalVaultDecisionDisposition.BLOCKED
    else:
        disposition = CanonicalVaultDecisionDisposition.HOLD

    tactical_timeframe = (
        candidate.tactical_microstructure.timeframe
        if vault_id is PaperVaultId.TACTICAL
        and candidate.tactical_microstructure is not None
        else None
    )
    source_timeframe = (
        tactical_timeframe
        if tactical_timeframe is not None
        else candidate.confluence.timeframe
        if candidate.confluence is not None
        else "event"
    )
    source_ids = {
        assessment.assessment_identity,
        candidate.candidate_identity,
        *candidate.source_evidence_identities,
    }
    payload = {
        "activation_identity": activation.activation_identity,
        "allocator_assessment_identity": assessment.assessment_identity,
        "allocator_candidate_identity": candidate.candidate_identity,
        "asset": candidate.asset,
        "assessed_at_ms": assessment.assessed_at_ms,
        "candidate_as_of_ms": candidate.as_of_ms,
        "confluence_identity": envelope.confluence_identity,
        "decided_at_ms": decided_at_ms,
        "disposition": disposition,
        "engine_version": S11_VAULT_DECISION_ENGINE_VERSION,
        "event_risk_identity": envelope.event_risk_identity,
        "event_risk_state": candidate.event_risk.state,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "reason_codes": envelope.reason_codes,
        "recovery_evidence_identity": envelope.recovery_evidence_identity,
        "schema_version": S11_VAULT_DECISION_SCHEMA_VERSION,
        "source_evidence_identities": tuple(sorted(source_ids)),
        "source_timeframe": source_timeframe,
        "starting_budget_usdt": envelope.starting_budget_usdt,
        "tactical_evidence_identity": envelope.tactical_evidence_identity,
        "tactical_timeframe": tactical_timeframe,
        "vault_id": vault_id,
    }
    return CanonicalVaultDecisionRecord(
        decision_identity=canonical_sha256(payload),
        activation_identity=activation.activation_identity,
        allocator_assessment_identity=assessment.assessment_identity,
        allocator_candidate_identity=candidate.candidate_identity,
        vault_id=vault_id,
        disposition=disposition,
        asset=candidate.asset,
        source_timeframe=source_timeframe,
        candidate_as_of_ms=candidate.as_of_ms,
        assessed_at_ms=assessment.assessed_at_ms,
        decided_at_ms=decided_at_ms,
        starting_budget_usdt=envelope.starting_budget_usdt,
        reason_codes=envelope.reason_codes,
        event_risk_identity=envelope.event_risk_identity,
        event_risk_state=candidate.event_risk.state,
        confluence_identity=envelope.confluence_identity,
        tactical_evidence_identity=envelope.tactical_evidence_identity,
        tactical_timeframe=tactical_timeframe,
        recovery_evidence_identity=envelope.recovery_evidence_identity,
        source_evidence_identities=tuple(sorted(source_ids)),
    )


def commit_canonical_hold(
    *,
    epoch2_path: Path,
    decision: CanonicalVaultDecisionRecord,
) -> CanonicalHoldCommitResult:
    """Persist one allocator HOLD/BLOCK decision and its R22 HOLD_CASH intent."""
    if decision.disposition is CanonicalVaultDecisionDisposition.ELIGIBLE:
        raise ValueError("S11 eligible vault cannot be committed as HOLD_CASH")
    ledger = CanonicalVaultDecisionLedger(epoch2_path)
    decision_inserted = ledger.append(decision)

    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    if decision.activation_identity != state.activation.activation_identity:
        raise ValueError("S11 HOLD decision activation mismatch")
    tape = R22Epoch2AtomicTape(epoch2_path)
    previous_intent, _ = tape.read_latest_chain_identities(decision.vault_id)
    reason_codes = tuple(
        sorted(
            {
                *decision.reason_codes,
                f"capital_{decision.disposition.value}",
            }
        )
    )
    intent: PaperTapeIntent = build_tape_intent(
        state.activation,
        vault_id=decision.vault_id,
        action=PaperAction.HOLD_CASH,
        decided_at_ms=decision.decided_at_ms,
        reason_codes=reason_codes,
        hold_policy_identity=decision.decision_identity,
        previous_intent_identity=previous_intent,
    )
    intent_inserted = tape.append_hold_decision(intent)
    return CanonicalHoldCommitResult(
        vault_decision_identity=decision.decision_identity,
        r22_intent_identity=intent.intent_identity,
        disposition=decision.disposition,
        decision_inserted=decision_inserted,
        intent_inserted=intent_inserted,
    )


def _decision_payload(value: CanonicalVaultDecisionRecord) -> dict[str, object]:
    return {
        "activation_identity": value.activation_identity,
        "allocator_assessment_identity": value.allocator_assessment_identity,
        "allocator_candidate_identity": value.allocator_candidate_identity,
        "asset": value.asset,
        "assessed_at_ms": value.assessed_at_ms,
        "candidate_as_of_ms": value.candidate_as_of_ms,
        "confluence_identity": value.confluence_identity,
        "decided_at_ms": value.decided_at_ms,
        "disposition": value.disposition,
        "engine_version": value.engine_version,
        "event_risk_identity": value.event_risk_identity,
        "event_risk_state": value.event_risk_state,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "reason_codes": value.reason_codes,
        "recovery_evidence_identity": value.recovery_evidence_identity,
        "schema_version": value.schema_version,
        "source_evidence_identities": value.source_evidence_identities,
        "source_timeframe": value.source_timeframe,
        "starting_budget_usdt": value.starting_budget_usdt,
        "tactical_evidence_identity": value.tactical_evidence_identity,
        "tactical_timeframe": value.tactical_timeframe,
        "vault_id": value.vault_id,
    }


def _identity_tuple(values: tuple[str, ...], label: str) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise ValueError(f"{label} identities must be non-empty sorted unique")
    for identity in values:
        _require_sha256(identity, label)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
