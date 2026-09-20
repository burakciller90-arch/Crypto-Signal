"""Read-only production scanner for post-activation paper signal events.

The scanner reads the immutable signal ledger and paper activation/processed
receipt tables strictly read-only. It emits deterministic Binance+Bybit 4h
provider pairs only. It does not evaluate autonomy, fetch candles or venue
rules, simulate fills, mutate ledgers, or activate PAPER/STABLE trading.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.deserialization import (
    LedgerDeserializationError,
    parse_signal_decision,
)
from crypto_signal.paper.activation import (
    PaperActivationState,
    compute_processed_event_identity,
)
from crypto_signal.paper.models import PERMITTED_SYMBOLS, REAL_CAPITAL, PaperSymbol
from crypto_signal.signals.models import SignalDecision

__all__ = [
    "PAPER_SIGNAL_EVENT_SCANNER_VERSION",
    "REAL_CAPITAL",
    "PaperSignalEventCandidate",
    "PaperSignalEventScanError",
    "PaperSignalEventScanResult",
    "scan_post_activation_signal_events",
]

PAPER_SIGNAL_EVENT_SCANNER_VERSION = "paper_signal_event_scanner.v2"
_REQUIRED_TIMEFRAME = "4h"
_REQUIRED_MARKET_TYPE = MarketType.SPOT
_PROVIDER_ORDER = (Exchange.BINANCE, Exchange.BYBIT)


class PaperSignalEventScanError(RuntimeError):
    """Raised when immutable event truth cannot be reconciled safely."""


@dataclass(frozen=True, slots=True)
class PaperSignalEventCandidate:
    event_identity: str
    scanner_version: str
    activation_identity: str
    symbol: PaperSymbol
    timeframe: str
    signal_as_of_ms: int
    source_cutoff_open_time_ms: int
    provider_signal_as_of_ms: tuple[int, int]
    source_freeze_identities: tuple[str, str]
    source_frozen_at_ms: tuple[int, int]
    signals: tuple[SignalDecision, SignalDecision]
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.scanner_version != PAPER_SIGNAL_EVENT_SCANNER_VERSION:
            raise ValueError("unsupported paper signal event scanner version")
        _require_sha256(self.event_identity, "event_identity")
        _require_sha256(self.activation_identity, "activation_identity")
        if self.timeframe != _REQUIRED_TIMEFRAME:
            raise ValueError("paper event candidate must be 4h")
        if self.signal_as_of_ms < 0 or self.source_cutoff_open_time_ms < 0:
            raise ValueError("paper event timestamps must be non-negative")
        if any(value < 0 for value in self.provider_signal_as_of_ms):
            raise ValueError("provider signal as-of values must be non-negative")
        if self.signal_as_of_ms != max(self.provider_signal_as_of_ms):
            raise ValueError(
                "paper event signal_as_of_ms must be the latest provider as-of"
            )
        if len(set(self.source_freeze_identities)) != 2:
            raise ValueError("candidate requires two unique freeze identities")
        for identity in self.source_freeze_identities:
            _require_sha256(identity, "source freeze identity")
        if any(
            frozen_at_ms < provider_as_of_ms
            for frozen_at_ms, provider_as_of_ms in zip(
                self.source_frozen_at_ms,
                self.provider_signal_as_of_ms,
                strict=True,
            )
        ):
            raise ValueError("source freeze cannot predate provider signal as-of")
        exchanges = tuple(signal.exchange for signal in self.signals)
        if exchanges != _PROVIDER_ORDER:
            raise ValueError("candidate provider order must be Binance then Bybit")
        for index, signal in enumerate(self.signals):
            if signal.freeze_identity != self.source_freeze_identities[index]:
                raise ValueError("candidate signal/freeze lineage mismatch")
            if signal.market_type is not _REQUIRED_MARKET_TYPE:
                raise ValueError("candidate requires spot signals")
            if signal.symbol != self.symbol.value:
                raise ValueError("candidate signal symbol mismatch")
            if signal.timeframe != self.timeframe:
                raise ValueError("candidate signal timeframe mismatch")
            if signal.as_of_ms != self.provider_signal_as_of_ms[index]:
                raise ValueError("candidate provider signal as-of mismatch")
            if signal.as_of_ms > self.signal_as_of_ms:
                raise ValueError("provider signal cannot postdate event availability")
        expected = compute_processed_event_identity(
            activation_identity=self.activation_identity,
            source_freeze_identities=self.source_freeze_identities,
            symbol=self.symbol,
            timeframe=self.timeframe,
            signal_as_of_ms=self.signal_as_of_ms,
        )
        if self.event_identity != expected:
            raise ValueError("candidate processed-event identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperSignalEventScanResult:
    scanner_version: str
    activation_identity: str
    eligible_freeze_count: int
    incomplete_pair_count: int
    processed_skip_count: int
    candidates: tuple[PaperSignalEventCandidate, ...]
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.scanner_version != PAPER_SIGNAL_EVENT_SCANNER_VERSION:
            raise ValueError("unsupported scanner version")
        _require_sha256(self.activation_identity, "activation_identity")
        if min(
            self.eligible_freeze_count,
            self.incomplete_pair_count,
            self.processed_skip_count,
        ) < 0:
            raise ValueError("scanner counts cannot be negative")
        ordered = tuple(
            sorted(
                self.candidates,
                key=lambda item: (
                    item.signal_as_of_ms,
                    item.symbol.value,
                    item.event_identity,
                ),
            )
        )
        if self.candidates != ordered:
            raise ValueError("scanner candidates must be deterministically ordered")


@dataclass(frozen=True, slots=True)
class _FreezeView:
    freeze_identity: str
    exchange: Exchange
    symbol: PaperSymbol
    as_of_ms: int
    source_cutoff_open_time_ms: int
    frozen_at_ms: int
    decision: SignalDecision


def scan_post_activation_signal_events(
    *,
    signal_ledger_path: Path,
    paper_ledger_path: Path,
    activation: PaperActivationState,
    observed_at_ms: int | None = None,
) -> PaperSignalEventScanResult:
    """Return unprocessed exact Binance+Bybit 4h event pairs after activation."""
    if activation.real_capital != REAL_CAPITAL:
        raise PaperSignalEventScanError("REAL_CAPITAL must remain 0")
    if observed_at_ms is not None and observed_at_ms < 0:
        raise PaperSignalEventScanError("observed_at_ms must be non-negative")
    _assert_persistent_activation(
        paper_ledger_path=paper_ledger_path,
        activation=activation,
    )
    processed = _read_processed_event_identities(paper_ledger_path)
    freezes = _read_eligible_freezes(
        signal_ledger_path=signal_ledger_path,
        activation=activation,
        observed_at_ms=observed_at_ms,
    )

    grouped: dict[tuple[PaperSymbol, int], list[_FreezeView]] = {}
    for item in freezes:
        grouped.setdefault(
            (item.symbol, item.source_cutoff_open_time_ms),
            [],
        ).append(item)

    candidates: list[PaperSignalEventCandidate] = []
    incomplete = 0
    skipped_processed = 0
    for symbol, source_cutoff_open_time_ms in sorted(
        grouped,
        key=lambda key: (key[1], key[0].value),
    ):
        items = grouped[(symbol, source_cutoff_open_time_ms)]
        by_exchange: dict[Exchange, _FreezeView] = {}
        for item in items:
            if item.exchange in by_exchange:
                raise PaperSignalEventScanError(
                    "duplicate provider freeze for the same paper event context"
                )
            by_exchange[item.exchange] = item

        if set(by_exchange) != set(_PROVIDER_ORDER):
            incomplete += 1
            continue

        binance = by_exchange[Exchange.BINANCE]
        bybit = by_exchange[Exchange.BYBIT]
        source_ids = (binance.freeze_identity, bybit.freeze_identity)
        provider_signal_as_of_ms = (binance.as_of_ms, bybit.as_of_ms)
        signal_as_of_ms = max(provider_signal_as_of_ms)
        event_identity = compute_processed_event_identity(
            activation_identity=activation.activation_identity,
            source_freeze_identities=source_ids,
            symbol=symbol,
            timeframe=_REQUIRED_TIMEFRAME,
            signal_as_of_ms=signal_as_of_ms,
        )
        if event_identity in processed:
            skipped_processed += 1
            continue
        candidates.append(
            PaperSignalEventCandidate(
                event_identity=event_identity,
                scanner_version=PAPER_SIGNAL_EVENT_SCANNER_VERSION,
                activation_identity=activation.activation_identity,
                symbol=symbol,
                timeframe=_REQUIRED_TIMEFRAME,
                signal_as_of_ms=signal_as_of_ms,
                source_cutoff_open_time_ms=source_cutoff_open_time_ms,
                provider_signal_as_of_ms=provider_signal_as_of_ms,
                source_freeze_identities=source_ids,
                source_frozen_at_ms=(
                    binance.frozen_at_ms,
                    bybit.frozen_at_ms,
                ),
                signals=(binance.decision, bybit.decision),
                real_capital=REAL_CAPITAL,
            )
        )

    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.signal_as_of_ms,
                item.symbol.value,
                item.event_identity,
            ),
        )
    )
    return PaperSignalEventScanResult(
        scanner_version=PAPER_SIGNAL_EVENT_SCANNER_VERSION,
        activation_identity=activation.activation_identity,
        eligible_freeze_count=len(freezes),
        incomplete_pair_count=incomplete,
        processed_skip_count=skipped_processed,
        candidates=ordered,
        real_capital=REAL_CAPITAL,
    )


def _read_eligible_freezes(
    *,
    signal_ledger_path: Path,
    activation: PaperActivationState,
    observed_at_ms: int | None,
) -> tuple[_FreezeView, ...]:
    if not signal_ledger_path.exists():
        raise PaperSignalEventScanError("immutable signal ledger does not exist")
    uri = f"file:{signal_ledger_path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            _require_table(connection, "signal_freezes", "signal ledger")
            placeholders = ",".join("?" for _ in PERMITTED_SYMBOLS)
            point_in_time_sql = ""
            point_in_time_params: tuple[int, ...] = ()
            if observed_at_ms is not None:
                point_in_time_sql = " AND as_of_ms <= ? AND frozen_at_ms <= ?"
                point_in_time_params = (observed_at_ms, observed_at_ms)
            rows = connection.execute(
                f"""
                SELECT
                    signal_freeze_identity,
                    exchange,
                    market_type,
                    symbol,
                    timeframe,
                    as_of_ms,
                    source_cutoff_open_time_ms,
                    frozen_at_ms,
                    signal_state,
                    direction,
                    bundle_json
                FROM signal_freezes
                WHERE market_type = ?
                  AND timeframe = ?
                  AND exchange IN (?, ?)
                  AND symbol IN ({placeholders})
                  AND as_of_ms >= ?
                  AND frozen_at_ms >= ?
                  {point_in_time_sql}
                ORDER BY
                    as_of_ms ASC,
                    symbol ASC,
                    exchange ASC,
                    signal_freeze_identity ASC
                """,
                (
                    _REQUIRED_MARKET_TYPE.value,
                    _REQUIRED_TIMEFRAME,
                    Exchange.BINANCE.value,
                    Exchange.BYBIT.value,
                    *(symbol.value for symbol in sorted(
                        PERMITTED_SYMBOLS,
                        key=lambda item: item.value,
                    )),
                    activation.activation_cutoff_ms,
                    activation.activated_at_ms,
                    *point_in_time_params,
                ),
            ).fetchall()
    except sqlite3.Error as exc:
        raise PaperSignalEventScanError(
            f"failed to read immutable signal ledger: {exc}"
        ) from exc

    result: list[_FreezeView] = []
    for row in rows:
        try:
            exchange = Exchange(str(row["exchange"]))
            symbol = PaperSymbol(str(row["symbol"]))
            root = json.loads(str(row["bundle_json"]))
            if not isinstance(root, dict) or "signal_decision" not in root:
                raise PaperSignalEventScanError(
                    "signal freeze bundle lacks signal_decision"
                )
            decision = parse_signal_decision(root["signal_decision"])
        except (
            ValueError,
            TypeError,
            json.JSONDecodeError,
            LedgerDeserializationError,
        ) as exc:
            if isinstance(exc, PaperSignalEventScanError):
                raise
            raise PaperSignalEventScanError(
                "failed to deserialize immutable signal decision"
            ) from exc

        freeze_identity = str(row["signal_freeze_identity"])
        as_of_ms = int(row["as_of_ms"])
        source_cutoff_open_time_ms = int(row["source_cutoff_open_time_ms"])
        frozen_at_ms = int(row["frozen_at_ms"])
        indexed_state = str(row["signal_state"])
        indexed_direction = str(row["direction"])
        if (
            decision.freeze_identity != freeze_identity
            or decision.exchange is not exchange
            or decision.market_type is not _REQUIRED_MARKET_TYPE
            or decision.symbol != symbol.value
            or decision.timeframe != _REQUIRED_TIMEFRAME
            or decision.as_of_ms != as_of_ms
            or decision.state.value != indexed_state
            or decision.direction.value != indexed_direction
        ):
            raise PaperSignalEventScanError(
                "signal freeze index/bundle lineage mismatch"
            )
        if frozen_at_ms < as_of_ms:
            raise PaperSignalEventScanError(
                "signal freeze timestamp predates signal as-of"
            )
        result.append(
            _FreezeView(
                freeze_identity=freeze_identity,
                exchange=exchange,
                symbol=symbol,
                as_of_ms=as_of_ms,
                source_cutoff_open_time_ms=source_cutoff_open_time_ms,
                frozen_at_ms=frozen_at_ms,
                decision=decision,
            )
        )
    return tuple(result)


def _assert_persistent_activation(
    *,
    paper_ledger_path: Path,
    activation: PaperActivationState,
) -> None:
    if not paper_ledger_path.exists():
        raise PaperSignalEventScanError("paper ledger does not exist")
    uri = f"file:{paper_ledger_path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            _require_table(connection, "paper_activation_state", "paper ledger")
            row = connection.execute(
                """
                SELECT activation_identity
                FROM paper_activation_state
                WHERE singleton = 1
                """
            ).fetchone()
    except sqlite3.Error as exc:
        raise PaperSignalEventScanError(
            f"failed to read persistent paper activation: {exc}"
        ) from exc
    if row is None:
        raise PaperSignalEventScanError("paper activation is not persisted")
    if str(row["activation_identity"]) != activation.activation_identity:
        raise PaperSignalEventScanError("persistent activation identity mismatch")


def _read_processed_event_identities(path: Path) -> frozenset[str]:
    uri = f"file:{path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            _require_table(connection, "paper_processed_events", "paper ledger")
            rows = connection.execute(
                """
                SELECT event_identity
                FROM paper_processed_events
                ORDER BY event_identity ASC
                """
            ).fetchall()
    except sqlite3.Error as exc:
        raise PaperSignalEventScanError(
            f"failed to read processed paper events: {exc}"
        ) from exc
    identities = frozenset(str(row["event_identity"]) for row in rows)
    for identity in identities:
        _require_sha256(identity, "processed event identity")
    return identities


def _require_table(
    connection: sqlite3.Connection,
    table: str,
    label: str,
) -> None:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table,),
    ).fetchone()
    if row is None:
        raise PaperSignalEventScanError(f"{label} missing required table: {table}")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
