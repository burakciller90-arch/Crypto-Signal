from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.sentiment_attention import (
    FearGreedSnapshot,
    PageviewWindowObservation,
    SentimentClassification,
    SentimentScope,
)
from crypto_signal.ledger.serialization import canonical_sha256

SENTIMENT_ATTENTION_ENGINE_VERSION = "bounded-sentiment-attention-v1/1"
SENTIMENT_ATTENTION_FREEZE_SCHEMA_VERSION = "bounded-sentiment-attention-freeze-v1/1"
_DAY_MS = 24 * 60 * 60 * 1000


class ProviderSentimentState(StrEnum):
    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"
    UNAVAILABLE = "unavailable"


class AttentionState(StrEnum):
    ELEVATED = "elevated"
    NORMAL = "normal"
    SUBDUED = "subdued"
    UNAVAILABLE = "unavailable"


class SentimentAttentionLabel(StrEnum):
    FEAR_CONTEXT = "fear_context"
    GREED_CONTEXT = "greed_context"
    NEUTRAL_CONTEXT = "neutral_context"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class SentimentAttentionConfig:
    baseline_attention_days: int = 7
    recent_attention_days: int = 3
    max_sentiment_ingest_age_ms: int = 36 * 60 * 60_000
    max_sentiment_provider_age_ms: int = 48 * 60 * 60_000
    max_attention_ingest_age_ms: int = 36 * 60 * 60_000
    max_attention_data_lag_ms: int = 4 * _DAY_MS
    elevated_attention_ratio: Decimal = Decimal("1.25")
    subdued_attention_ratio: Decimal = Decimal("0.75")

    def __post_init__(self) -> None:
        if self.baseline_attention_days < 2:
            raise ValueError("attention baseline must contain at least two days")
        if self.recent_attention_days < 1:
            raise ValueError("attention recent window must contain at least one day")
        if self.baseline_attention_days + self.recent_attention_days > 30:
            raise ValueError("attention lookback cannot exceed 30 days")
        for label, value in (
            ("max_sentiment_ingest_age_ms", self.max_sentiment_ingest_age_ms),
            ("max_sentiment_provider_age_ms", self.max_sentiment_provider_age_ms),
            ("max_attention_ingest_age_ms", self.max_attention_ingest_age_ms),
            ("max_attention_data_lag_ms", self.max_attention_data_lag_ms),
        ):
            if value <= 0:
                raise ValueError(f"{label} must be positive")
        if not Decimal(0) < self.subdued_attention_ratio < Decimal(1):
            raise ValueError("subdued attention ratio must be inside (0,1)")
        if self.elevated_attention_ratio <= Decimal(1):
            raise ValueError("elevated attention ratio must be greater than 1")


DEFAULT_SENTIMENT_ATTENTION_CONFIG = SentimentAttentionConfig()


@dataclass(frozen=True, slots=True)
class SentimentAttentionMetrics:
    provider_sentiment_value: int
    attention_baseline_average_views: Decimal
    attention_recent_average_views: Decimal
    attention_ratio: Decimal
    attention_record_count: int

    def __post_init__(self) -> None:
        if not 0 <= self.provider_sentiment_value <= 100:
            raise ValueError("provider sentiment value must be inside [0,100]")
        if self.attention_baseline_average_views <= Decimal(0):
            raise ValueError("attention baseline average must be positive")
        if self.attention_recent_average_views < Decimal(0):
            raise ValueError("attention recent average cannot be negative")
        if self.attention_ratio < Decimal(0):
            raise ValueError("attention ratio cannot be negative")
        if self.attention_record_count <= 0:
            raise ValueError("attention record count must be positive")
        if self.attention_ratio != (
            self.attention_recent_average_views
            / self.attention_baseline_average_views
        ):
            raise ValueError("attention ratio mismatch")


@dataclass(frozen=True, slots=True)
class SentimentAttentionAnalysis:
    evidence_identity: str
    engine_version: str
    as_of_ms: int
    sentiment_observed_at_ms: int | None
    sentiment_provider_timestamp_ms: int | None
    attention_observed_at_ms: int | None
    attention_latest_day_start_ms: int | None
    label: SentimentAttentionLabel
    sentiment_state: ProviderSentimentState
    attention_state: AttentionState
    metrics: SentimentAttentionMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "sentiment-attention evidence identity")
        if self.engine_version != SENTIMENT_ATTENTION_ENGINE_VERSION:
            raise ValueError("unsupported sentiment-attention engine version")
        if self.as_of_ms < 0:
            raise ValueError("sentiment-attention as_of_ms must be non-negative")
        for label, value in (
            ("sentiment_observed_at_ms", self.sentiment_observed_at_ms),
            ("sentiment_provider_timestamp_ms", self.sentiment_provider_timestamp_ms),
            ("attention_observed_at_ms", self.attention_observed_at_ms),
            ("attention_latest_day_start_ms", self.attention_latest_day_start_ms),
        ):
            if value is not None and not 0 <= value <= self.as_of_ms:
                raise ValueError(f"{label} must be available by as-of")
        if self.label is SentimentAttentionLabel.UNRESOLVED:
            if self.metrics is not None:
                raise ValueError("unresolved sentiment-attention cannot carry metrics")
            if self.sentiment_state is not ProviderSentimentState.UNAVAILABLE:
                raise ValueError("unresolved sentiment state must be unavailable")
            if self.attention_state is not AttentionState.UNAVAILABLE:
                raise ValueError("unresolved attention state must be unavailable")
            if not self.uncertainty_flags:
                raise ValueError("unresolved sentiment-attention requires uncertainty")
        else:
            if self.metrics is None:
                raise ValueError("resolved sentiment-attention requires metrics")
            if self.sentiment_state is ProviderSentimentState.UNAVAILABLE:
                raise ValueError("resolved sentiment state cannot be unavailable")
            if self.attention_state is AttentionState.UNAVAILABLE:
                raise ValueError("resolved attention state cannot be unavailable")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("sentiment-attention evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class SentimentAttentionEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: SentimentAttentionAnalysis
    sentiment_snapshot: FearGreedSnapshot | None
    attention_observation: PageviewWindowObservation | None

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "sentiment-attention freeze identity")
        if self.schema_version != SENTIMENT_ATTENTION_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported sentiment-attention freeze schema")
        if self.sentiment_snapshot is None:
            if self.analysis.sentiment_observed_at_ms is not None:
                raise ValueError("missing sentiment snapshot cannot have observation time")
        else:
            if (
                self.analysis.sentiment_observed_at_ms
                != self.sentiment_snapshot.observed_at_ms
            ):
                raise ValueError("sentiment freeze observation time mismatch")
            if (
                self.analysis.sentiment_provider_timestamp_ms
                != self.sentiment_snapshot.provider_timestamp_ms
            ):
                raise ValueError("sentiment freeze provider timestamp mismatch")
        if self.attention_observation is None:
            if self.analysis.attention_observed_at_ms is not None:
                raise ValueError(
                    "missing attention observation cannot have observation time"
                )
        elif (
            self.analysis.attention_observed_at_ms
            != self.attention_observation.observed_at_ms
        ):
            raise ValueError("attention freeze observation time mismatch")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("sentiment-attention freeze identity mismatch")


def analyze_sentiment_attention(
    sentiment_snapshots: Sequence[FearGreedSnapshot],
    attention_observations: Sequence[PageviewWindowObservation],
    *,
    as_of_ms: int,
    config: SentimentAttentionConfig = DEFAULT_SENTIMENT_ATTENTION_CONFIG,
) -> SentimentAttentionAnalysis:
    return build_sentiment_attention_evidence_freeze(
        sentiment_snapshots,
        attention_observations,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_sentiment_attention_evidence_freeze(
    sentiment_snapshots: Sequence[FearGreedSnapshot],
    attention_observations: Sequence[PageviewWindowObservation],
    *,
    as_of_ms: int,
    config: SentimentAttentionConfig = DEFAULT_SENTIMENT_ATTENTION_CONFIG,
) -> SentimentAttentionEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("sentiment-attention as_of_ms must be non-negative")

    _reject_duplicate_identities(sentiment_snapshots, attention_observations)
    _validate_context(sentiment_snapshots, attention_observations)

    safe_sentiment = tuple(
        sorted(
            (
                item
                for item in sentiment_snapshots
                if item.observed_at_ms <= as_of_ms
            ),
            key=lambda item: (item.observed_at_ms, item.snapshot_identity),
        )
    )
    safe_attention = tuple(
        sorted(
            (
                item
                for item in attention_observations
                if item.observed_at_ms <= as_of_ms
            ),
            key=lambda item: (item.observed_at_ms, item.observation_identity),
        )
    )
    sentiment = safe_sentiment[-1] if safe_sentiment else None
    attention = safe_attention[-1] if safe_attention else None
    flags: list[str] = []

    if sentiment is None:
        flags.append("sentiment_snapshot_unavailable_at_as_of")
    else:
        if as_of_ms - sentiment.observed_at_ms > config.max_sentiment_ingest_age_ms:
            flags.append("stale_sentiment_snapshot")
        if (
            as_of_ms - sentiment.provider_timestamp_ms
            > config.max_sentiment_provider_age_ms
        ):
            flags.append("stale_sentiment_provider_timestamp")

    required_attention_days = (
        config.baseline_attention_days + config.recent_attention_days
    )
    if attention is None:
        flags.append("attention_observation_unavailable_at_as_of")
    else:
        if as_of_ms - attention.observed_at_ms > config.max_attention_ingest_age_ms:
            flags.append("stale_attention_snapshot")
        latest_day_end_ms = attention.records[-1].day_start_ms + _DAY_MS
        if as_of_ms - latest_day_end_ms > config.max_attention_data_lag_ms:
            flags.append("stale_attention_source_window")
        if len(attention.records) < required_attention_days:
            flags.append("insufficient_attention_history")

    if flags:
        analysis = _unresolved(
            as_of_ms=as_of_ms,
            sentiment=sentiment,
            attention=attention,
            flags=tuple(flags),
        )
        return _freeze(
            analysis=analysis,
            sentiment=sentiment,
            attention=attention,
        )

    assert sentiment is not None
    assert attention is not None

    consumed_records = attention.records[-required_attention_days:]
    baseline = consumed_records[: config.baseline_attention_days]
    recent = consumed_records[config.baseline_attention_days :]
    baseline_average = Decimal(sum(item.views for item in baseline)) / Decimal(
        len(baseline)
    )
    if baseline_average <= Decimal(0):
        analysis = _unresolved(
            as_of_ms=as_of_ms,
            sentiment=sentiment,
            attention=attention,
            flags=("zero_attention_baseline",),
        )
        return _freeze(
            analysis=analysis,
            sentiment=sentiment,
            attention=attention,
        )
    recent_average = Decimal(sum(item.views for item in recent)) / Decimal(len(recent))
    attention_ratio = recent_average / baseline_average
    if attention_ratio >= config.elevated_attention_ratio:
        attention_state = AttentionState.ELEVATED
    elif attention_ratio <= config.subdued_attention_ratio:
        attention_state = AttentionState.SUBDUED
    else:
        attention_state = AttentionState.NORMAL

    sentiment_state = _sentiment_state(sentiment.classification)
    label = _label(sentiment_state)
    metrics = SentimentAttentionMetrics(
        provider_sentiment_value=sentiment.value,
        attention_baseline_average_views=baseline_average,
        attention_recent_average_views=recent_average,
        attention_ratio=attention_ratio,
        attention_record_count=len(consumed_records),
    )
    payload = {
        "as_of_ms": as_of_ms,
        "attention_latest_day_start_ms": consumed_records[-1].day_start_ms,
        "attention_observed_at_ms": attention.observed_at_ms,
        "attention_state": attention_state,
        "engine_version": SENTIMENT_ATTENTION_ENGINE_VERSION,
        "label": label,
        "metrics": _metrics_payload(metrics),
        "sentiment_observed_at_ms": sentiment.observed_at_ms,
        "sentiment_provider_timestamp_ms": sentiment.provider_timestamp_ms,
        "sentiment_state": sentiment_state,
        "uncertainty_flags": (),
    }
    analysis = SentimentAttentionAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=SENTIMENT_ATTENTION_ENGINE_VERSION,
        as_of_ms=as_of_ms,
        sentiment_observed_at_ms=sentiment.observed_at_ms,
        sentiment_provider_timestamp_ms=sentiment.provider_timestamp_ms,
        attention_observed_at_ms=attention.observed_at_ms,
        attention_latest_day_start_ms=consumed_records[-1].day_start_ms,
        label=label,
        sentiment_state=sentiment_state,
        attention_state=attention_state,
        metrics=metrics,
        uncertainty_flags=(),
    )
    return _freeze(
        analysis=analysis,
        sentiment=sentiment,
        attention=attention,
    )


def _validate_context(
    sentiment_snapshots: Sequence[FearGreedSnapshot],
    attention_observations: Sequence[PageviewWindowObservation],
) -> None:
    for item in sentiment_snapshots:
        if item.scope is not SentimentScope.BITCOIN:
            raise ValueError("sentiment-attention v1 supports Bitcoin sentiment only")
    for item in attention_observations:
        if (item.project, item.article) != ("en.wikipedia.org", "Bitcoin"):
            raise ValueError(
                "sentiment-attention v1 supports English Bitcoin pageviews only"
            )


def _reject_duplicate_identities(
    sentiment_snapshots: Sequence[FearGreedSnapshot],
    attention_observations: Sequence[PageviewWindowObservation],
) -> None:
    sentiment_ids = [item.snapshot_identity for item in sentiment_snapshots]
    attention_ids = [item.observation_identity for item in attention_observations]
    if len(sentiment_ids) != len(set(sentiment_ids)):
        raise ValueError("duplicate sentiment snapshot identity")
    if len(attention_ids) != len(set(attention_ids)):
        raise ValueError("duplicate attention observation identity")


def _sentiment_state(
    classification: SentimentClassification,
) -> ProviderSentimentState:
    return ProviderSentimentState(classification.value)


def _label(state: ProviderSentimentState) -> SentimentAttentionLabel:
    if state in {
        ProviderSentimentState.EXTREME_FEAR,
        ProviderSentimentState.FEAR,
    }:
        return SentimentAttentionLabel.FEAR_CONTEXT
    if state in {
        ProviderSentimentState.EXTREME_GREED,
        ProviderSentimentState.GREED,
    }:
        return SentimentAttentionLabel.GREED_CONTEXT
    if state is ProviderSentimentState.NEUTRAL:
        return SentimentAttentionLabel.NEUTRAL_CONTEXT
    raise ValueError("unavailable sentiment state cannot resolve context")


def _unresolved(
    *,
    as_of_ms: int,
    sentiment: FearGreedSnapshot | None,
    attention: PageviewWindowObservation | None,
    flags: tuple[str, ...],
) -> SentimentAttentionAnalysis:
    latest_attention_day = (
        None if attention is None else attention.records[-1].day_start_ms
    )
    payload = {
        "as_of_ms": as_of_ms,
        "attention_latest_day_start_ms": latest_attention_day,
        "attention_observed_at_ms": (
            None if attention is None else attention.observed_at_ms
        ),
        "attention_state": AttentionState.UNAVAILABLE,
        "engine_version": SENTIMENT_ATTENTION_ENGINE_VERSION,
        "label": SentimentAttentionLabel.UNRESOLVED,
        "metrics": None,
        "sentiment_observed_at_ms": (
            None if sentiment is None else sentiment.observed_at_ms
        ),
        "sentiment_provider_timestamp_ms": (
            None if sentiment is None else sentiment.provider_timestamp_ms
        ),
        "sentiment_state": ProviderSentimentState.UNAVAILABLE,
        "uncertainty_flags": flags,
    }
    return SentimentAttentionAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=SENTIMENT_ATTENTION_ENGINE_VERSION,
        as_of_ms=as_of_ms,
        sentiment_observed_at_ms=(
            None if sentiment is None else sentiment.observed_at_ms
        ),
        sentiment_provider_timestamp_ms=(
            None if sentiment is None else sentiment.provider_timestamp_ms
        ),
        attention_observed_at_ms=(
            None if attention is None else attention.observed_at_ms
        ),
        attention_latest_day_start_ms=latest_attention_day,
        label=SentimentAttentionLabel.UNRESOLVED,
        sentiment_state=ProviderSentimentState.UNAVAILABLE,
        attention_state=AttentionState.UNAVAILABLE,
        metrics=None,
        uncertainty_flags=flags,
    )


def _freeze(
    *,
    analysis: SentimentAttentionAnalysis,
    sentiment: FearGreedSnapshot | None,
    attention: PageviewWindowObservation | None,
) -> SentimentAttentionEvidenceFreeze:
    payload = {
        "analysis_identity": analysis.evidence_identity,
        "attention_observation_identity": (
            None if attention is None else attention.observation_identity
        ),
        "schema_version": SENTIMENT_ATTENTION_FREEZE_SCHEMA_VERSION,
        "sentiment_snapshot_identity": (
            None if sentiment is None else sentiment.snapshot_identity
        ),
    }
    return SentimentAttentionEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=SENTIMENT_ATTENTION_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        sentiment_snapshot=sentiment,
        attention_observation=attention,
    )


def _metrics_payload(metrics: SentimentAttentionMetrics) -> dict[str, object]:
    return {
        "attention_baseline_average_views": metrics.attention_baseline_average_views,
        "attention_ratio": metrics.attention_ratio,
        "attention_recent_average_views": metrics.attention_recent_average_views,
        "attention_record_count": metrics.attention_record_count,
        "provider_sentiment_value": metrics.provider_sentiment_value,
    }


def _analysis_payload(analysis: SentimentAttentionAnalysis) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "attention_latest_day_start_ms": analysis.attention_latest_day_start_ms,
        "attention_observed_at_ms": analysis.attention_observed_at_ms,
        "attention_state": analysis.attention_state,
        "engine_version": analysis.engine_version,
        "label": analysis.label,
        "metrics": (
            None if analysis.metrics is None else _metrics_payload(analysis.metrics)
        ),
        "sentiment_observed_at_ms": analysis.sentiment_observed_at_ms,
        "sentiment_provider_timestamp_ms": (
            analysis.sentiment_provider_timestamp_ms
        ),
        "sentiment_state": analysis.sentiment_state,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze_payload(
    freeze: SentimentAttentionEvidenceFreeze,
) -> dict[str, object]:
    return {
        "analysis_identity": freeze.analysis.evidence_identity,
        "attention_observation_identity": (
            None
            if freeze.attention_observation is None
            else freeze.attention_observation.observation_identity
        ),
        "schema_version": freeze.schema_version,
        "sentiment_snapshot_identity": (
            None
            if freeze.sentiment_snapshot is None
            else freeze.sentiment_snapshot.snapshot_identity
        ),
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
