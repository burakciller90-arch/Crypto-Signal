"""WC6 lab-only acknowledgement/latency/partial-fill shadow lifecycle.

Canonical paper v1 remains unchanged and continues to declare partial fills
unsupported. This module splits one already-accepted canonical simulated fill
into lab-only shadow fills for deterministic latency/reconciliation tests.
It grants no network, credential, exchange, broker, sandbox, testnet, or
real-order authority. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.activation import PaperProcessedTradeCommit
from crypto_signal.paper.execution import FrozenExecutionSnapshot
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol

WC6_SHADOW_LIFECYCLE_ENGINE_VERSION = "wc6-shadow-order-lifecycle-v1/1"
WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION = "wc6-shadow-order-lifecycle-schema-v1/1"


class WC6ShadowLifecycleError(ValueError):
    """Raised when lab-only order lifecycle evidence cannot reconcile safely."""


class WC6ShadowOrderStatus(StrEnum):
    FILLED = "filled"


class WC6PartialFillSupport(StrEnum):
    LAB_ONLY_CANONICAL_UNSUPPORTED = "lab_only_canonical_unsupported"


@dataclass(frozen=True, slots=True)
class WC6PartialFillScenario:
    scenario_identity: str
    schema_version: str
    engine_version: str
    processed_event_identity: str
    pretrade_identity: str
    execution_snapshot_identity: str
    canonical_fill_identity: str
    ack_latency_ms: int
    fill_latency_ms: tuple[int, ...]
    partial_quantities: tuple[Decimal, ...]
    partial_fill_support: WC6PartialFillSupport
    lab_only: bool = True
    network_authority: bool = False
    credential_authority: bool = False
    live_order_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.scenario_identity, "WC6 scenario identity"),
            (self.processed_event_identity, "WC6 processed-event identity"),
            (self.pretrade_identity, "WC6 pretrade identity"),
            (
                self.execution_snapshot_identity,
                "WC6 execution snapshot identity",
            ),
            (self.canonical_fill_identity, "WC6 canonical fill identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 partial-fill scenario schema")
        if self.engine_version != WC6_SHADOW_LIFECYCLE_ENGINE_VERSION:
            raise ValueError("unsupported WC6 partial-fill scenario engine")
        if self.ack_latency_ms < 0:
            raise ValueError("WC6 acknowledgement latency cannot be negative")
        if len(self.fill_latency_ms) < 2:
            raise ValueError("WC6 partial-fill scenario requires at least two fills")
        if len(self.partial_quantities) != len(self.fill_latency_ms):
            raise ValueError("WC6 partial quantity/latency cardinality mismatch")
        if any(value <= 0 for value in self.partial_quantities):
            raise ValueError("WC6 partial quantities must be positive")
        if any(value < self.ack_latency_ms for value in self.fill_latency_ms):
            raise ValueError("WC6 fill cannot predate acknowledgement")
        if any(
            current <= previous
            for previous, current in zip(
                self.fill_latency_ms,
                self.fill_latency_ms[1:],
                strict=False,
            )
        ):
            raise ValueError("WC6 fill latencies must be strictly increasing")
        if self.partial_fill_support is not (
            WC6PartialFillSupport.LAB_ONLY_CANONICAL_UNSUPPORTED
        ):
            raise ValueError("WC6 v1 partial fills are lab-only")
        if not self.lab_only:
            raise ValueError("WC6 partial-fill scenario must remain lab-only")
        if (
            self.network_authority
            or self.credential_authority
            or self.live_order_authority
        ):
            raise ValueError("WC6 shadow scenario grants no external/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.scenario_identity != canonical_sha256(_scenario_payload(self)):
            raise ValueError("WC6 partial-fill scenario identity mismatch")


@dataclass(frozen=True, slots=True)
class WC6ShadowOrderAcknowledgement:
    acknowledgement_identity: str
    schema_version: str
    engine_version: str
    scenario_identity: str
    order_identity: str
    acknowledged_at_ms: int
    simulated_venue_reference: str
    lab_only: bool = True
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.acknowledgement_identity, "WC6 acknowledgement identity"),
            (self.scenario_identity, "WC6 scenario identity"),
            (self.order_identity, "WC6 order identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 acknowledgement schema")
        if self.engine_version != WC6_SHADOW_LIFECYCLE_ENGINE_VERSION:
            raise ValueError("unsupported WC6 acknowledgement engine")
        if self.acknowledged_at_ms < 0:
            raise ValueError("WC6 acknowledgement time cannot be negative")
        if not self.simulated_venue_reference.startswith("wc6_lab_order:"):
            raise ValueError("WC6 acknowledgement requires lab-only venue reference")
        if not self.lab_only or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC6 acknowledgement must remain lab-only REAL_CAPITAL=0")
        if self.acknowledgement_identity != canonical_sha256(
            _ack_payload(self)
        ):
            raise ValueError("WC6 acknowledgement identity mismatch")


@dataclass(frozen=True, slots=True)
class WC6ShadowPartialFill:
    fill_identity: str
    schema_version: str
    engine_version: str
    scenario_identity: str
    order_identity: str
    acknowledgement_identity: str
    canonical_fill_identity: str
    sequence: int
    filled_at_ms: int
    action: PaperAction
    symbol: PaperSymbol
    quantity: Decimal
    simulated_fill_price: Decimal
    cumulative_quantity: Decimal
    lab_only: bool = True
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.fill_identity, "WC6 shadow fill identity"),
            (self.scenario_identity, "WC6 scenario identity"),
            (self.order_identity, "WC6 order identity"),
            (self.acknowledgement_identity, "WC6 acknowledgement identity"),
            (self.canonical_fill_identity, "WC6 canonical fill identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 shadow-fill schema")
        if self.engine_version != WC6_SHADOW_LIFECYCLE_ENGINE_VERSION:
            raise ValueError("unsupported WC6 shadow-fill engine")
        if self.sequence <= 0 or self.filled_at_ms < 0:
            raise ValueError("WC6 shadow fill sequence/time is invalid")
        if self.action is PaperAction.HOLD_CASH:
            raise ValueError("WC6 shadow fill cannot represent HOLD_CASH")
        if self.quantity <= 0 or self.simulated_fill_price <= 0:
            raise ValueError("WC6 shadow fill quantity/price must be positive")
        if self.cumulative_quantity < self.quantity:
            raise ValueError("WC6 cumulative quantity cannot be below fill quantity")
        if not self.lab_only or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC6 shadow fill must remain lab-only REAL_CAPITAL=0")
        if self.fill_identity != canonical_sha256(_partial_fill_payload(self)):
            raise ValueError("WC6 shadow fill identity mismatch")


@dataclass(frozen=True, slots=True)
class WC6ShadowOrderLifecycle:
    lifecycle_identity: str
    schema_version: str
    engine_version: str
    scenario_identity: str
    order_identity: str
    processed_event_identity: str
    pretrade_identity: str
    execution_snapshot_identity: str
    decision_identity: str
    canonical_fill_identity: str
    canonical_mutation_identity: str
    acknowledgement: WC6ShadowOrderAcknowledgement
    partial_fills: tuple[WC6ShadowPartialFill, ...]
    final_status: WC6ShadowOrderStatus
    requested_quantity: Decimal
    filled_quantity: Decimal
    canonical_fill_price: Decimal
    shadow_notional_usdt: Decimal
    canonical_notional_usdt: Decimal
    quantity_reconciled: bool
    notional_reconciled: bool
    accounting_shadow_reconciled: bool
    partial_fill_support: WC6PartialFillSupport
    canonical_partial_fills_supported: bool = False
    sandbox_adapter_implemented: bool = False
    network_authority: bool = False
    credential_authority: bool = False
    live_order_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.lifecycle_identity, "WC6 lifecycle identity"),
            (self.scenario_identity, "WC6 scenario identity"),
            (self.order_identity, "WC6 order identity"),
            (self.processed_event_identity, "WC6 processed-event identity"),
            (self.pretrade_identity, "WC6 pretrade identity"),
            (
                self.execution_snapshot_identity,
                "WC6 execution snapshot identity",
            ),
            (self.decision_identity, "WC6 decision identity"),
            (self.canonical_fill_identity, "WC6 canonical fill identity"),
            (self.canonical_mutation_identity, "WC6 canonical mutation identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 lifecycle schema")
        if self.engine_version != WC6_SHADOW_LIFECYCLE_ENGINE_VERSION:
            raise ValueError("unsupported WC6 lifecycle engine")
        if self.final_status is not WC6ShadowOrderStatus.FILLED:
            raise ValueError("WC6 v1 lifecycle must end FILLED")
        if len(self.partial_fills) < 2:
            raise ValueError("WC6 lifecycle requires at least two shadow fills")
        if self.acknowledgement.scenario_identity != self.scenario_identity:
            raise ValueError("WC6 acknowledgement scenario mismatch")
        if self.acknowledgement.order_identity != self.order_identity:
            raise ValueError("WC6 acknowledgement order mismatch")
        if any(item.scenario_identity != self.scenario_identity for item in self.partial_fills):
            raise ValueError("WC6 partial-fill scenario mismatch")
        if any(item.order_identity != self.order_identity for item in self.partial_fills):
            raise ValueError("WC6 partial-fill order mismatch")
        if tuple(item.sequence for item in self.partial_fills) != tuple(
            range(1, len(self.partial_fills) + 1)
        ):
            raise ValueError("WC6 partial-fill sequence is discontinuous")
        if self.requested_quantity <= 0 or self.filled_quantity <= 0:
            raise ValueError("WC6 lifecycle quantities must be positive")
        if self.canonical_fill_price <= 0:
            raise ValueError("WC6 canonical fill price must be positive")
        if self.shadow_notional_usdt < 0 or self.canonical_notional_usdt < 0:
            raise ValueError("WC6 lifecycle notionals cannot be negative")
        if not (
            self.quantity_reconciled
            and self.notional_reconciled
            and self.accounting_shadow_reconciled
        ):
            raise ValueError("WC6 lifecycle must reconcile to canonical paper accounting")
        if self.filled_quantity != self.requested_quantity:
            raise ValueError("WC6 lifecycle final quantity mismatch")
        if self.shadow_notional_usdt != self.canonical_notional_usdt:
            raise ValueError("WC6 lifecycle notional mismatch")
        if self.partial_fill_support is not (
            WC6PartialFillSupport.LAB_ONLY_CANONICAL_UNSUPPORTED
        ):
            raise ValueError("WC6 lifecycle partial fills must remain lab-only")
        if self.canonical_partial_fills_supported:
            raise ValueError("canonical paper v1 partial fills remain unsupported")
        if self.sandbox_adapter_implemented:
            raise ValueError("WC6 v1 does not implement sandbox/testnet adapter")
        if (
            self.network_authority
            or self.credential_authority
            or self.live_order_authority
            or self.production_authority
        ):
            raise ValueError("WC6 shadow lifecycle grants no external/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.lifecycle_identity != canonical_sha256(_lifecycle_payload(self)):
            raise ValueError("WC6 shadow lifecycle identity mismatch")


def build_wc6_partial_fill_scenario(
    *,
    commit: PaperProcessedTradeCommit,
    execution_snapshot: FrozenExecutionSnapshot,
    ack_latency_ms: int,
    fill_latency_ms: tuple[int, ...],
    partial_quantities: tuple[Decimal, ...],
) -> WC6PartialFillScenario:
    """Freeze one lab-only partial-fill timing scenario for an accepted trade."""

    bundle = commit.pipeline.bundle
    fill = bundle.fill
    if fill is None or bundle.mutation is None:
        raise WC6ShadowLifecycleError("WC6 lifecycle requires committed trade fill/mutation")
    if commit.pipeline.execution_snapshot_identity != execution_snapshot.snapshot_identity:
        raise WC6ShadowLifecycleError("WC6 execution snapshot lineage mismatch")
    if execution_snapshot.partial_fills_supported is not False:
        raise WC6ShadowLifecycleError(
            "canonical paper partial fills must remain unsupported"
        )
    if execution_snapshot.symbol is not fill.symbol:
        raise WC6ShadowLifecycleError("WC6 execution snapshot symbol mismatch")
    if len(partial_quantities) < 2:
        raise WC6ShadowLifecycleError("WC6 scenario requires at least two partial fills")
    if sum(partial_quantities, Decimal(0)) != fill.quantity:
        raise WC6ShadowLifecycleError(
            "WC6 partial quantities must sum to canonical fill quantity"
        )
    for quantity in partial_quantities:
        if quantity <= 0:
            raise WC6ShadowLifecycleError("WC6 partial quantities must be positive")
        steps = quantity / execution_snapshot.quantity_step
        if steps != steps.to_integral_value():
            raise WC6ShadowLifecycleError(
                "WC6 partial quantity must align to frozen quantity step"
            )

    payload = {
        "ack_latency_ms": ack_latency_ms,
        "canonical_fill_identity": fill.record_identity,
        "credential_authority": False,
        "engine_version": WC6_SHADOW_LIFECYCLE_ENGINE_VERSION,
        "execution_snapshot_identity": execution_snapshot.snapshot_identity,
        "fill_latency_ms": fill_latency_ms,
        "lab_only": True,
        "live_order_authority": False,
        "network_authority": False,
        "partial_fill_support": (
            WC6PartialFillSupport.LAB_ONLY_CANONICAL_UNSUPPORTED
        ),
        "partial_quantities": partial_quantities,
        "pretrade_identity": commit.pipeline.pretrade_identity,
        "processed_event_identity": commit.receipt.event_identity,
        "real_capital": REAL_CAPITAL,
        "schema_version": WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION,
    }
    return WC6PartialFillScenario(
        scenario_identity=canonical_sha256(payload),
        schema_version=WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION,
        engine_version=WC6_SHADOW_LIFECYCLE_ENGINE_VERSION,
        processed_event_identity=commit.receipt.event_identity,
        pretrade_identity=commit.pipeline.pretrade_identity,
        execution_snapshot_identity=execution_snapshot.snapshot_identity,
        canonical_fill_identity=fill.record_identity,
        ack_latency_ms=ack_latency_ms,
        fill_latency_ms=fill_latency_ms,
        partial_quantities=partial_quantities,
        partial_fill_support=(
            WC6PartialFillSupport.LAB_ONLY_CANONICAL_UNSUPPORTED
        ),
    )


def simulate_wc6_shadow_order_lifecycle(
    *,
    commit: PaperProcessedTradeCommit,
    execution_snapshot: FrozenExecutionSnapshot,
    scenario: WC6PartialFillScenario,
) -> WC6ShadowOrderLifecycle:
    """Split one canonical fill into deterministic lab-only shadow fills."""

    bundle = commit.pipeline.bundle
    decision = bundle.decision
    fill = bundle.fill
    mutation = bundle.mutation
    if fill is None or mutation is None:
        raise WC6ShadowLifecycleError("WC6 lifecycle requires trade fill/mutation")
    if scenario.processed_event_identity != commit.receipt.event_identity:
        raise WC6ShadowLifecycleError("WC6 scenario processed-event mismatch")
    if scenario.pretrade_identity != commit.pipeline.pretrade_identity:
        raise WC6ShadowLifecycleError("WC6 scenario pretrade mismatch")
    if scenario.execution_snapshot_identity != execution_snapshot.snapshot_identity:
        raise WC6ShadowLifecycleError("WC6 scenario snapshot mismatch")
    if scenario.canonical_fill_identity != fill.record_identity:
        raise WC6ShadowLifecycleError("WC6 scenario canonical fill mismatch")
    if mutation.source_identity != fill.record_identity:
        raise WC6ShadowLifecycleError("WC6 paper mutation is not sourced from fill")
    if decision.quantity != fill.quantity:
        raise WC6ShadowLifecycleError("WC6 decision/fill quantity mismatch")
    if decision.quantity is None or decision.symbol is None:
        raise WC6ShadowLifecycleError("WC6 trade decision lost quantity/symbol")

    order_payload = {
        "action": decision.action,
        "canonical_fill_identity": fill.record_identity,
        "decision_identity": decision.record_identity,
        "execution_snapshot_identity": execution_snapshot.snapshot_identity,
        "pretrade_identity": commit.pipeline.pretrade_identity,
        "processed_event_identity": commit.receipt.event_identity,
        "reference_price": decision.reference_price,
        "requested_quantity": decision.quantity,
        "submitted_at_ms": decision.decided_at_ms,
        "symbol": decision.symbol,
    }
    order_identity = canonical_sha256(order_payload)
    ack_at = decision.decided_at_ms + scenario.ack_latency_ms
    ack_payload = {
        "acknowledged_at_ms": ack_at,
        "engine_version": WC6_SHADOW_LIFECYCLE_ENGINE_VERSION,
        "lab_only": True,
        "order_identity": order_identity,
        "real_capital": REAL_CAPITAL,
        "scenario_identity": scenario.scenario_identity,
        "schema_version": WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION,
        "simulated_venue_reference": f"wc6_lab_order:{order_identity}",
    }
    acknowledgement = WC6ShadowOrderAcknowledgement(
        acknowledgement_identity=canonical_sha256(ack_payload),
        schema_version=WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION,
        engine_version=WC6_SHADOW_LIFECYCLE_ENGINE_VERSION,
        scenario_identity=scenario.scenario_identity,
        order_identity=order_identity,
        acknowledged_at_ms=ack_at,
        simulated_venue_reference=f"wc6_lab_order:{order_identity}",
    )

    partial_fills: list[WC6ShadowPartialFill] = []
    cumulative = Decimal(0)
    for index, (latency_ms, quantity) in enumerate(
        zip(
            scenario.fill_latency_ms,
            scenario.partial_quantities,
            strict=True,
        ),
        start=1,
    ):
        cumulative += quantity
        partial_payload = {
            "acknowledgement_identity": acknowledgement.acknowledgement_identity,
            "action": fill.action,
            "canonical_fill_identity": fill.record_identity,
            "cumulative_quantity": cumulative,
            "engine_version": WC6_SHADOW_LIFECYCLE_ENGINE_VERSION,
            "filled_at_ms": decision.decided_at_ms + latency_ms,
            "lab_only": True,
            "order_identity": order_identity,
            "quantity": quantity,
            "real_capital": REAL_CAPITAL,
            "scenario_identity": scenario.scenario_identity,
            "schema_version": WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION,
            "sequence": index,
            "simulated_fill_price": fill.simulated_fill_price,
            "symbol": fill.symbol,
        }
        partial_fills.append(
            WC6ShadowPartialFill(
                fill_identity=canonical_sha256(partial_payload),
                schema_version=WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION,
                engine_version=WC6_SHADOW_LIFECYCLE_ENGINE_VERSION,
                scenario_identity=scenario.scenario_identity,
                order_identity=order_identity,
                acknowledgement_identity=(
                    acknowledgement.acknowledgement_identity
                ),
                canonical_fill_identity=fill.record_identity,
                sequence=index,
                filled_at_ms=decision.decided_at_ms + latency_ms,
                action=fill.action,
                symbol=fill.symbol,
                quantity=quantity,
                simulated_fill_price=fill.simulated_fill_price,
                cumulative_quantity=cumulative,
            )
        )

    shadow_notional = sum(
        (
            item.quantity * item.simulated_fill_price
            for item in partial_fills
        ),
        Decimal(0),
    )
    canonical_notional = fill.quantity * fill.simulated_fill_price
    filled_quantity = sum((item.quantity for item in partial_fills), Decimal(0))
    quantity_reconciled = filled_quantity == fill.quantity == decision.quantity
    notional_reconciled = shadow_notional == canonical_notional
    accounting_reconciled = (
        quantity_reconciled
        and notional_reconciled
        and mutation.source_identity == fill.record_identity
        and commit.receipt.record_identities
        == (
            decision.record_identity,
            fill.record_identity,
            mutation.record_identity,
        )
    )
    lifecycle_payload = {
        "accounting_shadow_reconciled": accounting_reconciled,
        "acknowledgement": acknowledgement,
        "canonical_fill_identity": fill.record_identity,
        "canonical_fill_price": fill.simulated_fill_price,
        "canonical_mutation_identity": mutation.record_identity,
        "canonical_notional_usdt": canonical_notional,
        "canonical_partial_fills_supported": False,
        "credential_authority": False,
        "decision_identity": decision.record_identity,
        "engine_version": WC6_SHADOW_LIFECYCLE_ENGINE_VERSION,
        "execution_snapshot_identity": execution_snapshot.snapshot_identity,
        "filled_quantity": filled_quantity,
        "final_status": WC6ShadowOrderStatus.FILLED,
        "live_order_authority": False,
        "network_authority": False,
        "notional_reconciled": notional_reconciled,
        "order_identity": order_identity,
        "partial_fill_support": (
            WC6PartialFillSupport.LAB_ONLY_CANONICAL_UNSUPPORTED
        ),
        "partial_fills": tuple(partial_fills),
        "pretrade_identity": commit.pipeline.pretrade_identity,
        "processed_event_identity": commit.receipt.event_identity,
        "production_authority": False,
        "quantity_reconciled": quantity_reconciled,
        "real_capital": REAL_CAPITAL,
        "requested_quantity": decision.quantity,
        "sandbox_adapter_implemented": False,
        "scenario_identity": scenario.scenario_identity,
        "schema_version": WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION,
        "shadow_notional_usdt": shadow_notional,
    }
    return WC6ShadowOrderLifecycle(
        lifecycle_identity=canonical_sha256(lifecycle_payload),
        schema_version=WC6_SHADOW_LIFECYCLE_SCHEMA_VERSION,
        engine_version=WC6_SHADOW_LIFECYCLE_ENGINE_VERSION,
        scenario_identity=scenario.scenario_identity,
        order_identity=order_identity,
        processed_event_identity=commit.receipt.event_identity,
        pretrade_identity=commit.pipeline.pretrade_identity,
        execution_snapshot_identity=execution_snapshot.snapshot_identity,
        decision_identity=decision.record_identity,
        canonical_fill_identity=fill.record_identity,
        canonical_mutation_identity=mutation.record_identity,
        acknowledgement=acknowledgement,
        partial_fills=tuple(partial_fills),
        final_status=WC6ShadowOrderStatus.FILLED,
        requested_quantity=decision.quantity,
        filled_quantity=filled_quantity,
        canonical_fill_price=fill.simulated_fill_price,
        shadow_notional_usdt=shadow_notional,
        canonical_notional_usdt=canonical_notional,
        quantity_reconciled=quantity_reconciled,
        notional_reconciled=notional_reconciled,
        accounting_shadow_reconciled=accounting_reconciled,
        partial_fill_support=(
            WC6PartialFillSupport.LAB_ONLY_CANONICAL_UNSUPPORTED
        ),
    )


def _scenario_payload(scenario: WC6PartialFillScenario) -> dict[str, object]:
    return {
        "ack_latency_ms": scenario.ack_latency_ms,
        "canonical_fill_identity": scenario.canonical_fill_identity,
        "credential_authority": scenario.credential_authority,
        "engine_version": scenario.engine_version,
        "execution_snapshot_identity": scenario.execution_snapshot_identity,
        "fill_latency_ms": scenario.fill_latency_ms,
        "lab_only": scenario.lab_only,
        "live_order_authority": scenario.live_order_authority,
        "network_authority": scenario.network_authority,
        "partial_fill_support": scenario.partial_fill_support,
        "partial_quantities": scenario.partial_quantities,
        "pretrade_identity": scenario.pretrade_identity,
        "processed_event_identity": scenario.processed_event_identity,
        "real_capital": scenario.real_capital,
        "schema_version": scenario.schema_version,
    }


def _ack_payload(
    acknowledgement: WC6ShadowOrderAcknowledgement,
) -> dict[str, object]:
    return {
        "acknowledged_at_ms": acknowledgement.acknowledged_at_ms,
        "engine_version": acknowledgement.engine_version,
        "lab_only": acknowledgement.lab_only,
        "order_identity": acknowledgement.order_identity,
        "real_capital": acknowledgement.real_capital,
        "scenario_identity": acknowledgement.scenario_identity,
        "schema_version": acknowledgement.schema_version,
        "simulated_venue_reference": acknowledgement.simulated_venue_reference,
    }


def _partial_fill_payload(fill: WC6ShadowPartialFill) -> dict[str, object]:
    return {
        "acknowledgement_identity": fill.acknowledgement_identity,
        "action": fill.action,
        "canonical_fill_identity": fill.canonical_fill_identity,
        "cumulative_quantity": fill.cumulative_quantity,
        "engine_version": fill.engine_version,
        "filled_at_ms": fill.filled_at_ms,
        "lab_only": fill.lab_only,
        "order_identity": fill.order_identity,
        "quantity": fill.quantity,
        "real_capital": fill.real_capital,
        "scenario_identity": fill.scenario_identity,
        "schema_version": fill.schema_version,
        "sequence": fill.sequence,
        "simulated_fill_price": fill.simulated_fill_price,
        "symbol": fill.symbol,
    }


def _lifecycle_payload(lifecycle: WC6ShadowOrderLifecycle) -> dict[str, object]:
    return {
        "accounting_shadow_reconciled": lifecycle.accounting_shadow_reconciled,
        "acknowledgement": lifecycle.acknowledgement,
        "canonical_fill_identity": lifecycle.canonical_fill_identity,
        "canonical_fill_price": lifecycle.canonical_fill_price,
        "canonical_mutation_identity": lifecycle.canonical_mutation_identity,
        "canonical_notional_usdt": lifecycle.canonical_notional_usdt,
        "canonical_partial_fills_supported": (
            lifecycle.canonical_partial_fills_supported
        ),
        "credential_authority": lifecycle.credential_authority,
        "decision_identity": lifecycle.decision_identity,
        "engine_version": lifecycle.engine_version,
        "execution_snapshot_identity": lifecycle.execution_snapshot_identity,
        "filled_quantity": lifecycle.filled_quantity,
        "final_status": lifecycle.final_status,
        "live_order_authority": lifecycle.live_order_authority,
        "network_authority": lifecycle.network_authority,
        "notional_reconciled": lifecycle.notional_reconciled,
        "order_identity": lifecycle.order_identity,
        "partial_fill_support": lifecycle.partial_fill_support,
        "partial_fills": lifecycle.partial_fills,
        "pretrade_identity": lifecycle.pretrade_identity,
        "processed_event_identity": lifecycle.processed_event_identity,
        "production_authority": lifecycle.production_authority,
        "quantity_reconciled": lifecycle.quantity_reconciled,
        "real_capital": lifecycle.real_capital,
        "requested_quantity": lifecycle.requested_quantity,
        "sandbox_adapter_implemented": lifecycle.sandbox_adapter_implemented,
        "scenario_identity": lifecycle.scenario_identity,
        "schema_version": lifecycle.schema_version,
        "shadow_notional_usdt": lifecycle.shadow_notional_usdt,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
