from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_narrative import (
    StreamNarrativeRewriteRequest,
    StreamNarrativeText,
)

LOCAL_NARRATIVE_REWRITER_VERSION = "crypto-signal-local-rewriter-v1/1"
_REQUIRED_TEXT_KEYS = frozenset(
    {
        "collapsed_text",
        "simple_text",
        "technical_text",
        "intelligence_text",
        "decision_text",
        "capital_text",
    }
)
_ALLOWED_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class LocalNarrativeRewriteError(RuntimeError):
    """Raised when a local-only narrative rewrite cannot be safely consumed."""


@dataclass(frozen=True, slots=True)
class LocalNarrativeRewriteConfig:
    model: str
    base_url: str = "http://127.0.0.1:11434/v1"
    timeout_seconds: float = 8.0
    temperature: float = 0.25
    max_tokens: int = 1400
    version: str = LOCAL_NARRATIVE_REWRITER_VERSION

    def __post_init__(self) -> None:
        _require_loopback_base_url(self.base_url)
        if not self.model.strip():
            raise ValueError("local narrative model must be non-empty")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 30:
            raise ValueError("local narrative timeout must be inside (0,30]")
        if self.temperature < 0 or self.temperature > 1:
            raise ValueError("local narrative temperature must be inside [0,1]")
        if self.max_tokens < 128 or self.max_tokens > 4096:
            raise ValueError("local narrative max_tokens must be inside 128..4096")
        if self.version != LOCAL_NARRATIVE_REWRITER_VERSION:
            raise ValueError("unsupported local narrative rewriter version")

    @property
    def rewriter_identity(self) -> str:
        return canonical_sha256(
            {
                "base_url": self.base_url,
                "max_tokens": self.max_tokens,
                "model": self.model,
                "temperature": format(self.temperature, ".17g"),
                "timeout_seconds": format(self.timeout_seconds, ".17g"),
                "version": self.version,
            }
        )

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class LocalNarrativeChatTransport(Protocol):
    def post_chat(
        self,
        *,
        url: str,
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        ...


class HttpxLocalNarrativeChatTransport:
    """Bounded HTTP transport that ignores proxy environment and redirects."""

    def post_chat(
        self,
        *,
        url: str,
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        _require_loopback_chat_url(url)
        try:
            with httpx.Client(
                timeout=timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                raw: Any = response.json()
        except httpx.HTTPError as exc:
            raise LocalNarrativeRewriteError(
                "local narrative HTTP request failed"
            ) from exc
        except ValueError as exc:
            raise LocalNarrativeRewriteError(
                "local narrative response was not valid JSON"
            ) from exc
        if not isinstance(raw, dict):
            raise LocalNarrativeRewriteError(
                "local narrative response must be a JSON object"
            )
        return {str(key): value for key, value in raw.items()}


class OpenAICompatibleLocalNarrativeRewriter:
    """Local-only stylistic rewrite adapter for OpenAI-compatible chat servers.

    The model never receives authority to create market facts. Its output is
    parsed into the existing S5 text contract and is later revalidated against
    exact canonical facts by render_stream_narrative().
    """

    def __init__(
        self,
        config: LocalNarrativeRewriteConfig | None = None,
        *,
        transport: LocalNarrativeChatTransport | None = None,
    ) -> None:
        if config is None:
            raise ValueError("local narrative rewriter requires explicit model config")
        self.config = config
        self.transport = transport or HttpxLocalNarrativeChatTransport()

    @property
    def rewriter_identity(self) -> str:
        return self.config.rewriter_identity

    @property
    def rewriter_version(self) -> str:
        return self.config.version

    def rewrite(self, request: StreamNarrativeRewriteRequest) -> StreamNarrativeText:
        payload = _chat_payload(self.config, request)
        response = self.transport.post_chat(
            url=self.config.chat_completions_url,
            payload=payload,
            timeout_seconds=self.config.timeout_seconds,
        )
        content = _assistant_content(response)
        return _parse_rewrite_content(content)


def _chat_payload(
    config: LocalNarrativeRewriteConfig,
    request: StreamNarrativeRewriteRequest,
) -> dict[str, object]:
    protected_values = [
        format(value.normalize(), "f")
        for value in request.protected_numeric_values
    ]
    source_text = {
        "collapsed_text": request.deterministic_text.collapsed_text,
        "simple_text": request.deterministic_text.simple_text,
        "technical_text": request.deterministic_text.technical_text,
        "intelligence_text": request.deterministic_text.intelligence_text,
        "decision_text": request.deterministic_text.decision_text,
        "capital_text": request.deterministic_text.capital_text,
    }
    system = (
        "Sen Crypto Signal'in yerel Türkçe editörüsün. Yeni piyasa analizi yapma. "
        "Yeni rakam, fiyat, yüzde, hedef, seviye, neden, kanıt veya kesinlik ekleme. "
        "Yeni teknik kavram, aktör, haber, piyasa nedeni veya kanıt türü icat etme. "
        "Mevcut anlamı ve yönü tersine çevirme. Yalnız collapsed_text ve simple_text "
        "alanlarını daha doğal, sakin ve profesyonel trader Türkçesiyle yeniden yaz. "
        "technical_text, intelligence_text, decision_text ve capital_text alanlarını "
        "tek karakter dahi değiştirmeden kopyala. collapsed_text tek paragraf ve kısa "
        "kalmalı. Alan adlarını değiştirme. Çıktı yalnızca ham JSON nesnesi olmalı; "
        "markdown veya açıklama ekleme."
    )
    user_payload = {
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "protected_numeric_values": protected_values,
        "text": source_text,
    }
    return {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    user_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            },
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "reasoning_effort": "none",
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "stream_narrative_text",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        key: {"type": "string"}
                        for key in sorted(_REQUIRED_TEXT_KEYS)
                    },
                    "required": sorted(_REQUIRED_TEXT_KEYS),
                    "additionalProperties": False,
                },
            },
        },
        "stream": False,
    }


def _assistant_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise LocalNarrativeRewriteError(
            "local narrative response requires exactly one choice"
        )
    first = choices[0]
    if not isinstance(first, dict):
        raise LocalNarrativeRewriteError(
            "local narrative choice must be an object"
        )
    message = first.get("message")
    if not isinstance(message, dict):
        raise LocalNarrativeRewriteError(
            "local narrative choice requires message object"
        )
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LocalNarrativeRewriteError(
            "local narrative message content must be non-empty"
        )
    if len(content) > 16_000:
        raise LocalNarrativeRewriteError(
            "local narrative response exceeds bounded size"
        )
    return content.strip()


def _parse_rewrite_content(content: str) -> StreamNarrativeText:
    fence = chr(96) * 3
    if content.startswith(fence) or content.endswith(fence):
        raise LocalNarrativeRewriteError(
            "local narrative response must be raw JSON without markdown fences"
        )
    try:
        raw: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LocalNarrativeRewriteError(
            "local narrative content is not valid JSON"
        ) from exc
    if not isinstance(raw, dict):
        raise LocalNarrativeRewriteError(
            "local narrative content must decode to an object"
        )
    keys = frozenset(str(key) for key in raw)
    if keys != _REQUIRED_TEXT_KEYS:
        raise LocalNarrativeRewriteError(
            "local narrative content must contain exactly six text fields"
        )

    values: dict[str, str] = {}
    for key in sorted(_REQUIRED_TEXT_KEYS):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise LocalNarrativeRewriteError(
                f"local narrative field {key} must be non-empty text"
            )
        values[key] = value.strip()

    return StreamNarrativeText(
        collapsed_text=values["collapsed_text"],
        simple_text=values["simple_text"],
        technical_text=values["technical_text"],
        intelligence_text=values["intelligence_text"],
        decision_text=values["decision_text"],
        capital_text=values["capital_text"],
    )


def _require_loopback_base_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("local narrative base URL must use http or https")
    if parsed.hostname not in _ALLOWED_LOOPBACK_HOSTS:
        raise ValueError("local narrative base URL must be loopback-only")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("local narrative base URL cannot embed credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("local narrative base URL cannot contain query/fragment")
    normalized_path = parsed.path.rstrip("/")
    if normalized_path not in {"", "/v1"}:
        raise ValueError("local narrative base URL path must be empty or /v1")


def _require_loopback_chat_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise LocalNarrativeRewriteError(
            "local narrative chat URL must use http or https"
        )
    if parsed.hostname not in _ALLOWED_LOOPBACK_HOSTS:
        raise LocalNarrativeRewriteError(
            "local narrative chat URL must remain loopback-only"
        )
    if parsed.username is not None or parsed.password is not None:
        raise LocalNarrativeRewriteError(
            "local narrative chat URL cannot embed credentials"
        )
    if parsed.query or parsed.fragment:
        raise LocalNarrativeRewriteError(
            "local narrative chat URL cannot contain query/fragment"
        )
    if not parsed.path.endswith("/chat/completions"):
        raise LocalNarrativeRewriteError(
            "local narrative chat URL must target chat/completions"
        )
