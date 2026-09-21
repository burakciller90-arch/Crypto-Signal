from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_sha256

_DAY_MS = 24 * 60 * 60 * 1000


class SentimentScope(StrEnum):
    BITCOIN = "bitcoin"


class SentimentClassification(StrEnum):
    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"


@dataclass(frozen=True, slots=True)
class FearGreedSnapshot:
    snapshot_identity: str
    scope: SentimentScope
    value: int
    classification: SentimentClassification
    provider_timestamp_ms: int
    observed_at_ms: int
    source: DataSource
    adapter_version: str
    attribution: str
    temporal_semantic: str = "ingestion_time_snapshot"

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "fear-greed snapshot identity")
        if not 0 <= self.value <= 100:
            raise ValueError("fear-greed value must be inside [0,100]")
        if min(self.provider_timestamp_ms, self.observed_at_ms) < 0:
            raise ValueError("fear-greed timestamps must be non-negative")
        if self.provider_timestamp_ms > self.observed_at_ms:
            raise ValueError("fear-greed provider timestamp cannot postdate observation")
        if self.source is not DataSource.REST:
            raise ValueError("fear-greed v1 requires REST source")
        if not self.adapter_version.strip():
            raise ValueError("fear-greed adapter_version must be non-empty")
        if self.attribution != "alternative.me":
            raise ValueError("fear-greed attribution must identify alternative.me")
        if self.temporal_semantic != "ingestion_time_snapshot":
            raise ValueError("unsupported fear-greed temporal semantic")
        if self.snapshot_identity != canonical_sha256(fear_greed_snapshot_payload(self)):
            raise ValueError("fear-greed snapshot identity mismatch")


@dataclass(frozen=True, slots=True)
class PageviewDailyRecord:
    record_identity: str
    project: str
    article: str
    day_start_ms: int
    views: int
    access: str
    agent: str

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "pageview record identity")
        if not self.project.strip() or not self.article.strip():
            raise ValueError("pageview project/article must be non-empty")
        if self.day_start_ms < 0 or self.day_start_ms % _DAY_MS != 0:
            raise ValueError("pageview day_start_ms must be UTC-day aligned")
        if self.views < 0:
            raise ValueError("pageview views cannot be negative")
        if not self.access.strip() or not self.agent.strip():
            raise ValueError("pageview access/agent must be non-empty")
        if self.record_identity != canonical_sha256(pageview_daily_record_payload(self)):
            raise ValueError("pageview record identity mismatch")


@dataclass(frozen=True, slots=True)
class PageviewWindowObservation:
    observation_identity: str
    project: str
    article: str
    observed_at_ms: int
    records: tuple[PageviewDailyRecord, ...]
    source: DataSource
    adapter_version: str
    temporal_semantic: str = "ingestion_time_snapshot"

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "pageview observation identity")
        if not self.project.strip() or not self.article.strip():
            raise ValueError("pageview observation project/article must be non-empty")
        if self.observed_at_ms < 0:
            raise ValueError("pageview observed_at_ms must be non-negative")
        if not self.records:
            raise ValueError("pageview observation cannot be empty")
        if len(self.records) > 30:
            raise ValueError("pageview observation cannot exceed 30 daily records")
        for record in self.records:
            if (record.project, record.article) != (self.project, self.article):
                raise ValueError("pageview record context mismatch")
        if any(
            newer.day_start_ms != older.day_start_ms + _DAY_MS
            for older, newer in pairwise(self.records)
        ):
            raise ValueError("pageview daily records must be contiguous and ascending")
        if self.records[-1].day_start_ms + _DAY_MS > self.observed_at_ms:
            raise ValueError("pageview latest day must be complete by observation time")
        if self.source is not DataSource.REST:
            raise ValueError("pageview v1 requires REST source")
        if not self.adapter_version.strip():
            raise ValueError("pageview adapter_version must be non-empty")
        if self.temporal_semantic != "ingestion_time_snapshot":
            raise ValueError("unsupported pageview temporal semantic")
        if self.observation_identity != canonical_sha256(
            pageview_window_observation_payload(self)
        ):
            raise ValueError("pageview observation identity mismatch")


def build_fear_greed_snapshot(
    *,
    scope: SentimentScope,
    value: int,
    classification: SentimentClassification,
    provider_timestamp_ms: int,
    observed_at_ms: int,
    source: DataSource,
    adapter_version: str,
    attribution: str = "alternative.me",
) -> FearGreedSnapshot:
    payload = {
        "adapter_version": adapter_version,
        "attribution": attribution,
        "classification": classification,
        "observed_at_ms": observed_at_ms,
        "provider_timestamp_ms": provider_timestamp_ms,
        "scope": scope,
        "source": source,
        "temporal_semantic": "ingestion_time_snapshot",
        "value": value,
    }
    return FearGreedSnapshot(
        snapshot_identity=canonical_sha256(payload),
        scope=scope,
        value=value,
        classification=classification,
        provider_timestamp_ms=provider_timestamp_ms,
        observed_at_ms=observed_at_ms,
        source=source,
        adapter_version=adapter_version,
        attribution=attribution,
    )


def build_pageview_daily_record(
    *,
    project: str,
    article: str,
    day_start_ms: int,
    views: int,
    access: str,
    agent: str,
) -> PageviewDailyRecord:
    payload = {
        "access": access,
        "agent": agent,
        "article": article,
        "day_start_ms": day_start_ms,
        "project": project,
        "views": views,
    }
    return PageviewDailyRecord(
        record_identity=canonical_sha256(payload),
        project=project,
        article=article,
        day_start_ms=day_start_ms,
        views=views,
        access=access,
        agent=agent,
    )


def build_pageview_window_observation(
    *,
    project: str,
    article: str,
    observed_at_ms: int,
    records: tuple[PageviewDailyRecord, ...],
    source: DataSource,
    adapter_version: str,
) -> PageviewWindowObservation:
    payload = {
        "adapter_version": adapter_version,
        "article": article,
        "observed_at_ms": observed_at_ms,
        "project": project,
        "record_identities": [item.record_identity for item in records],
        "source": source,
        "temporal_semantic": "ingestion_time_snapshot",
    }
    return PageviewWindowObservation(
        observation_identity=canonical_sha256(payload),
        project=project,
        article=article,
        observed_at_ms=observed_at_ms,
        records=records,
        source=source,
        adapter_version=adapter_version,
    )


def fear_greed_snapshot_payload(snapshot: FearGreedSnapshot) -> dict[str, object]:
    return {
        "adapter_version": snapshot.adapter_version,
        "attribution": snapshot.attribution,
        "classification": snapshot.classification,
        "observed_at_ms": snapshot.observed_at_ms,
        "provider_timestamp_ms": snapshot.provider_timestamp_ms,
        "scope": snapshot.scope,
        "source": snapshot.source,
        "temporal_semantic": snapshot.temporal_semantic,
        "value": snapshot.value,
    }


def pageview_daily_record_payload(record: PageviewDailyRecord) -> dict[str, object]:
    return {
        "access": record.access,
        "agent": record.agent,
        "article": record.article,
        "day_start_ms": record.day_start_ms,
        "project": record.project,
        "views": record.views,
    }


def pageview_window_observation_payload(
    observation: PageviewWindowObservation,
) -> dict[str, object]:
    return {
        "adapter_version": observation.adapter_version,
        "article": observation.article,
        "observed_at_ms": observation.observed_at_ms,
        "project": observation.project,
        "record_identities": [
            item.record_identity for item in observation.records
        ],
        "source": observation.source,
        "temporal_semantic": observation.temporal_semantic,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
