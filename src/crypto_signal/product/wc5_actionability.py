"""WC5 read-only actionability projection from immutable WC2 cohort evidence.

This module does not create decisions. It verifies and projects one exact persisted
WC2 forecast/intent lineage for Product use. Missing or ambiguous intent evidence
fails closed as INSUFFICIENT_EVIDENCE. No notional, exposure or order authority is
inferred from the cohort journal.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_journal import (
    WC2_COHORT_SCHEMA_VERSION,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import PaperAction

WC5_ACTIONABILITY_SCHEMA_VERSION = "wc5-actionability-product-v1/1"
REAL_CAPITAL = 0

_META_TABLE = "wc2_cohort_meta"
_FORECAST_TABLE = "wc2_cohort_forecasts"
_INTENT_TABLE = "wc2_cohort_intents"


class WC5ActionabilityStatus(StrEnum):
    NO_COHORT_FORECAST = "NO_COHORT_FORECAST"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INSUFFICIENT_EVIDENCE_MULTIPLE_INTENTS = (
        "INSUFFICIENT_EVIDENCE_MULTIPLE_INTENTS"
    )
    PERSISTED_ACTION = "PERSISTED_ACTION"


@dataclass(frozen=True, slots=True)
class WC5ActionabilityTruth:
    status: WC5ActionabilityStatus
    forecast_identity: str
    proof_identity: str | None
    symbol: str | None
    regime: str | None
    issued_at_ms: int | None
    action: str | None
    intent_count: int
    intent_link_identity: str | None = None
    paper_intent_identity: str | None = None
    vault_id: str | None = None
    decided_at_ms: int | None = None
    previewed_at_ms: int | None = None
    maximum_exposure_status: str = "NOT_AVAILABLE_FROM_COHORT_INTENT"
    schema_version: str = WC5_ACTIONABILITY_SCHEMA_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.forecast_identity, "WC5 forecast identity")
        if self.proof_identity is not None:
            _require_sha256(self.proof_identity, "WC5 proof identity")
        if self.intent_count < 0:
            raise ValueError("WC5 intent count cannot be negative")
        if self.schema_version != WC5_ACTIONABILITY_SCHEMA_VERSION:
            raise ValueError("unsupported WC5 actionability schema")
        if self.maximum_exposure_status != "NOT_AVAILABLE_FROM_COHORT_INTENT":
            raise ValueError("WC5 cannot infer maximum exposure from cohort intent")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC5 Product projection cannot grant authority")

        if self.status is WC5ActionabilityStatus.PERSISTED_ACTION:
            if self.intent_count != 1 or self.action is None:
                raise ValueError("persisted WC5 action requires exactly one intent")
            PaperAction(self.action)
            for value, label in (
                (self.intent_link_identity, "WC5 intent link"),
                (self.paper_intent_identity, "WC5 paper intent"),
            ):
                if value is None:
                    raise ValueError(f"{label} missing")
                _require_sha256(value, label)
            if not self.vault_id:
                raise ValueError("WC5 persisted action vault missing")
            if self.decided_at_ms is None or self.previewed_at_ms is None:
                raise ValueError("WC5 persisted action timestamps missing")
        else:
            if self.action is not None:
                raise ValueError("insufficient WC5 evidence cannot expose action")


def read_wc5_actionability(
    path: Path,
    *,
    forecast_identity: str,
) -> WC5ActionabilityTruth:
    """Read one exact WC2 cohort actionability state without mutating SQLite."""
    _require_sha256(forecast_identity, "WC5 forecast lookup")
    if not path.is_file():
        raise FileNotFoundError(path)

    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA foreign_keys=ON")
        _require_schema(db)

        forecast_row = db.execute(
            f"""SELECT cohort_forecast_identity, proof_identity, symbol,
                       regime, issued_at_ms, payload_json
                FROM {_FORECAST_TABLE}
                WHERE forecast_identity=?
                LIMIT 1""",
            (forecast_identity,),
        ).fetchone()
        if forecast_row is None:
            return WC5ActionabilityTruth(
                status=WC5ActionabilityStatus.NO_COHORT_FORECAST,
                forecast_identity=forecast_identity,
                proof_identity=None,
                symbol=None,
                regime=None,
                issued_at_ms=None,
                action=None,
                intent_count=0,
            )

        cohort_identity = str(forecast_row["cohort_forecast_identity"])
        proof_identity = str(forecast_row["proof_identity"])
        symbol = str(forecast_row["symbol"])
        regime = str(forecast_row["regime"])
        issued_at_ms = int(forecast_row["issued_at_ms"])
        forecast_payload = _verified_payload(
            cohort_identity,
            str(forecast_row["payload_json"]),
            "WC2 cohort forecast",
        )
        if (
            forecast_payload.get("forecast_identity") != forecast_identity
            or forecast_payload.get("proof_identity") != proof_identity
            or forecast_payload.get("symbol") != symbol
            or forecast_payload.get("regime") != regime
            or int(forecast_payload.get("issued_at_ms", -1)) != issued_at_ms
        ):
            raise ValueError("WC5 cohort forecast row/payload mismatch")
        _require_authority_closed(forecast_payload, "WC2 cohort forecast")

        intent_rows = db.execute(
            f"""SELECT intent_link_identity, paper_intent_identity, vault_id,
                       action, payload_json
                FROM {_INTENT_TABLE}
                WHERE forecast_identity=?
                ORDER BY sequence_id ASC""",
            (forecast_identity,),
        ).fetchall()

    if len(intent_rows) != 1:
        status = (
            WC5ActionabilityStatus.INSUFFICIENT_EVIDENCE
            if len(intent_rows) == 0
            else WC5ActionabilityStatus.INSUFFICIENT_EVIDENCE_MULTIPLE_INTENTS
        )
        return WC5ActionabilityTruth(
            status=status,
            forecast_identity=forecast_identity,
            proof_identity=proof_identity,
            symbol=symbol,
            regime=regime,
            issued_at_ms=issued_at_ms,
            action=None,
            intent_count=len(intent_rows),
        )

    intent_row = intent_rows[0]
    intent_identity = str(intent_row["intent_link_identity"])
    intent_payload = _verified_payload(
        intent_identity,
        str(intent_row["payload_json"]),
        "WC2 cohort intent",
    )
    _require_authority_closed(intent_payload, "WC2 cohort intent")
    action = PaperAction(str(intent_payload.get("action"))).value
    if (
        intent_payload.get("forecast_identity") != forecast_identity
        or intent_payload.get("proof_identity") != proof_identity
        or intent_payload.get("cohort_forecast_identity") != cohort_identity
        or intent_payload.get("paper_intent_identity")
        != str(intent_row["paper_intent_identity"])
        or intent_payload.get("vault_id") != str(intent_row["vault_id"])
        or action != str(intent_row["action"])
    ):
        raise ValueError("WC5 cohort intent row/payload mismatch")

    return WC5ActionabilityTruth(
        status=WC5ActionabilityStatus.PERSISTED_ACTION,
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        symbol=symbol,
        regime=regime,
        issued_at_ms=issued_at_ms,
        action=action,
        intent_count=1,
        intent_link_identity=intent_identity,
        paper_intent_identity=str(intent_row["paper_intent_identity"]),
        vault_id=str(intent_row["vault_id"]),
        decided_at_ms=int(intent_payload["decided_at_ms"]),
        previewed_at_ms=int(intent_payload["previewed_at_ms"]),
    )


def _require_schema(db: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in db.execute(
            """SELECT name FROM sqlite_master
               WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
        ).fetchall()
    }
    required = {_META_TABLE, _FORECAST_TABLE, _INTENT_TABLE}
    if not required.issubset(tables):
        raise ValueError("WC5 actionability requires canonical WC2 cohort tables")
    row = db.execute(
        f"SELECT value FROM {_META_TABLE} WHERE key='schema_version'"
    ).fetchone()
    if row is None or str(row[0]) != WC2_COHORT_SCHEMA_VERSION:
        raise ValueError("WC5 actionability WC2 cohort schema mismatch")


def _verified_payload(identity: str, payload_json: str, label: str) -> dict[str, object]:
    _require_sha256(identity, f"{label} identity")
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError(f"{label} payload must be object")
    if canonical_sha256(raw) != identity:
        raise ValueError(f"{label} payload identity mismatch")
    return raw


def _require_authority_closed(payload: dict[str, object], label: str) -> None:
    if payload.get("production_authority") is True:
        raise ValueError(f"{label} unexpectedly grants production authority")
    if payload.get("real_capital") != REAL_CAPITAL:
        raise ValueError(f"{label} REAL_CAPITAL boundary mismatch")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
