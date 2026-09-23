from __future__ import annotations

from pathlib import Path

import pytest

from ops.continuity.watchdog_delivery_health import (
    HEALTHY,
    INCONSISTENT,
    PENDING,
    STALLED,
    WAITING_FOR_RUNTIME,
    classify_rolling_delivery,
    parse_status,
)


def _status(**updates: str) -> dict[str, str]:
    status = {
        "state": "RUNNING",
        "interval_seconds": "1200",
        "failure_count": "0",
        "next_due_epoch": "2300",
        "pending_event_id": "",
    }
    status.update(updates)
    return status


def test_running_without_pending_or_failures_is_genuinely_healthy() -> None:
    assert classify_rolling_delivery(_status(), 1500) == HEALTHY


def test_pending_first_retry_is_visible_but_does_not_create_second_event() -> None:
    value = _status(
        state="RETRYING",
        pending_event_id="crypto-20m-rolling:abc:5",
        failure_count="1",
        next_due_epoch="1400",
    )
    assert classify_rolling_delivery(value, 1410) == PENDING


def test_exact_historical_111_failure_case_is_stalled_not_healthy() -> None:
    value = _status(
        state="RETRYING",
        pending_event_id="crypto-20m-rolling:4bc50caa43074cf2:5",
        failure_count="111",
        next_due_epoch="1790115611",
    )
    assert classify_rolling_delivery(value, 1790121340) == STALLED


def test_persistent_pending_remains_same_event_across_threshold() -> None:
    value = _status(
        state="RETRYING",
        pending_event_id="crypto-20m-rolling:abc:5",
        failure_count="11",
        next_due_epoch="1200",
    )
    assert classify_rolling_delivery(value, 2500) == PENDING
    value["failure_count"] = "12"
    assert classify_rolling_delivery(value, 1320) == STALLED


@pytest.mark.parametrize(
    ("updates", "now", "expected"),
    [
        ({"state": "RETRYING", "failure_count": "111"}, 5000, INCONSISTENT),
        ({"state": "RUNNING", "failure_count": "1"}, 1500, INCONSISTENT),
        ({"state": "RUNNING", "next_due_epoch": "1000"}, 1100, INCONSISTENT),
        ({"state": "PAUSED"}, 1500, INCONSISTENT),
        ({"state": "WAITING_FOR_RUNTIME"}, 1500, WAITING_FOR_RUNTIME),
        ({"state": "RETRYING", "pending_event_id": "x", "failure_count": "NaN"}, 5000, INCONSISTENT),
        ({"interval_seconds": "999"}, 1500, INCONSISTENT),
        ({"state": "UNKNOWN"}, 1500, INCONSISTENT),
    ],
)
def test_liveness_is_never_equated_with_unproven_delivery(
    updates: dict[str, str],
    now: int,
    expected: str,
) -> None:
    assert classify_rolling_delivery(_status(**updates), now) == expected


def test_running_with_just_created_pending_identity_is_not_false_healthy() -> None:
    value = _status(
        pending_event_id="crypto-20m-rolling:abc:6",
        next_due_epoch="1400",
    )
    assert classify_rolling_delivery(value, 1410) == PENDING


def test_runtime_status_parser_keeps_first_record_and_ignores_bad_lines() -> None:
    parsed = parse_status(
        "state=RETRYING\ninterval_seconds=1200\n"
        "state=RUNNING\nbroken\npending_event_id=crypto:5\n"
    )
    assert parsed["state"] == "RETRYING"
    assert parsed["pending_event_id"] == "crypto:5"
    assert "broken" not in parsed


def test_workflow_never_marks_a_stalled_pending_timer_healthy() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (
        root / ".github/workflows/crypto-20m-continuity-wake.yml"
    ).read_text(encoding="utf-8")
    assert 'GITHUB_WATCHDOG_TIMER_ALIVE=YES' in workflow
    assert 'GITHUB_WATCHDOG_DELIVERY_STATE=$DELIVERY_STATE' in workflow
    assert 'GITHUB_WATCHDOG_DELIVERY_STALLED=YES' in workflow
    assert 'GITHUB_FALLBACK_SKIPPED_SAME_PENDING=YES' in workflow
    assert 'GITHUB_EMERGENCY_FALLBACK_SKIPPED_PENDING_EVENT=YES' in workflow
    assert 'watchdog_delivery_health.py' in workflow
    assert workflow.index('if [ -n "$PENDING" ]; then') < workflow.index(
        'EVENT_ID="crypto-20m-emergency:'
    )
    assert 'GITHUB_WATCHDOG_TIMER_HEALTHY=YES' in workflow
    assert 'cron: "*/5 * * * *"' in workflow


def test_transient_heartbeat_delay_never_duplicates_pending_delivery() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (
        root / ".github/workflows/crypto-20m-continuity-wake.yml"
    ).read_text(encoding="utf-8")

    # A transport call may block the timer heartbeat for up to 60 seconds.
    assert '[ "$AGE" -le 90 ]' in workflow
    assert 'GITHUB_WATCHDOG_HEARTBEAT_STALE_WITH_PENDING=YES' in workflow
    assert 'GITHUB_WATCHDOG_EXISTING_PENDING_TIMER_PRESERVED=YES' in workflow
    assert workflow.index(
        'GITHUB_WATCHDOG_EXISTING_PENDING_TIMER_PRESERVED=YES'
    ) < workflow.index('if [ -f "$TIMER" ]; then')
    assert '[ "$EXACT_TIMER_ALIVE" = "1" ]' in workflow

    # Read the persisted event ID before considering emergency fallback.
    assert 'STATE_FILE="$RUNTIME/rolling_wake_state.json"' in workflow
    assert 'GITHUB_WATCHDOG_PENDING_SNAPSHOT_CONFLICT=YES' in workflow
    assert 'GITHUB_FALLBACK_SKIPPED_UNCERTAIN_PENDING=YES' in workflow
    assert 'GITHUB_WATCHDOG_ROLLING_STATE_CORRUPT=YES' in workflow
    assert 'GITHUB_WATCHDOG_ROLLING_STATE_MISSING=YES' in workflow
    assert workflow.index('PENDING="$STATE_PENDING"') < workflow.index(
        'EVENT_ID="crypto-20m-emergency:'
    )
