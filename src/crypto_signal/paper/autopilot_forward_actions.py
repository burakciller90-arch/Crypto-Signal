"""FP3-C preregistered action bridge over canonical S11/R21/R22 truth.

The bridge never executes a real order and never owns accounting. It validates
an immutable preregistered action intent, preflights exact R22 lineage, delegates
all canonical mutation to the existing S11 BUY/SELL commit functions, projects
the persisted bundle through accepted Stream lifecycle projectors, and stores
only an isolated FP3-C orchestration receipt. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import cast

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.paper.autopilot_forward_runtime import (
    FP3AutopilotReceipt,
    FP3AutopilotStore,
)
from crypto_signal.paper.autopilot_forward_sizing import (
    FP3SizingStageReceipt,
    FP3SizingStageStatus,
    FP3SizingStageStore,
)
from crypto_signal.paper.canonical_capital_runtime import (
    CanonicalCapitalCommitResult,
    CanonicalCapitalSellCommitResult,
    commit_canonical_paper_buy,
    commit_canonical_paper_sell,
    read_canonical_active_buy_entries,
)
from crypto_signal.paper.canonical_sizing import CanonicalPaperSizingSelection
from crypto_signal.paper.canonical_vault_eligibility import CanonicalVaultEligibilityProof
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.execution import FrozenExecutionSnapshot
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol
from crypto_signal.paper.position_sizing_intelligence import PositionSizingAssessment
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.intelligence_stream_capital_lifecycle import (
    project_capital_bundle_lifecycle_to_stream,
)
from crypto_signal.product.intelligence_stream_ledger import IntelligenceStreamLedger
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

FP3_ACTION_SCHEMA_VERSION = "fp3-preregistered-action-bridge-v1/1"
FP3_ACTION_POLICY_V1 = "fp3-preregistered-action-policy-v1/1"
FP3_ACTION_POLICY_VERSION = "fp3-preregistered-action-policy-v2/1"
FP3_ACTION_ENGINE_V1 = "fp3-preregistered-action-engine-v1/1"
FP3_ACTION_ENGINE_VERSION = "fp3-preregistered-action-engine-v2/1"
_ACTION_RECEIPT_TABLE = "fp3_paper_autopilot_action_receipts"


class FP3ActionReason(StrEnum):
    OPEN = "OPEN"
    SCALE_IN = "SCALE_IN"
    PARTIAL_TAKE_PROFIT = "PARTIAL_TAKE_PROFIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP = "STOP"
    CLOSE = "CLOSE"
    WAIT = "WAIT"
    STOP_UPDATE = "STOP_UPDATE"


class FP3ActionStageStatus(StrEnum):
    NO_TRADE = "NO_TRADE"
    UNAVAILABLE = "UNAVAILABLE"
    COMMITTED = "COMMITTED"


class FP3ActionProcessDisposition(StrEnum):
    INSERTED = "inserted"
    RECOVERED = "recovered"
    REPLAYED = "replayed"
    WAITED = "waited"
    UNAVAILABLE = "unavailable"


_REASON_ACTION_V1: dict[FP3ActionReason, PaperAction | None] = {
    FP3ActionReason.OPEN: PaperAction.BUY,
    FP3ActionReason.SCALE_IN: None,
    FP3ActionReason.PARTIAL_TAKE_PROFIT: PaperAction.REDUCE,
    FP3ActionReason.TAKE_PROFIT: PaperAction.EXIT,
    FP3ActionReason.STOP: PaperAction.EXIT,
    FP3ActionReason.CLOSE: PaperAction.EXIT,
    FP3ActionReason.WAIT: None,
    FP3ActionReason.STOP_UPDATE: None,
}

_REASON_ACTION: dict[FP3ActionReason, PaperAction | None] = {
    **_REASON_ACTION_V1,
    FP3ActionReason.SCALE_IN: PaperAction.BUY,
}


def _reason_actions_for_policy(
    policy_version: str,
) -> dict[FP3ActionReason, PaperAction | None]:
    if policy_version == FP3_ACTION_POLICY_V1:
        return _REASON_ACTION_V1
    if policy_version == FP3_ACTION_POLICY_VERSION:
        return _REASON_ACTION
    raise ValueError("unsupported FP3-C action policy")


def _reason_actions_for_engine(
    engine_version: str,
) -> dict[FP3ActionReason, PaperAction | None]:
    if engine_version == FP3_ACTION_ENGINE_V1:
        return _REASON_ACTION_V1
    if engine_version == FP3_ACTION_ENGINE_VERSION:
        return _REASON_ACTION
    raise ValueError("unsupported FP3-C action engine")

_EXIT_REASON_CODES: dict[FP3ActionReason, tuple[str, ...]] = {
    FP3ActionReason.PARTIAL_TAKE_PROFIT: ("partial_take_profit",),
    FP3ActionReason.TAKE_PROFIT: ("take_profit",),
    FP3ActionReason.STOP: ("stop",),
    FP3ActionReason.CLOSE: ("close",),
}


@dataclass(frozen=True, slots=True)
class FP3PreregisteredActionIntent:
    action_intent_identity: str
    policy_version: str
    front_receipt_identity: str
    sizing_receipt_identity: str | None
    forecast_identity: str
    proof_identity: str
    vault_id: PaperVaultId
    symbol: PaperSymbol
    reason: FP3ActionReason
    canonical_action: PaperAction | None
    action_evidence_identity: str
    exit_reason_codes: tuple[str, ...]
    quantity: Decimal | None
    requested_at_ms: int
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = FP3_ACTION_SCHEMA_VERSION
    engine_version: str = FP3_ACTION_ENGINE_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.action_intent_identity, "FP3-C action intent"),
            (self.front_receipt_identity, "FP3-C front receipt"),
            (self.forecast_identity, "FP3-C forecast"),
            (self.proof_identity, "FP3-C proof"),
            (self.action_evidence_identity, "FP3-C action evidence"),
        ):
            _require_sha256(value, label)
        if self.sizing_receipt_identity is not None:
            _require_sha256(self.sizing_receipt_identity, "FP3-C sizing receipt")
        reason_actions = _reason_actions_for_policy(self.policy_version)
        if (
            self.policy_version == FP3_ACTION_POLICY_V1
            and self.engine_version != FP3_ACTION_ENGINE_V1
        ) or (
            self.policy_version == FP3_ACTION_POLICY_VERSION
            and self.engine_version != FP3_ACTION_ENGINE_VERSION
        ):
            raise ValueError("FP3-C action policy/engine version mismatch")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("FP3-C action intent requires canonical vault")
        if not isinstance(self.symbol, PaperSymbol):
            raise TypeError("FP3-C action intent requires canonical symbol")
        if not isinstance(self.reason, FP3ActionReason):
            raise TypeError("FP3-C action intent requires preregistered reason")
        expected_action = reason_actions[self.reason]
        if self.canonical_action is not expected_action:
            raise ValueError("FP3-C reason/action policy mismatch")
        expected_exit_codes = _EXIT_REASON_CODES.get(self.reason, ())
        if self.exit_reason_codes != expected_exit_codes:
            raise ValueError("FP3-C exit reason codes differ from preregistered policy")
        _require_non_negative_int(self.requested_at_ms, "FP3-C requested time")
        trade_reason = self.canonical_action is not None
        if trade_reason and self.sizing_receipt_identity is None:
            raise ValueError("FP3-C trade intent requires accepted FP3-B receipt")
        if not trade_reason and self.sizing_receipt_identity is not None:
            raise ValueError("FP3-C no-trade intent cannot invent sizing receipt")
        if self.reason in {FP3ActionReason.OPEN, FP3ActionReason.SCALE_IN}:
            if self.quantity is not None:
                raise ValueError("FP3-C BUY action quantity comes from canonical sizing")
        elif (
            self.reason is FP3ActionReason.PARTIAL_TAKE_PROFIT
            and (
                not isinstance(self.quantity, Decimal)
                or not self.quantity.is_finite()
                or self.quantity <= 0
            )
        ):
            raise ValueError("FP3-C partial take profit requires positive quantity")
        elif (
            self.reason
            in {
                FP3ActionReason.TAKE_PROFIT,
                FP3ActionReason.STOP,
                FP3ActionReason.CLOSE,
                FP3ActionReason.WAIT,
                FP3ActionReason.STOP_UPDATE,
            }
            and self.quantity is not None
        ):
            raise ValueError("FP3-C action requires omitted quantity")
        _require_authority_boundary(
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.schema_version != FP3_ACTION_SCHEMA_VERSION:
            raise ValueError("unsupported FP3-C action schema")
        _reason_actions_for_engine(self.engine_version)
        if canonical_sha256(_action_intent_payload(self)) != self.action_intent_identity:
            raise ValueError("FP3-C action intent identity mismatch")


@dataclass(frozen=True, slots=True)
class FP3ActionStageReceipt:
    receipt_identity: str
    action_intent_identity: str
    front_receipt_identity: str
    sizing_receipt_identity: str | None
    forecast_identity: str
    proof_identity: str
    vault_id: PaperVaultId
    symbol: PaperSymbol
    reason: FP3ActionReason
    canonical_action: PaperAction | None
    action_evidence_identity: str
    exit_reason_codes: tuple[str, ...]
    quantity: Decimal | None
    requested_at_ms: int
    processed_at_ms: int
    stage_status: FP3ActionStageStatus
    r22_intent_identity: str | None
    r22_fill_identity: str | None
    r22_bundle_identity: str | None
    outcome_identity: str | None
    after_vault_snapshot_identity: str | None
    after_consolidated_snapshot_identity: str | None
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = FP3_ACTION_SCHEMA_VERSION
    engine_version: str = FP3_ACTION_ENGINE_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.receipt_identity, "FP3-C action receipt"),
            (self.action_intent_identity, "FP3-C action intent"),
            (self.front_receipt_identity, "FP3-C front receipt"),
            (self.forecast_identity, "FP3-C forecast"),
            (self.proof_identity, "FP3-C proof"),
            (self.action_evidence_identity, "FP3-C action evidence"),
        ):
            _require_sha256(value, label)
        for optional_identity, label in (
            (self.sizing_receipt_identity, "FP3-C sizing receipt"),
            (self.r22_intent_identity, "FP3-C R22 intent"),
            (self.r22_fill_identity, "FP3-C R22 fill"),
            (self.r22_bundle_identity, "FP3-C R22 bundle"),
            (self.outcome_identity, "FP3-C outcome"),
            (self.after_vault_snapshot_identity, "FP3-C vault snapshot"),
            (
                self.after_consolidated_snapshot_identity,
                "FP3-C consolidated snapshot",
            ),
        ):
            if optional_identity is not None:
                _require_sha256(optional_identity, label)
        _require_non_negative_int(self.requested_at_ms, "FP3-C requested time")
        _require_non_negative_int(self.processed_at_ms, "FP3-C processed time")
        if self.processed_at_ms < self.requested_at_ms:
            raise ValueError("FP3-C processed time cannot predate action request")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("FP3-C receipt requires canonical vault")
        if not isinstance(self.symbol, PaperSymbol):
            raise TypeError("FP3-C receipt requires canonical symbol")
        expected_action = _reason_actions_for_engine(self.engine_version)[self.reason]
        if self.canonical_action is not expected_action:
            raise ValueError("FP3-C receipt reason/action mismatch")
        if self.exit_reason_codes != _EXIT_REASON_CODES.get(self.reason, ()):
            raise ValueError("FP3-C receipt exit reasons mismatch")
        trade_ids = (
            self.r22_intent_identity,
            self.r22_fill_identity,
            self.r22_bundle_identity,
            self.after_vault_snapshot_identity,
            self.after_consolidated_snapshot_identity,
        )
        if self.stage_status is FP3ActionStageStatus.COMMITTED:
            if self.canonical_action is None or any(item is None for item in trade_ids):
                raise ValueError("FP3-C committed receipt requires canonical trade lineage")
            if self.canonical_action is PaperAction.BUY and self.outcome_identity is not None:
                raise ValueError("FP3-C BUY receipt cannot invent sell outcome")
            if (
                self.canonical_action in {PaperAction.REDUCE, PaperAction.EXIT}
                and self.outcome_identity is None
            ):
                raise ValueError("FP3-C sell receipt requires canonical outcome")
        elif self.stage_status in {
            FP3ActionStageStatus.NO_TRADE,
            FP3ActionStageStatus.UNAVAILABLE,
        }:
            if self.canonical_action is not None or any(item is not None for item in trade_ids):
                raise ValueError("FP3-C no-trade receipt cannot invent canonical trade")
            if self.outcome_identity is not None:
                raise ValueError("FP3-C no-trade receipt cannot invent outcome")
        else:
            raise ValueError("unsupported FP3-C stage status")
        _require_authority_boundary(
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.schema_version != FP3_ACTION_SCHEMA_VERSION:
            raise ValueError("unsupported FP3-C receipt schema")
        _reason_actions_for_engine(self.engine_version)
        if canonical_sha256(_action_receipt_payload(self)) != self.receipt_identity:
            raise ValueError("FP3-C action receipt identity mismatch")


@dataclass(frozen=True, slots=True)
class FP3ActionProcessResult:
    disposition: FP3ActionProcessDisposition
    receipt: FP3ActionStageReceipt
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_authority_boundary(
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )


def build_fp3_action_intent(
    *,
    front_receipt_identity: str,
    sizing_receipt_identity: str | None,
    forecast_identity: str,
    proof_identity: str,
    vault_id: PaperVaultId,
    symbol: PaperSymbol,
    reason: FP3ActionReason,
    action_evidence_identity: str,
    requested_at_ms: int,
    quantity: Decimal | None = None,
) -> FP3PreregisteredActionIntent:
    action = _REASON_ACTION[reason]
    exit_codes = _EXIT_REASON_CODES.get(reason, ())
    payload = {
        "action_evidence_identity": action_evidence_identity,
        "canonical_action": action,
        "engine_version": FP3_ACTION_ENGINE_VERSION,
        "exit_reason_codes": exit_codes,
        "forecast_identity": forecast_identity,
        "front_receipt_identity": front_receipt_identity,
        "policy_version": FP3_ACTION_POLICY_VERSION,
        "production_authority": False,
        "proof_identity": proof_identity,
        "quantity": quantity,
        "real_capital": REAL_CAPITAL,
        "reason": reason,
        "requested_at_ms": requested_at_ms,
        "schema_version": FP3_ACTION_SCHEMA_VERSION,
        "sizing_receipt_identity": sizing_receipt_identity,
        "symbol": symbol,
        "vault_id": vault_id,
    }
    return FP3PreregisteredActionIntent(
        action_intent_identity=canonical_sha256(payload),
        policy_version=FP3_ACTION_POLICY_VERSION,
        front_receipt_identity=front_receipt_identity,
        sizing_receipt_identity=sizing_receipt_identity,
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        vault_id=vault_id,
        symbol=symbol,
        reason=reason,
        canonical_action=action,
        action_evidence_identity=action_evidence_identity,
        exit_reason_codes=exit_codes,
        quantity=quantity,
        requested_at_ms=requested_at_ms,
    )


class FP3ActionStageStore:
    """Append-only FP3-C action receipts inside the isolated FP3 store."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.base = FP3AutopilotStore(path)

    def initialize(self) -> None:
        self.base.initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_ACTION_RECEIPT_TABLE} (
                    receipt_identity TEXT PRIMARY KEY,
                    action_intent_identity TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                    {_ACTION_RECEIPT_TABLE}_immutable_{operation.lower()}
                    BEFORE {operation} ON {_ACTION_RECEIPT_TABLE}
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable FP3 action stage truth'
                        );
                    END
                    """
                )

    def append(self, receipt: FP3ActionStageReceipt) -> bool:
        self.initialize()
        payload_json = canonical_json(receipt)
        digest = sha256_text(payload_json)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                f"""
                SELECT receipt_identity, action_intent_identity,
                       payload_json, payload_sha256
                FROM {_ACTION_RECEIPT_TABLE}
                WHERE receipt_identity = ? OR action_intent_identity = ?
                LIMIT 1
                """,
                (receipt.receipt_identity, receipt.action_intent_identity),
            ).fetchone()
            if row is not None:
                existing = _verified_action_receipt_row(row)
                if existing == receipt:
                    return False
                raise ValueError("immutable FP3-C action receipt conflict")
            connection.execute(
                f"""
                INSERT INTO {_ACTION_RECEIPT_TABLE}(
                    receipt_identity,
                    action_intent_identity,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    receipt.receipt_identity,
                    receipt.action_intent_identity,
                    payload_json,
                    digest,
                ),
            )
        return True

    def read(self, action_intent_identity: str) -> FP3ActionStageReceipt | None:
        _require_sha256(action_intent_identity, "FP3-C action receipt lookup")
        if not self.path.is_file():
            return None
        with closing(_connect_read_only(self.path)) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if _ACTION_RECEIPT_TABLE not in tables:
                return None
            row = connection.execute(
                f"""
                SELECT receipt_identity, action_intent_identity,
                       payload_json, payload_sha256
                FROM {_ACTION_RECEIPT_TABLE}
                WHERE action_intent_identity = ?
                """,
                (action_intent_identity,),
            ).fetchone()
        return None if row is None else _verified_action_receipt_row(row)


class FP3PreregisteredActionBridge:
    """FP3-C owner for preregistered action -> canonical S11 commit."""

    def __init__(
        self,
        *,
        epoch2_path: Path,
        stream_path: Path,
        autopilot_path: Path,
    ) -> None:
        self.epoch2_path = epoch2_path
        self.stream_path = stream_path
        self.autopilot_store = FP3AutopilotStore(autopilot_path)
        self.sizing_store = FP3SizingStageStore(autopilot_path)
        self.action_store = FP3ActionStageStore(autopilot_path)

    def process_no_trade(
        self,
        intent: FP3PreregisteredActionIntent,
        *,
        processed_at_ms: int,
    ) -> FP3ActionProcessResult:
        legacy_scale_in = (
            intent.reason is FP3ActionReason.SCALE_IN
            and intent.canonical_action is None
            and intent.policy_version == FP3_ACTION_POLICY_V1
        )
        if (
            intent.reason not in {FP3ActionReason.WAIT, FP3ActionReason.STOP_UPDATE}
            and not legacy_scale_in
        ):
            raise ValueError("FP3-C no-trade API accepts WAIT/STOP_UPDATE only")
        front = self.autopilot_store.read_receipt_for_forecast(intent.forecast_identity)
        if front is None:
            raise ValueError("FP3-C requires accepted FP3-A receipt")
        _validate_front_intent(front, intent)
        existing = self.action_store.read(intent.action_intent_identity)
        if existing is not None:
            return FP3ActionProcessResult(
                disposition=FP3ActionProcessDisposition.REPLAYED,
                receipt=existing,
            )
        status = (
            FP3ActionStageStatus.NO_TRADE
            if intent.reason is FP3ActionReason.WAIT
            else FP3ActionStageStatus.UNAVAILABLE
        )
        receipt = _build_action_receipt(
            intent=intent,
            processed_at_ms=processed_at_ms,
            stage_status=status,
            context=None,
        )
        self.action_store.append(receipt)
        return FP3ActionProcessResult(
            disposition=(
                FP3ActionProcessDisposition.WAITED
                if status is FP3ActionStageStatus.NO_TRADE
                else FP3ActionProcessDisposition.UNAVAILABLE
            ),
            receipt=receipt,
        )

    def process_buy(
        self,
        intent: FP3PreregisteredActionIntent,
        issuance: UnifiedDecisionIssuance,
        *,
        sizing_assessment: PositionSizingAssessment,
        sizing_selection: CanonicalPaperSizingSelection,
        eligibility_proof: CanonicalVaultEligibilityProof,
        reference_price: Decimal,
        reference_price_evidence_identity: str,
        mark_prices: Mapping[PaperSymbol, Decimal],
        mark_evidence_identity: str,
        execution_snapshot: FrozenExecutionSnapshot,
        filled_at_ms: int,
        mutated_at_ms: int,
        snapshot_at_ms: int,
        processed_at_ms: int,
    ) -> FP3ActionProcessResult:
        if (
            intent.canonical_action is not PaperAction.BUY
            or intent.reason not in {FP3ActionReason.OPEN, FP3ActionReason.SCALE_IN}
        ):
            raise ValueError("FP3-C BUY API requires OPEN or SCALE_IN intent")
        front, sizing = self._validate_trade_inputs(
            intent,
            issuance=issuance,
            sizing_assessment=sizing_assessment,
        )
        if (
            sizing.selection_identity != sizing_selection.selection_identity
            or sizing.sizing_event_identity is None
            or sizing.sizing_event_identity != intent.action_evidence_identity
            or sizing.eligibility_proof_identity != eligibility_proof.proof_identity
            or sizing.sizing_assessment_identity != sizing_assessment.assessment_identity
            or sizing.fixed_fractional_result_identity
            != sizing_selection.sizing_result_identity
        ):
            raise ValueError("FP3-C BUY inputs differ from accepted FP3-B sizing")
        existing_receipt = self.action_store.read(intent.action_intent_identity)
        if existing_receipt is not None:
            return FP3ActionProcessResult(
                disposition=FP3ActionProcessDisposition.REPLAYED,
                receipt=existing_receipt,
            )
        existing_bundle = _find_existing_exact_trade_bundle(
            epoch2_path=self.epoch2_path,
            vault_id=intent.vault_id,
            symbol=intent.symbol,
            action=PaperAction.BUY,
            forecast_identity=intent.forecast_identity,
            proof_identity=intent.proof_identity,
            sizing_assessment_identity=sizing_assessment.assessment_identity,
            sizing_result_identity=sizing.fixed_fractional_result_identity,
            action_evidence_identity=intent.action_evidence_identity,
            requested_at_ms=intent.requested_at_ms,
            exit_reason_codes=(),
        )
        if existing_bundle is not None:
            return self._recover_trade(
                intent=intent,
                processed_at_ms=processed_at_ms,
                bundle_identity=existing_bundle,
            )

        current_quantity = _current_position_quantity(
            self.epoch2_path,
            vault_id=intent.vault_id,
            symbol=intent.symbol,
        )
        if intent.reason is FP3ActionReason.OPEN:
            if current_quantity != Decimal(0):
                raise ValueError("FP3-C OPEN requires zero current position")
        else:
            if current_quantity <= Decimal(0):
                raise ValueError("FP3-C SCALE_IN requires positive current position")
            active_entries = read_canonical_active_buy_entries(
                epoch2_path=self.epoch2_path,
                vault_id=intent.vault_id,
                symbol=intent.symbol,
            )
            if not active_entries:
                raise ValueError("FP3-C SCALE_IN requires exact active BUY lineage")
            for entry in active_entries:
                if (
                    entry.forecast_identity == intent.forecast_identity
                    or entry.proof_identity == intent.proof_identity
                    or entry.sizing_assessment_identity
                    == sizing_assessment.assessment_identity
                ):
                    raise ValueError(
                        "FP3-C SCALE_IN requires distinct forecast/proof/sizing lineage"
                    )
            if intent.requested_at_ms <= max(
                entry.decided_at_ms for entry in active_entries
            ):
                raise ValueError("FP3-C SCALE_IN must follow all active BUY decisions")
        if sizing.front_receipt_identity != front.receipt_identity:
            raise ValueError("FP3-C sizing/front receipt mismatch")

        result = commit_canonical_paper_buy(
            epoch2_path=self.epoch2_path,
            forecast=issuance.forecast,
            proof=issuance.proof,
            sizing_assessment=sizing_assessment,
            sizing_selection=sizing_selection,
            eligibility_proof=eligibility_proof,
            symbol=intent.symbol,
            reference_price=reference_price,
            reference_price_evidence_identity=reference_price_evidence_identity,
            mark_prices=mark_prices,
            mark_evidence_identity=mark_evidence_identity,
            execution_snapshot=execution_snapshot,
            decided_at_ms=intent.requested_at_ms,
            filled_at_ms=filled_at_ms,
            mutated_at_ms=mutated_at_ms,
            snapshot_at_ms=snapshot_at_ms,
            additional_source_evidence_identities=(intent.action_evidence_identity,),
            additional_reason_codes=(f"fp3_action_{intent.reason.value.lower()}",),
        )
        return self._finalize_buy(
            intent=intent,
            result=result,
            processed_at_ms=processed_at_ms,
        )

    def process_sell(
        self,
        intent: FP3PreregisteredActionIntent,
        issuance: UnifiedDecisionIssuance,
        *,
        sizing_assessment: PositionSizingAssessment,
        reference_price: Decimal,
        reference_price_evidence_identity: str,
        mark_prices: Mapping[PaperSymbol, Decimal],
        mark_evidence_identity: str,
        execution_snapshot: FrozenExecutionSnapshot,
        filled_at_ms: int,
        mutated_at_ms: int,
        snapshot_at_ms: int,
        processed_at_ms: int,
    ) -> FP3ActionProcessResult:
        if intent.canonical_action not in {PaperAction.REDUCE, PaperAction.EXIT}:
            raise ValueError("FP3-C SELL API requires preregistered REDUCE/EXIT intent")
        _, sizing = self._validate_trade_inputs(
            intent,
            issuance=issuance,
            sizing_assessment=sizing_assessment,
        )
        if sizing.sizing_assessment_identity != sizing_assessment.assessment_identity:
            raise ValueError("FP3-C sell sizing assessment differs from FP3-B")
        existing_receipt = self.action_store.read(intent.action_intent_identity)
        if existing_receipt is not None:
            return FP3ActionProcessResult(
                disposition=FP3ActionProcessDisposition.REPLAYED,
                receipt=existing_receipt,
            )
        existing_bundle = _find_existing_exact_trade_bundle(
            epoch2_path=self.epoch2_path,
            vault_id=intent.vault_id,
            symbol=intent.symbol,
            action=cast(PaperAction, intent.canonical_action),
            forecast_identity=intent.forecast_identity,
            proof_identity=intent.proof_identity,
            sizing_assessment_identity=sizing_assessment.assessment_identity,
            sizing_result_identity=sizing.fixed_fractional_result_identity,
            action_evidence_identity=intent.action_evidence_identity,
            requested_at_ms=intent.requested_at_ms,
            exit_reason_codes=intent.exit_reason_codes,
        )
        if existing_bundle is not None:
            return self._recover_trade(
                intent=intent,
                processed_at_ms=processed_at_ms,
                bundle_identity=existing_bundle,
            )

        result = commit_canonical_paper_sell(
            epoch2_path=self.epoch2_path,
            action=cast(PaperAction, intent.canonical_action),
            forecast=issuance.forecast,
            proof=issuance.proof,
            sizing_assessment=sizing_assessment,
            symbol=intent.symbol,
            quantity=intent.quantity,
            reference_price=reference_price,
            reference_price_evidence_identity=reference_price_evidence_identity,
            exit_evidence_identity=intent.action_evidence_identity,
            exit_reason_codes=intent.exit_reason_codes,
            mark_prices=mark_prices,
            mark_evidence_identity=mark_evidence_identity,
            execution_snapshot=execution_snapshot,
            decided_at_ms=intent.requested_at_ms,
            filled_at_ms=filled_at_ms,
            mutated_at_ms=mutated_at_ms,
            snapshot_at_ms=snapshot_at_ms,
            additional_source_evidence_identities=(intent.action_evidence_identity,),
        )
        return self._finalize_sell(
            intent=intent,
            result=result,
            processed_at_ms=processed_at_ms,
        )

    def _validate_trade_inputs(
        self,
        intent: FP3PreregisteredActionIntent,
        *,
        issuance: UnifiedDecisionIssuance,
        sizing_assessment: PositionSizingAssessment,
    ) -> tuple[FP3AutopilotReceipt, FP3SizingStageReceipt]:
        front = self.autopilot_store.read_receipt_for_forecast(intent.forecast_identity)
        if front is None:
            raise ValueError("FP3-C requires accepted FP3-A receipt")
        _validate_front_intent(front, intent)
        if (
            issuance.forecast.forecast_identity != intent.forecast_identity
            or issuance.proof.proof_identity != intent.proof_identity
        ):
            raise ValueError("FP3-C issuance differs from preregistered action")
        stream_context = IntelligenceStreamLedger(
            self.stream_path
        ).read_context_for_forecast(intent.forecast_identity)
        if stream_context is None:
            raise ValueError(
                "FP3-C requires existing forward Stream decision context"
            )
        if (
            stream_context.get("forecast_identity") != intent.forecast_identity
            or stream_context.get("proof_identity") != intent.proof_identity
        ):
            raise ValueError("FP3-C Stream decision context lineage mismatch")
        sizing = self.sizing_store.read(
            forecast_identity=intent.forecast_identity,
            vault_id=intent.vault_id,
        )
        if sizing is None or sizing.stage_status is not FP3SizingStageStatus.SIZED:
            raise ValueError("FP3-C requires accepted sized FP3-B receipt")
        if sizing.receipt_identity != intent.sizing_receipt_identity:
            raise ValueError("FP3-C action intent sizing receipt mismatch")
        if sizing.forecast_identity != intent.forecast_identity:
            raise ValueError("FP3-C sizing forecast mismatch")
        if sizing.proof_identity != intent.proof_identity:
            raise ValueError("FP3-C sizing proof mismatch")
        if sizing.front_receipt_identity != intent.front_receipt_identity:
            raise ValueError("FP3-C sizing/front lineage mismatch")
        if sizing.sizing_assessment_identity != sizing_assessment.assessment_identity:
            raise ValueError("FP3-C sizing assessment mismatch")
        return front, sizing

    def _recover_trade(
        self,
        *,
        intent: FP3PreregisteredActionIntent,
        processed_at_ms: int,
        bundle_identity: str,
    ) -> FP3ActionProcessResult:
        project_capital_bundle_lifecycle_to_stream(
            epoch2_path=self.epoch2_path,
            stream_path=self.stream_path,
            bundle_identity=bundle_identity,
        )
        context = R22Epoch2AtomicTape(self.epoch2_path).read_bundle_story_context(
            bundle_identity
        )
        receipt = _build_action_receipt(
            intent=intent,
            processed_at_ms=processed_at_ms,
            stage_status=FP3ActionStageStatus.COMMITTED,
            context=context,
        )
        self.action_store.append(receipt)
        return FP3ActionProcessResult(
            disposition=FP3ActionProcessDisposition.RECOVERED,
            receipt=receipt,
        )

    def _finalize_buy(
        self,
        *,
        intent: FP3PreregisteredActionIntent,
        result: CanonicalCapitalCommitResult,
        processed_at_ms: int,
    ) -> FP3ActionProcessResult:
        project_capital_bundle_lifecycle_to_stream(
            epoch2_path=self.epoch2_path,
            stream_path=self.stream_path,
            bundle_identity=result.accounting_bundle_identity,
        )
        context = R22Epoch2AtomicTape(self.epoch2_path).read_bundle_story_context(
            result.accounting_bundle_identity
        )
        receipt = _build_action_receipt(
            intent=intent,
            processed_at_ms=processed_at_ms,
            stage_status=FP3ActionStageStatus.COMMITTED,
            context=context,
        )
        self.action_store.append(receipt)
        return FP3ActionProcessResult(
            disposition=(
                FP3ActionProcessDisposition.INSERTED
                if result.inserted
                else FP3ActionProcessDisposition.RECOVERED
            ),
            receipt=receipt,
        )

    def _finalize_sell(
        self,
        *,
        intent: FP3PreregisteredActionIntent,
        result: CanonicalCapitalSellCommitResult,
        processed_at_ms: int,
    ) -> FP3ActionProcessResult:
        project_capital_bundle_lifecycle_to_stream(
            epoch2_path=self.epoch2_path,
            stream_path=self.stream_path,
            bundle_identity=result.accounting_bundle_identity,
        )
        context = R22Epoch2AtomicTape(self.epoch2_path).read_bundle_story_context(
            result.accounting_bundle_identity
        )
        receipt = _build_action_receipt(
            intent=intent,
            processed_at_ms=processed_at_ms,
            stage_status=FP3ActionStageStatus.COMMITTED,
            context=context,
        )
        self.action_store.append(receipt)
        return FP3ActionProcessResult(
            disposition=(
                FP3ActionProcessDisposition.INSERTED
                if result.inserted
                else FP3ActionProcessDisposition.RECOVERED
            ),
            receipt=receipt,
        )


def _validate_front_intent(
    front: FP3AutopilotReceipt,
    intent: FP3PreregisteredActionIntent,
) -> None:
    if front.receipt_identity != intent.front_receipt_identity:
        raise ValueError("FP3-C front receipt identity mismatch")
    if front.forecast_identity != intent.forecast_identity:
        raise ValueError("FP3-C front forecast mismatch")
    if front.proof_identity != intent.proof_identity:
        raise ValueError("FP3-C front proof mismatch")
    states = dict(front.decision_states)
    if intent.vault_id.value not in states:
        raise ValueError("FP3-C front receipt lost target vault")


def _find_existing_exact_trade_bundle(
    *,
    epoch2_path: Path,
    vault_id: PaperVaultId,
    symbol: PaperSymbol,
    action: PaperAction,
    forecast_identity: str,
    proof_identity: str,
    sizing_assessment_identity: str,
    sizing_result_identity: str,
    action_evidence_identity: str,
    requested_at_ms: int,
    exit_reason_codes: tuple[str, ...],
) -> str | None:
    tape = R22Epoch2AtomicTape(epoch2_path)
    matches: list[str] = []
    for item in tape.read_trade_history(vault_id, symbol):
        raw_intent = _mapping(item, "intent")
        raw_fill = _mapping(item, "fill")
        if (
            raw_intent.get("action") != action.value
            or raw_intent.get("forecast_identity") != forecast_identity
            or raw_intent.get("proof_identity") != proof_identity
            or raw_intent.get("sizing_assessment_identity")
            != sizing_assessment_identity
            or raw_intent.get("sizing_decision_identity") != sizing_result_identity
            or raw_intent.get("symbol") != symbol.value
            or raw_intent.get("decided_at_ms") != requested_at_ms
        ):
            continue
        source_ids = _string_set(raw_intent.get("source_evidence_identities"))
        if action_evidence_identity not in source_ids:
            continue
        reason_codes = _string_set(raw_intent.get("reason_codes"))
        if not set(exit_reason_codes).issubset(reason_codes):
            continue
        fill_identity = _required_text(raw_fill, "fill_identity")
        bundle_identity = tape.read_bundle_identity_for_fill(fill_identity)
        if bundle_identity is None:
            raise ValueError("FP3-C canonical fill lost R22 bundle")
        matches.append(bundle_identity)
    if len(matches) > 1:
        raise ValueError("FP3-C exact replay matched multiple canonical bundles")
    return None if not matches else matches[0]


def _current_position_quantity(
    epoch2_path: Path,
    *,
    vault_id: PaperVaultId,
    symbol: PaperSymbol,
) -> Decimal:
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    vaults = tuple(item for item in state.vault_snapshots if item.vault_id is vault_id)
    if len(vaults) != 1:
        raise ValueError("FP3-C target vault state is not unique")
    return sum(
        (item.quantity for item in vaults[0].positions if item.symbol is symbol),
        Decimal(0),
    )


def _build_action_receipt(
    *,
    intent: FP3PreregisteredActionIntent,
    processed_at_ms: int,
    stage_status: FP3ActionStageStatus,
    context: Mapping[str, object] | None,
) -> FP3ActionStageReceipt:
    r22_intent_identity = None
    r22_fill_identity = None
    r22_bundle_identity = None
    outcome_identity = None
    after_vault_snapshot_identity = None
    after_consolidated_snapshot_identity = None
    if context is not None:
        bundle = _mapping(context, "bundle")
        raw_intent = _mapping(context, "intent")
        fill = _mapping(context, "fill")
        after_vault = _mapping(context, "after_vault")
        after_parent = _mapping(context, "after_consolidated")
        r22_intent_identity = _required_text(raw_intent, "intent_identity")
        r22_fill_identity = _required_text(fill, "fill_identity")
        r22_bundle_identity = _required_text(bundle, "bundle_identity")
        after_vault_snapshot_identity = _required_text(
            after_vault,
            "snapshot_identity",
        )
        after_consolidated_snapshot_identity = _required_text(
            after_parent,
            "snapshot_identity",
        )
        raw_outcome = context.get("outcome")
        if raw_outcome is not None:
            outcome_identity = _required_text(
                _mapping_value(raw_outcome, "outcome"),
                "outcome_identity",
            )
    payload = {
        "action_evidence_identity": intent.action_evidence_identity,
        "action_intent_identity": intent.action_intent_identity,
        "after_consolidated_snapshot_identity": after_consolidated_snapshot_identity,
        "after_vault_snapshot_identity": after_vault_snapshot_identity,
        "canonical_action": intent.canonical_action,
        "engine_version": FP3_ACTION_ENGINE_VERSION,
        "exit_reason_codes": intent.exit_reason_codes,
        "forecast_identity": intent.forecast_identity,
        "front_receipt_identity": intent.front_receipt_identity,
        "outcome_identity": outcome_identity,
        "processed_at_ms": processed_at_ms,
        "production_authority": False,
        "proof_identity": intent.proof_identity,
        "quantity": intent.quantity,
        "r22_bundle_identity": r22_bundle_identity,
        "r22_fill_identity": r22_fill_identity,
        "r22_intent_identity": r22_intent_identity,
        "real_capital": REAL_CAPITAL,
        "reason": intent.reason,
        "requested_at_ms": intent.requested_at_ms,
        "schema_version": FP3_ACTION_SCHEMA_VERSION,
        "sizing_receipt_identity": intent.sizing_receipt_identity,
        "stage_status": stage_status,
        "symbol": intent.symbol,
        "vault_id": intent.vault_id,
    }
    return FP3ActionStageReceipt(
        receipt_identity=canonical_sha256(payload),
        action_intent_identity=intent.action_intent_identity,
        front_receipt_identity=intent.front_receipt_identity,
        sizing_receipt_identity=intent.sizing_receipt_identity,
        forecast_identity=intent.forecast_identity,
        proof_identity=intent.proof_identity,
        vault_id=intent.vault_id,
        symbol=intent.symbol,
        reason=intent.reason,
        canonical_action=intent.canonical_action,
        action_evidence_identity=intent.action_evidence_identity,
        exit_reason_codes=intent.exit_reason_codes,
        quantity=intent.quantity,
        requested_at_ms=intent.requested_at_ms,
        processed_at_ms=processed_at_ms,
        stage_status=stage_status,
        r22_intent_identity=r22_intent_identity,
        r22_fill_identity=r22_fill_identity,
        r22_bundle_identity=r22_bundle_identity,
        outcome_identity=outcome_identity,
        after_vault_snapshot_identity=after_vault_snapshot_identity,
        after_consolidated_snapshot_identity=after_consolidated_snapshot_identity,
    )


def _action_intent_payload(value: FP3PreregisteredActionIntent) -> dict[str, object]:
    return {
        "action_evidence_identity": value.action_evidence_identity,
        "canonical_action": value.canonical_action,
        "engine_version": value.engine_version,
        "exit_reason_codes": value.exit_reason_codes,
        "forecast_identity": value.forecast_identity,
        "front_receipt_identity": value.front_receipt_identity,
        "policy_version": value.policy_version,
        "production_authority": value.production_authority,
        "proof_identity": value.proof_identity,
        "quantity": value.quantity,
        "real_capital": value.real_capital,
        "reason": value.reason,
        "requested_at_ms": value.requested_at_ms,
        "schema_version": value.schema_version,
        "sizing_receipt_identity": value.sizing_receipt_identity,
        "symbol": value.symbol,
        "vault_id": value.vault_id,
    }


def _action_receipt_payload(value: FP3ActionStageReceipt) -> dict[str, object]:
    return {
        "action_evidence_identity": value.action_evidence_identity,
        "action_intent_identity": value.action_intent_identity,
        "after_consolidated_snapshot_identity": value.after_consolidated_snapshot_identity,
        "after_vault_snapshot_identity": value.after_vault_snapshot_identity,
        "canonical_action": value.canonical_action,
        "engine_version": value.engine_version,
        "exit_reason_codes": value.exit_reason_codes,
        "forecast_identity": value.forecast_identity,
        "front_receipt_identity": value.front_receipt_identity,
        "outcome_identity": value.outcome_identity,
        "processed_at_ms": value.processed_at_ms,
        "production_authority": value.production_authority,
        "proof_identity": value.proof_identity,
        "quantity": value.quantity,
        "r22_bundle_identity": value.r22_bundle_identity,
        "r22_fill_identity": value.r22_fill_identity,
        "r22_intent_identity": value.r22_intent_identity,
        "real_capital": value.real_capital,
        "reason": value.reason,
        "requested_at_ms": value.requested_at_ms,
        "schema_version": value.schema_version,
        "sizing_receipt_identity": value.sizing_receipt_identity,
        "stage_status": value.stage_status,
        "symbol": value.symbol,
        "vault_id": value.vault_id,
    }


def _verified_action_receipt_row(row: sqlite3.Row) -> FP3ActionStageReceipt:
    payload_json = str(row["payload_json"])
    if sha256_text(payload_json) != str(row["payload_sha256"]):
        raise ValueError("FP3-C action receipt payload digest mismatch")
    raw_json = json.loads(payload_json)
    if not isinstance(raw_json, dict):
        raise TypeError("FP3-C action receipt payload must be object")
    raw = cast(dict[str, object], raw_json)
    action_text = _optional_text(raw, "canonical_action")
    receipt = FP3ActionStageReceipt(
        receipt_identity=_required_text(raw, "receipt_identity"),
        action_intent_identity=_required_text(raw, "action_intent_identity"),
        front_receipt_identity=_required_text(raw, "front_receipt_identity"),
        sizing_receipt_identity=_optional_text(raw, "sizing_receipt_identity"),
        forecast_identity=_required_text(raw, "forecast_identity"),
        proof_identity=_required_text(raw, "proof_identity"),
        vault_id=PaperVaultId(_required_text(raw, "vault_id")),
        symbol=PaperSymbol(_required_text(raw, "symbol")),
        reason=FP3ActionReason(_required_text(raw, "reason")),
        canonical_action=None if action_text is None else PaperAction(action_text),
        action_evidence_identity=_required_text(raw, "action_evidence_identity"),
        exit_reason_codes=_string_tuple(raw, "exit_reason_codes"),
        quantity=_optional_decimal(raw, "quantity"),
        requested_at_ms=_required_int(raw, "requested_at_ms"),
        processed_at_ms=_required_int(raw, "processed_at_ms"),
        stage_status=FP3ActionStageStatus(_required_text(raw, "stage_status")),
        r22_intent_identity=_optional_text(raw, "r22_intent_identity"),
        r22_fill_identity=_optional_text(raw, "r22_fill_identity"),
        r22_bundle_identity=_optional_text(raw, "r22_bundle_identity"),
        outcome_identity=_optional_text(raw, "outcome_identity"),
        after_vault_snapshot_identity=_optional_text(
            raw,
            "after_vault_snapshot_identity",
        ),
        after_consolidated_snapshot_identity=_optional_text(
            raw,
            "after_consolidated_snapshot_identity",
        ),
        production_authority=_required_bool(raw, "production_authority"),
        real_capital=_required_int(raw, "real_capital"),
        schema_version=_required_text(raw, "schema_version"),
        engine_version=_required_text(raw, "engine_version"),
    )
    if str(row["receipt_identity"]) != receipt.receipt_identity:
        raise ValueError("FP3-C action receipt row identity mismatch")
    if str(row["action_intent_identity"]) != receipt.action_intent_identity:
        raise ValueError("FP3-C action receipt row intent mismatch")
    if canonical_json(receipt) != payload_json:
        raise ValueError("FP3-C action receipt canonical payload mismatch")
    return receipt


def _mapping(raw: Mapping[str, object], key: str) -> dict[str, object]:
    value = raw.get(key)
    return _mapping_value(value, key)


def _mapping_value(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be object")
    return cast(dict[str, object], value)


def _required_text(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty text")
    return value


def _optional_text(raw: Mapping[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty text when present")
    return value


def _required_int(raw: Mapping[str, object], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be int")
    return value


def _required_bool(raw: Mapping[str, object], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _string_tuple(raw: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be string array")
    return tuple(cast(list[str], value))


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("R22 string collection is malformed")
    return set(cast(list[str], value))


def _optional_decimal(raw: Mapping[str, object], key: str) -> Decimal | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be canonical Decimal text")
    return Decimal(value)


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


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
        raise ValueError("FP3-C crossed production/real-capital authority")
