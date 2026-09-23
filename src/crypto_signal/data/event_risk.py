from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_sha256

STRUCTURED_EVENT_SCHEMA_VERSION = "structured-event-v1/1"
EVENT_CALENDAR_COVERAGE_SCHEMA_VERSION = "event-calendar-coverage-v1/1"


class EventCategory(StrEnum):
    INFLATION = "inflation"
    CENTRAL_BANK = "central_bank"
    EMPLOYMENT = "employment"
    REGULATORY = "regulatory"
    EXCHANGE_SECURITY = "exchange_security"
    LISTING = "listing"
    DELISTING = "delisting"
    OTHER = "other"


class EventSourceQuality(StrEnum):
    OFFICIAL = "official"
    PRIMARY_PROVIDER = "primary_provider"
    SECONDARY_AGGREGATOR = "secondary_aggregator"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class StructuredEventObservation:
    event_identity: str
    schema_version: str
    provider_event_id: str
    title: str
    category: EventCategory
    scheduled_at_ms: int
    affected_assets: tuple[str, ...]
    source_provider: str
    source_quality: EventSourceQuality
    source: DataSource
    source_timestamp_ms: int
    ingested_at_ms: int
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.event_identity, "structured event identity")
        if self.schema_version != STRUCTURED_EVENT_SCHEMA_VERSION:
            raise ValueError("unsupported structured event schema")
        for value, label in (
            (self.provider_event_id, "provider_event_id"),
            (self.title, "title"),
            (self.source_provider, "source_provider"),
            (self.adapter_version, "adapter_version"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if min(self.scheduled_at_ms, self.source_timestamp_ms, self.ingested_at_ms) < 0:
            raise ValueError("structured event timestamps must be non-negative")
        if self.ingested_at_ms < self.source_timestamp_ms:
            raise ValueError("structured event ingestion cannot predate source timestamp")
        if tuple(sorted(set(self.affected_assets))) != self.affected_assets:
            raise ValueError("affected assets must be unique and sorted")
        for asset in self.affected_assets:
            if not asset or asset != asset.upper():
                raise ValueError("affected assets must be uppercase")
        if self.event_identity != canonical_sha256(structured_event_payload(self)):
            raise ValueError("structured event identity mismatch")


@dataclass(frozen=True, slots=True)
class EventCalendarCoverage:
    coverage_identity: str
    schema_version: str
    coverage_start_ms: int
    coverage_end_ms: int
    categories: tuple[EventCategory, ...]
    source_provider: str
    source_quality: EventSourceQuality
    source: DataSource
    observed_at_ms: int
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.coverage_identity, "event calendar coverage identity")
        if self.schema_version != EVENT_CALENDAR_COVERAGE_SCHEMA_VERSION:
            raise ValueError("unsupported event calendar coverage schema")
        if min(self.coverage_start_ms, self.coverage_end_ms, self.observed_at_ms) < 0:
            raise ValueError("event calendar coverage timestamps must be non-negative")
        if self.coverage_end_ms < self.coverage_start_ms:
            raise ValueError("event calendar coverage end precedes start")
        if not self.source_provider.strip() or not self.adapter_version.strip():
            raise ValueError("event calendar coverage provider/adapter must be non-empty")
        expected_categories = tuple(sorted(set(self.categories), key=lambda item: item.value))
        if not expected_categories or expected_categories != self.categories:
            raise ValueError("event calendar coverage categories must be unique and sorted")
        if self.coverage_identity != canonical_sha256(event_calendar_coverage_payload(self)):
            raise ValueError("event calendar coverage identity mismatch")


def build_structured_event_observation(
    *,
    provider_event_id: str,
    title: str,
    category: EventCategory,
    scheduled_at_ms: int,
    affected_assets: tuple[str, ...],
    source_provider: str,
    source_quality: EventSourceQuality,
    source: DataSource,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    adapter_version: str,
) -> StructuredEventObservation:
    assets = tuple(sorted(set(affected_assets)))
    payload = {
        "adapter_version": adapter_version,
        "affected_assets": assets,
        "category": category,
        "ingested_at_ms": ingested_at_ms,
        "provider_event_id": provider_event_id,
        "scheduled_at_ms": scheduled_at_ms,
        "schema_version": STRUCTURED_EVENT_SCHEMA_VERSION,
        "source": source,
        "source_provider": source_provider,
        "source_quality": source_quality,
        "source_timestamp_ms": source_timestamp_ms,
        "title": title,
    }
    return StructuredEventObservation(
        event_identity=canonical_sha256(payload),
        schema_version=STRUCTURED_EVENT_SCHEMA_VERSION,
        provider_event_id=provider_event_id,
        title=title,
        category=category,
        scheduled_at_ms=scheduled_at_ms,
        affected_assets=assets,
        source_provider=source_provider,
        source_quality=source_quality,
        source=source,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=adapter_version,
    )


def build_event_calendar_coverage(
    *,
    coverage_start_ms: int,
    coverage_end_ms: int,
    categories: tuple[EventCategory, ...],
    source_provider: str,
    source_quality: EventSourceQuality,
    source: DataSource,
    observed_at_ms: int,
    adapter_version: str,
) -> EventCalendarCoverage:
    normalized_categories = tuple(sorted(set(categories), key=lambda item: item.value))
    payload = {
        "adapter_version": adapter_version,
        "categories": normalized_categories,
        "coverage_end_ms": coverage_end_ms,
        "coverage_start_ms": coverage_start_ms,
        "observed_at_ms": observed_at_ms,
        "schema_version": EVENT_CALENDAR_COVERAGE_SCHEMA_VERSION,
        "source": source,
        "source_provider": source_provider,
        "source_quality": source_quality,
    }
    return EventCalendarCoverage(
        coverage_identity=canonical_sha256(payload),
        schema_version=EVENT_CALENDAR_COVERAGE_SCHEMA_VERSION,
        coverage_start_ms=coverage_start_ms,
        coverage_end_ms=coverage_end_ms,
        categories=normalized_categories,
        source_provider=source_provider,
        source_quality=source_quality,
        source=source,
        observed_at_ms=observed_at_ms,
        adapter_version=adapter_version,
    )


def structured_event_payload(
    event: StructuredEventObservation,
) -> dict[str, object]:
    return {
        "adapter_version": event.adapter_version,
        "affected_assets": event.affected_assets,
        "category": event.category,
        "ingested_at_ms": event.ingested_at_ms,
        "provider_event_id": event.provider_event_id,
        "scheduled_at_ms": event.scheduled_at_ms,
        "schema_version": event.schema_version,
        "source": event.source,
        "source_provider": event.source_provider,
        "source_quality": event.source_quality,
        "source_timestamp_ms": event.source_timestamp_ms,
        "title": event.title,
    }


def event_calendar_coverage_payload(
    coverage: EventCalendarCoverage,
) -> dict[str, object]:
    return {
        "adapter_version": coverage.adapter_version,
        "categories": coverage.categories,
        "coverage_end_ms": coverage.coverage_end_ms,
        "coverage_start_ms": coverage.coverage_start_ms,
        "observed_at_ms": coverage.observed_at_ms,
        "schema_version": coverage.schema_version,
        "source": coverage.source,
        "source_provider": coverage.source_provider,
        "source_quality": coverage.source_quality,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
