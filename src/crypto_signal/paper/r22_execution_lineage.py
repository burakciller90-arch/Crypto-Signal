"""Append-only FP4 execution/funding lineage attached to immutable R22 fills.

The companion tape does not alter historical R22 rows. It binds one accepted
ExecutionReceiptV2 plus its exact FP4 execution outcome to an existing R22
accounting bundle, and can append zero or more exact funding projections for the
same immutable trade. The store is local paper evidence only: REAL_CAPITAL=0.
"""
from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.execution_depth_v2 import DepthExecutionOutcome
from crypto_signal.paper.execution_limit_v2 import PassiveLimitExecutionOutcome
from crypto_signal.paper.execution_receipt_v2 import (
    ExecutionReceiptMode,
    ExecutionReceiptStatus,
    ExecutionReceiptV2,
)
from crypto_signal.paper.funding_cost_v2 import PaperFundingCostProjection
from crypto_signal.paper.models import REAL_CAPITAL

R22_EXECUTION_LINEAGE_SCHEMA_VERSION = "r22_execution_lineage.v1"

ExecutionOutcomeV2 = DepthExecutionOutcome | PassiveLimitExecutionOutcome


def _sha(value: str, label: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
    return value


def _object(payload_json: str, label: str) -> dict[str, Any]:
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError(f"{label} must be an object")
    return cast(dict[str, Any], raw)


def _decimal(raw: object, label: str) -> Decimal:
    try:
        value = Decimal(str(raw))
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise TypeError(f"{label} must be Decimal-compatible") from exc
    if not value.is_finite():
        raise ValueError(f"{label} must be finite")
    return value


def _outcome_market_evidence(outcome: ExecutionOutcomeV2) -> tuple[str, ...]:
    if isinstance(outcome, DepthExecutionOutcome):
        return (outcome.orderbook_snapshot_identity,)
    return tuple(
        dict.fromkeys(
            (
                outcome.orderbook_snapshot_identity,
                *outcome.evidence_trade_identities,
            )
        )
    )


@dataclass(frozen=True, slots=True)
class R22ExecutionLineageRecord:
    attachment_identity: str
    bundle_identity: str
    intent_identity: str
    fill_identity: str
    execution_receipt_identity: str
    execution_outcome_identity: str
    execution_receipt: dict[str, Any]
    execution_outcome: dict[str, Any]
    funding_projections: tuple[dict[str, Any], ...]
    schema_version: str = R22_EXECUTION_LINEAGE_SCHEMA_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL


class R22ExecutionLineageTape:
    """Read/write append-only execution lineage beside existing R22 evidence."""

    def __init__(self, epoch2_path: Path) -> None:
        self.epoch2_path = Path(epoch2_path)

    def initialize(self) -> None:
        if not self.epoch2_path.is_file():
            raise ValueError("R22 Epoch2 ledger is missing")
        with closing(sqlite3.connect(self.epoch2_path)) as connection, connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS r22_execution_lineage (
                    attachment_identity TEXT PRIMARY KEY,
                    bundle_identity TEXT NOT NULL UNIQUE,
                    intent_identity TEXT NOT NULL,
                    fill_identity TEXT NOT NULL UNIQUE,
                    execution_receipt_identity TEXT NOT NULL UNIQUE,
                    execution_outcome_identity TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    outcome_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    real_capital INTEGER NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS r22_funding_lineage (
                    projection_identity TEXT PRIMARY KEY,
                    bundle_identity TEXT NOT NULL,
                    fill_identity TEXT NOT NULL,
                    projection_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    real_capital INTEGER NOT NULL,
                    UNIQUE(bundle_identity, projection_identity)
                )"""
            )
            for table in ("r22_execution_lineage", "r22_funding_lineage"):
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN
                            SELECT RAISE(ABORT, 'immutable R22 execution lineage');
                        END"""
                    )

    def append_execution(
        self,
        *,
        bundle_identity: str,
        receipt: ExecutionReceiptV2,
        outcome: ExecutionOutcomeV2,
    ) -> bool:
        _sha(bundle_identity, "R22 bundle")
        self._validate_receipt_outcome(receipt, outcome)
        self.initialize()
        with closing(sqlite3.connect(self.epoch2_path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            bundle, intent, fill = self._r22_context(connection, bundle_identity)
            self._validate_r22_fill(receipt=receipt, bundle=bundle, intent=intent, fill=fill)
            fill_identity = str(fill["fill_identity"])
            intent_identity = str(intent["intent_identity"])
            payload = {
                "bundle_identity": bundle_identity,
                "execution_outcome_identity": receipt.execution_outcome_identity,
                "execution_receipt_identity": receipt.receipt_identity,
                "fill_identity": fill_identity,
                "intent_identity": intent_identity,
                "real_capital": REAL_CAPITAL,
                "schema_version": R22_EXECUTION_LINEAGE_SCHEMA_VERSION,
            }
            attachment_identity = canonical_sha256(payload)
            receipt_json = canonical_json(receipt)
            outcome_json = canonical_json(outcome)
            existing = connection.execute(
                """SELECT attachment_identity, intent_identity, fill_identity,
                          execution_receipt_identity, execution_outcome_identity,
                          receipt_json, outcome_json, schema_version, real_capital
                   FROM r22_execution_lineage WHERE bundle_identity = ?""",
                (bundle_identity,),
            ).fetchone()
            expected = (
                attachment_identity,
                intent_identity,
                fill_identity,
                receipt.receipt_identity,
                receipt.execution_outcome_identity,
                receipt_json,
                outcome_json,
                R22_EXECUTION_LINEAGE_SCHEMA_VERSION,
                REAL_CAPITAL,
            )
            if existing is not None:
                if tuple(existing) != expected:
                    raise ValueError("R22 immutable execution-lineage conflict")
                return False
            connection.execute(
                """INSERT INTO r22_execution_lineage (
                    attachment_identity, bundle_identity, intent_identity, fill_identity,
                    execution_receipt_identity, execution_outcome_identity,
                    receipt_json, outcome_json, schema_version, real_capital
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (attachment_identity, bundle_identity, *expected[1:]),
            )
        return True

    def append_funding(
        self,
        *,
        bundle_identity: str,
        projection: PaperFundingCostProjection,
    ) -> bool:
        _sha(bundle_identity, "R22 funding bundle")
        if projection.real_capital != REAL_CAPITAL:
            raise ValueError("R22 funding lineage cannot carry real capital")
        self.initialize()
        with closing(sqlite3.connect(self.epoch2_path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            _bundle, _intent, fill = self._r22_context(connection, bundle_identity)
            if str(fill.get("symbol")) != projection.symbol.value:
                raise ValueError("R22 funding projection symbol mismatch")
            fill_identity = str(fill["fill_identity"])
            execution = connection.execute(
                "SELECT fill_identity FROM r22_execution_lineage WHERE bundle_identity = ?",
                (bundle_identity,),
            ).fetchone()
            if execution is None or str(execution[0]) != fill_identity:
                raise ValueError("R22 funding requires immutable execution lineage first")
            payload_json = canonical_json(projection)
            existing = connection.execute(
                """SELECT bundle_identity, fill_identity, projection_json,
                          schema_version, real_capital
                   FROM r22_funding_lineage WHERE projection_identity = ?""",
                (projection.projection_identity,),
            ).fetchone()
            expected = (
                bundle_identity,
                fill_identity,
                payload_json,
                R22_EXECUTION_LINEAGE_SCHEMA_VERSION,
                REAL_CAPITAL,
            )
            if existing is not None:
                if tuple(existing) != expected:
                    raise ValueError("R22 immutable funding-lineage conflict")
                return False
            connection.execute(
                """INSERT INTO r22_funding_lineage (
                    projection_identity, bundle_identity, fill_identity,
                    projection_json, schema_version, real_capital
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (projection.projection_identity, *expected),
            )
        return True

    def read_for_bundle(self, bundle_identity: str) -> R22ExecutionLineageRecord | None:
        _sha(bundle_identity, "R22 execution-lineage read bundle")
        if not self.epoch2_path.is_file():
            raise ValueError("R22 Epoch2 ledger is missing")
        uri = f"{self.epoch2_path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    """SELECT name FROM sqlite_master
                       WHERE type='table' AND name IN (
                         'r22_execution_lineage', 'r22_funding_lineage'
                       )"""
                ).fetchall()
            }
            if "r22_execution_lineage" not in tables:
                return None
            row = connection.execute(
                """SELECT attachment_identity, intent_identity, fill_identity,
                          execution_receipt_identity, execution_outcome_identity,
                          receipt_json, outcome_json, schema_version, real_capital
                   FROM r22_execution_lineage WHERE bundle_identity = ?""",
                (bundle_identity,),
            ).fetchone()
            if row is None:
                return None
            funding_rows = (
                ()
                if "r22_funding_lineage" not in tables
                else connection.execute(
                    """SELECT projection_identity, projection_json, schema_version, real_capital
                       FROM r22_funding_lineage
                       WHERE bundle_identity = ? ORDER BY projection_identity""",
                    (bundle_identity,),
                ).fetchall()
            )
        attachment_identity = _sha(str(row[0]), "R22 execution attachment")
        intent_identity = _sha(str(row[1]), "R22 execution intent")
        fill_identity = _sha(str(row[2]), "R22 execution fill")
        receipt_identity = _sha(str(row[3]), "R22 execution receipt")
        outcome_identity = _sha(str(row[4]), "R22 execution outcome")
        if str(row[7]) != R22_EXECUTION_LINEAGE_SCHEMA_VERSION or int(row[8]) != 0:
            raise ValueError("R22 execution-lineage header mismatch")
        receipt = _object(str(row[5]), "R22 execution receipt")
        outcome = _object(str(row[6]), "R22 execution outcome")
        if receipt.get("receipt_identity") != receipt_identity:
            raise ValueError("R22 execution receipt identity mismatch")
        if receipt.get("execution_outcome_identity") != outcome_identity:
            raise ValueError("R22 execution receipt/outcome lineage mismatch")
        if outcome.get("outcome_identity") != outcome_identity:
            raise ValueError("R22 execution outcome identity mismatch")
        expected_attachment = canonical_sha256(
            {
                "bundle_identity": bundle_identity,
                "execution_outcome_identity": outcome_identity,
                "execution_receipt_identity": receipt_identity,
                "fill_identity": fill_identity,
                "intent_identity": intent_identity,
                "real_capital": REAL_CAPITAL,
                "schema_version": R22_EXECUTION_LINEAGE_SCHEMA_VERSION,
            }
        )
        if attachment_identity != expected_attachment:
            raise ValueError("R22 execution attachment hash mismatch")
        funding: list[dict[str, Any]] = []
        for projection_identity_raw, payload_json, schema_version, real_capital in funding_rows:
            projection_identity = _sha(str(projection_identity_raw), "R22 funding projection")
            if str(schema_version) != R22_EXECUTION_LINEAGE_SCHEMA_VERSION or int(real_capital) != 0:
                raise ValueError("R22 funding-lineage header mismatch")
            raw = _object(str(payload_json), "R22 funding projection")
            if raw.get("projection_identity") != projection_identity or raw.get("real_capital") != 0:
                raise ValueError("R22 funding projection identity/authority mismatch")
            funding.append(raw)
        return R22ExecutionLineageRecord(
            attachment_identity=attachment_identity,
            bundle_identity=bundle_identity,
            intent_identity=intent_identity,
            fill_identity=fill_identity,
            execution_receipt_identity=receipt_identity,
            execution_outcome_identity=outcome_identity,
            execution_receipt=receipt,
            execution_outcome=outcome,
            funding_projections=tuple(funding),
        )

    @staticmethod
    def _validate_receipt_outcome(
        receipt: ExecutionReceiptV2,
        outcome: ExecutionOutcomeV2,
    ) -> None:
        if receipt.real_capital != 0 or outcome.real_capital != 0:
            raise ValueError("R22 execution lineage cannot carry real capital")
        if receipt.execution_outcome_identity != outcome.outcome_identity:
            raise ValueError("execution receipt does not bind supplied outcome")
        if receipt.action is not outcome.action:
            raise ValueError("execution receipt/outcome action mismatch")
        if receipt.requested_quantity != outcome.requested_quantity:
            raise ValueError("execution receipt/outcome requested quantity mismatch")
        if receipt.filled_quantity != outcome.filled_quantity:
            raise ValueError("execution receipt/outcome filled quantity mismatch")
        if receipt.unfilled_quantity != outcome.unfilled_quantity:
            raise ValueError("execution receipt/outcome unfilled quantity mismatch")
        if receipt.average_fill_price != outcome.average_fill_price:
            raise ValueError("execution receipt/outcome average fill mismatch")
        if receipt.status.value != outcome.status.value:
            raise ValueError("execution receipt/outcome status mismatch")
        expected_mode = (
            ExecutionReceiptMode.DEPTH
            if isinstance(outcome, DepthExecutionOutcome)
            else ExecutionReceiptMode.PASSIVE_LIMIT
        )
        if receipt.mode is not expected_mode:
            raise ValueError("execution receipt/outcome mode mismatch")
        if tuple(receipt.market_evidence_identities) != _outcome_market_evidence(outcome):
            raise ValueError("execution receipt/outcome market evidence mismatch")
        if receipt.status not in {ExecutionReceiptStatus.FULL, ExecutionReceiptStatus.PARTIAL}:
            raise ValueError("R22 fill lineage requires an actually filled execution receipt")

    @staticmethod
    def _r22_context(
        connection: sqlite3.Connection,
        bundle_identity: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        row = connection.execute(
            """SELECT b.payload_json, i.payload_json, f.payload_json
               FROM r22_epoch2_bundles AS b
               JOIN r22_epoch2_fills AS f ON f.fill_identity = b.fill_identity
               JOIN r22_epoch2_intents AS i ON i.intent_identity = f.intent_identity
               WHERE b.bundle_identity = ?""",
            (bundle_identity,),
        ).fetchone()
        if row is None:
            raise ValueError("R22 execution lineage bundle not found")
        bundle = _object(str(row[0]), "R22 execution bundle")
        intent = _object(str(row[1]), "R22 execution intent")
        fill = _object(str(row[2]), "R22 execution fill")
        if bundle.get("bundle_identity") != bundle_identity:
            raise ValueError("R22 execution bundle identity mismatch")
        if bundle.get("fill_identity") != fill.get("fill_identity"):
            raise ValueError("R22 execution bundle/fill mismatch")
        if fill.get("intent_identity") != intent.get("intent_identity"):
            raise ValueError("R22 execution fill/intent mismatch")
        if bundle.get("real_capital") != 0 or fill.get("real_capital") != 0 or intent.get("real_capital") != 0:
            raise ValueError("R22 execution source authority mismatch")
        return bundle, intent, fill

    @staticmethod
    def _validate_r22_fill(
        *,
        receipt: ExecutionReceiptV2,
        bundle: dict[str, Any],
        intent: dict[str, Any],
        fill: dict[str, Any],
    ) -> None:
        del bundle
        if str(fill.get("action")) != receipt.action.value:
            raise ValueError("R22 fill/receipt action mismatch")
        if str(intent.get("action")) != receipt.action.value:
            raise ValueError("R22 intent/receipt action mismatch")
        if str(fill.get("symbol")) != receipt.symbol.value or str(intent.get("symbol")) != receipt.symbol.value:
            raise ValueError("R22 fill/receipt symbol mismatch")
        if _decimal(fill.get("quantity"), "R22 fill quantity") != receipt.filled_quantity:
            raise ValueError("R22 fill quantity does not equal immutable receipt fill")
        if receipt.average_fill_price is None:
            raise ValueError("R22 filled receipt must expose average fill price")
        if _decimal(fill.get("simulated_fill_price"), "R22 fill price") != receipt.average_fill_price:
            raise ValueError("R22 fill price does not equal immutable receipt fill")
        if _decimal(fill.get("fee_usdt"), "R22 fill fee") != receipt.fee_usdt:
            raise ValueError("R22 fill fee does not equal immutable receipt fee")
