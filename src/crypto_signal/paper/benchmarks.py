"""Read-only paper benchmark projection from point-in-time closed candle evidence.

Benchmarks start at the immutable paper activation cutoff and use only Binance
Spot 15m candles that were fully closed and available by the relevant point in
time. They are reference comparisons, not simulated executions and never grant
order authority. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import INITIAL_CASH_USDT, REAL_CAPITAL, PaperSymbol

PAPER_BENCHMARK_VERSION = "paper_benchmarks.v1"
_BENCHMARK_EXCHANGE = Exchange.BINANCE
_BENCHMARK_MARKET_TYPE = MarketType.SPOT
_BENCHMARK_TIMEFRAME = "15m"
_BENCHMARK_SYMBOLS = (
    PaperSymbol.BTCUSDT,
    PaperSymbol.ETHUSDT,
    PaperSymbol.SOLUSDT,
)


class PaperBenchmarkKind(StrEnum):
    CASH = "cash_100_usdt"
    BTC_BUY_HOLD = "btc_buy_hold_100_usdt"
    BTC_ETH_SOL_EQUAL_WEIGHT = "btc_eth_sol_equal_weight_100_usdt"


class PaperBenchmarkAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING_MARKS = "missing_marks"


@dataclass(frozen=True, slots=True)
class PaperBenchmarkMark:
    mark_identity: str
    symbol: PaperSymbol
    price: Decimal
    candle_open_time_ms: int
    candle_close_time_ms: int
    ingested_at_ms: int
    source_timestamp_ms: int
    source: str
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.mark_identity, "benchmark mark identity")
        if self.price <= Decimal(0):
            raise ValueError("benchmark mark price must be positive")
        if self.candle_open_time_ms < 0:
            raise ValueError("benchmark mark open time must be non-negative")
        if self.candle_close_time_ms <= self.candle_open_time_ms:
            raise ValueError("benchmark mark candle bounds are invalid")
        if min(self.ingested_at_ms, self.source_timestamp_ms) < 0:
            raise ValueError("benchmark mark source times must be non-negative")
        if not self.source.strip() or not self.adapter_version.strip():
            raise ValueError("benchmark mark source metadata must be non-empty")
        if self.mark_identity != canonical_sha256(_mark_payload(self)):
            raise ValueError("benchmark mark identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperBenchmarkPosition:
    symbol: PaperSymbol
    allocation_usdt: Decimal
    quantity: Decimal
    start_mark: PaperBenchmarkMark
    end_mark: PaperBenchmarkMark
    ending_value_usdt: Decimal

    def __post_init__(self) -> None:
        if self.allocation_usdt <= Decimal(0):
            raise ValueError("benchmark allocation must be positive")
        if self.quantity <= Decimal(0):
            raise ValueError("benchmark quantity must be positive")
        if self.start_mark.symbol is not self.symbol:
            raise ValueError("benchmark start mark symbol mismatch")
        if self.end_mark.symbol is not self.symbol:
            raise ValueError("benchmark end mark symbol mismatch")
        if self.quantity != self.allocation_usdt / self.start_mark.price:
            raise ValueError("benchmark quantity must derive from start mark")
        if self.ending_value_usdt != self.quantity * self.end_mark.price:
            raise ValueError("benchmark ending value must derive from end mark")


@dataclass(frozen=True, slots=True)
class PaperBenchmarkResult:
    kind: PaperBenchmarkKind
    availability: PaperBenchmarkAvailability
    initial_capital_usdt: Decimal
    start_at_ms: int
    observed_at_ms: int
    positions: tuple[PaperBenchmarkPosition, ...]
    missing_start_symbols: tuple[PaperSymbol, ...]
    missing_end_symbols: tuple[PaperSymbol, ...]
    nav_usdt: Decimal | None
    total_return_fraction: Decimal | None
    semantic: str = "frictionless_reference_not_execution"
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("benchmark must remain REAL_CAPITAL=0")
        if self.initial_capital_usdt != INITIAL_CASH_USDT:
            raise ValueError("benchmark initial capital must remain 100 USDT")
        if self.start_at_ms < 0 or self.observed_at_ms < self.start_at_ms:
            raise ValueError("benchmark time bounds are invalid")
        if self.semantic != "frictionless_reference_not_execution":
            raise ValueError("unsupported benchmark semantic")
        missing = self.missing_start_symbols + self.missing_end_symbols
        if self.kind is PaperBenchmarkKind.CASH:
            if missing or self.positions:
                raise ValueError("cash benchmark cannot carry market positions")
            if self.availability is not PaperBenchmarkAvailability.AVAILABLE:
                raise ValueError("cash benchmark must always be available")
            if self.nav_usdt != INITIAL_CASH_USDT:
                raise ValueError("cash benchmark NAV must remain 100 USDT")
            if self.total_return_fraction != Decimal(0):
                raise ValueError("cash benchmark return must be zero")
            return
        if self.availability is PaperBenchmarkAvailability.MISSING_MARKS:
            if not missing:
                raise ValueError("missing-marks benchmark requires missing symbols")
            if self.positions:
                raise ValueError("incomplete benchmark cannot carry positions")
            if self.nav_usdt is not None or self.total_return_fraction is not None:
                raise ValueError("incomplete benchmark cannot fabricate performance")
            return
        if missing:
            raise ValueError("available benchmark cannot have missing marks")
        if not self.positions:
            raise ValueError("available market benchmark requires positions")
        if sum(
            (item.allocation_usdt for item in self.positions),
            start=Decimal(0),
        ) != INITIAL_CASH_USDT:
            raise ValueError("benchmark allocations must sum to 100 USDT")
        expected_nav = sum(
            (item.ending_value_usdt for item in self.positions),
            start=Decimal(0),
        )
        if self.nav_usdt != expected_nav:
            raise ValueError("benchmark NAV mismatch")
        if self.total_return_fraction != (
            expected_nav - INITIAL_CASH_USDT
        ) / INITIAL_CASH_USDT:
            raise ValueError("benchmark return mismatch")


@dataclass(frozen=True, slots=True)
class PaperBenchmarkSnapshot:
    snapshot_identity: str
    version: str
    start_at_ms: int
    observed_at_ms: int
    results: tuple[PaperBenchmarkResult, ...]
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "benchmark snapshot identity")
        if self.version != PAPER_BENCHMARK_VERSION:
            raise ValueError("unsupported benchmark snapshot version")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("benchmark snapshot must remain REAL_CAPITAL=0")
        if self.start_at_ms < 0 or self.observed_at_ms < self.start_at_ms:
            raise ValueError("benchmark snapshot time bounds are invalid")
        expected_kinds = (
            PaperBenchmarkKind.CASH,
            PaperBenchmarkKind.BTC_BUY_HOLD,
            PaperBenchmarkKind.BTC_ETH_SOL_EQUAL_WEIGHT,
        )
        if tuple(item.kind for item in self.results) != expected_kinds:
            raise ValueError("benchmark result order/coverage mismatch")
        if any(
            item.start_at_ms != self.start_at_ms
            or item.observed_at_ms != self.observed_at_ms
            for item in self.results
        ):
            raise ValueError("benchmark result time bounds mismatch")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("benchmark snapshot identity mismatch")


def read_paper_benchmark_snapshot(
    *,
    candle_cache_path: Path,
    start_at_ms: int,
    observed_at_ms: int,
) -> PaperBenchmarkSnapshot:
    """Read all required benchmark marks through SQLite mode=ro/query_only."""
    if start_at_ms < 0 or observed_at_ms < start_at_ms:
        raise ValueError("benchmark time bounds are invalid")
    start_marks = _read_marks_at(
        candle_cache_path=candle_cache_path,
        as_of_ms=start_at_ms,
    )
    end_marks = _read_marks_at(
        candle_cache_path=candle_cache_path,
        as_of_ms=observed_at_ms,
    )
    return project_paper_benchmarks(
        start_marks=start_marks,
        end_marks=end_marks,
        start_at_ms=start_at_ms,
        observed_at_ms=observed_at_ms,
    )


def project_paper_benchmarks(
    *,
    start_marks: dict[PaperSymbol, PaperBenchmarkMark],
    end_marks: dict[PaperSymbol, PaperBenchmarkMark],
    start_at_ms: int,
    observed_at_ms: int,
) -> PaperBenchmarkSnapshot:
    if start_at_ms < 0 or observed_at_ms < start_at_ms:
        raise ValueError("benchmark time bounds are invalid")
    if any(mark.candle_close_time_ms > start_at_ms for mark in start_marks.values()):
        raise ValueError("benchmark start mark closes after start time")
    if any(mark.candle_close_time_ms > observed_at_ms for mark in end_marks.values()):
        raise ValueError("benchmark end mark closes after observation time")

    cash = PaperBenchmarkResult(
        kind=PaperBenchmarkKind.CASH,
        availability=PaperBenchmarkAvailability.AVAILABLE,
        initial_capital_usdt=INITIAL_CASH_USDT,
        start_at_ms=start_at_ms,
        observed_at_ms=observed_at_ms,
        positions=(),
        missing_start_symbols=(),
        missing_end_symbols=(),
        nav_usdt=INITIAL_CASH_USDT,
        total_return_fraction=Decimal(0),
    )
    btc = _market_result(
        kind=PaperBenchmarkKind.BTC_BUY_HOLD,
        symbols=(PaperSymbol.BTCUSDT,),
        allocations=(INITIAL_CASH_USDT,),
        start_marks=start_marks,
        end_marks=end_marks,
        start_at_ms=start_at_ms,
        observed_at_ms=observed_at_ms,
    )
    one_third = INITIAL_CASH_USDT / Decimal(3)
    equal = _market_result(
        kind=PaperBenchmarkKind.BTC_ETH_SOL_EQUAL_WEIGHT,
        symbols=_BENCHMARK_SYMBOLS,
        allocations=(
            one_third,
            one_third,
            INITIAL_CASH_USDT - one_third - one_third,
        ),
        start_marks=start_marks,
        end_marks=end_marks,
        start_at_ms=start_at_ms,
        observed_at_ms=observed_at_ms,
    )
    results = (cash, btc, equal)
    payload = {
        "observed_at_ms": observed_at_ms,
        "results": [_result_payload(item) for item in results],
        "start_at_ms": start_at_ms,
        "version": PAPER_BENCHMARK_VERSION,
    }
    return PaperBenchmarkSnapshot(
        snapshot_identity=canonical_sha256(payload),
        version=PAPER_BENCHMARK_VERSION,
        start_at_ms=start_at_ms,
        observed_at_ms=observed_at_ms,
        results=results,
        real_capital=REAL_CAPITAL,
    )


def _market_result(
    *,
    kind: PaperBenchmarkKind,
    symbols: tuple[PaperSymbol, ...],
    allocations: tuple[Decimal, ...],
    start_marks: dict[PaperSymbol, PaperBenchmarkMark],
    end_marks: dict[PaperSymbol, PaperBenchmarkMark],
    start_at_ms: int,
    observed_at_ms: int,
) -> PaperBenchmarkResult:
    missing_start = tuple(symbol for symbol in symbols if symbol not in start_marks)
    missing_end = tuple(symbol for symbol in symbols if symbol not in end_marks)
    if missing_start or missing_end:
        return PaperBenchmarkResult(
            kind=kind,
            availability=PaperBenchmarkAvailability.MISSING_MARKS,
            initial_capital_usdt=INITIAL_CASH_USDT,
            start_at_ms=start_at_ms,
            observed_at_ms=observed_at_ms,
            positions=(),
            missing_start_symbols=missing_start,
            missing_end_symbols=missing_end,
            nav_usdt=None,
            total_return_fraction=None,
        )
    positions = tuple(
        _position(
            symbol=symbol,
            allocation=allocation,
            start_mark=start_marks[symbol],
            end_mark=end_marks[symbol],
        )
        for symbol, allocation in zip(symbols, allocations, strict=True)
    )
    nav = sum(
        (item.ending_value_usdt for item in positions),
        start=Decimal(0),
    )
    return PaperBenchmarkResult(
        kind=kind,
        availability=PaperBenchmarkAvailability.AVAILABLE,
        initial_capital_usdt=INITIAL_CASH_USDT,
        start_at_ms=start_at_ms,
        observed_at_ms=observed_at_ms,
        positions=positions,
        missing_start_symbols=(),
        missing_end_symbols=(),
        nav_usdt=nav,
        total_return_fraction=(
            nav - INITIAL_CASH_USDT
        ) / INITIAL_CASH_USDT,
    )


def _position(
    *,
    symbol: PaperSymbol,
    allocation: Decimal,
    start_mark: PaperBenchmarkMark,
    end_mark: PaperBenchmarkMark,
) -> PaperBenchmarkPosition:
    quantity = allocation / start_mark.price
    return PaperBenchmarkPosition(
        symbol=symbol,
        allocation_usdt=allocation,
        quantity=quantity,
        start_mark=start_mark,
        end_mark=end_mark,
        ending_value_usdt=quantity * end_mark.price,
    )


def _read_marks_at(
    *,
    candle_cache_path: Path,
    as_of_ms: int,
) -> dict[PaperSymbol, PaperBenchmarkMark]:
    if not candle_cache_path.exists():
        return {}
    uri = f"file:{candle_cache_path.resolve()}?mode=ro"
    marks: dict[PaperSymbol, PaperBenchmarkMark] = {}
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
                return {}
            for symbol in _BENCHMARK_SYMBOLS:
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
                        _BENCHMARK_EXCHANGE.value,
                        _BENCHMARK_MARKET_TYPE.value,
                        symbol.value,
                        _BENCHMARK_TIMEFRAME,
                        as_of_ms,
                        as_of_ms,
                        as_of_ms,
                    ),
                ).fetchone()
                if row is None:
                    continue
                marks[symbol] = _build_mark(symbol=symbol, row=row)
    except sqlite3.Error as exc:
        raise RuntimeError(f"failed to read paper benchmark marks: {exc}") from exc
    return marks


def _build_mark(*, symbol: PaperSymbol, row: sqlite3.Row) -> PaperBenchmarkMark:
    adapter_version = str(row["adapter_version"])
    candle_close_time_ms = int(row["close_time_ms"])
    candle_open_time_ms = int(row["open_time_ms"])
    ingested_at_ms = int(row["ingested_at_ms"])
    price = Decimal(str(row["close"]))
    source = str(row["source"])
    source_timestamp_ms = int(row["source_timestamp_ms"])
    payload = {
        "adapter_version": adapter_version,
        "candle_close_time_ms": candle_close_time_ms,
        "candle_open_time_ms": candle_open_time_ms,
        "ingested_at_ms": ingested_at_ms,
        "price": price,
        "source": source,
        "source_timestamp_ms": source_timestamp_ms,
        "symbol": symbol.value,
    }
    return PaperBenchmarkMark(
        mark_identity=canonical_sha256(payload),
        symbol=symbol,
        price=price,
        candle_open_time_ms=candle_open_time_ms,
        candle_close_time_ms=candle_close_time_ms,
        ingested_at_ms=ingested_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        source=source,
        adapter_version=adapter_version,
    )


def _mark_payload(mark: PaperBenchmarkMark) -> dict[str, object]:
    return {
        "adapter_version": mark.adapter_version,
        "candle_close_time_ms": mark.candle_close_time_ms,
        "candle_open_time_ms": mark.candle_open_time_ms,
        "ingested_at_ms": mark.ingested_at_ms,
        "price": mark.price,
        "source": mark.source,
        "source_timestamp_ms": mark.source_timestamp_ms,
        "symbol": mark.symbol.value,
    }


def _position_payload(position: PaperBenchmarkPosition) -> dict[str, object]:
    return {
        "allocation_usdt": position.allocation_usdt,
        "ending_value_usdt": position.ending_value_usdt,
        "end_mark_identity": position.end_mark.mark_identity,
        "quantity": position.quantity,
        "start_mark_identity": position.start_mark.mark_identity,
        "symbol": position.symbol.value,
    }


def _result_payload(result: PaperBenchmarkResult) -> dict[str, object]:
    return {
        "availability": result.availability.value,
        "initial_capital_usdt": result.initial_capital_usdt,
        "kind": result.kind.value,
        "missing_end_symbols": [item.value for item in result.missing_end_symbols],
        "missing_start_symbols": [item.value for item in result.missing_start_symbols],
        "nav_usdt": result.nav_usdt,
        "observed_at_ms": result.observed_at_ms,
        "positions": [_position_payload(item) for item in result.positions],
        "semantic": result.semantic,
        "start_at_ms": result.start_at_ms,
        "total_return_fraction": result.total_return_fraction,
    }


def _snapshot_payload(snapshot: PaperBenchmarkSnapshot) -> dict[str, object]:
    return {
        "observed_at_ms": snapshot.observed_at_ms,
        "results": [_result_payload(item) for item in snapshot.results],
        "start_at_ms": snapshot.start_at_ms,
        "version": snapshot.version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
