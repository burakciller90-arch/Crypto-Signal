"""Immutable Paper Fund epoch contracts.

Epoch 1 remains the accepted 100 USDT legacy paper history. Epoch 2 is a
separate 1,000 USDT virtual-capital program specification. This module models
the transition without mutating either ledger and without granting paper or
real-order authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import (
    INITIAL_CASH_USDT,
    PAPER_FUND_SCHEMA_VERSION,
    REAL_CAPITAL,
    FundCreationRecord,
)

PAPER_EPOCH_SCHEMA_VERSION = "paper_fund_epoch.schema.v1"
PAPER_EPOCH1_ID = "epoch1-legacy-100-usdt"
PAPER_EPOCH2_ID = "epoch2-current-1000-usdt"
PAPER_EPOCH2_STARTING_NAV_USDT = Decimal("1000.00")
PAPER_EPOCH2_CAPITAL_POLICY_VERSION = "paper_capital_allocator.research.v1"


class PaperCapitalVault(StrEnum):
    CORE = "core"
    TACTICAL = "tactical"
    OPPORTUNITY_RESERVE = "opportunity_reserve"


class PaperEpochActivationStatus(StrEnum):
    LEGACY_IMMUTABLE = "legacy_immutable"
    SPECIFIED_NOT_ACTIVATED = "specified_not_activated"


class PaperEpochTransitionSemantic(StrEnum):
    NEW_VIRTUAL_SEED_NO_BALANCE_CARRY = "new_virtual_seed_no_balance_carry"


@dataclass(frozen=True, slots=True)
class PaperVaultAllocation:
    vault: PaperCapitalVault
    amount_usdt: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.vault, PaperCapitalVault):
            raise TypeError("vault must be PaperCapitalVault")
        _require_positive_decimal(self.amount_usdt, "vault amount_usdt")


@dataclass(frozen=True, slots=True)
class PaperFundEpochSpec:
    spec_identity: str
    epoch_id: str
    predecessor_epoch_id: str
    starting_nav_usdt: Decimal
    vault_allocations: tuple[PaperVaultAllocation, ...]
    activation_status: PaperEpochActivationStatus
    capital_policy_version: str
    real_capital: int
    schema_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.spec_identity, "epoch spec identity")
        if self.epoch_id != PAPER_EPOCH2_ID:
            raise ValueError("epoch spec must identify locked Epoch 2")
        if self.predecessor_epoch_id != PAPER_EPOCH1_ID:
            raise ValueError("Epoch 2 predecessor must be immutable Epoch 1")
        if self.starting_nav_usdt != PAPER_EPOCH2_STARTING_NAV_USDT:
            raise ValueError("Epoch 2 starting NAV must be exactly 1000.00 USDT")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.schema_version != PAPER_EPOCH_SCHEMA_VERSION:
            raise ValueError("unsupported paper epoch schema version")
        if self.activation_status is not PaperEpochActivationStatus.SPECIFIED_NOT_ACTIVATED:
            raise ValueError("Epoch 2 domain contract must not self-activate")
        if self.capital_policy_version != PAPER_EPOCH2_CAPITAL_POLICY_VERSION:
            raise ValueError("unexpected Epoch 2 capital policy version")

        normalized = tuple(
            sorted(self.vault_allocations, key=lambda item: item.vault.value)
        )
        if normalized != self.vault_allocations:
            raise ValueError("vault allocations must be deterministically sorted")
        if len({item.vault for item in self.vault_allocations}) != len(
            self.vault_allocations
        ):
            raise ValueError("vault allocations must contain unique vaults")
        if self.vault_allocations != _locked_epoch2_vault_allocations():
            raise ValueError("Epoch 2 vault allocation must remain 600/300/100 USDT")
        if sum(
            (item.amount_usdt for item in self.vault_allocations),
            start=Decimal(0),
        ) != self.starting_nav_usdt:
            raise ValueError("vault allocations must sum to Epoch 2 starting NAV")
        if self.spec_identity != compute_epoch_spec_identity(
            epoch_id=self.epoch_id,
            predecessor_epoch_id=self.predecessor_epoch_id,
            starting_nav_usdt=self.starting_nav_usdt,
            vault_allocations=self.vault_allocations,
            activation_status=self.activation_status,
            capital_policy_version=self.capital_policy_version,
            real_capital=self.real_capital,
            schema_version=self.schema_version,
        ):
            raise ValueError("paper epoch spec identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperEpochTransitionPlan:
    plan_identity: str
    planned_at_ms: int
    source_epoch_id: str
    source_fund_identity: str
    source_initial_cash_usdt: Decimal
    source_history_action: str
    target_epoch_id: str
    target_epoch_spec_identity: str
    target_starting_nav_usdt: Decimal
    semantic: PaperEpochTransitionSemantic
    real_capital: int
    schema_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.plan_identity, "epoch transition plan identity")
        _require_sha256(self.source_fund_identity, "source fund identity")
        _require_sha256(self.target_epoch_spec_identity, "target epoch spec identity")
        if self.planned_at_ms < 0:
            raise ValueError("planned_at_ms must be non-negative")
        if self.source_epoch_id != PAPER_EPOCH1_ID:
            raise ValueError("transition source must be Epoch 1")
        if self.source_initial_cash_usdt != INITIAL_CASH_USDT:
            raise ValueError("Epoch 1 source must retain exactly 100.00 USDT")
        if self.source_history_action != "preserve_immutable":
            raise ValueError("Epoch 1 history must remain immutable")
        if self.target_epoch_id != PAPER_EPOCH2_ID:
            raise ValueError("transition target must be Epoch 2")
        if self.target_starting_nav_usdt != PAPER_EPOCH2_STARTING_NAV_USDT:
            raise ValueError("Epoch 2 target must start at exactly 1000.00 USDT")
        if (
            self.semantic
            is not PaperEpochTransitionSemantic.NEW_VIRTUAL_SEED_NO_BALANCE_CARRY
        ):
            raise ValueError("Epoch transition must not carry or restate Epoch 1 balance")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.schema_version != PAPER_EPOCH_SCHEMA_VERSION:
            raise ValueError("unsupported paper epoch schema version")
        if self.plan_identity != compute_epoch_transition_plan_identity(
            planned_at_ms=self.planned_at_ms,
            source_epoch_id=self.source_epoch_id,
            source_fund_identity=self.source_fund_identity,
            source_initial_cash_usdt=self.source_initial_cash_usdt,
            source_history_action=self.source_history_action,
            target_epoch_id=self.target_epoch_id,
            target_epoch_spec_identity=self.target_epoch_spec_identity,
            target_starting_nav_usdt=self.target_starting_nav_usdt,
            semantic=self.semantic,
            real_capital=self.real_capital,
            schema_version=self.schema_version,
        ):
            raise ValueError("paper epoch transition plan identity mismatch")


def build_epoch2_spec() -> PaperFundEpochSpec:
    allocations = _locked_epoch2_vault_allocations()
    identity = compute_epoch_spec_identity(
        epoch_id=PAPER_EPOCH2_ID,
        predecessor_epoch_id=PAPER_EPOCH1_ID,
        starting_nav_usdt=PAPER_EPOCH2_STARTING_NAV_USDT,
        vault_allocations=allocations,
        activation_status=PaperEpochActivationStatus.SPECIFIED_NOT_ACTIVATED,
        capital_policy_version=PAPER_EPOCH2_CAPITAL_POLICY_VERSION,
        real_capital=REAL_CAPITAL,
        schema_version=PAPER_EPOCH_SCHEMA_VERSION,
    )
    return PaperFundEpochSpec(
        spec_identity=identity,
        epoch_id=PAPER_EPOCH2_ID,
        predecessor_epoch_id=PAPER_EPOCH1_ID,
        starting_nav_usdt=PAPER_EPOCH2_STARTING_NAV_USDT,
        vault_allocations=allocations,
        activation_status=PaperEpochActivationStatus.SPECIFIED_NOT_ACTIVATED,
        capital_policy_version=PAPER_EPOCH2_CAPITAL_POLICY_VERSION,
        real_capital=REAL_CAPITAL,
        schema_version=PAPER_EPOCH_SCHEMA_VERSION,
    )


def build_epoch2_transition_plan(
    *,
    legacy_fund: FundCreationRecord,
    planned_at_ms: int,
    target_spec: PaperFundEpochSpec | None = None,
) -> PaperEpochTransitionPlan:
    if planned_at_ms < 0:
        raise ValueError("planned_at_ms must be non-negative")
    if not isinstance(legacy_fund, FundCreationRecord):
        raise TypeError("legacy_fund must be a FundCreationRecord")
    if legacy_fund.initial_cash_usdt != INITIAL_CASH_USDT:
        raise ValueError("Epoch 1 source must retain exactly 100.00 USDT")
    if legacy_fund.real_capital != REAL_CAPITAL:
        raise ValueError("REAL_CAPITAL must remain 0")
    if legacy_fund.schema_version != PAPER_FUND_SCHEMA_VERSION:
        raise ValueError("legacy source must use accepted paper fund v1 schema")

    spec = build_epoch2_spec() if target_spec is None else target_spec
    identity = compute_epoch_transition_plan_identity(
        planned_at_ms=planned_at_ms,
        source_epoch_id=PAPER_EPOCH1_ID,
        source_fund_identity=legacy_fund.record_identity,
        source_initial_cash_usdt=legacy_fund.initial_cash_usdt,
        source_history_action="preserve_immutable",
        target_epoch_id=spec.epoch_id,
        target_epoch_spec_identity=spec.spec_identity,
        target_starting_nav_usdt=spec.starting_nav_usdt,
        semantic=PaperEpochTransitionSemantic.NEW_VIRTUAL_SEED_NO_BALANCE_CARRY,
        real_capital=REAL_CAPITAL,
        schema_version=PAPER_EPOCH_SCHEMA_VERSION,
    )
    return PaperEpochTransitionPlan(
        plan_identity=identity,
        planned_at_ms=planned_at_ms,
        source_epoch_id=PAPER_EPOCH1_ID,
        source_fund_identity=legacy_fund.record_identity,
        source_initial_cash_usdt=legacy_fund.initial_cash_usdt,
        source_history_action="preserve_immutable",
        target_epoch_id=spec.epoch_id,
        target_epoch_spec_identity=spec.spec_identity,
        target_starting_nav_usdt=spec.starting_nav_usdt,
        semantic=PaperEpochTransitionSemantic.NEW_VIRTUAL_SEED_NO_BALANCE_CARRY,
        real_capital=REAL_CAPITAL,
        schema_version=PAPER_EPOCH_SCHEMA_VERSION,
    )


def compute_epoch_spec_identity(
    *,
    epoch_id: str,
    predecessor_epoch_id: str,
    starting_nav_usdt: Decimal,
    vault_allocations: tuple[PaperVaultAllocation, ...],
    activation_status: PaperEpochActivationStatus,
    capital_policy_version: str,
    real_capital: int,
    schema_version: str,
) -> str:
    return canonical_sha256(
        {
            "activation_status": activation_status.value,
            "capital_policy_version": capital_policy_version,
            "epoch_id": epoch_id,
            "predecessor_epoch_id": predecessor_epoch_id,
            "real_capital": real_capital,
            "schema_version": schema_version,
            "starting_nav_usdt": starting_nav_usdt,
            "vault_allocations": [
                {
                    "amount_usdt": item.amount_usdt,
                    "vault": item.vault.value,
                }
                for item in vault_allocations
            ],
        }
    )


def compute_epoch_transition_plan_identity(
    *,
    planned_at_ms: int,
    source_epoch_id: str,
    source_fund_identity: str,
    source_initial_cash_usdt: Decimal,
    source_history_action: str,
    target_epoch_id: str,
    target_epoch_spec_identity: str,
    target_starting_nav_usdt: Decimal,
    semantic: PaperEpochTransitionSemantic,
    real_capital: int,
    schema_version: str,
) -> str:
    return canonical_sha256(
        {
            "planned_at_ms": planned_at_ms,
            "real_capital": real_capital,
            "schema_version": schema_version,
            "semantic": semantic.value,
            "source_epoch_id": source_epoch_id,
            "source_fund_identity": source_fund_identity,
            "source_history_action": source_history_action,
            "source_initial_cash_usdt": source_initial_cash_usdt,
            "target_epoch_id": target_epoch_id,
            "target_epoch_spec_identity": target_epoch_spec_identity,
            "target_starting_nav_usdt": target_starting_nav_usdt,
        }
    )


def _locked_epoch2_vault_allocations() -> tuple[PaperVaultAllocation, ...]:
    return tuple(
        sorted(
            (
                PaperVaultAllocation(
                    vault=PaperCapitalVault.CORE,
                    amount_usdt=Decimal("600.00"),
                ),
                PaperVaultAllocation(
                    vault=PaperCapitalVault.TACTICAL,
                    amount_usdt=Decimal("300.00"),
                ),
                PaperVaultAllocation(
                    vault=PaperCapitalVault.OPPORTUNITY_RESERVE,
                    amount_usdt=Decimal("100.00"),
                ),
            ),
            key=lambda item: item.vault.value,
        )
    )


def _require_positive_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal, not {type(value).__name__}")
    if value.is_nan() or value.is_infinite() or value <= Decimal(0):
        raise ValueError(f"{label} must be a finite positive Decimal")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be a SHA256 hex digest")
