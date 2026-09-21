from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.models import MethodologyKind
from crypto_signal.data.models import DataSource
from crypto_signal.data.sentiment_attention import (
    SentimentClassification,
    SentimentScope,
    build_fear_greed_snapshot,
    build_pageview_daily_record,
    build_pageview_window_observation,
)
from crypto_signal.intelligence.sentiment_attention import (
    SENTIMENT_ATTENTION_ENGINE_VERSION,
    SENTIMENT_ATTENTION_FREEZE_SCHEMA_VERSION,
    AttentionState,
    ProviderSentimentState,
    SentimentAttentionConfig,
    SentimentAttentionLabel,
    analyze_sentiment_attention,
    build_sentiment_attention_evidence_freeze,
)

_DAY_MS = 24 * 60 * 60 * 1000
_OBSERVED_AT_MS = 200 * _DAY_MS


def _sentiment(
    *,
    classification: SentimentClassification = SentimentClassification.FEAR,
    value: int = 25,
    observed_at_ms: int = _OBSERVED_AT_MS,
    provider_timestamp_ms: int | None = None,
):
    provider_ms = (
        observed_at_ms - _DAY_MS
        if provider_timestamp_ms is None
        else provider_timestamp_ms
    )
    return build_fear_greed_snapshot(
        scope=SentimentScope.BITCOIN,
        value=value,
        classification=classification,
        provider_timestamp_ms=provider_ms,
        observed_at_ms=observed_at_ms,
        source=DataSource.REST,
        adapter_version="sentiment-engine-test/1",
    )


def _attention(
    *,
    baseline_views: int = 100,
    recent_views: int = 200,
    observed_at_ms: int = _OBSERVED_AT_MS,
    article: str = "Bitcoin",
):
    start_day = observed_at_ms // _DAY_MS - 11
    values = [baseline_views] * 7 + [recent_views] * 3
    records = tuple(
        build_pageview_daily_record(
            project="en.wikipedia.org",
            article=article,
            day_start_ms=(start_day + offset) * _DAY_MS,
            views=views,
            access="all-access",
            agent="user",
        )
        for offset, views in enumerate(values)
    )
    return build_pageview_window_observation(
        project="en.wikipedia.org",
        article=article,
        observed_at_ms=observed_at_ms,
        records=records,
        source=DataSource.REST,
        adapter_version="attention-engine-test/1",
    )


def test_fear_context_with_elevated_attention_is_deterministic_and_frozen() -> None:
    sentiment = _sentiment()
    attention = _attention()

    first = build_sentiment_attention_evidence_freeze(
        (sentiment,),
        (attention,),
        as_of_ms=_OBSERVED_AT_MS,
    )
    second = build_sentiment_attention_evidence_freeze(
        (sentiment,),
        (attention,),
        as_of_ms=_OBSERVED_AT_MS,
    )

    assert first == second
    assert first.schema_version == SENTIMENT_ATTENTION_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == SENTIMENT_ATTENTION_ENGINE_VERSION
    assert first.analysis.label is SentimentAttentionLabel.FEAR_CONTEXT
    assert first.analysis.sentiment_state is ProviderSentimentState.FEAR
    assert first.analysis.attention_state is AttentionState.ELEVATED
    assert first.analysis.metrics is not None
    assert first.analysis.metrics.provider_sentiment_value == 25
    assert first.analysis.metrics.attention_baseline_average_views == Decimal(100)
    assert first.analysis.metrics.attention_recent_average_views == Decimal(200)
    assert first.analysis.metrics.attention_ratio == Decimal(2)
    assert first.analysis.metrics.attention_record_count == 10
    assert first.analysis.uncertainty_flags == ()
    assert len(first.freeze_identity) == 64


def test_greed_and_neutral_context_do_not_become_trade_direction_claims() -> None:
    greed = analyze_sentiment_attention(
        (
            _sentiment(
                classification=SentimentClassification.EXTREME_GREED,
                value=82,
            ),
        ),
        (_attention(baseline_views=200, recent_views=100),),
        as_of_ms=_OBSERVED_AT_MS,
    )
    neutral = analyze_sentiment_attention(
        (
            _sentiment(
                classification=SentimentClassification.NEUTRAL,
                value=50,
            ),
        ),
        (_attention(baseline_views=100, recent_views=100),),
        as_of_ms=_OBSERVED_AT_MS,
    )

    assert greed.label is SentimentAttentionLabel.GREED_CONTEXT
    assert greed.sentiment_state is ProviderSentimentState.EXTREME_GREED
    assert greed.attention_state is AttentionState.SUBDUED
    assert neutral.label is SentimentAttentionLabel.NEUTRAL_CONTEXT
    assert neutral.attention_state is AttentionState.NORMAL


def test_missing_or_stale_component_is_unresolved_without_partial_metrics() -> None:
    sentiment = _sentiment()
    attention = _attention()

    missing_attention = analyze_sentiment_attention(
        (sentiment,),
        (),
        as_of_ms=_OBSERVED_AT_MS,
    )
    stale = analyze_sentiment_attention(
        (sentiment,),
        (attention,),
        as_of_ms=_OBSERVED_AT_MS + 37 * 60 * 60_000,
    )

    assert missing_attention.label is SentimentAttentionLabel.UNRESOLVED
    assert missing_attention.metrics is None
    assert (
        "attention_observation_unavailable_at_as_of"
        in missing_attention.uncertainty_flags
    )
    assert stale.label is SentimentAttentionLabel.UNRESOLVED
    assert stale.metrics is None
    assert "stale_sentiment_snapshot" in stale.uncertainty_flags
    assert "stale_attention_snapshot" in stale.uncertainty_flags


def test_future_ingestion_cannot_change_historical_freeze() -> None:
    sentiment = _sentiment()
    attention = _attention()
    baseline = build_sentiment_attention_evidence_freeze(
        (sentiment,),
        (attention,),
        as_of_ms=_OBSERVED_AT_MS,
    )

    future_sentiment = _sentiment(
        classification=SentimentClassification.EXTREME_GREED,
        value=95,
        observed_at_ms=_OBSERVED_AT_MS + 10_000,
        provider_timestamp_ms=_OBSERVED_AT_MS,
    )
    future_attention = _attention(
        baseline_views=100,
        recent_views=1_000,
        observed_at_ms=_OBSERVED_AT_MS + 10_000,
    )

    with_future = build_sentiment_attention_evidence_freeze(
        (sentiment, future_sentiment),
        (attention, future_attention),
        as_of_ms=_OBSERVED_AT_MS,
    )

    assert with_future == baseline
    assert with_future.sentiment_snapshot == sentiment
    assert with_future.attention_observation == attention


def test_no_safe_observation_is_unresolved_without_fabricated_values() -> None:
    future_sentiment = _sentiment(observed_at_ms=_OBSERVED_AT_MS + 10_000)
    future_attention = _attention(observed_at_ms=_OBSERVED_AT_MS + 10_000)

    result = analyze_sentiment_attention(
        (future_sentiment,),
        (future_attention,),
        as_of_ms=_OBSERVED_AT_MS,
    )

    assert result.label is SentimentAttentionLabel.UNRESOLVED
    assert result.metrics is None
    assert result.sentiment_observed_at_ms is None
    assert result.attention_observed_at_ms is None
    assert result.uncertainty_flags == (
        "sentiment_snapshot_unavailable_at_as_of",
        "attention_observation_unavailable_at_as_of",
    )


def test_zero_attention_baseline_fails_closed() -> None:
    result = analyze_sentiment_attention(
        (_sentiment(),),
        (_attention(baseline_views=0, recent_views=100),),
        as_of_ms=_OBSERVED_AT_MS,
    )

    assert result.label is SentimentAttentionLabel.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("zero_attention_baseline",)


def test_duplicate_identity_and_freeze_tampering_fail_closed() -> None:
    sentiment = _sentiment()
    attention = _attention()

    with pytest.raises(ValueError, match="duplicate sentiment"):
        analyze_sentiment_attention(
            (sentiment, sentiment),
            (attention,),
            as_of_ms=_OBSERVED_AT_MS,
        )

    freeze = build_sentiment_attention_evidence_freeze(
        (sentiment,),
        (attention,),
        as_of_ms=_OBSERVED_AT_MS,
    )
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_invalid_config_and_wrong_attention_context_fail_closed() -> None:
    with pytest.raises(ValueError, match="baseline"):
        SentimentAttentionConfig(baseline_attention_days=1)

    wrong_attention = _attention(article="Ethereum")
    with pytest.raises(ValueError, match="Bitcoin pageviews"):
        analyze_sentiment_attention(
            (_sentiment(),),
            (wrong_attention,),
            as_of_ms=_OBSERVED_AT_MS,
        )


def test_stage8_sentiment_attention_is_observation_only_ablation_zero() -> None:
    assert set(MethodologyKind) == {
        MethodologyKind.PRICE_ACTION,
        MethodologyKind.HARMONIC,
        MethodologyKind.ELLIOTT,
    }

    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/crypto_signal/confluence/models.py",
        "src/crypto_signal/confluence/adapters.py",
        "src/crypto_signal/ledger/bundle.py",
        "src/crypto_signal/signals/models.py",
        "src/crypto_signal/paper/mission_control.py",
    ):
        source = (root / relative).read_text()
        assert "crypto_signal.intelligence.sentiment_attention" not in source
