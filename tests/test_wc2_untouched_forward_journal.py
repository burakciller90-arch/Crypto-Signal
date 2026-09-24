from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto_signal.evaluation.untouched_forward_journal import (
    WC2_COHORT_ENGINE_VERSION,
    WC2_COHORT_SCHEMA_VERSION,
    WC2CohortAppendDisposition,
    WC2CohortExecution,
    WC2CohortForecast,
    WC2CohortIntent,
    WC2CohortJournal,
    WC2CohortResolution,
    build_wc2_cohort_execution,
    build_wc2_cohort_resolution,
)
from crypto_signal.forecast_stream import ForecastResolutionState
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.outcomes.models import EvidenceClass
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction


def _sha(ch: str) -> str:
    return ch * 64


def _forecast(
    *,
    forecast_identity: str = _sha("a"),
    indexed_at_ms: int = 2_000,
) -> WC2CohortForecast:
    values = {
        "policy_identity": _sha("b"),
        "forecast_identity": forecast_identity,
        "proof_identity": _sha("c"),
        "signal_freeze_identity": _sha("d"),
        "confluence_identity": _sha("e"),
        "event_context_identity": _sha("f"),
        "asset": "BTC",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "regime": "high_vol_trend",
        "issued_at_ms": 1_000,
        "indexed_at_ms": indexed_at_ms,
        "source_evidence_identities": (_sha("1"), _sha("2")),
        "evidence_class": EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        "schema_version": WC2_COHORT_SCHEMA_VERSION,
        "engine_version": WC2_COHORT_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": 0,
    }
    return WC2CohortForecast(
        cohort_forecast_identity=canonical_sha256(values),
        **values,
    )


def _intent(
    forecast: WC2CohortForecast,
    *,
    vault_id: PaperVaultId = PaperVaultId.CORE,
    action: PaperAction = PaperAction.BUY,
    intent_seed: str = "3",
) -> WC2CohortIntent:
    values = {
        "policy_identity": forecast.policy_identity,
        "cohort_forecast_identity": forecast.cohort_forecast_identity,
        "forecast_identity": forecast.forecast_identity,
        "proof_identity": forecast.proof_identity,
        "persisted_cycle_identity": _sha("4"),
        "manifest_identity": _sha("5"),
        "shadow_cycle_identity": _sha("6"),
        "preview_identity": _sha("7"),
        "shadow_intent_record_identity": _sha("8"),
        "paper_intent_identity": _sha(intent_seed),
        "vault_id": vault_id,
        "action": action,
        "decided_at_ms": 1_100,
        "previewed_at_ms": 1_200,
        "indexed_at_ms": 2_100,
        "schema_version": WC2_COHORT_SCHEMA_VERSION,
        "engine_version": WC2_COHORT_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": 0,
    }
    return WC2CohortIntent(
        intent_link_identity=canonical_sha256(values),
        **values,
    )


def _execution(
    forecast: WC2CohortForecast,
    intent: WC2CohortIntent,
    *,
    fill_identity: str = _sha("9"),
) -> WC2CohortExecution:
    fill = SimpleNamespace(
        intent_identity=intent.paper_intent_identity,
        action=intent.action,
        fill_identity=fill_identity,
        filled_at_ms=1_300,
        fee_usdt=Decimal("0.10"),
        spread_usdt=Decimal("0.20"),
        slippage_usdt=Decimal("0.30"),
        execution_policy_version="paper-execution-v1",
        venue_reference="simulated-bybit-reference",
        mark_evidence_identity=_sha("a"),
    )
    record = build_wc2_cohort_execution(
        intent,
        fill,
        indexed_at_ms=2_200,
    )
    assert record.cohort_forecast_identity == forecast.cohort_forecast_identity
    return record


def _resolution(
    forecast: WC2CohortForecast,
) -> WC2CohortResolution:
    resolution = SimpleNamespace(
        forecast_identity=forecast.forecast_identity,
        signal_freeze_identity=forecast.signal_freeze_identity,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        evaluated_at_ms=3_000,
        resolution_identity=_sha("b"),
        source_outcome_identity=_sha("c"),
        state=ForecastResolutionState.HIT_TARGET,
    )
    return build_wc2_cohort_resolution(
        forecast,
        resolution,
        indexed_at_ms=3_100,
    )


def test_wc2_cohort_forecast_is_live_untouched_and_immutable() -> None:
    forecast = _forecast()

    assert forecast.evidence_class is EvidenceClass.LIVE_UNTOUCHED_FORWARD
    assert forecast.production_authority is False
    assert forecast.real_capital == 0

    with pytest.raises(ValueError, match="LIVE_UNTOUCHED_FORWARD"):
        replace(forecast, evidence_class=EvidenceClass.WALK_FORWARD)


def test_wc2_cohort_supports_multiple_vault_intents_without_forecast_duplication(
    tmp_path: Path,
) -> None:
    journal = WC2CohortJournal(tmp_path / "wc2-cohort.sqlite3")
    forecast = _forecast()
    core = _intent(
        forecast,
        vault_id=PaperVaultId.CORE,
        intent_seed="3",
    )
    tactical = _intent(
        forecast,
        vault_id=PaperVaultId.TACTICAL,
        action=PaperAction.HOLD_CASH,
        intent_seed="4",
    )

    assert journal.append_forecast(forecast) is WC2CohortAppendDisposition.INSERTED
    assert journal.append_forecast(forecast) is WC2CohortAppendDisposition.IDEMPOTENT
    assert journal.append_intent(core) is WC2CohortAppendDisposition.INSERTED
    assert journal.append_intent(tactical) is WC2CohortAppendDisposition.INSERTED

    status = journal.verify_read_only()
    assert status.forecast_count == 1
    assert status.intent_count == 2
    assert status.execution_count == 0
    assert status.resolution_count == 0
    assert status.unresolved_forecast_count == 1
    assert status.production_authority is False
    assert status.real_capital == 0


def test_wc2_same_forecast_vault_cannot_fork_intent(tmp_path: Path) -> None:
    journal = WC2CohortJournal(tmp_path / "wc2-cohort.sqlite3")
    forecast = _forecast()
    first = _intent(forecast)
    fork = _intent(forecast, intent_seed="4")

    journal.append_forecast(forecast)
    journal.append_intent(first)

    with pytest.raises(ValueError, match="intent conflict"):
        journal.append_intent(fork)


def test_wc2_hold_cash_never_creates_fake_execution() -> None:
    forecast = _forecast()
    hold = _intent(
        forecast,
        action=PaperAction.HOLD_CASH,
    )
    fake_fill = SimpleNamespace(
        intent_identity=hold.paper_intent_identity,
        action=PaperAction.HOLD_CASH,
    )

    with pytest.raises(ValueError, match="HOLD_CASH"):
        build_wc2_cohort_execution(
            hold,
            fake_fill,
            indexed_at_ms=2_200,
        )


def test_wc2_execution_binds_exact_intent_and_explicit_costs(
    tmp_path: Path,
) -> None:
    journal = WC2CohortJournal(tmp_path / "wc2-cohort.sqlite3")
    forecast = _forecast()
    intent = _intent(forecast)
    execution = _execution(forecast, intent)

    journal.append_forecast(forecast)
    journal.append_intent(intent)
    assert (
        journal.append_execution(execution)
        is WC2CohortAppendDisposition.INSERTED
    )
    assert (
        journal.append_execution(execution)
        is WC2CohortAppendDisposition.IDEMPOTENT
    )

    assert execution.cost_evidence_identity == canonical_sha256(
        {
            "fee_usdt": Decimal("0.10"),
            "fill_identity": execution.fill_identity,
            "spread_usdt": Decimal("0.20"),
            "slippage_usdt": Decimal("0.30"),
            "execution_policy_version": "paper-execution-v1",
            "venue_reference": "simulated-bybit-reference",
        }
    )
    assert journal.verify_read_only().execution_count == 1


def test_wc2_execution_rejects_unknown_or_wrong_intent(tmp_path: Path) -> None:
    journal = WC2CohortJournal(tmp_path / "wc2-cohort.sqlite3")
    forecast = _forecast()
    intent = _intent(forecast)
    execution = _execution(forecast, intent)

    journal.append_forecast(forecast)
    with pytest.raises(ValueError, match="unknown intent"):
        journal.append_execution(execution)

    journal.append_intent(intent)
    wrong = replace(
        execution,
        paper_intent_identity=_sha("d"),
    )
    with pytest.raises(ValueError, match="lineage conflict"):
        journal.append_execution(wrong)


def test_wc2_resolution_is_append_only_and_unresolved_is_retained(
    tmp_path: Path,
) -> None:
    journal = WC2CohortJournal(tmp_path / "wc2-cohort.sqlite3")
    forecast = _forecast()
    resolution = _resolution(forecast)

    journal.append_forecast(forecast)
    assert journal.verify_read_only().unresolved_forecast_count == 1

    assert (
        journal.append_resolution(resolution)
        is WC2CohortAppendDisposition.INSERTED
    )
    assert (
        journal.append_resolution(resolution)
        is WC2CohortAppendDisposition.IDEMPOTENT
    )
    status = journal.verify_read_only()
    assert status.resolution_count == 1
    assert status.unresolved_forecast_count == 0

    fork = replace(
        resolution,
        resolution_link_identity=_sha("d"),
        resolution_identity=_sha("e"),
        state=ForecastResolutionState.INVALIDATED,
    )
    with pytest.raises(ValueError, match="resolution conflict"):
        journal.append_resolution(fork)


def test_wc2_resolution_rejects_non_untouched_evidence() -> None:
    forecast = _forecast()
    resolution = SimpleNamespace(
        forecast_identity=forecast.forecast_identity,
        signal_freeze_identity=forecast.signal_freeze_identity,
        evidence_class=EvidenceClass.RETROSPECTIVE,
        evaluated_at_ms=3_000,
        resolution_identity=_sha("b"),
        source_outcome_identity=_sha("c"),
        state=ForecastResolutionState.HIT_TARGET,
    )

    with pytest.raises(ValueError, match="LIVE_UNTOUCHED_FORWARD"):
        build_wc2_cohort_resolution(
            forecast,
            resolution,
            indexed_at_ms=3_100,
        )


def test_wc2_journal_rejects_mutation_and_non_wc2_tables(tmp_path: Path) -> None:
    path = tmp_path / "wc2-cohort.sqlite3"
    journal = WC2CohortJournal(path)
    forecast = _forecast()
    journal.append_forecast(forecast)

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable WC2"):
            db.execute(
                "UPDATE wc2_cohort_forecasts SET symbol='ETHUSDT'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable WC2"):
            db.execute("DELETE FROM wc2_cohort_forecasts")

    other = tmp_path / "mixed.sqlite3"
    with sqlite3.connect(other) as db:
        db.execute("CREATE TABLE canonical_money(id INTEGER)")

    with pytest.raises(ValueError, match="non-WC2"):
        WC2CohortJournal(other).initialize()
