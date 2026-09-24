from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from ops.run_market_tape_stream import _MarketTapeCounterCache


class _BlockingStore:
    def __init__(
        self,
        *,
        release: threading.Event,
        started: threading.Event,
        total: int,
    ) -> None:
        self._release = release
        self._started = started
        self._total = total

    def counts(self) -> SimpleNamespace:
        self._started.set()
        if not self._release.wait(timeout=2):
            raise TimeoutError("test counter refresh release timeout")
        return SimpleNamespace(total=self._total)


class _BlockingRawStore:
    def __init__(
        self,
        *,
        release: threading.Event,
        total: int,
    ) -> None:
        self._release = release
        self._total = total

    def count(self) -> int:
        if not self._release.wait(timeout=2):
            raise TimeoutError("test raw counter refresh release timeout")
        return self._total


@pytest.mark.asyncio
async def test_counter_cache_remains_readable_while_heavy_refresh_runs() -> None:
    release = threading.Event()
    started = threading.Event()
    cache = _MarketTapeCounterCache(
        normalized_rows_total=11,
        raw_rows_total=22,
    )
    store = _BlockingStore(release=release, started=started, total=33)
    raw_store = _BlockingRawStore(release=release, total=44)

    refresh = asyncio.create_task(
        cache.refresh(store=store, raw_store=raw_store)  # type: ignore[arg-type]
    )
    started_ok = await asyncio.to_thread(started.wait, 1)
    assert started_ok is True

    assert cache.snapshot() == (11, 22)
    assert refresh.done() is False

    release.set()
    await refresh

    assert cache.snapshot() == (33, 44)
