"""FP3-A canonical paper-capital autopilot forward owner and replay receipts.

This module composes the already accepted forward Capital runtime. It does not
implement sizing or trade execution. Canonical R21/R22/S11 truth remains owned
by the existing accepted ledgers and commit functions. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
)
from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.paper.canonical_vault_decisions import CanonicalVaultDecisionLedger
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.product.intelligence_stream_capital_forward_runtime import (
    IntelligenceStreamCapitalForwardRuntime,
    StreamCapitalForwardDisposition,
)
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

FP3_AUTOPILOT_SCHEMA_VERSION = "fp3-paper-autopilot-forward-v1/1"
FP3_AUTOPILOT_RUNTIME_VERSION = "fp3-paper-autopilot-forward-runtime-v1/1"
FP3_AUTOPILOT_STORE_SUFFIX = ".fp3-paper-autopilot.sqlite3"

_META_TABLE = "fp3_paper_autopilot_meta"
_ACTIVATION_TABLE = "fp3_paper_autopilot_activation"
_RECEIPT_TABLE = "fp3_paper_autopilot_receipts"


class FP3AutopilotProcessDisposition(StrEnum):
    INSERTED = "inserted"
    RECOVERED = "recovered"
    REPLAYED = "replayed"
    SKIPPED_BEFORE_ACTIVATION = "skipped_before_activation"


@dataclass(frozen=True, slots=True)
class FP3AutopilotActivation:
    activation_identity: str
    activated_at_ms: int
    stream_capital_activation_identity: str
    epoch2_activation_identity: str
    historical_backfill_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = FP3_AUTOPILOT_SCHEMA_VERSION
    runtime_version: str = FP3_AUTOPILOT_RUNTIME_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.activation_identity, "FP3 activation identity")
        _require_sha256(
            self.stream_capital_activation_identity,
            "FP3 Stream capital activation",
        )
        _require_sha256(self.epoch2_activation_identity, "FP3 Epoch2 activation")
        _require_non_negative_int(self.activated_at_ms, "FP3 activation time")
        if self.historical_backfill_authority:
            raise ValueError("FP3 activation cannot grant historical backfill")
        _require_authority_boundary(
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.schema_version != FP3_AUTOPILOT_SCHEMA_VERSION:
            raise ValueError("unsupported FP3 autopilot schema")
        if self.runtime_version != FP3_AUTOPILOT_RUNTIME_VERSION:
            raise ValueError("unsupported FP3 autopilot runtime")
        if canonical_sha256(_activation_identity_payload(self)) != self.activation_identity:
            raise ValueError("FP3 activation identity mismatch")


@dataclass(frozen=True, slots=True)
class FP3AutopilotReceipt:
    receipt_identity: str
    activation_identity: str
    forecast_identity: str
    proof_identity: str
    source_as_of_ms: int
    issued_at_ms: int
    assessed_at_ms: int
    processed_at_ms: int
    allocator_candidate_identity: str
    allocator_assessment_identity: str
    decision_identities: tuple[str, ...]
    decision_states: tuple[tuple[str, str], ...]
    hold_or_block_count: int
    terminal_phase: str = "DECISIONS_COMMITTED"
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = FP3_AUTOPILOT_SCHEMA_VERSION
    runtime_version: str = FP3_AUTOPILOT_RUNTIME_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.receipt_identity, "FP3 receipt"),
            (self.activation_identity, "FP3 receipt activation"),
            (self.forecast_identity, "FP3 receipt forecast"),
            (self.proof_identity, "FP3 receipt proof"),
            (self.allocator_candidate_identity, "FP3 receipt allocator candidate"),
            (self.allocator_assessment_identity, "FP3 receipt allocator assessment"),
        ):
            _require_sha256(value, label)
        if len(self.decision_identities) != len(tuple(PaperVaultId)):
            raise ValueError("FP3 receipt requires exactly three decision identities")
        if self.decision_identities != tuple(sorted(set(self.decision_identities))):
            raise ValueError("FP3 receipt decision identities must be sorted unique")
        for value in self.decision_identities:
            _require_sha256(value, "FP3 receipt decision")
        expected_vaults = tuple(sorted(vault.value for vault in PaperVaultId))
        actual_vaults = tuple(item[0] for item in self.decision_states)
        if actual_vaults != expected_vaults:
            raise ValueError("FP3 receipt decision states require canonical vault order")
        valid_states = {"eligible", "hold", "blocked"}
        if any(state not in valid_states for _, state in self.decision_states):
            raise ValueError("FP3 receipt contains unsupported vault disposition")
        derived_hold = sum(
            1 for _, state in self.decision_states if state in {"hold", "blocked"}
        )
        if self.hold_or_block_count != derived_hold:
            raise ValueError("FP3 receipt HOLD/BLOCK count mismatch")
        for value, label in (
            (self.source_as_of_ms, "FP3 source as-of"),
            (self.issued_at_ms, "FP3 issued time"),
            (self.assessed_at_ms, "FP3 assessed time"),
            (self.processed_at_ms, "FP3 processed time"),
        ):
            _require_non_negative_int(value, label)
        if self.source_as_of_ms > self.issued_at_ms:
            raise ValueError("FP3 source as-of cannot follow forecast issuance")
        if self.assessed_at_ms <= self.issued_at_ms:
            raise ValueError("FP3 assessment must follow forecast issuance")
        if self.processed_at_ms < self.assessed_at_ms:
            raise ValueError("FP3 process time cannot predate assessment")
        if self.terminal_phase != "DECISIONS_COMMITTED":
            raise ValueError("unsupported FP3-A terminal phase")
        _require_authority_boundary(
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.schema_version != FP3_AUTOPILOT_SCHEMA_VERSION:
            raise ValueError("unsupported FP3 receipt schema")
        if self.runtime_version != FP3_AUTOPILOT_RUNTIME_VERSION:
            raise ValueError("unsupported FP3 receipt runtime")
        if canonical_sha256(_receipt_identity_payload(self)) != self.receipt_identity:
            raise ValueError("FP3 receipt identity mismatch")


@dataclass(frozen=True, slots=True)
class FP3AutopilotProcessResult:
    disposition: FP3AutopilotProcessDisposition
    activation_identity: str
    forecast_identity: str
    receipt: FP3AutopilotReceipt | None
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.activation_identity, "FP3 result activation")
        _require_sha256(self.forecast_identity, "FP3 result forecast")
        if (
            self.disposition
            is FP3AutopilotProcessDisposition.SKIPPED_BEFORE_ACTIVATION
        ):
            if self.receipt is not None:
                raise ValueError("skipped FP3 result cannot carry receipt")
        elif self.receipt is None:
            raise ValueError("processed FP3 result requires receipt")
        _require_authority_boundary(
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )


class FP3AutopilotStore:
    """Isolated append-only activation and processing receipt store."""

    def __init__(self, path: Path) -> None:
        if not str(path).endswith(FP3_AUTOPILOT_STORE_SUFFIX):
            raise ValueError(
                f"FP3 autopilot store path must end with {FP3_AUTOPILOT_STORE_SUFFIX}"
            )
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                INSERT OR IGNORE INTO {_META_TABLE}(key, value)
                VALUES ('schema_version', ?)
                """,
                (FP3_AUTOPILOT_SCHEMA_VERSION,),
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_ACTIVATION_TABLE} (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    activation_identity TEXT NOT NULL UNIQUE,
                    activated_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_RECEIPT_TABLE} (
                    receipt_identity TEXT PRIMARY KEY,
                    forecast_identity TEXT NOT NULL UNIQUE,
                    assessed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )
            for table in (_ACTIVATION_TABLE, _RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'immutable FP3 paper autopilot truth'
                            );
                        END
                        """
                    )
            _require_store_schema(connection)

    def append_activation(self, value: FP3AutopilotActivation) -> bool:
        self.initialize()
        payload_json = canonical_json(value)
        digest = sha256_text(payload_json)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            _require_store_schema(connection)
            row = connection.execute(
                f"""
                SELECT activation_identity, activated_at_ms,
                       payload_json, payload_sha256
                FROM {_ACTIVATION_TABLE}
                WHERE singleton = 1
                """
            ).fetchone()
            if row is not None:
                existing = _verified_activation_row(row)
                if existing == value:
                    return False
                raise ValueError("FP3 autopilot activation is immutable")
            connection.execute(
                f"""
                INSERT INTO {_ACTIVATION_TABLE}(
                    singleton,
                    activation_identity,
                    activated_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (1, ?, ?, ?, ?)
                """,
                (
                    value.activation_identity,
                    value.activated_at_ms,
                    payload_json,
                    digest,
                ),
            )
        return True

    def read_activation(self) -> FP3AutopilotActivation | None:
        if not self.path.is_file():
            return None
        with closing(_connect_read_only(self.path)) as connection:
            _require_store_schema(connection)
            row = connection.execute(
                f"""
                SELECT activation_identity, activated_at_ms,
                       payload_json, payload_sha256
                FROM {_ACTIVATION_TABLE}
                WHERE singleton = 1
                """
            ).fetchone()
        return None if row is None else _verified_activation_row(row)

    def append_receipt(self, value: FP3AutopilotReceipt) -> bool:
        self.initialize()
        payload_json = canonical_json(value)
        digest = sha256_text(payload_json)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            _require_store_schema(connection)
            row = connection.execute(
                f"""
                SELECT receipt_identity, forecast_identity, assessed_at_ms,
                       payload_json, payload_sha256
                FROM {_RECEIPT_TABLE}
                WHERE receipt_identity = ? OR forecast_identity = ?
                LIMIT 1
                """,
                (value.receipt_identity, value.forecast_identity),
            ).fetchone()
            if row is not None:
                existing = _verified_receipt_row(row)
                if existing == value:
                    return False
                raise ValueError("FP3 autopilot receipt identity conflict")
            connection.execute(
                f"""
                INSERT INTO {_RECEIPT_TABLE}(
                    receipt_identity,
                    forecast_identity,
                    assessed_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    value.receipt_identity,
                    value.forecast_identity,
                    value.assessed_at_ms,
                    payload_json,
                    digest,
                ),
            )
        return True

    def read_receipt_for_forecast(
        self,
        forecast_identity: str,
    ) -> FP3AutopilotReceipt | None:
        _require_sha256(forecast_identity, "FP3 receipt forecast lookup")
        if not self.path.is_file():
            return None
        with closing(_connect_read_only(self.path)) as connection:
            _require_store_schema(connection)
            row = connection.execute(
                f"""
                SELECT receipt_identity, forecast_identity, assessed_at_ms,
                       payload_json, payload_sha256
                FROM {_RECEIPT_TABLE}
                WHERE forecast_identity = ?
                """,
                (forecast_identity,),
            ).fetchone()
        return None if row is None else _verified_receipt_row(row)


class CanonicalPaperAutopilotForwardRuntime:
    """FP3-A owner over the accepted Capital forward projection rail."""

    def __init__(
        self,
        *,
        epoch2_path: Path,
        stream_path: Path,
        autopilot_path: Path,
    ) -> None:
        resolved = {
            epoch2_path.resolve(),
            stream_path.resolve(),
            autopilot_path.resolve(),
        }
        if len(resolved) != 3:
            raise ValueError("FP3 autopilot, Epoch2 and Stream paths must be separate")
        self.epoch2_path = epoch2_path
        self.stream_path = stream_path
        self.store = FP3AutopilotStore(autopilot_path)
        self.front = IntelligenceStreamCapitalForwardRuntime(
            epoch2_path=epoch2_path,
            stream_path=stream_path,
        )

    def ensure_activated(self, *, activated_at_ms: int) -> str:
        _require_non_negative_int(activated_at_ms, "FP3 activation time")
        front_identity = self.front.ensure_activated(
            activated_at_ms=activated_at_ms,
        )
        front_activation = self.front.activation()
        if front_activation.get("activation_identity") != front_identity:
            raise ValueError("FP3 front activation identity mismatch")
        if front_activation.get("activated_at_ms") != activated_at_ms:
            raise ValueError("FP3 activation time differs from existing front runtime")

        epoch2 = Epoch2CanonicalLedger(self.epoch2_path).read_state()
        if epoch2 is None:
            raise ValueError("FP3 activation requires canonical Epoch2 state")
        payload = {
            "activated_at_ms": activated_at_ms,
            "epoch2_activation_identity": epoch2.activation.activation_identity,
            "historical_backfill_authority": False,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
            "runtime_version": FP3_AUTOPILOT_RUNTIME_VERSION,
            "schema_version": FP3_AUTOPILOT_SCHEMA_VERSION,
            "stream_capital_activation_identity": front_identity,
        }
        value = FP3AutopilotActivation(
            activation_identity=canonical_sha256(payload),
            activated_at_ms=activated_at_ms,
            stream_capital_activation_identity=front_identity,
            epoch2_activation_identity=epoch2.activation.activation_identity,
        )
        self.store.append_activation(value)
        return value.activation_identity

    def process_issuance(
        self,
        issuance: UnifiedDecisionIssuance,
        *,
        event_context: CircuitBreakerAnalysis,
        base_asset: str,
        assessed_at_ms: int,
        processed_at_ms: int,
    ) -> FP3AutopilotProcessResult:
        activation = self.store.read_activation()
        if activation is None:
            raise ValueError("FP3 autopilot runtime is not activated")
        forecast = issuance.forecast
        if issuance.proof.forecast_identity != forecast.forecast_identity:
            raise ValueError("FP3 issuance proof/forecast lineage mismatch")
        if (
            forecast.issued_at_ms < activation.activated_at_ms
            or assessed_at_ms < activation.activated_at_ms
        ):
            return FP3AutopilotProcessResult(
                disposition=(
                    FP3AutopilotProcessDisposition.SKIPPED_BEFORE_ACTIVATION
                ),
                activation_identity=activation.activation_identity,
                forecast_identity=forecast.forecast_identity,
                receipt=None,
            )
        if assessed_at_ms <= forecast.issued_at_ms:
            raise ValueError("FP3 assessment must follow forecast issuance")
        if processed_at_ms < assessed_at_ms:
            raise ValueError("FP3 process time cannot predate assessment")

        existing = self.store.read_receipt_for_forecast(
            forecast.forecast_identity
        )
        if existing is not None:
            _verify_receipt_request(
                existing,
                activation=activation,
                issuance=issuance,
                assessed_at_ms=assessed_at_ms,
            )
            return FP3AutopilotProcessResult(
                disposition=FP3AutopilotProcessDisposition.REPLAYED,
                activation_identity=activation.activation_identity,
                forecast_identity=forecast.forecast_identity,
                receipt=existing,
            )

        front = self.front.project_issuance(
            issuance,
            event_context=event_context,
            base_asset=base_asset,
            assessed_at_ms=assessed_at_ms,
        )
        if (
            front.disposition
            is StreamCapitalForwardDisposition.SKIPPED_BEFORE_ACTIVATION
        ):
            raise ValueError("FP3/front activation boundary diverged")
        if (
            front.allocator_candidate_identity is None
            or front.allocator_assessment_identity is None
        ):
            raise ValueError("FP3 front-half lost allocator lineage")

        decisions = CanonicalVaultDecisionLedger(
            self.epoch2_path
        ).read_assessment_decisions(front.allocator_assessment_identity)
        receipt = _build_receipt(
            activation=activation,
            issuance=issuance,
            assessed_at_ms=assessed_at_ms,
            processed_at_ms=processed_at_ms,
            allocator_candidate_identity=front.allocator_candidate_identity,
            allocator_assessment_identity=front.allocator_assessment_identity,
            front_decision_identities=front.decision_identities,
            decisions=decisions,
        )
        inserted = self.store.append_receipt(receipt)
        disposition = (
            FP3AutopilotProcessDisposition.RECOVERED
            if (
                inserted
                and front.disposition is StreamCapitalForwardDisposition.UNCHANGED
            )
            else FP3AutopilotProcessDisposition.INSERTED
            if inserted
            else FP3AutopilotProcessDisposition.REPLAYED
        )
        return FP3AutopilotProcessResult(
            disposition=disposition,
            activation_identity=activation.activation_identity,
            forecast_identity=forecast.forecast_identity,
            receipt=receipt,
        )


def _build_receipt(
    *,
    activation: FP3AutopilotActivation,
    issuance: UnifiedDecisionIssuance,
    assessed_at_ms: int,
    processed_at_ms: int,
    allocator_candidate_identity: str,
    allocator_assessment_identity: str,
    front_decision_identities: tuple[str, ...],
    decisions: tuple[dict[str, object], ...],
) -> FP3AutopilotReceipt:
    if len(decisions) != len(tuple(PaperVaultId)):
        raise ValueError("FP3 requires exactly three canonical vault decisions")
    by_vault: dict[str, dict[str, object]] = {}
    decision_ids: list[str] = []
    states: list[tuple[str, str]] = []
    for raw in decisions:
        vault = _required_text(raw, "vault_id")
        if vault in by_vault:
            raise ValueError("FP3 canonical vault decision is duplicated")
        by_vault[vault] = raw
    for vault_id in sorted(PaperVaultId, key=lambda item: item.value):
        raw = by_vault.get(vault_id.value)
        if raw is None:
            raise ValueError("FP3 canonical vault decision is missing")
        decision_identity = _required_sha(raw, "decision_identity")
        decision_ids.append(decision_identity)
        states.append((vault_id.value, _required_text(raw, "disposition")))

    canonical_decision_ids = tuple(sorted(decision_ids))
    if canonical_decision_ids != tuple(sorted(front_decision_identities)):
        raise ValueError("FP3 front result/canonical decision identities mismatch")

    forecast = issuance.forecast
    proof = issuance.proof
    provisional = {
        "activation_identity": activation.activation_identity,
        "allocator_assessment_identity": allocator_assessment_identity,
        "allocator_candidate_identity": allocator_candidate_identity,
        "assessed_at_ms": assessed_at_ms,
        "decision_identities": canonical_decision_ids,
        "decision_states": tuple(states),
        "forecast_identity": forecast.forecast_identity,
        "hold_or_block_count": sum(
            1 for _, state in states if state in {"hold", "blocked"}
        ),
        "issued_at_ms": forecast.issued_at_ms,
        "production_authority": False,
        "proof_identity": proof.proof_identity,
        "real_capital": REAL_CAPITAL,
        "runtime_version": FP3_AUTOPILOT_RUNTIME_VERSION,
        "schema_version": FP3_AUTOPILOT_SCHEMA_VERSION,
        "source_as_of_ms": forecast.source_as_of_ms,
        "terminal_phase": "DECISIONS_COMMITTED",
    }
    return FP3AutopilotReceipt(
        receipt_identity=canonical_sha256(provisional),
        activation_identity=activation.activation_identity,
        forecast_identity=forecast.forecast_identity,
        proof_identity=proof.proof_identity,
        source_as_of_ms=forecast.source_as_of_ms,
        issued_at_ms=forecast.issued_at_ms,
        assessed_at_ms=assessed_at_ms,
        processed_at_ms=processed_at_ms,
        allocator_candidate_identity=allocator_candidate_identity,
        allocator_assessment_identity=allocator_assessment_identity,
        decision_identities=canonical_decision_ids,
        decision_states=tuple(states),
        hold_or_block_count=provisional["hold_or_block_count"],
    )


def _verify_receipt_request(
    receipt: FP3AutopilotReceipt,
    *,
    activation: FP3AutopilotActivation,
    issuance: UnifiedDecisionIssuance,
    assessed_at_ms: int,
) -> None:
    if receipt.activation_identity != activation.activation_identity:
        raise ValueError("FP3 replay activation mismatch")
    if receipt.forecast_identity != issuance.forecast.forecast_identity:
        raise ValueError("FP3 replay forecast mismatch")
    if receipt.proof_identity != issuance.proof.proof_identity:
        raise ValueError("FP3 replay proof mismatch")
    if receipt.assessed_at_ms != assessed_at_ms:
        raise ValueError("FP3 replay assessment time mismatch")


def _activation_identity_payload(
    value: FP3AutopilotActivation,
) -> dict[str, object]:
    return {
        "activated_at_ms": value.activated_at_ms,
        "epoch2_activation_identity": value.epoch2_activation_identity,
        "historical_backfill_authority": value.historical_backfill_authority,
        "production_authority": value.production_authority,
        "real_capital": value.real_capital,
        "runtime_version": value.runtime_version,
        "schema_version": value.schema_version,
        "stream_capital_activation_identity": (
            value.stream_capital_activation_identity
        ),
    }


def _receipt_identity_payload(
    value: FP3AutopilotReceipt,
) -> dict[str, object]:
    return {
        "activation_identity": value.activation_identity,
        "allocator_assessment_identity": value.allocator_assessment_identity,
        "allocator_candidate_identity": value.allocator_candidate_identity,
        "assessed_at_ms": value.assessed_at_ms,
        "decision_identities": value.decision_identities,
        "decision_states": value.decision_states,
        "forecast_identity": value.forecast_identity,
        "hold_or_block_count": value.hold_or_block_count,
        "issued_at_ms": value.issued_at_ms,
        "production_authority": value.production_authority,
        "proof_identity": value.proof_identity,
        "real_capital": value.real_capital,
        "runtime_version": value.runtime_version,
        "schema_version": value.schema_version,
        "source_as_of_ms": value.source_as_of_ms,
        "terminal_phase": value.terminal_phase,
    }


def _verified_activation_row(row: sqlite3.Row) -> FP3AutopilotActivation:
    raw = _verified_json_payload(
        payload_json=str(row["payload_json"]),
        expected_digest=str(row["payload_sha256"]),
        label="FP3 activation",
    )
    value = FP3AutopilotActivation(
        activation_identity=_required_text(raw, "activation_identity"),
        activated_at_ms=_required_int(raw, "activated_at_ms"),
        stream_capital_activation_identity=_required_text(
            raw,
            "stream_capital_activation_identity",
        ),
        epoch2_activation_identity=_required_text(
            raw,
            "epoch2_activation_identity",
        ),
        historical_backfill_authority=_required_bool(
            raw,
            "historical_backfill_authority",
        ),
        production_authority=_required_bool(raw, "production_authority"),
        real_capital=_required_int(raw, "real_capital"),
        schema_version=_required_text(raw, "schema_version"),
        runtime_version=_required_text(raw, "runtime_version"),
    )
    if str(row["activation_identity"]) != value.activation_identity:
        raise ValueError("FP3 activation row identity mismatch")
    if int(row["activated_at_ms"]) != value.activated_at_ms:
        raise ValueError("FP3 activation row time mismatch")
    if canonical_json(value) != str(row["payload_json"]):
        raise ValueError("FP3 activation canonical payload mismatch")
    return value


def _verified_receipt_row(row: sqlite3.Row) -> FP3AutopilotReceipt:
    raw = _verified_json_payload(
        payload_json=str(row["payload_json"]),
        expected_digest=str(row["payload_sha256"]),
        label="FP3 receipt",
    )
    decision_states_raw = raw.get("decision_states")
    if not isinstance(decision_states_raw, list):
        raise TypeError("FP3 receipt decision states must be array")
    states: list[tuple[str, str]] = []
    for item in decision_states_raw:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(value, str) for value in item)
        ):
            raise TypeError("FP3 receipt decision state is invalid")
        states.append((cast(list[str], item)[0], cast(list[str], item)[1]))
    decision_ids_raw = raw.get("decision_identities")
    if not isinstance(decision_ids_raw, list) or not all(
        isinstance(item, str) for item in decision_ids_raw
    ):
        raise TypeError("FP3 receipt decision identities must be string array")
    value = FP3AutopilotReceipt(
        receipt_identity=_required_text(raw, "receipt_identity"),
        activation_identity=_required_text(raw, "activation_identity"),
        forecast_identity=_required_text(raw, "forecast_identity"),
        proof_identity=_required_text(raw, "proof_identity"),
        source_as_of_ms=_required_int(raw, "source_as_of_ms"),
        issued_at_ms=_required_int(raw, "issued_at_ms"),
        assessed_at_ms=_required_int(raw, "assessed_at_ms"),
        processed_at_ms=_required_int(raw, "processed_at_ms"),
        allocator_candidate_identity=_required_text(
            raw,
            "allocator_candidate_identity",
        ),
        allocator_assessment_identity=_required_text(
            raw,
            "allocator_assessment_identity",
        ),
        decision_identities=tuple(cast(list[str], decision_ids_raw)),
        decision_states=tuple(states),
        hold_or_block_count=_required_int(raw, "hold_or_block_count"),
        terminal_phase=_required_text(raw, "terminal_phase"),
        production_authority=_required_bool(raw, "production_authority"),
        real_capital=_required_int(raw, "real_capital"),
        schema_version=_required_text(raw, "schema_version"),
        runtime_version=_required_text(raw, "runtime_version"),
    )
    if str(row["receipt_identity"]) != value.receipt_identity:
        raise ValueError("FP3 receipt row identity mismatch")
    if str(row["forecast_identity"]) != value.forecast_identity:
        raise ValueError("FP3 receipt row forecast mismatch")
    if int(row["assessed_at_ms"]) != value.assessed_at_ms:
        raise ValueError("FP3 receipt row assessment mismatch")
    if canonical_json(value) != str(row["payload_json"]):
        raise ValueError("FP3 receipt canonical payload mismatch")
    return value


def _verified_json_payload(
    *,
    payload_json: str,
    expected_digest: str,
    label: str,
) -> dict[str, object]:
    if sha256_text(payload_json) != expected_digest:
        raise ValueError(f"{label} payload digest mismatch")
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError(f"{label} payload must be object")
    return cast(dict[str, object], raw)


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _require_store_schema(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    required = {_META_TABLE, _ACTIVATION_TABLE, _RECEIPT_TABLE}
    if not required.issubset(tables):
        raise ValueError("FP3 autopilot store required table missing")
    row = connection.execute(
        f"SELECT value FROM {_META_TABLE} WHERE key='schema_version'"
    ).fetchone()
    if row is None or str(row[0]) != FP3_AUTOPILOT_SCHEMA_VERSION:
        raise ValueError("FP3 autopilot store schema mismatch")


def _required_text(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty text")
    return value


def _required_sha(raw: dict[str, object], key: str) -> str:
    value = _required_text(raw, key)
    _require_sha256(value, key)
    return value


def _required_int(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be int")
    return value


def _required_bool(raw: dict[str, object], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be exact SHA256")


def _require_non_negative_int(value: int, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be non-negative integer")


def _require_authority_boundary(
    *,
    production_authority: bool,
    real_capital: int,
) -> None:
    if production_authority or real_capital != REAL_CAPITAL:
        raise ValueError("FP3 autopilot crossed authority boundary")
