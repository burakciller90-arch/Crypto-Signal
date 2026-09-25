from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Any

from crypto_signal.ledger.serialization import canonical_json
from crypto_signal.product.intelligence_stream_models import REAL_CAPITAL
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamCursor,
    StreamMessageQuery,
    StreamReadModelError,
    decode_stream_cursor,
    encode_stream_cursor,
)

STREAM_REALTIME_SCHEMA_VERSION = "intelligence-stream-realtime-v1/1"
DEFAULT_STREAM_POLL_INTERVAL_MS = 500
DEFAULT_STREAM_HEARTBEAT_MS = 15_000
DEFAULT_STREAM_SSE_RETRY_MS = 2_000
DEFAULT_STREAM_LIVE_BATCH_LIMIT = 100
MAX_STREAM_LIVE_BATCH_LIMIT = 200


@dataclass(frozen=True, slots=True)
class StreamLiveBatch:
    items: tuple[dict[str, Any], ...]
    start_cursor: str
    end_cursor: str
    has_more: bool
    schema_version: str = STREAM_REALTIME_SCHEMA_VERSION
    read_only: bool = True
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        decode_stream_cursor(self.start_cursor)
        decode_stream_cursor(self.end_cursor)
        if self.schema_version != STREAM_REALTIME_SCHEMA_VERSION:
            raise ValueError("unsupported Stream realtime schema")
        if not self.read_only:
            raise ValueError("Stream realtime transport must remain read-only")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")


@dataclass(frozen=True, slots=True)
class StreamRealtimeConfig:
    poll_interval_ms: int = DEFAULT_STREAM_POLL_INTERVAL_MS
    heartbeat_ms: int = DEFAULT_STREAM_HEARTBEAT_MS
    retry_ms: int = DEFAULT_STREAM_SSE_RETRY_MS
    batch_limit: int = DEFAULT_STREAM_LIVE_BATCH_LIMIT

    def __post_init__(self) -> None:
        if self.poll_interval_ms < 100 or self.poll_interval_ms > 10_000:
            raise ValueError("Stream poll interval must be inside 100..10000 ms")
        if self.heartbeat_ms < 1_000 or self.heartbeat_ms > 120_000:
            raise ValueError("Stream heartbeat must be inside 1000..120000 ms")
        if self.retry_ms < 250 or self.retry_ms > 60_000:
            raise ValueError("Stream SSE retry must be inside 250..60000 ms")
        if self.batch_limit < 1 or self.batch_limit > MAX_STREAM_LIVE_BATCH_LIMIT:
            raise ValueError(
                f"Stream live batch limit must be inside 1..{MAX_STREAM_LIVE_BATCH_LIMIT}"
            )


class IntelligenceStreamRealtime:
    """Cursor-based live transport over immutable S5 narrative persistence."""

    def __init__(
        self,
        path: Path,
        *,
        config: StreamRealtimeConfig | None = None,
    ) -> None:
        self.path = path
        self.config = config or StreamRealtimeConfig()
        self.reader = IntelligenceStreamReadModel(path)

    def resolve_start_cursor(self, resume_cursor: str | None) -> str:
        if resume_cursor is None:
            return self.reader.live_start_cursor()
        decoded = decode_stream_cursor(resume_cursor)
        activation_at_ms = self.reader.activation_boundary_ms()
        if decoded.event_at_ms < activation_at_ms:
            raise StreamReadModelError(
                "Stream resume cursor predates activation boundary"
            )
        return encode_stream_cursor(decoded)

    def poll_after(self, cursor: str) -> StreamLiveBatch:
        decoded = decode_stream_cursor(cursor)
        activation_at_ms = self.reader.activation_boundary_ms()
        if decoded.event_at_ms < activation_at_ms:
            raise StreamReadModelError(
                "Stream live cursor predates activation boundary"
            )
        page = self.reader.read_messages(
            StreamMessageQuery(
                limit=self.config.batch_limit,
                after=decoded,
            )
        )
        if not page.items:
            return StreamLiveBatch(
                items=(),
                start_cursor=cursor,
                end_cursor=cursor,
                has_more=False,
            )
        end_cursor = page.newest_cursor
        if end_cursor is None:
            raise StreamReadModelError(
                "Stream live page with items must expose newest cursor"
            )
        return StreamLiveBatch(
            items=page.items,
            start_cursor=cursor,
            end_cursor=end_cursor,
            has_more=page.has_more,
        )

    async def sse_events(
        self,
        *,
        resume_cursor: str | None = None,
    ) -> AsyncIterator[str]:
        cursor = self.resolve_start_cursor(resume_cursor)
        yield encode_sse_ready(
            cursor,
            retry_ms=self.config.retry_ms,
        )
        last_emit_monotonic = time.monotonic()

        while True:
            batch = self.poll_after(cursor)
            if batch.items:
                for item in batch.items:
                    item_cursor = cursor_for_stream_record(item)
                    yield encode_sse_message(
                        item,
                        cursor=item_cursor,
                    )
                    cursor = item_cursor
                    last_emit_monotonic = time.monotonic()
                if batch.has_more:
                    continue

            now = time.monotonic()
            if (
                now - last_emit_monotonic
                >= self.config.heartbeat_ms / 1000
            ):
                yield encode_sse_heartbeat()
                last_emit_monotonic = now
            await asyncio.sleep(self.config.poll_interval_ms / 1000)


def cursor_for_stream_record(record: dict[str, Any]) -> str:
    event_at_ms = record.get("event_at_ms")
    narrative_identity = record.get("narrative_identity")
    if not isinstance(event_at_ms, int) or event_at_ms < 0:
        raise StreamReadModelError(
            "Stream realtime record missing valid event time"
        )
    if not isinstance(narrative_identity, str):
        raise StreamReadModelError(
            "Stream realtime record missing narrative identity"
        )
    try:
        cursor = StreamCursor(
            event_at_ms=event_at_ms,
            narrative_identity=narrative_identity,
        )
    except ValueError as exc:
        raise StreamReadModelError(
            "Stream realtime record has invalid cursor identity"
        ) from exc
    return encode_stream_cursor(cursor)


def encode_sse_ready(cursor: str, *, retry_ms: int) -> str:
    decode_stream_cursor(cursor)
    payload = canonical_json(
        {
            "cursor": cursor,
            "read_only": True,
            "real_capital": REAL_CAPITAL,
            "schema_version": STREAM_REALTIME_SCHEMA_VERSION,
        }
    )
    return (
        f"id: {cursor}\n"
        "event: ready\n"
        f"retry: {retry_ms}\n"
        f"data: {payload}\n\n"
    )


def encode_sse_message(
    message: dict[str, Any],
    *,
    cursor: str,
) -> str:
    decode_stream_cursor(cursor)
    expected_cursor = cursor_for_stream_record(message)
    if cursor != expected_cursor:
        raise StreamReadModelError(
            "Stream SSE cursor/message identity mismatch"
        )
    payload = canonical_json(
        {
            "cursor": cursor,
            "message": message,
            "read_only": True,
            "real_capital": REAL_CAPITAL,
            "schema_version": STREAM_REALTIME_SCHEMA_VERSION,
        }
    )
    return (
        f"id: {cursor}\n"
        "event: message\n"
        f"data: {payload}\n\n"
    )


def encode_sse_heartbeat() -> str:
    return ": heartbeat\n\n"
