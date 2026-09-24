"""WC6 paper execution-lab recovery, reconciliation, and kill-switch evidence.

This module composes only already-accepted virtual-paper boundaries. It has no
network, exchange, credential, broker, sandbox, testnet, or real-order surface.
REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.activation import (
    PaperActivationState,
    PaperProcessedEventReceipt,
    PaperProcessedTradeCommit,
    commit_planned_pretrade_event,
    list_processed_paper_events,
)
from crypto_signal.paper.execution import FrozenExecutionSnapshot
from crypto_signal.paper.execution_input import FrozenPaperExecutionInput
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerEntry,
    PaperLedgerWriteAuthorityError,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.pretrade import PaperPretradeDecision
from crypto_signal.paper.state import PaperFundState
from crypto_signal.paper.write_authority import (
    PaperWriteAuthorityEvent,
    load_current_paper_write_authority,
)

WC6_EXECUTION_LAB_ENGINE_VERSION = "wc6-paper-execution-lab-v1/1"
WC6_EXECUTION_LAB_SCHEMA_VERSION = "wc6-paper-execution-lab-schema-v1/1"


class WC6ExecutionLabSemantic(StrEnum):
    PAPER_RECOVERY_RECONCILIATION_NO_LIVE_ORDER_AUTHORITY = (
        "paper_recovery_reconciliation_no_live_order_authority"
    )


class WC6SandboxAdapterStatus(StrEnum):
    NOT_IMPLEMENTED = "not_implemented"


class WC6PartialFillStatus(StrEnum):
    UNSUPPORTED_V1 = "unsupported_v1"


class WC6ExecutionLabError(ValueError):
    """Raised when WC6 paper execution evidence cannot be reconciled safely."""


@dataclass(frozen=True, slots=True)
class WC6KillSwitchProbe:
    probe_identity: str
    schema_version: str
    engine_version: str
    disabled_authority_identity: str
    activation_identity: str
    pretrade_identity: str
    execution_snapshot_identity: str
    replay_identity_before: str
    replay_identity_after: str
    processed_receipts_identity_before: str
    processed_receipts_identity_after: str
    rejected_by_disabled_authority: bool
    ledger_unchanged: bool
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.probe_identity, "WC6 kill-switch probe identity"),
            (
                self.disabled_authority_identity,
                "WC6 disabled-authority identity",
            ),
            (self.activation_identity, "WC6 activation identity"),
            (self.pretrade_identity, "WC6 pretrade identity"),
            (
                self.execution_snapshot_identity,
                "WC6 execution snapshot identity",
            ),
            (self.replay_identity_before, "WC6 replay-before identity"),
            (self.replay_identity_after, "WC6 replay-after identity"),
            (
                self.processed_receipts_identity_before,
                "WC6 receipts-before identity",
            ),
            (
                self.processed_receipts_identity_after,
                "WC6 receipts-after identity",
            ),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_EXECUTION_LAB_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 kill-switch probe schema")
        if self.engine_version != WC6_EXECUTION_LAB_ENGINE_VERSION:
            raise ValueError("unsupported WC6 kill-switch probe engine")
        if not self.rejected_by_disabled_authority:
            raise ValueError("WC6 kill-switch probe must observe authority rejection")
        if not self.ledger_unchanged:
            raise ValueError("WC6 kill-switch probe must leave ledger unchanged")
        if self.replay_identity_before != self.replay_identity_after:
            raise ValueError("WC6 kill-switch probe changed paper replay")
        if (
            self.processed_receipts_identity_before
            != self.processed_receipts_identity_after
        ):
            raise ValueError("WC6 kill-switch probe changed processed receipts")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.probe_identity != canonical_sha256(_kill_switch_payload(self)):
            raise ValueError("WC6 kill-switch probe identity mismatch")


@dataclass(frozen=True, slots=True)
class WC6ExecutionLabDossier:
    dossier_identity: str
    schema_version: str
    engine_version: str
    semantic: WC6ExecutionLabSemantic
    activation_identity: str
    enabled_authority_identity: str
    disabled_authority_identity: str
    kill_switch_probe_identity: str
    processed_event_identity: str
    pretrade_identity: str
    execution_snapshot_identity: str
    decision_identity: str
    fill_identity: str
    mutation_identity: str
    state_before_identity: str
    state_after_identity: str
    first_commit_disposition: PaperLedgerWriteDisposition
    retry_commit_disposition: PaperLedgerWriteDisposition
    exact_retry_idempotence_proven: bool
    duplicate_prevention_proven: bool
    reconciliation_proven: bool
    kill_switch_proven: bool
    sandbox_adapter_status: WC6SandboxAdapterStatus
    partial_fill_status: WC6PartialFillStatus
    network_authority: bool = False
    credential_authority: bool = False
    live_order_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.dossier_identity, "WC6 dossier identity"),
            (self.activation_identity, "WC6 activation identity"),
            (
                self.enabled_authority_identity,
                "WC6 enabled-authority identity",
            ),
            (
                self.disabled_authority_identity,
                "WC6 disabled-authority identity",
            ),
            (self.kill_switch_probe_identity, "WC6 kill-switch probe identity"),
            (self.processed_event_identity, "WC6 processed-event identity"),
            (self.pretrade_identity, "WC6 pretrade identity"),
            (
                self.execution_snapshot_identity,
                "WC6 execution snapshot identity",
            ),
            (self.decision_identity, "WC6 decision identity"),
            (self.fill_identity, "WC6 fill identity"),
            (self.mutation_identity, "WC6 mutation identity"),
            (self.state_before_identity, "WC6 state-before identity"),
            (self.state_after_identity, "WC6 state-after identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_EXECUTION_LAB_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 execution-lab schema")
        if self.engine_version != WC6_EXECUTION_LAB_ENGINE_VERSION:
            raise ValueError("unsupported WC6 execution-lab engine")
        if self.semantic is not (
            WC6ExecutionLabSemantic.PAPER_RECOVERY_RECONCILIATION_NO_LIVE_ORDER_AUTHORITY
        ):
            raise ValueError("unsupported WC6 execution-lab semantic")
        if self.first_commit_disposition is not PaperLedgerWriteDisposition.INSERTED:
            raise ValueError("WC6 dossier requires one inserted paper commit")
        if self.retry_commit_disposition is not PaperLedgerWriteDisposition.UNCHANGED:
            raise ValueError("WC6 dossier requires exact retry to be unchanged")
        if not (
            self.exact_retry_idempotence_proven
            and self.duplicate_prevention_proven
            and self.reconciliation_proven
            and self.kill_switch_proven
        ):
            raise ValueError("WC6 dossier requires all paper safety evidence")
        if self.sandbox_adapter_status is not WC6SandboxAdapterStatus.NOT_IMPLEMENTED:
            raise ValueError("WC6 v1 must not imply a sandbox adapter")
        if self.partial_fill_status is not WC6PartialFillStatus.UNSUPPORTED_V1:
            raise ValueError("WC6 v1 must preserve unsupported partial-fill truth")
        if (
            self.network_authority
            or self.credential_authority
            or self.live_order_authority
            or self.production_authority
        ):
            raise ValueError("WC6 paper dossier grants no external/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.dossier_identity != canonical_sha256(_dossier_payload(self)):
            raise ValueError("WC6 execution-lab dossier identity mismatch")


def probe_disabled_paper_write_authority(
    *,
    ledger: PaperFundLedger,
    state: PaperFundState,
    activation: PaperActivationState,
    pretrade: PaperPretradeDecision,
    execution_input: FrozenPaperExecutionInput,
    execution_snapshot: FrozenExecutionSnapshot,
    disabled_authority: PaperWriteAuthorityEvent,
) -> WC6KillSwitchProbe:
    """Prove disabled virtual-write authority blocks the paper commit boundary."""

    current = load_current_paper_write_authority(ledger)
    if current != disabled_authority:
        raise WC6ExecutionLabError(
            "kill-switch probe requires exact current disabled authority"
        )
    if disabled_authority.enabled:
        raise WC6ExecutionLabError("kill-switch probe requires disabled authority")
    if disabled_authority.activation_identity != activation.activation_identity:
        raise WC6ExecutionLabError("kill-switch authority activation mismatch")

    replay_before = ledger.replay()
    receipts_before = list_processed_paper_events(ledger)
    replay_before_identity = _replay_identity(replay_before)
    receipts_before_identity = _receipts_identity(receipts_before)

    rejected = False
    try:
        commit_planned_pretrade_event(
            ledger=ledger,
            state=state,
            activation=activation,
            pretrade=pretrade,
            execution_input=execution_input,
            execution_snapshot=execution_snapshot,
            required_authority_event_identity=(
                disabled_authority.authority_event_identity
            ),
        )
    except PaperLedgerWriteAuthorityError:
        rejected = True

    replay_after = ledger.replay()
    receipts_after = list_processed_paper_events(ledger)
    replay_after_identity = _replay_identity(replay_after)
    receipts_after_identity = _receipts_identity(receipts_after)
    unchanged = (
        replay_before == replay_after
        and receipts_before == receipts_after
        and replay_before_identity == replay_after_identity
        and receipts_before_identity == receipts_after_identity
    )
    if not rejected:
        raise WC6ExecutionLabError(
            "disabled paper authority did not reject commit boundary"
        )
    if not unchanged:
        raise WC6ExecutionLabError(
            "kill-switch rejection mutated paper ledger evidence"
        )

    payload = {
        "activation_identity": activation.activation_identity,
        "disabled_authority_identity": (
            disabled_authority.authority_event_identity
        ),
        "engine_version": WC6_EXECUTION_LAB_ENGINE_VERSION,
        "execution_snapshot_identity": execution_snapshot.snapshot_identity,
        "ledger_unchanged": True,
        "pretrade_identity": pretrade.pretrade_identity,
        "processed_receipts_identity_after": receipts_after_identity,
        "processed_receipts_identity_before": receipts_before_identity,
        "real_capital": REAL_CAPITAL,
        "rejected_by_disabled_authority": True,
        "replay_identity_after": replay_after_identity,
        "replay_identity_before": replay_before_identity,
        "schema_version": WC6_EXECUTION_LAB_SCHEMA_VERSION,
    }
    return WC6KillSwitchProbe(
        probe_identity=canonical_sha256(payload),
        schema_version=WC6_EXECUTION_LAB_SCHEMA_VERSION,
        engine_version=WC6_EXECUTION_LAB_ENGINE_VERSION,
        disabled_authority_identity=disabled_authority.authority_event_identity,
        activation_identity=activation.activation_identity,
        pretrade_identity=pretrade.pretrade_identity,
        execution_snapshot_identity=execution_snapshot.snapshot_identity,
        replay_identity_before=replay_before_identity,
        replay_identity_after=replay_after_identity,
        processed_receipts_identity_before=receipts_before_identity,
        processed_receipts_identity_after=receipts_after_identity,
        rejected_by_disabled_authority=True,
        ledger_unchanged=True,
        real_capital=REAL_CAPITAL,
    )


def build_wc6_execution_lab_dossier(
    *,
    state_before: PaperFundState,
    first_commit: PaperProcessedTradeCommit,
    retry_commit: PaperProcessedTradeCommit,
    enabled_authority: PaperWriteAuthorityEvent,
    disabled_authority: PaperWriteAuthorityEvent,
    kill_switch_probe: WC6KillSwitchProbe,
) -> WC6ExecutionLabDossier:
    """Bind deterministic paper recovery/reconciliation evidence without promotion."""

    if not enabled_authority.enabled:
        raise WC6ExecutionLabError("WC6 dossier requires enabled authority evidence")
    if disabled_authority.enabled:
        raise WC6ExecutionLabError("WC6 dossier requires disabled authority evidence")
    if (
        disabled_authority.previous_event_identity
        != enabled_authority.authority_event_identity
    ):
        raise WC6ExecutionLabError("WC6 authority disable is not chained to enable")
    if (
        enabled_authority.activation_identity
        != disabled_authority.activation_identity
        or enabled_authority.activation_identity
        != first_commit.receipt.activation_identity
    ):
        raise WC6ExecutionLabError("WC6 authority/receipt activation mismatch")

    if first_commit.pipeline.commit.disposition is not (
        PaperLedgerWriteDisposition.INSERTED
    ):
        raise WC6ExecutionLabError("WC6 first commit must insert")
    if retry_commit.pipeline.commit.disposition is not (
        PaperLedgerWriteDisposition.UNCHANGED
    ):
        raise WC6ExecutionLabError("WC6 exact retry must be unchanged")
    if first_commit.receipt != retry_commit.receipt:
        raise WC6ExecutionLabError("WC6 exact retry changed processed receipt")
    if (
        first_commit.pipeline.commit.record_identities
        != retry_commit.pipeline.commit.record_identities
    ):
        raise WC6ExecutionLabError("WC6 exact retry changed record identities")
    if (
        first_commit.pipeline.commit.state_after
        != retry_commit.pipeline.commit.state_after
    ):
        raise WC6ExecutionLabError("WC6 exact retry changed reconstructed state")

    bundle = first_commit.pipeline.bundle
    if bundle.fill is None or bundle.mutation is None:
        raise WC6ExecutionLabError("WC6 committed trade lost fill/mutation")
    record_identities = (
        bundle.decision.record_identity,
        bundle.fill.record_identity,
        bundle.mutation.record_identity,
    )
    if first_commit.receipt.record_identities != record_identities:
        raise WC6ExecutionLabError("WC6 receipt/record reconciliation failed")
    if first_commit.pipeline.commit.record_identities != record_identities:
        raise WC6ExecutionLabError("WC6 commit/record reconciliation failed")
    if (
        first_commit.pipeline.commit.processed_event_identity
        != first_commit.receipt.event_identity
    ):
        raise WC6ExecutionLabError("WC6 processed-event reconciliation failed")
    if (
        first_commit.pipeline.pretrade_identity
        != first_commit.receipt.pretrade_identity
    ):
        raise WC6ExecutionLabError("WC6 pretrade/receipt reconciliation failed")
    if (
        bundle.execution_snapshot_identity
        != first_commit.pipeline.execution_snapshot_identity
    ):
        raise WC6ExecutionLabError("WC6 execution snapshot reconciliation failed")

    state_after = first_commit.pipeline.commit.state_after
    if state_after.last_mutation_identity != bundle.mutation.record_identity:
        raise WC6ExecutionLabError("WC6 state does not end at committed mutation")
    if state_after.replayed_record_count != state_before.replayed_record_count + 3:
        raise WC6ExecutionLabError("WC6 replay count does not match trade bundle")
    if state_after.real_capital != REAL_CAPITAL:
        raise WC6ExecutionLabError("REAL_CAPITAL must remain 0")
    if bundle.fill.costs.partial_fills_supported is not False:
        raise WC6ExecutionLabError("WC6 v1 partial fills must remain unsupported")

    if (
        kill_switch_probe.disabled_authority_identity
        != disabled_authority.authority_event_identity
        or kill_switch_probe.activation_identity
        != disabled_authority.activation_identity
        or kill_switch_probe.pretrade_identity
        != first_commit.pipeline.pretrade_identity
        or kill_switch_probe.execution_snapshot_identity
        != first_commit.pipeline.execution_snapshot_identity
    ):
        raise WC6ExecutionLabError("WC6 kill-switch probe lineage mismatch")

    state_before_identity = _state_identity(state_before)
    state_after_identity = _state_identity(state_after)
    payload = {
        "activation_identity": first_commit.receipt.activation_identity,
        "credential_authority": False,
        "decision_identity": bundle.decision.record_identity,
        "disabled_authority_identity": (
            disabled_authority.authority_event_identity
        ),
        "duplicate_prevention_proven": True,
        "enabled_authority_identity": enabled_authority.authority_event_identity,
        "engine_version": WC6_EXECUTION_LAB_ENGINE_VERSION,
        "exact_retry_idempotence_proven": True,
        "execution_snapshot_identity": (
            first_commit.pipeline.execution_snapshot_identity
        ),
        "fill_identity": bundle.fill.record_identity,
        "first_commit_disposition": first_commit.pipeline.commit.disposition,
        "kill_switch_probe_identity": kill_switch_probe.probe_identity,
        "kill_switch_proven": True,
        "live_order_authority": False,
        "mutation_identity": bundle.mutation.record_identity,
        "network_authority": False,
        "partial_fill_status": WC6PartialFillStatus.UNSUPPORTED_V1,
        "pretrade_identity": first_commit.pipeline.pretrade_identity,
        "processed_event_identity": first_commit.receipt.event_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reconciliation_proven": True,
        "retry_commit_disposition": retry_commit.pipeline.commit.disposition,
        "sandbox_adapter_status": WC6SandboxAdapterStatus.NOT_IMPLEMENTED,
        "schema_version": WC6_EXECUTION_LAB_SCHEMA_VERSION,
        "semantic": (
            WC6ExecutionLabSemantic.PAPER_RECOVERY_RECONCILIATION_NO_LIVE_ORDER_AUTHORITY
        ),
        "state_after_identity": state_after_identity,
        "state_before_identity": state_before_identity,
    }
    return WC6ExecutionLabDossier(
        dossier_identity=canonical_sha256(payload),
        schema_version=WC6_EXECUTION_LAB_SCHEMA_VERSION,
        engine_version=WC6_EXECUTION_LAB_ENGINE_VERSION,
        semantic=(
            WC6ExecutionLabSemantic.PAPER_RECOVERY_RECONCILIATION_NO_LIVE_ORDER_AUTHORITY
        ),
        activation_identity=first_commit.receipt.activation_identity,
        enabled_authority_identity=enabled_authority.authority_event_identity,
        disabled_authority_identity=disabled_authority.authority_event_identity,
        kill_switch_probe_identity=kill_switch_probe.probe_identity,
        processed_event_identity=first_commit.receipt.event_identity,
        pretrade_identity=first_commit.pipeline.pretrade_identity,
        execution_snapshot_identity=(
            first_commit.pipeline.execution_snapshot_identity
        ),
        decision_identity=bundle.decision.record_identity,
        fill_identity=bundle.fill.record_identity,
        mutation_identity=bundle.mutation.record_identity,
        state_before_identity=state_before_identity,
        state_after_identity=state_after_identity,
        first_commit_disposition=first_commit.pipeline.commit.disposition,
        retry_commit_disposition=retry_commit.pipeline.commit.disposition,
        exact_retry_idempotence_proven=True,
        duplicate_prevention_proven=True,
        reconciliation_proven=True,
        kill_switch_proven=True,
        sandbox_adapter_status=WC6SandboxAdapterStatus.NOT_IMPLEMENTED,
        partial_fill_status=WC6PartialFillStatus.UNSUPPORTED_V1,
        network_authority=False,
        credential_authority=False,
        live_order_authority=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def _state_identity(state: PaperFundState) -> str:
    return canonical_sha256(
        {
            "cash_usdt": state.cash_usdt,
            "created_at_ms": state.created_at_ms,
            "execution_policy_version": state.execution_policy_version,
            "fund_identity": state.fund_identity,
            "last_mutation_at_ms": state.last_mutation_at_ms,
            "last_mutation_identity": state.last_mutation_identity,
            "positions": [
                {
                    "quantity": item.quantity,
                    "symbol": item.symbol.value,
                }
                for item in state.positions
            ],
            "real_capital": state.real_capital,
            "replayed_record_count": state.replayed_record_count,
            "risk_policy_version": state.risk_policy_version,
            "schema_version": state.schema_version,
        }
    )


def _replay_identity(entries: tuple[PaperLedgerEntry, ...]) -> str:
    return canonical_sha256(
        [
            {
                "appended_at_ms": entry.appended_at_ms,
                "record_identity": entry.record_identity,
                "record_kind": entry.record_kind,
                "sequence_id": entry.sequence_id,
            }
            for entry in entries
        ]
    )


def _receipts_identity(
    receipts: tuple[PaperProcessedEventReceipt, ...],
) -> str:
    return canonical_sha256(
        [
            {
                "event_identity": item.event_identity,
                "processed_at_ms": item.processed_at_ms,
            }
            for item in receipts
        ]
    )


def _kill_switch_payload(probe: WC6KillSwitchProbe) -> dict[str, object]:
    return {
        "activation_identity": probe.activation_identity,
        "disabled_authority_identity": probe.disabled_authority_identity,
        "engine_version": probe.engine_version,
        "execution_snapshot_identity": probe.execution_snapshot_identity,
        "ledger_unchanged": probe.ledger_unchanged,
        "pretrade_identity": probe.pretrade_identity,
        "processed_receipts_identity_after": (
            probe.processed_receipts_identity_after
        ),
        "processed_receipts_identity_before": (
            probe.processed_receipts_identity_before
        ),
        "real_capital": probe.real_capital,
        "rejected_by_disabled_authority": probe.rejected_by_disabled_authority,
        "replay_identity_after": probe.replay_identity_after,
        "replay_identity_before": probe.replay_identity_before,
        "schema_version": probe.schema_version,
    }


def _dossier_payload(dossier: WC6ExecutionLabDossier) -> dict[str, object]:
    return {
        "activation_identity": dossier.activation_identity,
        "credential_authority": dossier.credential_authority,
        "decision_identity": dossier.decision_identity,
        "disabled_authority_identity": dossier.disabled_authority_identity,
        "duplicate_prevention_proven": dossier.duplicate_prevention_proven,
        "enabled_authority_identity": dossier.enabled_authority_identity,
        "engine_version": dossier.engine_version,
        "exact_retry_idempotence_proven": (
            dossier.exact_retry_idempotence_proven
        ),
        "execution_snapshot_identity": dossier.execution_snapshot_identity,
        "fill_identity": dossier.fill_identity,
        "first_commit_disposition": dossier.first_commit_disposition,
        "kill_switch_probe_identity": dossier.kill_switch_probe_identity,
        "kill_switch_proven": dossier.kill_switch_proven,
        "live_order_authority": dossier.live_order_authority,
        "mutation_identity": dossier.mutation_identity,
        "network_authority": dossier.network_authority,
        "partial_fill_status": dossier.partial_fill_status,
        "pretrade_identity": dossier.pretrade_identity,
        "processed_event_identity": dossier.processed_event_identity,
        "production_authority": dossier.production_authority,
        "real_capital": dossier.real_capital,
        "reconciliation_proven": dossier.reconciliation_proven,
        "retry_commit_disposition": dossier.retry_commit_disposition,
        "sandbox_adapter_status": dossier.sandbox_adapter_status,
        "schema_version": dossier.schema_version,
        "semantic": dossier.semantic,
        "state_after_identity": dossier.state_after_identity,
        "state_before_identity": dossier.state_before_identity,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
