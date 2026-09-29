"""FP4-D immutable instrument-specific paper fee schedule.

Normalizes a caller-supplied Binance Spot account commission response. This
module does not fetch credentials or place orders. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol

FP4_INSTRUMENT_FEE_SCHEMA_VERSION = "paper_instrument_fee_schedule.v2"
BINANCE_SPOT_ACCOUNT_COMMISSION_SOURCE = "binance_spot_account_commission.v1"


class InstrumentFeeRole(StrEnum):
    MAKER = "maker"
    TAKER = "taker"


class InstrumentFeeProjectionStatus(StrEnum):
    PROVEN = "proven"
    FEE_NOT_PROVEN = "fee_not_proven"


@dataclass(frozen=True, slots=True)
class CommissionRateFamily:
    maker: Decimal
    taker: Decimal
    buyer: Decimal
    seller: Decimal

    def __post_init__(self) -> None:
        for label, value in (
            ("maker", self.maker),
            ("taker", self.taker),
            ("buyer", self.buyer),
            ("seller", self.seller),
        ):
            _require_rate(value, label)

    def rate_for(self, *, role: InstrumentFeeRole, action: PaperAction) -> Decimal:
        role_rate = self.maker if role is InstrumentFeeRole.MAKER else self.taker
        side_rate = self.buyer if action is PaperAction.BUY else self.seller
        return role_rate + side_rate


@dataclass(frozen=True, slots=True)
class InstrumentFeeScheduleSnapshot:
    snapshot_identity: str
    schema_version: str
    source_contract: str
    symbol: PaperSymbol
    observed_at_ms: int
    ingested_at_ms: int
    source_payload_sha256: str
    standard: CommissionRateFamily
    special: CommissionRateFamily
    tax: CommissionRateFamily
    discount_enabled_for_account: bool
    discount_enabled_for_symbol: bool
    discount_asset: str
    discount_rate: Decimal
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.snapshot_identity, "snapshot_identity")
        _require_sha256(self.source_payload_sha256, "source_payload_sha256")
        if self.schema_version != FP4_INSTRUMENT_FEE_SCHEMA_VERSION:
            raise ValueError("unsupported instrument fee schema version")
        if self.source_contract != BINANCE_SPOT_ACCOUNT_COMMISSION_SOURCE:
            raise ValueError("instrument fee source contract mismatch")
        if min(self.observed_at_ms, self.ingested_at_ms) < 0:
            raise ValueError("fee snapshot timestamps must be non-negative")
        if self.observed_at_ms > self.ingested_at_ms:
            raise ValueError("fee snapshot observation cannot postdate ingestion")
        if not self.discount_asset.strip():
            raise ValueError("discount_asset must be non-empty")
        _require_rate(self.discount_rate, "discount_rate")
        expected = compute_instrument_fee_snapshot_identity(
            schema_version=self.schema_version,
            source_contract=self.source_contract,
            symbol=self.symbol,
            observed_at_ms=self.observed_at_ms,
            ingested_at_ms=self.ingested_at_ms,
            source_payload_sha256=self.source_payload_sha256,
            standard=self.standard,
            special=self.special,
            tax=self.tax,
            discount_enabled_for_account=self.discount_enabled_for_account,
            discount_enabled_for_symbol=self.discount_enabled_for_symbol,
            discount_asset=self.discount_asset,
            discount_rate=self.discount_rate,
        )
        if self.snapshot_identity != expected:
            raise ValueError("instrument fee snapshot identity mismatch")


@dataclass(frozen=True, slots=True)
class InstrumentFeeProjection:
    projection_identity: str
    policy_version: str
    status: InstrumentFeeProjectionStatus
    symbol: PaperSymbol
    action: PaperAction
    role: InstrumentFeeRole
    fill_notional_usdt: Decimal
    snapshot_identity: str | None
    standard_rate_before_discount: Decimal | None
    standard_rate_after_discount: Decimal | None
    special_rate: Decimal | None
    tax_rate: Decimal | None
    effective_fee_rate: Decimal | None
    fee_usdt: Decimal | None
    discount_applied: bool
    discount_payment_proof_identity: str | None
    reason_code: str
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.projection_identity, "projection_identity")
        _require_positive_decimal(self.fill_notional_usdt, "fill_notional_usdt")
        if self.action not in {PaperAction.BUY, PaperAction.REDUCE, PaperAction.EXIT}:
            raise ValueError("fee projection requires BUY/REDUCE/EXIT")
        if not self.policy_version.strip() or not self.reason_code.strip():
            raise ValueError("policy_version and reason_code must be non-empty")
        if self.status is InstrumentFeeProjectionStatus.PROVEN:
            if self.snapshot_identity is None:
                raise ValueError("PROVEN fee requires snapshot identity")
            _require_sha256(self.snapshot_identity, "snapshot_identity")
            for label, value in (
                ("standard_rate_before_discount", self.standard_rate_before_discount),
                ("standard_rate_after_discount", self.standard_rate_after_discount),
                ("special_rate", self.special_rate),
                ("tax_rate", self.tax_rate),
                ("effective_fee_rate", self.effective_fee_rate),
                ("fee_usdt", self.fee_usdt),
            ):
                if value is None:
                    raise ValueError(f"PROVEN fee requires {label}")
                _require_non_negative_decimal(value, label)
            assert self.standard_rate_after_discount is not None
            assert self.special_rate is not None
            assert self.tax_rate is not None
            assert self.effective_fee_rate is not None
            assert self.fee_usdt is not None
            if (
                self.effective_fee_rate
                != self.standard_rate_after_discount + self.special_rate + self.tax_rate
            ):
                raise ValueError("effective fee rate does not reconcile")
            if self.fee_usdt != self.fill_notional_usdt * self.effective_fee_rate:
                raise ValueError("fee_usdt does not reconcile to fill notional")
            if self.discount_applied:
                if self.discount_payment_proof_identity is None:
                    raise ValueError("discount requires explicit payment proof")
                _require_sha256(
                    self.discount_payment_proof_identity,
                    "discount_payment_proof_identity",
                )
            elif self.discount_payment_proof_identity is not None:
                raise ValueError("unused discount proof must not be persisted")
        else:
            if any(
                value is not None
                for value in (
                    self.snapshot_identity,
                    self.standard_rate_before_discount,
                    self.standard_rate_after_discount,
                    self.special_rate,
                    self.tax_rate,
                    self.effective_fee_rate,
                    self.fee_usdt,
                    self.discount_payment_proof_identity,
                )
            ):
                raise ValueError("FEE_NOT_PROVEN cannot invent fee evidence")
            if self.discount_applied:
                raise ValueError("FEE_NOT_PROVEN cannot apply discount")
        expected = compute_instrument_fee_projection_identity(
            policy_version=self.policy_version,
            status=self.status,
            symbol=self.symbol,
            action=self.action,
            role=self.role,
            fill_notional_usdt=self.fill_notional_usdt,
            snapshot_identity=self.snapshot_identity,
            standard_rate_before_discount=self.standard_rate_before_discount,
            standard_rate_after_discount=self.standard_rate_after_discount,
            special_rate=self.special_rate,
            tax_rate=self.tax_rate,
            effective_fee_rate=self.effective_fee_rate,
            fee_usdt=self.fee_usdt,
            discount_applied=self.discount_applied,
            discount_payment_proof_identity=self.discount_payment_proof_identity,
            reason_code=self.reason_code,
        )
        if self.projection_identity != expected:
            raise ValueError("instrument fee projection identity mismatch")


def normalize_binance_spot_commission_snapshot(
    *,
    payload: Mapping[str, Any],
    observed_at_ms: int,
    ingested_at_ms: int,
) -> InstrumentFeeScheduleSnapshot:
    """Normalize the documented account.commission result object."""
    if min(observed_at_ms, ingested_at_ms) < 0:
        raise ValueError("fee snapshot timestamps must be non-negative")
    if observed_at_ms > ingested_at_ms:
        raise ValueError("fee observation cannot postdate ingestion")

    symbol = PaperSymbol(str(payload["symbol"]))
    standard = _parse_family(payload["standardCommission"], "standardCommission")
    special = _parse_family(payload["specialCommission"], "specialCommission")
    tax = _parse_family(payload["taxCommission"], "taxCommission")
    discount = _require_mapping(payload["discount"], "discount")
    discount_asset = str(discount["discountAsset"])
    discount_rate = Decimal(str(discount["discount"]))
    enabled_account = _require_bool(
        discount["enabledForAccount"],
        "discount.enabledForAccount",
    )
    enabled_symbol = _require_bool(
        discount["enabledForSymbol"],
        "discount.enabledForSymbol",
    )

    source_payload_sha256 = canonical_sha256(_canonical_payload(payload))
    identity = compute_instrument_fee_snapshot_identity(
        schema_version=FP4_INSTRUMENT_FEE_SCHEMA_VERSION,
        source_contract=BINANCE_SPOT_ACCOUNT_COMMISSION_SOURCE,
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        source_payload_sha256=source_payload_sha256,
        standard=standard,
        special=special,
        tax=tax,
        discount_enabled_for_account=enabled_account,
        discount_enabled_for_symbol=enabled_symbol,
        discount_asset=discount_asset,
        discount_rate=discount_rate,
    )
    return InstrumentFeeScheduleSnapshot(
        snapshot_identity=identity,
        schema_version=FP4_INSTRUMENT_FEE_SCHEMA_VERSION,
        source_contract=BINANCE_SPOT_ACCOUNT_COMMISSION_SOURCE,
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        source_payload_sha256=source_payload_sha256,
        standard=standard,
        special=special,
        tax=tax,
        discount_enabled_for_account=enabled_account,
        discount_enabled_for_symbol=enabled_symbol,
        discount_asset=discount_asset,
        discount_rate=discount_rate,
        real_capital=REAL_CAPITAL,
    )


def project_instrument_fee(
    *,
    snapshot: InstrumentFeeScheduleSnapshot | None,
    symbol: PaperSymbol,
    action: PaperAction,
    role: InstrumentFeeRole,
    fill_notional_usdt: Decimal,
    evaluation_cutoff_ms: int,
    discount_payment_proof_identity: str | None = None,
    policy_version: str = FP4_INSTRUMENT_FEE_SCHEMA_VERSION,
) -> InstrumentFeeProjection:
    _require_positive_decimal(fill_notional_usdt, "fill_notional_usdt")
    if evaluation_cutoff_ms < 0:
        raise ValueError("evaluation_cutoff_ms must be non-negative")
    if snapshot is None:
        return _not_proven(
            policy_version=policy_version,
            symbol=symbol,
            action=action,
            role=role,
            fill_notional_usdt=fill_notional_usdt,
            reason_code="missing_exact_instrument_fee_snapshot",
        )
    if snapshot.ingested_at_ms > evaluation_cutoff_ms:
        raise ValueError("future fee snapshot cannot enter historical execution")
    if snapshot.symbol is not symbol:
        raise ValueError("fee snapshot symbol mismatch")
    if action not in {PaperAction.BUY, PaperAction.REDUCE, PaperAction.EXIT}:
        raise ValueError("fee projection requires BUY/REDUCE/EXIT")

    standard = snapshot.standard.rate_for(role=role, action=action)
    special = snapshot.special.rate_for(role=role, action=action)
    tax = snapshot.tax.rate_for(role=role, action=action)

    discount_eligible = (
        snapshot.discount_enabled_for_account
        and snapshot.discount_enabled_for_symbol
    )
    discount_applied = (
        discount_eligible and discount_payment_proof_identity is not None
    )
    if discount_payment_proof_identity is not None:
        _require_sha256(
            discount_payment_proof_identity,
            "discount_payment_proof_identity",
        )
    standard_after_discount = (
        standard * snapshot.discount_rate
        if discount_applied
        else standard
    )
    effective = standard_after_discount + special + tax
    fee_usdt = fill_notional_usdt * effective
    reason = (
        "exact_schedule_with_proven_discount_payment"
        if discount_applied
        else "exact_schedule_without_discount_assumption"
    )
    return _build_projection(
        policy_version=policy_version,
        status=InstrumentFeeProjectionStatus.PROVEN,
        symbol=symbol,
        action=action,
        role=role,
        fill_notional_usdt=fill_notional_usdt,
        snapshot_identity=snapshot.snapshot_identity,
        standard_rate_before_discount=standard,
        standard_rate_after_discount=standard_after_discount,
        special_rate=special,
        tax_rate=tax,
        effective_fee_rate=effective,
        fee_usdt=fee_usdt,
        discount_applied=discount_applied,
        discount_payment_proof_identity=(
            discount_payment_proof_identity if discount_applied else None
        ),
        reason_code=reason,
    )


def compute_instrument_fee_snapshot_identity(
    *,
    schema_version: str,
    source_contract: str,
    symbol: PaperSymbol,
    observed_at_ms: int,
    ingested_at_ms: int,
    source_payload_sha256: str,
    standard: CommissionRateFamily,
    special: CommissionRateFamily,
    tax: CommissionRateFamily,
    discount_enabled_for_account: bool,
    discount_enabled_for_symbol: bool,
    discount_asset: str,
    discount_rate: Decimal,
) -> str:
    return canonical_sha256(
        {
            "discount_asset": discount_asset,
            "discount_enabled_for_account": discount_enabled_for_account,
            "discount_enabled_for_symbol": discount_enabled_for_symbol,
            "discount_rate": discount_rate,
            "ingested_at_ms": ingested_at_ms,
            "observed_at_ms": observed_at_ms,
            "schema_version": schema_version,
            "source_contract": source_contract,
            "source_payload_sha256": source_payload_sha256,
            "special": _family_payload(special),
            "standard": _family_payload(standard),
            "symbol": symbol.value,
            "tax": _family_payload(tax),
        }
    )


def compute_instrument_fee_projection_identity(
    *,
    policy_version: str,
    status: InstrumentFeeProjectionStatus,
    symbol: PaperSymbol,
    action: PaperAction,
    role: InstrumentFeeRole,
    fill_notional_usdt: Decimal,
    snapshot_identity: str | None,
    standard_rate_before_discount: Decimal | None,
    standard_rate_after_discount: Decimal | None,
    special_rate: Decimal | None,
    tax_rate: Decimal | None,
    effective_fee_rate: Decimal | None,
    fee_usdt: Decimal | None,
    discount_applied: bool,
    discount_payment_proof_identity: str | None,
    reason_code: str,
) -> str:
    return canonical_sha256(
        {
            "action": action.value,
            "discount_applied": discount_applied,
            "discount_payment_proof_identity": discount_payment_proof_identity,
            "effective_fee_rate": effective_fee_rate,
            "fee_usdt": fee_usdt,
            "fill_notional_usdt": fill_notional_usdt,
            "policy_version": policy_version,
            "reason_code": reason_code,
            "role": role.value,
            "snapshot_identity": snapshot_identity,
            "special_rate": special_rate,
            "standard_rate_after_discount": standard_rate_after_discount,
            "standard_rate_before_discount": standard_rate_before_discount,
            "status": status.value,
            "symbol": symbol.value,
            "tax_rate": tax_rate,
        }
    )


def _not_proven(
    *,
    policy_version: str,
    symbol: PaperSymbol,
    action: PaperAction,
    role: InstrumentFeeRole,
    fill_notional_usdt: Decimal,
    reason_code: str,
) -> InstrumentFeeProjection:
    return _build_projection(
        policy_version=policy_version,
        status=InstrumentFeeProjectionStatus.FEE_NOT_PROVEN,
        symbol=symbol,
        action=action,
        role=role,
        fill_notional_usdt=fill_notional_usdt,
        snapshot_identity=None,
        standard_rate_before_discount=None,
        standard_rate_after_discount=None,
        special_rate=None,
        tax_rate=None,
        effective_fee_rate=None,
        fee_usdt=None,
        discount_applied=False,
        discount_payment_proof_identity=None,
        reason_code=reason_code,
    )


def _build_projection(
    *,
    policy_version: str,
    status: InstrumentFeeProjectionStatus,
    symbol: PaperSymbol,
    action: PaperAction,
    role: InstrumentFeeRole,
    fill_notional_usdt: Decimal,
    snapshot_identity: str | None,
    standard_rate_before_discount: Decimal | None,
    standard_rate_after_discount: Decimal | None,
    special_rate: Decimal | None,
    tax_rate: Decimal | None,
    effective_fee_rate: Decimal | None,
    fee_usdt: Decimal | None,
    discount_applied: bool,
    discount_payment_proof_identity: str | None,
    reason_code: str,
) -> InstrumentFeeProjection:
    identity = compute_instrument_fee_projection_identity(
        policy_version=policy_version,
        status=status,
        symbol=symbol,
        action=action,
        role=role,
        fill_notional_usdt=fill_notional_usdt,
        snapshot_identity=snapshot_identity,
        standard_rate_before_discount=standard_rate_before_discount,
        standard_rate_after_discount=standard_rate_after_discount,
        special_rate=special_rate,
        tax_rate=tax_rate,
        effective_fee_rate=effective_fee_rate,
        fee_usdt=fee_usdt,
        discount_applied=discount_applied,
        discount_payment_proof_identity=discount_payment_proof_identity,
        reason_code=reason_code,
    )
    return InstrumentFeeProjection(
        projection_identity=identity,
        policy_version=policy_version,
        status=status,
        symbol=symbol,
        action=action,
        role=role,
        fill_notional_usdt=fill_notional_usdt,
        snapshot_identity=snapshot_identity,
        standard_rate_before_discount=standard_rate_before_discount,
        standard_rate_after_discount=standard_rate_after_discount,
        special_rate=special_rate,
        tax_rate=tax_rate,
        effective_fee_rate=effective_fee_rate,
        fee_usdt=fee_usdt,
        discount_applied=discount_applied,
        discount_payment_proof_identity=discount_payment_proof_identity,
        reason_code=reason_code,
        real_capital=REAL_CAPITAL,
    )


def _parse_family(value: Any, label: str) -> CommissionRateFamily:
    mapping = _require_mapping(value, label)
    return CommissionRateFamily(
        maker=Decimal(str(mapping["maker"])),
        taker=Decimal(str(mapping["taker"])),
        buyer=Decimal(str(mapping["buyer"])),
        seller=Decimal(str(mapping["seller"])),
    )


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be bool")
    return value


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _canonical_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "discount": dict(_require_mapping(payload["discount"], "discount")),
        "specialCommission": dict(
            _require_mapping(payload["specialCommission"], "specialCommission")
        ),
        "standardCommission": dict(
            _require_mapping(payload["standardCommission"], "standardCommission")
        ),
        "symbol": str(payload["symbol"]),
        "taxCommission": dict(_require_mapping(payload["taxCommission"], "taxCommission")),
    }


def _family_payload(family: CommissionRateFamily) -> dict[str, Decimal]:
    return {
        "buyer": family.buyer,
        "maker": family.maker,
        "seller": family.seller,
        "taker": family.taker,
    }


def _require_rate(value: Decimal, label: str) -> None:
    _require_non_negative_decimal(value, label)
    if value > Decimal(1):
        raise ValueError(f"{label} must be <= 1")


def _require_positive_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite() or value <= Decimal(0):
        raise ValueError(f"{label} must be finite and positive")


def _require_non_negative_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite() or value < Decimal(0):
        raise ValueError(f"{label} must be finite and non-negative")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


__all__ = [
    "BINANCE_SPOT_ACCOUNT_COMMISSION_SOURCE",
    "FP4_INSTRUMENT_FEE_SCHEMA_VERSION",
    "CommissionRateFamily",
    "InstrumentFeeProjection",
    "InstrumentFeeProjectionStatus",
    "InstrumentFeeRole",
    "InstrumentFeeScheduleSnapshot",
    "compute_instrument_fee_projection_identity",
    "compute_instrument_fee_snapshot_identity",
    "normalize_binance_spot_commission_snapshot",
    "project_instrument_fee",
]
