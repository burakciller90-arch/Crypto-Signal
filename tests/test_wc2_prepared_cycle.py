from __future__ import annotations

from pathlib import Path

import pytest
from test_position_sizing_intelligence import _policy
from test_r22_intent_preview import _activation
from test_wc2_live_source_adapter import _bundle as directional_bundle

from crypto_signal.decision_ledger import (
    DecisionLedgerWriteDisposition,
    ImmutableDecisionEvidenceLedger,
)
from crypto_signal.evaluation.untouched_forward_journal import (
    WC2CohortAppendDisposition,
    WC2CohortJournal,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    build_wc2_untouched_forward_policy,
)
from crypto_signal.evaluation.untouched_forward_prepared import (
    WC2PreparedCycleJournal,
    build_wc2_prepared_cycle_receipt,
)
from crypto_signal.evaluation.untouched_forward_prepared_runtime import (
    complete_wc2_prepared_cycle,
)
from crypto_signal.paper.models import PaperAction
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal


class FailingForecastCohortJournal(WC2CohortJournal):
    def append_forecast(self, record):
        raise RuntimeError("forced cohort forecast crash")


class FailingShadowIntentJournal(R25ShadowIntentJournal):
    def append(self, preview):
        raise RuntimeError("forced shadow intent crash")


PROTOCOL_IDENTITY = "f" * 64


def _inputs(tmp_path: Path):
    bundle = directional_bundle()
    signal = bundle.signal_decision
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=signal.as_of_ms - 2_000,
        collection_start_ms=signal.as_of_ms - 1_000,
    )
    activation = _activation()
    frozen_at = signal.as_of_ms + 10
    issued_at = frozen_at + 10
    receipt = build_wc2_prepared_cycle_receipt(
        bundle,
        policy=policy,
        activation=activation,
        collection_protocol_identity=PROTOCOL_IDENTITY,
        sizing_policy=_policy(),
        source_frozen_at_ms=frozen_at,
        issued_at_ms=issued_at,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        capital_assessed_at_ms=issued_at + 1,
        sized_at_ms=issued_at + 2,
        previewed_at_ms=issued_at + 3,
        indexed_at_ms=issued_at + 3,
    )
    prepared = WC2PreparedCycleJournal(
        tmp_path / "cycle.wc2-prepared.sqlite3"
    )
    assert prepared.append(receipt) is True
    return receipt, policy, activation, prepared


def _runtime_paths(tmp_path: Path):
    return (
        tmp_path / "decision.sqlite3",
        tmp_path / "cohort.sqlite3",
        tmp_path / "cycle.shadow-intent.sqlite3",
        tmp_path / "cycle.shadow-cycle.sqlite3",
    )


def test_prepared_receipt_round_trips_before_any_r20_write(
    tmp_path: Path,
) -> None:
    receipt, _, _, prepared = _inputs(tmp_path)
    decision, cohort, shadow, manifest = _runtime_paths(tmp_path)

    assert prepared.verify_read_only() == 1
    assert prepared.read_for_signal(receipt.signal.freeze_identity) == receipt
    assert receipt.collection_protocol_identity == PROTOCOL_IDENTITY
    assert receipt.historical_backfill_authority is False
    assert receipt.canonical_epoch2_write_authority is False
    assert receipt.production_authority is False
    assert receipt.real_capital == 0
    assert not decision.exists()
    assert not cohort.exists()
    assert not shadow.exists()
    assert not manifest.exists()


def test_prepared_cycle_completes_forecast_and_required_hold_cash_intent(
    tmp_path: Path,
) -> None:
    receipt, policy, activation, _ = _inputs(tmp_path)
    decision_path, cohort_path, shadow_path, manifest_path = _runtime_paths(
        tmp_path
    )
    decision = ImmutableDecisionEvidenceLedger(decision_path)
    cohort = WC2CohortJournal(cohort_path)

    result = complete_wc2_prepared_cycle(
        receipt,
        policy=policy,
        activation=activation,
        decision_ledger=decision,
        cohort_journal=cohort,
        shadow_journal=R25ShadowIntentJournal(shadow_path),
        shadow_manifest=R25ShadowCycleManifest(manifest_path),
    )

    status = cohort.verify_read_only()
    assert result.action is PaperAction.HOLD_CASH
    assert result.historical_market_read_performed is False
    assert result.historical_backfill_authority is False
    assert result.canonical_epoch2_mutation is False
    assert result.production_authority is False
    assert result.real_capital == 0
    assert status.forecast_count == 1
    assert status.intent_count == 1
    assert status.execution_count == 0
    assert decision.read_status().forecast_count == 1
    persisted = decision.read_issuance_for_signal(
        receipt.signal.freeze_identity
    )
    assert persisted is not None
    forecast, _ = persisted
    assert PROTOCOL_IDENTITY in forecast["source_evidence_identities"]
    refs = {
        item["component"]: item["version"]
        for item in forecast["version_refs"]
    }
    assert refs["wc2_collection_protocol"] == PROTOCOL_IDENTITY
    assert R25ShadowIntentJournal(shadow_path).verify_read_only().record_count == 1
    assert R25ShadowCycleManifest(manifest_path).verify_read_only().record_count == 1


def test_prepared_cycle_round_trips_and_completes_without_sizing_policy(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=signal.as_of_ms - 2_000,
        collection_start_ms=signal.as_of_ms - 1_000,
    )
    activation = _activation()
    frozen_at = signal.as_of_ms + 10
    issued_at = frozen_at + 10
    receipt = build_wc2_prepared_cycle_receipt(
        bundle,
        policy=policy,
        activation=activation,
        collection_protocol_identity=PROTOCOL_IDENTITY,
        sizing_policy=None,
        source_frozen_at_ms=frozen_at,
        issued_at_ms=issued_at,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        capital_assessed_at_ms=issued_at + 1,
        sized_at_ms=issued_at + 2,
        previewed_at_ms=issued_at + 3,
        indexed_at_ms=issued_at + 3,
    )
    prepared = WC2PreparedCycleJournal(
        tmp_path / "policy-free.wc2-prepared.sqlite3"
    )
    assert prepared.append(receipt) is True
    replayed = prepared.read_for_signal(signal.freeze_identity)
    assert replayed is not None
    assert replayed.sizing_policy is None
    assert replayed == receipt

    decision_path, cohort_path, shadow_path, manifest_path = _runtime_paths(
        tmp_path
    )
    result = complete_wc2_prepared_cycle(
        replayed,
        policy=policy,
        activation=activation,
        decision_ledger=ImmutableDecisionEvidenceLedger(decision_path),
        cohort_journal=WC2CohortJournal(cohort_path),
        shadow_journal=R25ShadowIntentJournal(shadow_path),
        shadow_manifest=R25ShadowCycleManifest(manifest_path),
    )

    assert result.action is PaperAction.HOLD_CASH
    assert result.historical_market_read_performed is False
    assert result.historical_backfill_authority is False
    assert result.canonical_epoch2_mutation is False
    status = WC2CohortJournal(cohort_path).verify_read_only()
    assert status.forecast_count == 1
    assert status.intent_count == 1
    assert status.execution_count == 0


def test_prepared_cycle_exact_replay_is_fully_idempotent(
    tmp_path: Path,
) -> None:
    receipt, policy, activation, _ = _inputs(tmp_path)
    decision_path, cohort_path, shadow_path, manifest_path = _runtime_paths(
        tmp_path
    )
    decision = ImmutableDecisionEvidenceLedger(decision_path)
    cohort = WC2CohortJournal(cohort_path)
    kwargs = {
        "policy": policy,
        "activation": activation,
        "decision_ledger": decision,
        "cohort_journal": cohort,
        "shadow_journal": R25ShadowIntentJournal(shadow_path),
        "shadow_manifest": R25ShadowCycleManifest(manifest_path),
    }

    first = complete_wc2_prepared_cycle(receipt, **kwargs)
    second = complete_wc2_prepared_cycle(receipt, **kwargs)

    assert first.forecast_identity == second.forecast_identity
    assert first.cohort_forecast_identity == second.cohort_forecast_identity
    assert first.paper_intent_identity == second.paper_intent_identity
    assert first.decision_ledger_disposition is DecisionLedgerWriteDisposition.INSERTED
    assert second.decision_ledger_disposition is DecisionLedgerWriteDisposition.UNCHANGED
    assert first.cohort_forecast_disposition is WC2CohortAppendDisposition.INSERTED
    assert second.cohort_forecast_disposition is WC2CohortAppendDisposition.IDEMPOTENT
    assert first.cohort_intent_disposition is WC2CohortAppendDisposition.INSERTED
    assert second.cohort_intent_disposition is WC2CohortAppendDisposition.IDEMPOTENT
    assert decision.read_status().forecast_count == 1
    status = cohort.verify_read_only()
    assert status.forecast_count == 1
    assert status.intent_count == 1
    assert status.execution_count == 0


def test_crash_after_r20_before_cohort_recovers_from_receipt(
    tmp_path: Path,
) -> None:
    receipt, policy, activation, prepared = _inputs(tmp_path)
    decision_path, cohort_path, shadow_path, manifest_path = _runtime_paths(
        tmp_path
    )
    decision = ImmutableDecisionEvidenceLedger(decision_path)

    with pytest.raises(RuntimeError, match="forced cohort forecast crash"):
        complete_wc2_prepared_cycle(
            receipt,
            policy=policy,
            activation=activation,
            decision_ledger=decision,
            cohort_journal=FailingForecastCohortJournal(cohort_path),
            shadow_journal=R25ShadowIntentJournal(shadow_path),
            shadow_manifest=R25ShadowCycleManifest(manifest_path),
        )

    assert prepared.read_for_signal(receipt.signal.freeze_identity) == receipt
    assert decision.read_status().forecast_count == 1
    assert not cohort_path.exists()
    assert not shadow_path.exists()
    assert not manifest_path.exists()

    recovered = complete_wc2_prepared_cycle(
        receipt,
        policy=policy,
        activation=activation,
        decision_ledger=decision,
        cohort_journal=WC2CohortJournal(cohort_path),
        shadow_journal=R25ShadowIntentJournal(shadow_path),
        shadow_manifest=R25ShadowCycleManifest(manifest_path),
    )

    assert recovered.decision_ledger_disposition is DecisionLedgerWriteDisposition.UNCHANGED
    assert recovered.action is PaperAction.HOLD_CASH
    assert recovered.historical_market_read_performed is False
    assert decision.read_status().forecast_count == 1
    status = WC2CohortJournal(cohort_path).verify_read_only()
    assert status.forecast_count == 1
    assert status.intent_count == 1
    assert status.execution_count == 0


def test_crash_after_cohort_before_shadow_intent_recovers_from_receipt(
    tmp_path: Path,
) -> None:
    receipt, policy, activation, prepared = _inputs(tmp_path)
    decision_path, cohort_path, shadow_path, manifest_path = _runtime_paths(
        tmp_path
    )
    decision = ImmutableDecisionEvidenceLedger(decision_path)
    cohort = WC2CohortJournal(cohort_path)

    with pytest.raises(RuntimeError, match="forced shadow intent crash"):
        complete_wc2_prepared_cycle(
            receipt,
            policy=policy,
            activation=activation,
            decision_ledger=decision,
            cohort_journal=cohort,
            shadow_journal=FailingShadowIntentJournal(shadow_path),
            shadow_manifest=R25ShadowCycleManifest(manifest_path),
        )

    assert prepared.read_for_signal(receipt.signal.freeze_identity) == receipt
    assert decision.read_status().forecast_count == 1
    status = cohort.verify_read_only()
    assert status.forecast_count == 1
    assert status.intent_count == 0
    assert status.execution_count == 0
    assert not manifest_path.exists()

    recovered = complete_wc2_prepared_cycle(
        receipt,
        policy=policy,
        activation=activation,
        decision_ledger=decision,
        cohort_journal=cohort,
        shadow_journal=R25ShadowIntentJournal(shadow_path),
        shadow_manifest=R25ShadowCycleManifest(manifest_path),
    )

    assert recovered.action is PaperAction.HOLD_CASH
    assert decision.read_status().forecast_count == 1
    status = cohort.verify_read_only()
    assert status.forecast_count == 1
    assert status.intent_count == 1
    assert status.execution_count == 0


def test_receipt_refuses_source_before_preregistered_collection(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=signal.as_of_ms - 1_000,
        collection_start_ms=signal.as_of_ms + 10_000,
    )

    with pytest.raises(ValueError, match="predates collection start"):
        build_wc2_prepared_cycle_receipt(
            bundle,
            policy=policy,
            activation=_activation(),
            collection_protocol_identity=PROTOCOL_IDENTITY,
            sizing_policy=_policy(),
            source_frozen_at_ms=signal.as_of_ms + 10,
            issued_at_ms=signal.as_of_ms + 20,
            maximum_issuance_delay_ms=100,
            horizon_bars=4,
            base_asset="BTC",
            capital_assessed_at_ms=signal.as_of_ms + 21,
            sized_at_ms=signal.as_of_ms + 22,
            previewed_at_ms=signal.as_of_ms + 23,
            indexed_at_ms=signal.as_of_ms + 23,
        )

    assert not (tmp_path / "cycle.wc2-prepared.sqlite3").exists()
