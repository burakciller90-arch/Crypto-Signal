from __future__ import annotations

from pathlib import Path

import pytest
from test_immutable_ledger import build_bundle, candles
from test_r22_intent_preview import _activation
from test_wc2_live_source_adapter import _bundle as directional_bundle

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.untouched_forward_journal import WC2CohortJournal
from crypto_signal.evaluation.untouched_forward_policy import (
    build_wc2_untouched_forward_policy,
)
from crypto_signal.evaluation.untouched_forward_prepared import (
    WC2PreparedCycleJournal,
)
from crypto_signal.evaluation.untouched_forward_prepared_runtime import (
    WC2PreparedLiveStatus,
    process_wc2_prepared_live_freeze,
)
from crypto_signal.ledger.coverage import (
    LiveCoverageContext,
    LiveCoverageSourceStrategy,
)
from crypto_signal.ledger.live_clock import LiveFreezeResult, LiveFreezeStatus
from crypto_signal.ledger.store import ImmutableSignalLedger
from crypto_signal.paper.epoch2_accounting import build_epoch2_activation_record
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal


class FailingDecisionLedger(ImmutableDecisionEvidenceLedger):
    def append_issuance_bundle(self, forecast, proof, event):
        raise RuntimeError("forced R20 persistence crash")


def _context(bundle) -> LiveCoverageContext:
    signal = bundle.signal_decision
    return LiveCoverageContext(
        exchange=signal.exchange,
        market_type=signal.market_type,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        source_strategy=LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M,
    )


def _policy(bundle, *, collection_offset_ms: int = -1_000):
    start = bundle.signal_decision.as_of_ms + collection_offset_ms
    return build_wc2_untouched_forward_policy(
        preregistered_at_ms=start - 1_000,
        collection_start_ms=start,
    )


def _fresh(bundle, frozen_at_ms: int) -> LiveFreezeResult:
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


def _replay(bundle) -> LiveFreezeResult:
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


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "prepared": tmp_path / "cycle.wc2-prepared.sqlite3",
        "decision": tmp_path / "decision.sqlite3",
        "cohort": tmp_path / "cohort.sqlite3",
        "shadow": tmp_path / "cycle.shadow-intent.sqlite3",
        "manifest": tmp_path / "cycle.shadow-cycle.sqlite3",
    }


def _call(
    result: LiveFreezeResult,
    *,
    bundle,
    signal_ledger: ImmutableSignalLedger,
    policy,
    activation,
    paths: dict[str, Path],
    observed_at_ms: int,
    decision_ledger: ImmutableDecisionEvidenceLedger | None = None,
    collection_start_ms: int | None = None,
):
    return process_wc2_prepared_live_freeze(
        result,
        context=_context(bundle),
        signal_ledger=signal_ledger,
        policy=policy,
        activation=activation,
        prepared_journal=WC2PreparedCycleJournal(paths["prepared"]),
        decision_ledger=(
            decision_ledger
            if decision_ledger is not None
            else ImmutableDecisionEvidenceLedger(paths["decision"])
        ),
        cohort_journal=WC2CohortJournal(paths["cohort"]),
        shadow_journal=R25ShadowIntentJournal(paths["shadow"]),
        shadow_manifest=R25ShadowCycleManifest(paths["manifest"]),
        observed_at_ms=observed_at_ms,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        collection_start_ms=collection_start_ms,
    )


def test_fresh_prepared_cycle_persists_receipt_forecast_and_hold_cash(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    observed_at = frozen_at + 20
    paths = _paths(tmp_path)
    ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(ledger, bundle, frozen_at_ms=frozen_at)

    result = _call(
        _fresh(bundle, frozen_at),
        bundle=bundle,
        signal_ledger=ledger,
        policy=_policy(bundle),
        activation=_activation(),
        paths=paths,
        observed_at_ms=observed_at,
    )

    assert result.status is WC2PreparedLiveStatus.COMPLETED_FRESH
    assert result.receipt_identity is not None
    assert result.forecast_identity is not None
    assert result.cohort_forecast_identity is not None
    assert result.paper_intent_identity is not None
    assert result.historical_market_read_performed is False
    assert result.historical_backfill_authority is False
    assert result.canonical_epoch2_mutation is False
    assert result.production_authority is False
    assert result.real_capital == 0
    assert WC2PreparedCycleJournal(paths["prepared"]).verify_read_only() == 1
    assert (
        ImmutableDecisionEvidenceLedger(paths["decision"])
        .read_status()
        .forecast_count
        == 1
    )
    cohort = WC2CohortJournal(paths["cohort"]).verify_read_only()
    assert cohort.forecast_count == 1
    assert cohort.intent_count == 1
    assert cohort.execution_count == 0
    assert cohort.resolution_count == 0
    assert R25ShadowIntentJournal(paths["shadow"]).verify_read_only().record_count == 1
    assert R25ShadowCycleManifest(paths["manifest"]).verify_read_only().record_count == 1


def test_exact_replay_uses_receipt_and_is_idempotent_without_market_read(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    observed_at = frozen_at + 20
    paths = _paths(tmp_path)
    ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(ledger, bundle, frozen_at_ms=frozen_at)
    policy = _policy(bundle)
    activation = _activation()

    first = _call(
        _fresh(bundle, frozen_at),
        bundle=bundle,
        signal_ledger=ledger,
        policy=policy,
        activation=activation,
        paths=paths,
        observed_at_ms=observed_at,
    )
    replay = _call(
        _replay(bundle),
        bundle=bundle,
        signal_ledger=ledger,
        policy=policy,
        activation=activation,
        paths=paths,
        observed_at_ms=observed_at + 50_000,
    )

    assert replay.status is WC2PreparedLiveStatus.COMPLETED_RECOVERED
    assert replay.receipt_identity == first.receipt_identity
    assert replay.forecast_identity == first.forecast_identity
    assert replay.cohort_forecast_identity == first.cohort_forecast_identity
    assert replay.paper_intent_identity == first.paper_intent_identity
    assert replay.historical_market_read_performed is False
    assert WC2PreparedCycleJournal(paths["prepared"]).verify_read_only() == 1
    assert (
        ImmutableDecisionEvidenceLedger(paths["decision"])
        .read_status()
        .forecast_count
        == 1
    )
    cohort = WC2CohortJournal(paths["cohort"]).verify_read_only()
    assert cohort.forecast_count == 1
    assert cohort.intent_count == 1
    assert cohort.execution_count == 0


def test_receipt_is_durable_before_r20_persistence_is_attempted(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    observed_at = frozen_at + 20
    paths = _paths(tmp_path)
    ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(ledger, bundle, frozen_at_ms=frozen_at)

    with pytest.raises(RuntimeError, match="forced R20 persistence crash"):
        _call(
            _fresh(bundle, frozen_at),
            bundle=bundle,
            signal_ledger=ledger,
            policy=_policy(bundle),
            activation=_activation(),
            paths=paths,
            observed_at_ms=observed_at,
            decision_ledger=FailingDecisionLedger(paths["decision"]),
        )

    prepared = WC2PreparedCycleJournal(paths["prepared"])
    assert prepared.verify_read_only() == 1
    assert prepared.read_for_signal(signal.freeze_identity) is not None
    assert not paths["decision"].exists()
    assert not paths["cohort"].exists()
    assert not paths["shadow"].exists()
    assert not paths["manifest"].exists()


def test_post_activation_replay_without_receipt_never_backfills(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    paths = _paths(tmp_path)
    ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(ledger, bundle, frozen_at_ms=frozen_at)

    result = _call(
        _replay(bundle),
        bundle=bundle,
        signal_ledger=ledger,
        policy=_policy(bundle),
        activation=_activation(),
        paths=paths,
        observed_at_ms=frozen_at + 10_000,
    )

    assert result.status is WC2PreparedLiveStatus.NO_PREPARED_RECEIPT
    assert result.forecast_identity is None
    assert result.historical_market_read_performed is False
    assert result.historical_backfill_authority is False
    assert not paths["prepared"].exists()
    assert not paths["decision"].exists()
    assert not paths["cohort"].exists()
    assert not paths["shadow"].exists()
    assert not paths["manifest"].exists()


def test_pre_activation_replay_is_expected_skip_not_receipt_gap(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    paths = _paths(tmp_path)
    ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(ledger, bundle, frozen_at_ms=frozen_at)
    base = _activation()
    activation = build_epoch2_activation_record(
        activated_at_ms=frozen_at + 100,
        epoch1_ledger_sha256=base.epoch1_ledger_sha256,
    )

    result = _call(
        _replay(bundle),
        bundle=bundle,
        signal_ledger=ledger,
        policy=_policy(bundle),
        activation=activation,
        paths=paths,
        observed_at_ms=frozen_at + 10_000,
    )

    assert result.status is WC2PreparedLiveStatus.SKIPPED_BEFORE_ACTIVATION
    assert result.receipt_identity is None
    assert not paths["prepared"].exists()
    assert not paths["decision"].exists()
    assert not paths["cohort"].exists()


def test_operational_collection_boundary_blocks_fresh_before_protocol_start(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    observed_at = frozen_at + 20
    protocol_start = observed_at + 1_000
    paths = _paths(tmp_path)
    ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(ledger, bundle, frozen_at_ms=frozen_at)

    result = _call(
        _fresh(bundle, frozen_at),
        bundle=bundle,
        signal_ledger=ledger,
        policy=_policy(bundle),
        activation=_activation(),
        paths=paths,
        observed_at_ms=observed_at,
        collection_start_ms=protocol_start,
    )

    assert result.status is WC2PreparedLiveStatus.SKIPPED_BEFORE_COLLECTION
    assert result.receipt_identity is None
    assert not paths["prepared"].exists()
    assert not paths["decision"].exists()
    assert not paths["cohort"].exists()
    assert not paths["shadow"].exists()
    assert not paths["manifest"].exists()


def test_operational_collection_boundary_blocks_replay_before_protocol_start(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    paths = _paths(tmp_path)
    ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(ledger, bundle, frozen_at_ms=frozen_at)

    result = _call(
        _replay(bundle),
        bundle=bundle,
        signal_ledger=ledger,
        policy=_policy(bundle),
        activation=_activation(),
        paths=paths,
        observed_at_ms=frozen_at + 10_000,
        collection_start_ms=frozen_at + 1,
    )

    assert result.status is WC2PreparedLiveStatus.SKIPPED_BEFORE_COLLECTION
    assert result.receipt_identity is None
    assert not paths["prepared"].exists()
    assert not paths["decision"].exists()
    assert not paths["cohort"].exists()


def test_operational_collection_boundary_cannot_predate_review_policy(
    tmp_path: Path,
) -> None:
    bundle = directional_bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    policy = _policy(bundle)
    paths = _paths(tmp_path)
    ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(ledger, bundle, frozen_at_ms=frozen_at)

    with pytest.raises(ValueError, match="cannot predate review-policy"):
        _call(
            _fresh(bundle, frozen_at),
            bundle=bundle,
            signal_ledger=ledger,
            policy=policy,
            activation=_activation(),
            paths=paths,
            observed_at_ms=frozen_at + 20,
            collection_start_ms=policy.collection_start_ms - 1,
        )

    assert not paths["prepared"].exists()
    assert not paths["decision"].exists()
    assert not paths["cohort"].exists()


def test_ineligible_fresh_source_creates_no_wc2_runtime_evidence(
    tmp_path: Path,
) -> None:
    bundle = build_bundle(candles())
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    paths = _paths(tmp_path)
    ledger = ImmutableSignalLedger(tmp_path / "signal.sqlite3")
    _persist_source(ledger, bundle, frozen_at_ms=frozen_at)

    result = _call(
        _fresh(bundle, frozen_at),
        bundle=bundle,
        signal_ledger=ledger,
        policy=_policy(bundle),
        activation=_activation(),
        paths=paths,
        observed_at_ms=frozen_at + 20,
    )

    assert result.status is WC2PreparedLiveStatus.SKIPPED_INELIGIBLE_SOURCE
    assert not paths["prepared"].exists()
    assert not paths["decision"].exists()
    assert not paths["cohort"].exists()
    assert not paths["shadow"].exists()
    assert not paths["manifest"].exists()
