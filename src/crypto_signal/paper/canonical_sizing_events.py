"""S11 immutable canonical sizing events inside the Epoch 2 paper database.

A sizing event is the durable bridge between allocator eligibility and a later
simulated capital mutation. It grants no exchange or real-money authority.
REAL_CAPITAL remains 0.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.canonical_sizing import CanonicalPaperSizingSelection
from crypto_signal.paper.canonical_vault_eligibility import (
    CanonicalVaultEligibilityProof,
)
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.position_sizing_intelligence import SizingMethod

S11_SIZING_EVENT_SCHEMA_VERSION = "stream-s11-sizing-event-v1/1"
S11_SIZING_EVENT_ENGINE_VERSION = "stream-s11-sizing-event-engine-v1/1"
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class CanonicalSizingEvent:
    event_identity: str
    selection_identity: str
    eligibility_proof_identity: str
    allocator_assessment_identity: str
    allocator_candidate_identity: str
    sizing_assessment_identity: str
    sizing_result_identity: str
    sizing_policy_identity: str
    current_vault_snapshot_identity: str
    vault_id: PaperVaultId
    asset: str
    timeframe: str
    candidate_as_of_ms: int
    eligibility_assessed_at_ms: int
    selected_at_ms: int
    method: SizingMethod
    fraction_of_vault: Decimal
    canonical_notional_usdt: Decimal
    current_cash_usdt: Decimal
    current_nav_usdt: Decimal
    reason_codes: tuple[str, ...]
    source_evidence_identities: tuple[str, ...]
    schema_version: str = S11_SIZING_EVENT_SCHEMA_VERSION
    engine_version: str = S11_SIZING_EVENT_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.event_identity, "S11 sizing event"),
            (self.selection_identity, "S11 sizing selection"),
            (self.eligibility_proof_identity, "S11 eligibility proof"),
            (self.allocator_assessment_identity, "S11 allocator assessment"),
            (self.allocator_candidate_identity, "S11 allocator candidate"),
            (self.sizing_assessment_identity, "S11 sizing assessment"),
            (self.sizing_result_identity, "S11 sizing result"),
            (self.sizing_policy_identity, "S11 sizing policy"),
            (self.current_vault_snapshot_identity, "S11 current vault snapshot"),
        ):
            _require_sha256(identity, label)
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("S11 sizing event requires canonical vault")
        if not isinstance(self.method, SizingMethod):
            raise TypeError("S11 sizing event requires canonical sizing method")
        if self.method is not SizingMethod.FIXED_FRACTIONAL:
            raise ValueError("S11 sizing event only permits fixed fractional")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("S11 sizing event asset must be uppercase")
        if not self.timeframe.strip():
            raise ValueError("S11 sizing event timeframe must be non-empty")
        if min(
            self.candidate_as_of_ms,
            self.eligibility_assessed_at_ms,
            self.selected_at_ms,
        ) < 0:
            raise ValueError("S11 sizing event times must be non-negative")
        if not (
            self.candidate_as_of_ms
            <= self.eligibility_assessed_at_ms
            <= self.selected_at_ms
        ):
            raise ValueError("S11 sizing event chronology is invalid")
        for amount, label, positive in (
            (self.fraction_of_vault, "fraction", True),
            (self.canonical_notional_usdt, "notional", True),
            (self.current_cash_usdt, "cash", False),
            (self.current_nav_usdt, "NAV", False),
        ):
            _decimal(amount, label, positive=positive)
        if self.fraction_of_vault > Decimal(1):
            raise ValueError("S11 sizing event fraction cannot exceed one")
        if self.canonical_notional_usdt > self.current_cash_usdt:
            raise ValueError("S11 sizing event notional cannot exceed vault cash")
        if not self.reason_codes or self.reason_codes != tuple(
            sorted(set(self.reason_codes))
        ):
            raise ValueError("S11 sizing event reasons must be sorted unique")
        _identity_tuple(self.source_evidence_identities, "S11 sizing event source")
        required = {
            self.selection_identity,
            self.eligibility_proof_identity,
            self.allocator_assessment_identity,
            self.allocator_candidate_identity,
            self.sizing_assessment_identity,
            self.sizing_result_identity,
            self.sizing_policy_identity,
            self.current_vault_snapshot_identity,
        }
        if not required.issubset(set(self.source_evidence_identities)):
            raise ValueError("S11 sizing event lost exact source lineage")
        if self.schema_version != S11_SIZING_EVENT_SCHEMA_VERSION:
            raise ValueError("unsupported S11 sizing event schema")
        if self.engine_version != S11_SIZING_EVENT_ENGINE_VERSION:
            raise ValueError("unsupported S11 sizing event engine")
        if not self.read_only or self.production_authority or self.real_capital != 0:
            raise ValueError("S11 sizing event authority boundary mismatch")
        if self.event_identity != canonical_sha256(_event_payload(self)):
            raise ValueError("S11 sizing event identity mismatch")


class CanonicalSizingEventLedger:
    """Append-only sizing evidence colocated with canonical Epoch 2 accounting."""

    def __init__(self, epoch2_path: Path) -> None:
        self.epoch2_path = epoch2_path

    def initialize(self) -> None:
        Epoch2CanonicalLedger(self.epoch2_path).initialize()
        with closing(sqlite3.connect(self.epoch2_path)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS s11_canonical_sizing_events (
                    event_identity TEXT PRIMARY KEY,
                    selection_identity TEXT NOT NULL UNIQUE,
                    allocator_candidate_identity TEXT NOT NULL,
                    vault_id TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS s11_sizing_candidate_order
                ON s11_canonical_sizing_events (
                    allocator_candidate_identity,
                    vault_id,
                    event_at_ms,
                    event_identity
                )
                """
            )
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                    s11_canonical_sizing_events_immutable_{operation.lower()}
                    BEFORE {operation} ON s11_canonical_sizing_events
                    BEGIN
                        SELECT RAISE(ABORT, 'immutable S11 canonical sizing event ledger');
                    END
                    """
                )

    def append(self, event: CanonicalSizingEvent) -> bool:
        self.initialize()
        payload = canonical_json(event)
        with closing(sqlite3.connect(self.epoch2_path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            snapshot = connection.execute(
                """
                SELECT vault_id
                FROM r21_vault_snapshots
                WHERE snapshot_identity = ?
                """,
                (event.current_vault_snapshot_identity,),
            ).fetchone()
            if snapshot is None:
                raise ValueError("S11 sizing event references unknown R21 vault snapshot")
            if str(snapshot[0]) != event.vault_id.value:
                raise ValueError("S11 sizing event R21 vault lineage mismatch")

            existing = connection.execute(
                """
                SELECT event_identity, payload_json
                FROM s11_canonical_sizing_events
                WHERE event_identity = ? OR selection_identity = ?
                LIMIT 1
                """,
                (event.event_identity, event.selection_identity),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == event.event_identity
                    and str(existing[1]) == payload
                ):
                    return False
                raise ValueError("immutable S11 sizing event identity conflict")

            latest = connection.execute(
                """
                SELECT event_at_ms, event_identity
                FROM s11_canonical_sizing_events
                WHERE vault_id = ?
                ORDER BY event_at_ms DESC, event_identity DESC
                LIMIT 1
                """,
                (event.vault_id.value,),
            ).fetchone()
            if latest is not None and event.selected_at_ms <= int(str(latest[0])):
                raise ValueError("S11 sizing events cannot backfill or fork time")

            connection.execute(
                """
                INSERT INTO s11_canonical_sizing_events (
                    event_identity,
                    selection_identity,
                    allocator_candidate_identity,
                    vault_id,
                    event_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_identity,
                    event.selection_identity,
                    event.allocator_candidate_identity,
                    event.vault_id.value,
                    event.selected_at_ms,
                    payload,
                ),
            )
            connection.commit()
        return True

    def read(self, event_identity: str) -> dict[str, object] | None:
        _require_sha256(event_identity, "S11 sizing event lookup")
        if not self.epoch2_path.is_file():
            return None
        uri = f"file:{quote(str(self.epoch2_path.resolve()), safe='/')}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            row = connection.execute(
                """
                SELECT event_at_ms, payload_json
                FROM s11_canonical_sizing_events
                WHERE event_identity = ?
                """,
                (event_identity,),
            ).fetchone()
        if row is None:
            return None
        return _verify_payload(
            event_identity=event_identity,
            event_at_ms=int(str(row[0])),
            payload_json=str(row[1]),
        )

    def read_by_selection(
        self,
        selection_identity: str,
    ) -> dict[str, object] | None:
        _require_sha256(selection_identity, "S11 sizing selection lookup")
        if not self.epoch2_path.is_file():
            return None
        uri = f"file:{quote(str(self.epoch2_path.resolve()), safe='/')}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            row = connection.execute(
                """
                SELECT event_identity, event_at_ms, payload_json
                FROM s11_canonical_sizing_events
                WHERE selection_identity = ?
                """,
                (selection_identity,),
            ).fetchone()
        if row is None:
            return None
        return _verify_payload(
            event_identity=str(row[0]),
            event_at_ms=int(str(row[1])),
            payload_json=str(row[2]),
        )


def build_canonical_sizing_event(
    selection: CanonicalPaperSizingSelection,
    eligibility: CanonicalVaultEligibilityProof,
) -> CanonicalSizingEvent:
    if selection.vault_id is not eligibility.vault_id:
        raise ValueError("S11 sizing event vault mismatch")
    if selection.allocator_candidate_identity != eligibility.allocator_candidate_identity:
        raise ValueError("S11 sizing event allocator candidate mismatch")
    if selection.selected_at_ms < eligibility.assessed_at_ms:
        raise ValueError("S11 sizing event predates allocator eligibility")
    if not eligibility.canonical_paper_execution_eligible:
        raise ValueError("S11 sizing event requires executable eligibility proof")
    if selection.production_authority or selection.real_capital != REAL_CAPITAL:
        raise ValueError("S11 sizing selection authority boundary mismatch")
    if eligibility.production_authority or eligibility.real_capital != REAL_CAPITAL:
        raise ValueError("S11 eligibility authority boundary mismatch")

    sources = tuple(
        sorted(
            {
                *selection.source_evidence_identities,
                *eligibility.candidate_source_evidence_identities,
                selection.selection_identity,
                eligibility.proof_identity,
                eligibility.allocator_assessment_identity,
                eligibility.allocator_candidate_identity,
            }
        )
    )
    payload = {
        "allocator_assessment_identity": eligibility.allocator_assessment_identity,
        "allocator_candidate_identity": eligibility.allocator_candidate_identity,
        "asset": eligibility.asset,
        "candidate_as_of_ms": eligibility.candidate_as_of_ms,
        "canonical_notional_usdt": selection.canonical_notional_usdt,
        "current_cash_usdt": selection.current_cash_usdt,
        "current_nav_usdt": selection.current_nav_usdt,
        "current_vault_snapshot_identity": selection.current_vault_snapshot_identity,
        "eligibility_proof_identity": eligibility.proof_identity,
        "eligibility_assessed_at_ms": eligibility.assessed_at_ms,
        "engine_version": S11_SIZING_EVENT_ENGINE_VERSION,
        "fraction_of_vault": selection.fraction_of_vault,
        "method": selection.method,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "reason_codes": selection.reason_codes,
        "schema_version": S11_SIZING_EVENT_SCHEMA_VERSION,
        "selected_at_ms": selection.selected_at_ms,
        "selection_identity": selection.selection_identity,
        "sizing_assessment_identity": selection.sizing_assessment_identity,
        "sizing_policy_identity": selection.sizing_policy_identity,
        "sizing_result_identity": selection.sizing_result_identity,
        "source_evidence_identities": sources,
        "timeframe": eligibility.source_timeframe,
        "vault_id": selection.vault_id,
    }
    return CanonicalSizingEvent(
        event_identity=canonical_sha256(payload),
        selection_identity=selection.selection_identity,
        eligibility_proof_identity=eligibility.proof_identity,
        allocator_assessment_identity=eligibility.allocator_assessment_identity,
        allocator_candidate_identity=eligibility.allocator_candidate_identity,
        sizing_assessment_identity=selection.sizing_assessment_identity,
        sizing_result_identity=selection.sizing_result_identity,
        sizing_policy_identity=selection.sizing_policy_identity,
        current_vault_snapshot_identity=selection.current_vault_snapshot_identity,
        vault_id=selection.vault_id,
        asset=eligibility.asset,
        timeframe=eligibility.source_timeframe,
        candidate_as_of_ms=eligibility.candidate_as_of_ms,
        eligibility_assessed_at_ms=eligibility.assessed_at_ms,
        selected_at_ms=selection.selected_at_ms,
        method=selection.method,
        fraction_of_vault=selection.fraction_of_vault,
        canonical_notional_usdt=selection.canonical_notional_usdt,
        current_cash_usdt=selection.current_cash_usdt,
        current_nav_usdt=selection.current_nav_usdt,
        reason_codes=selection.reason_codes,
        source_evidence_identities=sources,
    )


def _verify_payload(
    *,
    event_identity: str,
    event_at_ms: int,
    payload_json: str,
) -> dict[str, object]:
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("S11 stored sizing event must decode to object")
    if raw.get("event_identity") != event_identity:
        raise ValueError("S11 stored sizing event identity column mismatch")
    if raw.get("selected_at_ms") != event_at_ms:
        raise ValueError("S11 stored sizing event time column mismatch")
    payload = dict(raw)
    payload.pop("event_identity", None)
    if canonical_sha256(payload) != event_identity:
        raise ValueError("S11 stored sizing event canonical identity mismatch")
    if raw.get("schema_version") != S11_SIZING_EVENT_SCHEMA_VERSION:
        raise ValueError("S11 stored sizing event schema mismatch")
    if raw.get("engine_version") != S11_SIZING_EVENT_ENGINE_VERSION:
        raise ValueError("S11 stored sizing event engine mismatch")
    if raw.get("read_only") is not True:
        raise ValueError("S11 stored sizing event read-only mismatch")
    if raw.get("production_authority") is not False:
        raise ValueError("S11 stored sizing event authority mismatch")
    if raw.get("real_capital") != REAL_CAPITAL:
        raise ValueError("S11 stored sizing event REAL_CAPITAL mismatch")
    return raw


def _event_payload(value: CanonicalSizingEvent) -> dict[str, object]:
    return {
        "allocator_assessment_identity": value.allocator_assessment_identity,
        "allocator_candidate_identity": value.allocator_candidate_identity,
        "asset": value.asset,
        "candidate_as_of_ms": value.candidate_as_of_ms,
        "canonical_notional_usdt": value.canonical_notional_usdt,
        "current_cash_usdt": value.current_cash_usdt,
        "current_nav_usdt": value.current_nav_usdt,
        "current_vault_snapshot_identity": value.current_vault_snapshot_identity,
        "eligibility_assessed_at_ms": value.eligibility_assessed_at_ms,
        "eligibility_proof_identity": value.eligibility_proof_identity,
        "engine_version": value.engine_version,
        "fraction_of_vault": value.fraction_of_vault,
        "method": value.method,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "reason_codes": value.reason_codes,
        "schema_version": value.schema_version,
        "selected_at_ms": value.selected_at_ms,
        "selection_identity": value.selection_identity,
        "sizing_assessment_identity": value.sizing_assessment_identity,
        "sizing_policy_identity": value.sizing_policy_identity,
        "sizing_result_identity": value.sizing_result_identity,
        "source_evidence_identities": value.source_evidence_identities,
        "timeframe": value.timeframe,
        "vault_id": value.vault_id,
    }


def _identity_tuple(values: tuple[str, ...], label: str) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise ValueError(f"{label} identities must be non-empty sorted unique")
    for identity in values:
        _require_sha256(identity, label)


def _decimal(value: Decimal, label: str, *, positive: bool) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError(f"S11 sizing event {label} must be finite Decimal")
    if value < 0 or (positive and value <= 0):
        raise ValueError(f"S11 sizing event {label} is outside allowed range")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
