"""Strictly read-only marked portfolio projection for the virtual paper fund.

The portfolio view reconstructs immutable paper accounting state from SQLite
opened in read-only/query-only mode, then marks held positions from the latest
fully closed Binance Spot 15m candle available as of the requested observation
time. It does not create NAV records, trade records, venue data, or orders.
REAL_CAPITAL remains 0.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.ledger import (
    PaperLedgerEntry,
    PaperRecordKind,
    deserialize_paper_record,
)
from crypto_signal.paper.models import (
    INITIAL_CASH_USDT,
    REAL_CAPITAL,
    DecisionIntentRecord,
    NavSnapshotRecord,
    PaperSymbol,
    SimulatedFillRecord,
)
from crypto_signal.paper.state import (
    PaperFundState,
    reconstruct_paper_fund_state_from_entries,
)

__all__ = [
    "PAPER_PORTFOLIO_VIEW_VERSION",
    "PaperMarkEvidence",
    "PaperPortfolioAvailability",
    "PaperPortfolioError",
    "PaperPortfolioPositionView",
    "PaperPortfolioSnapshot",
    "project_paper_portfolio",
    "read_paper_entries_read_only",
    "read_paper_portfolio_snapshot",
]

PAPER_PORTFOLIO_VIEW_VERSION = "paper_portfolio_view.v1"
_MARK_EXCHANGE = Exchange.BINANCE
_MARK_MARKET_TYPE = MarketType.SPOT
_MARK_TIMEFRAME = "15m"
_MARK_PRICE_FIELD = "close"
_TABLE_BY_KIND = {
    PaperRecordKind.FUND_CREATION: "paper_fund_creations",
    PaperRecordKind.DECISION_INTENT: "paper_decision_intents",
    PaperRecordKind.SIMULATED_FILL: "paper_simulated_fills",
    PaperRecordKind.POSITION_CASH_MUTATION: "paper_position_cash_mutations",
    PaperRecordKind.NAV_SNAPSHOT: "paper_nav_snapshots",
}


class PaperPortfolioError(RuntimeError):
    """Raised when a read-only portfolio projection cannot be trusted."""


class PaperPortfolioAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING_MARKS = "missing_marks"


@dataclass(frozen=True, slots=True)
class PaperMarkEvidence:
    """Immutable reference to the real closed candle used for one paper mark."""

    mark_identity: str
    symbol: PaperSymbol
    price: Decimal
    source_exchange: Exchange
    source_market_type: MarketType
    source_timeframe: str
    source_candle_open_time_ms: int
    source_candle_close_time_ms: int
    source_candle_ingested_at_ms: int
    source_timestamp_ms: int
    source: str
    source_adapter_version: str
    price_field: str = _MARK_PRICE_FIELD

    def __post_init__(self) -> None:
        _require_sha256(self.mark_identity, "mark_identity")
        if self.source_exchange is not _MARK_EXCHANGE:
            raise ValueError("paper mark v1 requires Binance source")
        if self.source_market_type is not _MARK_MARKET_TYPE:
            raise ValueError("paper mark v1 requires spot source")
        if self.source_timeframe != _MARK_TIMEFRAME:
            raise ValueError("paper mark v1 requires 15m source")
        if self.price_field != _MARK_PRICE_FIELD:
            raise ValueError("paper mark v1 requires candle CLOSE")
        if self.source_candle_open_time_ms < 0:
            raise ValueError("mark candle open time must be non-negative")
        if self.source_candle_close_time_ms <= self.source_candle_open_time_ms:
            raise ValueError("mark candle bounds are invalid")
        if self.source_candle_ingested_at_ms < 0 or self.source_timestamp_ms < 0:
            raise ValueError("mark source timestamps must be non-negative")
        if not self.source.strip():
            raise ValueError("mark source must be non-empty")
        if not self.source_adapter_version.strip():
            raise ValueError("mark adapter version must be non-empty")
        if (
            not isinstance(self.price, Decimal)
            or self.price.is_nan()
            or self.price.is_infinite()
            or self.price <= Decimal(0)
        ):
            raise ValueError("mark price must be finite and positive")
        expected = canonical_sha256(_mark_identity_payload(self))
        if self.mark_identity != expected:
            raise ValueError("mark identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperPortfolioPositionView:
    symbol: PaperSymbol
    quantity: Decimal
    mark: PaperMarkEvidence | None
    marked_value_usdt: Decimal | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.quantity, Decimal)
            or self.quantity.is_nan()
            or self.quantity.is_infinite()
            or self.quantity <= Decimal(0)
        ):
            raise ValueError("portfolio position quantity must be finite and positive")
        if self.mark is None:
            if self.marked_value_usdt is not None:
                raise ValueError("unmarked position cannot carry marked value")
            return
        if self.mark.symbol is not self.symbol:
            raise ValueError("position/mark symbol mismatch")
        expected = self.quantity * self.mark.price
        if self.marked_value_usdt != expected:
            raise ValueError("marked value must equal quantity times mark price")


@dataclass(frozen=True, slots=True)
class PaperPortfolioSnapshot:
    snapshot_identity: str
    version: str
    fund_identity: str
    observed_at_ms: int
    availability: PaperPortfolioAvailability
    cash_usdt: Decimal
    initial_cash_usdt: Decimal
    positions: tuple[PaperPortfolioPositionView, ...]
    missing_mark_symbols: tuple[PaperSymbol, ...]
    marked_positions_value_usdt: Decimal | None
    nav_usdt: Decimal | None
    pnl_usdt: Decimal | None
    total_return_fraction: Decimal | None
    decision_count: int
    simulated_fill_count: int
    nav_snapshot_count: int
    replayed_record_count: int
    last_mutation_identity: str | None
    last_mutation_at_ms: int | None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.version != PAPER_PORTFOLIO_VIEW_VERSION:
            raise ValueError("unsupported paper portfolio view version")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.snapshot_identity, "portfolio snapshot identity")
        _require_sha256(self.fund_identity, "fund identity")
        if self.observed_at_ms < 0:
            raise ValueError("portfolio observation time must be non-negative")
        if self.initial_cash_usdt != INITIAL_CASH_USDT:
            raise ValueError("paper portfolio initial cash must remain 100 USDT")
        if self.cash_usdt < Decimal(0):
            raise ValueError("paper portfolio cash cannot be negative")
        for value in (
            self.decision_count,
            self.simulated_fill_count,
            self.nav_snapshot_count,
            self.replayed_record_count,
        ):
            if value < 0:
                raise ValueError("portfolio record counts cannot be negative")
        if (self.last_mutation_identity is None) != (self.last_mutation_at_ms is None):
            raise ValueError("last mutation identity/time must appear together")
        if self.last_mutation_identity is not None:
            _require_sha256(self.last_mutation_identity, "last mutation identity")
        if self.last_mutation_at_ms is not None and self.last_mutation_at_ms < 0:
            raise ValueError("last mutation timestamp must be non-negative")

        symbols = tuple(item.symbol for item in self.positions)
        if symbols != tuple(sorted(symbols, key=lambda item: item.value)):
            raise ValueError("portfolio positions must be sorted")
        if len(set(symbols)) != len(symbols):
            raise ValueError("portfolio positions must be unique by symbol")
        expected_missing = tuple(
            item.symbol for item in self.positions if item.mark is None
        )
        if self.missing_mark_symbols != expected_missing:
            raise ValueError("missing mark symbols must match unmarked positions")

        if self.availability is PaperPortfolioAvailability.AVAILABLE:
            if self.missing_mark_symbols:
                raise ValueError("available portfolio cannot have missing marks")
            if any(item.marked_value_usdt is None for item in self.positions):
                raise ValueError("available portfolio requires all marked values")
            if any(
                value is None
                for value in (
                    self.marked_positions_value_usdt,
                    self.nav_usdt,
                    self.pnl_usdt,
                    self.total_return_fraction,
                )
            ):
                raise ValueError("available portfolio requires NAV/PnL/return metrics")
            marked_total = sum(
                (
                    item.marked_value_usdt
                    for item in self.positions
                    if item.marked_value_usdt is not None
                ),
                start=Decimal(0),
            )
            if self.marked_positions_value_usdt != marked_total:
                raise ValueError("marked portfolio value mismatch")
            if self.nav_usdt != self.cash_usdt + marked_total:
                raise ValueError("portfolio NAV mismatch")
            if self.pnl_usdt != self.nav_usdt - self.initial_cash_usdt:
                raise ValueError("portfolio PnL mismatch")
            if (
                self.total_return_fraction
                != self.pnl_usdt / self.initial_cash_usdt
            ):
                raise ValueError("portfolio total return mismatch")
        else:
            if not self.missing_mark_symbols:
                raise ValueError("missing-marks availability requires missing marks")
            if any(
                value is not None
                for value in (
                    self.marked_positions_value_usdt,
                    self.nav_usdt,
                    self.pnl_usdt,
                    self.total_return_fraction,
                )
            ):
                raise ValueError(
                    "incomplete marks cannot produce aggregate NAV/PnL/return"
                )

        expected_identity = canonical_sha256(_snapshot_identity_payload(self))
        if self.snapshot_identity != expected_identity:
            raise ValueError("portfolio snapshot identity mismatch")


def read_paper_portfolio_snapshot(
    *,
    paper_ledger_path: Path,
    candle_cache_path: Path,
    observed_at_ms: int,
) -> PaperPortfolioSnapshot:
    """Read immutable paper state and real closed-candle marks without writes."""
    if observed_at_ms < 0:
        raise ValueError("observed_at_ms must be non-negative")
    entries = read_paper_entries_read_only(paper_ledger_path)
    state = reconstruct_paper_fund_state_from_entries(entries)
    marks = _read_latest_marks_read_only(
        candle_cache_path=candle_cache_path,
        state=state,
        observed_at_ms=observed_at_ms,
    )
    return project_paper_portfolio(
        state=state,
        entries=entries,
        marks=marks,
        observed_at_ms=observed_at_ms,
    )


def project_paper_portfolio(
    *,
    state: PaperFundState,
    entries: tuple[PaperLedgerEntry, ...],
    marks: Mapping[PaperSymbol, PaperMarkEvidence],
    observed_at_ms: int,
) -> PaperPortfolioSnapshot:
    """Pure projection from reconstructed accounting truth plus mark evidence."""
    if state.real_capital != REAL_CAPITAL:
        raise PaperPortfolioError("REAL_CAPITAL must remain 0")
    if observed_at_ms < state.created_at_ms:
        raise PaperPortfolioError("portfolio observation predates fund creation")

    views: list[PaperPortfolioPositionView] = []
    for position in state.positions:
        mark = marks.get(position.symbol)
        if mark is not None:
            if mark.source_candle_close_time_ms > observed_at_ms:
                raise PaperPortfolioError("mark candle closes after observation time")
            if mark.source_candle_ingested_at_ms > observed_at_ms:
                raise PaperPortfolioError("mark was ingested after observation time")
            if mark.source_timestamp_ms > observed_at_ms:
                raise PaperPortfolioError("mark source timestamp is in the future")
        views.append(
            PaperPortfolioPositionView(
                symbol=position.symbol,
                quantity=position.quantity,
                mark=mark,
                marked_value_usdt=(
                    None if mark is None else position.quantity * mark.price
                ),
            )
        )

    positions = tuple(views)
    missing = tuple(item.symbol for item in positions if item.mark is None)
    if missing:
        availability = PaperPortfolioAvailability.MISSING_MARKS
        marked_total = None
        nav = None
        pnl = None
        total_return = None
    else:
        availability = PaperPortfolioAvailability.AVAILABLE
        marked_total = sum(
            (
                item.marked_value_usdt
                for item in positions
                if item.marked_value_usdt is not None
            ),
            start=Decimal(0),
        )
        nav = state.cash_usdt + marked_total
        pnl = nav - INITIAL_CASH_USDT
        total_return = pnl / INITIAL_CASH_USDT

    decision_count = sum(
        1 for entry in entries if isinstance(entry.record, DecisionIntentRecord)
    )
    fill_count = sum(
        1 for entry in entries if isinstance(entry.record, SimulatedFillRecord)
    )
    nav_snapshot_count = sum(
        1 for entry in entries if isinstance(entry.record, NavSnapshotRecord)
    )
    payload = {
        "availability": availability.value,
        "cash_usdt": state.cash_usdt,
        "decision_count": decision_count,
        "fund_identity": state.fund_identity,
        "initial_cash_usdt": INITIAL_CASH_USDT,
        "last_mutation_at_ms": state.last_mutation_at_ms,
        "last_mutation_identity": state.last_mutation_identity,
        "marked_positions_value_usdt": marked_total,
        "missing_mark_symbols": [item.value for item in missing],
        "nav_snapshot_count": nav_snapshot_count,
        "nav_usdt": nav,
        "observed_at_ms": observed_at_ms,
        "pnl_usdt": pnl,
        "positions": [_position_payload(item) for item in positions],
        "replayed_record_count": state.replayed_record_count,
        "simulated_fill_count": fill_count,
        "total_return_fraction": total_return,
        "version": PAPER_PORTFOLIO_VIEW_VERSION,
    }
    identity = canonical_sha256(payload)
    return PaperPortfolioSnapshot(
        snapshot_identity=identity,
        version=PAPER_PORTFOLIO_VIEW_VERSION,
        fund_identity=state.fund_identity,
        observed_at_ms=observed_at_ms,
        availability=availability,
        cash_usdt=state.cash_usdt,
        initial_cash_usdt=INITIAL_CASH_USDT,
        positions=positions,
        missing_mark_symbols=missing,
        marked_positions_value_usdt=marked_total,
        nav_usdt=nav,
        pnl_usdt=pnl,
        total_return_fraction=total_return,
        decision_count=decision_count,
        simulated_fill_count=fill_count,
        nav_snapshot_count=nav_snapshot_count,
        replayed_record_count=state.replayed_record_count,
        last_mutation_identity=state.last_mutation_identity,
        last_mutation_at_ms=state.last_mutation_at_ms,
        real_capital=REAL_CAPITAL,
    )


def read_paper_entries_read_only(path: Path) -> tuple[PaperLedgerEntry, ...]:
    if not path.exists():
        raise PaperPortfolioError("paper ledger does not exist")
    uri = f"file:{path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            _require_table(connection, "paper_replay_index", "paper ledger")
            for table in _TABLE_BY_KIND.values():
                _require_table(connection, table, "paper ledger")
            rows = connection.execute(
                """
                SELECT sequence_id, record_kind, record_identity, appended_at_ms
                FROM paper_replay_index
                ORDER BY sequence_id ASC
                """
            ).fetchall()
            entries: list[PaperLedgerEntry] = []
            for row in rows:
                try:
                    kind = PaperRecordKind(str(row["record_kind"]))
                except ValueError as exc:
                    raise PaperPortfolioError(
                        "paper replay index has unsupported record kind"
                    ) from exc
                table = _TABLE_BY_KIND[kind]
                payload_row = connection.execute(
                    f"""
                    SELECT payload_json
                    FROM {table}
                    WHERE record_identity = ?
                    """,
                    (str(row["record_identity"]),),
                ).fetchone()
                if payload_row is None:
                    raise PaperPortfolioError(
                        "paper replay index references missing payload"
                    )
                payload_json = str(payload_row["payload_json"])
                entries.append(
                    PaperLedgerEntry(
                        sequence_id=int(row["sequence_id"]),
                        record_kind=kind,
                        record_identity=str(row["record_identity"]),
                        appended_at_ms=int(row["appended_at_ms"]),
                        payload_json=payload_json,
                        record=deserialize_paper_record(kind, payload_json),
                    )
                )
    except sqlite3.Error as exc:
        raise PaperPortfolioError(f"failed to read paper ledger: {exc}") from exc
    return tuple(entries)


def _read_latest_marks_read_only(
    *,
    candle_cache_path: Path,
    state: PaperFundState,
    observed_at_ms: int,
) -> dict[PaperSymbol, PaperMarkEvidence]:
    if not state.positions:
        return {}
    if not candle_cache_path.exists():
        return {}
    uri = f"file:{candle_cache_path.resolve()}?mode=ro"
    marks: dict[PaperSymbol, PaperMarkEvidence] = {}
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            _require_table(connection, "candles", "candle cache")
            for position in state.positions:
                row = connection.execute(
                    """
                    SELECT
                        open_time_ms,
                        close_time_ms,
                        close,
                        ingested_at_ms,
                        source_timestamp_ms,
                        source,
                        adapter_version
                    FROM candles
                    WHERE exchange = ?
                      AND market_type = ?
                      AND symbol = ?
                      AND timeframe = ?
                      AND is_closed = 1
                      AND close_time_ms <= ?
                      AND ingested_at_ms <= ?
                      AND source_timestamp_ms <= ?
                    ORDER BY open_time_ms DESC
                    LIMIT 1
                    """,
                    (
                        _MARK_EXCHANGE.value,
                        _MARK_MARKET_TYPE.value,
                        position.symbol.value,
                        _MARK_TIMEFRAME,
                        observed_at_ms,
                        observed_at_ms,
                        observed_at_ms,
                    ),
                ).fetchone()
                if row is None:
                    continue
                marks[position.symbol] = _build_mark_evidence(
                    symbol=position.symbol,
                    price=Decimal(str(row["close"])),
                    source_candle_open_time_ms=int(row["open_time_ms"]),
                    source_candle_close_time_ms=int(row["close_time_ms"]),
                    source_candle_ingested_at_ms=int(row["ingested_at_ms"]),
                    source_timestamp_ms=int(row["source_timestamp_ms"]),
                    source=str(row["source"]),
                    source_adapter_version=str(row["adapter_version"]),
                )
    except sqlite3.Error as exc:
        raise PaperPortfolioError(f"failed to read candle marks: {exc}") from exc
    return marks


def _build_mark_evidence(
    *,
    symbol: PaperSymbol,
    price: Decimal,
    source_candle_open_time_ms: int,
    source_candle_close_time_ms: int,
    source_candle_ingested_at_ms: int,
    source_timestamp_ms: int,
    source: str,
    source_adapter_version: str,
) -> PaperMarkEvidence:
    payload = {
        "price": price,
        "price_field": _MARK_PRICE_FIELD,
        "source": source,
        "source_adapter_version": source_adapter_version,
        "source_candle_close_time_ms": source_candle_close_time_ms,
        "source_candle_ingested_at_ms": source_candle_ingested_at_ms,
        "source_candle_open_time_ms": source_candle_open_time_ms,
        "source_exchange": _MARK_EXCHANGE.value,
        "source_market_type": _MARK_MARKET_TYPE.value,
        "source_timeframe": _MARK_TIMEFRAME,
        "source_timestamp_ms": source_timestamp_ms,
        "symbol": symbol.value,
    }
    return PaperMarkEvidence(
        mark_identity=canonical_sha256(payload),
        symbol=symbol,
        price=price,
        source_exchange=_MARK_EXCHANGE,
        source_market_type=_MARK_MARKET_TYPE,
        source_timeframe=_MARK_TIMEFRAME,
        source_candle_open_time_ms=source_candle_open_time_ms,
        source_candle_close_time_ms=source_candle_close_time_ms,
        source_candle_ingested_at_ms=source_candle_ingested_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        source=source,
        source_adapter_version=source_adapter_version,
        price_field=_MARK_PRICE_FIELD,
    )


def _mark_identity_payload(mark: PaperMarkEvidence) -> dict[str, object]:
    return {
        "price": mark.price,
        "price_field": mark.price_field,
        "source": mark.source,
        "source_adapter_version": mark.source_adapter_version,
        "source_candle_close_time_ms": mark.source_candle_close_time_ms,
        "source_candle_ingested_at_ms": mark.source_candle_ingested_at_ms,
        "source_candle_open_time_ms": mark.source_candle_open_time_ms,
        "source_exchange": mark.source_exchange.value,
        "source_market_type": mark.source_market_type.value,
        "source_timeframe": mark.source_timeframe,
        "source_timestamp_ms": mark.source_timestamp_ms,
        "symbol": mark.symbol.value,
    }


def _position_payload(position: PaperPortfolioPositionView) -> dict[str, object]:
    return {
        "mark": None if position.mark is None else _mark_identity_payload(position.mark),
        "mark_identity": (
            None if position.mark is None else position.mark.mark_identity
        ),
        "marked_value_usdt": position.marked_value_usdt,
        "quantity": position.quantity,
        "symbol": position.symbol.value,
    }


def _snapshot_identity_payload(
    snapshot: PaperPortfolioSnapshot,
) -> dict[str, object]:
    return {
        "availability": snapshot.availability.value,
        "cash_usdt": snapshot.cash_usdt,
        "decision_count": snapshot.decision_count,
        "fund_identity": snapshot.fund_identity,
        "initial_cash_usdt": snapshot.initial_cash_usdt,
        "last_mutation_at_ms": snapshot.last_mutation_at_ms,
        "last_mutation_identity": snapshot.last_mutation_identity,
        "marked_positions_value_usdt": snapshot.marked_positions_value_usdt,
        "missing_mark_symbols": [
            item.value for item in snapshot.missing_mark_symbols
        ],
        "nav_snapshot_count": snapshot.nav_snapshot_count,
        "nav_usdt": snapshot.nav_usdt,
        "observed_at_ms": snapshot.observed_at_ms,
        "pnl_usdt": snapshot.pnl_usdt,
        "positions": [_position_payload(item) for item in snapshot.positions],
        "replayed_record_count": snapshot.replayed_record_count,
        "simulated_fill_count": snapshot.simulated_fill_count,
        "total_return_fraction": snapshot.total_return_fraction,
        "version": snapshot.version,
    }


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
        raise PaperPortfolioError(f"{label} missing required table: {table}")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
