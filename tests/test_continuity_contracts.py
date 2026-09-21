from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).parents[1]
    / "ops"
    / "continuity"
    / "continuity_contracts.py"
)
SPEC = importlib.util.spec_from_file_location("continuity_contracts", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
contracts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = contracts
SPEC.loader.exec_module(contracts)


def test_exact_chat_binding_requires_same_single_conversation() -> None:
    target = "https://chatgpt.com/c/example-conversation"
    assert contracts.require_exact_binding(
        expected=target,
        local_current=target,
        shared_current=target,
        shared_expected=target,
    ) == target

    with pytest.raises(ValueError, match="binding mismatch"):
        contracts.require_exact_binding(
            expected=target,
            local_current=target,
            shared_current="https://chatgpt.com/c/other-conversation",
            shared_expected=target,
        )

    for invalid in (
        "http://chatgpt.com/c/x",
        "https://example.com/c/x",
        "https://chatgpt.com/",
        "https://chatgpt.com/c/x/extra",
        "https://chatgpt.com/c/x?foo=bar",
    ):
        with pytest.raises(ValueError, match="conversation URL"):
            contracts.require_chat_url(invalid)


def test_relay_event_is_namespace_and_protocol_bound() -> None:
    secret = b"x" * 32
    raw = contracts.encode_relay_event(
        secret=secret,
        event_id="continuation:abc",
        message="continue safely",
        created="2026-09-22 02:40:00 +0300",
    )
    decoded = contracts.decode_relay_event(raw, secret=secret)

    assert decoded.protocol == "crypto-relay-v2"
    assert decoded.project_namespace == "crypto-signal"
    assert decoded.event_id == "continuation:abc"
    assert decoded.message == "continue safely"

    payload = json.loads(raw)
    payload["project_namespace"] = "durdurulmaz"
    tampered = json.dumps(payload)
    with pytest.raises(ValueError, match="namespace"):
        contracts.decode_relay_event(tampered, secret=secret)

    payload = json.loads(raw)
    payload["protocol"] = "crypto-relay-v1"
    with pytest.raises(ValueError, match="protocol"):
        contracts.decode_relay_event(json.dumps(payload), secret=secret)


def test_relay_hmac_cannot_be_reused_across_namespace() -> None:
    secret = b"s" * 32
    signed = contracts.signature(secret, "event-1", "message")
    legacy = hashlib.sha256(b"event-1\nmessage").hexdigest()

    assert len(signed) == 64
    assert signed != legacy
    with pytest.raises(ValueError, match="namespace"):
        contracts.signature(
            secret,
            "event-1",
            "message",
            namespace="quantum-capital",
        )


def test_event_marker_and_wire_hash_are_deterministic() -> None:
    marker = contracts.marker_for("event-1")
    assert marker == contracts.marker_for("event-1")
    assert marker != contracts.marker_for("event-2")
    assert contracts.expected_wire_sha(
        "event-1",
        "message",
    ) == contracts.expected_wire_sha("event-1", "message")
