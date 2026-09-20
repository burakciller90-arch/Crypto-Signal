"""Deterministic closed-trade performance for the virtual paper fund.

This module reports performance only from immutable simulated fill evidence.
Spread/slippage are already embedded in simulated fill prices; fee cash impact is
applied separately, matching paper orchestration. Explicit execution-cost totals
are reported for audit but are never subtracted twice from PnL.

No closed round trip means performance is NOT_YET_MEASURED rather than a
fabricated 0% win rate. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.execution import total_simulated_cost_usdt
from crypto_signal.paper.ledger import PaperLedgerEntry
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperAction,
    PaperSymbol,
    SimulatedFillRecord,
)
from crypto_signal.paper.portfolio import read_paper_entries_read_only
from crypto_signal.paper.state import reconstruct_paper_fund_state_from_entries

__all__ = [
    "PAPER_TRADE_PERFORMANCE_VERSION",
    "PaperClosedTradeResult",
    "PaperTradeOutcome",
    "PaperTradePerformanceError",
    "PaperTradePerformanceSnapshot",
    "PaperTradePerformanceStatus",
    "project_paper_trade_performance",
    "read_paper_trade_performance",
]

PAPER_TRADE_PERFORMANCE_VERSION = "paper_trade_performance.v1"


class PaperTradePerformanceError(RuntimeError):
    """Raised when immutable fill lineage is unsafe to score."""


class PaperTradePerformanceStatus(StrEnum):
    NOT_YET_MEASURED = "not_yet_measured"
    AVAILABLE = "available"


class PaperTradeOutcome(StrEnum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"


@dataclass(frozen=True, slots=True)
class PaperClosedTradeResult:
    trade_identity: str
    symbol: PaperSymbol
    quantity: Decimal
    entry_fill_identity: str
    exit_fill_identity: str
    entered_at_ms: int
    exited_at_ms: int
    entry_fill_price: Decimal
    exit_fill_price: Decimal
    entry_cash_outflow_usdt: Decimal
    exit_cash_inflow_usdt: Decimal
    net_pnl_usdt: Decimal
    return_fraction: Decimal
    explicit_execution_cost_usdt: Decimal
    outcome: PaperTradeOutcome

    def __post_init__(self) -> None:
        _require_sha256(self.trade_identity, "trade identity")
        _require_sha256(self.entry_fill_identity, "entry fill identity")
        _require_sha256(self.exit_fill_identity, "exit fill identity")
        if self.exit_fill_identity == self.entry_fill_identity:
            raise ValueError("entry/exit fill identities must differ")
        if self.entered_at_ms < 0 or self.exited_at_ms < self.entered_at_ms:
            raise ValueError("closed trade time bounds are invalid")
        for label, value in (
            ("quantity", self.quantity),
            ("entry_fill_price", self.entry_fill_price),
            ("exit_fill_price", self.exit_fill_price),
            ("entry_cash_outflow_usdt", self.entry_cash_outflow_usdt),
            ("exit_cash_inflow_usdt", self.exit_cash_inflow_usdt),
            ("explicit_execution_cost_usdt", self.explicit_execution_cost_usdt),
        ):
            if (
                not isinstance(value, Decimal)
                or value.is_nan()
                or value.is_infinite()
                or value <= Decimal(0)
            ):
                raise ValueError(f"{label} must be finite and positive")
        if (
            not isinstance(self.net_pnl_usdt, Decimal)
            or self.net_pnl_usdt.is_nan()
            or self.net_pnl_usdt.is_infinite()
        ):
            raise ValueError("net_pnl_usdt must be finite")
        if (
            not isinstance(self.return_fraction, Decimal)
            or self.return_fraction.is_nan()
            or self.return_fraction.is_infinite()
        ):
            raise ValueError("return_fraction must be finite")
        expected_pnl = self.exit_cash_inflow_usdt - self.entry_cash_outflow_usdt
        if self.net_pnl_usdt != expected_pnl:
            raise ValueError("closed trade net PnL mismatch")
        if self.return_fraction != self.net_pnl_usdt / self.entry_cash_outflow_usdt:
            raise ValueError("closed trade return mismatch")
        expected_outcome = _outcome_for_pnl(self.net_pnl_usdt)
        if self.outcome is not expected_outcome:
            raise ValueError("closed trade outcome does not match PnL")
        if self.trade_identity != canonical_sha256(_closed_trade_payload(self)):
            raise ValueError("closed trade identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperTradePerformanceSnapshot:
    snapshot_identity: str
    version: str
    fund_identity: str
    observed_at_ms: int
    status: PaperTradePerformanceStatus
    closed_trades: tuple[PaperClosedTradeResult, ...]
    open_trade_symbols: tuple[PaperSymbol, ...]
    closed_trade_count: int
    open_trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate_fraction: Decimal | None
    total_closed_trade_net_pnl_usdt: Decimal | None
    average_closed_trade_net_pnl_usdt: Decimal | None
    average_closed_trade_return_fraction: Decimal | None
    gross_profit_usdt: Decimal | None
    gross_loss_usdt: Decimal | None
    profit_factor: Decimal | None
    best_trade_pnl_usdt: Decimal | None
    worst_trade_pnl_usdt: Decimal | None
    total_explicit_execution_cost_usdt: Decimal | None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "performance snapshot identity")
        _require_sha256(self.fund_identity, "fund identity")
        if self.version != PAPER_TRADE_PERFORMANCE_VERSION:
            raise ValueError("unsupported paper trade performance version")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.observed_at_ms < 0:
            raise ValueError("performance observation time must be non-negative")
        if self.closed_trade_count != len(self.closed_trades):
            raise ValueError("closed_trade_count mismatch")
        if self.open_trade_count != len(self.open_trade_symbols):
            raise ValueError("open_trade_count mismatch")
        if self.open_trade_symbols != tuple(
            sorted(self.open_trade_symbols, key=lambda item: item.value)
        ):
            raise ValueError("open trade symbols must be sorted")
        if len(set(self.open_trade_symbols)) != len(self.open_trade_symbols):
            raise ValueError("open trade symbols must be unique")
        if self.win_count + self.loss_count + self.breakeven_count != self.closed_trade_count:
            raise ValueError("closed trade outcome counts do not reconcile")

        metric_values = (
            self.win_rate_fraction,
            self.total_closed_trade_net_pnl_usdt,
            self.average_closed_trade_net_pnl_usdt,
            self.average_closed_trade_return_fraction,
            self.gross_profit_usdt,
            self.gross_loss_usdt,
            self.best_trade_pnl_usdt,
            self.worst_trade_pnl_usdt,
            self.total_explicit_execution_cost_usdt,
        )
        if self.status is PaperTradePerformanceStatus.NOT_YET_MEASURED:
            if self.closed_trade_count != 0:
                raise ValueError("not-yet-measured status requires zero closed trades")
            if any(value is not None for value in metric_values):
                raise ValueError("unmeasured performance cannot carry aggregate metrics")
            if self.profit_factor is not None:
                raise ValueError("unmeasured performance cannot carry profit factor")
        else:
            if self.closed_trade_count <= 0:
                raise ValueError("available performance requires closed trades")
            if any(value is None for value in metric_values):
                raise ValueError("available performance requires aggregate metrics")
            assert self.win_rate_fraction is not None
            assert self.total_closed_trade_net_pnl_usdt is not None
            assert self.average_closed_trade_net_pnl_usdt is not None
            assert self.average_closed_trade_return_fraction is not None
            assert self.gross_profit_usdt is not None
            assert self.gross_loss_usdt is not None
            assert self.best_trade_pnl_usdt is not None
            assert self.worst_trade_pnl_usdt is not None
            assert self.total_explicit_execution_cost_usdt is not None
            if self.win_rate_fraction != Decimal(self.win_count) / Decimal(
                self.closed_trade_count
            ):
                raise ValueError("win rate mismatch")
            total_pnl = sum(
                (trade.net_pnl_usdt for trade in self.closed_trades),
                start=Decimal(0),
            )
            if self.total_closed_trade_net_pnl_usdt != total_pnl:
                raise ValueError("total closed-trade PnL mismatch")
            if (
                self.average_closed_trade_net_pnl_usdt
                != total_pnl / Decimal(self.closed_trade_count)
            ):
                raise ValueError("average closed-trade PnL mismatch")
            average_return = sum(
                (trade.return_fraction for trade in self.closed_trades),
                start=Decimal(0),
            ) / Decimal(self.closed_trade_count)
            if self.average_closed_trade_return_fraction != average_return:
                raise ValueError("average closed-trade return mismatch")
            gross_profit = sum(
                (
                    trade.net_pnl_usdt
                    for trade in self.closed_trades
                    if trade.net_pnl_usdt > Decimal(0)
                ),
                start=Decimal(0),
            )
            gross_loss = sum(
                (
                    -trade.net_pnl_usdt
                    for trade in self.closed_trades
                    if trade.net_pnl_usdt < Decimal(0)
                ),
                start=Decimal(0),
            )
            if self.gross_profit_usdt != gross_profit:
                raise ValueError("gross profit mismatch")
            if self.gross_loss_usdt != gross_loss:
                raise ValueError("gross loss mismatch")
            expected_profit_factor = (
                None if gross_loss == Decimal(0) else gross_profit / gross_loss
            )
            if self.profit_factor != expected_profit_factor:
                raise ValueError("profit factor mismatch")
            if self.best_trade_pnl_usdt != max(
                trade.net_pnl_usdt for trade in self.closed_trades
            ):
                raise ValueError("best-trade PnL mismatch")
            if self.worst_trade_pnl_usdt != min(
                trade.net_pnl_usdt for trade in self.closed_trades
            ):
                raise ValueError("worst-trade PnL mismatch")
            total_cost = sum(
                (trade.explicit_execution_cost_usdt for trade in self.closed_trades),
                start=Decimal(0),
            )
            if self.total_explicit_execution_cost_usdt != total_cost:
                raise ValueError("total execution cost mismatch")

        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("performance snapshot identity mismatch")


def read_paper_trade_performance(
    *,
    paper_ledger_path: Path,
    observed_at_ms: int,
) -> PaperTradePerformanceSnapshot:
    """Read the immutable paper ledger without writes and score closed trades."""
    entries = read_paper_entries_read_only(paper_ledger_path)
    state = reconstruct_paper_fund_state_from_entries(entries)
    return project_paper_trade_performance(
        fund_identity=state.fund_identity,
        entries=entries,
        observed_at_ms=observed_at_ms,
    )


def project_paper_trade_performance(
    *,
    fund_identity: str,
    entries: tuple[PaperLedgerEntry, ...],
    observed_at_ms: int,
) -> PaperTradePerformanceSnapshot:
    if observed_at_ms < 0:
        raise ValueError("observed_at_ms must be non-negative")
    _require_sha256(fund_identity, "fund identity")

    fills = tuple(
        entry.record
        for entry in entries
        if isinstance(entry.record, SimulatedFillRecord)
    )
    open_entries: dict[PaperSymbol, SimulatedFillRecord] = {}
    closed: list[PaperClosedTradeResult] = []

    for fill in fills:
        if fill.fund_identity != fund_identity:
            raise PaperTradePerformanceError("cross-fund fill lineage rejected")
        if fill.filled_at_ms > observed_at_ms:
            raise PaperTradePerformanceError(
                "paper fill occurs after performance observation time"
            )
        if fill.action is PaperAction.BUY:
            if fill.symbol in open_entries:
                raise PaperTradePerformanceError(
                    "pyramided BUY fill sequence is unsupported by performance v1"
                )
            open_entries[fill.symbol] = fill
            continue
        if fill.action is PaperAction.EXIT:
            entry = open_entries.pop(fill.symbol, None)
            if entry is None:
                raise PaperTradePerformanceError(
                    "EXIT fill has no preceding open BUY fill"
                )
            closed.append(_close_trade(entry=entry, exit_fill=fill))
            continue
        raise PaperTradePerformanceError(
            f"fill action unsupported by performance v1: {fill.action.value}"
        )

    open_symbols = tuple(sorted(open_entries, key=lambda item: item.value))
    closed_trades = tuple(closed)
    if not closed_trades:
        status = PaperTradePerformanceStatus.NOT_YET_MEASURED
        win_count = loss_count = breakeven_count = 0
        win_rate = None
        total_pnl = average_pnl = average_return = None
        gross_profit = gross_loss = None
        profit_factor = None
        best_pnl = worst_pnl = None
        total_cost = None
    else:
        status = PaperTradePerformanceStatus.AVAILABLE
        win_count = sum(
            1 for trade in closed_trades if trade.outcome is PaperTradeOutcome.WIN
        )
        loss_count = sum(
            1 for trade in closed_trades if trade.outcome is PaperTradeOutcome.LOSS
        )
        breakeven_count = sum(
            1
            for trade in closed_trades
            if trade.outcome is PaperTradeOutcome.BREAKEVEN
        )
        count = Decimal(len(closed_trades))
        win_rate = Decimal(win_count) / count
        total_pnl = sum(
            (trade.net_pnl_usdt for trade in closed_trades),
            start=Decimal(0),
        )
        average_pnl = total_pnl / count
        average_return = (
            sum(
                (trade.return_fraction for trade in closed_trades),
                start=Decimal(0),
            )
            / count
        )
        gross_profit = sum(
            (
                trade.net_pnl_usdt
                for trade in closed_trades
                if trade.net_pnl_usdt > Decimal(0)
            ),
            start=Decimal(0),
        )
        gross_loss = sum(
            (
                -trade.net_pnl_usdt
                for trade in closed_trades
                if trade.net_pnl_usdt < Decimal(0)
            ),
            start=Decimal(0),
        )
        profit_factor = (
            None if gross_loss == Decimal(0) else gross_profit / gross_loss
        )
        best_pnl = max(trade.net_pnl_usdt for trade in closed_trades)
        worst_pnl = min(trade.net_pnl_usdt for trade in closed_trades)
        total_cost = sum(
            (trade.explicit_execution_cost_usdt for trade in closed_trades),
            start=Decimal(0),
        )

    payload = {
        "average_closed_trade_net_pnl_usdt": average_pnl,
        "average_closed_trade_return_fraction": average_return,
        "best_trade_pnl_usdt": best_pnl,
        "breakeven_count": breakeven_count,
        "closed_trades": [_closed_trade_payload(trade) for trade in closed_trades],
        "fund_identity": fund_identity,
        "gross_loss_usdt": gross_loss,
        "gross_profit_usdt": gross_profit,
        "loss_count": loss_count,
        "observed_at_ms": observed_at_ms,
        "open_trade_symbols": [item.value for item in open_symbols],
        "profit_factor": profit_factor,
        "status": status.value,
        "total_closed_trade_net_pnl_usdt": total_pnl,
        "total_explicit_execution_cost_usdt": total_cost,
        "version": PAPER_TRADE_PERFORMANCE_VERSION,
        "win_count": win_count,
        "win_rate_fraction": win_rate,
        "worst_trade_pnl_usdt": worst_pnl,
    }
    identity = canonical_sha256(payload)
    return PaperTradePerformanceSnapshot(
        snapshot_identity=identity,
        version=PAPER_TRADE_PERFORMANCE_VERSION,
        fund_identity=fund_identity,
        observed_at_ms=observed_at_ms,
        status=status,
        closed_trades=closed_trades,
        open_trade_symbols=open_symbols,
        closed_trade_count=len(closed_trades),
        open_trade_count=len(open_symbols),
        win_count=win_count,
        loss_count=loss_count,
        breakeven_count=breakeven_count,
        win_rate_fraction=win_rate,
        total_closed_trade_net_pnl_usdt=total_pnl,
        average_closed_trade_net_pnl_usdt=average_pnl,
        average_closed_trade_return_fraction=average_return,
        gross_profit_usdt=gross_profit,
        gross_loss_usdt=gross_loss,
        profit_factor=profit_factor,
        best_trade_pnl_usdt=best_pnl,
        worst_trade_pnl_usdt=worst_pnl,
        total_explicit_execution_cost_usdt=total_cost,
        real_capital=REAL_CAPITAL,
    )


def _close_trade(
    *,
    entry: SimulatedFillRecord,
    exit_fill: SimulatedFillRecord,
) -> PaperClosedTradeResult:
    if entry.action is not PaperAction.BUY:
        raise PaperTradePerformanceError("closed trade entry must be BUY")
    if exit_fill.action is not PaperAction.EXIT:
        raise PaperTradePerformanceError("closed trade exit must be EXIT")
    if entry.symbol is not exit_fill.symbol:
        raise PaperTradePerformanceError("closed trade symbol mismatch")
    if entry.quantity != exit_fill.quantity:
        raise PaperTradePerformanceError(
            "performance v1 requires full-quantity EXIT matching BUY"
        )
    if exit_fill.filled_at_ms < entry.filled_at_ms:
        raise PaperTradePerformanceError("EXIT fill predates BUY fill")

    entry_outflow = (
        entry.quantity * entry.simulated_fill_price + entry.costs.fee_usdt
    )
    exit_inflow = (
        exit_fill.quantity * exit_fill.simulated_fill_price
        - exit_fill.costs.fee_usdt
    )
    if exit_inflow <= Decimal(0):
        raise PaperTradePerformanceError("EXIT cash inflow must be positive")
    pnl = exit_inflow - entry_outflow
    return_fraction = pnl / entry_outflow
    explicit_cost = (
        total_simulated_cost_usdt(entry.costs)
        + total_simulated_cost_usdt(exit_fill.costs)
    )
    outcome = _outcome_for_pnl(pnl)
    payload = {
        "entered_at_ms": entry.filled_at_ms,
        "entry_cash_outflow_usdt": entry_outflow,
        "entry_fill_identity": entry.record_identity,
        "entry_fill_price": entry.simulated_fill_price,
        "exit_cash_inflow_usdt": exit_inflow,
        "exit_fill_identity": exit_fill.record_identity,
        "exit_fill_price": exit_fill.simulated_fill_price,
        "exited_at_ms": exit_fill.filled_at_ms,
        "explicit_execution_cost_usdt": explicit_cost,
        "net_pnl_usdt": pnl,
        "outcome": outcome.value,
        "quantity": entry.quantity,
        "return_fraction": return_fraction,
        "symbol": entry.symbol.value,
    }
    return PaperClosedTradeResult(
        trade_identity=canonical_sha256(payload),
        symbol=entry.symbol,
        quantity=entry.quantity,
        entry_fill_identity=entry.record_identity,
        exit_fill_identity=exit_fill.record_identity,
        entered_at_ms=entry.filled_at_ms,
        exited_at_ms=exit_fill.filled_at_ms,
        entry_fill_price=entry.simulated_fill_price,
        exit_fill_price=exit_fill.simulated_fill_price,
        entry_cash_outflow_usdt=entry_outflow,
        exit_cash_inflow_usdt=exit_inflow,
        net_pnl_usdt=pnl,
        return_fraction=return_fraction,
        explicit_execution_cost_usdt=explicit_cost,
        outcome=outcome,
    )


def _outcome_for_pnl(pnl: Decimal) -> PaperTradeOutcome:
    if pnl > Decimal(0):
        return PaperTradeOutcome.WIN
    if pnl < Decimal(0):
        return PaperTradeOutcome.LOSS
    return PaperTradeOutcome.BREAKEVEN


def _closed_trade_payload(trade: PaperClosedTradeResult) -> dict[str, object]:
    return {
        "entered_at_ms": trade.entered_at_ms,
        "entry_cash_outflow_usdt": trade.entry_cash_outflow_usdt,
        "entry_fill_identity": trade.entry_fill_identity,
        "entry_fill_price": trade.entry_fill_price,
        "exit_cash_inflow_usdt": trade.exit_cash_inflow_usdt,
        "exit_fill_identity": trade.exit_fill_identity,
        "exit_fill_price": trade.exit_fill_price,
        "exited_at_ms": trade.exited_at_ms,
        "explicit_execution_cost_usdt": trade.explicit_execution_cost_usdt,
        "net_pnl_usdt": trade.net_pnl_usdt,
        "outcome": trade.outcome.value,
        "quantity": trade.quantity,
        "return_fraction": trade.return_fraction,
        "symbol": trade.symbol.value,
    }


def _snapshot_payload(
    snapshot: PaperTradePerformanceSnapshot,
) -> dict[str, object]:
    return {
        "average_closed_trade_net_pnl_usdt": (
            snapshot.average_closed_trade_net_pnl_usdt
        ),
        "average_closed_trade_return_fraction": (
            snapshot.average_closed_trade_return_fraction
        ),
        "best_trade_pnl_usdt": snapshot.best_trade_pnl_usdt,
        "breakeven_count": snapshot.breakeven_count,
        "closed_trades": [
            _closed_trade_payload(trade) for trade in snapshot.closed_trades
        ],
        "fund_identity": snapshot.fund_identity,
        "gross_loss_usdt": snapshot.gross_loss_usdt,
        "gross_profit_usdt": snapshot.gross_profit_usdt,
        "loss_count": snapshot.loss_count,
        "observed_at_ms": snapshot.observed_at_ms,
        "open_trade_symbols": [
            item.value for item in snapshot.open_trade_symbols
        ],
        "profit_factor": snapshot.profit_factor,
        "status": snapshot.status.value,
        "total_closed_trade_net_pnl_usdt": snapshot.total_closed_trade_net_pnl_usdt,
        "total_explicit_execution_cost_usdt": (
            snapshot.total_explicit_execution_cost_usdt
        ),
        "version": snapshot.version,
        "win_count": snapshot.win_count,
        "win_rate_fraction": snapshot.win_rate_fraction,
        "worst_trade_pnl_usdt": snapshot.worst_trade_pnl_usdt,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
