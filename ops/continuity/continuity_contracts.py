"""Pure continuity protocol contracts for Crypto Signal.

This module is intentionally stdlib-only because selected continuity scripts are
installed as standalone files outside the repository checkout.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from urllib.parse import urlsplit

PROJECT_NAMESPACE = "crypto-signal"
RELAY_PROTOCOL = "crypto-relay-v2"


@dataclass(frozen=True, slots=True)
class RelayEvent:
    protocol: str
    project_namespace: str
    event_id: str
    created: str
    signature: str
    message: str


def require_chat_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "chatgpt.com"
        or not parsed.path.startswith("/c/")
        or len(parsed.path) <= 3
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid ChatGPT conversation URL")
    if "/" in parsed.path[3:]:
        raise ValueError("ChatGPT conversation URL must identify one conversation")
    return candidate


def require_exact_binding(
    *,
    expected: str,
    local_current: str,
    shared_current: str,
    shared_expected: str,
) -> str:
    values = tuple(
        require_chat_url(item)
        for item in (expected, local_current, shared_current, shared_expected)
    )
    if len(set(values)) != 1:
        raise ValueError("continuity exact-chat binding mismatch")
    return values[0]


def event_key(event_id: str) -> str:
    if not event_id.strip():
        raise ValueError("event_id must be non-empty")
    return hashlib.sha256(event_id.encode()).hexdigest()


def marker_for(event_id: str) -> str:
    return f"[#cryptowake:{event_key(event_id)[:16]}]"


def expected_wire_sha(event_id: str, message: str) -> str:
    wire = f"{message} {marker_for(event_id)}"
    return hashlib.sha256(wire.encode()).hexdigest()


def signature(
    secret: bytes,
    event_id: str,
    message: str,
    *,
    namespace: str = PROJECT_NAMESPACE,
    protocol: str = RELAY_PROTOCOL,
) -> str:
    if len(secret) < 32:
        raise ValueError("relay secret is invalid")
    if namespace != PROJECT_NAMESPACE:
        raise ValueError("relay project namespace mismatch")
    if protocol != RELAY_PROTOCOL:
        raise ValueError("relay protocol mismatch")
    payload = f"{protocol}\n{namespace}\n{event_id}\n{message}".encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def encode_relay_event(
    *,
    secret: bytes,
    event_id: str,
    message: str,
    created: str,
) -> str:
    clean_message = " ".join(message.splitlines()).strip()
    if not event_id.strip() or not clean_message:
        raise ValueError("relay event id/message must be non-empty")
    payload = {
        "protocol": RELAY_PROTOCOL,
        "project_namespace": PROJECT_NAMESPACE,
        "event_id": event_id,
        "created": created,
        "signature": signature(secret, event_id, clean_message),
        "message": clean_message,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"


def decode_relay_event(raw: str, *, secret: bytes) -> RelayEvent:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("relay event is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("relay event must be an object")

    required = {
        "protocol",
        "project_namespace",
        "event_id",
        "created",
        "signature",
        "message",
    }
    if set(value) != required:
        raise ValueError("relay event fields mismatch")
    if value["protocol"] != RELAY_PROTOCOL:
        raise ValueError("relay protocol mismatch")
    if value["project_namespace"] != PROJECT_NAMESPACE:
        raise ValueError("relay project namespace mismatch")

    fields = {
        key: value[key]
        for key in required
    }
    if not all(isinstance(item, str) for item in fields.values()):
        raise ValueError("relay event fields must be strings")
    event_id = str(value["event_id"]).strip()
    created = str(value["created"]).strip()
    supplied = str(value["signature"]).strip()
    message = str(value["message"]).strip()
    if not event_id or not created or not supplied or not message:
        raise ValueError("relay event has empty required field")
    expected = signature(secret, event_id, message)
    if not hmac.compare_digest(supplied, expected):
        raise ValueError("relay event HMAC mismatch")
    return RelayEvent(
        protocol=RELAY_PROTOCOL,
        project_namespace=PROJECT_NAMESPACE,
        event_id=event_id,
        created=created,
        signature=supplied,
        message=message,
    )
