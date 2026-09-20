"""Deterministic domain models for the virtual 100 USDT paper fund.

Simulation only. REAL_CAPITAL remains 0. No real exchange order path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256

REAL_CAPITAL = 0
INITIAL_CASH_USDT = Decimal("100.00")
PAPER_FUND_SCHEMA_VERSION = "paper_fund.schema.v1"
PAPER_EXECUTION_POLICY_VERSION = "paper_execution_policy.v1"
PAPER_RISK_POLICY_VERSION = "paper_risk_policy.v1"

# Explicit limitation: partial fills are not implemented in v1.
PARTIAL_FILLS_SUPPORTED = False


class PaperSymbol(StrEnum):
    BTCUSDT = "BTCUSDT"
    ETHUSDT = "ETHUSDT"
    SOLUSDT = "SOLUSDT"


class PaperAction(StrEnum):
    HOLD_CASH = "HOLD_CASH"
    BUY = "BUY"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class BenchmarkId(StrEnum):
    CASH_100 = "CASH_100"
    BTC_BUY_HOLD_100 = "BTC_BUY_HOLD_100"
    BTC_ETH_SOL_EQUAL_WEIGHT_100 = "BTC_ETH_SOL_EQUAL_WEIGHT_100"


PERMITTED_SYMBOLS: frozenset[PaperSymbol] = frozenset(PaperSymbol)
PERMITTED_ACTIONS: frozenset[PaperAction] = frozenset(PaperAction)
BENCHMARK_IDS: frozenset[BenchmarkId] = frozenset(BenchmarkId)


def _require_non_negative_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal, not {type(value).__name__}")
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be a finite Decimal")
    if value < Decimal(0):
        raise ValueError(f"{label} cannot be negative")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be a SHA256 hex digest")


def _positions_payload(
    positions: tuple[PaperPosition, ...],
) -> list[dict[str, object]]:
    return [
        {"quantity": item.quantity, "symbol": item.symbol.value}
        for item in positions
    ]


@dataclass(frozen=True, slots=True)
class PaperPosition:
    """Non-negative virtual holding for one permitted symbol."""

    symbol: PaperSymbol
    quantity: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, PaperSymbol):
            raise TypeError("position symbol must be a PaperSymbol")
        _require_non_negative_decimal(self.quantity, "position quantity")


def normalize_positions(
    positions: Mapping[PaperSymbol, Decimal] | tuple[PaperPosition, ...],
) -> tuple[PaperPosition, ...]:
    """Return sorted positions with zero quantities omitted."""
    aggregated: dict[PaperSymbol, Decimal] = {}
    if isinstance(positions, tuple):
        items = positions
    else:
        items = tuple(
            PaperPosition(symbol=symbol, quantity=quantity)
            for symbol, quantity in positions.items()
        )
    for item in items:
        if not isinstance(item, PaperPosition):
            raise TypeError("positions must be PaperPosition values")
        _require_non_negative_decimal(item.quantity, "position quantity")
        aggregated[item.symbol] = (
            aggregated.get(item.symbol, Decimal(0)) + item.quantity
        )
    return tuple(
        PaperPosition(symbol=symbol, quantity=aggregated[symbol])
        for symbol in sorted(aggregated, key=lambda value: value.value)
        if aggregated[symbol] > Decimal(0)
    )


@dataclass(frozen=True, slots=True)
class ExecutionCostAssumptions:
    """Explicit simulated costs — free fills are forbidden."""

    fee_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    execution_policy_version: str = PAPER_EXECUTION_POLICY_VERSION
    partial_fills_supported: bool = PARTIAL_FILLS_SUPPORTED

    def __post_init__(self) -> None:
        _require_non_negative_decimal(self.fee_usdt, "fee_usdt")
        _require_non_negative_decimal(self.spread_usdt, "spread_usdt")
        _require_non_negative_decimal(self.slippage_usdt, "slippage_usdt")
        if not self.execution_policy_version.strip():
            raise ValueError("execution_policy_version must be non-empty")
        if self.partial_fills_supported is not False:
            raise ValueError("v1 partial fills are not supported; must be False")


@dataclass(frozen=True, slots=True)
class FundCreationRecord:
    """Immutable virtual fund creation at exactly 100.00 USDT cash."""

    record_identity: str
    created_at_ms: int
    initial_cash_usdt: Decimal
    real_capital: int
    positions: tuple[PaperPosition, ...]
    schema_version: str
    execution_policy_version: str
    risk_policy_version: str
    permitted_symbols: tuple[PaperSymbol, ...]
    benchmark_ids: tuple[BenchmarkId, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "fund creation identity")
        if self.created_at_ms < 0:
            raise ValueError("created_at_ms must be non-negative")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.initial_cash_usdt != INITIAL_CASH_USDT:
            raise ValueError("initial cash must be exactly 100.00 USDT")
        _require_non_negative_decimal(self.initial_cash_usdt, "initial_cash_usdt")
        if self.positions != ():
            raise ValueError("initial positions must be empty")
        if self.schema_version != PAPER_FUND_SCHEMA_VERSION:
            raise ValueError("unexpected paper fund schema version")
        if self.execution_policy_version != PAPER_EXECUTION_POLICY_VERSION:
            raise ValueError("unexpected execution policy version")
        if self.risk_policy_version != PAPER_RISK_POLICY_VERSION:
            raise ValueError("unexpected risk policy version")
        expected_symbols = tuple(
            sorted(PERMITTED_SYMBOLS, key=lambda item: item.value)
        )
        if self.permitted_symbols != expected_symbols:
            raise ValueError("permitted symbols must be BTCUSDT/ETHUSDT/SOLUSDT")
        expected_benchmarks = tuple(
            sorted(BENCHMARK_IDS, key=lambda item: item.value)
        )
        if self.benchmark_ids != expected_benchmarks:
            raise ValueError("benchmark ids must match the v1 contract set")
        if self.record_identity != compute_fund_creation_identity(
            created_at_ms=self.created_at_ms,
            initial_cash_usdt=self.initial_cash_usdt,
            real_capital=self.real_capital,
            positions=self.positions,
            schema_version=self.schema_version,
            execution_policy_version=self.execution_policy_version,
            risk_policy_version=self.risk_policy_version,
            permitted_symbols=self.permitted_symbols,
            benchmark_ids=self.benchmark_ids,
        ):
            raise ValueError("fund creation identity mismatch")


@dataclass(frozen=True, slots=True)
class DecisionIntentRecord:
    """Immutable paper decision intent — not a real exchange order."""

    record_identity: str
    fund_identity: str
    decided_at_ms: int
    action: PaperAction
    symbol: PaperSymbol | None
    quantity: Decimal | None
    reference_price: Decimal | None
    reason: str
    invalidation_context: str
    schema_version: str
    risk_policy_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "decision intent identity")
        _require_sha256(self.fund_identity, "fund identity")
        if self.decided_at_ms < 0:
            raise ValueError("decided_at_ms must be non-negative")
        if self.action not in PERMITTED_ACTIONS:
            raise ValueError(f"action not permitted: {self.action}")
        if self.action is PaperAction.HOLD_CASH:
            if self.symbol is not None or self.quantity is not None:
                raise ValueError("HOLD_CASH must not specify symbol or quantity")
            if self.reference_price is not None:
                raise ValueError("HOLD_CASH must not specify reference_price")
        else:
            if self.symbol is None or self.symbol not in PERMITTED_SYMBOLS:
                raise ValueError("trade action requires a permitted symbol")
            if self.quantity is None:
                raise ValueError("trade action requires quantity")
            _require_non_negative_decimal(self.quantity, "decision quantity")
            if self.quantity <= Decimal(0):
                raise ValueError("trade quantity must be positive")
            if self.reference_price is None:
                raise ValueError("trade action requires reference_price")
            _require_non_negative_decimal(self.reference_price, "reference_price")
            if self.reference_price <= Decimal(0):
                raise ValueError("reference_price must be positive")
        if not self.reason.strip():
            raise ValueError("reason must be non-empty")
        if not self.invalidation_context.strip():
            raise ValueError("invalidation_context must be non-empty")
        if self.schema_version != PAPER_FUND_SCHEMA_VERSION:
            raise ValueError("unexpected paper fund schema version")
        if self.risk_policy_version != PAPER_RISK_POLICY_VERSION:
            raise ValueError("unexpected risk policy version")
        if self.record_identity != compute_decision_intent_identity(
            fund_identity=self.fund_identity,
            decided_at_ms=self.decided_at_ms,
            action=self.action,
            symbol=self.symbol,
            quantity=self.quantity,
            reference_price=self.reference_price,
            reason=self.reason,
            invalidation_context=self.invalidation_context,
            schema_version=self.schema_version,
            risk_policy_version=self.risk_policy_version,
        ):
            raise ValueError("decision intent identity mismatch")


@dataclass(frozen=True, slots=True)
class SimulatedFillRecord:
    """Immutable simulated fill with explicit fee, spread and slippage."""

    record_identity: str
    fund_identity: str
    decision_identity: str
    filled_at_ms: int
    action: PaperAction
    symbol: PaperSymbol
    quantity: Decimal
    reference_price: Decimal
    simulated_fill_price: Decimal
    costs: ExecutionCostAssumptions
    venue_reference: str
    schema_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "simulated fill identity")
        _require_sha256(self.fund_identity, "fund identity")
        _require_sha256(self.decision_identity, "decision identity")
        if self.filled_at_ms < 0:
            raise ValueError("filled_at_ms must be non-negative")
        if self.action is PaperAction.HOLD_CASH:
            raise ValueError("HOLD_CASH does not produce a simulated fill")
        if self.action not in PERMITTED_ACTIONS:
            raise ValueError(f"action not permitted: {self.action}")
        if self.symbol not in PERMITTED_SYMBOLS:
            raise ValueError("fill symbol is not permitted")
        _require_non_negative_decimal(self.quantity, "fill quantity")
        if self.quantity <= Decimal(0):
            raise ValueError("fill quantity must be positive")
        _require_non_negative_decimal(self.reference_price, "reference_price")
        _require_non_negative_decimal(
            self.simulated_fill_price,
            "simulated_fill_price",
        )
        if self.reference_price <= Decimal(0) or self.simulated_fill_price <= Decimal(0):
            raise ValueError("fill prices must be positive")
        if not self.venue_reference.strip():
            raise ValueError("venue_reference must be non-empty")
        if self.schema_version != PAPER_FUND_SCHEMA_VERSION:
            raise ValueError("unexpected paper fund schema version")
        if self.record_identity != compute_simulated_fill_identity(
            fund_identity=self.fund_identity,
            decision_identity=self.decision_identity,
            filled_at_ms=self.filled_at_ms,
            action=self.action,
            symbol=self.symbol,
            quantity=self.quantity,
            reference_price=self.reference_price,
            simulated_fill_price=self.simulated_fill_price,
            costs=self.costs,
            venue_reference=self.venue_reference,
            schema_version=self.schema_version,
        ):
            raise ValueError("simulated fill identity mismatch")


@dataclass(frozen=True, slots=True)
class PositionCashMutationRecord:
    """Immutable cash/position mutation after a simulated decision or fill."""

    record_identity: str
    fund_identity: str
    source_identity: str
    mutated_at_ms: int
    cash_before_usdt: Decimal
    cash_after_usdt: Decimal
    positions_before: tuple[PaperPosition, ...]
    positions_after: tuple[PaperPosition, ...]
    schema_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "mutation identity")
        _require_sha256(self.fund_identity, "fund identity")
        _require_sha256(self.source_identity, "source identity")
        if self.mutated_at_ms < 0:
            raise ValueError("mutated_at_ms must be non-negative")
        _require_non_negative_decimal(self.cash_before_usdt, "cash_before_usdt")
        _require_non_negative_decimal(self.cash_after_usdt, "cash_after_usdt")
        for position in (*self.positions_before, *self.positions_after):
            if not isinstance(position, PaperPosition):
                raise TypeError("mutation positions must be PaperPosition")
            _require_non_negative_decimal(position.quantity, "position quantity")
        if normalize_positions(self.positions_before) != self.positions_before:
            raise ValueError("positions_before must be normalized")
        if normalize_positions(self.positions_after) != self.positions_after:
            raise ValueError("positions_after must be normalized")
        if self.schema_version != PAPER_FUND_SCHEMA_VERSION:
            raise ValueError("unexpected paper fund schema version")
        if self.record_identity != compute_position_cash_mutation_identity(
            fund_identity=self.fund_identity,
            source_identity=self.source_identity,
            mutated_at_ms=self.mutated_at_ms,
            cash_before_usdt=self.cash_before_usdt,
            cash_after_usdt=self.cash_after_usdt,
            positions_before=self.positions_before,
            positions_after=self.positions_after,
            schema_version=self.schema_version,
        ):
            raise ValueError("position/cash mutation identity mismatch")


@dataclass(frozen=True, slots=True)
class NavSnapshotRecord:
    """Immutable NAV snapshot for reconstructable paper-fund state."""

    record_identity: str
    fund_identity: str
    snapshot_at_ms: int
    cash_usdt: Decimal
    positions: tuple[PaperPosition, ...]
    mark_prices: tuple[tuple[PaperSymbol, Decimal], ...]
    nav_usdt: Decimal
    benchmark_ids: tuple[BenchmarkId, ...]
    schema_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "nav snapshot identity")
        _require_sha256(self.fund_identity, "fund identity")
        if self.snapshot_at_ms < 0:
            raise ValueError("snapshot_at_ms must be non-negative")
        _require_non_negative_decimal(self.cash_usdt, "cash_usdt")
        _require_non_negative_decimal(self.nav_usdt, "nav_usdt")
        if normalize_positions(self.positions) != self.positions:
            raise ValueError("positions must be normalized")
        seen: set[PaperSymbol] = set()
        for symbol, price in self.mark_prices:
            if symbol in seen:
                raise ValueError("duplicate mark price symbol")
            seen.add(symbol)
            if symbol not in PERMITTED_SYMBOLS:
                raise ValueError("mark price symbol is not permitted")
            _require_non_negative_decimal(price, "mark price")
            if price <= Decimal(0):
                raise ValueError("mark price must be positive")
        mark_price_by_symbol = dict(self.mark_prices)
        missing_mark_symbols = {
            position.symbol
            for position in self.positions
            if position.symbol not in mark_price_by_symbol
        }
        if missing_mark_symbols:
            raise ValueError("every held position requires a mark price")
        expected_nav_usdt = self.cash_usdt + sum(
            (
                position.quantity * mark_price_by_symbol[position.symbol]
                for position in self.positions
            ),
            start=Decimal(0),
        )
        if self.nav_usdt != expected_nav_usdt:
            raise ValueError(
                "nav_usdt must equal cash plus marked position value"
            )

        expected_benchmarks = tuple(
            sorted(BENCHMARK_IDS, key=lambda item: item.value)
        )
        if self.benchmark_ids != expected_benchmarks:
            raise ValueError("benchmark ids must match the v1 contract set")
        if self.schema_version != PAPER_FUND_SCHEMA_VERSION:
            raise ValueError("unexpected paper fund schema version")
        if self.record_identity != compute_nav_snapshot_identity(
            fund_identity=self.fund_identity,
            snapshot_at_ms=self.snapshot_at_ms,
            cash_usdt=self.cash_usdt,
            positions=self.positions,
            mark_prices=self.mark_prices,
            nav_usdt=self.nav_usdt,
            benchmark_ids=self.benchmark_ids,
            schema_version=self.schema_version,
        ):
            raise ValueError("nav snapshot identity mismatch")


def compute_fund_creation_identity(
    *,
    created_at_ms: int,
    initial_cash_usdt: Decimal,
    real_capital: int,
    positions: tuple[PaperPosition, ...],
    schema_version: str,
    execution_policy_version: str,
    risk_policy_version: str,
    permitted_symbols: tuple[PaperSymbol, ...],
    benchmark_ids: tuple[BenchmarkId, ...],
) -> str:
    return canonical_sha256(
        {
            "benchmark_ids": [item.value for item in benchmark_ids],
            "created_at_ms": created_at_ms,
            "execution_policy_version": execution_policy_version,
            "initial_cash_usdt": initial_cash_usdt,
            "permitted_symbols": [item.value for item in permitted_symbols],
            "positions": _positions_payload(positions),
            "real_capital": real_capital,
            "risk_policy_version": risk_policy_version,
            "schema_version": schema_version,
        }
    )


def compute_decision_intent_identity(
    *,
    fund_identity: str,
    decided_at_ms: int,
    action: PaperAction,
    symbol: PaperSymbol | None,
    quantity: Decimal | None,
    reference_price: Decimal | None,
    reason: str,
    invalidation_context: str,
    schema_version: str,
    risk_policy_version: str,
) -> str:
    return canonical_sha256(
        {
            "action": action.value,
            "decided_at_ms": decided_at_ms,
            "fund_identity": fund_identity,
            "invalidation_context": invalidation_context,
            "quantity": quantity,
            "reason": reason,
            "reference_price": reference_price,
            "risk_policy_version": risk_policy_version,
            "schema_version": schema_version,
            "symbol": None if symbol is None else symbol.value,
        }
    )


def compute_simulated_fill_identity(
    *,
    fund_identity: str,
    decision_identity: str,
    filled_at_ms: int,
    action: PaperAction,
    symbol: PaperSymbol,
    quantity: Decimal,
    reference_price: Decimal,
    simulated_fill_price: Decimal,
    costs: ExecutionCostAssumptions,
    venue_reference: str,
    schema_version: str,
) -> str:
    return canonical_sha256(
        {
            "action": action.value,
            "costs": {
                "execution_policy_version": costs.execution_policy_version,
                "fee_usdt": costs.fee_usdt,
                "partial_fills_supported": costs.partial_fills_supported,
                "slippage_usdt": costs.slippage_usdt,
                "spread_usdt": costs.spread_usdt,
            },
            "decision_identity": decision_identity,
            "filled_at_ms": filled_at_ms,
            "fund_identity": fund_identity,
            "quantity": quantity,
            "reference_price": reference_price,
            "schema_version": schema_version,
            "simulated_fill_price": simulated_fill_price,
            "symbol": symbol.value,
            "venue_reference": venue_reference,
        }
    )


def compute_position_cash_mutation_identity(
    *,
    fund_identity: str,
    source_identity: str,
    mutated_at_ms: int,
    cash_before_usdt: Decimal,
    cash_after_usdt: Decimal,
    positions_before: tuple[PaperPosition, ...],
    positions_after: tuple[PaperPosition, ...],
    schema_version: str,
) -> str:
    return canonical_sha256(
        {
            "cash_after_usdt": cash_after_usdt,
            "cash_before_usdt": cash_before_usdt,
            "fund_identity": fund_identity,
            "mutated_at_ms": mutated_at_ms,
            "positions_after": _positions_payload(positions_after),
            "positions_before": _positions_payload(positions_before),
            "schema_version": schema_version,
            "source_identity": source_identity,
        }
    )


def compute_nav_snapshot_identity(
    *,
    fund_identity: str,
    snapshot_at_ms: int,
    cash_usdt: Decimal,
    positions: tuple[PaperPosition, ...],
    mark_prices: tuple[tuple[PaperSymbol, Decimal], ...],
    nav_usdt: Decimal,
    benchmark_ids: tuple[BenchmarkId, ...],
    schema_version: str,
) -> str:
    return canonical_sha256(
        {
            "benchmark_ids": [item.value for item in benchmark_ids],
            "cash_usdt": cash_usdt,
            "fund_identity": fund_identity,
            "mark_prices": [
                {"price": price, "symbol": symbol.value}
                for symbol, price in mark_prices
            ],
            "nav_usdt": nav_usdt,
            "positions": _positions_payload(positions),
            "schema_version": schema_version,
            "snapshot_at_ms": snapshot_at_ms,
        }
    )


def build_fund_creation(*, created_at_ms: int) -> FundCreationRecord:
    """Create the initial virtual fund at exactly 100.00 USDT, zero positions."""
    permitted = tuple(sorted(PERMITTED_SYMBOLS, key=lambda item: item.value))
    benchmarks = tuple(sorted(BENCHMARK_IDS, key=lambda item: item.value))
    identity = compute_fund_creation_identity(
        created_at_ms=created_at_ms,
        initial_cash_usdt=INITIAL_CASH_USDT,
        real_capital=REAL_CAPITAL,
        positions=(),
        schema_version=PAPER_FUND_SCHEMA_VERSION,
        execution_policy_version=PAPER_EXECUTION_POLICY_VERSION,
        risk_policy_version=PAPER_RISK_POLICY_VERSION,
        permitted_symbols=permitted,
        benchmark_ids=benchmarks,
    )
    return FundCreationRecord(
        record_identity=identity,
        created_at_ms=created_at_ms,
        initial_cash_usdt=INITIAL_CASH_USDT,
        real_capital=REAL_CAPITAL,
        positions=(),
        schema_version=PAPER_FUND_SCHEMA_VERSION,
        execution_policy_version=PAPER_EXECUTION_POLICY_VERSION,
        risk_policy_version=PAPER_RISK_POLICY_VERSION,
        permitted_symbols=permitted,
        benchmark_ids=benchmarks,
    )


def build_decision_intent(
    *,
    fund_identity: str,
    decided_at_ms: int,
    action: PaperAction,
    reason: str,
    invalidation_context: str,
    symbol: PaperSymbol | None = None,
    quantity: Decimal | None = None,
    reference_price: Decimal | None = None,
) -> DecisionIntentRecord:
    identity = compute_decision_intent_identity(
        fund_identity=fund_identity,
        decided_at_ms=decided_at_ms,
        action=action,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        reason=reason,
        invalidation_context=invalidation_context,
        schema_version=PAPER_FUND_SCHEMA_VERSION,
        risk_policy_version=PAPER_RISK_POLICY_VERSION,
    )
    return DecisionIntentRecord(
        record_identity=identity,
        fund_identity=fund_identity,
        decided_at_ms=decided_at_ms,
        action=action,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        reason=reason,
        invalidation_context=invalidation_context,
        schema_version=PAPER_FUND_SCHEMA_VERSION,
        risk_policy_version=PAPER_RISK_POLICY_VERSION,
    )


def build_simulated_fill(
    *,
    fund_identity: str,
    decision_identity: str,
    filled_at_ms: int,
    action: PaperAction,
    symbol: PaperSymbol,
    quantity: Decimal,
    reference_price: Decimal,
    simulated_fill_price: Decimal,
    costs: ExecutionCostAssumptions,
    venue_reference: str,
) -> SimulatedFillRecord:
    identity = compute_simulated_fill_identity(
        fund_identity=fund_identity,
        decision_identity=decision_identity,
        filled_at_ms=filled_at_ms,
        action=action,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        simulated_fill_price=simulated_fill_price,
        costs=costs,
        venue_reference=venue_reference,
        schema_version=PAPER_FUND_SCHEMA_VERSION,
    )
    return SimulatedFillRecord(
        record_identity=identity,
        fund_identity=fund_identity,
        decision_identity=decision_identity,
        filled_at_ms=filled_at_ms,
        action=action,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        simulated_fill_price=simulated_fill_price,
        costs=costs,
        venue_reference=venue_reference,
        schema_version=PAPER_FUND_SCHEMA_VERSION,
    )


def build_position_cash_mutation(
    *,
    fund_identity: str,
    source_identity: str,
    mutated_at_ms: int,
    cash_before_usdt: Decimal,
    cash_after_usdt: Decimal,
    positions_before: Mapping[PaperSymbol, Decimal] | tuple[PaperPosition, ...],
    positions_after: Mapping[PaperSymbol, Decimal] | tuple[PaperPosition, ...],
) -> PositionCashMutationRecord:
    before = normalize_positions(positions_before)
    after = normalize_positions(positions_after)
    identity = compute_position_cash_mutation_identity(
        fund_identity=fund_identity,
        source_identity=source_identity,
        mutated_at_ms=mutated_at_ms,
        cash_before_usdt=cash_before_usdt,
        cash_after_usdt=cash_after_usdt,
        positions_before=before,
        positions_after=after,
        schema_version=PAPER_FUND_SCHEMA_VERSION,
    )
    return PositionCashMutationRecord(
        record_identity=identity,
        fund_identity=fund_identity,
        source_identity=source_identity,
        mutated_at_ms=mutated_at_ms,
        cash_before_usdt=cash_before_usdt,
        cash_after_usdt=cash_after_usdt,
        positions_before=before,
        positions_after=after,
        schema_version=PAPER_FUND_SCHEMA_VERSION,
    )


def build_nav_snapshot(
    *,
    fund_identity: str,
    snapshot_at_ms: int,
    cash_usdt: Decimal,
    positions: Mapping[PaperSymbol, Decimal] | tuple[PaperPosition, ...],
    mark_prices: Mapping[PaperSymbol, Decimal],
    nav_usdt: Decimal,
) -> NavSnapshotRecord:
    normalized = normalize_positions(positions)
    marks = tuple(
        (symbol, mark_prices[symbol])
        for symbol in sorted(mark_prices, key=lambda item: item.value)
    )
    benchmarks = tuple(sorted(BENCHMARK_IDS, key=lambda item: item.value))
    identity = compute_nav_snapshot_identity(
        fund_identity=fund_identity,
        snapshot_at_ms=snapshot_at_ms,
        cash_usdt=cash_usdt,
        positions=normalized,
        mark_prices=marks,
        nav_usdt=nav_usdt,
        benchmark_ids=benchmarks,
        schema_version=PAPER_FUND_SCHEMA_VERSION,
    )
    return NavSnapshotRecord(
        record_identity=identity,
        fund_identity=fund_identity,
        snapshot_at_ms=snapshot_at_ms,
        cash_usdt=cash_usdt,
        positions=normalized,
        mark_prices=marks,
        nav_usdt=nav_usdt,
        benchmark_ids=benchmarks,
        schema_version=PAPER_FUND_SCHEMA_VERSION,
    )


def initial_account_state() -> tuple[Decimal, tuple[PaperPosition, ...]]:
    """Exact starting state: 100.00 USDT cash, zero positions, REAL_CAPITAL=0."""
    if REAL_CAPITAL != 0:
        raise RuntimeError("REAL_CAPITAL invariant violated")
    return INITIAL_CASH_USDT, ()
