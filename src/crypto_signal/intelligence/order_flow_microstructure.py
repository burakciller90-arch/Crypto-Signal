from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookSnapshot,
    PublicTradeObservation,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256

ORDER_FLOW_MICROSTRUCTURE_ENGINE_VERSION = "order-flow-microstructure-v1/1"
ORDER_FLOW_MICROSTRUCTURE_FREEZE_SCHEMA_VERSION = (
    "order-flow-microstructure-freeze-v1/1"
)
_BPS = Decimal(10_000)


class BookPressureState(StrEnum):
    BID_HEAVY = "bid_heavy"
    ASK_HEAVY = "ask_heavy"
    BALANCED = "balanced"
    UNAVAILABLE = "unavailable"


class TakerFlowState(StrEnum):
    BUY_DOMINANT = "buy_dominant"
    SELL_DOMINANT = "sell_dominant"
    BALANCED = "balanced"
    UNAVAILABLE = "unavailable"


class OrderFlowMicrostructureLabel(StrEnum):
    BUY_PRESSURE = "buy_pressure"
    SELL_PRESSURE = "sell_pressure"
    BALANCED = "balanced"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class OrderFlowMicrostructureConfig:
    depth_levels: int = 10
    minimum_trades: int = 5
    trade_lookback_ms: int = 60_000
    max_book_age_ms: int = 30_000
    max_trade_age_ms: int = 30_000
    imbalance_threshold: Decimal = Decimal("0.15")

    def __post_init__(self) -> None:
        if self.depth_levels <= 0:
            raise ValueError("depth_levels must be positive")
        if self.minimum_trades <= 0:
            raise ValueError("minimum_trades must be positive")
        if self.trade_lookback_ms <= 0:
            raise ValueError("trade_lookback_ms must be positive")
        if self.max_book_age_ms <= 0:
            raise ValueError("max_book_age_ms must be positive")
        if not 0 < self.max_trade_age_ms <= self.trade_lookback_ms:
            raise ValueError(
                "max_trade_age_ms must be positive and not exceed trade lookback"
            )
        if (
            self.imbalance_threshold.is_nan()
            or self.imbalance_threshold.is_infinite()
            or not Decimal(0) < self.imbalance_threshold < Decimal(1)
        ):
            raise ValueError("imbalance_threshold must be finite inside (0,1)")


DEFAULT_ORDER_FLOW_MICROSTRUCTURE_CONFIG = OrderFlowMicrostructureConfig()


@dataclass(frozen=True, slots=True)
class OrderFlowMicrostructureMetrics:
    best_bid_price: Decimal
    best_ask_price: Decimal
    mid_price: Decimal
    spread_bps: Decimal
    bid_depth_notional: Decimal
    ask_depth_notional: Decimal
    book_imbalance: Decimal
    taker_buy_notional: Decimal
    taker_sell_notional: Decimal
    taker_flow_imbalance: Decimal
    eligible_trade_count: int
    excluded_trade_count: int
    depth_levels: int

    def __post_init__(self) -> None:
        for label, value in (
            ("best_bid_price", self.best_bid_price),
            ("best_ask_price", self.best_ask_price),
            ("mid_price", self.mid_price),
            ("spread_bps", self.spread_bps),
            ("bid_depth_notional", self.bid_depth_notional),
            ("ask_depth_notional", self.ask_depth_notional),
            ("taker_buy_notional", self.taker_buy_notional),
            ("taker_sell_notional", self.taker_sell_notional),
        ):
            if value.is_nan() or value.is_infinite() or value < Decimal(0):
                raise ValueError(f"{label} must be finite and non-negative")
        if self.best_bid_price <= Decimal(0) or self.best_ask_price <= Decimal(0):
            raise ValueError("best bid/ask must be positive")
        if self.best_bid_price >= self.best_ask_price:
            raise ValueError("microstructure best bid/ask must not be crossed")
        if self.mid_price != (self.best_bid_price + self.best_ask_price) / Decimal(2):
            raise ValueError("microstructure mid price mismatch")
        if self.spread_bps != (
            (self.best_ask_price - self.best_bid_price) / self.mid_price * _BPS
        ):
            raise ValueError("microstructure spread bps mismatch")
        for label, value in (
            ("book_imbalance", self.book_imbalance),
            ("taker_flow_imbalance", self.taker_flow_imbalance),
        ):
            if (
                value.is_nan()
                or value.is_infinite()
                or value < Decimal(-1)
                or value > Decimal(1)
            ):
                raise ValueError(f"{label} must be finite inside [-1,1]")
        if self.eligible_trade_count <= 0:
            raise ValueError("microstructure metrics require eligible trades")
        if self.excluded_trade_count < 0:
            raise ValueError("excluded trade count cannot be negative")
        if self.depth_levels <= 0:
            raise ValueError("microstructure metrics require depth levels")


@dataclass(frozen=True, slots=True)
class OrderFlowMicrostructureAnalysis:
    evidence_identity: str
    engine_version: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    as_of_ms: int
    observed_at_ms: int
    book_event_at_ms: int | None
    book_sequence: int | None
    latest_trade_event_at_ms: int | None
    trade_window_start_ms: int
    consumed_trade_count: int
    excluded_trade_count: int
    label: OrderFlowMicrostructureLabel
    book_pressure: BookPressureState
    taker_flow: TakerFlowState
    metrics: OrderFlowMicrostructureMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "microstructure evidence identity")
        if self.engine_version != ORDER_FLOW_MICROSTRUCTURE_ENGINE_VERSION:
            raise ValueError("unsupported microstructure engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("microstructure analysis symbol must be uppercase")
        if min(self.as_of_ms, self.observed_at_ms, self.trade_window_start_ms) < 0:
            raise ValueError("microstructure analysis timestamps must be non-negative")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("microstructure analysis cannot observe future evidence")
        if self.trade_window_start_ms > self.as_of_ms:
            raise ValueError("microstructure trade window starts after as-of")
        if self.book_event_at_ms is not None and self.book_event_at_ms > self.as_of_ms:
            raise ValueError("microstructure book event is from the future")
        if (
            self.latest_trade_event_at_ms is not None
            and self.latest_trade_event_at_ms > self.as_of_ms
        ):
            raise ValueError("microstructure trade event is from the future")
        if self.consumed_trade_count < 0 or self.excluded_trade_count < 0:
            raise ValueError("microstructure trade counts cannot be negative")
        if self.excluded_trade_count > self.consumed_trade_count:
            raise ValueError("excluded trades cannot exceed consumed trades")
        if self.label is OrderFlowMicrostructureLabel.UNRESOLVED:
            if self.metrics is not None:
                raise ValueError("unresolved microstructure cannot carry metrics")
            if self.book_pressure is not BookPressureState.UNAVAILABLE:
                raise ValueError("unresolved microstructure cannot carry book state")
            if self.taker_flow is not TakerFlowState.UNAVAILABLE:
                raise ValueError("unresolved microstructure cannot carry flow state")
            if not self.uncertainty_flags:
                raise ValueError("unresolved microstructure requires uncertainty")
        elif self.metrics is None:
            raise ValueError("resolved microstructure requires metrics")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("microstructure evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class OrderFlowMicrostructureEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: OrderFlowMicrostructureAnalysis
    orderbook: OrderBookSnapshot | None
    trades: tuple[PublicTradeObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "microstructure freeze identity")
        if self.schema_version != ORDER_FLOW_MICROSTRUCTURE_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported microstructure freeze schema")
        if self.orderbook is not None:
            _require_same_context(
                self.analysis.exchange,
                self.analysis.market_type,
                self.analysis.symbol,
                self.orderbook.exchange,
                self.orderbook.market_type,
                self.orderbook.symbol,
            )
        for trade in self.trades:
            _require_same_context(
                self.analysis.exchange,
                self.analysis.market_type,
                self.analysis.symbol,
                trade.exchange,
                trade.market_type,
                trade.symbol,
            )
        if self.analysis.consumed_trade_count != len(self.trades):
            raise ValueError("microstructure freeze trade count mismatch")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("microstructure freeze identity mismatch")


def analyze_order_flow_microstructure(
    orderbooks: Sequence[OrderBookSnapshot],
    trades: Sequence[PublicTradeObservation],
    *,
    as_of_ms: int,
    config: OrderFlowMicrostructureConfig = DEFAULT_ORDER_FLOW_MICROSTRUCTURE_CONFIG,
) -> OrderFlowMicrostructureAnalysis:
    freeze = build_order_flow_microstructure_evidence_freeze(
        orderbooks,
        trades,
        as_of_ms=as_of_ms,
        config=config,
    )
    return freeze.analysis


def build_order_flow_microstructure_evidence_freeze(
    orderbooks: Sequence[OrderBookSnapshot],
    trades: Sequence[PublicTradeObservation],
    *,
    as_of_ms: int,
    config: OrderFlowMicrostructureConfig = DEFAULT_ORDER_FLOW_MICROSTRUCTURE_CONFIG,
) -> OrderFlowMicrostructureEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("microstructure as_of_ms must be non-negative")
    context = _context(orderbooks, trades)
    exchange, market_type, symbol = context

    books_sorted = tuple(
        sorted(
            orderbooks,
            key=lambda item: (
                item.event_at_ms,
                item.sequence,
                item.update_id,
                item.snapshot_identity,
            ),
        )
    )
    trades_sorted = tuple(
        sorted(
            trades,
            key=lambda item: (
                item.event_at_ms,
                item.sequence,
                item.exec_id,
                item.trade_identity,
            ),
        )
    )
    _reject_duplicate_identities(books_sorted, trades_sorted)

    safe_books = tuple(
        item
        for item in books_sorted
        if item.event_at_ms <= as_of_ms
        and item.source_timestamp_ms <= as_of_ms
        and item.response_time_ms <= as_of_ms
        and item.ingested_at_ms <= as_of_ms
    )
    latest_book = safe_books[-1] if safe_books else None

    window_start = max(0, as_of_ms - config.trade_lookback_ms)
    safe_window_trades = tuple(
        item
        for item in trades_sorted
        if window_start <= item.event_at_ms <= as_of_ms
        and item.source_timestamp_ms <= as_of_ms
        and item.ingested_at_ms <= as_of_ms
    )

    analysis = _analyze_selected(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        latest_book=latest_book,
        trades=safe_window_trades,
        as_of_ms=as_of_ms,
        trade_window_start_ms=window_start,
        config=config,
    )
    payload = {
        "analysis_identity": analysis.evidence_identity,
        "orderbook_identity": (
            None if latest_book is None else latest_book.snapshot_identity
        ),
        "schema_version": ORDER_FLOW_MICROSTRUCTURE_FREEZE_SCHEMA_VERSION,
        "trade_identities": [item.trade_identity for item in safe_window_trades],
    }
    return OrderFlowMicrostructureEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=ORDER_FLOW_MICROSTRUCTURE_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        orderbook=latest_book,
        trades=safe_window_trades,
    )


def _analyze_selected(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    latest_book: OrderBookSnapshot | None,
    trades: tuple[PublicTradeObservation, ...],
    as_of_ms: int,
    trade_window_start_ms: int,
    config: OrderFlowMicrostructureConfig,
) -> OrderFlowMicrostructureAnalysis:
    observed_at_ms = max(
        (
            *(
                (latest_book.ingested_at_ms,)
                if latest_book is not None
                else ()
            ),
            *(item.ingested_at_ms for item in trades),
            0,
        )
    )
    flags: list[str] = []

    if latest_book is None:
        flags.append("orderbook_unavailable_at_as_of")
        return _unresolved(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            as_of_ms=as_of_ms,
            observed_at_ms=observed_at_ms,
            latest_book=None,
            trades=trades,
            trade_window_start_ms=trade_window_start_ms,
            flags=tuple(flags),
        )

    if as_of_ms - latest_book.event_at_ms > config.max_book_age_ms:
        flags.append("stale_orderbook")
    if len(latest_book.bids) < config.depth_levels or len(latest_book.asks) < (
        config.depth_levels
    ):
        flags.append("insufficient_orderbook_depth")

    eligible = tuple(item for item in trades if item.book_eligible)
    excluded_count = len(trades) - len(eligible)
    if excluded_count:
        flags.append("excluded_block_or_rpi_trades")
    if len(eligible) < config.minimum_trades:
        flags.append("insufficient_public_trades")
    latest_trade_event_at_ms = (
        None if not eligible else max(item.event_at_ms for item in eligible)
    )
    if (
        latest_trade_event_at_ms is not None
        and as_of_ms - latest_trade_event_at_ms > config.max_trade_age_ms
    ):
        flags.append("stale_public_trades")

    blocking = {
        "stale_orderbook",
        "insufficient_orderbook_depth",
        "insufficient_public_trades",
        "stale_public_trades",
    }
    if any(flag in blocking for flag in flags):
        return _unresolved(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            as_of_ms=as_of_ms,
            observed_at_ms=observed_at_ms,
            latest_book=latest_book,
            trades=trades,
            trade_window_start_ms=trade_window_start_ms,
            flags=tuple(flags),
        )

    metrics = _derive_metrics(
        latest_book=latest_book,
        eligible_trades=eligible,
        excluded_trade_count=excluded_count,
        depth_levels=config.depth_levels,
    )
    book_pressure = _book_pressure(metrics.book_imbalance, config=config)
    taker_flow = _taker_flow(metrics.taker_flow_imbalance, config=config)
    if (
        book_pressure is BookPressureState.BID_HEAVY
        and taker_flow is TakerFlowState.BUY_DOMINANT
    ):
        label = OrderFlowMicrostructureLabel.BUY_PRESSURE
    elif (
        book_pressure is BookPressureState.ASK_HEAVY
        and taker_flow is TakerFlowState.SELL_DOMINANT
    ):
        label = OrderFlowMicrostructureLabel.SELL_PRESSURE
    elif (
        book_pressure is BookPressureState.BALANCED
        and taker_flow is TakerFlowState.BALANCED
    ):
        label = OrderFlowMicrostructureLabel.BALANCED
    else:
        label = OrderFlowMicrostructureLabel.MIXED
        flags.append("book_flow_disagreement_or_partial_alignment")

    payload = {
        "as_of_ms": as_of_ms,
        "book_event_at_ms": latest_book.event_at_ms,
        "book_pressure": book_pressure,
        "book_sequence": latest_book.sequence,
        "consumed_trade_count": len(trades),
        "engine_version": ORDER_FLOW_MICROSTRUCTURE_ENGINE_VERSION,
        "exchange": exchange,
        "excluded_trade_count": excluded_count,
        "label": label,
        "latest_trade_event_at_ms": latest_trade_event_at_ms,
        "market_type": market_type,
        "metrics": _metrics_payload(metrics),
        "observed_at_ms": observed_at_ms,
        "symbol": symbol,
        "taker_flow": taker_flow,
        "trade_window_start_ms": trade_window_start_ms,
        "uncertainty_flags": tuple(flags),
    }
    return OrderFlowMicrostructureAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=ORDER_FLOW_MICROSTRUCTURE_ENGINE_VERSION,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        as_of_ms=as_of_ms,
        observed_at_ms=observed_at_ms,
        book_event_at_ms=latest_book.event_at_ms,
        book_sequence=latest_book.sequence,
        latest_trade_event_at_ms=latest_trade_event_at_ms,
        trade_window_start_ms=trade_window_start_ms,
        consumed_trade_count=len(trades),
        excluded_trade_count=excluded_count,
        label=label,
        book_pressure=book_pressure,
        taker_flow=taker_flow,
        metrics=metrics,
        uncertainty_flags=tuple(flags),
    )


def _unresolved(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    as_of_ms: int,
    observed_at_ms: int,
    latest_book: OrderBookSnapshot | None,
    trades: tuple[PublicTradeObservation, ...],
    trade_window_start_ms: int,
    flags: tuple[str, ...],
) -> OrderFlowMicrostructureAnalysis:
    latest_trade_event_at_ms = (
        None if not trades else max(item.event_at_ms for item in trades)
    )
    payload = {
        "as_of_ms": as_of_ms,
        "book_event_at_ms": (
            None if latest_book is None else latest_book.event_at_ms
        ),
        "book_pressure": BookPressureState.UNAVAILABLE,
        "book_sequence": None if latest_book is None else latest_book.sequence,
        "consumed_trade_count": len(trades),
        "engine_version": ORDER_FLOW_MICROSTRUCTURE_ENGINE_VERSION,
        "exchange": exchange,
        "excluded_trade_count": sum(not item.book_eligible for item in trades),
        "label": OrderFlowMicrostructureLabel.UNRESOLVED,
        "latest_trade_event_at_ms": latest_trade_event_at_ms,
        "market_type": market_type,
        "metrics": None,
        "observed_at_ms": observed_at_ms,
        "symbol": symbol,
        "taker_flow": TakerFlowState.UNAVAILABLE,
        "trade_window_start_ms": trade_window_start_ms,
        "uncertainty_flags": flags,
    }
    return OrderFlowMicrostructureAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=ORDER_FLOW_MICROSTRUCTURE_ENGINE_VERSION,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        as_of_ms=as_of_ms,
        observed_at_ms=observed_at_ms,
        book_event_at_ms=(
            None if latest_book is None else latest_book.event_at_ms
        ),
        book_sequence=None if latest_book is None else latest_book.sequence,
        latest_trade_event_at_ms=latest_trade_event_at_ms,
        trade_window_start_ms=trade_window_start_ms,
        consumed_trade_count=len(trades),
        excluded_trade_count=sum(not item.book_eligible for item in trades),
        label=OrderFlowMicrostructureLabel.UNRESOLVED,
        book_pressure=BookPressureState.UNAVAILABLE,
        taker_flow=TakerFlowState.UNAVAILABLE,
        metrics=None,
        uncertainty_flags=flags,
    )


def _derive_metrics(
    *,
    latest_book: OrderBookSnapshot,
    eligible_trades: tuple[PublicTradeObservation, ...],
    excluded_trade_count: int,
    depth_levels: int,
) -> OrderFlowMicrostructureMetrics:
    bids = latest_book.bids[:depth_levels]
    asks = latest_book.asks[:depth_levels]
    best_bid = bids[0].price
    best_ask = asks[0].price
    mid = (best_bid + best_ask) / Decimal(2)
    spread_bps = (best_ask - best_bid) / mid * _BPS
    bid_depth = sum((item.notional for item in bids), start=Decimal(0))
    ask_depth = sum((item.notional for item in asks), start=Decimal(0))
    total_depth = bid_depth + ask_depth
    if total_depth <= Decimal(0):
        raise ValueError("microstructure depth notional must be positive")
    book_imbalance = (bid_depth - ask_depth) / total_depth

    buy_notional = sum(
        (
            item.notional
            for item in eligible_trades
            if item.aggressor_side is AggressorSide.BUY
        ),
        start=Decimal(0),
    )
    sell_notional = sum(
        (
            item.notional
            for item in eligible_trades
            if item.aggressor_side is AggressorSide.SELL
        ),
        start=Decimal(0),
    )
    total_flow = buy_notional + sell_notional
    if total_flow <= Decimal(0):
        raise ValueError("microstructure trade notional must be positive")
    taker_flow_imbalance = (buy_notional - sell_notional) / total_flow

    return OrderFlowMicrostructureMetrics(
        best_bid_price=best_bid,
        best_ask_price=best_ask,
        mid_price=mid,
        spread_bps=spread_bps,
        bid_depth_notional=bid_depth,
        ask_depth_notional=ask_depth,
        book_imbalance=book_imbalance,
        taker_buy_notional=buy_notional,
        taker_sell_notional=sell_notional,
        taker_flow_imbalance=taker_flow_imbalance,
        eligible_trade_count=len(eligible_trades),
        excluded_trade_count=excluded_trade_count,
        depth_levels=depth_levels,
    )


def _book_pressure(
    imbalance: Decimal,
    *,
    config: OrderFlowMicrostructureConfig,
) -> BookPressureState:
    if imbalance >= config.imbalance_threshold:
        return BookPressureState.BID_HEAVY
    if imbalance <= -config.imbalance_threshold:
        return BookPressureState.ASK_HEAVY
    return BookPressureState.BALANCED


def _taker_flow(
    imbalance: Decimal,
    *,
    config: OrderFlowMicrostructureConfig,
) -> TakerFlowState:
    if imbalance >= config.imbalance_threshold:
        return TakerFlowState.BUY_DOMINANT
    if imbalance <= -config.imbalance_threshold:
        return TakerFlowState.SELL_DOMINANT
    return TakerFlowState.BALANCED


def _context(
    orderbooks: Sequence[OrderBookSnapshot],
    trades: Sequence[PublicTradeObservation],
) -> tuple[Exchange, MarketType, str]:
    if not orderbooks and not trades:
        raise ValueError("microstructure analysis requires source evidence")
    first = orderbooks[0] if orderbooks else trades[0]
    expected = (first.exchange, first.market_type, first.symbol)
    for item in (*orderbooks, *trades):
        _require_same_context(
            *expected,
            item.exchange,
            item.market_type,
            item.symbol,
        )
    return expected


def _reject_duplicate_identities(
    orderbooks: tuple[OrderBookSnapshot, ...],
    trades: tuple[PublicTradeObservation, ...],
) -> None:
    book_ids = [item.snapshot_identity for item in orderbooks]
    trade_ids = [item.trade_identity for item in trades]
    if len(book_ids) != len(set(book_ids)):
        raise ValueError("duplicate orderbook snapshot identity")
    if len(trade_ids) != len(set(trade_ids)):
        raise ValueError("duplicate public trade identity")


def _require_same_context(
    expected_exchange: Exchange,
    expected_market_type: MarketType,
    expected_symbol: str,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
) -> None:
    if (exchange, market_type, symbol) != (
        expected_exchange,
        expected_market_type,
        expected_symbol,
    ):
        raise ValueError("microstructure context mismatch")


def _metrics_payload(
    metrics: OrderFlowMicrostructureMetrics,
) -> dict[str, object]:
    return {
        "ask_depth_notional": metrics.ask_depth_notional,
        "best_ask_price": metrics.best_ask_price,
        "best_bid_price": metrics.best_bid_price,
        "bid_depth_notional": metrics.bid_depth_notional,
        "book_imbalance": metrics.book_imbalance,
        "depth_levels": metrics.depth_levels,
        "eligible_trade_count": metrics.eligible_trade_count,
        "excluded_trade_count": metrics.excluded_trade_count,
        "mid_price": metrics.mid_price,
        "spread_bps": metrics.spread_bps,
        "taker_buy_notional": metrics.taker_buy_notional,
        "taker_flow_imbalance": metrics.taker_flow_imbalance,
        "taker_sell_notional": metrics.taker_sell_notional,
    }


def _analysis_payload(
    analysis: OrderFlowMicrostructureAnalysis,
) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "book_event_at_ms": analysis.book_event_at_ms,
        "book_pressure": analysis.book_pressure,
        "book_sequence": analysis.book_sequence,
        "consumed_trade_count": analysis.consumed_trade_count,
        "engine_version": analysis.engine_version,
        "exchange": analysis.exchange,
        "excluded_trade_count": analysis.excluded_trade_count,
        "label": analysis.label,
        "latest_trade_event_at_ms": analysis.latest_trade_event_at_ms,
        "market_type": analysis.market_type,
        "metrics": (
            None if analysis.metrics is None else _metrics_payload(analysis.metrics)
        ),
        "observed_at_ms": analysis.observed_at_ms,
        "symbol": analysis.symbol,
        "taker_flow": analysis.taker_flow,
        "trade_window_start_ms": analysis.trade_window_start_ms,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze_payload(
    freeze: OrderFlowMicrostructureEvidenceFreeze,
) -> dict[str, object]:
    return {
        "analysis_identity": freeze.analysis.evidence_identity,
        "orderbook_identity": (
            None if freeze.orderbook is None else freeze.orderbook.snapshot_identity
        ),
        "schema_version": freeze.schema_version,
        "trade_identities": [item.trade_identity for item in freeze.trades],
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
