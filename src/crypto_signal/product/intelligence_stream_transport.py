from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from crypto_signal.ledger.serialization import canonical_json
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamCursor,
    StreamMessageQuery,
    StreamReadModelError,
    decode_stream_cursor,
    encode_stream_cursor,
)

STREAM_SSE_EVENT_NAME = "message"
STREAM_SSE_RETRY_MS = 3000
STREAM_SSE_BATCH_LIMIT = 200
_STREAM_ORIGIN_CURSOR = encode_stream_cursor(
    StreamCursor(event_at_ms=0, narrative_identity="0" * 64)
)


@dataclass(frozen=True, slots=True)
class StreamLiveEvent:
    event_id: str
    data: dict[str, Any]
    event_name: str = STREAM_SSE_EVENT_NAME

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("Stream live event id cannot be blank")
        decode_stream_cursor(self.event_id)
        if not self.event_name.strip():
            raise ValueError("Stream live event name cannot be blank")


@dataclass(frozen=True, slots=True)
class StreamLiveBatch:
    events: tuple[StreamLiveEvent, ...]
    next_cursor: str | None
    has_more: bool

    def __post_init__(self) -> None:
        if self.next_cursor is not None:
            decode_stream_cursor(self.next_cursor)
        if self.events:
            if self.next_cursor != self.events[-1].event_id:
                raise ValueError("Stream live batch cursor must match final event")
        elif self.has_more:
            raise ValueError("empty Stream live batch cannot claim more data")


def resolve_stream_resume_cursor(
    *,
    reader: IntelligenceStreamReadModel,
    after: str | None,
    last_event_id: str | None,
) -> str | None:
    """Resolve an SSE resume cursor without permitting ambiguous replay semantics.

    On a first connection with no explicit cursor, the transport tails from the
    latest immutable narrative instead of replaying historical messages.
    """
    after_cursor = None if after is None else decode_stream_cursor(after)
    last_cursor = (
        None if last_event_id is None else decode_stream_cursor(last_event_id)
    )
    explicit = after
    if last_cursor is not None and (
        after_cursor is None
        or (last_cursor.event_at_ms, last_cursor.narrative_identity)
        >= (after_cursor.event_at_ms, after_cursor.narrative_identity)
    ):
        explicit = last_event_id
    if explicit is not None:
        return explicit
    latest = reader.latest_cursor()
    return latest if latest is not None else _STREAM_ORIGIN_CURSOR


def read_stream_live_batch(
    reader: IntelligenceStreamReadModel,
    base_query: StreamMessageQuery,
    *,
    after_cursor: str | None,
) -> StreamLiveBatch:
    if base_query.before is not None or base_query.after is not None:
        raise ValueError("Stream live base query must not bind before/after")
    cursor = None if after_cursor is None else decode_stream_cursor(after_cursor)
    page = reader.read_messages(
        replace(
            base_query,
            limit=min(base_query.limit, STREAM_SSE_BATCH_LIMIT),
            after=cursor,
        )
    )
    events = tuple(
        StreamLiveEvent(
            event_id=cursor_for_stream_record(item),
            data=item,
        )
        for item in page.items
    )
    return StreamLiveBatch(
        events=events,
        next_cursor=(
            after_cursor
            if not events
            else events[-1].event_id
        ),
        has_more=page.has_more,
    )


def cursor_for_stream_record(record: dict[str, Any]) -> str:
    event_at_ms = record.get("event_at_ms")
    narrative_identity = record.get("narrative_identity")
    if not isinstance(event_at_ms, int) or event_at_ms < 0:
        raise StreamReadModelError("Stream live record missing event_at_ms")
    if not isinstance(narrative_identity, str):
        raise StreamReadModelError("Stream live record missing narrative_identity")
    return encode_stream_cursor(
        StreamCursor(
            event_at_ms=event_at_ms,
            narrative_identity=narrative_identity,
        )
    )


def encode_stream_sse_event(event: StreamLiveEvent) -> str:
    payload = canonical_json(event.data)
    return (
        f"id: {event.event_id}\n"
        f"event: {event.event_name}\n"
        f"data: {payload}\n\n"
    )


def encode_stream_sse_retry() -> str:
    return f"retry: {STREAM_SSE_RETRY_MS}\n\n"


def encode_stream_sse_heartbeat(*, now_ms: int) -> str:
    if now_ms < 0:
        raise ValueError("Stream SSE heartbeat time must be non-negative")
    return f": heartbeat {now_ms}\n\n"
