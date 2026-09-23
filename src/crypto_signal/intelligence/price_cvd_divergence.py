"""Independent point-in-time book-mid vs window-local CVD research evidence."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from crypto_signal.data.microstructure import OrderBookSnapshot, PublicTradeObservation
from crypto_signal.intelligence.temporal_order_flow import (
    TemporalFlowConfig,
    TemporalFlowEvidenceFreeze,
    TemporalFlowStatus,
    build_temporal_order_flow_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256

VERSION = "m3-price-cvd-divergence-slice2/1"
_BPS = Decimal(10000)


class DivergenceState(StrEnum):
    BEARISH_CANDIDATE = "bearish_price_cvd_divergence_candidate"
    BULLISH_CANDIDATE = "bullish_price_cvd_divergence_candidate"
    NONE = "none"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class DivergenceConfig:
    window_ms: int = 120_000
    minimum_snapshots: int = 3
    max_book_age_ms: int = 30_000
    max_book_gap_ms: int = 30_000
    min_price_move_bps: Decimal = Decimal(5)
    min_opposing_imbalance: Decimal = Decimal("0.20")

    def __post_init__(self) -> None:
        if (
            self.window_ms <= 0
            or self.minimum_snapshots < 2
            or self.max_book_age_ms <= 0
            or self.max_book_gap_ms <= 0
        ):
            raise ValueError("invalid divergence time/depth configuration")
        for number in (self.min_price_move_bps, self.min_opposing_imbalance):
            if not number.is_finite() or number <= 0:
                raise ValueError("divergence thresholds must be finite and positive")
        if self.min_opposing_imbalance > 1:
            raise ValueError("opposing imbalance cannot exceed 1")

    @property
    def identity(self) -> str:
        return canonical_sha256(
            {
                "window_ms": self.window_ms,
                "minimum_snapshots": self.minimum_snapshots,
                "max_book_age_ms": self.max_book_age_ms,
                "max_book_gap_ms": self.max_book_gap_ms,
                "min_price_move_bps": self.min_price_move_bps,
                "min_opposing_imbalance": self.min_opposing_imbalance,
            }
        )


@dataclass(frozen=True, slots=True)
class DivergenceAnalysis:
    evidence_identity: str
    config_identity: str
    flow_identity: str
    flow_freeze_identity: str
    as_of_ms: int
    snapshot_count: int
    first_snapshot_identity: str | None
    last_snapshot_identity: str | None
    state: DivergenceState
    first_mid: Decimal | None
    last_mid: Decimal | None
    price_move_bps: Decimal | None
    window_local_cvd: Decimal | None
    taker_imbalance: Decimal | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.evidence_identity != canonical_sha256(_payload(self)):
            raise ValueError("divergence evidence identity mismatch")
        if self.state is DivergenceState.UNRESOLVED:
            if any(x is not None for x in (
                self.first_mid, self.last_mid, self.price_move_bps,
                self.window_local_cvd, self.taker_imbalance,
            )):
                raise ValueError("unresolved divergence cannot show partial metrics")
            if not self.uncertainty_flags:
                raise ValueError("unresolved divergence needs uncertainty")


@dataclass(frozen=True, slots=True)
class DivergenceFreeze:
    freeze_identity: str
    analysis: DivergenceAnalysis
    flow: TemporalFlowEvidenceFreeze
    books: tuple[OrderBookSnapshot, ...]

    def __post_init__(self) -> None:
        if self.analysis.flow_freeze_identity != self.flow.freeze_identity:
            raise ValueError("divergence flow freeze mismatch")
        if self.analysis.snapshot_count != len(self.books):
            raise ValueError("divergence frozen book count mismatch")
        expected = canonical_sha256({
            "analysis_identity": self.analysis.evidence_identity,
            "flow_freeze_identity": self.flow.freeze_identity,
            "books": [book.snapshot_identity for book in self.books],
            "version": VERSION,
        })
        if expected != self.freeze_identity:
            raise ValueError("divergence freeze identity mismatch")


def build_divergence_freeze(
    books: Sequence[OrderBookSnapshot],
    trades: Sequence[PublicTradeObservation],
    *,
    as_of_ms: int,
    config: DivergenceConfig = DivergenceConfig(),
    flow_config: TemporalFlowConfig = TemporalFlowConfig(),
) -> DivergenceFreeze:
    if as_of_ms < 0 or config.window_ms != flow_config.window_ms:
        raise ValueError("invalid as_of or unmatched evidence windows")
    if not books:
        raise ValueError("divergence requires source order-book evidence")
    flow = build_temporal_order_flow_freeze(
        trades, as_of_ms=as_of_ms, config=flow_config
    )
    ordered = tuple(sorted(books, key=lambda b: (
        b.event_at_ms, b.sequence, b.update_id, b.snapshot_identity,
    )))
    if len({b.snapshot_identity for b in ordered}) != len(ordered):
        raise ValueError("duplicate divergence book identity")
    context = (
        flow.analysis.exchange, flow.analysis.market_type, flow.analysis.symbol
    )
    if any((b.exchange, b.market_type, b.symbol) != context for b in ordered):
        raise ValueError("mixed divergence market context")
    start = max(0, as_of_ms - config.window_ms)
    selected = tuple(b for b in ordered if start <= b.event_at_ms <= as_of_ms
        and max(b.source_timestamp_ms, b.response_time_ms, b.ingested_at_ms)
        <= as_of_ms)
    eligible = tuple(t for t in flow.trades if t.book_eligible)
    problems: list[str] = []
    if flow.analysis.status is not TemporalFlowStatus.MEASURED:
        problems.append("temporal_flow_unresolved")
    if len(selected) < config.minimum_snapshots:
        problems.append("insufficient_orderbook_snapshots")
    if selected and as_of_ms - selected[-1].event_at_ms > config.max_book_age_ms:
        problems.append("stale_latest_orderbook")
    if any(
        b.event_at_ms - a.event_at_ms > config.max_book_gap_ms
        for a, b in pairwise(selected)
    ):
        problems.append("orderbook_gap_exceeds_limit")
    if selected and selected[0].event_at_ms == selected[-1].event_at_ms:
        problems.append("insufficient_price_span")
    if selected and eligible and (
        selected[0].event_at_ms > eligible[0].event_at_ms
        or selected[-1].event_at_ms < eligible[-1].event_at_ms
    ):
        problems.append("price_does_not_cover_trade_window")

    state = DivergenceState.UNRESOLVED
    first_mid: Decimal | None = None
    last_mid: Decimal | None = None
    move: Decimal | None = None
    cvd: Decimal | None = None
    imbalance: Decimal | None = None
    flags = ["window_local_cvd_only", "book_mid_not_executable_price", *problems]
    if not problems:
        assert flow.analysis.metrics is not None
        first_mid = (selected[0].bids[0].price + selected[0].asks[0].price) / 2
        last_mid = (selected[-1].bids[0].price + selected[-1].asks[0].price) / 2
        move = (last_mid - first_mid) / first_mid * _BPS
        cvd = flow.analysis.metrics.cvd_window_end_notional
        imbalance = flow.analysis.metrics.taker_imbalance
        state = DivergenceState.NONE
        if move >= config.min_price_move_bps and imbalance <= -config.min_opposing_imbalance:
            state = DivergenceState.BEARISH_CANDIDATE
        elif move <= -config.min_price_move_bps and imbalance >= config.min_opposing_imbalance:
            state = DivergenceState.BULLISH_CANDIDATE
        flags.append("candidate_not_reversal_prediction" if state is not DivergenceState.NONE
                     else "no_qualified_divergence")
    payload: dict[str, object] = {
        "config_identity": config.identity,
        "flow_identity": flow.analysis.evidence_identity,
        "flow_freeze_identity": flow.freeze_identity,
        "as_of_ms": as_of_ms,
        "snapshot_count": len(selected),
        "first_snapshot_identity": None if not selected else selected[0].snapshot_identity,
        "last_snapshot_identity": None if not selected else selected[-1].snapshot_identity,
        "state": state,
        "first_mid": first_mid,
        "last_mid": last_mid,
        "price_move_bps": move,
        "window_local_cvd": cvd,
        "taker_imbalance": imbalance,
        "uncertainty_flags": tuple(flags),
    }
    analysis = DivergenceAnalysis(evidence_identity=canonical_sha256(payload), **payload)
    return DivergenceFreeze(
        freeze_identity=canonical_sha256({
            "analysis_identity": analysis.evidence_identity,
            "flow_freeze_identity": flow.freeze_identity,
            "books": [b.snapshot_identity for b in selected],
            "version": VERSION,
        }),
        analysis=analysis, flow=flow, books=selected,
    )


def _payload(a: DivergenceAnalysis) -> dict[str, object]:
    return {
        key: getattr(a, key)
        for key in a.__dataclass_fields__
        if key != "evidence_identity"
    }
