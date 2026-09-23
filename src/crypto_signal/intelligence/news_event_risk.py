from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.event_risk import EventCategory, EventSourceQuality
from crypto_signal.data.news_events import NewsEventObservation
from crypto_signal.ledger.serialization import canonical_sha256

NEWS_EVENT_ENGINE_VERSION = "news-event-risk-v1-slice2/1"
NEWS_EVENT_FREEZE_SCHEMA_VERSION = "news-event-risk-freeze-v1/1"


class NewsEvidenceState(StrEnum):
    MULTI_SOURCE_CONFIRMED = "multi_source_confirmed"
    SINGLE_SOURCE_CONTEXT = "single_source_context"
    PROVIDER_DISAGREEMENT = "provider_disagreement"
    DEGRADED_DATA = "degraded_data"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class NewsEvidenceConfig:
    lookback_ms: int = 6 * 60 * 60_000
    minimum_relevance_confidence: Decimal = Decimal("0.60")
    multi_source_provider_count: int = 2

    def __post_init__(self) -> None:
        if self.lookback_ms <= 0:
            raise ValueError("news evidence lookback must be positive")
        if self.multi_source_provider_count < 2:
            raise ValueError("news multi-source provider count must be at least two")
        value = self.minimum_relevance_confidence
        if (
            value.is_nan()
            or value.is_infinite()
            or not Decimal(0) <= value <= Decimal(1)
        ):
            raise ValueError("news minimum relevance confidence must be inside [0,1]")


DEFAULT_NEWS_EVIDENCE_CONFIG = NewsEvidenceConfig()


@dataclass(frozen=True, slots=True)
class NewsEvidenceMetrics:
    article_count: int
    distinct_provider_count: int
    official_or_primary_provider_count: int
    mean_relevance_confidence_0_1: Decimal
    earliest_published_at_ms: int
    latest_published_at_ms: int

    def __post_init__(self) -> None:
        if self.article_count <= 0:
            raise ValueError("news evidence metrics require articles")
        if not 1 <= self.distinct_provider_count <= self.article_count:
            raise ValueError("news distinct provider count outside article count")
        if not 0 <= self.official_or_primary_provider_count <= self.distinct_provider_count:
            raise ValueError("news high-quality provider count outside provider count")
        confidence = self.mean_relevance_confidence_0_1
        if (
            confidence.is_nan()
            or confidence.is_infinite()
            or not Decimal(0) <= confidence <= Decimal(1)
        ):
            raise ValueError("news mean relevance confidence outside [0,1]")
        if not 0 <= self.earliest_published_at_ms <= self.latest_published_at_ms:
            raise ValueError("news publication bounds invalid")


@dataclass(frozen=True, slots=True)
class NewsEvidenceAnalysis:
    evidence_identity: str
    engine_version: str
    asset: str
    as_of_ms: int
    state: NewsEvidenceState
    event_cluster_key: str | None
    consensus_category: EventCategory | None
    consumed_news_identities: tuple[str, ...]
    metrics: NewsEvidenceMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "news evidence identity")
        if self.engine_version != NEWS_EVENT_ENGINE_VERSION:
            raise ValueError("unsupported news evidence engine version")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("news evidence asset must be non-empty uppercase")
        if self.as_of_ms < 0:
            raise ValueError("news evidence as_of_ms must be non-negative")
        if tuple(sorted(set(self.consumed_news_identities))) != self.consumed_news_identities:
            raise ValueError("news evidence identities must be unique and sorted")
        for identity in self.consumed_news_identities:
            _require_sha256(identity, "consumed news identity")
        if self.state is NewsEvidenceState.UNRESOLVED:
            if (
                self.event_cluster_key is not None
                or self.consensus_category is not None
                or self.metrics is not None
                or self.consumed_news_identities
            ):
                raise ValueError("unresolved news evidence cannot expose measured context")
            if not self.uncertainty_flags:
                raise ValueError("unresolved news evidence requires uncertainty")
        else:
            if self.event_cluster_key is None or self.metrics is None:
                raise ValueError("resolved news evidence requires cluster and metrics")
        if self.state is NewsEvidenceState.PROVIDER_DISAGREEMENT:
            if self.consensus_category is not None:
                raise ValueError("provider disagreement cannot expose consensus category")
        elif self.state is not NewsEvidenceState.UNRESOLVED and self.consensus_category is None:
            raise ValueError("resolved non-conflict news evidence requires consensus category")
        if self.state is NewsEvidenceState.DEGRADED_DATA and not self.uncertainty_flags:
            raise ValueError("degraded news evidence requires uncertainty")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("news evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class NewsEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: NewsEvidenceAnalysis
    observations: tuple[NewsEventObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "news evidence freeze identity")
        if self.schema_version != NEWS_EVENT_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported news evidence freeze schema")
        if any(
            max(item.published_at_ms, item.source_timestamp_ms, item.ingested_at_ms)
            > self.analysis.as_of_ms
            for item in self.observations
        ):
            raise ValueError("news evidence freeze contains future evidence")
        expected = tuple(sorted(item.news_identity for item in self.observations))
        if expected != self.analysis.consumed_news_identities:
            raise ValueError("news freeze consumed identity mismatch")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("news evidence freeze identity mismatch")


def analyze_news_evidence(
    observations: Sequence[NewsEventObservation],
    *,
    asset: str,
    as_of_ms: int,
    config: NewsEvidenceConfig = DEFAULT_NEWS_EVIDENCE_CONFIG,
) -> NewsEvidenceAnalysis:
    return build_news_evidence_freeze(
        observations,
        asset=asset,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_news_evidence_freeze(
    observations: Sequence[NewsEventObservation],
    *,
    asset: str,
    as_of_ms: int,
    config: NewsEvidenceConfig = DEFAULT_NEWS_EVIDENCE_CONFIG,
) -> NewsEvidenceFreeze:
    if not asset or asset != asset.upper():
        raise ValueError("news evidence asset must be non-empty uppercase")
    if as_of_ms < 0:
        raise ValueError("news evidence as_of_ms must be non-negative")

    window_start = max(0, as_of_ms - config.lookback_ms)
    eligible = tuple(
        sorted(
            (
                item
                for item in observations
                if max(
                    item.published_at_ms,
                    item.source_timestamp_ms,
                    item.ingested_at_ms,
                )
                <= as_of_ms
                and item.published_at_ms >= window_start
                and (not item.affected_assets or asset in item.affected_assets)
            ),
            key=lambda item: (
                item.published_at_ms,
                item.event_cluster_key,
                item.source_provider,
                item.provider_article_id,
                item.news_identity,
            ),
        )
    )
    if not eligible:
        return _freeze(
            _unresolved(
                asset=asset,
                as_of_ms=as_of_ms,
                flags=("news_event_evidence_unavailable_at_as_of",),
            ),
            (),
        )

    _reject_duplicates(eligible)
    groups: dict[str, list[NewsEventObservation]] = defaultdict(list)
    for item in eligible:
        groups[item.event_cluster_key].append(item)

    selected_key = max(
        groups,
        key=lambda key: (
            max(item.published_at_ms for item in groups[key]),
            key,
        ),
    )
    selected = tuple(
        sorted(
            groups[selected_key],
            key=lambda item: (
                item.published_at_ms,
                item.source_provider,
                item.provider_article_id,
                item.news_identity,
            ),
        )
    )
    categories = {item.category for item in selected}
    providers = {item.source_provider for item in selected}
    high_quality_providers = {
        item.source_provider
        for item in selected
        if item.source_quality
        in {EventSourceQuality.OFFICIAL, EventSourceQuality.PRIMARY_PROVIDER}
    }
    mean_confidence = (
        sum(
            (item.relevance_confidence_0_1 for item in selected),
            start=Decimal(0),
        )
        / Decimal(len(selected))
    )
    metrics = NewsEvidenceMetrics(
        article_count=len(selected),
        distinct_provider_count=len(providers),
        official_or_primary_provider_count=len(high_quality_providers),
        mean_relevance_confidence_0_1=mean_confidence,
        earliest_published_at_ms=min(item.published_at_ms for item in selected),
        latest_published_at_ms=max(item.published_at_ms for item in selected),
    )

    flags: list[str] = [
        "news_nlp_context_is_not_directional_price_truth",
        "event_cluster_key_is_upstream_extraction_not_actor_identity",
    ]
    if any(item.source_quality is EventSourceQuality.UNVERIFIED for item in selected):
        flags.append("unverified_news_source_in_selected_cluster")
    if any(
        item.relevance_confidence_0_1 < config.minimum_relevance_confidence
        for item in selected
    ):
        flags.append("low_relevance_confidence_in_selected_cluster")

    if len(categories) > 1:
        state = NewsEvidenceState.PROVIDER_DISAGREEMENT
        consensus: EventCategory | None = None
        flags.append("news_provider_category_disagreement")
    else:
        consensus = next(iter(categories))
        if (
            "unverified_news_source_in_selected_cluster" in flags
            or "low_relevance_confidence_in_selected_cluster" in flags
        ):
            state = NewsEvidenceState.DEGRADED_DATA
        elif len(providers) >= config.multi_source_provider_count:
            state = NewsEvidenceState.MULTI_SOURCE_CONFIRMED
        else:
            state = NewsEvidenceState.SINGLE_SOURCE_CONTEXT
        if high_quality_providers == set():
            flags.append("no_official_or_primary_source_in_selected_cluster")

    analysis = _analysis(
        asset=asset,
        as_of_ms=as_of_ms,
        state=state,
        event_cluster_key=selected_key,
        consensus_category=consensus,
        observations=selected,
        metrics=metrics,
        flags=tuple(flags),
    )
    return _freeze(analysis, selected)


def _reject_duplicates(observations: tuple[NewsEventObservation, ...]) -> None:
    identities = tuple(item.news_identity for item in observations)
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate news event identity")
    provider_keys = tuple(
        (item.source_provider, item.provider_article_id)
        for item in observations
    )
    if len(provider_keys) != len(set(provider_keys)):
        raise ValueError("duplicate news provider/article identity")


def _unresolved(
    *,
    asset: str,
    as_of_ms: int,
    flags: tuple[str, ...],
) -> NewsEvidenceAnalysis:
    payload = {
        "asset": asset,
        "as_of_ms": as_of_ms,
        "consensus_category": None,
        "consumed_news_identities": (),
        "engine_version": NEWS_EVENT_ENGINE_VERSION,
        "event_cluster_key": None,
        "metrics": None,
        "state": NewsEvidenceState.UNRESOLVED,
        "uncertainty_flags": flags,
    }
    return NewsEvidenceAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=NEWS_EVENT_ENGINE_VERSION,
        asset=asset,
        as_of_ms=as_of_ms,
        state=NewsEvidenceState.UNRESOLVED,
        event_cluster_key=None,
        consensus_category=None,
        consumed_news_identities=(),
        metrics=None,
        uncertainty_flags=flags,
    )


def _analysis(
    *,
    asset: str,
    as_of_ms: int,
    state: NewsEvidenceState,
    event_cluster_key: str,
    consensus_category: EventCategory | None,
    observations: tuple[NewsEventObservation, ...],
    metrics: NewsEvidenceMetrics,
    flags: tuple[str, ...],
) -> NewsEvidenceAnalysis:
    ids = tuple(sorted(item.news_identity for item in observations))
    payload = {
        "asset": asset,
        "as_of_ms": as_of_ms,
        "consensus_category": consensus_category,
        "consumed_news_identities": ids,
        "engine_version": NEWS_EVENT_ENGINE_VERSION,
        "event_cluster_key": event_cluster_key,
        "metrics": metrics,
        "state": state,
        "uncertainty_flags": flags,
    }
    return NewsEvidenceAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=NEWS_EVENT_ENGINE_VERSION,
        asset=asset,
        as_of_ms=as_of_ms,
        state=state,
        event_cluster_key=event_cluster_key,
        consensus_category=consensus_category,
        consumed_news_identities=ids,
        metrics=metrics,
        uncertainty_flags=flags,
    )


def _freeze(
    analysis: NewsEvidenceAnalysis,
    observations: tuple[NewsEventObservation, ...],
) -> NewsEvidenceFreeze:
    payload = {
        "analysis_identity": analysis.evidence_identity,
        "news_identities": [item.news_identity for item in observations],
        "schema_version": NEWS_EVENT_FREEZE_SCHEMA_VERSION,
    }
    return NewsEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=NEWS_EVENT_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        observations=observations,
    )


def _analysis_payload(analysis: NewsEvidenceAnalysis) -> dict[str, object]:
    return {
        "asset": analysis.asset,
        "as_of_ms": analysis.as_of_ms,
        "consensus_category": analysis.consensus_category,
        "consumed_news_identities": analysis.consumed_news_identities,
        "engine_version": analysis.engine_version,
        "event_cluster_key": analysis.event_cluster_key,
        "metrics": analysis.metrics,
        "state": analysis.state,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze_payload(freeze: NewsEvidenceFreeze) -> dict[str, object]:
    return {
        "analysis_identity": freeze.analysis.evidence_identity,
        "news_identities": [item.news_identity for item in freeze.observations],
        "schema_version": freeze.schema_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
