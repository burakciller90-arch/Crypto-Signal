from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.paper.epochs import (
    PAPER_EPOCH1_ID,
    PAPER_EPOCH2_CAPITAL_POLICY_VERSION,
    PAPER_EPOCH2_ID,
    PAPER_EPOCH2_STARTING_NAV_USDT,
    PAPER_EPOCH_SCHEMA_VERSION,
    PaperCapitalVault,
    PaperEpochActivationStatus,
    PaperEpochTransitionSemantic,
    PaperFundEpochSpec,
    PaperVaultAllocation,
    build_epoch2_spec,
    build_epoch2_transition_plan,
)
from crypto_signal.paper.models import (
    INITIAL_CASH_USDT,
    REAL_CAPITAL,
    build_fund_creation,
)


def test_epoch1_legacy_contract_is_not_rewritten() -> None:
    assert INITIAL_CASH_USDT == Decimal("100.00")
    legacy = build_fund_creation(created_at_ms=1_700_000_000_000)
    assert legacy.initial_cash_usdt == Decimal("100.00")
    assert legacy.real_capital == 0


def test_epoch2_locked_spec_is_deterministic_and_not_activated() -> None:
    first = build_epoch2_spec()
    second = build_epoch2_spec()

    assert first == second
    assert first.spec_identity == second.spec_identity
    assert len(first.spec_identity) == 64
    assert first.epoch_id == PAPER_EPOCH2_ID
    assert first.predecessor_epoch_id == PAPER_EPOCH1_ID
    assert first.starting_nav_usdt == Decimal("1000.00")
    assert first.starting_nav_usdt == PAPER_EPOCH2_STARTING_NAV_USDT
    assert (
        first.activation_status
        is PaperEpochActivationStatus.SPECIFIED_NOT_ACTIVATED
    )
    assert first.capital_policy_version == PAPER_EPOCH2_CAPITAL_POLICY_VERSION
    assert first.schema_version == PAPER_EPOCH_SCHEMA_VERSION
    assert first.real_capital == REAL_CAPITAL == 0


def test_epoch2_locked_vault_allocation_is_exact_600_300_100() -> None:
    spec = build_epoch2_spec()
    by_vault = {item.vault: item.amount_usdt for item in spec.vault_allocations}

    assert by_vault == {
        PaperCapitalVault.CORE: Decimal("600.00"),
        PaperCapitalVault.TACTICAL: Decimal("300.00"),
        PaperCapitalVault.OPPORTUNITY_RESERVE: Decimal("100.00"),
    }
    assert sum(by_vault.values(), start=Decimal(0)) == Decimal("1000.00")


def test_epoch2_spec_rejects_wrong_capital_or_allocation() -> None:
    spec = build_epoch2_spec()

    with pytest.raises(ValueError, match="starting NAV"):
        PaperFundEpochSpec(
            spec_identity=spec.spec_identity,
            epoch_id=spec.epoch_id,
            predecessor_epoch_id=spec.predecessor_epoch_id,
            starting_nav_usdt=Decimal("999.00"),
            vault_allocations=spec.vault_allocations,
            activation_status=spec.activation_status,
            capital_policy_version=spec.capital_policy_version,
            real_capital=spec.real_capital,
            schema_version=spec.schema_version,
        )

    wrong_allocations = tuple(
        sorted(
            (
                PaperVaultAllocation(
                    vault=PaperCapitalVault.CORE,
                    amount_usdt=Decimal("500.00"),
                ),
                PaperVaultAllocation(
                    vault=PaperCapitalVault.TACTICAL,
                    amount_usdt=Decimal("400.00"),
                ),
                PaperVaultAllocation(
                    vault=PaperCapitalVault.OPPORTUNITY_RESERVE,
                    amount_usdt=Decimal("100.00"),
                ),
            ),
            key=lambda item: item.vault.value,
        )
    )
    with pytest.raises(ValueError, match="600/300/100"):
        replace(spec, vault_allocations=wrong_allocations)


def test_epoch2_transition_preserves_epoch1_and_never_carries_balance() -> None:
    legacy = build_fund_creation(created_at_ms=1_700_000_000_000)
    spec = build_epoch2_spec()

    plan = build_epoch2_transition_plan(
        legacy_fund=legacy,
        planned_at_ms=1_800_000_000_000,
        target_spec=spec,
    )

    assert plan.source_epoch_id == PAPER_EPOCH1_ID
    assert plan.source_fund_identity == legacy.record_identity
    assert plan.source_initial_cash_usdt == Decimal("100.00")
    assert plan.source_history_action == "preserve_immutable"
    assert plan.target_epoch_id == PAPER_EPOCH2_ID
    assert plan.target_epoch_spec_identity == spec.spec_identity
    assert plan.target_starting_nav_usdt == Decimal("1000.00")
    assert (
        plan.semantic
        is PaperEpochTransitionSemantic.NEW_VIRTUAL_SEED_NO_BALANCE_CARRY
    )
    assert plan.real_capital == 0
    assert len(plan.plan_identity) == 64

    # Planning an epoch transition is a pure model operation. The accepted
    # legacy FundCreationRecord remains byte-semantically unchanged.
    assert legacy == build_fund_creation(created_at_ms=1_700_000_000_000)


def test_epoch2_transition_identity_is_deterministic_and_time_bound() -> None:
    legacy = build_fund_creation(created_at_ms=42)
    first = build_epoch2_transition_plan(
        legacy_fund=legacy,
        planned_at_ms=100,
    )
    second = build_epoch2_transition_plan(
        legacy_fund=legacy,
        planned_at_ms=100,
    )
    later = build_epoch2_transition_plan(
        legacy_fund=legacy,
        planned_at_ms=101,
    )

    assert first == second
    assert first.plan_identity == second.plan_identity
    assert first.plan_identity != later.plan_identity


def test_epoch2_contract_cannot_self_grant_real_capital_or_activation() -> None:
    spec = build_epoch2_spec()

    with pytest.raises(ValueError, match="REAL_CAPITAL"):
        replace(spec, real_capital=1)

    with pytest.raises(ValueError, match="must not self-activate"):
        replace(spec, activation_status=PaperEpochActivationStatus.LEGACY_IMMUTABLE)
