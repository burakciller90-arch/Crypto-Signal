"""PIT-safe, bounded two-anchor price/CVD mismatch evidence.

Not classical swing-pivot divergence, absorption, a signal, or probability.
Independent closed candles and one immutable temporal public-trade freeze required.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from crypto_signal.data.microstructure import AggressorSide, PublicTradeObservation
from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.intelligence.temporal_order_flow import (
    TemporalFlowEvidenceFreeze,
    TemporalFlowQuality,
    TemporalFlowStatus,
)
from crypto_signal.ledger.serialization import canonical_sha256

ENGINE_VERSION = "m3-price-flow-mismatch-slice2/1"
FREEZE_SCHEMA_VERSION = "m3-price-flow-mismatch-freeze-v1/1"
_ZERO = Decimal(0)
_BPS = Decimal(10000)


class PriceFlowStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class PriceFlowState(StrEnum):
    BEARISH_CANDIDATE = "bearish_price_flow_mismatch_candidate"
    BULLISH_CANDIDATE = "bullish_price_flow_mismatch_candidate"
    NO_MISMATCH = "no_mismatch"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class PriceFlowConfig:
    min_anchor_gap_ms: int = 60_000
    max_candle_age_ms: int = 30_000
    max_trade_to_candle_gap_ms: int = 30_000
    max_intervening_trade_gap_ms: int = 30_000
    min_first_candle_trades: int = 2
    min_last_candle_trades: int = 2
    min_intervening_trades: int = 3
    min_price_displacement_bps: Decimal = Decimal(10)
    min_opposing_cvd_notional: Decimal = Decimal(1000)

    def __post_init__(self) -> None:
        for name, number in (
            ("min_anchor_gap_ms", self.min_anchor_gap_ms),
            ("max_candle_age_ms", self.max_candle_age_ms),
            ("max_trade_to_candle_gap_ms", self.max_trade_to_candle_gap_ms),
            ("max_intervening_trade_gap_ms", self.max_intervening_trade_gap_ms),
            ("min_first_candle_trades", self.min_first_candle_trades),
            ("min_last_candle_trades", self.min_last_candle_trades),
            ("min_intervening_trades", self.min_intervening_trades),
        ):
            if number <= 0:
                raise ValueError(f"{name} must be positive")
        for name, value in (
            ("min_price_displacement_bps", self.min_price_displacement_bps),
            ("min_opposing_cvd_notional", self.min_opposing_cvd_notional),
        ):
            _finite(value, name)
            if value <= _ZERO:
                raise ValueError(f"{name} must be positive")

    @property
    def identity(self) -> str:
        return canonical_sha256(
            {name: getattr(self, name) for name in self.__dataclass_fields__}
        )


DEFAULT_PRICE_FLOW_CONFIG = PriceFlowConfig()


@dataclass(frozen=True, slots=True)
class PriceFlowMetrics:
    first_close: Decimal
    last_close: Decimal
    price_move_bps: Decimal
    first_close_cvd_notional: Decimal
    last_close_cvd_notional: Decimal
    cvd_move_notional: Decimal
    intervening_buy_notional: Decimal
    intervening_sell_notional: Decimal
    intervening_trade_count: int
    first_candle_trade_count: int
    last_candle_trade_count: int

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, Decimal):
                _finite(value, name)
        if self.first_close <= _ZERO or self.last_close <= _ZERO:
            raise ValueError("anchor closes must be positive")
        if min(
            self.intervening_trade_count,
            self.first_candle_trade_count,
            self.last_candle_trade_count,
        ) <= 0:
            raise ValueError("measured price flow requires observed trades")
        if self.intervening_buy_notional < _ZERO or self.intervening_sell_notional < _ZERO:
            raise ValueError("intervening notional cannot be negative")
        if self.cvd_move_notional != (
            self.last_close_cvd_notional - self.first_close_cvd_notional
        ):
            raise ValueError("CVD anchor movement mismatch")
        if self.cvd_move_notional != (
            self.intervening_buy_notional - self.intervening_sell_notional
        ):
            raise ValueError("intervening flow mismatch")
        if self.price_move_bps != (
            (self.last_close - self.first_close) / self.first_close * _BPS
        ):
            raise ValueError("price displacement mismatch")


@dataclass(frozen=True, slots=True)
class PriceFlowAnalysis:
    evidence_identity: str
    engine_version: str
    config_identity: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    observed_at_ms: int
    flow_evidence_identity: str
    flow_freeze_identity: str
    first_candle_identity: str | None
    last_candle_identity: str | None
    first_anchor_close_ms: int | None
    last_anchor_close_ms: int | None
    consumed_closed_candle_count: int
    status: PriceFlowStatus
    state: PriceFlowState
    metrics: PriceFlowMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("evidence_identity", "config_identity", "flow_evidence_identity", "flow_freeze_identity"):
            _sha(getattr(self, name), name)
        if self.engine_version != ENGINE_VERSION:
            raise ValueError("unsupported price-flow engine version")
        if not self.symbol or self.symbol != self.symbol.upper() or not self.timeframe:
            raise ValueError("invalid price-flow market context")
        if not 0 <= self.observed_at_ms <= self.as_of_ms:
            raise ValueError("price-flow observed future evidence")
        if self.consumed_closed_candle_count < 0:
            raise ValueError("negative candle count")
        for name in ("first_candle_identity", "last_candle_identity"):
            val = getattr(self, name)
            if val is not None:
                _sha(val, name)
        if self.status is PriceFlowStatus.MEASURED:
            if self.state is PriceFlowState.UNAVAILABLE or self.metrics is None:
                raise ValueError("measured price-flow requires metrics")
            if (
                self.first_anchor_close_ms is None
                or self.last_anchor_close_ms is None
                or self.first_candle_identity is None
                or self.last_candle_identity is None
            ):
                raise ValueError("measured price-flow requires both anchors")
        else:
            if self.state is not PriceFlowState.UNAVAILABLE or self.metrics is not None:
                raise ValueError("unresolved price-flow cannot claim metrics")
            if not self.uncertainty_flags:
                raise ValueError("unresolved price-flow requires uncertainty")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("price-flow evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class PriceFlowEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: PriceFlowAnalysis
    flow: TemporalFlowEvidenceFreeze
    closed_candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        _sha(self.freeze_identity, "price-flow freeze")
        if self.schema_version != FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported price-flow freeze schema")
        if self.analysis.flow_freeze_identity != self.flow.freeze_identity:
            raise ValueError("underlying temporal flow freeze identity mismatch")
        if len(self.closed_candles) != self.analysis.consumed_closed_candle_count:
            raise ValueError("frozen candle count mismatch")
        for candle in self.closed_candles:
            if (
                not candle.is_closed
                or candle.exchange is not self.analysis.exchange
                or candle.market_type is not self.analysis.market_type
                or candle.symbol != self.analysis.symbol
                or candle.timeframe != self.analysis.timeframe
                or max(
                    candle.close_time_ms,
                    candle.source_timestamp_ms,
                    candle.ingested_at_ms,
                ) > self.analysis.as_of_ms
            ):
                raise ValueError("price-flow freeze contains future/mixed candle")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "candle_identities": [_candle_identity(x) for x in self.closed_candles],
                "flow_freeze_identity": self.flow.freeze_identity,
                "schema_version": FREEZE_SCHEMA_VERSION,
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("price-flow freeze identity mismatch")


def analyze_price_flow_mismatch(
    candles: Sequence[Candle],
    flow: TemporalFlowEvidenceFreeze,
    *,
    as_of_ms: int,
    config: PriceFlowConfig = DEFAULT_PRICE_FLOW_CONFIG,
) -> PriceFlowAnalysis:
    return build_price_flow_mismatch_freeze(
        candles, flow, as_of_ms=as_of_ms, config=config
    ).analysis


def build_price_flow_mismatch_freeze(
    candles: Sequence[Candle],
    flow: TemporalFlowEvidenceFreeze,
    *,
    as_of_ms: int,
    config: PriceFlowConfig = DEFAULT_PRICE_FLOW_CONFIG,
) -> PriceFlowEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("as_of_ms must be non-negative")
    if not candles:
        raise ValueError("price-flow requires at least one candle")
    if flow.analysis.as_of_ms != as_of_ms:
        raise ValueError("independent flow as-of must match price-flow as-of")

    ordered = tuple(sorted(candles, key=lambda item: (item.open_time_ms, item.close_time_ms)))
    first = ordered[0]
    ctx = (first.exchange, first.market_type, first.symbol, first.timeframe)
    expected = (
        flow.analysis.exchange,
        flow.analysis.market_type,
        flow.analysis.symbol,
    )
    if ctx[:3] != expected:
        raise ValueError("price/flow market context mismatch")
    if any(
        (item.exchange, item.market_type, item.symbol, item.timeframe) != ctx
        for item in ordered
    ):
        raise ValueError("mixed candle market context/timeframe")
    if len({item.open_time_ms for item in ordered}) != len(ordered):
        raise ValueError("duplicate candle open-time identity")

    safe = tuple(
        item
        for item in ordered
        if item.is_closed
        and item.open_time_ms >= flow.analysis.window_start_ms
        and max(
            item.close_time_ms,
            item.source_timestamp_ms,
            item.ingested_at_ms,
        ) <= as_of_ms
    )
    analysis = _analyze(
        safe,
        flow,
        as_of_ms=as_of_ms,
        config=config,
        timeframe=first.timeframe,
    )
    return PriceFlowEvidenceFreeze(
        freeze_identity=canonical_sha256(
            {
                "analysis_identity": analysis.evidence_identity,
                "candle_identities": [_candle_identity(x) for x in safe],
                "flow_freeze_identity": flow.freeze_identity,
                "schema_version": FREEZE_SCHEMA_VERSION,
            }
        ),
        schema_version=FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        flow=flow,
        closed_candles=safe,
    )


def _analyze(
    candles: tuple[Candle, ...],
    flow: TemporalFlowEvidenceFreeze,
    *,
    as_of_ms: int,
    config: PriceFlowConfig,
    timeframe: str,
) -> PriceFlowAnalysis:
    exchange, market_type, symbol = (
        flow.analysis.exchange,
        flow.analysis.market_type,
        flow.analysis.symbol,
    )
    flags: list[str] = ["window_local_cvd_not_exchange_global"]
    if flow.analysis.status is not TemporalFlowStatus.MEASURED or (
        flow.analysis.quality is not TemporalFlowQuality.GOOD
    ):
        flags.append("temporal_trade_flow_unresolved")
    if len(candles) < 2:
        flags.append("insufficient_closed_anchor_candles")
    if any(
        right.open_time_ms - left.close_time_ms > 1
        or right.open_time_ms < left.close_time_ms
        for left, right in pairwise(candles)
    ):
        flags.append("closed_candle_gap_or_overlap")
    if candles:
        if as_of_ms - candles[-1].close_time_ms > config.max_candle_age_ms:
            flags.append("stale_latest_closed_candle")
        if (
            candles[-1].close_time_ms - candles[0].close_time_ms
            < config.min_anchor_gap_ms
        ):
            flags.append("insufficient_anchor_time_span")

    eligible: tuple[PublicTradeObservation, ...] = tuple(
        item for item in flow.trades if item.book_eligible
    )
    between: tuple[PublicTradeObservation, ...] = ()
    first_count = 0
    last_count = 0
    first_cvd = _ZERO
    last_cvd = _ZERO
    if len(candles) >= 2:
        first_candle, last_candle = candles[0], candles[-1]
        first_count = sum(
            first_candle.open_time_ms <= item.event_at_ms <= first_candle.close_time_ms
            for item in eligible
        )
        last_count = sum(
            last_candle.open_time_ms <= item.event_at_ms <= last_candle.close_time_ms
            for item in eligible
        )
        between = tuple(
            item
            for item in eligible
            if first_candle.close_time_ms < item.event_at_ms <= last_candle.close_time_ms
        )
        if first_count < config.min_first_candle_trades:
            flags.append("insufficient_first_anchor_trades")
        if last_count < config.min_last_candle_trades:
            flags.append("insufficient_last_anchor_trades")
        if len(between) < config.min_intervening_trades:
            flags.append("insufficient_intervening_trades")
        if between and (
            last_candle.close_time_ms - between[-1].event_at_ms
            > config.max_trade_to_candle_gap_ms
        ):
            flags.append("stale_last_intervening_trade")
        relevant = tuple(
            item
            for item in eligible
            if first_candle.open_time_ms <= item.event_at_ms <= last_candle.close_time_ms
        )
        if relevant and (
            relevant[0].event_at_ms - first_candle.open_time_ms
            > config.max_trade_to_candle_gap_ms
        ):
            flags.append("first_anchor_trade_coverage_gap")
        if any(
            later.event_at_ms - earlier.event_at_ms
            > config.max_intervening_trade_gap_ms
            for earlier, later in pairwise(relevant)
        ):
            flags.append("intervening_trade_gap_exceeds_limit")
        first_cvd = sum(
            (_signed_notional(item) for item in eligible if item.event_at_ms <= first_candle.close_time_ms),
            _ZERO,
        )
        last_cvd = sum(
            (_signed_notional(item) for item in eligible if item.event_at_ms <= last_candle.close_time_ms),
            _ZERO,
        )

    blocking = {
        "temporal_trade_flow_unresolved",
        "insufficient_closed_anchor_candles",
        "closed_candle_gap_or_overlap",
        "stale_latest_closed_candle",
        "insufficient_anchor_time_span",
        "insufficient_first_anchor_trades",
        "insufficient_last_anchor_trades",
        "insufficient_intervening_trades",
        "stale_last_intervening_trade",
        "first_anchor_trade_coverage_gap",
        "intervening_trade_gap_exceeds_limit",
    }

    state = PriceFlowState.UNAVAILABLE
    status = PriceFlowStatus.UNRESOLVED
    metrics: PriceFlowMetrics | None = None
    if not any(flag in blocking for flag in flags):
        first_candle, last_candle = candles[0], candles[-1]
        buy = sum(
            (item.notional for item in between if item.aggressor_side is AggressorSide.BUY),
            _ZERO,
        )
        sell = sum(
            (item.notional for item in between if item.aggressor_side is AggressorSide.SELL),
            _ZERO,
        )
        movement = (last_candle.close - first_candle.close) / first_candle.close * _BPS
        cvd_movement = last_cvd - first_cvd
        metrics = PriceFlowMetrics(
            first_close=first_candle.close,
            last_close=last_candle.close,
            price_move_bps=movement,
            first_close_cvd_notional=first_cvd,
            last_close_cvd_notional=last_cvd,
            cvd_move_notional=cvd_movement,
            intervening_buy_notional=buy,
            intervening_sell_notional=sell,
            intervening_trade_count=len(between),
            first_candle_trade_count=first_count,
            last_candle_trade_count=last_count,
        )
        state = PriceFlowState.NO_MISMATCH
        if (
            movement >= config.min_price_displacement_bps
            and cvd_movement <= -config.min_opposing_cvd_notional
        ):
            state = PriceFlowState.BEARISH_CANDIDATE
        elif (
            movement <= -config.min_price_displacement_bps
            and cvd_movement >= config.min_opposing_cvd_notional
        ):
            state = PriceFlowState.BULLISH_CANDIDATE
        status = PriceFlowStatus.MEASURED
        flags.extend(
            (
                "two_anchor_mismatch_not_classical_pivot_divergence",
                "public_trade_feed_coverage_not_independently_proven",
            )
        )
    if not flags:
        flags.append("unresolved_price_flow")
    observed_at_ms = max(
        (flow.analysis.observed_at_ms, *(item.ingested_at_ms for item in candles))
    )
    payload: dict[str, object] = {
        "as_of_ms": as_of_ms,
        "config_identity": config.identity,
        "consumed_closed_candle_count": len(candles),
        "engine_version": ENGINE_VERSION,
        "exchange": exchange,
        "first_anchor_close_ms": None if not candles else candles[0].close_time_ms,
        "first_candle_identity": None if not candles else _candle_identity(candles[0]),
        "flow_evidence_identity": flow.analysis.evidence_identity,
        "flow_freeze_identity": flow.freeze_identity,
        "last_anchor_close_ms": None if not candles else candles[-1].close_time_ms,
        "last_candle_identity": None if not candles else _candle_identity(candles[-1]),
        "market_type": market_type,
        "metrics": None if metrics is None else _metrics_payload(metrics),
        "observed_at_ms": observed_at_ms,
        "state": state,
        "status": status,
        "symbol": symbol,
        "timeframe": timeframe,
        "uncertainty_flags": tuple(flags),
    }
    return PriceFlowAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=ENGINE_VERSION,
        config_identity=config.identity,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        as_of_ms=as_of_ms,
        observed_at_ms=observed_at_ms,
        flow_evidence_identity=flow.analysis.evidence_identity,
        flow_freeze_identity=flow.freeze_identity,
        first_candle_identity=None if not candles else _candle_identity(candles[0]),
        last_candle_identity=None if not candles else _candle_identity(candles[-1]),
        first_anchor_close_ms=None if not candles else candles[0].close_time_ms,
        last_anchor_close_ms=None if not candles else candles[-1].close_time_ms,
        consumed_closed_candle_count=len(candles),
        status=status,
        state=state,
        metrics=metrics,
        uncertainty_flags=tuple(flags),
    )


def _signed_notional(item: PublicTradeObservation) -> Decimal:
    return item.notional if item.aggressor_side is AggressorSide.BUY else -item.notional


def _candle_identity(candle: Candle) -> str:
    return canonical_sha256(
        {name: getattr(candle, name) for name in candle.__dataclass_fields__}
    )


def _metrics_payload(item: PriceFlowMetrics) -> dict[str, object]:
    return {name: getattr(item, name) for name in item.__dataclass_fields__}


def _analysis_payload(item: PriceFlowAnalysis) -> dict[str, object]:
    return {
        name: (
            None if item.metrics is None else _metrics_payload(item.metrics)
        ) if name == "metrics" else getattr(item, name)
        for name in item.__dataclass_fields__
        if name != "evidence_identity"
    }


def _finite(value: Decimal, name: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{name} must be finite")


def _sha(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be SHA256")
