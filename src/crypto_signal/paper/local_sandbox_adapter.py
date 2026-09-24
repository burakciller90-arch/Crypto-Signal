"""WC6 local deterministic sandbox adapter over accepted shadow lifecycle.

This adapter wraps the already-accepted lab-only acknowledgement/partial-fill
lifecycle with an immutable client-order journal plus explicit venue-policy and
kill-switch rejection evidence. It has no network, credential, exchange,
broker, testnet, or real-order surface. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.execution_lab_lifecycle import (
    WC6PartialFillSupport,
    WC6ShadowOrderLifecycle,
)
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.pretrade import PaperPretradeStatus
from crypto_signal.paper.venue_rules import (
    FrozenBinanceSpotVenueRules,
    PaperVenueBoundPretrade,
)
from crypto_signal.paper.write_authority import (
    PaperWriteAuthorityEvent,
    load_current_paper_write_authority,
)

WC6_LOCAL_SANDBOX_ADAPTER_VERSION = "wc6-local-sandbox-adapter-v1/1"
WC6_LOCAL_SANDBOX_SCHEMA_VERSION = "wc6-local-sandbox-adapter-schema-v1/1"


class WC6LocalSandboxAdapterStatus(StrEnum):
    IMPLEMENTED_NO_NETWORK = "implemented_no_network"


class WC6ExternalTestnetStatus(StrEnum):
    NOT_CONNECTED = "not_connected"


class WC6SandboxRejectReason(StrEnum):
    VENUE_POLICY_REJECTED = "venue_policy_rejected"
    KILL_SWITCH_DISABLED = "kill_switch_disabled"


class WC6SandboxJournalDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


class WC6LocalSandboxError(ValueError):
    """Raised when local-sandbox evidence cannot be reconciled safely."""


class WC6SandboxJournalConflict(WC6LocalSandboxError):
    """Raised when a deterministic client-order key is reused inconsistently."""


@dataclass(frozen=True, slots=True)
class WC6LocalSandboxAcceptedOrder:
    adapter_order_identity: str
    schema_version: str
    adapter_version: str
    client_order_key: str
    lifecycle_identity: str
    order_identity: str
    acknowledgement_identity: str
    pretrade_identity: str
    execution_snapshot_identity: str
    venue_rule_snapshot_identity: str
    authority_event_identity: str
    submitted_at_ms: int
    acknowledgement_latency_ms: int
    final_fill_latency_ms: int
    canonical_fill_identity: str
    canonical_mutation_identity: str
    partial_fill_identities: tuple[str, ...]
    adapter_status: WC6LocalSandboxAdapterStatus
    external_testnet_status: WC6ExternalTestnetStatus
    network_authority: bool = False
    credential_authority: bool = False
    live_order_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.adapter_order_identity, "WC6 adapter-order identity"),
            (self.client_order_key, "WC6 client-order key"),
            (self.lifecycle_identity, "WC6 lifecycle identity"),
            (self.order_identity, "WC6 shadow order identity"),
            (self.acknowledgement_identity, "WC6 acknowledgement identity"),
            (self.pretrade_identity, "WC6 pretrade identity"),
            (
                self.execution_snapshot_identity,
                "WC6 execution snapshot identity",
            ),
            (
                self.venue_rule_snapshot_identity,
                "WC6 venue-rule snapshot identity",
            ),
            (self.authority_event_identity, "WC6 authority-event identity"),
            (self.canonical_fill_identity, "WC6 canonical fill identity"),
            (
                self.canonical_mutation_identity,
                "WC6 canonical mutation identity",
            ),
        ):
            _require_sha256(value, label)
        if not self.partial_fill_identities:
            raise ValueError("WC6 adapter order requires partial-fill identities")
        for identity in self.partial_fill_identities:
            _require_sha256(identity, "WC6 partial-fill identity")
        if self.schema_version != WC6_LOCAL_SANDBOX_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 local-sandbox schema")
        if self.adapter_version != WC6_LOCAL_SANDBOX_ADAPTER_VERSION:
            raise ValueError("unsupported WC6 local-sandbox adapter")
        if self.submitted_at_ms < 0:
            raise ValueError("WC6 sandbox submit time cannot be negative")
        if self.acknowledgement_latency_ms <= 0:
            raise ValueError("WC6 sandbox acknowledgement latency must be positive")
        if self.final_fill_latency_ms <= self.acknowledgement_latency_ms:
            raise ValueError("WC6 sandbox final fill must follow acknowledgement")
        if self.adapter_status is not (
            WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK
        ):
            raise ValueError("WC6 local sandbox must remain no-network")
        if self.external_testnet_status is not WC6ExternalTestnetStatus.NOT_CONNECTED:
            raise ValueError("WC6 adapter must not imply external testnet")
        if (
            self.network_authority
            or self.credential_authority
            or self.live_order_authority
            or self.production_authority
        ):
            raise ValueError("WC6 local sandbox grants no external/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.adapter_order_identity != canonical_sha256(
            _accepted_order_payload(self)
        ):
            raise ValueError("WC6 adapter-order identity mismatch")


@dataclass(frozen=True, slots=True)
class WC6LocalSandboxRejection:
    rejection_identity: str
    schema_version: str
    adapter_version: str
    client_order_key: str
    pretrade_identity: str
    execution_snapshot_identity: str
    venue_rule_snapshot_identity: str
    authority_event_identity: str
    submitted_at_ms: int
    acknowledged_at_ms: int
    reason: WC6SandboxRejectReason
    detail: str
    adapter_status: WC6LocalSandboxAdapterStatus
    external_testnet_status: WC6ExternalTestnetStatus
    fill_count: int = 0
    network_authority: bool = False
    credential_authority: bool = False
    live_order_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.rejection_identity, "WC6 rejection identity"),
            (self.client_order_key, "WC6 client-order key"),
            (self.pretrade_identity, "WC6 pretrade identity"),
            (
                self.execution_snapshot_identity,
                "WC6 execution snapshot identity",
            ),
            (
                self.venue_rule_snapshot_identity,
                "WC6 venue-rule snapshot identity",
            ),
            (self.authority_event_identity, "WC6 authority-event identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_LOCAL_SANDBOX_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 rejection schema")
        if self.adapter_version != WC6_LOCAL_SANDBOX_ADAPTER_VERSION:
            raise ValueError("unsupported WC6 rejection adapter")
        if self.submitted_at_ms < 0:
            raise ValueError("WC6 rejection submit time cannot be negative")
        if self.acknowledged_at_ms <= self.submitted_at_ms:
            raise ValueError("WC6 rejection acknowledgement must follow submit")
        if not self.detail.strip():
            raise ValueError("WC6 rejection detail must be non-empty")
        if self.fill_count != 0:
            raise ValueError("WC6 rejected sandbox order cannot contain fills")
        if self.adapter_status is not (
            WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK
        ):
            raise ValueError("WC6 rejection must remain local sandbox")
        if self.external_testnet_status is not WC6ExternalTestnetStatus.NOT_CONNECTED:
            raise ValueError("WC6 rejection must not imply external testnet")
        if (
            self.network_authority
            or self.credential_authority
            or self.live_order_authority
            or self.production_authority
        ):
            raise ValueError("WC6 rejection grants no external/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.rejection_identity != canonical_sha256(_rejection_payload(self)):
            raise ValueError("WC6 sandbox rejection identity mismatch")

    @property
    def acknowledgement_latency_ms(self) -> int:
        return self.acknowledged_at_ms - self.submitted_at_ms


@dataclass(frozen=True, slots=True)
class WC6LocalSandboxDossier:
    dossier_identity: str
    schema_version: str
    adapter_version: str
    accepted_adapter_order_identity: str
    accepted_lifecycle_identity: str
    venue_rejection_identity: str
    kill_switch_rejection_identity: str
    canonical_fill_identity: str
    canonical_mutation_identity: str
    first_journal_disposition: WC6SandboxJournalDisposition
    restart_retry_disposition: WC6SandboxJournalDisposition
    partial_fill_count: int
    acknowledgement_latency_ms: int
    final_fill_latency_ms: int
    quantity_reconciled: bool
    notional_reconciled: bool
    accounting_shadow_reconciled: bool
    venue_rejection_proven: bool
    kill_switch_proven: bool
    duplicate_prevention_proven: bool
    restart_idempotence_proven: bool
    adapter_status: WC6LocalSandboxAdapterStatus
    external_testnet_status: WC6ExternalTestnetStatus
    partial_fill_support: WC6PartialFillSupport
    network_authority: bool = False
    credential_authority: bool = False
    live_order_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.dossier_identity, "WC6 sandbox dossier identity"),
            (
                self.accepted_adapter_order_identity,
                "WC6 accepted adapter-order identity",
            ),
            (
                self.accepted_lifecycle_identity,
                "WC6 accepted lifecycle identity",
            ),
            (self.venue_rejection_identity, "WC6 venue-rejection identity"),
            (
                self.kill_switch_rejection_identity,
                "WC6 kill-switch rejection identity",
            ),
            (self.canonical_fill_identity, "WC6 canonical fill identity"),
            (
                self.canonical_mutation_identity,
                "WC6 canonical mutation identity",
            ),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_LOCAL_SANDBOX_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 sandbox dossier schema")
        if self.adapter_version != WC6_LOCAL_SANDBOX_ADAPTER_VERSION:
            raise ValueError("unsupported WC6 sandbox dossier adapter")
        if self.first_journal_disposition is not (
            WC6SandboxJournalDisposition.INSERTED
        ):
            raise ValueError("WC6 first sandbox journal append must insert")
        if self.restart_retry_disposition is not (
            WC6SandboxJournalDisposition.UNCHANGED
        ):
            raise ValueError("WC6 sandbox restart retry must be unchanged")
        if self.partial_fill_count < 2:
            raise ValueError("WC6 sandbox dossier requires partial fills")
        if self.acknowledgement_latency_ms <= 0:
            raise ValueError("WC6 acknowledgement latency must be positive")
        if self.final_fill_latency_ms <= self.acknowledgement_latency_ms:
            raise ValueError("WC6 final fill cannot predate acknowledgement")
        if not (
            self.quantity_reconciled
            and self.notional_reconciled
            and self.accounting_shadow_reconciled
            and self.venue_rejection_proven
            and self.kill_switch_proven
            and self.duplicate_prevention_proven
            and self.restart_idempotence_proven
        ):
            raise ValueError("WC6 sandbox dossier requires all acceptance evidence")
        if self.adapter_status is not (
            WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK
        ):
            raise ValueError("WC6 sandbox dossier requires local adapter")
        if self.external_testnet_status is not WC6ExternalTestnetStatus.NOT_CONNECTED:
            raise ValueError("WC6 sandbox dossier must not imply external testnet")
        if self.partial_fill_support is not (
            WC6PartialFillSupport.LAB_ONLY_CANONICAL_UNSUPPORTED
        ):
            raise ValueError("WC6 partial fills must remain lab-only")
        if (
            self.network_authority
            or self.credential_authority
            or self.live_order_authority
            or self.production_authority
        ):
            raise ValueError("WC6 sandbox dossier grants no external/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.dossier_identity != canonical_sha256(_dossier_payload(self)):
            raise ValueError("WC6 sandbox dossier identity mismatch")


class WC6LocalSandboxJournal:
    """Immutable local sandbox journal keyed by deterministic client-order key."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS wc6_local_sandbox_orders (
                    client_order_key TEXT PRIMARY KEY,
                    adapter_order_identity TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL
                )
                """
            )
            for action in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                    wc6_local_sandbox_orders_reject_{action.lower()}
                    BEFORE {action} ON wc6_local_sandbox_orders
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable WC6 local sandbox journal rejects mutation'
                        );
                    END
                    """
                )

    def append(
        self,
        order: WC6LocalSandboxAcceptedOrder,
    ) -> WC6SandboxJournalDisposition:
        self.initialize()
        payload_json = canonical_json(order)
        with sqlite3.connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT adapter_order_identity, payload_json
                FROM wc6_local_sandbox_orders
                WHERE client_order_key = ?
                """,
                (order.client_order_key,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == order.adapter_order_identity
                    and str(existing[1]) == payload_json
                ):
                    return WC6SandboxJournalDisposition.UNCHANGED
                raise WC6SandboxJournalConflict(
                    "sandbox client-order key conflicts with stored order"
                )
            connection.execute(
                """
                INSERT INTO wc6_local_sandbox_orders (
                    client_order_key,
                    adapter_order_identity,
                    payload_json
                )
                VALUES (?, ?, ?)
                """,
                (
                    order.client_order_key,
                    order.adapter_order_identity,
                    payload_json,
                ),
            )
        return WC6SandboxJournalDisposition.INSERTED


def build_local_sandbox_accepted_order(
    *,
    paper_ledger: PaperFundLedger,
    lifecycle: WC6ShadowOrderLifecycle,
    bound_pretrade: PaperVenueBoundPretrade,
    venue_rules: FrozenBinanceSpotVenueRules,
    authority: PaperWriteAuthorityEvent,
) -> WC6LocalSandboxAcceptedOrder:
    """Bind one accepted shadow lifecycle to a no-network sandbox adapter."""

    _validate_common(
        paper_ledger=paper_ledger,
        bound_pretrade=bound_pretrade,
        venue_rules=venue_rules,
        authority=authority,
    )
    if not authority.enabled:
        raise WC6LocalSandboxError(
            "accepted sandbox order requires enabled paper write authority"
        )
    if bound_pretrade.pretrade.status is not PaperPretradeStatus.PLANNED:
        raise WC6LocalSandboxError(
            "accepted sandbox order requires PLANNED pretrade"
        )
    if lifecycle.pretrade_identity != bound_pretrade.pretrade.pretrade_identity:
        raise WC6LocalSandboxError("sandbox lifecycle/pretrade mismatch")
    if (
        lifecycle.execution_snapshot_identity
        != bound_pretrade.execution_snapshot.snapshot_identity
    ):
        raise WC6LocalSandboxError("sandbox lifecycle/snapshot mismatch")
    plan = bound_pretrade.pretrade.plan
    if plan is None:
        raise WC6LocalSandboxError("accepted sandbox order lost paper plan")
    submitted_at_ms = plan.planned_at_ms
    acknowledgement_latency_ms = (
        lifecycle.acknowledgement.acknowledged_at_ms - submitted_at_ms
    )
    final_fill_latency_ms = (
        lifecycle.partial_fills[-1].filled_at_ms - submitted_at_ms
    )
    if acknowledgement_latency_ms <= 0:
        raise WC6LocalSandboxError(
            "accepted sandbox acknowledgement latency must be positive"
        )
    if final_fill_latency_ms <= acknowledgement_latency_ms:
        raise WC6LocalSandboxError(
            "accepted sandbox final fill must follow acknowledgement"
        )
    if lifecycle.sandbox_adapter_implemented:
        raise WC6LocalSandboxError(
            "shadow lifecycle must remain adapter-agnostic before wrapping"
        )
    if not (
        lifecycle.quantity_reconciled
        and lifecycle.notional_reconciled
        and lifecycle.accounting_shadow_reconciled
    ):
        raise WC6LocalSandboxError("sandbox lifecycle is not reconciled")

    client_order_key = _client_order_key(
        pretrade_identity=lifecycle.pretrade_identity,
        execution_snapshot_identity=lifecycle.execution_snapshot_identity,
        venue_rule_snapshot_identity=venue_rules.snapshot_identity,
    )
    payload = {
        "acknowledgement_identity": (
            lifecycle.acknowledgement.acknowledgement_identity
        ),
        "adapter_status": WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK,
        "adapter_version": WC6_LOCAL_SANDBOX_ADAPTER_VERSION,
        "authority_event_identity": authority.authority_event_identity,
        "acknowledgement_latency_ms": accepted_order.acknowledgement_latency_ms,
        "canonical_fill_identity": lifecycle.canonical_fill_identity,
        "canonical_mutation_identity": lifecycle.canonical_mutation_identity,
        "client_order_key": client_order_key,
        "credential_authority": False,
        "execution_snapshot_identity": lifecycle.execution_snapshot_identity,
        "external_testnet_status": WC6ExternalTestnetStatus.NOT_CONNECTED,
        "lifecycle_identity": lifecycle.lifecycle_identity,
        "live_order_authority": False,
        "network_authority": False,
        "order_identity": lifecycle.order_identity,
        "final_fill_latency_ms": accepted_order.final_fill_latency_ms,
        "partial_fill_identities": tuple(
            item.fill_identity for item in lifecycle.partial_fills
        ),
        "pretrade_identity": lifecycle.pretrade_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "submitted_at_ms": submitted_at_ms,
        "schema_version": WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        "venue_rule_snapshot_identity": venue_rules.snapshot_identity,
    }
    return WC6LocalSandboxAcceptedOrder(
        adapter_order_identity=canonical_sha256(payload),
        schema_version=WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        adapter_version=WC6_LOCAL_SANDBOX_ADAPTER_VERSION,
        client_order_key=client_order_key,
        lifecycle_identity=lifecycle.lifecycle_identity,
        order_identity=lifecycle.order_identity,
        acknowledgement_identity=(
            lifecycle.acknowledgement.acknowledgement_identity
        ),
        pretrade_identity=lifecycle.pretrade_identity,
        execution_snapshot_identity=lifecycle.execution_snapshot_identity,
        venue_rule_snapshot_identity=venue_rules.snapshot_identity,
        authority_event_identity=authority.authority_event_identity,
        submitted_at_ms=submitted_at_ms,
        acknowledgement_latency_ms=accepted_order.acknowledgement_latency_ms,
        final_fill_latency_ms=accepted_order.final_fill_latency_ms,
        canonical_fill_identity=lifecycle.canonical_fill_identity,
        canonical_mutation_identity=lifecycle.canonical_mutation_identity,
        partial_fill_identities=tuple(
            item.fill_identity for item in lifecycle.partial_fills
        ),
        adapter_status=WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK,
        external_testnet_status=WC6ExternalTestnetStatus.NOT_CONNECTED,
        network_authority=False,
        credential_authority=False,
        live_order_authority=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def build_local_sandbox_rejection(
    *,
    paper_ledger: PaperFundLedger,
    bound_pretrade: PaperVenueBoundPretrade,
    venue_rules: FrozenBinanceSpotVenueRules,
    authority: PaperWriteAuthorityEvent,
    submitted_at_ms: int,
    acknowledgement_latency_ms: int,
) -> WC6LocalSandboxRejection:
    """Build deterministic venue-policy or kill-switch rejection evidence."""

    _validate_common(
        paper_ledger=paper_ledger,
        bound_pretrade=bound_pretrade,
        venue_rules=venue_rules,
        authority=authority,
    )
    if submitted_at_ms < 0 or acknowledgement_latency_ms <= 0:
        raise WC6LocalSandboxError("sandbox rejection timing is invalid")

    pretrade = bound_pretrade.pretrade
    if not authority.enabled:
        reason = WC6SandboxRejectReason.KILL_SWITCH_DISABLED
        detail = "current virtual-paper write authority is disabled"
    elif pretrade.status is PaperPretradeStatus.REJECTED:
        reason = WC6SandboxRejectReason.VENUE_POLICY_REJECTED
        detail = pretrade.reason_code.value
    else:
        raise WC6LocalSandboxError(
            "sandbox rejection requires rejected pretrade or disabled authority"
        )

    client_order_key = _client_order_key(
        pretrade_identity=pretrade.pretrade_identity,
        execution_snapshot_identity=bound_pretrade.execution_snapshot.snapshot_identity,
        venue_rule_snapshot_identity=venue_rules.snapshot_identity,
    )
    payload = {
        "acknowledged_at_ms": submitted_at_ms + acknowledgement_latency_ms,
        "adapter_status": WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK,
        "adapter_version": WC6_LOCAL_SANDBOX_ADAPTER_VERSION,
        "authority_event_identity": authority.authority_event_identity,
        "client_order_key": client_order_key,
        "credential_authority": False,
        "detail": detail,
        "execution_snapshot_identity": (
            bound_pretrade.execution_snapshot.snapshot_identity
        ),
        "external_testnet_status": WC6ExternalTestnetStatus.NOT_CONNECTED,
        "fill_count": 0,
        "live_order_authority": False,
        "network_authority": False,
        "pretrade_identity": pretrade.pretrade_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reason": reason,
        "schema_version": WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        "submitted_at_ms": submitted_at_ms,
        "venue_rule_snapshot_identity": venue_rules.snapshot_identity,
    }
    return WC6LocalSandboxRejection(
        rejection_identity=canonical_sha256(payload),
        schema_version=WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        adapter_version=WC6_LOCAL_SANDBOX_ADAPTER_VERSION,
        client_order_key=client_order_key,
        pretrade_identity=pretrade.pretrade_identity,
        execution_snapshot_identity=(
            bound_pretrade.execution_snapshot.snapshot_identity
        ),
        venue_rule_snapshot_identity=venue_rules.snapshot_identity,
        authority_event_identity=authority.authority_event_identity,
        submitted_at_ms=submitted_at_ms,
        acknowledged_at_ms=submitted_at_ms + acknowledgement_latency_ms,
        reason=reason,
        detail=detail,
        adapter_status=WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK,
        external_testnet_status=WC6ExternalTestnetStatus.NOT_CONNECTED,
        fill_count=0,
        network_authority=False,
        credential_authority=False,
        live_order_authority=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def build_wc6_local_sandbox_dossier(
    *,
    accepted_order: WC6LocalSandboxAcceptedOrder,
    lifecycle: WC6ShadowOrderLifecycle,
    venue_rejection: WC6LocalSandboxRejection,
    kill_switch_rejection: WC6LocalSandboxRejection,
    first_journal_disposition: WC6SandboxJournalDisposition,
    restart_retry_disposition: WC6SandboxJournalDisposition,
) -> WC6LocalSandboxDossier:
    """Bind one complete local-sandbox execution dossier."""

    if accepted_order.lifecycle_identity != lifecycle.lifecycle_identity:
        raise WC6LocalSandboxError("sandbox accepted-order/lifecycle mismatch")
    if accepted_order.client_order_key != kill_switch_rejection.client_order_key:
        raise WC6LocalSandboxError(
            "kill switch must reject the same deterministic client-order key"
        )
    if (
        venue_rejection.reason
        is not WC6SandboxRejectReason.VENUE_POLICY_REJECTED
    ):
        raise WC6LocalSandboxError("WC6 dossier lacks venue-policy rejection")
    if (
        kill_switch_rejection.reason
        is not WC6SandboxRejectReason.KILL_SWITCH_DISABLED
    ):
        raise WC6LocalSandboxError("WC6 dossier lacks kill-switch rejection")
    if first_journal_disposition is not WC6SandboxJournalDisposition.INSERTED:
        raise WC6LocalSandboxError("WC6 first journal append must insert")
    if restart_retry_disposition is not WC6SandboxJournalDisposition.UNCHANGED:
        raise WC6LocalSandboxError("WC6 restart retry must be unchanged")
    if len(lifecycle.partial_fills) < 2:
        raise WC6LocalSandboxError("WC6 sandbox dossier requires partial fills")
    if not (
        lifecycle.quantity_reconciled
        and lifecycle.notional_reconciled
        and lifecycle.accounting_shadow_reconciled
    ):
        raise WC6LocalSandboxError("WC6 lifecycle reconciliation is incomplete")

    payload = {
        "accepted_adapter_order_identity": (
            accepted_order.adapter_order_identity
        ),
        "accepted_lifecycle_identity": lifecycle.lifecycle_identity,
        "acknowledgement_latency_ms": acknowledgement_latency_ms,
        "accounting_shadow_reconciled": lifecycle.accounting_shadow_reconciled,
        "adapter_status": WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK,
        "adapter_version": WC6_LOCAL_SANDBOX_ADAPTER_VERSION,
        "canonical_fill_identity": lifecycle.canonical_fill_identity,
        "canonical_mutation_identity": lifecycle.canonical_mutation_identity,
        "credential_authority": False,
        "duplicate_prevention_proven": True,
        "external_testnet_status": WC6ExternalTestnetStatus.NOT_CONNECTED,
        "final_fill_latency_ms": final_fill_latency_ms,
        "first_journal_disposition": first_journal_disposition,
        "kill_switch_proven": True,
        "kill_switch_rejection_identity": (
            kill_switch_rejection.rejection_identity
        ),
        "live_order_authority": False,
        "network_authority": False,
        "notional_reconciled": lifecycle.notional_reconciled,
        "partial_fill_count": len(lifecycle.partial_fills),
        "partial_fill_support": lifecycle.partial_fill_support,
        "production_authority": False,
        "quantity_reconciled": lifecycle.quantity_reconciled,
        "real_capital": REAL_CAPITAL,
        "restart_idempotence_proven": True,
        "restart_retry_disposition": restart_retry_disposition,
        "schema_version": WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        "venue_rejection_identity": venue_rejection.rejection_identity,
        "venue_rejection_proven": True,
    }
    return WC6LocalSandboxDossier(
        dossier_identity=canonical_sha256(payload),
        schema_version=WC6_LOCAL_SANDBOX_SCHEMA_VERSION,
        adapter_version=WC6_LOCAL_SANDBOX_ADAPTER_VERSION,
        accepted_adapter_order_identity=accepted_order.adapter_order_identity,
        accepted_lifecycle_identity=lifecycle.lifecycle_identity,
        venue_rejection_identity=venue_rejection.rejection_identity,
        kill_switch_rejection_identity=kill_switch_rejection.rejection_identity,
        canonical_fill_identity=lifecycle.canonical_fill_identity,
        canonical_mutation_identity=lifecycle.canonical_mutation_identity,
        first_journal_disposition=first_journal_disposition,
        restart_retry_disposition=restart_retry_disposition,
        partial_fill_count=len(lifecycle.partial_fills),
        acknowledgement_latency_ms=acknowledgement_latency_ms,
        final_fill_latency_ms=final_fill_latency_ms,
        quantity_reconciled=lifecycle.quantity_reconciled,
        notional_reconciled=lifecycle.notional_reconciled,
        accounting_shadow_reconciled=lifecycle.accounting_shadow_reconciled,
        venue_rejection_proven=True,
        kill_switch_proven=True,
        duplicate_prevention_proven=True,
        restart_idempotence_proven=True,
        adapter_status=WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK,
        external_testnet_status=WC6ExternalTestnetStatus.NOT_CONNECTED,
        partial_fill_support=lifecycle.partial_fill_support,
        network_authority=False,
        credential_authority=False,
        live_order_authority=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def _validate_common(
    *,
    paper_ledger: PaperFundLedger,
    bound_pretrade: PaperVenueBoundPretrade,
    venue_rules: FrozenBinanceSpotVenueRules,
    authority: PaperWriteAuthorityEvent,
) -> None:
    if (
        bound_pretrade.real_capital != REAL_CAPITAL
        or venue_rules.real_capital != REAL_CAPITAL
        or authority.real_capital != REAL_CAPITAL
    ):
        raise WC6LocalSandboxError("REAL_CAPITAL must remain 0")
    current = load_current_paper_write_authority(paper_ledger)
    if current != authority:
        raise WC6LocalSandboxError(
            "local sandbox requires exact current paper write authority"
        )
    if bound_pretrade.venue_rule_snapshot_identity != venue_rules.snapshot_identity:
        raise WC6LocalSandboxError("local sandbox venue-rule lineage mismatch")
    marker = f"|rules:{venue_rules.snapshot_identity}|"
    if marker not in bound_pretrade.execution_snapshot.venue_reference:
        raise WC6LocalSandboxError(
            "local sandbox execution snapshot lost venue-rule identity"
        )
    if bound_pretrade.pretrade.symbol is not venue_rules.symbol:
        raise WC6LocalSandboxError("local sandbox venue-rule symbol mismatch")


def _client_order_key(
    *,
    pretrade_identity: str,
    execution_snapshot_identity: str,
    venue_rule_snapshot_identity: str,
) -> str:
    return canonical_sha256(
        {
            "adapter_version": WC6_LOCAL_SANDBOX_ADAPTER_VERSION,
            "execution_snapshot_identity": execution_snapshot_identity,
            "pretrade_identity": pretrade_identity,
            "venue_rule_snapshot_identity": venue_rule_snapshot_identity,
        }
    )


def _accepted_order_payload(
    order: WC6LocalSandboxAcceptedOrder,
) -> dict[str, object]:
    return {
        "acknowledgement_identity": order.acknowledgement_identity,
        "adapter_status": order.adapter_status,
        "adapter_version": order.adapter_version,
        "authority_event_identity": order.authority_event_identity,
        "submitted_at_ms": order.submitted_at_ms,
        "acknowledgement_latency_ms": order.acknowledgement_latency_ms,
        "final_fill_latency_ms": order.final_fill_latency_ms,
        "canonical_fill_identity": order.canonical_fill_identity,
        "canonical_mutation_identity": order.canonical_mutation_identity,
        "client_order_key": order.client_order_key,
        "credential_authority": order.credential_authority,
        "execution_snapshot_identity": order.execution_snapshot_identity,
        "external_testnet_status": order.external_testnet_status,
        "lifecycle_identity": order.lifecycle_identity,
        "live_order_authority": order.live_order_authority,
        "network_authority": order.network_authority,
        "order_identity": order.order_identity,
        "partial_fill_identities": order.partial_fill_identities,
        "pretrade_identity": order.pretrade_identity,
        "production_authority": order.production_authority,
        "real_capital": order.real_capital,
        "schema_version": order.schema_version,
        "venue_rule_snapshot_identity": order.venue_rule_snapshot_identity,
    }


def _rejection_payload(
    rejection: WC6LocalSandboxRejection,
) -> dict[str, object]:
    return {
        "acknowledged_at_ms": rejection.acknowledged_at_ms,
        "adapter_status": rejection.adapter_status,
        "adapter_version": rejection.adapter_version,
        "authority_event_identity": rejection.authority_event_identity,
        "client_order_key": rejection.client_order_key,
        "credential_authority": rejection.credential_authority,
        "detail": rejection.detail,
        "execution_snapshot_identity": rejection.execution_snapshot_identity,
        "external_testnet_status": rejection.external_testnet_status,
        "fill_count": rejection.fill_count,
        "live_order_authority": rejection.live_order_authority,
        "network_authority": rejection.network_authority,
        "pretrade_identity": rejection.pretrade_identity,
        "production_authority": rejection.production_authority,
        "real_capital": rejection.real_capital,
        "reason": rejection.reason,
        "schema_version": rejection.schema_version,
        "submitted_at_ms": rejection.submitted_at_ms,
        "venue_rule_snapshot_identity": rejection.venue_rule_snapshot_identity,
    }


def _dossier_payload(
    dossier: WC6LocalSandboxDossier,
) -> dict[str, object]:
    return {
        "accepted_adapter_order_identity": (
            dossier.accepted_adapter_order_identity
        ),
        "accepted_lifecycle_identity": dossier.accepted_lifecycle_identity,
        "acknowledgement_latency_ms": dossier.acknowledgement_latency_ms,
        "accounting_shadow_reconciled": dossier.accounting_shadow_reconciled,
        "adapter_status": dossier.adapter_status,
        "adapter_version": dossier.adapter_version,
        "canonical_fill_identity": dossier.canonical_fill_identity,
        "canonical_mutation_identity": dossier.canonical_mutation_identity,
        "credential_authority": dossier.credential_authority,
        "duplicate_prevention_proven": dossier.duplicate_prevention_proven,
        "external_testnet_status": dossier.external_testnet_status,
        "final_fill_latency_ms": dossier.final_fill_latency_ms,
        "first_journal_disposition": dossier.first_journal_disposition,
        "kill_switch_proven": dossier.kill_switch_proven,
        "kill_switch_rejection_identity": (
            dossier.kill_switch_rejection_identity
        ),
        "live_order_authority": dossier.live_order_authority,
        "network_authority": dossier.network_authority,
        "notional_reconciled": dossier.notional_reconciled,
        "partial_fill_count": dossier.partial_fill_count,
        "partial_fill_support": dossier.partial_fill_support,
        "production_authority": dossier.production_authority,
        "quantity_reconciled": dossier.quantity_reconciled,
        "real_capital": dossier.real_capital,
        "restart_idempotence_proven": dossier.restart_idempotence_proven,
        "restart_retry_disposition": dossier.restart_retry_disposition,
        "schema_version": dossier.schema_version,
        "venue_rejection_identity": dossier.venue_rejection_identity,
        "venue_rejection_proven": dossier.venue_rejection_proven,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
