from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from crypto_signal.confluence.adapters import (
    elliott_result_evidence,
    harmonic_result_evidence,
    price_action_structure_evidence,
)
from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.data.adapters.base import (
    MarketDataAdapter,
    SourceAwareMarketDataAdapter,
)
from crypto_signal.data.candle_source_contract import (
    persist_candle_source_snapshot,
)
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle
from crypto_signal.data.source_contract import SourceContractStore
from crypto_signal.data.store import CandleStore
from crypto_signal.ledger.bundle import DecisionFreezeBundle, build_decision_freeze_bundle
from crypto_signal.ledger.store import (
    ImmutableSignalLedger,
    LedgerWriteDisposition,
)
from crypto_signal.methodologies.elliott.analysis import analyze_elliott
from crypto_signal.methodologies.harmonic.analysis import analyze_harmonics
from crypto_signal.methodologies.price_action.analysis import analyze_price_action
from crypto_signal.signals.lifecycle import evaluate_signal_lifecycle
from crypto_signal.signals.models import SignalState
from crypto_signal.signals.semantics import build_signal_decision


class LiveFreezeStatus(StrEnum):
    FROZEN = "frozen"
    ALREADY_FROZEN = "already_frozen"


@dataclass(frozen=True, slots=True)
class LiveFreezeResult:
    status: LiveFreezeStatus
    source_cutoff_open_time_ms: int
    signal_freeze_identity: str | None
    bundle_identity: str | None
    signal_state: SignalState | None
    confluence_score: str | None
    lifecycle_disposition: LedgerWriteDisposition | None
    bundle: DecisionFreezeBundle | None = None
    frozen_at_ms: int | None = None

    def __post_init__(self) -> None:
        if self.source_cutoff_open_time_ms < 0:
            raise ValueError("live freeze source cutoff must be non-negative")
        if self.status is LiveFreezeStatus.FROZEN:
            if self.bundle is None or self.frozen_at_ms is None:
                raise ValueError(
                    "fresh live freeze requires exact in-process bundle and timestamp"
                )
            if self.bundle.bundle_identity != self.bundle_identity:
                raise ValueError("live freeze result bundle identity mismatch")
            if (
                self.bundle.signal_decision.freeze_identity
                != self.signal_freeze_identity
            ):
                raise ValueError("live freeze result signal identity mismatch")
            if self.frozen_at_ms < self.bundle.signal_decision.as_of_ms:
                raise ValueError("live freeze timestamp predates signal as-of")
        elif self.bundle is not None or self.frozen_at_ms is not None:
            raise ValueError(
                "already-frozen result cannot replay historical bundle as fresh"
            )


def utc_now_ms() -> int:
    return time.time_ns() // 1_000_000


def _closed_observed(
    candles: tuple[Candle, ...],
    *,
    observed_at_ms: int,
) -> tuple[Candle, ...]:
    eligible = tuple(
        candle
        for candle in candles
        if candle.is_closed
        and candle.close_time_ms <= observed_at_ms
        and candle.ingested_at_ms <= observed_at_ms
    )
    if not eligible:
        raise ValueError("live freeze has no closed observed candles")
    eligible = tuple(sorted(eligible, key=lambda candle: candle.open_time_ms))
    if detect_gaps(eligible, eligible[0].timeframe):
        raise ValueError("live freeze refuses candle gaps")
    return eligible


def freeze_live_candles(
    *,
    candles: tuple[Candle, ...],
    ledger: ImmutableSignalLedger,
    minimum_closed_candles: int = 100,
    now_ms: Callable[[], int] = utc_now_ms,
) -> LiveFreezeResult:
    if minimum_closed_candles <= 0:
        raise ValueError(
            "live freeze minimum closed candle count must be positive"
        )
    raw = tuple(candles)
    observed_at_ms = max(
        now_ms(),
        max((candle.ingested_at_ms for candle in raw), default=0),
    )
    eligible = _closed_observed(raw, observed_at_ms=observed_at_ms)
    if len(eligible) < minimum_closed_candles:
        raise ValueError(
            "live freeze has insufficient closed candle history"
        )

    first = eligible[0]
    source_cutoff = eligible[-1].open_time_ms
    if ledger.has_source_cutoff(
        exchange=first.exchange.value,
        market_type=first.market_type.value,
        symbol=first.symbol,
        timeframe=first.timeframe,
        source_cutoff_open_time_ms=source_cutoff,
    ):
        return LiveFreezeResult(
            status=LiveFreezeStatus.ALREADY_FROZEN,
            source_cutoff_open_time_ms=source_cutoff,
            signal_freeze_identity=None,
            bundle_identity=None,
            signal_state=None,
            confluence_score=None,
            lifecycle_disposition=None,
            bundle=None,
            frozen_at_ms=None,
        )

    as_of_ms = max(observed_at_ms, now_ms())
    price_action = analyze_price_action(eligible, as_of_ms=as_of_ms)
    harmonic = analyze_harmonics(eligible, as_of_ms=as_of_ms)
    elliott = analyze_elliott(eligible, as_of_ms=as_of_ms)

    evidence = []
    pa_item = price_action_structure_evidence(price_action)
    if pa_item is not None:
        evidence.append(pa_item)
    evidence.extend(harmonic_result_evidence(harmonic))
    evidence.extend(elliott_result_evidence(elliott))

    confluence = analyze_confluence(
        evidence,
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=as_of_ms,
    )
    decision = build_signal_decision(confluence)
    bundle: DecisionFreezeBundle = build_decision_freeze_bundle(
        decision=decision,
        confluence=confluence,
        price_action=price_action,
        harmonic=harmonic,
        elliott=elliott,
        candles=eligible,
    )
    frozen_at_ms = max(now_ms(), decision.as_of_ms)
    disposition = ledger.freeze(
        bundle,
        frozen_at_ms=frozen_at_ms,
    )
    if disposition is not LedgerWriteDisposition.INSERTED:
        raise AssertionError("new source cutoff did not insert a ledger freeze")

    lifecycle = evaluate_signal_lifecycle(
        decision,
        bundle.candles,
        as_of_ms=decision.as_of_ms,
    )
    lifecycle_disposition = ledger.append_lifecycle_evaluation(
        lifecycle,
        appended_at_ms=max(now_ms(), lifecycle.evaluated_as_of_ms),
    )

    return LiveFreezeResult(
        status=LiveFreezeStatus.FROZEN,
        source_cutoff_open_time_ms=source_cutoff,
        signal_freeze_identity=decision.freeze_identity,
        bundle_identity=bundle.bundle_identity,
        signal_state=decision.state,
        confluence_score=str(confluence.score.value),
        lifecycle_disposition=lifecycle_disposition,
        bundle=bundle,
        frozen_at_ms=frozen_at_ms,
    )


async def freeze_live_provider(
    *,
    adapter: MarketDataAdapter,
    ledger: ImmutableSignalLedger,
    candle_store: CandleStore | None = None,
    source_store: SourceContractStore | None = None,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    limit: int = 500,
    minimum_closed_candles: int = 100,
    now_ms: Callable[[], int] = utc_now_ms,
) -> LiveFreezeResult:
    if source_store is not None:
        if candle_store is None:
            raise ValueError(
                "source-aware live freeze requires candle store"
            )
        if not hasattr(adapter, "fetch_source_candles"):
            raise TypeError(
                "source-aware live freeze requires source-aware adapter"
            )
        snapshot = await cast(
            SourceAwareMarketDataAdapter,
            adapter,
        ).fetch_source_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        persist_candle_source_snapshot(
            candle_store=candle_store,
            source_store=source_store,
            snapshot=snapshot,
        )
        raw = snapshot.candles
    else:
        raw = tuple(
            await adapter.fetch_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
        )
        if candle_store is not None:
            for candle in raw:
                candle_store.upsert(candle)
    return freeze_live_candles(
        candles=raw,
        ledger=ledger,
        minimum_closed_candles=minimum_closed_candles,
        now_ms=now_ms,
    )
