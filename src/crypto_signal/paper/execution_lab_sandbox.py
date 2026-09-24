"""Fail-closed WC6 sandbox/testnet adapter boundary.

This module prepares immutable sandbox-order intent from accepted WC6 shadow
execution evidence, but v1 deliberately has no transport implementation,
endpoint, credentials, network call, venue acknowledgement, or venue fill.
REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.execution_lab_lifecycle import (
    WC6ShadowOrderLifecycle,
    WC6ShadowOrderStatus,
)
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol

WC6_SANDBOX_BOUNDARY_ENGINE_VERSION = "wc6-sandbox-boundary-v1/1"
WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION = "wc6-sandbox-boundary-schema-v1/1"


class WC6SandboxBoundaryError(ValueError):
    """Raised when sandbox/testnet dispatch is not explicitly configured."""


class WC6SandboxAdapterStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"


class WC6SandboxEnvironment(StrEnum):
    SANDBOX_TESTNET_ONLY = "sandbox_testnet_only"


class WC6SandboxDispatchStatus(StrEnum):
    BLOCKED_NOT_CONFIGURED = "blocked_not_configured"


class WC6SandboxEvidenceSemantic(StrEnum):
    REQUEST_PREPARED_NO_DISPATCH_NO_VENUE_EVIDENCE = (
        "request_prepared_no_dispatch_no_venue_evidence"
    )


@dataclass(frozen=True, slots=True)
class WC6SandboxAdapterConfig:
    config_identity: str
    schema_version: str
    engine_version: str
    status: WC6SandboxAdapterStatus
    environment: WC6SandboxEnvironment
    endpoint_reference_identity: str | None = None
    credential_reference_identity: str | None = None
    transport_reference_identity: str | None = None
    network_authority: bool = False
    credential_loaded: bool = False
    live_order_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.config_identity, "WC6 sandbox config identity")
        if self.schema_version != WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 sandbox-boundary schema")
        if self.engine_version != WC6_SANDBOX_BOUNDARY_ENGINE_VERSION:
            raise ValueError("unsupported WC6 sandbox-boundary engine")
        if self.status is not WC6SandboxAdapterStatus.NOT_CONFIGURED:
            raise ValueError("WC6 sandbox adapter v1 supports NOT_CONFIGURED only")
        if self.environment is not WC6SandboxEnvironment.SANDBOX_TESTNET_ONLY:
            raise ValueError("WC6 sandbox boundary cannot target live environment")
        if any(
            value is not None
            for value in (
                self.endpoint_reference_identity,
                self.credential_reference_identity,
                self.transport_reference_identity,
            )
        ):
            raise ValueError(
                "NOT_CONFIGURED sandbox boundary cannot bind endpoint/credential/transport"
            )
        if (
            self.network_authority
            or self.credential_loaded
            or self.live_order_authority
            or self.production_authority
        ):
            raise ValueError("WC6 NOT_CONFIGURED boundary grants no authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.config_identity != canonical_sha256(_config_payload(self)):
            raise ValueError("WC6 sandbox config identity mismatch")


@dataclass(frozen=True, slots=True)
class WC6SandboxOrderRequest:
    request_identity: str
    schema_version: str
    engine_version: str
    lifecycle_identity: str
    scenario_identity: str
    processed_event_identity: str
    pretrade_identity: str
    execution_snapshot_identity: str
    canonical_fill_identity: str
    canonical_mutation_identity: str
    order_identity: str
    idempotency_identity: str
    client_order_reference: str
    action: PaperAction
    symbol: PaperSymbol
    quantity: Decimal
    reference_price: Decimal
    lab_shadow_fill_count: int
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.request_identity, "WC6 sandbox request identity"),
            (self.lifecycle_identity, "WC6 lifecycle identity"),
            (self.scenario_identity, "WC6 scenario identity"),
            (self.processed_event_identity, "WC6 processed-event identity"),
            (self.pretrade_identity, "WC6 pretrade identity"),
            (
                self.execution_snapshot_identity,
                "WC6 execution snapshot identity",
            ),
            (self.canonical_fill_identity, "WC6 canonical fill identity"),
            (self.canonical_mutation_identity, "WC6 canonical mutation identity"),
            (self.order_identity, "WC6 order identity"),
            (self.idempotency_identity, "WC6 idempotency identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 sandbox request schema")
        if self.engine_version != WC6_SANDBOX_BOUNDARY_ENGINE_VERSION:
            raise ValueError("unsupported WC6 sandbox request engine")
        if self.action is PaperAction.HOLD_CASH:
            raise ValueError("WC6 sandbox order request cannot represent HOLD_CASH")
        if self.quantity <= 0 or self.reference_price <= 0:
            raise ValueError("WC6 sandbox request quantity/price must be positive")
        if self.lab_shadow_fill_count < 2:
            raise ValueError("WC6 sandbox request requires accepted shadow lifecycle")
        expected_reference = f"wc6-sandbox-{self.idempotency_identity[:24]}"
        if self.client_order_reference != expected_reference:
            raise ValueError("WC6 client-order reference mismatch")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.request_identity != canonical_sha256(_request_payload(self)):
            raise ValueError("WC6 sandbox request identity mismatch")


@dataclass(frozen=True, slots=True)
class WC6SandboxBoundaryEvidence:
    evidence_identity: str
    schema_version: str
    engine_version: str
    semantic: WC6SandboxEvidenceSemantic
    config_identity: str
    request_identity: str
    dispatch_status: WC6SandboxDispatchStatus
    dispatch_attempted: bool
    venue_acknowledgement_identity: str | None
    venue_fill_identities: tuple[str, ...]
    endpoint_bound: bool
    credential_bound: bool
    transport_bound: bool
    network_authority: bool
    live_order_authority: bool
    production_authority: bool
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "WC6 sandbox evidence identity")
        _require_sha256(self.config_identity, "WC6 sandbox config identity")
        _require_sha256(self.request_identity, "WC6 sandbox request identity")
        if self.schema_version != WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION:
            raise ValueError("unsupported WC6 sandbox evidence schema")
        if self.engine_version != WC6_SANDBOX_BOUNDARY_ENGINE_VERSION:
            raise ValueError("unsupported WC6 sandbox evidence engine")
        if self.semantic is not (
            WC6SandboxEvidenceSemantic.REQUEST_PREPARED_NO_DISPATCH_NO_VENUE_EVIDENCE
        ):
            raise ValueError("unsupported WC6 sandbox evidence semantic")
        if self.dispatch_status is not (
            WC6SandboxDispatchStatus.BLOCKED_NOT_CONFIGURED
        ):
            raise ValueError("WC6 v1 sandbox evidence must remain blocked")
        if self.dispatch_attempted:
            raise ValueError("NOT_CONFIGURED boundary cannot attempt dispatch")
        if self.venue_acknowledgement_identity is not None:
            raise ValueError("blocked sandbox boundary cannot claim acknowledgement")
        if self.venue_fill_identities:
            raise ValueError("blocked sandbox boundary cannot claim venue fills")
        if self.endpoint_bound or self.credential_bound or self.transport_bound:
            raise ValueError("blocked sandbox boundary cannot claim configured transport")
        if (
            self.network_authority
            or self.live_order_authority
            or self.production_authority
        ):
            raise ValueError("blocked sandbox boundary grants no authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.evidence_identity != canonical_sha256(_evidence_payload(self)):
            raise ValueError("WC6 sandbox evidence identity mismatch")


def build_wc6_not_configured_sandbox_config() -> WC6SandboxAdapterConfig:
    """Return the only truthful v1 sandbox adapter state."""

    payload = {
        "credential_loaded": False,
        "credential_reference_identity": None,
        "endpoint_reference_identity": None,
        "engine_version": WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
        "environment": WC6SandboxEnvironment.SANDBOX_TESTNET_ONLY,
        "live_order_authority": False,
        "network_authority": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
        "status": WC6SandboxAdapterStatus.NOT_CONFIGURED,
        "transport_reference_identity": None,
    }
    return WC6SandboxAdapterConfig(
        config_identity=canonical_sha256(payload),
        schema_version=WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
        engine_version=WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
        status=WC6SandboxAdapterStatus.NOT_CONFIGURED,
        environment=WC6SandboxEnvironment.SANDBOX_TESTNET_ONLY,
    )


def build_wc6_sandbox_order_request(
    lifecycle: WC6ShadowOrderLifecycle,
) -> WC6SandboxOrderRequest:
    """Project accepted lab execution lineage into an immutable future request."""

    if lifecycle.final_status is not WC6ShadowOrderStatus.FILLED:
        raise WC6SandboxBoundaryError("sandbox request requires completed lab lifecycle")
    if not (
        lifecycle.quantity_reconciled
        and lifecycle.notional_reconciled
        and lifecycle.accounting_shadow_reconciled
    ):
        raise WC6SandboxBoundaryError(
            "sandbox request requires fully reconciled lab evidence"
        )
    if (
        lifecycle.network_authority
        or lifecycle.credential_authority
        or lifecycle.live_order_authority
        or lifecycle.production_authority
    ):
        raise WC6SandboxBoundaryError("sandbox request source has forbidden authority")
    if lifecycle.real_capital != REAL_CAPITAL:
        raise WC6SandboxBoundaryError("REAL_CAPITAL must remain 0")
    if not lifecycle.partial_fills:
        raise WC6SandboxBoundaryError("sandbox request requires shadow fill evidence")

    first_fill = lifecycle.partial_fills[0]
    action = first_fill.action
    symbol = first_fill.symbol
    quantity = lifecycle.requested_quantity
    reference_price = lifecycle.canonical_fill_price
    idempotency_identity = canonical_sha256(
        {
            "execution_snapshot_identity": lifecycle.execution_snapshot_identity,
            "lifecycle_identity": lifecycle.lifecycle_identity,
            "order_identity": lifecycle.order_identity,
            "pretrade_identity": lifecycle.pretrade_identity,
            "processed_event_identity": lifecycle.processed_event_identity,
        }
    )
    client_order_reference = f"wc6-sandbox-{idempotency_identity[:24]}"
    payload = {
        "action": action,
        "canonical_fill_identity": lifecycle.canonical_fill_identity,
        "canonical_mutation_identity": lifecycle.canonical_mutation_identity,
        "client_order_reference": client_order_reference,
        "engine_version": WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
        "execution_snapshot_identity": lifecycle.execution_snapshot_identity,
        "idempotency_identity": idempotency_identity,
        "lab_shadow_fill_count": len(lifecycle.partial_fills),
        "lifecycle_identity": lifecycle.lifecycle_identity,
        "order_identity": lifecycle.order_identity,
        "pretrade_identity": lifecycle.pretrade_identity,
        "processed_event_identity": lifecycle.processed_event_identity,
        "quantity": quantity,
        "real_capital": REAL_CAPITAL,
        "reference_price": reference_price,
        "scenario_identity": lifecycle.scenario_identity,
        "schema_version": WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
        "symbol": symbol,
    }
    return WC6SandboxOrderRequest(
        request_identity=canonical_sha256(payload),
        schema_version=WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
        engine_version=WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
        lifecycle_identity=lifecycle.lifecycle_identity,
        scenario_identity=lifecycle.scenario_identity,
        processed_event_identity=lifecycle.processed_event_identity,
        pretrade_identity=lifecycle.pretrade_identity,
        execution_snapshot_identity=lifecycle.execution_snapshot_identity,
        canonical_fill_identity=lifecycle.canonical_fill_identity,
        canonical_mutation_identity=lifecycle.canonical_mutation_identity,
        order_identity=lifecycle.order_identity,
        idempotency_identity=idempotency_identity,
        client_order_reference=client_order_reference,
        action=action,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        lab_shadow_fill_count=len(lifecycle.partial_fills),
    )


def evaluate_wc6_sandbox_boundary(
    *,
    config: WC6SandboxAdapterConfig,
    request: WC6SandboxOrderRequest,
) -> WC6SandboxBoundaryEvidence:
    """Record explicit missing sandbox configuration without dispatching."""

    if config.status is not WC6SandboxAdapterStatus.NOT_CONFIGURED:
        raise WC6SandboxBoundaryError("unsupported sandbox adapter state")
    if config.real_capital != REAL_CAPITAL or request.real_capital != REAL_CAPITAL:
        raise WC6SandboxBoundaryError("REAL_CAPITAL must remain 0")

    payload = {
        "config_identity": config.config_identity,
        "credential_bound": False,
        "dispatch_attempted": False,
        "dispatch_status": WC6SandboxDispatchStatus.BLOCKED_NOT_CONFIGURED,
        "endpoint_bound": False,
        "engine_version": WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
        "live_order_authority": False,
        "network_authority": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "request_identity": request.request_identity,
        "schema_version": WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
        "semantic": (
            WC6SandboxEvidenceSemantic.REQUEST_PREPARED_NO_DISPATCH_NO_VENUE_EVIDENCE
        ),
        "transport_bound": False,
        "venue_acknowledgement_identity": None,
        "venue_fill_identities": (),
    }
    return WC6SandboxBoundaryEvidence(
        evidence_identity=canonical_sha256(payload),
        schema_version=WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
        engine_version=WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
        semantic=(
            WC6SandboxEvidenceSemantic.REQUEST_PREPARED_NO_DISPATCH_NO_VENUE_EVIDENCE
        ),
        config_identity=config.config_identity,
        request_identity=request.request_identity,
        dispatch_status=WC6SandboxDispatchStatus.BLOCKED_NOT_CONFIGURED,
        dispatch_attempted=False,
        venue_acknowledgement_identity=None,
        venue_fill_identities=(),
        endpoint_bound=False,
        credential_bound=False,
        transport_bound=False,
        network_authority=False,
        live_order_authority=False,
        production_authority=False,
    )


def require_wc6_sandbox_dispatch_ready(
    config: WC6SandboxAdapterConfig,
) -> None:
    """Fail closed until a future reviewed sandbox transport exists."""

    if config.status is WC6SandboxAdapterStatus.NOT_CONFIGURED:
        raise WC6SandboxBoundaryError(
            "WC6_SANDBOX_NOT_CONFIGURED: no endpoint, credential reference, "
            "transport, or venue execution evidence"
        )
    raise WC6SandboxBoundaryError("unsupported sandbox adapter state")


def _config_payload(config: WC6SandboxAdapterConfig) -> dict[str, object]:
    return {
        "credential_loaded": config.credential_loaded,
        "credential_reference_identity": config.credential_reference_identity,
        "endpoint_reference_identity": config.endpoint_reference_identity,
        "engine_version": config.engine_version,
        "environment": config.environment,
        "live_order_authority": config.live_order_authority,
        "network_authority": config.network_authority,
        "production_authority": config.production_authority,
        "real_capital": config.real_capital,
        "schema_version": config.schema_version,
        "status": config.status,
        "transport_reference_identity": config.transport_reference_identity,
    }


def _request_payload(request: WC6SandboxOrderRequest) -> dict[str, object]:
    return {
        "action": request.action,
        "canonical_fill_identity": request.canonical_fill_identity,
        "canonical_mutation_identity": request.canonical_mutation_identity,
        "client_order_reference": request.client_order_reference,
        "engine_version": request.engine_version,
        "execution_snapshot_identity": request.execution_snapshot_identity,
        "idempotency_identity": request.idempotency_identity,
        "lab_shadow_fill_count": request.lab_shadow_fill_count,
        "lifecycle_identity": request.lifecycle_identity,
        "order_identity": request.order_identity,
        "pretrade_identity": request.pretrade_identity,
        "processed_event_identity": request.processed_event_identity,
        "quantity": request.quantity,
        "real_capital": request.real_capital,
        "reference_price": request.reference_price,
        "scenario_identity": request.scenario_identity,
        "schema_version": request.schema_version,
        "symbol": request.symbol,
    }


def _evidence_payload(
    evidence: WC6SandboxBoundaryEvidence,
) -> dict[str, object]:
    return {
        "config_identity": evidence.config_identity,
        "credential_bound": evidence.credential_bound,
        "dispatch_attempted": evidence.dispatch_attempted,
        "dispatch_status": evidence.dispatch_status,
        "endpoint_bound": evidence.endpoint_bound,
        "engine_version": evidence.engine_version,
        "live_order_authority": evidence.live_order_authority,
        "network_authority": evidence.network_authority,
        "production_authority": evidence.production_authority,
        "real_capital": evidence.real_capital,
        "request_identity": evidence.request_identity,
        "schema_version": evidence.schema_version,
        "semantic": evidence.semantic,
        "transport_bound": evidence.transport_bound,
        "venue_acknowledgement_identity": evidence.venue_acknowledgement_identity,
        "venue_fill_identities": evidence.venue_fill_identities,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
