from __future__ import annotations

from pathlib import Path

import pytest
from test_immutable_ledger import build_bundle, candles
from test_wc2_live_source_adapter import _bundle as directional_bundle

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.live_untouched_forward_operational import (
    WC2_LIVE_SOURCE_ADAPTER_VERSION,
)
from crypto_signal.evaluation.live_untouched_forward_runtime import (
    WC2LiveIndexStatus,
    process_wc2_live_freeze,
)
from crypto_signal.evaluation.untouched_forward_journal import WC2CohortJournal
from crypto_signal.evaluation.untouched_forward_policy import (
    build_wc2_untouched_forward_policy,
)
from crypto_signal.ledger.coverage import (
    LiveCoverageContext,
    LiveCoverageSourceStrategy,
)
from crypto_signal.ledger.live_clock import (
    LiveFreezeResult,
    LiveFreezeStatus,
)
from crypto_signal.ledger.store import ImmutableSignalLedger

PROTOCOL_IDENTITY = "c" * 64


class FailingCohortJournal(WC2CohortJournal):
    def append_forecast(self, record):
        raise RuntimeError("forced cohort append crash")


def _context(bundle):
    signal = bundle.signal_decision
    return LiveCoverageContext(
        exchange=signal.exchange,
        market_type=signal.market_type,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        source_strategy=LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M,
    )


def _policy(bundle, *, collection_offset_ms: int = -1_000):
    as_of = bundle.signal_decision.as_of_ms
    collection_start = as_of + collection_offset_ms
    return build_wc2_untouched_forward_policy(
        preregistered_at_ms=collection_start - 1_000,
        collection_start_ms=collection_start,
    )


def _fresh_result(bundle, *, frozen_at_ms: int) -> LiveFreezeResult:
    signal = bundle.signal_decision
    return LiveFreezeResult(
        status=LiveFreezeStatus.FROZEN,
        source_cutoff_open_time_ms=bundle.source_cutoff_open_time_ms,
        signal_freeze_identity=signal.freeze_identity,
        bundle_identity=bundle.bundle_identity,
        signal_state=signal.state,
        confluence_score=str(signal.agreement.confluence_score),
        lifecycle_disposition=None,
        bundle=bundle,
        frozen_at_ms=frozen_at_ms,
    )


def _replay_result(bundle) -> LiveFreezeResult:
    return LiveFreezeResult(
        status=LiveFreezeStatus.ALREADY_FROZEN,
        source_cutoff_open_time_ms=bundle.source_cutoff_open_time_ms,
        signal_freeze_identity=None,
        bundle_identity=None,
        signal_state=None,
        confluence_score=None,
        lifecycle_disposition=None,
    )


def _persist_source(
    ledger: ImmutableSignalLedger,
    bundle,
    *,
    frozen_at_ms: int,
) -> None:
    ledger.freeze(bundle, frozen_at_ms=frozen_at_ms)


def test_fresh_wc2_cycle_persists_r20_and_cohort_with_source_version(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    observed_at = frozen_at + 20
    signal_ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(signal_ledger, bundle, frozen_at_ms=frozen_at)
    decision = ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3")
    cohort = WC2CohortJournal(tmp_path / "cohort.sqlite3")

    result = process_wc2_live_freeze(
        _fresh_result(bundle, frozen_at_ms=frozen_at),
        context=_context(bundle),
        signal_ledger=signal_ledger,
        policy=_policy(bundle),
        decision_ledger=decision,
        cohort_journal=cohort,
        observed_at_ms=observed_at,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        collection_protocol_identity=PROTOCOL_IDENTITY,
    )

    assert result.status is WC2LiveIndexStatus.INDEXED_FRESH
    assert result.historical_forecast_created is False
    assert result.real_capital == 0
    assert decision.read_status().forecast_count == 1
    status = cohort.verify_read_only()
    assert status.forecast_count == 1
    assert status.unresolved_forecast_count == 1

    persisted = decision.read_issuance_for_signal(signal.freeze_identity)
    assert persisted is not None
    forecast, proof = persisted
    assert proof["forecast_identity"] == forecast["forecast_identity"]
    version_refs = {
        item["component"]: item["version"]
        for item in forecast["version_refs"]
    }
    assert (
        version_refs["wc2_live_source_adapter"]
        == WC2_LIVE_SOURCE_ADAPTER_VERSION
    )
    assert version_refs["wc2_collection_protocol"] == PROTOCOL_IDENTITY


def test_fresh_wc2_cycle_before_collection_creates_no_r20_or_cohort(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    observed_at = frozen_at + 20
    policy = _policy(bundle, collection_offset_ms=10_000)
    signal_ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(signal_ledger, bundle, frozen_at_ms=frozen_at)
    decision_path = tmp_path / "decision.sqlite3"
    cohort_path = tmp_path / "cohort.sqlite3"

    result = process_wc2_live_freeze(
        _fresh_result(bundle, frozen_at_ms=frozen_at),
        context=_context(bundle),
        signal_ledger=signal_ledger,
        policy=policy,
        decision_ledger=ImmutableDecisionEvidenceLedger(decision_path),
        cohort_journal=WC2CohortJournal(cohort_path),
        observed_at_ms=observed_at,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        collection_protocol_identity=PROTOCOL_IDENTITY,
    )

    assert result.status is WC2LiveIndexStatus.SKIPPED_BEFORE_COLLECTION
    assert not decision_path.exists()
    assert not cohort_path.exists()


def test_neutral_fresh_source_creates_no_r20_or_cohort(tmp_path: Path) -> None:
    bundle = build_bundle(candles())
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    signal_ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(signal_ledger, bundle, frozen_at_ms=frozen_at)
    decision_path = tmp_path / "decision.sqlite3"
    cohort_path = tmp_path / "cohort.sqlite3"

    result = process_wc2_live_freeze(
        _fresh_result(bundle, frozen_at_ms=frozen_at),
        context=_context(bundle),
        signal_ledger=signal_ledger,
        policy=_policy(bundle),
        decision_ledger=ImmutableDecisionEvidenceLedger(decision_path),
        cohort_journal=WC2CohortJournal(cohort_path),
        observed_at_ms=frozen_at + 20,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        collection_protocol_identity=PROTOCOL_IDENTITY,
    )

    assert result.status is WC2LiveIndexStatus.SKIPPED_INELIGIBLE_SOURCE
    assert not decision_path.exists()
    assert not cohort_path.exists()


def test_replay_without_persisted_r20_never_backfills_forecast(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    signal_ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(signal_ledger, bundle, frozen_at_ms=frozen_at)
    decision_path = tmp_path / "decision.sqlite3"
    cohort_path = tmp_path / "cohort.sqlite3"

    result = process_wc2_live_freeze(
        _replay_result(bundle),
        context=_context(bundle),
        signal_ledger=signal_ledger,
        policy=_policy(bundle),
        decision_ledger=ImmutableDecisionEvidenceLedger(decision_path),
        cohort_journal=WC2CohortJournal(cohort_path),
        observed_at_ms=frozen_at + 10_000,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        collection_protocol_identity=PROTOCOL_IDENTITY,
    )

    assert result.status is WC2LiveIndexStatus.NO_PERSISTED_ISSUANCE
    assert result.historical_forecast_created is False
    assert not decision_path.exists()
    assert not cohort_path.exists()


def test_crash_after_r20_commit_recovers_cohort_without_new_forecast(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    first_observed = frozen_at + 20
    signal_ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(signal_ledger, bundle, frozen_at_ms=frozen_at)
    decision = ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3")
    failing = FailingCohortJournal(tmp_path / "cohort.sqlite3")
    policy = _policy(bundle)

    with pytest.raises(RuntimeError, match="forced cohort append crash"):
        process_wc2_live_freeze(
            _fresh_result(bundle, frozen_at_ms=frozen_at),
            context=_context(bundle),
            signal_ledger=signal_ledger,
            policy=policy,
            decision_ledger=decision,
            cohort_journal=failing,
            observed_at_ms=first_observed,
            maximum_issuance_delay_ms=100,
            horizon_bars=4,
            base_asset="BTC",
        )

    assert decision.read_status().forecast_count == 1
    assert not failing.path.exists()

    cohort = WC2CohortJournal(tmp_path / "cohort.sqlite3")
    recovered = process_wc2_live_freeze(
        _replay_result(bundle),
        context=_context(bundle),
        signal_ledger=signal_ledger,
        policy=policy,
        decision_ledger=decision,
        cohort_journal=cohort,
        observed_at_ms=first_observed + 10_000,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        collection_protocol_identity=PROTOCOL_IDENTITY,
    )

    assert recovered.status is WC2LiveIndexStatus.INDEXED_RECOVERED
    assert recovered.historical_forecast_created is False
    assert decision.read_status().forecast_count == 1
    assert cohort.verify_read_only().forecast_count == 1

    replayed = process_wc2_live_freeze(
        _replay_result(bundle),
        context=_context(bundle),
        signal_ledger=signal_ledger,
        policy=policy,
        decision_ledger=decision,
        cohort_journal=cohort,
        observed_at_ms=first_observed + 20_000,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        collection_protocol_identity=PROTOCOL_IDENTITY,
    )
    assert replayed.status is WC2LiveIndexStatus.ALREADY_INDEXED
    assert replayed.cohort_forecast_identity == (
        recovered.cohort_forecast_identity
    )
    assert decision.read_status().forecast_count == 1
    assert cohort.verify_read_only().forecast_count == 1


def test_retry_of_same_fresh_result_uses_persisted_r20_not_second_issuance(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    signal_ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(signal_ledger, bundle, frozen_at_ms=frozen_at)
    decision = ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3")
    cohort = WC2CohortJournal(tmp_path / "cohort.sqlite3")
    policy = _policy(bundle)

    first = process_wc2_live_freeze(
        _fresh_result(bundle, frozen_at_ms=frozen_at),
        context=_context(bundle),
        signal_ledger=signal_ledger,
        policy=policy,
        decision_ledger=decision,
        cohort_journal=cohort,
        observed_at_ms=frozen_at + 20,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        collection_protocol_identity=PROTOCOL_IDENTITY,
    )
    second = process_wc2_live_freeze(
        _fresh_result(bundle, frozen_at_ms=frozen_at),
        context=_context(bundle),
        signal_ledger=signal_ledger,
        policy=policy,
        decision_ledger=decision,
        cohort_journal=cohort,
        observed_at_ms=frozen_at + 90,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        collection_protocol_identity=PROTOCOL_IDENTITY,
    )

    assert first.status is WC2LiveIndexStatus.INDEXED_FRESH
    assert second.status is WC2LiveIndexStatus.ALREADY_INDEXED
    assert second.forecast_identity == first.forecast_identity
    assert decision.read_status().forecast_count == 1
    assert cohort.verify_read_only().forecast_count == 1
