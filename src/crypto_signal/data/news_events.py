from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.data.event_risk import EventCategory, EventSourceQuality
from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_sha256

NEWS_EVENT_SCHEMA_VERSION = "news-event-v1/1"


@dataclass(frozen=True, slots=True)
class NewsEventObservation:
    news_identity: str
    schema_version: str
    provider_article_id: str
    event_cluster_key: str
    headline: str
    category: EventCategory
    affected_assets: tuple[str, ...]
    published_at_ms: int
    source_provider: str
    source_quality: EventSourceQuality
    source: DataSource
    source_timestamp_ms: int
    ingested_at_ms: int
    extraction_method: str
    extraction_version: str
    relevance_confidence_0_1: Decimal
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.news_identity, "news event identity")
        if self.schema_version != NEWS_EVENT_SCHEMA_VERSION:
            raise ValueError("unsupported news event schema")
        for text_value, label in (
            (self.provider_article_id, "provider_article_id"),
            (self.event_cluster_key, "event_cluster_key"),
            (self.headline, "headline"),
            (self.source_provider, "source_provider"),
            (self.extraction_method, "extraction_method"),
            (self.extraction_version, "extraction_version"),
            (self.adapter_version, "adapter_version"),
        ):
            if not text_value.strip():
                raise ValueError(f"{label} must be non-empty")
        if min(self.published_at_ms, self.source_timestamp_ms, self.ingested_at_ms) < 0:
            raise ValueError("news event timestamps must be non-negative")
        if self.source_timestamp_ms < self.published_at_ms:
            raise ValueError("news source timestamp cannot predate publication")
        if self.ingested_at_ms < self.source_timestamp_ms:
            raise ValueError("news ingestion cannot predate source timestamp")
        assets = tuple(sorted(set(self.affected_assets)))
        if assets != self.affected_assets:
            raise ValueError("news affected assets must be unique and sorted")
        for asset in self.affected_assets:
            if not asset or asset != asset.upper():
                raise ValueError("news affected assets must be uppercase")
        confidence = self.relevance_confidence_0_1
        if (
            confidence.is_nan()
            or confidence.is_infinite()
            or not Decimal(0) <= confidence <= Decimal(1)
        ):
            raise ValueError("news relevance confidence must be inside [0,1]")
        if self.news_identity != canonical_sha256(news_event_payload(self)):
            raise ValueError("news event identity mismatch")


def build_news_event_observation(
    *,
    provider_article_id: str,
    event_cluster_key: str,
    headline: str,
    category: EventCategory,
    affected_assets: tuple[str, ...],
    published_at_ms: int,
    source_provider: str,
    source_quality: EventSourceQuality,
    source: DataSource,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    extraction_method: str,
    extraction_version: str,
    relevance_confidence_0_1: Decimal,
    adapter_version: str,
) -> NewsEventObservation:
    assets = tuple(sorted(set(affected_assets)))
    payload = {
        "adapter_version": adapter_version,
        "affected_assets": assets,
        "category": category,
        "event_cluster_key": event_cluster_key,
        "extraction_method": extraction_method,
        "extraction_version": extraction_version,
        "headline": headline,
        "ingested_at_ms": ingested_at_ms,
        "provider_article_id": provider_article_id,
        "published_at_ms": published_at_ms,
        "relevance_confidence_0_1": relevance_confidence_0_1,
        "schema_version": NEWS_EVENT_SCHEMA_VERSION,
        "source": source,
        "source_provider": source_provider,
        "source_quality": source_quality,
        "source_timestamp_ms": source_timestamp_ms,
    }
    return NewsEventObservation(
        news_identity=canonical_sha256(payload),
        schema_version=NEWS_EVENT_SCHEMA_VERSION,
        provider_article_id=provider_article_id,
        event_cluster_key=event_cluster_key,
        headline=headline,
        category=category,
        affected_assets=assets,
        published_at_ms=published_at_ms,
        source_provider=source_provider,
        source_quality=source_quality,
        source=source,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        extraction_method=extraction_method,
        extraction_version=extraction_version,
        relevance_confidence_0_1=relevance_confidence_0_1,
        adapter_version=adapter_version,
    )


def news_event_payload(observation: NewsEventObservation) -> dict[str, object]:
    return {
        "adapter_version": observation.adapter_version,
        "affected_assets": observation.affected_assets,
        "category": observation.category,
        "event_cluster_key": observation.event_cluster_key,
        "extraction_method": observation.extraction_method,
        "extraction_version": observation.extraction_version,
        "headline": observation.headline,
        "ingested_at_ms": observation.ingested_at_ms,
        "provider_article_id": observation.provider_article_id,
        "published_at_ms": observation.published_at_ms,
        "relevance_confidence_0_1": observation.relevance_confidence_0_1,
        "schema_version": observation.schema_version,
        "source": observation.source,
        "source_provider": observation.source_provider,
        "source_quality": observation.source_quality,
        "source_timestamp_ms": observation.source_timestamp_ms,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
