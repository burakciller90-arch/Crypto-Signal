from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_signal.ledger.serialization import canonical_json
from crypto_signal.product.intelligence_stream_models import REAL_CAPITAL
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamCursor,
    StreamMessageQuery,
    decode_stream_cursor,
    encode_stream_cursor,
)

STREAM_LIVE_SCHEMA_VERSION = "intelligence-stream-live-v1/1"
STREAM_LIVE_EVENT_NAME = "message"
STREAM_LIVE_READY_EVENT_NAME = "ready"
STREAM_LIVE_HEARTBEAT_COMMENT = "crypto-signal-stream-keepalive"
STREAM_LIVE_DEFAULT_BATCH_LIMIT = 100
STREAM_LIVE_MAX_BATCH_LIMIT = 200

_STREAM_ORIGIN_CURSOR = StreamCursor(
    event_at_ms=0,
    narrative_identity="0" * 64,
)


@dataclass(frozen=True, slots=True)
class StreamLivePoll:
    items: tuple[dict[str, Any], ...]
    cursor: str
    has_more: bool
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = STREAM_LIVE_SCHEMA_VERSION


class IntelligenceStreamLiveSession:
    """Cursor state for one read-only SSE/polling consumer."""

    def __init__(
        self,
        reader: IntelligenceStreamReadModel,
        *,
        after: str | None = None,
    ) -> None:
        self.reader = reader
        if after is not None:
            decode_stream_cursor(after)
            self._cursor = after
        else:
            latest = reader.latest_cursor()
            self._cursor = (
                latest
                if latest is not None
                else encode_stream_cursor(_STREAM_ORIGIN_CURSOR)
            )

    @property
    def cursor(self) -> str:
        return self._cursor

    def poll(
        self,
        *,
        limit: int = STREAM_LIVE_DEFAULT_BATCH_LIMIT,
    ) -> StreamLivePoll:
        if limit < 1 or limit > STREAM_LIVE_MAX_BATCH_LIMIT:
            raise ValueError(
                f"Stream live batch limit must be inside 1..{STREAM_LIVE_MAX_BATCH_LIMIT}"
            )
        page = self.reader.read_messages(
            StreamMessageQuery(
                limit=limit,
                after=decode_stream_cursor(self._cursor),
            )
        )
        items = page.items
        if items:
            newest_cursor = page.newest_cursor
            if newest_cursor is None:
                raise ValueError("Stream live page with items must expose newest cursor")
            self._cursor = newest_cursor
        return StreamLivePoll(
            items=items,
            cursor=self._cursor,
            has_more=page.has_more,
        )


def resolve_stream_resume_cursor(
    *,
    after: str | None,
    last_event_id: str | None,
) -> str | None:
    if after is not None:
        decode_stream_cursor(after)
    if last_event_id is not None:
        decode_stream_cursor(last_event_id)
    if after is not None and last_event_id is not None and after != last_event_id:
        raise ValueError("Stream resume cursors disagree")
    return after if after is not None else last_event_id


def stream_ready_sse(cursor: str) -> str:
    decode_stream_cursor(cursor)
    return _format_sse(
        event=STREAM_LIVE_READY_EVENT_NAME,
        event_id=cursor,
        data={
            "cursor": cursor,
            "read_only": True,
            "real_capital": REAL_CAPITAL,
            "schema_version": STREAM_LIVE_SCHEMA_VERSION,
        },
    )


def stream_message_sse(item: dict[str, Any]) -> tuple[str, str]:
    narrative_identity = item.get("narrative_identity")
    event_at_ms = item.get("event_at_ms")
    if not isinstance(narrative_identity, str):
        raise ValueError("Stream live item missing narrative identity")
    if not isinstance(event_at_ms, int) or event_at_ms < 0:
        raise ValueError("Stream live item missing event time")
    cursor = encode_stream_cursor(
        StreamCursor(
            event_at_ms=event_at_ms,
            narrative_identity=narrative_identity,
        )
    )
    return (
        _format_sse(
            event=STREAM_LIVE_EVENT_NAME,
            event_id=cursor,
            data=item,
        ),
        cursor,
    )


def stream_heartbeat_sse() -> str:
    return f": {STREAM_LIVE_HEARTBEAT_COMMENT}\n\n"


def _format_sse(
    *,
    event: str,
    event_id: str,
    data: dict[str, Any],
) -> str:
    if "\n" in event or "\r" in event:
        raise ValueError("Stream SSE event name must be one line")
    decode_stream_cursor(event_id)
    payload = canonical_json(data)
    return (
        f"id: {event_id}\n"
        f"event: {event}\n"
        f"data: {payload}\n\n"
    )
