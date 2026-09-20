"""Frozen market-price input for paper execution planning.

V1 reads the canonical base-candle cache strictly read-only and selects the
first fully closed Binance spot 15m candle whose open time is strictly after
the autonomy signal as-of. The selected candle OPEN is a reference price only,
not a real or simulated fill. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.autonomy import PaperAutonomyDecision
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol

__all__ = [
    "PAPER_EXECUTION_INPUT_POLICY_VERSION",
    "REAL_CAPITAL",
    "FrozenPaperExecutionInput",
    "PaperExecutionInputError",
    "PaperExecutionInputResult",
    "PaperExecutionInputStatus",
    "freeze_execution_input_from_cache",
]

PAPER_EXECUTION_INPUT_POLICY_VERSION = "paper_execution_input_policy.v1"
_EXECUTION_REFERENCE_EXCHANGE = Exchange.BINANCE
_EXECUTION_REFERENCE_MARKET_TYPE = MarketType.SPOT
_EXECUTION_REFERENCE_TIMEFRAME = "15m"
_EXECUTION_REFERENCE_PRICE_FIELD = "open"
_EXECUTION_REFERENCE_RULE = "binance_spot_15m_first_closed_after_signal_open"


class PaperExecutionInputError(ValueError):
    """Raised when frozen execution-input truth cannot be established safely."""


class PaperExecutionInputStatus(StrEnum):
    FROZEN = "frozen"
    WAITING_FOR_NEXT_CLOSED_CANDLE = "waiting_for_next_closed_candle"


@dataclass(frozen=True, slots=True)
class FrozenPaperExecutionInput:
    input_identity: str
    policy_version: str
    candidate_action: PaperAction
    symbol: PaperSymbol
    source_freeze_identities: tuple[str, ...]
    signal_as_of_ms: int
    observed_at_ms: int
    source_exchange: Exchange
    source_market_type: MarketType
    source_timeframe: str
    source_candle_open_time_ms: int
    source_candle_close_time_ms: int
    source_candle_ingested_at_ms: int
    source_adapter_version: str
    reference_price: Decimal
    price_field: str = _EXECUTION_REFERENCE_PRICE_FIELD
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.candidate_action not in {PaperAction.BUY, PaperAction.EXIT}:
            raise ValueError("frozen execution input requires BUY or EXIT candidate")
        if not self.policy_version.strip():
            raise ValueError("execution input policy version must be non-empty")
        if not self.source_freeze_identities:
            raise ValueError("execution input requires source signal identities")
        if self.signal_as_of_ms < 0 or self.observed_at_ms < 0:
            raise ValueError("execution input timestamps must be non-negative")
        if self.observed_at_ms < self.signal_as_of_ms:
            raise ValueError("execution input cannot be observed before signal as-of")
        if self.source_exchange is not _EXECUTION_REFERENCE_EXCHANGE:
            raise ValueError("execution input v1 requires Binance source")
        if self.source_market_type is not _EXECUTION_REFERENCE_MARKET_TYPE:
            raise ValueError("execution input v1 requires spot source")
        if self.source_timeframe != _EXECUTION_REFERENCE_TIMEFRAME:
            raise ValueError("execution input v1 requires 15m source")
        if self.price_field != _EXECUTION_REFERENCE_PRICE_FIELD:
            raise ValueError("execution input v1 requires candle OPEN reference")
        if self.source_candle_open_time_ms <= self.signal_as_of_ms:
            raise ValueError("source candle must begin strictly after signal as-of")
        if self.source_candle_close_time_ms <= self.source_candle_open_time_ms:
            raise ValueError("source candle time bounds are invalid")
        if self.source_candle_close_time_ms > self.observed_at_ms:
            raise ValueError("source candle must be fully closed by observation time")
        if self.source_candle_ingested_at_ms > self.observed_at_ms:
            raise ValueError("source candle must be ingested by observation time")
        if not self.source_adapter_version.strip():
            raise ValueError("source adapter version must be non-empty")
        if not isinstance(self.reference_price, Decimal):
            raise TypeError("reference_price must be Decimal")
        if (
            self.reference_price.is_nan()
            or self.reference_price.is_infinite()
            or self.reference_price <= Decimal(0)
        ):
            raise ValueError("reference_price must be finite and positive")
        expected = compute_execution_input_identity(
            policy_version=self.policy_version,
            candidate_action=self.candidate_action,
            symbol=self.symbol,
            source_freeze_identities=self.source_freeze_identities,
            signal_as_of_ms=self.signal_as_of_ms,
            source_exchange=self.source_exchange,
            source_market_type=self.source_market_type,
            source_timeframe=self.source_timeframe,
            source_candle_open_time_ms=self.source_candle_open_time_ms,
            source_candle_close_time_ms=self.source_candle_close_time_ms,
            source_candle_ingested_at_ms=self.source_candle_ingested_at_ms,
            source_adapter_version=self.source_adapter_version,
            reference_price=self.reference_price,
            price_field=self.price_field,
        )
        if self.input_identity != expected:
            raise ValueError("execution input identity mismatch")

    @property
    def venue_reference(self) -> str:
        return f"{_EXECUTION_REFERENCE_RULE}|input:{self.input_identity}"


@dataclass(frozen=True, slots=True)
class PaperExecutionInputResult:
    status: PaperExecutionInputStatus
    frozen_input: FrozenPaperExecutionInput | None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.status is PaperExecutionInputStatus.FROZEN:
            if self.frozen_input is None:
                raise ValueError("FROZEN result requires frozen_input")
        elif self.frozen_input is not None:
            raise ValueError("waiting result cannot carry frozen_input")


def compute_execution_input_identity(
    *,
    policy_version: str,
    candidate_action: PaperAction,
    symbol: PaperSymbol,
    source_freeze_identities: tuple[str, ...],
    signal_as_of_ms: int,
    source_exchange: Exchange,
    source_market_type: MarketType,
    source_timeframe: str,
    source_candle_open_time_ms: int,
    source_candle_close_time_ms: int,
    source_candle_ingested_at_ms: int,
    source_adapter_version: str,
    reference_price: Decimal,
    price_field: str,
) -> str:
    return canonical_sha256(
        {
            "candidate_action": candidate_action.value,
            "policy_version": policy_version,
            "price_field": price_field,
            "reference_price": reference_price,
            "signal_as_of_ms": signal_as_of_ms,
            "source_adapter_version": source_adapter_version,
            "source_candle_close_time_ms": source_candle_close_time_ms,
            "source_candle_ingested_at_ms": source_candle_ingested_at_ms,
            "source_candle_open_time_ms": source_candle_open_time_ms,
            "source_exchange": source_exchange.value,
            "source_freeze_identities": list(source_freeze_identities),
            "source_market_type": source_market_type.value,
            "source_timeframe": source_timeframe,
            "symbol": symbol.value,
        }
    )


def freeze_execution_input_from_cache(
    *,
    candle_cache_path: Path,
    autonomy_decision: PaperAutonomyDecision,
    observed_at_ms: int,
) -> PaperExecutionInputResult:
    _validate_candidate(autonomy_decision)
    symbol = autonomy_decision.symbol
    source_as_of_ms = autonomy_decision.source_as_of_ms
    if symbol is None or source_as_of_ms is None:
        raise PaperExecutionInputError("invalid autonomy trade candidate")
    if observed_at_ms < autonomy_decision.evaluated_at_ms:
        raise PaperExecutionInputError(
            "execution input observation cannot predate autonomy evaluation"
        )
    if not candle_cache_path.exists():
        raise PaperExecutionInputError("canonical base-candle cache does not exist")

    uri = f"file:{candle_cache_path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            if connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'candles'
                """
            ).fetchone() is None:
                raise PaperExecutionInputError(
                    "canonical base-candle cache is missing candles table"
                )
            row = connection.execute(
                """
                SELECT
                    open_time_ms,
                    close_time_ms,
                    open,
                    ingested_at_ms,
                    source_timestamp_ms,
                    adapter_version
                FROM candles
                WHERE exchange = ?
                  AND market_type = ?
                  AND symbol = ?
                  AND timeframe = ?
                  AND is_closed = 1
                  AND open_time_ms > ?
                  AND close_time_ms <= ?
                  AND ingested_at_ms <= ?
                  AND source_timestamp_ms <= ?
                ORDER BY open_time_ms ASC
                LIMIT 1
                """,
                (
                    _EXECUTION_REFERENCE_EXCHANGE.value,
                    _EXECUTION_REFERENCE_MARKET_TYPE.value,
                    symbol.value,
                    _EXECUTION_REFERENCE_TIMEFRAME,
                    source_as_of_ms,
                    observed_at_ms,
                    observed_at_ms,
                    observed_at_ms,
                ),
            ).fetchone()
    except sqlite3.Error as exc:
        raise PaperExecutionInputError(
            f"failed to read canonical base-candle cache: {exc}"
        ) from exc

    if row is None:
        return PaperExecutionInputResult(
            status=PaperExecutionInputStatus.WAITING_FOR_NEXT_CLOSED_CANDLE,
            frozen_input=None,
            real_capital=REAL_CAPITAL,
        )

    reference_price = Decimal(str(row["open"]))
    frozen = _build_frozen_input(
        autonomy_decision=autonomy_decision,
        observed_at_ms=observed_at_ms,
        source_candle_open_time_ms=int(row["open_time_ms"]),
        source_candle_close_time_ms=int(row["close_time_ms"]),
        source_candle_ingested_at_ms=int(row["ingested_at_ms"]),
        source_adapter_version=str(row["adapter_version"]),
        reference_price=reference_price,
    )
    return PaperExecutionInputResult(
        status=PaperExecutionInputStatus.FROZEN,
        frozen_input=frozen,
        real_capital=REAL_CAPITAL,
    )


def _validate_candidate(decision: PaperAutonomyDecision) -> None:
    if decision.real_capital != REAL_CAPITAL:
        raise PaperExecutionInputError("REAL_CAPITAL must remain 0")
    if decision.candidate_action not in {PaperAction.BUY, PaperAction.EXIT}:
        raise PaperExecutionInputError(
            "execution input requires BUY or EXIT autonomy candidate"
        )
    if not decision.execution_input_required:
        raise PaperExecutionInputError(
            "autonomy candidate does not require execution input"
        )
    if decision.symbol is None or decision.source_as_of_ms is None:
        raise PaperExecutionInputError(
            "autonomy trade candidate lacks symbol/as-of truth"
        )
    if not decision.source_freeze_identities:
        raise PaperExecutionInputError(
            "autonomy trade candidate lacks source signal identities"
        )


def _build_frozen_input(
    *,
    autonomy_decision: PaperAutonomyDecision,
    observed_at_ms: int,
    source_candle_open_time_ms: int,
    source_candle_close_time_ms: int,
    source_candle_ingested_at_ms: int,
    source_adapter_version: str,
    reference_price: Decimal,
) -> FrozenPaperExecutionInput:
    if autonomy_decision.symbol is None or autonomy_decision.source_as_of_ms is None:
        raise PaperExecutionInputError("invalid autonomy trade candidate")
    identity = compute_execution_input_identity(
        policy_version=PAPER_EXECUTION_INPUT_POLICY_VERSION,
        candidate_action=autonomy_decision.candidate_action,
        symbol=autonomy_decision.symbol,
        source_freeze_identities=autonomy_decision.source_freeze_identities,
        signal_as_of_ms=autonomy_decision.source_as_of_ms,
        source_exchange=_EXECUTION_REFERENCE_EXCHANGE,
        source_market_type=_EXECUTION_REFERENCE_MARKET_TYPE,
        source_timeframe=_EXECUTION_REFERENCE_TIMEFRAME,
        source_candle_open_time_ms=source_candle_open_time_ms,
        source_candle_close_time_ms=source_candle_close_time_ms,
        source_candle_ingested_at_ms=source_candle_ingested_at_ms,
        source_adapter_version=source_adapter_version,
        reference_price=reference_price,
        price_field=_EXECUTION_REFERENCE_PRICE_FIELD,
    )
    return FrozenPaperExecutionInput(
        input_identity=identity,
        policy_version=PAPER_EXECUTION_INPUT_POLICY_VERSION,
        candidate_action=autonomy_decision.candidate_action,
        symbol=autonomy_decision.symbol,
        source_freeze_identities=autonomy_decision.source_freeze_identities,
        signal_as_of_ms=autonomy_decision.source_as_of_ms,
        observed_at_ms=observed_at_ms,
        source_exchange=_EXECUTION_REFERENCE_EXCHANGE,
        source_market_type=_EXECUTION_REFERENCE_MARKET_TYPE,
        source_timeframe=_EXECUTION_REFERENCE_TIMEFRAME,
        source_candle_open_time_ms=source_candle_open_time_ms,
        source_candle_close_time_ms=source_candle_close_time_ms,
        source_candle_ingested_at_ms=source_candle_ingested_at_ms,
        source_adapter_version=source_adapter_version,
        reference_price=reference_price,
        price_field=_EXECUTION_REFERENCE_PRICE_FIELD,
        real_capital=REAL_CAPITAL,
    )
