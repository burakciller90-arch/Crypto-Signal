from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from test_wc2_live_source_adapter import _bundle as directional_bundle

from crypto_signal.data.models import Candle, DataSource
from crypto_signal.data.store import CandleStore
from crypto_signal.data.timeframes import bucket_open_ms, spec
from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.live_untouched_forward_operational import (
    issue_same_cycle_untouched_forward_forecast,
)
from crypto_signal.evaluation.untouched_forward_journal import (
    WC2CohortJournal,
    build_wc2_cohort_forecast,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    build_wc2_untouched_forward_policy,
)
from crypto_signal.evaluation.untouched_forward_resolution_runtime import (
    resolve_wc2_outcomes_once,
)
from crypto_signal.forecast_stream import build_forecast_resolution
from crypto_signal.ledger.store import ImmutableSignalLedger
from crypto_signal.outcomes.evaluator import evaluate_outcome
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeResolutionStatus,
    OutcomeState,
)
from crypto_signal.signals.models import SignalDirection


def _first_full_open(as_of_ms: int, timeframe: str) -> int:
    duration = spec(timeframe).duration_ms
    bucket = bucket_open_ms(as_of_ms, timeframe)
    return bucket + duration if bucket < as_of_ms else bucket


def _invalidating_candle(bundle) -> Candle:
    decision = bundle.signal_decision
    assert decision.geometry is not None
    assert decision.timeframe == "15m"
    duration = spec("15m").duration_ms
    open_time = _first_full_open(decision.as_of_ms, "15m")
    close_time = open_time + duration - 1

    if decision.direction is SignalDirection.BULLISH:
        high = decision.geometry.entry_reference_price - Decimal("1")
        low = decision.geometry.invalidation_price - Decimal("1")
    else:
        low = decision.geometry.entry_reference_price + Decimal("1")
        high = decision.geometry.invalidation_price + Decimal("1")
    close = (high + low) / Decimal("2")

    return Candle(
        exchange=decision.exchange,
        market_type=decision.market_type,
        symbol=decision.symbol,
        timeframe="15m",
        open_time_ms=open_time,
        close_time_ms=close_time,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=Decimal("1"),
        quote_volume=Decimal("1000"),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=close_time + 1,
        ingested_at_ms=close_time + 2,
        adapter_version="wc2-outcome-test/1",
    )


def _fixture(tmp_path: Path):
    bundle = directional_bundle()
    signal = bundle.signal_decision
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=signal.as_of_ms - 2_000,
        collection_start_ms=signal.as_of_ms - 1_000,
    )
    frozen_at = signal.as_of_ms + 10
    issued_at = frozen_at + 20

    signal_ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    signal_ledger.freeze(bundle, frozen_at_ms=frozen_at)

    decision = ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3")
    issuance = issue_same_cycle_untouched_forward_forecast(
        bundle,
        frozen_at_ms=frozen_at,
        issued_at_ms=issued_at,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset=signal.symbol.removesuffix("USDT"),
        ledger=decision,
    )
    cohort = WC2CohortJournal(tmp_path / "cohort.sqlite3")
    cohort_forecast = build_wc2_cohort_forecast(
        policy=policy,
        issuance=issuance,
        indexed_at_ms=issued_at + 1,
    )
    cohort.append_forecast(cohort_forecast)

    cache = CandleStore(tmp_path / "candles.sqlite3")
    # Keep the cache physically present even before post-decision evidence arrives.
    cache.upsert(bundle.candles[-1])
    return bundle, signal_ledger, decision, cohort, cache, issuance


def test_wc2_outcome_resolver_persists_terminal_live_outcome_and_resolution(
    tmp_path: Path,
) -> None:
    bundle, signal_ledger, decision, cohort, cache, _ = _fixture(tmp_path)
    candle = _invalidating_candle(bundle)
    cache.upsert(candle)

    result = resolve_wc2_outcomes_once(
        signal_ledger=signal_ledger,
        candle_store=cache,
        decision_ledger=decision,
        cohort_journal=cohort,
        observed_at_ms=candle.ingested_at_ms,
    )

    assert result.scanned == 1
    assert result.resolved_fresh == 1
    assert result.pending == 0
    assert result.recovered == 0
    assert result.historical_backfill_performed is False
    assert result.real_capital == 0

    outcomes = signal_ledger.list_outcome_evaluations(
        bundle.signal_decision.freeze_identity
    )
    assert len(outcomes) == 1
    assert outcomes[0].evidence_class == EvidenceClass.LIVE_UNTOUCHED_FORWARD.value
    assert outcomes[0].resolution_status == OutcomeResolutionStatus.RESOLVED.value
    assert outcomes[0].outcome_state == OutcomeState.INVALIDATED.value
    assert decision.read_status().resolution_count == 1
    status = cohort.verify_read_only()
    assert status.resolution_count == 1
    assert status.unresolved_forecast_count == 0


def test_wc2_outcome_resolver_does_not_persist_pending_snapshot(
    tmp_path: Path,
) -> None:
    bundle, signal_ledger, decision, cohort, cache, issuance = _fixture(tmp_path)

    result = resolve_wc2_outcomes_once(
        signal_ledger=signal_ledger,
        candle_store=cache,
        decision_ledger=decision,
        cohort_journal=cohort,
        observed_at_ms=issuance.forecast.issued_at_ms + 1,
    )

    assert result.scanned == 1
    assert result.pending == 1
    assert result.resolved_fresh == 0
    assert signal_ledger.count_outcome_evaluations() == 0
    assert decision.read_status().resolution_count == 0
    assert cohort.verify_read_only().unresolved_forecast_count == 1


def test_wc2_outcome_resolver_recovers_from_persisted_closed_outcome(
    tmp_path: Path,
) -> None:
    bundle, signal_ledger, decision, cohort, cache, issuance = _fixture(tmp_path)
    candle = _invalidating_candle(bundle)
    cache.upsert(candle)
    outcome = evaluate_outcome(
        bundle.signal_decision,
        (candle,),
        as_of_ms=candle.ingested_at_ms,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        max_holding_bars=issuance.forecast.horizon_bars,
    )
    assert outcome.resolution_status is OutcomeResolutionStatus.RESOLVED
    signal_ledger.append_outcome_evaluation(
        outcome,
        appended_at_ms=candle.ingested_at_ms,
    )

    result = resolve_wc2_outcomes_once(
        signal_ledger=signal_ledger,
        candle_store=cache,
        decision_ledger=decision,
        cohort_journal=cohort,
        observed_at_ms=candle.ingested_at_ms + 1,
    )

    assert result.recovered == 1
    assert result.resolved_fresh == 0
    assert decision.read_status().resolution_count == 1
    assert cohort.verify_read_only().resolution_count == 1


def test_wc2_outcome_resolver_recovers_cohort_from_persisted_r20_resolution(
    tmp_path: Path,
) -> None:
    bundle, signal_ledger, decision, cohort, cache, issuance = _fixture(tmp_path)
    candle = _invalidating_candle(bundle)
    cache.upsert(candle)
    outcome = evaluate_outcome(
        bundle.signal_decision,
        (candle,),
        as_of_ms=candle.ingested_at_ms,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        max_holding_bars=issuance.forecast.horizon_bars,
    )
    signal_ledger.append_outcome_evaluation(
        outcome,
        appended_at_ms=candle.ingested_at_ms,
    )
    resolution = build_forecast_resolution(issuance.forecast, outcome)
    decision.append_resolution(resolution)

    result = resolve_wc2_outcomes_once(
        signal_ledger=signal_ledger,
        candle_store=cache,
        decision_ledger=decision,
        cohort_journal=cohort,
        observed_at_ms=candle.ingested_at_ms + 1,
    )

    assert result.recovered == 1
    assert decision.read_status().resolution_count == 1
    assert cohort.verify_read_only().resolution_count == 1


def test_wc2_outcome_source_readers_do_not_create_missing_databases(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "missing-signal.sqlite3"
    candle_path = tmp_path / "missing-candles.sqlite3"

    assert ImmutableSignalLedger(signal_path).read_freeze_by_signal("a" * 64) is None
    assert not signal_path.exists()
    with pytest.raises(FileNotFoundError):
        CandleStore(candle_path).list_candles_read_only(
            exchange=directional_bundle().signal_decision.exchange,
            market_type=directional_bundle().signal_decision.market_type,
            symbol="BTCUSDT",
            timeframe="15m",
        )
    assert not candle_path.exists()
