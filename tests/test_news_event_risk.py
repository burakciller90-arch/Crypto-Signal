from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.event_risk import EventCategory, EventSourceQuality
from crypto_signal.data.models import DataSource
from crypto_signal.data.news_events import build_news_event_observation
from crypto_signal.intelligence.news_event_risk import (
    NewsEvidenceConfig,
    NewsEvidenceState,
    build_news_evidence_freeze,
)

AS_OF = 1_000_000_000
MINUTE = 60_000


def _news(
    provider: str,
    article_id: str,
    *,
    cluster: str = "cluster-1",
    category: EventCategory = EventCategory.REGULATORY,
    assets: tuple[str, ...] = ("BTC",),
    published_delta_minutes: int = -10,
    quality: EventSourceQuality = EventSourceQuality.PRIMARY_PROVIDER,
    confidence: str = "0.90",
    source_timestamp_ms: int | None = None,
    ingested_at_ms: int | None = None,
):
    published = AS_OF + published_delta_minutes * MINUTE
    source_ms = (
        published + 1_000 if source_timestamp_ms is None else source_timestamp_ms
    )
    ingest_ms = source_ms + 1_000 if ingested_at_ms is None else ingested_at_ms
    return build_news_event_observation(
        provider_article_id=article_id,
        event_cluster_key=cluster,
        headline=f"{provider} {article_id}",
        category=category,
        affected_assets=assets,
        published_at_ms=published,
        source_provider=provider,
        source_quality=quality,
        source=DataSource.AGGREGATED,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingest_ms,
        extraction_method="provider-metadata-plus-nlp",
        extraction_version="news-nlp-test/1",
        relevance_confidence_0_1=Decimal(confidence),
        adapter_version="news-event-test/1",
    )


def test_multi_source_confirmation_is_deterministic_without_directional_claim() -> None:
    first = _news("provider-a", "a1")
    second = _news("provider-b", "b1", published_delta_minutes=-9)

    one = build_news_evidence_freeze(
        (second, first),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    two = build_news_evidence_freeze(
        (first, second),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert one == two
    assert one.analysis.state is NewsEvidenceState.MULTI_SOURCE_CONFIRMED
    assert one.analysis.consensus_category is EventCategory.REGULATORY
    assert one.analysis.metrics is not None
    assert one.analysis.metrics.article_count == 2
    assert one.analysis.metrics.distinct_provider_count == 2
    assert one.analysis.metrics.official_or_primary_provider_count == 2
    assert one.analysis.metrics.mean_relevance_confidence_0_1 == Decimal("0.90")
    assert "news_nlp_context_is_not_directional_price_truth" in (
        one.analysis.uncertainty_flags
    )


def test_single_source_context_remains_distinct_from_multi_source_confirmation() -> None:
    freeze = build_news_evidence_freeze(
        (_news("provider-a", "a1"),),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert freeze.analysis.state is NewsEvidenceState.SINGLE_SOURCE_CONTEXT
    assert freeze.analysis.consensus_category is EventCategory.REGULATORY
    assert freeze.analysis.metrics is not None
    assert freeze.analysis.metrics.distinct_provider_count == 1


def test_provider_category_disagreement_is_explicit_conflict() -> None:
    regulatory = _news("provider-a", "a1")
    security = _news(
        "provider-b",
        "b1",
        category=EventCategory.EXCHANGE_SECURITY,
        published_delta_minutes=-9,
    )

    freeze = build_news_evidence_freeze(
        (regulatory, security),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert freeze.analysis.state is NewsEvidenceState.PROVIDER_DISAGREEMENT
    assert freeze.analysis.consensus_category is None
    assert "news_provider_category_disagreement" in freeze.analysis.uncertainty_flags


@pytest.mark.parametrize(
    ("quality", "confidence", "expected_flag"),
    [
        (
            EventSourceQuality.UNVERIFIED,
            "0.90",
            "unverified_news_source_in_selected_cluster",
        ),
        (
            EventSourceQuality.PRIMARY_PROVIDER,
            "0.40",
            "low_relevance_confidence_in_selected_cluster",
        ),
    ],
)
def test_unverified_or_low_confidence_selected_cluster_degrades(
    quality: EventSourceQuality,
    confidence: str,
    expected_flag: str,
) -> None:
    event = _news(
        "provider-a",
        "a1",
        quality=quality,
        confidence=confidence,
    )
    freeze = build_news_evidence_freeze(
        (event,),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert freeze.analysis.state is NewsEvidenceState.DEGRADED_DATA
    assert expected_flag in freeze.analysis.uncertainty_flags


def test_no_pit_relevant_news_is_unresolved_not_clear() -> None:
    future = _news(
        "provider-a",
        "future",
        published_delta_minutes=10,
        source_timestamp_ms=AS_OF + 11 * MINUTE,
        ingested_at_ms=AS_OF + 11 * MINUTE + 1,
    )
    old = _news(
        "provider-a",
        "old",
        published_delta_minutes=-(7 * 60),
    )
    other_asset = _news(
        "provider-a",
        "eth",
        assets=("ETH",),
    )

    freeze = build_news_evidence_freeze(
        (future, old, other_asset),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert freeze.analysis.state is NewsEvidenceState.UNRESOLVED
    assert freeze.analysis.metrics is None
    assert freeze.observations == ()
    assert freeze.analysis.uncertainty_flags == (
        "news_event_evidence_unavailable_at_as_of",
    )


def test_future_late_or_other_cluster_evidence_cannot_rewrite_selected_history() -> None:
    baseline = (
        _news("provider-a", "a1"),
        _news("provider-b", "b1", published_delta_minutes=-9),
    )
    first = build_news_evidence_freeze(
        baseline,
        asset="BTC",
        as_of_ms=AS_OF,
    )
    future = _news(
        "provider-c",
        "future",
        cluster="cluster-2",
        published_delta_minutes=5,
        category=EventCategory.EXCHANGE_SECURITY,
        source_timestamp_ms=AS_OF + 6 * MINUTE,
        ingested_at_ms=AS_OF + 6 * MINUTE + 1,
    )
    late = _news(
        "provider-c",
        "late",
        cluster="cluster-2",
        published_delta_minutes=-1,
        category=EventCategory.EXCHANGE_SECURITY,
        source_timestamp_ms=AS_OF - 30_000,
        ingested_at_ms=AS_OF + 1,
    )
    older_cluster = _news(
        "provider-c",
        "older",
        cluster="cluster-older",
        published_delta_minutes=-60,
        category=EventCategory.INFLATION,
    )

    changed = build_news_evidence_freeze(
        (*baseline, future, late, older_cluster),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert changed == first


def test_latest_cluster_is_selected_without_cross_cluster_aggregation() -> None:
    older = _news(
        "provider-a",
        "older",
        cluster="cluster-old",
        published_delta_minutes=-30,
        category=EventCategory.INFLATION,
    )
    latest_a = _news(
        "provider-a",
        "new-a",
        cluster="cluster-new",
        published_delta_minutes=-5,
        category=EventCategory.CENTRAL_BANK,
    )
    latest_b = _news(
        "provider-b",
        "new-b",
        cluster="cluster-new",
        published_delta_minutes=-4,
        category=EventCategory.CENTRAL_BANK,
    )

    freeze = build_news_evidence_freeze(
        (older, latest_a, latest_b),
        asset="BTC",
        as_of_ms=AS_OF,
    )

    assert freeze.analysis.event_cluster_key == "cluster-new"
    assert freeze.analysis.consensus_category is EventCategory.CENTRAL_BANK
    assert set(freeze.observations) == {latest_a, latest_b}


def test_duplicate_provider_article_and_identity_tampering_fail_closed() -> None:
    first = _news("provider-a", "same")
    duplicate = _news(
        "provider-a",
        "same",
        published_delta_minutes=-9,
    )

    with pytest.raises(ValueError, match="duplicate news provider/article identity"):
        build_news_evidence_freeze(
            (first, duplicate),
            asset="BTC",
            as_of_ms=AS_OF,
        )

    freeze = build_news_evidence_freeze(
        (first,),
        asset="BTC",
        as_of_ms=AS_OF,
    )
    with pytest.raises(ValueError, match="news event identity mismatch"):
        replace(first, news_identity="f" * 64)
    with pytest.raises(ValueError, match="news evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)


def test_invalid_confidence_or_policy_fails_closed() -> None:
    with pytest.raises(ValueError, match="inside"):
        _news("provider-a", "a1", confidence="1.1")
    with pytest.raises(ValueError, match="lookback"):
        NewsEvidenceConfig(lookback_ms=0)
    with pytest.raises(ValueError, match="at least two"):
        NewsEvidenceConfig(multi_source_provider_count=1)
