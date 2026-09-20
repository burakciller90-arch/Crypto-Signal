from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


def canonicalize(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: canonicalize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        return [canonicalize(item) for item in value]
    if isinstance(value, dict):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, Enum):
                key_text = str(key.value)
            elif isinstance(key, str | int):
                key_text = str(key)
            else:
                raise TypeError(
                    f"unsupported canonical mapping key: {type(key).__name__}"
                )
            converted[key_text] = canonicalize(item)
        return {
            key: converted[key]
            for key in sorted(converted)
        }
    if value is None or isinstance(value, str | int | bool):
        return value
    raise TypeError(
        f"unsupported canonical serialization type: {type(value).__name__}"
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_text(canonical_json(value))
