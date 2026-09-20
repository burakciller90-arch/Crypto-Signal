from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.alerts.models import (
    AlertEvent,
    DeliveryAttemptStatus,
    DeliveryResult,
)
from crypto_signal.alerts.planner import plan_initial_alert
from crypto_signal.alerts.store import AlertOutbox
from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.product.models import ProductDataStatus
from crypto_signal.product.reader import DashboardReader
from crypto_signal.product.web import create_app
from crypto_signal.signals.models import (
    EntryReferenceModel,
    HistoricalStatsStatus,
    MethodologyVersionRef,
    ProbabilityStatus,
    RiskRewardTarget,
    SignalAgreementSummary,
    SignalDecision,
    SignalDirection,
    SignalGeometry,
    SignalState,
)


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def active_signal(seed: str) -> SignalDecision:
    return SignalDecision(
        freeze_identity=digest(f"signal-{seed}"),
        signal_version="signal-v1/1",
        state=SignalState.ACTIVE,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=1_000,
        direction=SignalDirection.BULLISH,
        setup_type="gartley",
        geometry=SignalGeometry(
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
        ),
        agreement=SignalAgreementSummary(
            confluence_score=Decimal("66.67"),
            score_semantic=ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY,
            support_method_count=2,
            opposing_method_count=0,
            resolved_method_count=2,
            total_methodology_slots=3,
            pairwise_relations=(),
        ),
        selected_evidence_ids=(f"harmonic-{seed}",),
        methodology_versions=(
            MethodologyVersionRef(
                methodology=MethodologyKind.HARMONIC,
                version="harmonic-v1/1",
            ),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=("partial_methodology_coverage",),
        evidence_summary=(),
    )


def append_event(
    outbox: AlertOutbox,
    seed: str,
    *,
    appended_at_ms: int,
) -> AlertEvent:
    event = plan_initial_alert(active_signal(seed))
    assert event is not None
    outbox.append_event(event, appended_at_ms=appended_at_ms)
    return event


def test_alert_center_missing_outbox_is_explicit_and_read_only(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-alerts.sqlite3"
    reader = DashboardReader(
        tmp_path / "signal.sqlite3",
        alert_outbox_path=missing,
    )

    view = reader.alert_center()

    assert view.status is ProductDataStatus.NO_LEDGER
    assert view.total_count == 0
    assert view.events == ()
    assert not missing.exists()


def test_alert_center_empty_outbox_is_not_fake_alert_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "alerts.sqlite3"
    AlertOutbox(path).initialize()
    reader = DashboardReader(
        tmp_path / "signal.sqlite3",
        alert_outbox_path=path,
    )

    view = reader.alert_center()

    assert view.status is ProductDataStatus.EMPTY
    assert view.total_count == 0
    assert view.events == ()


def test_alert_center_projects_pending_and_sink_delivery_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "alerts.sqlite3"
    outbox = AlertOutbox(path)
    pending = append_event(
        outbox,
        "pending",
        appended_at_ms=1_100,
    )
    delivered = append_event(
        outbox,
        "delivered",
        appended_at_ms=1_200,
    )

    outbox.record_delivery_attempt(
        delivered.event_identity,
        "sink/a",
        DeliveryResult(
            status=DeliveryAttemptStatus.RETRYABLE_FAILURE,
            error_code="timeout",
            error_message="provider timeout",
        ),
        attempted_at_ms=1_300,
    )
    outbox.record_delivery_attempt(
        delivered.event_identity,
        "sink/a",
        DeliveryResult(
            status=DeliveryAttemptStatus.DELIVERED,
            receipt="receipt-a",
        ),
        attempted_at_ms=1_400,
    )
    outbox.record_delivery_attempt(
        delivered.event_identity,
        "sink/b",
        DeliveryResult(
            status=DeliveryAttemptStatus.PERMANENT_FAILURE,
            error_code="invalid_destination",
            error_message="destination invalid",
        ),
        attempted_at_ms=1_350,
    )

    reader = DashboardReader(
        tmp_path / "signal.sqlite3",
        alert_outbox_path=path,
    )
    view = reader.alert_center()

    assert view.status is ProductDataStatus.READY
    assert view.total_count == 2
    assert [item.event_identity for item in view.events] == [
        delivered.event_identity,
        pending.event_identity,
    ]

    delivered_view = view.events[0]
    assert delivered_view.signal_state is SignalState.ACTIVE
    assert delivered_view.probability_status is ProbabilityStatus.NOT_CALIBRATED
    assert delivered_view.confluence_score_semantic is (
        ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY
    )
    assert len(delivered_view.delivery_states) == 2

    by_sink = {
        item.sink_id: item
        for item in delivered_view.delivery_states
    }
    assert by_sink["sink/a"].attempts == 2
    assert by_sink["sink/a"].latest_status is DeliveryAttemptStatus.DELIVERED
    assert by_sink["sink/a"].delivered is True
    assert by_sink["sink/a"].latest_receipt == "receipt-a"
    assert by_sink["sink/b"].latest_status is (
        DeliveryAttemptStatus.PERMANENT_FAILURE
    )
    assert by_sink["sink/b"].terminal is True
    assert by_sink["sink/b"].delivered is False

    pending_view = view.events[1]
    assert pending_view.delivery_states == ()


def test_alert_center_api_serializes_pending_event(tmp_path: Path) -> None:
    alert_path = tmp_path / "alerts.sqlite3"
    outbox = AlertOutbox(alert_path)
    event = append_event(outbox, "api", appended_at_ms=1_100)

    client = TestClient(
        create_app(
            tmp_path / "signal.sqlite3",
            alert_outbox_path=alert_path,
        )
    )
    response = client.get("/api/alerts")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["total_count"] == 1
    assert body["events"][0]["event_identity"] == event.event_identity
    assert body["events"][0]["source_kind"] == "initial_signal"
    assert body["events"][0]["signal_state"] == "active"
    assert body["events"][0]["delivery_states"] == []
