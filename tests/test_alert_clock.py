from __future__ import annotations

import hashlib
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.alerts.clock import (
    AlertClockSourceError,
    materialize_alert_events,
)
from crypto_signal.alerts.models import AlertSourceKind
from crypto_signal.alerts.store import AlertOutbox
from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.signals.models import (
    EntryReferenceModel,
    HistoricalStatsStatus,
    LifecycleEvaluationStatus,
    LifecycleTransitionReason,
    MethodologyVersionRef,
    ProbabilityStatus,
    RiskRewardTarget,
    SignalAgreementSummary,
    SignalDecision,
    SignalDirection,
    SignalGeometry,
    SignalLifecycleEvaluation,
    SignalState,
    SignalStateTransition,
)


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def decision(
    seed: str,
    *,
    state: SignalState,
) -> SignalDecision:
    geometry: SignalGeometry | None = None
    if state is SignalState.ACTIVE:
        geometry = SignalGeometry(
            source_evidence_id=f"harmonic-{seed}",
            source_methodology=MethodologyKind.HARMONIC,
            entry_zone=PriceZone(Decimal(100), Decimal(102)),
            entry_reference_price=Decimal(101),
            entry_reference_model=(
                EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
            ),
            invalidation_price=Decimal(90),
            invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
            targets=(
                RiskRewardTarget(
                    label="target_1",
                    target_price=Decimal(110),
                    reference_rr=Decimal(1),
                ),
            ),
        )
    return SignalDecision(
        freeze_identity=digest(f"signal-{seed}"),
        signal_version="signal-v1/1",
        state=state,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=1_000,
        direction=SignalDirection.BULLISH,
        setup_type=(
            "gartley"
            if state is SignalState.ACTIVE
            else "confluence_watch"
        ),
        geometry=geometry,
        agreement=SignalAgreementSummary(
            confluence_score=Decimal("66.67"),
            score_semantic=ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY,
            support_method_count=2,
            opposing_method_count=0,
            resolved_method_count=2,
            total_methodology_slots=3,
            pairwise_relations=(),
        ),
        selected_evidence_ids=(f"evidence-{seed}",),
        methodology_versions=(
            MethodologyVersionRef(
                methodology=MethodologyKind.HARMONIC,
                version="harmonic-v1/1",
            ),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=(),
        evidence_summary=(),
    )


def invalidated(
    item: SignalDecision,
) -> SignalLifecycleEvaluation:
    transition = SignalStateTransition(
        transition_identity=digest(
            f"transition-{item.freeze_identity}"
        ),
        signal_freeze_identity=item.freeze_identity,
        from_state=item.state,
        to_state=SignalState.INVALIDATED,
        reason=LifecycleTransitionReason.INVALIDATION_TOUCH_OR_CROSS,
        trigger_candle_identity=(
            "bybit",
            "spot",
            "BTCUSDT",
            "15m",
            1_800,
        ),
        market_confirmed_at_ms=2_699,
        observed_at_ms=2_700,
        evaluated_as_of_ms=3_000,
        first_trigger_candle_certain=True,
    )
    return SignalLifecycleEvaluation(
        signal_freeze_identity=item.freeze_identity,
        evaluated_as_of_ms=3_000,
        current_state=SignalState.INVALIDATED,
        status=LifecycleEvaluationStatus.COMPLETE,
        missing_open_times_ms=(),
        skipped_partial_decision_bucket=True,
        transition=transition,
    )


def create_source(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE signal_freezes (
                signal_freeze_identity TEXT NOT NULL,
                as_of_ms INTEGER NOT NULL,
                signal_state TEXT NOT NULL,
                bundle_json TEXT NOT NULL,
                frozen_at_ms INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE lifecycle_evaluations (
                evaluation_identity TEXT NOT NULL,
                signal_freeze_identity TEXT NOT NULL,
                evaluated_as_of_ms INTEGER NOT NULL,
                current_state TEXT NOT NULL,
                status TEXT NOT NULL,
                evaluation_json TEXT NOT NULL,
                appended_at_ms INTEGER NOT NULL
            )
            """
        )


def insert_signal(
    path: Path,
    item: SignalDecision,
    *,
    frozen_at_ms: int = 1_100,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO signal_freezes (
                signal_freeze_identity,
                as_of_ms,
                signal_state,
                bundle_json,
                frozen_at_ms
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                item.freeze_identity,
                item.as_of_ms,
                item.state.value,
                canonical_json({"signal_decision": item}),
                frozen_at_ms,
            ),
        )


def insert_lifecycle(
    path: Path,
    item: SignalLifecycleEvaluation,
    *,
    appended_at_ms: int = 3_100,
    identity: str | None = None,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO lifecycle_evaluations (
                evaluation_identity,
                signal_freeze_identity,
                evaluated_as_of_ms,
                current_state,
                status,
                evaluation_json,
                appended_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_sha256(item) if identity is None else identity,
                item.signal_freeze_identity,
                item.evaluated_as_of_ms,
                item.current_state.value,
                item.status.value,
                canonical_json(item),
                appended_at_ms,
            ),
        )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_clock_materializes_active_and_invalidation_events(
    tmp_path: Path,
) -> None:
    source = tmp_path / "signals.sqlite3"
    create_source(source)
    active = decision("active", state=SignalState.ACTIVE)
    watch = decision("watch", state=SignalState.WATCH)
    insert_signal(source, active)
    insert_signal(source, watch, frozen_at_ms=1_200)
    insert_lifecycle(source, invalidated(watch))

    outbox = AlertOutbox(tmp_path / "alerts.sqlite3")
    result = materialize_alert_events(source, outbox)

    assert result.signal_rows == 2
    assert result.lifecycle_rows == 1
    assert result.eligible_events == 2
    assert result.inserted_events == 2
    assert result.unchanged_events == 0
    events = tuple(record.event for record in outbox.list_events())
    assert {event.source_kind for event in events} == {
        AlertSourceKind.INITIAL_SIGNAL,
        AlertSourceKind.LIFECYCLE_TRANSITION,
    }


def test_repeated_clock_run_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "signals.sqlite3"
    create_source(source)
    active = decision("repeat", state=SignalState.ACTIVE)
    insert_signal(source, active)
    outbox = AlertOutbox(tmp_path / "alerts.sqlite3")

    first = materialize_alert_events(source, outbox)
    second = materialize_alert_events(source, outbox)

    assert first.inserted_events == 1
    assert first.unchanged_events == 0
    assert second.inserted_events == 0
    assert second.unchanged_events == 1
    assert outbox.count_events() == 1


def test_watch_only_source_has_no_default_initial_alert(
    tmp_path: Path,
) -> None:
    source = tmp_path / "signals.sqlite3"
    create_source(source)
    insert_signal(source, decision("watch-only", state=SignalState.WATCH))
    outbox = AlertOutbox(tmp_path / "alerts.sqlite3")

    result = materialize_alert_events(source, outbox)

    assert result.signal_rows == 1
    assert result.eligible_events == 0
    assert result.inserted_events == 0
    assert outbox.count_events() == 0


def test_clock_does_not_mutate_source_ledger(tmp_path: Path) -> None:
    source = tmp_path / "signals.sqlite3"
    create_source(source)
    insert_signal(source, decision("readonly", state=SignalState.ACTIVE))
    before = file_sha256(source)
    outbox = AlertOutbox(tmp_path / "alerts.sqlite3")

    materialize_alert_events(source, outbox)

    after = file_sha256(source)
    assert after == before
    with sqlite3.connect(source) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert tables == {"signal_freezes", "lifecycle_evaluations"}


def test_tampered_lifecycle_identity_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "signals.sqlite3"
    create_source(source)
    watch = decision("tamper", state=SignalState.WATCH)
    insert_signal(source, watch)
    insert_lifecycle(
        source,
        invalidated(watch),
        identity="0" * 64,
    )

    with pytest.raises(
        AlertClockSourceError,
        match="lifecycle evaluation identity mismatch",
    ):
        materialize_alert_events(
            source,
            AlertOutbox(tmp_path / "alerts.sqlite3"),
        )


def test_signal_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "signals.sqlite3"
    create_source(source)
    item = decision("signal-mismatch", state=SignalState.ACTIVE)
    insert_signal(source, item)
    with sqlite3.connect(source) as connection:
        connection.execute(
            "UPDATE signal_freezes SET signal_freeze_identity=?",
            (digest("different"),),
        )

    with pytest.raises(
        AlertClockSourceError,
        match="signal freeze identity mismatch",
    ):
        materialize_alert_events(
            source,
            AlertOutbox(tmp_path / "alerts.sqlite3"),
        )


def test_missing_required_source_table_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "signals.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE signal_freezes (x INTEGER)")

    with pytest.raises(
        AlertClockSourceError,
        match="missing required table: lifecycle_evaluations",
    ):
        materialize_alert_events(
            source,
            AlertOutbox(tmp_path / "alerts.sqlite3"),
        )
