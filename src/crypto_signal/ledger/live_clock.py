from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.confluence.adapters import (
    elliott_result_evidence,
    harmonic_result_evidence,
    price_action_structure_evidence,
)
from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.data.adapters.base import MarketDataAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle
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


async def freeze_live_provider(
    *,
    adapter: MarketDataAdapter,
    ledger: ImmutableSignalLedger,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    limit: int = 500,
    minimum_closed_candles: int = 100,
    now_ms: Callable[[], int] = utc_now_ms,
) -> LiveFreezeResult:
    raw = tuple(
        await adapter.fetch_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
    )
    observed_at_ms = max(
        now_ms(),
        max((candle.ingested_at_ms for candle in raw), default=0),
    )
    candles = _closed_observed(raw, observed_at_ms=observed_at_ms)
    if len(candles) < minimum_closed_candles:
        raise ValueError(
            "live freeze has insufficient closed candle history"
        )

    first = candles[0]
    source_cutoff = candles[-1].open_time_ms
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
        )

    as_of_ms = max(observed_at_ms, now_ms())
    price_action = analyze_price_action(candles, as_of_ms=as_of_ms)
    harmonic = analyze_harmonics(candles, as_of_ms=as_of_ms)
    elliott = analyze_elliott(candles, as_of_ms=as_of_ms)

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
        candles=candles,
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
    )
