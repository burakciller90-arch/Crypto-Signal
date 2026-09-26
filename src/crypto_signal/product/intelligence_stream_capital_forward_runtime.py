"""Forward-only canonical three-vault Capital Story runtime.

F5 closes the production gap between an exact UnifiedDecisionIssuance and the
already accepted S11 canonical capital / Stream projectors.

This runtime deliberately owns only the parts for which exact forward inputs
already exist:
- Capital Science candidate + three-vault allocator assessment;
- canonical ELIGIBLE / HOLD / BLOCKED decisions;
- canonical R22 HOLD_CASH intent for HOLD/BLOCK;
- first-class CAPITAL candidate / vault-decision Stream messages.

It does not invent sizing risk inputs, does not auto-select sizing, does not
create fills, does not place exchange orders, and never grants real-capital
authority. Later canonical sizing/fill projection remains possible through the
existing S11 projectors once exact accepted inputs exist.

REAL_CAPITAL=0.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
)
from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.paper.capital_science_bridge import assess_unified_decision_capital
from crypto_signal.paper.canonical_sizing_events import CanonicalSizingEventLedger
from crypto_signal.paper.canonical_vault_decisions import (
    CanonicalVaultDecisionDisposition,
    CanonicalVaultDecisionLedger,
    build_vault_decision,
    commit_canonical_hold,
)
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.intelligence_stream_capital import (
    IntelligenceStreamCapitalLedger,
)
from crypto_signal.product.intelligence_stream_capital_decisions import (
    IntelligenceStreamCapitalDecisionLedger,
    project_vault_decision_to_stream,
)
from crypto_signal.product.intelligence_stream_capital_forward_evidence import (
    build_capital_forward_auxiliary_evidence,
)
from crypto_signal.product.intelligence_stream_capital_lifecycle import (
    IntelligenceStreamCapitalLifecycleLedger,
    project_capital_candidate_to_stream,
)
from crypto_signal.product.intelligence_stream_capital_sizing import (
    IntelligenceStreamCapitalSizingLedger,
)
from crypto_signal.product.intelligence_stream_ledger import IntelligenceStreamLedger
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

STREAM_CAPITAL_FORWARD_ACTIVATION_SCHEMA_VERSION = (
    "intelligence-stream-capital-forward-activation-v1/1"
)
STREAM_CAPITAL_FORWARD_RUNTIME_VERSION = (
    "intelligence-stream-capital-forward-runtime-v1/1"
)
REAL_CAPITAL = 0

_ACTIVATION_TABLE = "stream_capital_projection_activation"


class StreamCapitalForwardDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"
    SKIPPED_BEFORE_ACTIVATION = "skipped_before_activation"


@dataclass(frozen=True, slots=True)
class StreamCapitalForwardResult:
    disposition: StreamCapitalForwardDisposition
    activation_identity: str
    forecast_identity: str
    allocator_candidate_identity: str | None
    allocator_assessment_identity: str | None
    decision_identities: tuple[str, ...]
    inserted_decision_count: int
    hold_intent_count: int
    projected_message_count: int
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _sha(self.activation_identity, "capital forward activation")
        _sha(self.forecast_identity, "capital forward forecast")
        for value, label in (
            (self.allocator_candidate_identity, "capital forward candidate"),
            (self.allocator_assessment_identity, "capital forward assessment"),
        ):
            if value is not None:
                _sha(value, label)
        for value in self.decision_identities:
            _sha(value, "capital forward decision")
        if self.decision_identities and len(self.decision_identities) != len(
            tuple(PaperVaultId)
        ):
            raise ValueError("capital forward result requires all three vault decisions")
        if min(
            self.inserted_decision_count,
            self.hold_intent_count,
            self.projected_message_count,
        ) < 0:
            raise ValueError("capital forward counts cannot be negative")
        if (
            self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("capital forward runtime crossed authority boundary")


class IntelligenceStreamCapitalForwardRuntime:
    """Promote exact forward issuance into canonical paper-capital story truth."""

    def __init__(self, *, epoch2_path: Path, stream_path: Path) -> None:
        self.epoch2_path = epoch2_path
        self.stream_path = stream_path

    def ensure_activated(self, *, activated_at_ms: int) -> str:
        if activated_at_ms < 0:
            raise ValueError("capital forward activation cannot be negative")

        stream = IntelligenceStreamLedger(self.stream_path)
        global_activation = stream.read_activation()
        global_activation_identity = _text(
            global_activation,
            "activation_identity",
        )
        global_activated_at_ms = _integer(
            global_activation,
            "activated_at_ms",
        )
        if activated_at_ms < global_activated_at_ms:
            raise ValueError(
                "capital forward activation cannot predate Stream activation"
            )

        state = Epoch2CanonicalLedger(self.epoch2_path).read_state()
        if state is None:
            raise ValueError("capital forward runtime requires canonical Epoch2 state")
        if state.consolidated_snapshot.real_capital != REAL_CAPITAL:
            raise ValueError("capital forward Epoch2 REAL_CAPITAL mismatch")

        # Schema-only activation. These initialize accepted append-only ledgers but
        # create no decision, intent, sizing, fill, accounting or message rows.
        CanonicalVaultDecisionLedger(self.epoch2_path).initialize()
        CanonicalSizingEventLedger(self.epoch2_path).initialize()
        R22Epoch2AtomicTape(self.epoch2_path).initialize()
        IntelligenceStreamCapitalDecisionLedger(self.stream_path).initialize()
        IntelligenceStreamCapitalSizingLedger(self.stream_path).initialize()
        IntelligenceStreamCapitalLedger(self.stream_path).initialize()
        IntelligenceStreamCapitalLifecycleLedger(self.stream_path).initialize()

        with closing(sqlite3.connect(self.stream_path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_ACTIVATION_TABLE} (
                    activation_identity TEXT PRIMARY KEY,
                    activated_at_ms INTEGER NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                    {_ACTIVATION_TABLE}_immutable_{operation.lower()}
                    BEFORE {operation} ON {_ACTIVATION_TABLE}
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable Stream capital forward activation'
                        );
                    END
                    """
                )

            row = connection.execute(
                f"""
                SELECT activation_identity, activated_at_ms,
                       payload_json, payload_sha256
                FROM {_ACTIVATION_TABLE}
                ORDER BY activated_at_ms, activation_identity
                """
            ).fetchall()
            if len(row) > 1:
                raise ValueError("capital forward permits exactly one activation")
            if row:
                existing = row[0]
                payload_json = str(existing[2])
                if sha256_text(payload_json) != str(existing[3]):
                    raise ValueError("capital forward activation digest mismatch")
                payload = json.loads(payload_json)
                if not isinstance(payload, dict):
                    raise TypeError("capital forward activation payload must be object")
                if (
                    payload.get("activation_identity") != str(existing[0])
                    or payload.get("activated_at_ms") != int(existing[1])
                    or payload.get("stream_activation_identity")
                    != global_activation_identity
                    or payload.get("epoch2_activation_identity")
                    != state.activation.activation_identity
                    or payload.get("historical_rich_backfill_allowed") is not False
                    or payload.get("production_authority") is not False
                    or payload.get("real_capital") != REAL_CAPITAL
                ):
                    raise ValueError("capital forward activation payload mismatch")
                return str(existing[0])

            payload_without_identity = {
                "activated_at_ms": activated_at_ms,
                "epoch2_activation_identity": state.activation.activation_identity,
                "historical_rich_backfill_allowed": False,
                "production_authority": False,
                "read_only_projection": True,
                "real_capital": REAL_CAPITAL,
                "runtime_version": STREAM_CAPITAL_FORWARD_RUNTIME_VERSION,
                "schema_version": STREAM_CAPITAL_FORWARD_ACTIVATION_SCHEMA_VERSION,
                "stream_activation_identity": global_activation_identity,
            }
            identity = canonical_sha256(payload_without_identity)
            payload = {
                "activation_identity": identity,
                **payload_without_identity,
            }
            encoded = canonical_json(payload)
            connection.execute(
                f"""
                INSERT INTO {_ACTIVATION_TABLE} (
                    activation_identity,
                    activated_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    identity,
                    activated_at_ms,
                    encoded,
                    sha256_text(encoded),
                ),
            )
            connection.commit()
            return identity

    def activation(self) -> dict[str, object]:
        if not self.stream_path.is_file():
            raise ValueError("capital forward Stream ledger missing")
        uri = f"{self.stream_path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.execute("PRAGMA query_only=ON")
            rows = connection.execute(
                f"""
                SELECT activation_identity, activated_at_ms,
                       payload_json, payload_sha256
                FROM {_ACTIVATION_TABLE}
                ORDER BY activated_at_ms, activation_identity
                """
            ).fetchall()
        if len(rows) != 1:
            raise ValueError("capital forward activation is missing or ambiguous")
        payload_json = str(rows[0][2])
        if sha256_text(payload_json) != str(rows[0][3]):
            raise ValueError("capital forward activation digest mismatch")
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise TypeError("capital forward activation payload must be object")
        if (
            payload.get("activation_identity") != str(rows[0][0])
            or payload.get("activated_at_ms") != int(rows[0][1])
        ):
            raise ValueError("capital forward activation row/payload mismatch")
        return payload

    def project_issuance(
        self,
        issuance: UnifiedDecisionIssuance,
        *,
        event_context: CircuitBreakerAnalysis,
        base_asset: str,
        assessed_at_ms: int,
    ) -> StreamCapitalForwardResult:
        activation = self.activation()
        activation_identity = _text(activation, "activation_identity")
        activated_at_ms = _integer(activation, "activated_at_ms")
        forecast = issuance.forecast

        if (
            forecast.issued_at_ms < activated_at_ms
            or assessed_at_ms < activated_at_ms
        ):
            return StreamCapitalForwardResult(
                disposition=(
                    StreamCapitalForwardDisposition.SKIPPED_BEFORE_ACTIVATION
                ),
                activation_identity=activation_identity,
                forecast_identity=forecast.forecast_identity,
                allocator_candidate_identity=None,
                allocator_assessment_identity=None,
                decision_identities=(),
                inserted_decision_count=0,
                hold_intent_count=0,
                projected_message_count=0,
            )
        if assessed_at_ms <= forecast.issued_at_ms:
            raise ValueError(
                "capital forward assessment must follow forecast issuance"
            )

        state = Epoch2CanonicalLedger(self.epoch2_path).read_state()
        if state is None:
            raise ValueError("capital forward lost canonical Epoch2 state")
        auxiliary = build_capital_forward_auxiliary_evidence(
            issuance,
            event_context=event_context,
        )
        capital = assess_unified_decision_capital(
            issuance,
            event_context=event_context,
            base_asset=base_asset,
            assessed_at_ms=assessed_at_ms,
            tactical_microstructure=auxiliary.tactical,
            opportunity_recovery=auxiliary.opportunity,
        )

        ledger = CanonicalVaultDecisionLedger(self.epoch2_path)
        decisions = []
        inserted_decisions = 0
        hold_intents = 0
        # The allocator assessment is one canonical event.  Vault decisions are
        # subsequent canonical decisions and therefore receive a deterministic
        # monotonic millisecond after the assessment in stable vault order.
        # This preserves the Stream's global forward-only chronology without
        # weakening its anti-backfill guard or inventing market timestamps.
        for decision_offset_ms, vault_id in enumerate(PaperVaultId, start=1):
            decision = build_vault_decision(
                state.activation,
                capital.candidate,
                capital.allocation,
                vault_id=vault_id,
                decided_at_ms=assessed_at_ms + decision_offset_ms,
            )
            existing = ledger.read(decision.decision_identity)
            if existing is None:
                if (
                    decision.disposition
                    is CanonicalVaultDecisionDisposition.ELIGIBLE
                ):
                    if ledger.append(decision):
                        inserted_decisions += 1
                else:
                    committed = commit_canonical_hold(
                        epoch2_path=self.epoch2_path,
                        decision=decision,
                    )
                    if committed.decision_inserted:
                        inserted_decisions += 1
                    if committed.intent_inserted:
                        hold_intents += 1
            decisions.append(decision)

        candidate_projection = project_capital_candidate_to_stream(
            epoch2_path=self.epoch2_path,
            stream_path=self.stream_path,
            allocator_assessment_identity=capital.allocation.assessment_identity,
        )
        decision_projections = tuple(
            project_vault_decision_to_stream(
                epoch2_path=self.epoch2_path,
                stream_path=self.stream_path,
                decision_identity=decision.decision_identity,
            )
            for decision in decisions
        )

        inserted_messages = sum(
            1
            for item in decision_projections
            if item.message_disposition.value == "inserted"
        )
        if candidate_projection.message_disposition.value == "inserted":
            inserted_messages += 1

        disposition = (
            StreamCapitalForwardDisposition.INSERTED
            if inserted_decisions or hold_intents or inserted_messages
            else StreamCapitalForwardDisposition.UNCHANGED
        )
        return StreamCapitalForwardResult(
            disposition=disposition,
            activation_identity=activation_identity,
            forecast_identity=forecast.forecast_identity,
            allocator_candidate_identity=capital.candidate.candidate_identity,
            allocator_assessment_identity=capital.allocation.assessment_identity,
            decision_identities=tuple(
                decision.decision_identity for decision in decisions
            ),
            inserted_decision_count=inserted_decisions,
            hold_intent_count=hold_intents,
            projected_message_count=inserted_messages,
        )


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")


def _text(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty text")
    return value


def _integer(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be integer")
    return value
