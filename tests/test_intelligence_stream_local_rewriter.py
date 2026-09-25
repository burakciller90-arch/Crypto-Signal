from __future__ import annotations

import json
from decimal import Decimal

import pytest

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_local_rewriter import (
    LocalNarrativeRewriteConfig,
    LocalNarrativeRewriteError,
    OpenAICompatibleLocalNarrativeRewriter,
)
from crypto_signal.product.intelligence_stream_narrative import (
    StreamNarrativeRewriteRequest,
    StreamNarrativeText,
)


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _baseline_text() -> StreamNarrativeText:
    return StreamNarrativeText(
        collapsed_text=(
            "BTCUSDT 4h: Görünümüm yukarı yönlü ve mevcut kanıt dengesi güçlü."
        ),
        simple_text=(
            "Görünümüm yukarı yönlü. Tetik bölgesi korunuyor ve ek teyit izleniyor."
        ),
        technical_text="Destek puanı 82, karşı ağırlık 0.",
        intelligence_text="Intelligence sonucu: duruş=bullish, güç=high.",
        decision_text="Bir sonraki karar koşulu tetik bölgesidir.",
        capital_text="Bu mesajda sanal sermayeye bağlı yeni bir referans yok.",
    )


def _request() -> StreamNarrativeRewriteRequest:
    return StreamNarrativeRewriteRequest(
        plan_identity=_sha("plan"),
        analytical_view_identity=_sha("analytical"),
        deterministic_text=_baseline_text(),
        protected_numeric_values=(Decimal(0), Decimal(82)),
        symbol="BTCUSDT",
        timeframe="4h",
    )


class _CapturingTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object], float]] = []

    def post_chat(
        self,
        *,
        url: str,
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        self.calls.append((url, payload, timeout_seconds))
        return self.response


def _completion_response(text: StreamNarrativeText) -> dict[str, object]:
    content = json.dumps(
        {
            "capital_text": text.capital_text,
            "collapsed_text": text.collapsed_text,
            "decision_text": text.decision_text,
            "intelligence_text": text.intelligence_text,
            "simple_text": text.simple_text,
            "technical_text": text.technical_text,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return {
        "choices": [
            {
                "message": {
                    "content": content,
                }
            }
        ]
    }


def test_local_rewriter_defaults_to_documented_ollama_loopback_endpoint() -> None:
    config = LocalNarrativeRewriteConfig(model="qwen3:8b")

    assert config.base_url == "http://127.0.0.1:11434/v1"
    assert (
        config.chat_completions_url
        == "http://127.0.0.1:11434/v1/chat/completions"
    )
    assert len(config.rewriter_identity) == 64
    assert config.rewriter_identity == LocalNarrativeRewriteConfig(
        model="qwen3:8b"
    ).rewriter_identity


@pytest.mark.parametrize(
    "base_url",
    (
        "https://ollama.com/v1",
        "http://192.168.1.10:11434/v1",
        "http://user:pass@127.0.0.1:11434/v1",
        "file:///tmp/model",
        "http://127.0.0.1:11434/not-v1",
    ),
)
def test_local_rewriter_rejects_non_loopback_or_unsafe_base_urls(
    base_url: str,
) -> None:
    with pytest.raises(ValueError):
        LocalNarrativeRewriteConfig(
            model="qwen3:8b",
            base_url=base_url,
        )


def test_local_rewriter_emits_bounded_openai_compatible_request() -> None:
    baseline = _baseline_text()
    rewritten = StreamNarrativeText(
        collapsed_text=(
            "BTCUSDT 4h: Yukarı yönlü tabloyu güçlü buluyorum; acele etmeden izliyorum."
        ),
        simple_text=(
            "Yukarı yön önde. Tetik bölgesi korunurken ek teyidi takip ediyorum."
        ),
        technical_text=baseline.technical_text,
        intelligence_text=baseline.intelligence_text,
        decision_text=baseline.decision_text,
        capital_text=baseline.capital_text,
    )
    transport = _CapturingTransport(_completion_response(rewritten))
    config = LocalNarrativeRewriteConfig(
        model="qwen3:8b",
        temperature=0.2,
        max_tokens=900,
    )
    rewriter = OpenAICompatibleLocalNarrativeRewriter(
        config,
        transport=transport,
    )

    result = rewriter.rewrite(_request())

    assert result == rewritten
    assert rewriter.rewriter_identity == config.rewriter_identity
    assert rewriter.rewriter_version == config.version
    assert len(transport.calls) == 1
    url, payload, timeout = transport.calls[0]
    assert url == "http://127.0.0.1:11434/v1/chat/completions"
    assert timeout == config.timeout_seconds
    assert payload["model"] == "qwen3:8b"
    assert payload["stream"] is False
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 900
    assert "response_format" not in payload

    messages = payload["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 2
    system = messages[0]
    user = messages[1]
    assert isinstance(system, dict)
    assert isinstance(user, dict)
    assert "tek karakter dahi değiştirmeden kopyala" in str(system["content"])
    assert "Yeni teknik kavram" in str(system["content"])
    user_payload = json.loads(str(user["content"]))
    assert user_payload["symbol"] == "BTCUSDT"
    assert user_payload["timeframe"] == "4h"
    assert user_payload["protected_numeric_values"] == ["0", "82"]


@pytest.mark.parametrize(
    "response",
    (
        {},
        {"choices": []},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": "not-json"}}]},
        {
            "choices": [
                {
                    "message": {
                        "content": "\u0060\u0060\u0060json\n{}\n\u0060\u0060\u0060"
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "collapsed_text": "x",
                                "simple_text": "x",
                                "technical_text": "x",
                                "intelligence_text": "x",
                                "decision_text": "x",
                                "capital_text": "x",
                                "extra": "not-allowed",
                            }
                        )
                    }
                }
            ]
        },
    ),
)
def test_local_rewriter_rejects_malformed_or_unbounded_response(
    response: dict[str, object],
) -> None:
    transport = _CapturingTransport(response)
    rewriter = OpenAICompatibleLocalNarrativeRewriter(
        LocalNarrativeRewriteConfig(model="qwen3:8b"),
        transport=transport,
    )

    with pytest.raises(LocalNarrativeRewriteError):
        rewriter.rewrite(_request())
