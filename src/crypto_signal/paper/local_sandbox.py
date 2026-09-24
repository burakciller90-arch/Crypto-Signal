"""Deterministic WC6 local-sandbox order lifecycle and reconciliation.

This module is a local simulation adapter only. It never opens a network
connection, never accepts exchange credentials, never submits a real/testnet
order, and never mutates the canonical paper ledger. REAL_CAPITAL remains 0.

Partial fills are modeled only inside this sandbox rail. The accepted canonical
paper execution contract remains full-fill-only in v1.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol
from crypto_signal.paper.pipeline import materialize_planned_pretrade
from crypto_signal.paper.pretrade import PaperPretradeStatus
from crypto_signal.paper.state import PaperFundState
from crypto_signal.paper.venue_rules import (
    FrozenBinanceSpotVenueRules,
    PaperVenueBoundPretrade,
)
from crypto_signal.paper.write_authority import (
    PaperWriteAuthorityEvent,
    load_current_paper_write_authority,
)

WC6_LOCAL_SANDBOX_ENGINE_VERSION = "wc6-local-sandbox-order-lifecycle-v1/1"
WC6_LOCAL_SANDBOX_SCHEMA_VERSION = "wc6-local-sandbox-order-lifecycle-schema-v1/1"


class WC6SandboxAdapterStatus(StrEnum):
    LOCAL_DETERMINISTIC_SANDBOX = "local_deterministic_sandbox"


class WC6ExternalTestnetStatus(StrEnum):
    NOT_CONNECTED = "not_connected"


class WC6SandboxPartialFillStatus(StrEnum):
    SUPPORTED_SANDBOX_ONLY = "supported_sandbox_only"


class WC6SandboxOrderStatus(StrEnum):
    FILLED = "filled"
    REJECTED = "rejected"


class WC6SandboxRejectReason(StrEnum):
    PRETRADE_REJECTED = "pretrade_rejected"
    KILL_SWITCH_DISABLED = "kill_switch_disabled"


class WC6SandboxJournalDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


class WC6SandboxError(ValueError):
    """Raised when local sandbox evidence cannot be built safely."""


class WC6SandboxJournalConflict(WC6SandboxError):
    """Raised when one client-order key is reused with different evidence."""


@dataclass(frozen=True, slots=True)
class WC6SandboxAcknowledgement:
    acknowledgement_identity: str
    order_identity: str
    acknowledged_at_ms: int
    accepted: bool
    reject_reason: WC6SandboxRejectReason | None
    reject_detail: str | None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(
            self.acknowledgement_identity,
            "WC6 sandbox acknowledgement identity",
        )
        _require_sha256(self.order_identity, "WC6 sandbox order identity")
        if self.acknowledged_at_ms < 0:
            raise ValueError("sandbox acknowledgement time must be non-negative")
        if self.accepted:
            if self.reject_reason is not None or self.reject_detail is not None:
                raise ValueError(
                    "accepted sandbox acknowledgement cannot carry rejection"
                )
        else:
            if self.reject_reason is None or not self.reject_detail:
                raise ValueError(
                    "rejected sandbox acknowledgement requires reason/detail"
                )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.acknowledgement_identity != canonical_sha256(
            _acknowledgement_payload(self)
        ):
            raise ValueError("sandbox acknowledgement identity mismatch")


@dataclass(frozen=True, slots=True)
class WC6SandboxFillFragment:
    fragment_identity: str
    order_identity: str
    sequence_no: int
    quantity: Decimal
    fill_price: Decimal
    filled_at_ms: int
    cumulative_quantity: Decimal
    remaining_quantity: Decimal
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.fragment_identity, "WC6 sandbox fill identity")
        _require_sha256(self.order_identity, "WC6 sandbox order identity")
        if self.sequence_no <= 0:
            raise ValueError("sandbox fill sequence must be positive")
        for value, label in (
            (self.quantity, "sandbox fill quantity"),
            (self.fill_price, "sandbox fill price"),
            (self.cumulative_quantity, "sandbox cumulative quantity"),
            (self.remaining_quantity, "sandbox remaining quantity"),
        ):
            _require_finite_decimal(value, label)
        if self.quantity <= Decimal(0):
            raise ValueError("sandbox fill quantity must be positive")
        if self.fill_price <= Decimal(0):
            raise ValueError("sandbox fill price must be positive")
        if self.cumulative_quantity <= Decimal(0):
            raise ValueError("sandbox cumulative quantity must be positive")
        if self.remaining_quantity < Decimal(0):
            raise ValueError("sandbox remaining quantity cannot be negative")
        if self.filled_at_ms < 0:
            raise ValueError("sandbox fill time must be non-negative")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.fragment_identity != canonical_sha256(_fill_payload(self)):
            raise ValueError("sandbox fill fragment identity mismatch")


@dataclass(frozen=True, slots=True)
class WC6LocalSandboxTrace:
    trace_identity: str
    schema_version: str
    engine_version: str
    client_order_key: str
    order_identity: str
    pretrade_identity: str
    venue_rule_snapshot_identity: str
    execution_snapshot_identity: str
    authority_event_identity: str
    action: PaperAction
    symbol: PaperSymbol
    submitted_at_ms: int
    acknowledgement: WC6SandboxAcknowledgement
    status: WC6SandboxOrderStatus
    intended_quantity: Decimal | None
    reference_price: Decimal
    canonical_fill_identity: str | None
    canonical_fill_price: Decimal | None
    paper_shadow_mutation_identity: str | None
    simulated_fee_usdt: Decimal | None
    simulated_spread_usdt: Decimal | None
    simulated_slippage_usdt: Decimal | None
    fill_fragments: tuple[WC6SandboxFillFragment, ...]
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.trace_identity, "WC6 sandbox trace identity"),
            (self.client_order_key, "WC6 sandbox client-order key"),
            (self.order_identity, "WC6 sandbox order identity"),
            (self.pretrade_identity, "WC6 sandbox pretrade identity"),
            (
                self.venue_rule_snapshot_identity,
                "WC6 sandbox venue-rule identity",
            ),
            (
                self.execution_snapshot_identity,
                "WC6 sandbox execution snapshot identity",
            ),
            (
                self.authority_event_identity,
                "WC6 sandbox authority-event identity",
            ),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_LOCAL_SANDBOX_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 local-sandbox schema")
        if self.engine_version != WC6_LOCAL_SANDBOX_ENGINE_VERSION:
            raise ValueError("unsupported WC6 local-sandbox engine")
        if self.submitted_at_ms < 0:
            raise ValueError("sandbox submit time must be non-negative")
        _require_finite_decimal(self.reference_price, "sandbox reference price")
        if self.reference_price <= Decimal(0):
            raise ValueError("sandbox reference price must be positive")
        if self.acknowledgement.order_identity != self.order_identity:
            raise ValueError("sandbox acknowledgement lost order identity")
        if self.acknowledgement.acknowledged_at_ms < self.submitted_at_ms:
            raise ValueError("sandbox acknowledgement cannot predate submit")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")

        if self.status is WC6SandboxOrderStatus.REJECTED:
            if self.acknowledgement.accepted:
                raise ValueError("rejected sandbox trace cannot have accepted ack")
            if self.intended_quantity is not None:
                raise ValueError(
                    "rejected sandbox trace cannot carry intended quantity"
                )
            if self.fill_fragments:
                raise ValueError("rejected sandbox trace cannot carry fills")
            if any(
                value is not None
                for value in (
                    self.canonical_fill_identity,
                    self.canonical_fill_price,
                    self.paper_shadow_mutation_identity,
                    self.simulated_fee_usdt,
                    self.simulated_spread_usdt,
                    self.simulated_slippage_usdt,
                )
            ):
                raise ValueError(
                    "rejected sandbox trace cannot invent execution/accounting"
                )
        elif self.status is WC6SandboxOrderStatus.FILLED:
            if not self.acknowledgement.accepted:
                raise ValueError("filled sandbox trace requires accepted ack")
            if self.intended_quantity is None:
                raise ValueError("filled sandbox trace requires intended quantity")
            _require_finite_decimal(
                self.intended_quantity,
                "sandbox intended quantity",
            )
            if self.intended_quantity <= Decimal(0):
                raise ValueError("sandbox intended quantity must be positive")
            if len(self.fill_fragments) < 2:
                raise ValueError(
                    "WC6 sandbox partial-fill acceptance requires >=2 fills"
                )
            for value, label in (
                (self.canonical_fill_price, "sandbox canonical fill price"),
                (self.simulated_fee_usdt, "sandbox simulated fee"),
                (self.simulated_spread_usdt, "sandbox simulated spread"),
                (self.simulated_slippage_usdt, "sandbox simulated slippage"),
            ):
                if value is None:
                    raise ValueError(f"{label} is required")
                _require_finite_decimal(value, label)
            if (
                self.canonical_fill_identity is None
                or self.paper_shadow_mutation_identity is None
            ):
                raise ValueError(
                    "filled sandbox trace requires canonical fill/mutation lineage"
                )
            _require_sha256(
                self.canonical_fill_identity,
                "WC6 canonical fill identity",
            )
            _require_sha256(
                self.paper_shadow_mutation_identity,
                "WC6 paper shadow mutation identity",
            )
            _validate_fill_chain(self)
        else:
            raise ValueError("unsupported WC6 sandbox order status")

        if self.trace_identity != canonical_sha256(_trace_payload(self)):
            raise ValueError("WC6 sandbox trace identity mismatch")

    @property
    def acknowledgement_latency_ms(self) -> int:
        return self.acknowledgement.acknowledged_at_ms - self.submitted_at_ms

    @property
    def final_fill_latency_ms(self) -> int | None:
        if not self.fill_fragments:
            return None
        return self.fill_fragments[-1].filled_at_ms - self.submitted_at_ms

    @property
    def weighted_fill_price(self) -> Decimal | None:
        if not self.fill_fragments or self.intended_quantity is None:
            return None
        total = sum(
            (
                fragment.quantity * fragment.fill_price
                for fragment in self.fill_fragments
            ),
            Decimal(0),
        )
        return total / self.intended_quantity


@dataclass(frozen=True, slots=True)
class WC6SandboxExecutionDossier:
    dossier_identity: str
    schema_version: str
    engine_version: str
    accepted_trace_identity: str
    venue_rejection_trace_identity: str
    kill_switch_trace_identity: str
    accepted_acknowledgement_identity: str
    canonical_fill_identity: str
    paper_shadow_mutation_identity: str
    first_journal_disposition: WC6SandboxJournalDisposition
    retry_journal_disposition: WC6SandboxJournalDisposition
    partial_fill_count: int
    acknowledgement_latency_ms: int
    final_fill_latency_ms: int
    intended_quantity: Decimal
    reconciled_filled_quantity: Decimal
    weighted_fill_price: Decimal
    canonical_fill_price: Decimal
    latency_simulation_proven: bool
    slippage_simulation_proven: bool
    partial_fill_simulation_proven: bool
    venue_rejection_proven: bool
    kill_switch_proven: bool
    duplicate_prevention_proven: bool
    restart_idempotence_proven: bool
    reconciliation_proven: bool
    sandbox_adapter_status: WC6SandboxAdapterStatus
    external_testnet_status: WC6ExternalTestnetStatus
    partial_fill_status: WC6SandboxPartialFillStatus
    network_authority: bool = False
    credential_authority: bool = False
    live_order_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.dossier_identity, "WC6 sandbox dossier identity"),
            (self.accepted_trace_identity, "WC6 accepted trace identity"),
            (
                self.venue_rejection_trace_identity,
                "WC6 venue-rejection trace identity",
            ),
            (
                self.kill_switch_trace_identity,
                "WC6 kill-switch trace identity",
            ),
            (
                self.accepted_acknowledgement_identity,
                "WC6 accepted acknowledgement identity",
            ),
            (self.canonical_fill_identity, "WC6 canonical fill identity"),
            (
                self.paper_shadow_mutation_identity,
                "WC6 paper-shadow mutation identity",
            ),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_LOCAL_SANDBOX_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 sandbox dossier schema")
        if self.engine_version != WC6_LOCAL_SANDBOX_ENGINE_VERSION:
            raise ValueError("unsupported WC6 sandbox dossier engine")
        if self.first_journal_disposition is not (
            WC6SandboxJournalDisposition.INSERTED
        ):
            raise ValueError("WC6 first sandbox journal append must insert")
        if self.retry_journal_disposition is not (
            WC6SandboxJournalDisposition.UNCHANGED
        ):
            raise ValueError("WC6 sandbox restart retry must be unchanged")
        if self.partial_fill_count < 2:
            raise ValueError("WC6 sandbox dossier requires partial-fill lifecycle")
        if self.acknowledgement_latency_ms <= 0:
            raise ValueError("WC6 sandbox ack latency must be positive")
        if self.final_fill_latency_ms <= self.acknowledgement_latency_ms:
            raise ValueError("WC6 sandbox fill must occur after acknowledgement")
        for value, label in (
            (self.intended_quantity, "WC6 intended quantity"),
            (self.reconciled_filled_quantity, "WC6 filled quantity"),
            (self.weighted_fill_price, "WC6 weighted fill price"),
            (self.canonical_fill_price, "WC6 canonical fill price"),
        ):
            _require_finite_decimal(value, label)
            if value <= Decimal(0):
                raise ValueError(f"{label} must be positive")
        if self.intended_quantity != self.reconciled_filled_quantity:
            raise ValueError("WC6 sandbox filled quantity does not reconcile")
        if self.weighted_fill_price != self.canonical_fill_price:
            raise ValueError("WC6 sandbox weighted fill price does not reconcile")
        if not (
            self.latency_simulation_proven
            and self.slippage_simulation_proven
            and self.partial_fill_simulation_proven
            and self.venue_rejection_proven
            and self.kill_switch_proven
            and self.duplicate_prevention_proven
            and self.restart_idempotence_proven
            and self.reconciliation_proven
        ):
            raise ValueError("WC6 sandbox dossier requires all acceptance evidence")
        if self.sandbox_adapter_status is not (
            WC6SandboxAdapterStatus.LOCAL_DETERMINISTIC_SANDBOX
        ):
            raise ValueError("WC6 dossier requires local deterministic sandbox")
        if self.external_testnet_status is not WC6ExternalTestnetStatus.NOT_CONNECTED:
            raise ValueError("WC6 v1 must not imply external testnet connectivity")
        if self.partial_fill_status is not (
            WC6SandboxPartialFillStatus.SUPPORTED_SANDBOX_ONLY
        ):
            raise ValueError("WC6 partial fills must remain sandbox-only")
        if (
            self.network_authority
            or self.credential_authority
            or self.live_order_authority
            or self.production_authority
        ):
            raise ValueError("WC6 local sandbox grants no external/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.dossier_identity != canonical_sha256(_dossier_payload(self)):
            raise ValueError("WC6 sandbox dossier identity mismatch")


class WC6LocalSandboxJournal:
    """Immutable local sandbox trace journal with idempotent client-order keys."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS wc6_sandbox_traces (
                    client_order_key TEXT PRIMARY KEY,
                    trace_identity TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL
                )
                """
            )
            for action in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                    wc6_sandbox_traces_reject_{action.lower()}
                    BEFORE {action} ON wc6_sandbox_traces
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable WC6 sandbox journal rejects mutation'
                        );
                    END
                    """
                )

    def append(
        self,
        trace: WC6LocalSandboxTrace,
    ) -> WC6SandboxJournalDisposition:
        self.initialize()
        payload_json = canonical_json(trace)
        with sqlite3.connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT trace_identity, payload_json
                FROM wc6_sandbox_traces
                WHERE client_order_key = ?
                """,
                (trace.client_order_key,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == trace.trace_identity
                    and str(existing[1]) == payload_json
                ):
                    return WC6SandboxJournalDisposition.UNCHANGED
                raise WC6SandboxJournalConflict(
                    "sandbox client-order key conflicts with stored trace"
                )
            connection.execute(
                """
                INSERT INTO wc6_sandbox_traces (
                    client_order_key,
                    trace_identity,
                    payload_json,
                    created_at_ms
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    trace.client_order_key,
                    trace.trace_identity,
                    payload_json,
                    trace.submitted_at_ms,
                ),
            )
        return WC6SandboxJournalDisposition.INSERTED


def build_local_sandbox_trace(
    *,
    paper_ledger: PaperFundLedger,
    state: PaperFundState,
    bound_pretrade: PaperVenueBoundPretrade,
    venue_rules: FrozenBinanceSpotVenueRules,
    authority: PaperWriteAuthorityEvent,
    submitted_at_ms: int,
    acknowledgement_latency_ms: int,
    partial_fill_quantities: tuple[Decimal, ...] = (),
    partial_fill_latency_ms: tuple[int, ...] = (),
) -> WC6LocalSandboxTrace:
    """Build one deterministic local-sandbox order lifecycle without I/O."""

    _validate_bound_inputs(
        paper_ledger=paper_ledger,
        state=state,
        bound_pretrade=bound_pretrade,
        venue_rules=venue_rules,
        authority=authority,
    )
    if submitted_at_ms < 0:
        raise WC6SandboxError("sandbox submit time must be non-negative")
    if acknowledgement_latency_ms <= 0:
        raise WC6SandboxError("sandbox acknowledgement latency must be positive")

    pretrade = bound_pretrade.pretrade
    snapshot = bound_pretrade.execution_snapshot
    client_order_key = canonical_sha256(
        {
            "engine_version": WC6_LOCAL_SANDBOX_ENGINE_VERSION,
            "execution_snapshot_identity": snapshot.snapshot_identity,
            "pretrade_identity": pretrade.pretrade_identity,
            "venue_rule_snapshot_identity": venue_rules.snapshot_identity,
        }
    )
    order_identity = canonical_sha256(
        {
            "authority_event_identity": authority.authority_event_identity,
            "client_order_key": client_order_key,
            "submitted_at_ms": submitted_at_ms,
        }
    )
    acknowledged_at_ms = submitted_at_ms + acknowledgement_latency_ms

    if not authority.enabled:
        acknowledgement = _build_acknowledgement(
            order_identity=order_identity,
            acknowledged_at_ms=acknowledged_at_ms,
            accepted=False,
            reject_reason=WC6SandboxRejectReason.KILL_SWITCH_DISABLED,
            reject_detail="current virtual-paper write authority is disabled",
        )
        return _build_rejected_trace(
            client_order_key=client_order_key,
            order_identity=order_identity,
            pretrade_identity=pretrade.pretrade_identity,
            venue_rule_snapshot_identity=venue_rules.snapshot_identity,
            execution_snapshot_identity=snapshot.snapshot_identity,
            authority_event_identity=authority.authority_event_identity,
            action=pretrade.action,
            symbol=pretrade.symbol,
            submitted_at_ms=submitted_at_ms,
            acknowledgement=acknowledgement,
            reference_price=pretrade.reference_price,
        )

    if pretrade.status is PaperPretradeStatus.REJECTED:
        acknowledgement = _build_acknowledgement(
            order_identity=order_identity,
            acknowledged_at_ms=acknowledged_at_ms,
            accepted=False,
            reject_reason=WC6SandboxRejectReason.PRETRADE_REJECTED,
            reject_detail=pretrade.reason_code.value,
        )
        return _build_rejected_trace(
            client_order_key=client_order_key,
            order_identity=order_identity,
            pretrade_identity=pretrade.pretrade_identity,
            venue_rule_snapshot_identity=venue_rules.snapshot_identity,
            execution_snapshot_identity=snapshot.snapshot_identity,
            authority_event_identity=authority.authority_event_identity,
            action=pretrade.action,
            symbol=pretrade.symbol,
            submitted_at_ms=submitted_at_ms,
            acknowledgement=acknowledgement,
            reference_price=pretrade.reference_price,
        )

    if not partial_fill_quantities or not partial_fill_latency_ms:
        raise WC6SandboxError("accepted sandbox trace requires partial-fill schedule")
    if len(partial_fill_quantities) != len(partial_fill_latency_ms):
        raise WC6SandboxError("sandbox partial-fill schedule cardinality mismatch")
    if len(partial_fill_quantities) < 2:
        raise WC6SandboxError("sandbox partial-fill schedule requires >=2 fills")

    bundle = materialize_planned_pretrade(
        state=state,
        pretrade=pretrade,
        execution_snapshot=snapshot,
    )
    if bundle.fill is None or bundle.mutation is None or bundle.execution.costs is None:
        raise WC6SandboxError("accepted sandbox pretrade lost execution lineage")
    intended_quantity = pretrade.planned_quantity
    if intended_quantity is None:
        raise WC6SandboxError("accepted sandbox pretrade lost intended quantity")
    if sum(partial_fill_quantities, Decimal(0)) != intended_quantity:
        raise WC6SandboxError("sandbox partial-fill quantities must sum to intent")
    _validate_fragment_schedule(
        quantities=partial_fill_quantities,
        fill_latency_ms=partial_fill_latency_ms,
        acknowledgement_latency_ms=acknowledgement_latency_ms,
        quantity_step=snapshot.quantity_step,
    )

    acknowledgement = _build_acknowledgement(
        order_identity=order_identity,
        acknowledged_at_ms=acknowledged_at_ms,
        accepted=True,
        reject_reason=None,
        reject_detail=None,
    )
    fragments = _build_fill_fragments(
        order_identity=order_identity,
        intended_quantity=intended_quantity,
        fill_price=bundle.fill.simulated_fill_price,
        submitted_at_ms=submitted_at_ms,
        quantities=partial_fill_quantities,
        fill_latency_ms=partial_fill_latency_ms,
    )
    costs = bundle.execution.costs
    payload = {
        "acknowledgement": acknowledgement,
        "action": pretrade.action,
        "authority_event_identity": authority.authority_event_identity,
        "canonical_fill_identity": bundle.fill.record_identity,
        "canonical_fill_price": bundle.fill.simulated_fill_price,
        "client_order_key": client_order_key,
        "engine_version": WC6_LOCAL_SANDBOX_ENGINE_VERSION,
        "execution_snapshot_identity": snapshot.snapshot_identity,
        "fill_fragments": fragments,
        "intended_quantity": intended_quantity,
        "order_identity": order_identity,
        "paper_shadow_mutation_identity": bundle.mutation.record_identity,
        "pretrade_identity": pretrade.pretrade_identity,
        "real_capital": REAL_CAPITAL,
        "reference_price": pretrade.reference_price,
        "schema_version": WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        "simulated_fee_usdt": costs.fee_usdt,
        "simulated_slippage_usdt": costs.slippage_usdt,
        "simulated_spread_usdt": costs.spread_usdt,
        "status": WC6SandboxOrderStatus.FILLED,
        "submitted_at_ms": submitted_at_ms,
        "symbol": pretrade.symbol,
        "venue_rule_snapshot_identity": venue_rules.snapshot_identity,
    }
    return WC6LocalSandboxTrace(
        trace_identity=canonical_sha256(payload),
        schema_version=WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        engine_version=WC6_LOCAL_SANDBOX_ENGINE_VERSION,
        client_order_key=client_order_key,
        order_identity=order_identity,
        pretrade_identity=pretrade.pretrade_identity,
        venue_rule_snapshot_identity=venue_rules.snapshot_identity,
        execution_snapshot_identity=snapshot.snapshot_identity,
        authority_event_identity=authority.authority_event_identity,
        action=pretrade.action,
        symbol=pretrade.symbol,
        submitted_at_ms=submitted_at_ms,
        acknowledgement=acknowledgement,
        status=WC6SandboxOrderStatus.FILLED,
        intended_quantity=intended_quantity,
        reference_price=pretrade.reference_price,
        canonical_fill_identity=bundle.fill.record_identity,
        canonical_fill_price=bundle.fill.simulated_fill_price,
        paper_shadow_mutation_identity=bundle.mutation.record_identity,
        simulated_fee_usdt=costs.fee_usdt,
        simulated_spread_usdt=costs.spread_usdt,
        simulated_slippage_usdt=costs.slippage_usdt,
        fill_fragments=fragments,
        real_capital=REAL_CAPITAL,
    )


def build_wc6_sandbox_execution_dossier(
    *,
    accepted_trace: WC6LocalSandboxTrace,
    venue_rejection_trace: WC6LocalSandboxTrace,
    kill_switch_trace: WC6LocalSandboxTrace,
    first_journal_disposition: WC6SandboxJournalDisposition,
    retry_journal_disposition: WC6SandboxJournalDisposition,
) -> WC6SandboxExecutionDossier:
    """Bind one complete local-sandbox execution acceptance dossier."""

    if accepted_trace.status is not WC6SandboxOrderStatus.FILLED:
        raise WC6SandboxError("WC6 dossier requires one filled sandbox trace")
    if venue_rejection_trace.status is not WC6SandboxOrderStatus.REJECTED:
        raise WC6SandboxError("WC6 dossier requires venue rejection trace")
    if (
        venue_rejection_trace.acknowledgement.reject_reason
        is not WC6SandboxRejectReason.PRETRADE_REJECTED
    ):
        raise WC6SandboxError("WC6 venue rejection trace has wrong reason")
    if kill_switch_trace.status is not WC6SandboxOrderStatus.REJECTED:
        raise WC6SandboxError("WC6 dossier requires kill-switch rejection trace")
    if (
        kill_switch_trace.acknowledgement.reject_reason
        is not WC6SandboxRejectReason.KILL_SWITCH_DISABLED
    ):
        raise WC6SandboxError("WC6 kill-switch trace has wrong reason")
    if kill_switch_trace.client_order_key != accepted_trace.client_order_key:
        raise WC6SandboxError(
            "WC6 kill-switch must reject the same deterministic client-order key"
        )
    if first_journal_disposition is not WC6SandboxJournalDisposition.INSERTED:
        raise WC6SandboxError("WC6 sandbox journal first append must insert")
    if retry_journal_disposition is not WC6SandboxJournalDisposition.UNCHANGED:
        raise WC6SandboxError("WC6 sandbox journal exact retry must be unchanged")

    intended = accepted_trace.intended_quantity
    weighted = accepted_trace.weighted_fill_price
    canonical_price = accepted_trace.canonical_fill_price
    final_latency = accepted_trace.final_fill_latency_ms
    if intended is None or weighted is None or canonical_price is None:
        raise WC6SandboxError("WC6 accepted trace lacks reconciliation values")
    if final_latency is None:
        raise WC6SandboxError("WC6 accepted trace lacks fill latency")
    filled = sum(
        (fragment.quantity for fragment in accepted_trace.fill_fragments),
        Decimal(0),
    )
    if intended != filled or weighted != canonical_price:
        raise WC6SandboxError("WC6 sandbox fills do not reconcile to canonical fill")
    if (
        accepted_trace.canonical_fill_identity is None
        or accepted_trace.paper_shadow_mutation_identity is None
    ):
        raise WC6SandboxError("WC6 accepted trace lost paper accounting shadow")
    if (
        accepted_trace.simulated_slippage_usdt is None
        or accepted_trace.simulated_slippage_usdt <= Decimal(0)
    ):
        raise WC6SandboxError("WC6 sandbox requires explicit positive slippage")
    if accepted_trace.canonical_fill_price == accepted_trace.reference_price:
        raise WC6SandboxError("WC6 sandbox slippage did not affect fill price")

    payload = {
        "accepted_acknowledgement_identity": (
            accepted_trace.acknowledgement.acknowledgement_identity
        ),
        "accepted_trace_identity": accepted_trace.trace_identity,
        "acknowledgement_latency_ms": accepted_trace.acknowledgement_latency_ms,
        "canonical_fill_identity": accepted_trace.canonical_fill_identity,
        "canonical_fill_price": canonical_price,
        "credential_authority": False,
        "duplicate_prevention_proven": True,
        "engine_version": WC6_LOCAL_SANDBOX_ENGINE_VERSION,
        "external_testnet_status": WC6ExternalTestnetStatus.NOT_CONNECTED,
        "final_fill_latency_ms": final_latency,
        "first_journal_disposition": first_journal_disposition,
        "intended_quantity": intended,
        "kill_switch_proven": True,
        "kill_switch_trace_identity": kill_switch_trace.trace_identity,
        "latency_simulation_proven": True,
        "live_order_authority": False,
        "network_authority": False,
        "paper_shadow_mutation_identity": (
            accepted_trace.paper_shadow_mutation_identity
        ),
        "partial_fill_count": len(accepted_trace.fill_fragments),
        "partial_fill_simulation_proven": True,
        "partial_fill_status": WC6SandboxPartialFillStatus.SUPPORTED_SANDBOX_ONLY,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reconciled_filled_quantity": filled,
        "reconciliation_proven": True,
        "restart_idempotence_proven": True,
        "retry_journal_disposition": retry_journal_disposition,
        "sandbox_adapter_status": (
            WC6SandboxAdapterStatus.LOCAL_DETERMINISTIC_SANDBOX
        ),
        "schema_version": WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        "slippage_simulation_proven": True,
        "venue_rejection_proven": True,
        "venue_rejection_trace_identity": venue_rejection_trace.trace_identity,
        "weighted_fill_price": weighted,
    }
    return WC6SandboxExecutionDossier(
        dossier_identity=canonical_sha256(payload),
        schema_version=WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        engine_version=WC6_LOCAL_SANDBOX_ENGINE_VERSION,
        accepted_trace_identity=accepted_trace.trace_identity,
        venue_rejection_trace_identity=venue_rejection_trace.trace_identity,
        kill_switch_trace_identity=kill_switch_trace.trace_identity,
        accepted_acknowledgement_identity=(
            accepted_trace.acknowledgement.acknowledgement_identity
        ),
        canonical_fill_identity=accepted_trace.canonical_fill_identity,
        paper_shadow_mutation_identity=(
            accepted_trace.paper_shadow_mutation_identity
        ),
        first_journal_disposition=first_journal_disposition,
        retry_journal_disposition=retry_journal_disposition,
        partial_fill_count=len(accepted_trace.fill_fragments),
        acknowledgement_latency_ms=accepted_trace.acknowledgement_latency_ms,
        final_fill_latency_ms=final_latency,
        intended_quantity=intended,
        reconciled_filled_quantity=filled,
        weighted_fill_price=weighted,
        canonical_fill_price=canonical_price,
        latency_simulation_proven=True,
        slippage_simulation_proven=True,
        partial_fill_simulation_proven=True,
        venue_rejection_proven=True,
        kill_switch_proven=True,
        duplicate_prevention_proven=True,
        restart_idempotence_proven=True,
        reconciliation_proven=True,
        sandbox_adapter_status=(
            WC6SandboxAdapterStatus.LOCAL_DETERMINISTIC_SANDBOX
        ),
        external_testnet_status=WC6ExternalTestnetStatus.NOT_CONNECTED,
        partial_fill_status=WC6SandboxPartialFillStatus.SUPPORTED_SANDBOX_ONLY,
        network_authority=False,
        credential_authority=False,
        live_order_authority=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def _validate_bound_inputs(
    *,
    paper_ledger: PaperFundLedger,
    state: PaperFundState,
    bound_pretrade: PaperVenueBoundPretrade,
    venue_rules: FrozenBinanceSpotVenueRules,
    authority: PaperWriteAuthorityEvent,
) -> None:
    if (
        state.real_capital != REAL_CAPITAL
        or bound_pretrade.real_capital != REAL_CAPITAL
        or venue_rules.real_capital != REAL_CAPITAL
        or authority.real_capital != REAL_CAPITAL
    ):
        raise WC6SandboxError("REAL_CAPITAL must remain 0")
    current = load_current_paper_write_authority(paper_ledger)
    if current != authority:
        raise WC6SandboxError(
            "sandbox simulation requires exact current paper write authority"
        )
    if bound_pretrade.venue_rule_snapshot_identity != venue_rules.snapshot_identity:
        raise WC6SandboxError("sandbox venue-rule lineage mismatch")
    if bound_pretrade.pretrade.symbol is not venue_rules.symbol:
        raise WC6SandboxError("sandbox venue-rule symbol mismatch")
    marker = f"|rules:{venue_rules.snapshot_identity}|"
    if marker not in bound_pretrade.execution_snapshot.venue_reference:
        raise WC6SandboxError("sandbox execution snapshot lost venue-rule identity")


def _build_rejected_trace(
    *,
    client_order_key: str,
    order_identity: str,
    pretrade_identity: str,
    venue_rule_snapshot_identity: str,
    execution_snapshot_identity: str,
    authority_event_identity: str,
    action: PaperAction,
    symbol: PaperSymbol,
    submitted_at_ms: int,
    acknowledgement: WC6SandboxAcknowledgement,
    reference_price: Decimal,
) -> WC6LocalSandboxTrace:
    payload = {
        "acknowledgement": acknowledgement,
        "action": action,
        "authority_event_identity": authority_event_identity,
        "canonical_fill_identity": None,
        "canonical_fill_price": None,
        "client_order_key": client_order_key,
        "engine_version": WC6_LOCAL_SANDBOX_ENGINE_VERSION,
        "execution_snapshot_identity": execution_snapshot_identity,
        "fill_fragments": (),
        "intended_quantity": None,
        "order_identity": order_identity,
        "paper_shadow_mutation_identity": None,
        "pretrade_identity": pretrade_identity,
        "real_capital": REAL_CAPITAL,
        "reference_price": reference_price,
        "schema_version": WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        "simulated_fee_usdt": None,
        "simulated_slippage_usdt": None,
        "simulated_spread_usdt": None,
        "status": WC6SandboxOrderStatus.REJECTED,
        "submitted_at_ms": submitted_at_ms,
        "symbol": symbol,
        "venue_rule_snapshot_identity": venue_rule_snapshot_identity,
    }
    return WC6LocalSandboxTrace(
        trace_identity=canonical_sha256(payload),
        schema_version=WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        engine_version=WC6_LOCAL_SANDBOX_ENGINE_VERSION,
        client_order_key=client_order_key,
        order_identity=order_identity,
        pretrade_identity=pretrade_identity,
        venue_rule_snapshot_identity=venue_rule_snapshot_identity,
        execution_snapshot_identity=execution_snapshot_identity,
        authority_event_identity=authority_event_identity,
        action=action,
        symbol=symbol,
        submitted_at_ms=submitted_at_ms,
        acknowledgement=acknowledgement,
        status=WC6SandboxOrderStatus.REJECTED,
        intended_quantity=None,
        reference_price=reference_price,
        canonical_fill_identity=None,
        canonical_fill_price=None,
        paper_shadow_mutation_identity=None,
        simulated_fee_usdt=None,
        simulated_spread_usdt=None,
        simulated_slippage_usdt=None,
        fill_fragments=(),
        real_capital=REAL_CAPITAL,
    )


def _build_acknowledgement(
    *,
    order_identity: str,
    acknowledged_at_ms: int,
    accepted: bool,
    reject_reason: WC6SandboxRejectReason | None,
    reject_detail: str | None,
) -> WC6SandboxAcknowledgement:
    payload = {
        "accepted": accepted,
        "acknowledged_at_ms": acknowledged_at_ms,
        "order_identity": order_identity,
        "real_capital": REAL_CAPITAL,
        "reject_detail": reject_detail,
        "reject_reason": reject_reason,
    }
    return WC6SandboxAcknowledgement(
        acknowledgement_identity=canonical_sha256(payload),
        order_identity=order_identity,
        acknowledged_at_ms=acknowledged_at_ms,
        accepted=accepted,
        reject_reason=reject_reason,
        reject_detail=reject_detail,
        real_capital=REAL_CAPITAL,
    )


def _build_fill_fragments(
    *,
    order_identity: str,
    intended_quantity: Decimal,
    fill_price: Decimal,
    submitted_at_ms: int,
    quantities: tuple[Decimal, ...],
    fill_latency_ms: tuple[int, ...],
) -> tuple[WC6SandboxFillFragment, ...]:
    fragments: list[WC6SandboxFillFragment] = []
    cumulative = Decimal(0)
    for sequence_no, (quantity, latency_ms) in enumerate(
        zip(quantities, fill_latency_ms, strict=True),
        start=1,
    ):
        cumulative += quantity
        remaining = intended_quantity - cumulative
        payload = {
            "cumulative_quantity": cumulative,
            "fill_price": fill_price,
            "filled_at_ms": submitted_at_ms + latency_ms,
            "order_identity": order_identity,
            "quantity": quantity,
            "real_capital": REAL_CAPITAL,
            "remaining_quantity": remaining,
            "sequence_no": sequence_no,
        }
        fragments.append(
            WC6SandboxFillFragment(
                fragment_identity=canonical_sha256(payload),
                order_identity=order_identity,
                sequence_no=sequence_no,
                quantity=quantity,
                fill_price=fill_price,
                filled_at_ms=submitted_at_ms + latency_ms,
                cumulative_quantity=cumulative,
                remaining_quantity=remaining,
                real_capital=REAL_CAPITAL,
            )
        )
    return tuple(fragments)


def _validate_fragment_schedule(
    *,
    quantities: tuple[Decimal, ...],
    fill_latency_ms: tuple[int, ...],
    acknowledgement_latency_ms: int,
    quantity_step: Decimal,
) -> None:
    previous_latency = acknowledgement_latency_ms
    for quantity, latency_ms in zip(
        quantities,
        fill_latency_ms,
        strict=True,
    ):
        _require_finite_decimal(quantity, "sandbox partial-fill quantity")
        if quantity <= Decimal(0):
            raise WC6SandboxError("sandbox partial-fill quantity must be positive")
        steps = quantity / quantity_step
        if steps != steps.to_integral_value():
            raise WC6SandboxError(
                "sandbox partial-fill quantity violates quantity step"
            )
        if latency_ms <= previous_latency:
            raise WC6SandboxError(
                "sandbox fill latencies must be strictly increasing after ack"
            )
        previous_latency = latency_ms


def _validate_fill_chain(trace: WC6LocalSandboxTrace) -> None:
    intended = trace.intended_quantity
    canonical_price = trace.canonical_fill_price
    if intended is None or canonical_price is None:
        raise ValueError("filled sandbox trace lost intended/canonical values")
    cumulative = Decimal(0)
    previous_time = trace.acknowledgement.acknowledged_at_ms
    for expected_sequence, fragment in enumerate(trace.fill_fragments, start=1):
        if fragment.order_identity != trace.order_identity:
            raise ValueError("sandbox fill lost order identity")
        if fragment.sequence_no != expected_sequence:
            raise ValueError("sandbox fill sequence is discontinuous")
        if fragment.filled_at_ms <= previous_time:
            raise ValueError("sandbox fills must be strictly chronological")
        if fragment.fill_price != canonical_price:
            raise ValueError("sandbox fragment price diverges from canonical fill")
        cumulative += fragment.quantity
        if fragment.cumulative_quantity != cumulative:
            raise ValueError("sandbox cumulative quantity mismatch")
        if fragment.remaining_quantity != intended - cumulative:
            raise ValueError("sandbox remaining quantity mismatch")
        previous_time = fragment.filled_at_ms
    if cumulative != intended:
        raise ValueError("sandbox partial fills do not complete intended quantity")
    if trace.fill_fragments[-1].remaining_quantity != Decimal(0):
        raise ValueError("sandbox final partial fill must complete order")
    if trace.weighted_fill_price != canonical_price:
        raise ValueError("sandbox weighted fill price mismatch")


def _acknowledgement_payload(
    acknowledgement: WC6SandboxAcknowledgement,
) -> dict[str, object]:
    return {
        "accepted": acknowledgement.accepted,
        "acknowledged_at_ms": acknowledgement.acknowledged_at_ms,
        "order_identity": acknowledgement.order_identity,
        "real_capital": acknowledgement.real_capital,
        "reject_detail": acknowledgement.reject_detail,
        "reject_reason": acknowledgement.reject_reason,
    }


def _fill_payload(fragment: WC6SandboxFillFragment) -> dict[str, object]:
    return {
        "cumulative_quantity": fragment.cumulative_quantity,
        "fill_price": fragment.fill_price,
        "filled_at_ms": fragment.filled_at_ms,
        "order_identity": fragment.order_identity,
        "quantity": fragment.quantity,
        "real_capital": fragment.real_capital,
        "remaining_quantity": fragment.remaining_quantity,
        "sequence_no": fragment.sequence_no,
    }


def _trace_payload(trace: WC6LocalSandboxTrace) -> dict[str, object]:
    return {
        "acknowledgement": trace.acknowledgement,
        "action": trace.action,
        "authority_event_identity": trace.authority_event_identity,
        "canonical_fill_identity": trace.canonical_fill_identity,
        "canonical_fill_price": trace.canonical_fill_price,
        "client_order_key": trace.client_order_key,
        "engine_version": trace.engine_version,
        "execution_snapshot_identity": trace.execution_snapshot_identity,
        "fill_fragments": trace.fill_fragments,
        "intended_quantity": trace.intended_quantity,
        "order_identity": trace.order_identity,
        "paper_shadow_mutation_identity": trace.paper_shadow_mutation_identity,
        "pretrade_identity": trace.pretrade_identity,
        "real_capital": trace.real_capital,
        "reference_price": trace.reference_price,
        "schema_version": trace.schema_version,
        "simulated_fee_usdt": trace.simulated_fee_usdt,
        "simulated_slippage_usdt": trace.simulated_slippage_usdt,
        "simulated_spread_usdt": trace.simulated_spread_usdt,
        "status": trace.status,
        "submitted_at_ms": trace.submitted_at_ms,
        "symbol": trace.symbol,
        "venue_rule_snapshot_identity": trace.venue_rule_snapshot_identity,
    }


def _dossier_payload(
    dossier: WC6SandboxExecutionDossier,
) -> dict[str, object]:
    return {
        "accepted_acknowledgement_identity": (
            dossier.accepted_acknowledgement_identity
        ),
        "accepted_trace_identity": dossier.accepted_trace_identity,
        "acknowledgement_latency_ms": dossier.acknowledgement_latency_ms,
        "canonical_fill_identity": dossier.canonical_fill_identity,
        "canonical_fill_price": dossier.canonical_fill_price,
        "credential_authority": dossier.credential_authority,
        "duplicate_prevention_proven": dossier.duplicate_prevention_proven,
        "engine_version": dossier.engine_version,
        "external_testnet_status": dossier.external_testnet_status,
        "final_fill_latency_ms": dossier.final_fill_latency_ms,
        "first_journal_disposition": dossier.first_journal_disposition,
        "intended_quantity": dossier.intended_quantity,
        "kill_switch_proven": dossier.kill_switch_proven,
        "kill_switch_trace_identity": dossier.kill_switch_trace_identity,
        "latency_simulation_proven": dossier.latency_simulation_proven,
        "live_order_authority": dossier.live_order_authority,
        "network_authority": dossier.network_authority,
        "paper_shadow_mutation_identity": dossier.paper_shadow_mutation_identity,
        "partial_fill_count": dossier.partial_fill_count,
        "partial_fill_simulation_proven": (
            dossier.partial_fill_simulation_proven
        ),
        "partial_fill_status": dossier.partial_fill_status,
        "production_authority": dossier.production_authority,
        "real_capital": dossier.real_capital,
        "reconciled_filled_quantity": dossier.reconciled_filled_quantity,
        "reconciliation_proven": dossier.reconciliation_proven,
        "restart_idempotence_proven": dossier.restart_idempotence_proven,
        "retry_journal_disposition": dossier.retry_journal_disposition,
        "sandbox_adapter_status": dossier.sandbox_adapter_status,
        "schema_version": dossier.schema_version,
        "slippage_simulation_proven": dossier.slippage_simulation_proven,
        "venue_rejection_proven": dossier.venue_rejection_proven,
        "venue_rejection_trace_identity": dossier.venue_rejection_trace_identity,
        "weighted_fill_price": dossier.weighted_fill_price,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")


def _require_finite_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")
