from __future__ import annotations

from dataclasses import replace

import pytest

from crypto_signal.data.event_risk import (
    EventCategory,
    EventSourceQuality,
    build_event_calendar_coverage,
    build_structured_event_observation,
)
from crypto_signal.data.models import DataSource
from crypto_signal.intelligence.event_risk import (
    DEFAULT_REQUIRED_EVENT_CATEGORIES,
    EventRiskConfig,
    EventRiskState,
    build_event_risk_evidence_freeze,
)

AS_OF = 100_000_000
MINUTE = 60_000


def _coverage(
    *,
    observed_at_ms: int = AS_OF - 1_000,
    start_ms: int = AS_OF - 60 * MINUTE,
    end_ms: int = AS_OF + 90 * MINUTE,
    provider: str = "calendar-provider",
    quality: EventSourceQuality = EventSourceQuality.OFFICIAL,
    categories: tuple[EventCategory, ...] = DEFAULT_REQUIRED_EVENT_CATEGORIES,
):
    return build_event_calendar_coverage(
        coverage_start_ms=start_ms,
        coverage_end_ms=end_ms,
        categories=categories,
        source_provider=provider,
        source_quality=quality,
        source=DataSource.AGGREGATED,
        observed_at_ms=observed_at_ms,
        adapter_version="event-calendar-test/1",
    )


def _event(
    event_id: str,
    *,
    delta_minutes: int,
    category: EventCategory = EventCategory.INFLATION,
    assets: tuple[str, ...] = ("BTC",),
    provider: str = "calendar-provider",
    quality: EventSourceQuality = EventSourceQuality.OFFICIAL,
    source_timestamp_ms: int | None = None,
    ingested_at_ms: int | None = None,
):
    scheduled = AS_OF + delta_minutes * MINUTE
    source_ms = (
        AS_OF - 10_000 if source_timestamp_ms is None else source_timestamp_ms
    )
    ingest_ms = source_ms + 1_000 if ingested_at_ms is None else ingested_at_ms
    return build_structured_event_observation(
        provider_event_id=event_id,
        title=f"Event {event_id}",
        category=category,
        scheduled_at_ms=scheduled,
        affected_assets=assets,
        source_provider=provider,
        source_quality=quality,
        source=DataSource.AGGREGATED,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingest_ms,
        adapter_version="event-risk-test/1",
    )


@pytest.mark.parametrize(
    ("delta_minutes", "expected"),
    [
        (30, EventRiskState.PRE_EVENT_CAUTION),
        (10, EventRiskState.EVENT_BLOCK),
        (-10, EventRiskState.EVENT_BLOCK),
        (-20, EventRiskState.POST_EVENT_STABILIZATION),
    ],
)
def test_event_window_states_are_explicit_and_versioned(
    delta_minutes: int,
    expected: EventRiskState,
) -> None:
    event = _event(f"state-{delta_minutes}", delta_minutes=delta_minutes)
    freeze = build_event_risk_evidence_freeze(
        (event,),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert freeze.analysis.state is expected
    assert freeze.analysis.nearest_event_identity == event.event_identity
    assert freeze.analysis.nearest_event_scheduled_at_ms == event.scheduled_at_ms
    assert (
        "event_window_is_versioned_research_policy_not_universal_law"
        in freeze.analysis.uncertainty_flags
    )
    assert "event_risk_is_context_or_veto_not_directional_signal" in (
        freeze.analysis.uncertainty_flags
    )


def test_overlapping_events_use_more_restrictive_state_and_global_scope() -> None:
    post = _event("post", delta_minutes=-20)
    caution = _event("caution", delta_minutes=30)
    block = _event("block", delta_minutes=5)
    global_event = _event(
        "global",
        delta_minutes=10,
        assets=(),
        category=EventCategory.CENTRAL_BANK,
    )

    combined = build_event_risk_evidence_freeze(
        (post, caution, block),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    global_freeze = build_event_risk_evidence_freeze(
        (global_event,),
        coverage=_coverage(),
        asset="ETH",
        as_of_ms=AS_OF,
    )

    assert combined.analysis.state is EventRiskState.EVENT_BLOCK
    assert combined.analysis.nearest_event_identity == block.event_identity
    assert global_freeze.analysis.state is EventRiskState.EVENT_BLOCK
    assert global_event.event_identity in global_freeze.analysis.consumed_event_identities


def test_clear_state_requires_complete_coverage_not_missing_event_assumption() -> None:
    freeze = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert freeze.analysis.state is EventRiskState.CLEAR
    assert freeze.analysis.consumed_event_identities == ()
    assert freeze.analysis.nearest_event_identity is None


def test_missing_or_future_coverage_degrades_without_future_identity_leakage() -> None:
    missing = build_event_risk_evidence_freeze(
        (),
        coverage=None,
        asset="BTC",
        as_of_ms=AS_OF,
    )
    future_a = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(
            observed_at_ms=AS_OF + 1,
            provider="future-provider-a",
        ),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    future_b = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(
            observed_at_ms=AS_OF + 2,
            provider="future-provider-b",
        ),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert missing == future_a == future_b
    assert missing.coverage is None
    assert missing.analysis.coverage_identity is None
    assert missing.analysis.state is EventRiskState.DEGRADED_DATA
    assert missing.analysis.uncertainty_flags == (
        "event_calendar_coverage_unavailable_at_as_of",
    )


def test_stale_incomplete_or_unverified_coverage_fails_closed() -> None:
    stale = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(observed_at_ms=AS_OF - 7 * 60 * MINUTE),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    incomplete = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(end_ms=AS_OF + 30 * MINUTE),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    unverified = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(quality=EventSourceQuality.UNVERIFIED),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert stale.analysis.state is EventRiskState.DEGRADED_DATA
    assert "stale_event_calendar_coverage" in stale.analysis.uncertainty_flags
    assert incomplete.analysis.state is EventRiskState.DEGRADED_DATA
    assert "event_calendar_future_horizon_incomplete" in (
        incomplete.analysis.uncertainty_flags
    )
    assert unverified.analysis.state is EventRiskState.DEGRADED_DATA
    assert "unverified_event_calendar_coverage" in (
        unverified.analysis.uncertainty_flags
    )


def test_required_category_coverage_is_fail_closed() -> None:
    categories = tuple(
        category
        for category in DEFAULT_REQUIRED_EVENT_CATEGORIES
        if category is not EventCategory.CENTRAL_BANK
    )
    freeze = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(categories=categories),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert freeze.analysis.state is EventRiskState.DEGRADED_DATA
    assert "event_calendar_required_categories_incomplete" in (
        freeze.analysis.uncertainty_flags
    )


def test_unverified_relevant_event_degrades_verified_calendar() -> None:
    event = _event(
        "unverified-active",
        delta_minutes=10,
        quality=EventSourceQuality.UNVERIFIED,
    )
    freeze = build_event_risk_evidence_freeze(
        (event,),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert freeze.analysis.state is EventRiskState.DEGRADED_DATA
    assert freeze.analysis.nearest_event_identity == event.event_identity
    assert "unverified_event_source_in_active_horizon" in (
        freeze.analysis.uncertainty_flags
    )


def test_future_late_or_other_asset_events_cannot_rewrite_historical_freeze() -> None:
    baseline = _event("baseline", delta_minutes=30)
    first = build_event_risk_evidence_freeze(
        (baseline,),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    future_ingestion = _event(
        "future-ingestion",
        delta_minutes=10,
        source_timestamp_ms=AS_OF + 1,
        ingested_at_ms=AS_OF + 2,
    )
    late_ingestion = _event(
        "late-ingestion",
        delta_minutes=-10,
        source_timestamp_ms=AS_OF - 1_000,
        ingested_at_ms=AS_OF + 1,
    )
    other_asset = _event(
        "other-asset",
        delta_minutes=10,
        assets=("ETH",),
    )

    changed = build_event_risk_evidence_freeze(
        (baseline, future_ingestion, late_ingestion, other_asset),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert changed == first


def test_out_of_horizon_wrong_provider_does_not_poison_current_freeze() -> None:
    baseline = _event("baseline", delta_minutes=30)
    outside = _event(
        "outside",
        delta_minutes=180,
        provider="other-provider",
    )

    first = build_event_risk_evidence_freeze(
        (baseline,),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    changed = build_event_risk_evidence_freeze(
        (baseline, outside),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert changed == first


def test_relevant_context_mismatch_and_duplicates_fail_closed() -> None:
    wrong_provider = _event(
        "wrong-provider",
        delta_minutes=10,
        provider="other-provider",
    )
    with pytest.raises(ValueError, match="provider mismatch"):
        build_event_risk_evidence_freeze(
            (wrong_provider,),
            coverage=_coverage(),
            asset="BTC",
            as_of_ms=AS_OF,
        )

    baseline = _event("duplicate", delta_minutes=10)
    duplicate_provider_id = _event("duplicate", delta_minutes=20)
    with pytest.raises(ValueError, match="duplicate provider event id"):
        build_event_risk_evidence_freeze(
            (baseline, duplicate_provider_id),
            coverage=_coverage(),
            asset="BTC",
            as_of_ms=AS_OF,
        )


def test_identity_tampering_and_invalid_policy_fail_closed() -> None:
    event = _event("tamper", delta_minutes=10)
    freeze = build_event_risk_evidence_freeze(
        (event,),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    with pytest.raises(ValueError, match="structured event identity mismatch"):
        replace(event, event_identity="f" * 64)
    with pytest.raises(ValueError, match="event-risk evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)
    with pytest.raises(ValueError, match="event-risk freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)

    with pytest.raises(ValueError, match="block-before"):
        EventRiskConfig(
            caution_lead_ms=15 * MINUTE,
            block_before_ms=15 * MINUTE,
        )
