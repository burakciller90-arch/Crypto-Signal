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

AS_OF = 10_000_000
MINUTE = 60_000


def _coverage(
    *,
    observed_at_ms: int = AS_OF - 100,
    start_ms: int = AS_OF - 3_000_000,
    end_ms: int = AS_OF + 4_000_000,
    categories=DEFAULT_REQUIRED_EVENT_CATEGORIES,
    quality: EventSourceQuality = EventSourceQuality.OFFICIAL,
):
    return build_event_calendar_coverage(
        coverage_start_ms=start_ms,
        coverage_end_ms=end_ms,
        categories=tuple(categories),
        source_provider="calendar-provider",
        source_quality=quality,
        source=DataSource.AGGREGATED,
        observed_at_ms=observed_at_ms,
        adapter_version="event-risk-test/1",
    )


def _event(
    event_id: str,
    *,
    scheduled_at_ms: int,
    category: EventCategory = EventCategory.CENTRAL_BANK,
    assets: tuple[str, ...] = ("BTC",),
    quality: EventSourceQuality = EventSourceQuality.OFFICIAL,
    provider: str = "calendar-provider",
    source_timestamp_ms: int = AS_OF - 1_000,
    ingested_at_ms: int = AS_OF - 900,
):
    return build_structured_event_observation(
        provider_event_id=event_id,
        title=f"Event {event_id}",
        category=category,
        scheduled_at_ms=scheduled_at_ms,
        affected_assets=assets,
        source_provider=provider,
        source_quality=quality,
        source=DataSource.AGGREGATED,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version="event-risk-test/1",
    )


def test_complete_verified_coverage_with_no_event_is_clear_not_missing_data() -> None:
    first = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    second = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert first == second
    assert first.analysis.state is EventRiskState.CLEAR
    assert first.analysis.consumed_event_identities == ()
    assert first.analysis.nearest_event_identity is None
    assert first.coverage is not None
    assert len(first.freeze_identity) == 64


def test_pre_block_and_post_windows_are_distinct_with_block_precedence() -> None:
    caution = _event("caution", scheduled_at_ms=AS_OF + 30 * MINUTE)
    block = _event("block", scheduled_at_ms=AS_OF + 5 * MINUTE)
    post = _event("post", scheduled_at_ms=AS_OF - 30 * MINUTE)

    caution_freeze = build_event_risk_evidence_freeze(
        (caution,),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    post_freeze = build_event_risk_evidence_freeze(
        (post,),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    combined = build_event_risk_evidence_freeze(
        (post, caution, block),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert caution_freeze.analysis.state is EventRiskState.PRE_EVENT_CAUTION
    assert post_freeze.analysis.state is EventRiskState.POST_EVENT_STABILIZATION
    assert combined.analysis.state is EventRiskState.EVENT_BLOCK
    assert combined.analysis.nearest_event_identity == block.event_identity


def test_global_event_applies_to_asset_without_directional_claim() -> None:
    event = _event(
        "global-cpi",
        scheduled_at_ms=AS_OF + 10 * MINUTE,
        category=EventCategory.INFLATION,
        assets=(),
    )
    freeze = build_event_risk_evidence_freeze(
        (event,),
        coverage=_coverage(),
        asset="ETH",
        as_of_ms=AS_OF,
    )

    assert freeze.analysis.state is EventRiskState.EVENT_BLOCK
    assert event.event_identity in freeze.analysis.consumed_event_identities
    assert "event_risk_is_context_or_veto_not_directional_signal" in (
        freeze.analysis.uncertainty_flags
    )


def test_missing_future_or_stale_or_incomplete_coverage_fails_closed() -> None:
    missing = build_event_risk_evidence_freeze(
        (),
        coverage=None,
        asset="BTC",
        as_of_ms=AS_OF,
    )
    future = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(observed_at_ms=AS_OF + 1),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    stale = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(observed_at_ms=AS_OF - 7 * 60 * MINUTE),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    incomplete = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(categories=(EventCategory.CENTRAL_BANK,)),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    for freeze in (missing, future, stale, incomplete):
        assert freeze.analysis.state is EventRiskState.DEGRADED_DATA

    assert missing.coverage is None
    assert future.coverage is None
    assert missing.analysis.coverage_identity is None
    assert future.analysis.coverage_identity is None
    assert stale.coverage is not None
    assert "stale_event_calendar_coverage" in stale.analysis.uncertainty_flags
    assert "event_calendar_required_categories_incomplete" in (
        incomplete.analysis.uncertainty_flags
    )


def test_unverified_active_event_is_degraded_not_event_block() -> None:
    event = _event(
        "rumor",
        scheduled_at_ms=AS_OF + 5 * MINUTE,
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


def test_future_late_or_out_of_horizon_wrong_context_cannot_rewrite_history() -> None:
    baseline = build_event_risk_evidence_freeze(
        (),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    future_wrong_provider = _event(
        "future-wrong-provider",
        scheduled_at_ms=AS_OF + 5 * MINUTE,
        provider="other-provider",
        source_timestamp_ms=AS_OF + 1,
        ingested_at_ms=AS_OF + 2,
    )
    late_wrong_provider = _event(
        "late-wrong-provider",
        scheduled_at_ms=AS_OF - 5 * MINUTE,
        provider="other-provider",
        source_timestamp_ms=AS_OF - 100,
        ingested_at_ms=AS_OF + 1,
    )
    far_wrong_provider = _event(
        "far-wrong-provider",
        scheduled_at_ms=AS_OF + 2 * 60 * MINUTE,
        provider="other-provider",
    )

    changed = build_event_risk_evidence_freeze(
        (future_wrong_provider, late_wrong_provider, far_wrong_provider),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert changed == baseline


def test_eligible_provider_mismatch_and_duplicate_provider_event_fail_closed() -> None:
    wrong_provider = _event(
        "wrong-provider",
        scheduled_at_ms=AS_OF + 5 * MINUTE,
        provider="other-provider",
    )
    with pytest.raises(ValueError, match="provider mismatch"):
        build_event_risk_evidence_freeze(
            (wrong_provider,),
            coverage=_coverage(),
            asset="BTC",
            as_of_ms=AS_OF,
        )

    first = _event("same-id", scheduled_at_ms=AS_OF + 5 * MINUTE)
    second = build_structured_event_observation(
        provider_event_id="same-id",
        title="Second same provider id",
        category=EventCategory.REGULATORY,
        scheduled_at_ms=AS_OF + 6 * MINUTE,
        affected_assets=("BTC",),
        source_provider="calendar-provider",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.AGGREGATED,
        source_timestamp_ms=AS_OF - 1_000,
        ingested_at_ms=AS_OF - 900,
        adapter_version="event-risk-test/1",
    )
    with pytest.raises(ValueError, match="duplicate provider event id"):
        build_event_risk_evidence_freeze(
            (first, second),
            coverage=_coverage(),
            asset="BTC",
            as_of_ms=AS_OF,
        )


def test_identity_tampering_and_invalid_timing_fail_closed() -> None:
    event = _event("block", scheduled_at_ms=AS_OF + 5 * MINUTE)
    freeze = build_event_risk_evidence_freeze(
        (event,),
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    with pytest.raises(ValueError, match="event identity mismatch"):
        replace(event, event_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="shorter than caution lead"):
        EventRiskConfig(caution_lead_ms=15 * MINUTE, block_before_ms=15 * MINUTE)
    with pytest.raises(ValueError, match="required categories"):
        EventRiskConfig(required_categories=())
