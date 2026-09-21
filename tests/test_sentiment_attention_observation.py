from __future__ import annotations

from dataclasses import replace

import pytest

from crypto_signal.data.models import DataSource
from crypto_signal.data.sentiment_attention import (
    SentimentClassification,
    SentimentScope,
    build_fear_greed_snapshot,
    build_pageview_daily_record,
    build_pageview_window_observation,
)

_DAY_MS = 24 * 60 * 60 * 1000


def _fear_snapshot():
    return build_fear_greed_snapshot(
        scope=SentimentScope.BITCOIN,
        value=42,
        classification=SentimentClassification.FEAR,
        provider_timestamp_ms=10 * _DAY_MS,
        observed_at_ms=11 * _DAY_MS,
        source=DataSource.REST,
        adapter_version="sentiment-test/1",
    )


def _record(day: int, *, views: int = 100, article: str = "Bitcoin"):
    return build_pageview_daily_record(
        project="en.wikipedia.org",
        article=article,
        day_start_ms=day * _DAY_MS,
        views=views,
        access="all-access",
        agent="user",
    )


def test_fear_greed_snapshot_identity_and_ingestion_semantic_are_deterministic() -> None:
    first = _fear_snapshot()
    second = _fear_snapshot()

    assert first == second
    assert first.temporal_semantic == "ingestion_time_snapshot"
    assert first.attribution == "alternative.me"
    assert len(first.snapshot_identity) == 64


def test_fear_greed_snapshot_tampering_and_future_provider_time_fail_closed() -> None:
    snapshot = _fear_snapshot()

    with pytest.raises(ValueError, match="identity mismatch"):
        replace(snapshot, snapshot_identity="f" * 64)

    with pytest.raises(ValueError, match="cannot postdate"):
        build_fear_greed_snapshot(
            scope=SentimentScope.BITCOIN,
            value=50,
            classification=SentimentClassification.NEUTRAL,
            provider_timestamp_ms=12 * _DAY_MS,
            observed_at_ms=11 * _DAY_MS,
            source=DataSource.REST,
            adapter_version="sentiment-test/1",
        )


def test_fear_greed_value_and_attribution_are_bounded() -> None:
    with pytest.raises(ValueError, match=r"\[0,100\]"):
        build_fear_greed_snapshot(
            scope=SentimentScope.BITCOIN,
            value=101,
            classification=SentimentClassification.GREED,
            provider_timestamp_ms=10 * _DAY_MS,
            observed_at_ms=11 * _DAY_MS,
            source=DataSource.REST,
            adapter_version="sentiment-test/1",
        )

    with pytest.raises(ValueError, match="attribution"):
        replace(_fear_snapshot(), attribution="unknown")


def test_pageview_record_and_window_identity_are_deterministic() -> None:
    records = tuple(_record(day) for day in range(10, 20))

    first = build_pageview_window_observation(
        project="en.wikipedia.org",
        article="Bitcoin",
        observed_at_ms=21 * _DAY_MS,
        records=records,
        source=DataSource.REST,
        adapter_version="pageview-test/1",
    )
    second = build_pageview_window_observation(
        project="en.wikipedia.org",
        article="Bitcoin",
        observed_at_ms=21 * _DAY_MS,
        records=records,
        source=DataSource.REST,
        adapter_version="pageview-test/1",
    )

    assert first == second
    assert first.temporal_semantic == "ingestion_time_snapshot"
    assert len(first.observation_identity) == 64
    assert all(len(item.record_identity) == 64 for item in first.records)


def test_pageview_window_requires_contiguous_context_and_completed_days() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        build_pageview_window_observation(
            project="en.wikipedia.org",
            article="Bitcoin",
            observed_at_ms=21 * _DAY_MS,
            records=(_record(10), _record(12)),
            source=DataSource.REST,
            adapter_version="pageview-test/1",
        )

    with pytest.raises(ValueError, match="context mismatch"):
        build_pageview_window_observation(
            project="en.wikipedia.org",
            article="Bitcoin",
            observed_at_ms=21 * _DAY_MS,
            records=(_record(10), _record(11, article="Ethereum")),
            source=DataSource.REST,
            adapter_version="pageview-test/1",
        )

    with pytest.raises(ValueError, match="complete"):
        build_pageview_window_observation(
            project="en.wikipedia.org",
            article="Bitcoin",
            observed_at_ms=11 * _DAY_MS,
            records=(_record(10), _record(11)),
            source=DataSource.REST,
            adapter_version="pageview-test/1",
        )


def test_pageview_identity_tampering_and_invalid_measurements_fail_closed() -> None:
    record = _record(10)

    with pytest.raises(ValueError, match="record identity mismatch"):
        replace(record, record_identity="f" * 64)

    with pytest.raises(ValueError, match="cannot be negative"):
        _record(10, views=-1)

    window = build_pageview_window_observation(
        project="en.wikipedia.org",
        article="Bitcoin",
        observed_at_ms=13 * _DAY_MS,
        records=(_record(10), _record(11)),
        source=DataSource.REST,
        adapter_version="pageview-test/1",
    )
    with pytest.raises(ValueError, match="observation identity mismatch"):
        replace(window, observation_identity="f" * 64)
