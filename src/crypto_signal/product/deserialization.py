"""Compatibility exports for persisted evidence deserialization.

Canonical implementation lives in crypto_signal.ledger.deserialization so
product and alert lanes reconstruct immutable evidence identically.
"""

from crypto_signal.ledger.deserialization import (
    LedgerDeserializationError as ProductDeserializationError,
)
from crypto_signal.ledger.deserialization import (
    parse_outcome_evaluation,
    parse_signal_decision,
)

__all__ = [
    "ProductDeserializationError",
    "parse_outcome_evaluation",
    "parse_signal_decision",
]
