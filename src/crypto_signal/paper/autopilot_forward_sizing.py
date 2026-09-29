"""FP3-B eligible fixed-fractional sizing bridge.

This slice composes accepted allocator eligibility, Position Sizing Intelligence,
S11 fixed-fractional promotion, canonical sizing events and the Capital Stream
sizing projector. It does not execute BUY/REDUCE/EXIT and never grants real
capital or production authority.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
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
from crypto_signal.paper.autopilot_forward_runtime import (
    FP3AutopilotReceipt,
    FP3AutopilotStore,
)
from crypto_signal.paper.canonical_sizing import (
    CanonicalPaperSizingSelection,
    promote_fixed_fractional_sizing,
)
from crypto_signal.paper.canonical_sizing_events import (
    CanonicalSizingEventLedger,
    build_canonical_sizing_event,
)
from crypto_signal.paper.canonical_vault_decisions import CanonicalVaultDecisionLedger
from crypto_signal.paper.canonical_vault_eligibility import (
    CanonicalVaultEligibilityProof,
    promote_vault_eligibility,
)
from crypto_signal.paper.capital_science_bridge import (
    assess_unified_decision_capital,
)
from crypto_signal.paper.epoch2_accounting import (
    Epoch2CanonicalLedger,
    Epoch2VaultAccountingSnapshot,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.position_sizing_intelligence import (
    PositionSizingAssessment,
    PositionSizingPolicy,
    SizingMethod,
    SizingMethodResult,
    SizingMethodStatus,
    build_position_sizing_risk_context,
    evaluate_position_sizing_intelligence,
)
from crypto_signal.product.intelligence_stream_capital_forward_evidence import (
    build_capital_forward_auxiliary_evidence,
)
from crypto_signal.product.intelligence_stream_capital_sizing import (
    project_sizing_event_to_stream,
)
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

FP3_SIZING_SCHEMA_VERSION = "fp3-paper-autopilot-sizing-v1/1"
FP3_SIZING_ENGINE_VERSION = "fp3-paper-autopilot-sizing-bridge-v1/1"

_SIZING_RECEIPT_TABLE = "fp3_paper_autopilot_sizing_receipts"


class FP3SizingStageStatus(StrEnum):
    SIZED = "sized"
    HELD_RISK_GATE = "held_risk_gate"


class FP3SizingProcessDisposition(StrEnum):
    INSERTED = "inserted"
    RECOVERED = "recovered"
    REPLAYED = "replayed"
    HELD_RISK_GATE = "held_risk_gate"
    SKIPPED_NOT_ELIGIBLE = "skipped_not_eligible"


@dataclass(frozen=True, slots=True)
class FP3SizingRiskInputs:
    risk_input_identity: str
    vault_id: PaperVaultId
    asset: str
    as_of_ms: int
    expected_win_r: Decimal
    expected_loss_r: Decimal
    transaction_cost_r: Decimal
    absolute_correlation_0_1: Decimal
    current_drawdown_fraction: Decimal
    volatility_fraction: Decimal
    liquidity_score_0_1: Decimal
    source_evidence_identities: tuple[str, ...]
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = FP3_SIZING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.risk_input_identity, "FP3 sizing risk input")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("FP3 sizing risk input requires canonical vault")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("FP3 sizing risk asset must be uppercase")
        _require_non_negative_int(self.as_of_ms, "FP3 sizing risk as-of")
        for value, label in (
            (self.expected_win_r, "expected win R"),
            (self.expected_loss_r, "expected loss R"),
        ):
            _require_positive_decimal(value, label)
        _require_non_negative_decimal(
            self.transaction_cost_r,
            "transaction cost R",
        )
        for value, label in (
            (self.absolute_correlation_0_1, "absolute correlation"),
            (self.current_drawdown_fraction, "current drawdown"),
            (self.volatility_fraction, "volatility"),
            (self.liquidity_score_0_1, "liquidity"),
        ):
            _require_unit_interval(value, label)
        if (
            not self.source_evidence_identities
            or self.source_evidence_identities
            != tuple(sorted(set(self.source_evidence_identities)))
        ):
            raise ValueError(
                "FP3 sizing risk evidence identities must be non-empty sorted unique"
            )
        for identity in self.source_evidence_identities:
            _require_sha256(identity, "FP3 sizing risk evidence")
        _require_authority_boundary(
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.schema_version != FP3_SIZING_SCHEMA_VERSION:
            raise ValueError("unsupported FP3 sizing risk schema")
        if canonical_sha256(_risk_input_payload(self)) != self.risk_input_identity:
            raise ValueError("FP3 sizing risk input identity mismatch")


@dataclass(frozen=True, slots=True)
class FP3SizingStageReceipt:
    receipt_identity: str
    front_receipt_identity: str
    activation_identity: str
    forecast_identity: str
    proof_identity: str
    vault_id: PaperVaultId
    allocator_candidate_identity: str
    allocator_assessment_identity: str
    eligibility_proof_identity: str
    current_vault_snapshot_identity: str
    risk_input_identity: str
    sizing_context_identity: str
    sizing_policy_identity: str
    sizing_policy_version: str
    sizing_assessment_identity: str
    fixed_fractional_result_identity: str
    fixed_fractional_status: str
    reason_codes: tuple[str, ...]
    stage_status: FP3SizingStageStatus
    selection_identity: str | None
    sizing_event_identity: str | None
    stream_source_event_identity: str | None
    stream_event_identity: str | None
    narrative_identity: str | None
    selected_at_ms: int
    processed_at_ms: int
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = FP3_SIZING_SCHEMA_VERSION
    engine_version: str = FP3_SIZING_ENGINE_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.receipt_identity, "FP3 sizing receipt"),
            (self.front_receipt_identity, "FP3 front receipt"),
            (self.activation_identity, "FP3 sizing activation"),
            (self.forecast_identity, "FP3 sizing forecast"),
            (self.proof_identity, "FP3 sizing proof"),
            (self.allocator_candidate_identity, "FP3 sizing candidate"),
            (self.allocator_assessment_identity, "FP3 sizing allocation"),
            (self.eligibility_proof_identity, "FP3 sizing eligibility"),
            (self.current_vault_snapshot_identity, "FP3 sizing vault snapshot"),
            (self.risk_input_identity, "FP3 sizing risk input"),
            (self.sizing_context_identity, "FP3 sizing context"),
            (self.sizing_policy_identity, "FP3 sizing policy"),
            (self.sizing_assessment_identity, "FP3 sizing assessment"),
            (self.fixed_fractional_result_identity, "FP3 sizing fixed result"),
        ):
            _require_sha256(value, label)
        for value, label in (
            (self.selection_identity, "FP3 sizing selection"),
            (self.sizing_event_identity, "FP3 sizing event"),
            (self.stream_source_event_identity, "FP3 sizing source event"),
            (self.stream_event_identity, "FP3 sizing Stream event"),
            (self.narrative_identity, "FP3 sizing narrative"),
        ):
            if value is not None:
                _require_sha256(value, label)
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("FP3 sizing receipt requires canonical vault")
        if not self.sizing_policy_version.strip():
            raise ValueError("FP3 sizing policy version must be non-empty")
        if not self.fixed_fractional_status.strip():
            raise ValueError("FP3 fixed-fractional status must be non-empty")
        if (
            not self.reason_codes
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
        ):
            raise ValueError("FP3 sizing receipt reasons must be non-empty sorted unique")
        _require_non_negative_int(self.selected_at_ms, "FP3 sizing selected time")
        _require_non_negative_int(self.processed_at_ms, "FP3 sizing processed time")
        if self.processed_at_ms < self.selected_at_ms:
            raise ValueError("FP3 sizing process time cannot predate selection time")
        if self.stage_status is FP3SizingStageStatus.SIZED:
            if any(
                value is None
                for value in (
                    self.selection_identity,
                    self.sizing_event_identity,
                    self.stream_source_event_identity,
                    self.stream_event_identity,
                    self.narrative_identity,
                )
            ):
                raise ValueError("FP3 sized receipt requires complete canonical lineage")
            if self.fixed_fractional_status != SizingMethodStatus.AVAILABLE_SHADOW.value:
                raise ValueError("FP3 sized receipt requires available fixed fractional")
        elif self.stage_status is FP3SizingStageStatus.HELD_RISK_GATE:
            if any(
                value is not None
                for value in (
                    self.selection_identity,
                    self.sizing_event_identity,
                    self.stream_source_event_identity,
                    self.stream_event_identity,
                    self.narrative_identity,
                )
            ):
                raise ValueError("FP3 held sizing receipt cannot invent canonical event")
            if self.fixed_fractional_status == SizingMethodStatus.AVAILABLE_SHADOW.value:
                raise ValueError("FP3 held sizing receipt cannot carry available result")
        else:
            raise ValueError("unsupported FP3 sizing stage status")
        _require_authority_boundary(
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.schema_version != FP3_SIZING_SCHEMA_VERSION:
            raise ValueError("unsupported FP3 sizing receipt schema")
        if self.engine_version != FP3_SIZING_ENGINE_VERSION:
            raise ValueError("unsupported FP3 sizing engine")
        if canonical_sha256(_sizing_receipt_identity_payload(self)) != self.receipt_identity:
            raise ValueError("FP3 sizing receipt identity mismatch")


@dataclass(frozen=True, slots=True)
class FP3SizingProcessResult:
    disposition: FP3SizingProcessDisposition
    forecast_identity: str
    vault_id: PaperVaultId
    receipt: FP3SizingStageReceipt | None
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.forecast_identity, "FP3 sizing result forecast")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("FP3 sizing result requires canonical vault")
        if (
            self.disposition
            is FP3SizingProcessDisposition.SKIPPED_NOT_ELIGIBLE
        ):
            if self.receipt is not None:
                raise ValueError("skipped FP3 sizing result cannot carry receipt")
        elif self.receipt is None:
            raise ValueError("processed FP3 sizing result requires receipt")
        _require_authority_boundary(
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )


def build_fp3_sizing_risk_inputs(
    *,
    vault_id: PaperVaultId,
    asset: str,
    as_of_ms: int,
    expected_win_r: Decimal,
    expected_loss_r: Decimal,
    transaction_cost_r: Decimal,
    absolute_correlation_0_1: Decimal,
    current_drawdown_fraction: Decimal,
    volatility_fraction: Decimal,
    liquidity_score_0_1: Decimal,
    source_evidence_identities: tuple[str, ...],
) -> FP3SizingRiskInputs:
    sources = tuple(sorted(set(source_evidence_identities)))
    payload = {
        "absolute_correlation_0_1": absolute_correlation_0_1,
        "as_of_ms": as_of_ms,
        "asset": asset,
        "current_drawdown_fraction": current_drawdown_fraction,
        "expected_loss_r": expected_loss_r,
        "expected_win_r": expected_win_r,
        "liquidity_score_0_1": liquidity_score_0_1,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": FP3_SIZING_SCHEMA_VERSION,
        "source_evidence_identities": sources,
        "transaction_cost_r": transaction_cost_r,
        "vault_id": vault_id,
        "volatility_fraction": volatility_fraction,
    }
    return FP3SizingRiskInputs(
        risk_input_identity=canonical_sha256(payload),
        vault_id=vault_id,
        asset=asset,
        as_of_ms=as_of_ms,
        expected_win_r=expected_win_r,
        expected_loss_r=expected_loss_r,
        transaction_cost_r=transaction_cost_r,
        absolute_correlation_0_1=absolute_correlation_0_1,
        current_drawdown_fraction=current_drawdown_fraction,
        volatility_fraction=volatility_fraction,
        liquidity_score_0_1=liquidity_score_0_1,
        source_evidence_identities=sources,
    )


class FP3SizingStageStore:
    """Append-only FP3-B receipt table inside the isolated FP3 store."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.base = FP3AutopilotStore(path)

    def initialize(self) -> None:
        self.base.initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_SIZING_RECEIPT_TABLE} (
                    receipt_identity TEXT PRIMARY KEY,
                    forecast_identity TEXT NOT NULL,
                    vault_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    UNIQUE(forecast_identity, vault_id)
                )
                """
            )
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                    {_SIZING_RECEIPT_TABLE}_immutable_{operation.lower()}
                    BEFORE {operation} ON {_SIZING_RECEIPT_TABLE}
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable FP3 sizing stage truth'
                        );
                    END
                    """
                )

    def append(self, receipt: FP3SizingStageReceipt) -> bool:
        self.initialize()
        payload_json = canonical_json(receipt)
        digest = sha256_text(payload_json)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                f"""
                SELECT receipt_identity, forecast_identity, vault_id,
                       payload_json, payload_sha256
                FROM {_SIZING_RECEIPT_TABLE}
                WHERE receipt_identity = ?
                   OR (forecast_identity = ? AND vault_id = ?)
                LIMIT 1
                """,
                (
                    receipt.receipt_identity,
                    receipt.forecast_identity,
                    receipt.vault_id.value,
                ),
            ).fetchone()
            if row is not None:
                existing = _verified_sizing_receipt_row(row)
                if existing == receipt:
                    return False
                raise ValueError("immutable FP3 sizing receipt conflict")
            connection.execute(
                f"""
                INSERT INTO {_SIZING_RECEIPT_TABLE}(
                    receipt_identity,
                    forecast_identity,
                    vault_id,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    receipt.receipt_identity,
                    receipt.forecast_identity,
                    receipt.vault_id.value,
                    payload_json,
                    digest,
                ),
            )
        return True

    def read(
        self,
        *,
        forecast_identity: str,
        vault_id: PaperVaultId,
    ) -> FP3SizingStageReceipt | None:
        _require_sha256(forecast_identity, "FP3 sizing receipt forecast lookup")
        if not isinstance(vault_id, PaperVaultId):
            raise TypeError("FP3 sizing receipt lookup requires canonical vault")
        if not self.path.is_file():
            return None
        with closing(_connect_read_only(self.path)) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if _SIZING_RECEIPT_TABLE not in tables:
                return None
            row = connection.execute(
                f"""
                SELECT receipt_identity, forecast_identity, vault_id,
                       payload_json, payload_sha256
                FROM {_SIZING_RECEIPT_TABLE}
                WHERE forecast_identity = ? AND vault_id = ?
                """,
                (forecast_identity, vault_id.value),
            ).fetchone()
        return None if row is None else _verified_sizing_receipt_row(row)


class FP3EligibleFixedFractionalSizingBridge:
    """FP3-B owner for canonical eligible fixed-fractional sizing."""

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

    def process(
        self,
        issuance: UnifiedDecisionIssuance,
        *,
        event_context: CircuitBreakerAnalysis,
        base_asset: str,
        vault_id: PaperVaultId,
        policy: PositionSizingPolicy,
        risk_inputs: FP3SizingRiskInputs,
        selected_at_ms: int,
        processed_at_ms: int,
    ) -> FP3SizingProcessResult:
        front_receipt = self.autopilot_store.read_receipt_for_forecast(
            issuance.forecast.forecast_identity
        )
        if front_receipt is None:
            raise ValueError("FP3-B requires accepted FP3-A receipt")
        _validate_front_receipt(
            front_receipt,
            issuance=issuance,
            vault_id=vault_id,
        )
        state_by_vault = dict(front_receipt.decision_states)
        if state_by_vault[vault_id.value] != "eligible":
            return FP3SizingProcessResult(
                disposition=FP3SizingProcessDisposition.SKIPPED_NOT_ELIGIBLE,
                forecast_identity=issuance.forecast.forecast_identity,
                vault_id=vault_id,
                receipt=None,
            )
        _validate_process_times(
            front_receipt=front_receipt,
            risk_inputs=risk_inputs,
            selected_at_ms=selected_at_ms,
            processed_at_ms=processed_at_ms,
        )
        if risk_inputs.vault_id is not vault_id:
            raise ValueError("FP3-B risk input vault mismatch")
        if risk_inputs.asset != issuance.forecast.symbol:
            raise ValueError("FP3-B risk input asset mismatch")

        auxiliary = build_capital_forward_auxiliary_evidence(
            issuance,
            event_context=event_context,
        )
        capital = assess_unified_decision_capital(
            issuance,
            event_context=event_context,
            base_asset=base_asset,
            assessed_at_ms=front_receipt.assessed_at_ms,
            tactical_microstructure=auxiliary.tactical,
            opportunity_recovery=auxiliary.opportunity,
        )
        if (
            capital.candidate.candidate_identity
            != front_receipt.allocator_candidate_identity
            or capital.allocation.assessment_identity
            != front_receipt.allocator_assessment_identity
        ):
            raise ValueError("FP3-B recomputed allocator lineage differs from FP3-A")

        eligibility = promote_vault_eligibility(
            capital.candidate,
            capital.allocation,
            vault_id=vault_id,
        )
        envelope = next(
            (
                item
                for item in capital.allocation.vaults
                if item.vault_id is vault_id
            ),
            None,
        )
        if envelope is None:
            raise ValueError("FP3-B allocator lost target vault envelope")

        decision_rows = CanonicalVaultDecisionLedger(
            self.epoch2_path
        ).read_assessment_decisions(
            front_receipt.allocator_assessment_identity
        )
        if len(decision_rows) != len(tuple(PaperVaultId)):
            raise ValueError("FP3-B requires exact three-vault decision chronology")
        decision_identities = tuple(
            sorted(_required_text(item, "decision_identity") for item in decision_rows)
        )
        if decision_identities != front_receipt.decision_identities:
            raise ValueError("FP3-B canonical decision lineage differs from FP3-A")
        latest_decision_at_ms = max(
            _required_int(item, "decided_at_ms") for item in decision_rows
        )
        if selected_at_ms <= latest_decision_at_ms:
            raise ValueError(
                "FP3-B sizing selection must follow latest canonical vault decision"
            )

        epoch2 = Epoch2CanonicalLedger(self.epoch2_path).read_state()
        current_vault = _current_vault(epoch2.vault_snapshots, vault_id)
        if risk_inputs.current_drawdown_fraction != current_vault.drawdown_fraction:
            raise ValueError("FP3-B risk drawdown differs from canonical R21 state")
        if risk_inputs.as_of_ms < capital.allocation.assessed_at_ms:
            raise ValueError("FP3-B risk observation predates allocator assessment")
        if selected_at_ms < max(
            risk_inputs.as_of_ms,
            eligibility.assessed_at_ms,
            current_vault.snapshot_at_ms,
        ):
            raise ValueError("FP3-B sizing selection predates exact source truth")

        sources = tuple(
            sorted(
                {
                    *risk_inputs.source_evidence_identities,
                    risk_inputs.risk_input_identity,
                    eligibility.proof_identity,
                    current_vault.snapshot_identity,
                }
            )
        )
        context = build_position_sizing_risk_context(
            vault_id=vault_id,
            asset=risk_inputs.asset,
            as_of_ms=risk_inputs.as_of_ms,
            allocator_assessment_identity=front_receipt.allocator_assessment_identity,
            allocator_candidate_identity=front_receipt.allocator_candidate_identity,
            expected_win_r=risk_inputs.expected_win_r,
            expected_loss_r=risk_inputs.expected_loss_r,
            transaction_cost_r=risk_inputs.transaction_cost_r,
            absolute_correlation_0_1=risk_inputs.absolute_correlation_0_1,
            current_drawdown_fraction=risk_inputs.current_drawdown_fraction,
            volatility_fraction=risk_inputs.volatility_fraction,
            liquidity_score_0_1=risk_inputs.liquidity_score_0_1,
            source_evidence_identities=sources,
        )
        if (
            context.allocator_assessment_identity
            != front_receipt.allocator_assessment_identity
            or context.allocator_candidate_identity
            != front_receipt.allocator_candidate_identity
        ):
            raise ValueError("FP3-B sizing context lost allocator lineage")

        assessment = evaluate_position_sizing_intelligence(
            policy=policy,
            vault=envelope,
            context=context,
        )
        fixed = _fixed_fractional_result(assessment)
        existing = self.sizing_store.read(
            forecast_identity=issuance.forecast.forecast_identity,
            vault_id=vault_id,
        )

        if fixed.status is not SizingMethodStatus.AVAILABLE_SHADOW:
            expected = _build_hold_receipt(
                front_receipt=front_receipt,
                issuance=issuance,
                vault_id=vault_id,
                eligibility=eligibility,
                current_vault=current_vault,
                risk_inputs=risk_inputs,
                context_identity=context.context_identity,
                policy=policy,
                assessment=assessment,
                fixed=fixed,
                selected_at_ms=selected_at_ms,
                processed_at_ms=(
                    existing.processed_at_ms
                    if existing is not None
                    else processed_at_ms
                ),
            )
            if existing is not None:
                if existing != expected:
                    raise ValueError("FP3-B replay inputs conflict with held receipt")
                return FP3SizingProcessResult(
                    disposition=FP3SizingProcessDisposition.REPLAYED,
                    forecast_identity=issuance.forecast.forecast_identity,
                    vault_id=vault_id,
                    receipt=existing,
                )
            self.sizing_store.append(expected)
            return FP3SizingProcessResult(
                disposition=FP3SizingProcessDisposition.HELD_RISK_GATE,
                forecast_identity=issuance.forecast.forecast_identity,
                vault_id=vault_id,
                receipt=expected,
            )

        selection = promote_fixed_fractional_sizing(
            assessment,
            current_vault=current_vault,
            selected_at_ms=selected_at_ms,
        )
        sizing_event = build_canonical_sizing_event(selection, eligibility)

        if existing is not None:
            _verify_existing_sized_receipt(
                existing,
                front_receipt=front_receipt,
                risk_inputs=risk_inputs,
                policy=policy,
                context_identity=context.context_identity,
                assessment=assessment,
                fixed=fixed,
                selection=selection,
                sizing_event_identity=sizing_event.event_identity,
            )
            return FP3SizingProcessResult(
                disposition=FP3SizingProcessDisposition.REPLAYED,
                forecast_identity=issuance.forecast.forecast_identity,
                vault_id=vault_id,
                receipt=existing,
            )

        event_inserted = CanonicalSizingEventLedger(self.epoch2_path).append(
            sizing_event
        )
        projection = project_sizing_event_to_stream(
            epoch2_path=self.epoch2_path,
            stream_path=self.stream_path,
            sizing_event_identity=sizing_event.event_identity,
        )
        receipt = _build_sized_receipt(
            front_receipt=front_receipt,
            issuance=issuance,
            vault_id=vault_id,
            eligibility=eligibility,
            current_vault=current_vault,
            risk_inputs=risk_inputs,
            context_identity=context.context_identity,
            policy=policy,
            assessment=assessment,
            fixed=fixed,
            selection=selection,
            sizing_event_identity=sizing_event.event_identity,
            stream_source_event_identity=projection.source_event_identity,
            stream_event_identity=projection.stream_event_identity,
            narrative_identity=projection.narrative_identity,
            selected_at_ms=selected_at_ms,
            processed_at_ms=processed_at_ms,
        )
        self.sizing_store.append(receipt)
        return FP3SizingProcessResult(
            disposition=(
                FP3SizingProcessDisposition.INSERTED
                if event_inserted
                else FP3SizingProcessDisposition.RECOVERED
            ),
            forecast_identity=issuance.forecast.forecast_identity,
            vault_id=vault_id,
            receipt=receipt,
        )


def _validate_front_receipt(
    receipt: FP3AutopilotReceipt,
    *,
    issuance: UnifiedDecisionIssuance,
    vault_id: PaperVaultId,
) -> None:
    if receipt.forecast_identity != issuance.forecast.forecast_identity:
        raise ValueError("FP3-B front receipt forecast mismatch")
    if receipt.proof_identity != issuance.proof.proof_identity:
        raise ValueError("FP3-B front receipt proof mismatch")
    states = dict(receipt.decision_states)
    if vault_id.value not in states:
        raise ValueError("FP3-B front receipt lacks target vault")


def _validate_process_times(
    *,
    front_receipt: FP3AutopilotReceipt,
    risk_inputs: FP3SizingRiskInputs,
    selected_at_ms: int,
    processed_at_ms: int,
) -> None:
    _require_non_negative_int(selected_at_ms, "FP3 sizing selected time")
    _require_non_negative_int(processed_at_ms, "FP3 sizing processed time")
    if risk_inputs.as_of_ms < front_receipt.assessed_at_ms:
        raise ValueError("FP3-B risk observation predates FP3-A assessment")
    if selected_at_ms < risk_inputs.as_of_ms:
        raise ValueError("FP3-B selection predates risk observation")
    if processed_at_ms < selected_at_ms:
        raise ValueError("FP3-B processing predates sizing selection")


def _current_vault(
    vaults: tuple[Epoch2VaultAccountingSnapshot, ...],
    vault_id: PaperVaultId,
) -> Epoch2VaultAccountingSnapshot:
    matches = tuple(item for item in vaults if item.vault_id is vault_id)
    if len(matches) != 1:
        raise ValueError("FP3-B requires exactly one current target vault snapshot")
    return matches[0]


def _fixed_fractional_result(
    assessment: PositionSizingAssessment,
) -> SizingMethodResult:
    matches = tuple(
        item
        for item in assessment.results
        if item.method is SizingMethod.FIXED_FRACTIONAL
    )
    if len(matches) != 1:
        raise ValueError("FP3-B sizing assessment lost fixed-fractional result")
    return matches[0]


def _build_hold_receipt(
    *,
    front_receipt: FP3AutopilotReceipt,
    issuance: UnifiedDecisionIssuance,
    vault_id: PaperVaultId,
    eligibility: CanonicalVaultEligibilityProof,
    current_vault: Epoch2VaultAccountingSnapshot,
    risk_inputs: FP3SizingRiskInputs,
    context_identity: str,
    policy: PositionSizingPolicy,
    assessment: PositionSizingAssessment,
    fixed: SizingMethodResult,
    selected_at_ms: int,
    processed_at_ms: int,
) -> FP3SizingStageReceipt:
    reasons = tuple(sorted(set(fixed.reason_codes)))
    values = _base_receipt_values(
        front_receipt=front_receipt,
        issuance=issuance,
        vault_id=vault_id,
        eligibility=eligibility,
        current_vault=current_vault,
        risk_inputs=risk_inputs,
        context_identity=context_identity,
        policy=policy,
        assessment=assessment,
        fixed=fixed,
        stage_status=FP3SizingStageStatus.HELD_RISK_GATE,
        reason_codes=reasons,
        selection_identity=None,
        sizing_event_identity=None,
        stream_source_event_identity=None,
        stream_event_identity=None,
        narrative_identity=None,
        selected_at_ms=selected_at_ms,
        processed_at_ms=processed_at_ms,
    )
    return FP3SizingStageReceipt(
        receipt_identity=canonical_sha256(values),
        **values,
    )


def _build_sized_receipt(
    *,
    front_receipt: FP3AutopilotReceipt,
    issuance: UnifiedDecisionIssuance,
    vault_id: PaperVaultId,
    eligibility: CanonicalVaultEligibilityProof,
    current_vault: Epoch2VaultAccountingSnapshot,
    risk_inputs: FP3SizingRiskInputs,
    context_identity: str,
    policy: PositionSizingPolicy,
    assessment: PositionSizingAssessment,
    fixed: SizingMethodResult,
    selection: CanonicalPaperSizingSelection,
    sizing_event_identity: str,
    stream_source_event_identity: str,
    stream_event_identity: str,
    narrative_identity: str,
    selected_at_ms: int,
    processed_at_ms: int,
) -> FP3SizingStageReceipt:
    values = _base_receipt_values(
        front_receipt=front_receipt,
        issuance=issuance,
        vault_id=vault_id,
        eligibility=eligibility,
        current_vault=current_vault,
        risk_inputs=risk_inputs,
        context_identity=context_identity,
        policy=policy,
        assessment=assessment,
        fixed=fixed,
        stage_status=FP3SizingStageStatus.SIZED,
        reason_codes=selection.reason_codes,
        selection_identity=selection.selection_identity,
        sizing_event_identity=sizing_event_identity,
        stream_source_event_identity=stream_source_event_identity,
        stream_event_identity=stream_event_identity,
        narrative_identity=narrative_identity,
        selected_at_ms=selected_at_ms,
        processed_at_ms=processed_at_ms,
    )
    return FP3SizingStageReceipt(
        receipt_identity=canonical_sha256(values),
        **values,
    )


def _base_receipt_values(
    *,
    front_receipt: FP3AutopilotReceipt,
    issuance: UnifiedDecisionIssuance,
    vault_id: PaperVaultId,
    eligibility: CanonicalVaultEligibilityProof,
    current_vault: Epoch2VaultAccountingSnapshot,
    risk_inputs: FP3SizingRiskInputs,
    context_identity: str,
    policy: PositionSizingPolicy,
    assessment: PositionSizingAssessment,
    fixed: SizingMethodResult,
    stage_status: FP3SizingStageStatus,
    reason_codes: tuple[str, ...],
    selection_identity: str | None,
    sizing_event_identity: str | None,
    stream_source_event_identity: str | None,
    stream_event_identity: str | None,
    narrative_identity: str | None,
    selected_at_ms: int,
    processed_at_ms: int,
) -> dict[str, object]:
    return {
        "activation_identity": front_receipt.activation_identity,
        "allocator_assessment_identity": front_receipt.allocator_assessment_identity,
        "allocator_candidate_identity": front_receipt.allocator_candidate_identity,
        "current_vault_snapshot_identity": current_vault.snapshot_identity,
        "eligibility_proof_identity": eligibility.proof_identity,
        "engine_version": FP3_SIZING_ENGINE_VERSION,
        "fixed_fractional_result_identity": fixed.result_identity,
        "fixed_fractional_status": fixed.status.value,
        "forecast_identity": issuance.forecast.forecast_identity,
        "front_receipt_identity": front_receipt.receipt_identity,
        "narrative_identity": narrative_identity,
        "processed_at_ms": processed_at_ms,
        "production_authority": False,
        "proof_identity": issuance.proof.proof_identity,
        "real_capital": REAL_CAPITAL,
        "reason_codes": tuple(sorted(set(reason_codes))),
        "risk_input_identity": risk_inputs.risk_input_identity,
        "schema_version": FP3_SIZING_SCHEMA_VERSION,
        "selected_at_ms": selected_at_ms,
        "selection_identity": selection_identity,
        "sizing_assessment_identity": assessment.assessment_identity,
        "sizing_context_identity": context_identity,
        "sizing_event_identity": sizing_event_identity,
        "sizing_policy_identity": policy.policy_identity,
        "sizing_policy_version": policy.policy_version,
        "stage_status": stage_status,
        "stream_event_identity": stream_event_identity,
        "stream_source_event_identity": stream_source_event_identity,
        "vault_id": vault_id,
    }


def _verify_existing_sized_receipt(
    receipt: FP3SizingStageReceipt,
    *,
    front_receipt: FP3AutopilotReceipt,
    risk_inputs: FP3SizingRiskInputs,
    policy: PositionSizingPolicy,
    context_identity: str,
    assessment: PositionSizingAssessment,
    fixed: SizingMethodResult,
    selection: CanonicalPaperSizingSelection,
    sizing_event_identity: str,
) -> None:
    expected = (
        receipt.front_receipt_identity == front_receipt.receipt_identity
        and receipt.activation_identity == front_receipt.activation_identity
        and receipt.allocator_candidate_identity
        == front_receipt.allocator_candidate_identity
        and receipt.allocator_assessment_identity
        == front_receipt.allocator_assessment_identity
        and receipt.risk_input_identity == risk_inputs.risk_input_identity
        and receipt.sizing_context_identity == context_identity
        and receipt.sizing_policy_identity == policy.policy_identity
        and receipt.sizing_assessment_identity == assessment.assessment_identity
        and receipt.fixed_fractional_result_identity == fixed.result_identity
        and receipt.selection_identity == selection.selection_identity
        and receipt.sizing_event_identity == sizing_event_identity
        and receipt.stage_status is FP3SizingStageStatus.SIZED
    )
    if not expected:
        raise ValueError("FP3-B replay inputs conflict with sized receipt")


def _risk_input_payload(value: FP3SizingRiskInputs) -> dict[str, object]:
    return {
        "absolute_correlation_0_1": value.absolute_correlation_0_1,
        "as_of_ms": value.as_of_ms,
        "asset": value.asset,
        "current_drawdown_fraction": value.current_drawdown_fraction,
        "expected_loss_r": value.expected_loss_r,
        "expected_win_r": value.expected_win_r,
        "liquidity_score_0_1": value.liquidity_score_0_1,
        "production_authority": value.production_authority,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "source_evidence_identities": value.source_evidence_identities,
        "transaction_cost_r": value.transaction_cost_r,
        "vault_id": value.vault_id,
        "volatility_fraction": value.volatility_fraction,
    }


def _sizing_receipt_identity_payload(
    value: FP3SizingStageReceipt,
) -> dict[str, object]:
    return {
        "activation_identity": value.activation_identity,
        "allocator_assessment_identity": value.allocator_assessment_identity,
        "allocator_candidate_identity": value.allocator_candidate_identity,
        "current_vault_snapshot_identity": value.current_vault_snapshot_identity,
        "eligibility_proof_identity": value.eligibility_proof_identity,
        "engine_version": value.engine_version,
        "fixed_fractional_result_identity": value.fixed_fractional_result_identity,
        "fixed_fractional_status": value.fixed_fractional_status,
        "forecast_identity": value.forecast_identity,
        "front_receipt_identity": value.front_receipt_identity,
        "narrative_identity": value.narrative_identity,
        "processed_at_ms": value.processed_at_ms,
        "production_authority": value.production_authority,
        "proof_identity": value.proof_identity,
        "real_capital": value.real_capital,
        "reason_codes": value.reason_codes,
        "risk_input_identity": value.risk_input_identity,
        "schema_version": value.schema_version,
        "selected_at_ms": value.selected_at_ms,
        "selection_identity": value.selection_identity,
        "sizing_assessment_identity": value.sizing_assessment_identity,
        "sizing_context_identity": value.sizing_context_identity,
        "sizing_event_identity": value.sizing_event_identity,
        "sizing_policy_identity": value.sizing_policy_identity,
        "sizing_policy_version": value.sizing_policy_version,
        "stage_status": value.stage_status,
        "stream_event_identity": value.stream_event_identity,
        "stream_source_event_identity": value.stream_source_event_identity,
        "vault_id": value.vault_id,
    }


def _verified_sizing_receipt_row(row: sqlite3.Row) -> FP3SizingStageReceipt:
    payload_json = str(row["payload_json"])
    if sha256_text(payload_json) != str(row["payload_sha256"]):
        raise ValueError("FP3 sizing receipt digest mismatch")
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("FP3 sizing receipt payload must be object")
    value = FP3SizingStageReceipt(
        receipt_identity=_required_text(raw, "receipt_identity"),
        front_receipt_identity=_required_text(raw, "front_receipt_identity"),
        activation_identity=_required_text(raw, "activation_identity"),
        forecast_identity=_required_text(raw, "forecast_identity"),
        proof_identity=_required_text(raw, "proof_identity"),
        vault_id=PaperVaultId(_required_text(raw, "vault_id")),
        allocator_candidate_identity=_required_text(
            raw,
            "allocator_candidate_identity",
        ),
        allocator_assessment_identity=_required_text(
            raw,
            "allocator_assessment_identity",
        ),
        eligibility_proof_identity=_required_text(
            raw,
            "eligibility_proof_identity",
        ),
        current_vault_snapshot_identity=_required_text(
            raw,
            "current_vault_snapshot_identity",
        ),
        risk_input_identity=_required_text(raw, "risk_input_identity"),
        sizing_context_identity=_required_text(raw, "sizing_context_identity"),
        sizing_policy_identity=_required_text(raw, "sizing_policy_identity"),
        sizing_policy_version=_required_text(raw, "sizing_policy_version"),
        sizing_assessment_identity=_required_text(
            raw,
            "sizing_assessment_identity",
        ),
        fixed_fractional_result_identity=_required_text(
            raw,
            "fixed_fractional_result_identity",
        ),
        fixed_fractional_status=_required_text(
            raw,
            "fixed_fractional_status",
        ),
        reason_codes=_string_tuple(raw, "reason_codes"),
        stage_status=FP3SizingStageStatus(_required_text(raw, "stage_status")),
        selection_identity=_optional_text(raw, "selection_identity"),
        sizing_event_identity=_optional_text(raw, "sizing_event_identity"),
        stream_source_event_identity=_optional_text(
            raw,
            "stream_source_event_identity",
        ),
        stream_event_identity=_optional_text(raw, "stream_event_identity"),
        narrative_identity=_optional_text(raw, "narrative_identity"),
        selected_at_ms=_required_int(raw, "selected_at_ms"),
        processed_at_ms=_required_int(raw, "processed_at_ms"),
        production_authority=_required_bool(raw, "production_authority"),
        real_capital=_required_int(raw, "real_capital"),
        schema_version=_required_text(raw, "schema_version"),
        engine_version=_required_text(raw, "engine_version"),
    )
    if str(row["receipt_identity"]) != value.receipt_identity:
        raise ValueError("FP3 sizing receipt row identity mismatch")
    if str(row["forecast_identity"]) != value.forecast_identity:
        raise ValueError("FP3 sizing receipt row forecast mismatch")
    if str(row["vault_id"]) != value.vault_id.value:
        raise ValueError("FP3 sizing receipt row vault mismatch")
    if canonical_json(value) != payload_json:
        raise ValueError("FP3 sizing receipt canonical payload mismatch")
    return value


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _required_text(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty text")
    return value


def _optional_text(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty text or None")
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


def _string_tuple(raw: dict[str, object], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be string array")
    return tuple(cast(list[str], value))


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be exact SHA256")


def _require_non_negative_int(value: int, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be non-negative integer")


def _require_positive_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{label} must be positive finite Decimal")


def _require_non_negative_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{label} must be non-negative finite Decimal")


def _require_unit_interval(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not value.is_finite() or value < 0 or value > 1:
        raise ValueError(f"{label} must be finite Decimal inside 0..1")


def _require_authority_boundary(
    *,
    production_authority: bool,
    real_capital: int,
) -> None:
    if production_authority or real_capital != REAL_CAPITAL:
        raise ValueError("FP3 sizing bridge crossed authority boundary")
