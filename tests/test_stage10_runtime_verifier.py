from __future__ import annotations

from typing import Any

import pytest

from ops import verify_stage10_integrated as stage10


class _FakeResponse:
    status = 200

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"status":"ok"}'


def test_get_json_retries_transient_timeout_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_urlopen(
        request: Any,
        timeout: float,
    ) -> _FakeResponse:
        del timeout
        calls.append(request.full_url)
        if len(calls) == 1:
            raise TimeoutError("transient")
        return _FakeResponse()

    monkeypatch.setattr(stage10.urllib.request, "urlopen", fake_urlopen)

    payload = stage10._get_json(
        "http://127.0.0.1:48700",
        "/api/paper/mission-control",
        timeout_seconds=1,
        attempts=3,
        retry_delay_seconds=0,
    )

    assert payload == {"status": "ok"}
    assert len(calls) == 2


def test_get_json_repeated_timeout_fails_closed_with_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_urlopen(
        request: Any,
        timeout: float,
    ) -> _FakeResponse:
        nonlocal calls
        del request, timeout
        calls += 1
        raise TimeoutError("still slow")

    monkeypatch.setattr(stage10.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(
        RuntimeError,
        match=r"/api/market-radar failed after 2 attempts",
    ):
        stage10._get_json(
            "http://127.0.0.1:48700",
            "/api/market-radar",
            timeout_seconds=1,
            attempts=2,
            retry_delay_seconds=0,
        )

    assert calls == 2


@pytest.mark.parametrize(
    ("timeout_seconds", "attempts", "retry_delay_seconds", "message"),
    (
        (0.0, 1, 0.0, "timeout_seconds must be positive"),
        (1.0, 0, 0.0, "attempts must be positive"),
        (1.0, 1, -1.0, "retry_delay_seconds cannot be negative"),
    ),
)
def test_get_json_rejects_invalid_retry_policy(
    timeout_seconds: float,
    attempts: int,
    retry_delay_seconds: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        stage10._get_json(
            "http://127.0.0.1:48700",
            "/api/health",
            timeout_seconds=timeout_seconds,
            attempts=attempts,
            retry_delay_seconds=retry_delay_seconds,
        )
