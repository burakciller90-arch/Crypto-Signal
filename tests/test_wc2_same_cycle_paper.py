from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from test_immutable_forecast_stream import _event_context
from test_position_sizing_intelligence import _policy
from test_r22_intent_preview import _activation
from test_unified_decision_runtime import _issue

from crypto_signal.evaluation.untouched_forward_journal import (
    WC2CohortAppendDisposition,
    WC2CohortJournal,
    build_wc2_cohort_forecast,
)
from crypto_signal.evaluation.untouched_forward_paper import (
    persist_wc2_same_cycle_hold_cash_intent,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    build_wc2_untouched_forward_policy,
)
from crypto_signal.paper.models import PaperAction
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal


def _cohort(tmp_path: Path):
    _, issuance = _issue(tmp_path)
    issued = issuance.forecast.issued_at_ms
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=issued - 2_000,
        collection_start_ms=issued - 1_000,
    )
    cohort = build_wc2_cohort_forecast(
        policy=policy,
        issuance=issuance,
        indexed_at_ms=issued,
    )
    journal = WC2CohortJournal(tmp_path / "wc2-cohort.sqlite3")
    assert (
        journal.append_forecast(cohort)
        is WC2CohortAppendDisposition.INSERTED
    )
    return issuance, cohort, journal


def _paths(tmp_path: Path):
    return (
        tmp_path / "wc2.shadow-intent.sqlite3",
        tmp_path / "wc2.shadow-cycle.sqlite3",
    )


def test_wc2_same_cycle_persists_explicit_hold_cash_without_fill(
    tmp_path: Path,
) -> None:
    issuance, cohort, cohort_journal = _cohort(tmp_path)
    shadow_path, manifest_path = _paths(tmp_path)
    issued = issuance.forecast.issued_at_ms

    result = persist_wc2_same_cycle_hold_cash_intent(
        issuance,
        cohort,
        event_context=_event_context(),
        base_asset="BTC",
        activation=_activation(),
        sizing_policy=_policy(),
        shadow_journal=R25ShadowIntentJournal(shadow_path),
        shadow_manifest=R25ShadowCycleManifest(manifest_path),
        cohort_journal=cohort_journal,
        capital_assessed_at_ms=issued + 1,
        sized_at_ms=issued + 2,
        previewed_at_ms=issued + 3,
        indexed_at_ms=issued + 3,
    )

    status = cohort_journal.verify_read_only()
    assert result.action is PaperAction.HOLD_CASH
    assert result.simulated_execution_created is False
    assert result.explicit_review_used is False
    assert result.canonical_epoch2_mutation is False
    assert result.production_authority is False
    assert result.real_capital == 0
    assert status.forecast_count == 1
    assert status.intent_count == 1
    assert status.execution_count == 0
    assert status.resolution_count == 0
    assert status.unresolved_forecast_count == 1
    assert R25ShadowIntentJournal(shadow_path).verify_read_only().record_count == 1
    assert R25ShadowCycleManifest(manifest_path).verify_read_only().record_count == 1


def test_wc2_same_cycle_exact_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    issuance, cohort, cohort_journal = _cohort(tmp_path)
    shadow_path, manifest_path = _paths(tmp_path)
    issued = issuance.forecast.issued_at_ms
    kwargs = {
        "event_context": _event_context(),
        "base_asset": "BTC",
        "activation": _activation(),
        "sizing_policy": _policy(),
        "shadow_journal": R25ShadowIntentJournal(shadow_path),
        "shadow_manifest": R25ShadowCycleManifest(manifest_path),
        "cohort_journal": cohort_journal,
        "capital_assessed_at_ms": issued + 1,
        "sized_at_ms": issued + 2,
        "previewed_at_ms": issued + 3,
        "indexed_at_ms": issued + 3,
    }

    first = persist_wc2_same_cycle_hold_cash_intent(
        issuance,
        cohort,
        **kwargs,
    )
    second = persist_wc2_same_cycle_hold_cash_intent(
        issuance,
        cohort,
        **kwargs,
    )

    assert first.paper_intent_identity == second.paper_intent_identity
    assert first.intent_link_identity == second.intent_link_identity
    assert (
        first.persisted_shadow_cycle_identity
        == second.persisted_shadow_cycle_identity
    )
    assert first.shadow_manifest_identity == second.shadow_manifest_identity
    assert first.cohort_intent_disposition is WC2CohortAppendDisposition.INSERTED
    assert (
        second.cohort_intent_disposition
        is WC2CohortAppendDisposition.IDEMPOTENT
    )
    status = cohort_journal.verify_read_only()
    assert status.forecast_count == 1
    assert status.intent_count == 1
    assert status.execution_count == 0


def test_wc2_same_cycle_api_has_no_trade_review_or_execution_inputs() -> None:
    params = inspect.signature(
        persist_wc2_same_cycle_hold_cash_intent
    ).parameters

    for forbidden in (
        "risk_inputs",
        "reviewed_method",
        "reviewed_at_ms",
        "market_reference",
        "quantity",
        "fill",
        "calibrated_probability",
    ):
        assert forbidden not in params


def test_wc2_same_cycle_rejects_epoch2_activation_after_forecast_before_writes(
    tmp_path: Path,
) -> None:
    issuance, cohort, cohort_journal = _cohort(tmp_path)
    shadow_path, manifest_path = _paths(tmp_path)
    issued = issuance.forecast.issued_at_ms
    late_activation = _activation()
    late_activation = type(late_activation)(
        activation_identity=late_activation.activation_identity,
        schema_version=late_activation.schema_version,
        engine_version=late_activation.engine_version,
        epoch_identity=late_activation.epoch_identity,
        predecessor_epoch_identity=late_activation.predecessor_epoch_identity,
        activated_at_ms=issued + 10,
        starting_cash_usdt=late_activation.starting_cash_usdt,
        vault_starting_cash=late_activation.vault_starting_cash,
        epoch1_ledger_sha256=late_activation.epoch1_ledger_sha256,
        real_capital=late_activation.real_capital,
        leverage_allowed=late_activation.leverage_allowed,
        borrowing_allowed=late_activation.borrowing_allowed,
        martingale_allowed=late_activation.martingale_allowed,
    )

    with pytest.raises(ValueError):
        persist_wc2_same_cycle_hold_cash_intent(
            issuance,
            cohort,
            event_context=_event_context(),
            base_asset="BTC",
            activation=late_activation,
            sizing_policy=_policy(),
            shadow_journal=R25ShadowIntentJournal(shadow_path),
            shadow_manifest=R25ShadowCycleManifest(manifest_path),
            cohort_journal=cohort_journal,
            capital_assessed_at_ms=issued + 11,
            sized_at_ms=issued + 12,
            previewed_at_ms=issued + 13,
            indexed_at_ms=issued + 13,
        )

    assert not shadow_path.exists()
    assert not manifest_path.exists()
    status = cohort_journal.verify_read_only()
    assert status.forecast_count == 1
    assert status.intent_count == 0
    assert status.execution_count == 0
