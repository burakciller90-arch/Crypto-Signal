#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import fcntl
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from crypto_signal.data.adapters.base import MarketDataAdapter
from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.data.provider_divergence import (
    ProviderDivergenceCycleResult,
    collect_provider_divergence_cycle,
)
from crypto_signal.data.store import CandleStore
from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.live_untouched_forward_runtime import (
    process_wc2_live_freeze,
)
from crypto_signal.evaluation.untouched_forward_journal import WC2CohortJournal
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2PolicyStore,
    WC2UntouchedForwardPolicy,
)
from crypto_signal.ledger.coverage import (
    LiveCoveragePlan,
)
from crypto_signal.ledger.live_coverage import freeze_coverage_context
from crypto_signal.ledger.store import (
    ImmutableSignalLedger,
    LedgerConflictError,
)

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_DB = BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
DEFAULT_CANDLE_CACHE = BASE / "runtime" / "data" / "live_base_15m_cache.sqlite3"
LOCK_PATH = BASE / "runtime" / "ledger" / "live_clock.lock"
PROVIDER_DIVERGENCE_LOOKBACK = 96


@dataclass(frozen=True, slots=True)
class WC2ClockConfig:
    enabled: bool = False
    policy_path: Path | None = None
    decision_evidence_path: Path | None = None
    cohort_path: Path | None = None
    maximum_issuance_delay_ms: int | None = None
    horizon_bars: int | None = None

    def __post_init__(self) -> None:
        values = (
            self.policy_path,
            self.decision_evidence_path,
            self.cohort_path,
            self.maximum_issuance_delay_ms,
            self.horizon_bars,
        )
        if not self.enabled:
            if any(value is not None for value in values):
                raise ValueError(
                    "WC2 clock options require explicit --wc2-enabled"
                )
            return
        if any(value is None for value in values):
            raise ValueError(
                "enabled WC2 clock requires policy, decision, cohort, "
                "issuance-delay and horizon inputs"
            )
        assert self.maximum_issuance_delay_ms is not None
        assert self.horizon_bars is not None
        if self.maximum_issuance_delay_ms <= 0:
            raise ValueError("WC2 clock issuance delay must be positive")
        if self.horizon_bars <= 0:
            raise ValueError("WC2 clock horizon bars must be positive")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="immutable ledger SQLite path",
    )
    parser.add_argument(
        "--candle-cache",
        type=Path,
        default=DEFAULT_CANDLE_CACHE,
        help="canonical 15m cache used for higher-timeframe preparation",
    )
    parser.add_argument(
        "--provider-divergence",
        type=Path,
        default=None,
        help=(
            "append-only provider divergence SQLite path; defaults next "
            "to the active candle cache"
        ),
    )
    parser.add_argument(
        "--wc2-enabled",
        action="store_true",
        help="explicitly enable preregistered WC2 untouched-forward indexing",
    )
    parser.add_argument("--wc2-policy", type=Path, default=None)
    parser.add_argument("--wc2-decision-evidence", type=Path, default=None)
    parser.add_argument("--wc2-cohort", type=Path, default=None)
    parser.add_argument(
        "--wc2-maximum-issuance-delay-ms",
        type=int,
        default=None,
    )
    parser.add_argument("--wc2-horizon-bars", type=int, default=None)
    return parser.parse_args()


def build_wc2_clock_config(args: argparse.Namespace) -> WC2ClockConfig:
    return WC2ClockConfig(
        enabled=bool(args.wc2_enabled),
        policy_path=args.wc2_policy,
        decision_evidence_path=args.wc2_decision_evidence,
        cohort_path=args.wc2_cohort,
        maximum_issuance_delay_ms=args.wc2_maximum_issuance_delay_ms,
        horizon_bars=args.wc2_horizon_bars,
    )


def load_wc2_policy(config: WC2ClockConfig) -> WC2UntouchedForwardPolicy | None:
    if not config.enabled:
        return None
    assert config.policy_path is not None
    policy = WC2PolicyStore(config.policy_path).latest()
    if policy is None:
        raise ValueError("WC2 clock enabled but preregistered policy is missing")
    return policy


def wc2_base_asset(symbol: str) -> str:
    if not symbol.endswith("USDT") or len(symbol) <= len("USDT"):
        raise ValueError("WC2 live clock requires explicit USDT coverage symbol")
    asset = symbol[: -len("USDT")]
    if not asset or asset != asset.upper():
        raise ValueError("WC2 live clock base asset must be uppercase")
    return asset


def provider_divergence_symbols(
    plan: LiveCoveragePlan,
) -> tuple[str, ...]:
    exchanges_by_symbol: dict[str, set[Exchange]] = {}
    for context in plan.enabled_contexts:
        if (
            context.market_type is not MarketType.SPOT
            or context.timeframe != "15m"
        ):
            continue
        exchanges_by_symbol.setdefault(context.symbol, set()).add(
            context.exchange
        )
    required = {Exchange.BINANCE, Exchange.BYBIT}
    return tuple(
        sorted(
            symbol
            for symbol, exchanges in exchanges_by_symbol.items()
            if required.issubset(exchanges)
        )
    )


def persist_provider_divergence_for_plan(
    *,
    plan: LiveCoveragePlan,
    candle_cache_path: Path,
    provider_divergence_path: Path,
    observed_at_ms: int,
) -> ProviderDivergenceCycleResult | None:
    symbols = provider_divergence_symbols(plan)
    if not symbols:
        return None
    return collect_provider_divergence_cycle(
        candle_db=candle_cache_path,
        divergence_db=provider_divergence_path,
        symbols=symbols,
        timeframe="15m",
        lookback=PROVIDER_DIVERGENCE_LOOKBACK,
        observed_at_ms=observed_at_ms,
    )


async def run(
    db_path: Path,
    *,
    plan: LiveCoveragePlan | None = None,
    candle_cache_path: Path = DEFAULT_CANDLE_CACHE,
    provider_divergence_path: Path | None = None,
    wc2_config: WC2ClockConfig | None = None,
) -> int:
    ledger = ImmutableSignalLedger(db_path)
    candle_store = CandleStore(candle_cache_path)
    failures = 0
    selected_wc2 = wc2_config or WC2ClockConfig()
    try:
        wc2_policy = load_wc2_policy(selected_wc2)
    except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
        print(
            f"wc2 status=ERROR error={type(exc).__name__}:{exc} "
            "REAL_CAPITAL=0",
            file=sys.stderr,
            flush=True,
        )
        return 1
    wc2_decision = (
        None
        if not selected_wc2.enabled
        else ImmutableDecisionEvidenceLedger(
            _required_path(
                selected_wc2.decision_evidence_path,
                "WC2 decision evidence",
            )
        )
    )
    wc2_cohort = (
        None
        if not selected_wc2.enabled
        else WC2CohortJournal(
            _required_path(selected_wc2.cohort_path, "WC2 cohort")
        )
    )
    selected_plan = LiveCoveragePlan.current_pilot() if plan is None else plan
    adapters: dict[Exchange, MarketDataAdapter] = {
        Exchange.BYBIT: BybitSpotAdapter(),
        Exchange.BINANCE: BinanceSpotAdapter(),
    }

    for context in selected_plan.enabled_contexts:
        name = context.exchange.value
        adapter = adapters[context.exchange]
        try:
            result = await freeze_coverage_context(
                context=context,
                adapter=adapter,
                ledger=ledger,
                candle_store=candle_store,
            )
        except (
            LedgerConflictError,
            OSError,
            ValueError,
            httpx.HTTPError,
            sqlite3.Error,
        ) as exc:
            failures += 1
            print(
                f"provider={name} symbol={context.symbol} "
                f"timeframe={context.timeframe} status=ERROR "
                f"error={type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
            continue

        print(
            f"provider={name} symbol={context.symbol} "
            f"timeframe={context.timeframe} status={result.status.value} "
            f"cutoff={result.source_cutoff_open_time_ms} "
            f"signal={result.signal_freeze_identity or '-'} "
            f"bundle={result.bundle_identity or '-'} "
            f"state={result.signal_state.value if result.signal_state else '-'} "
            f"score={result.confluence_score or '-'} "
            f"lifecycle={result.lifecycle_disposition.value if result.lifecycle_disposition else '-'}",
            flush=True,
        )

        if selected_wc2.enabled:
            assert wc2_policy is not None
            assert wc2_decision is not None
            assert wc2_cohort is not None
            assert selected_wc2.maximum_issuance_delay_ms is not None
            assert selected_wc2.horizon_bars is not None
            try:
                wc2_result = process_wc2_live_freeze(
                    result,
                    context=context,
                    signal_ledger=ledger,
                    policy=wc2_policy,
                    decision_ledger=wc2_decision,
                    cohort_journal=wc2_cohort,
                    observed_at_ms=time.time_ns() // 1_000_000,
                    maximum_issuance_delay_ms=(
                        selected_wc2.maximum_issuance_delay_ms
                    ),
                    horizon_bars=selected_wc2.horizon_bars,
                    base_asset=wc2_base_asset(context.symbol),
                )
            except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
                failures += 1
                print(
                    f"wc2 provider={name} symbol={context.symbol} "
                    f"timeframe={context.timeframe} status=ERROR "
                    f"error={type(exc).__name__}:{exc} REAL_CAPITAL=0",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(
                    f"wc2 provider={name} symbol={context.symbol} "
                    f"timeframe={context.timeframe} "
                    f"status={wc2_result.status.value} "
                    f"forecast={wc2_result.forecast_identity or '-'} "
                    f"cohort={wc2_result.cohort_forecast_identity or '-'} "
                    "HISTORICAL_FORECAST_BACKFILL=NO REAL_CAPITAL=0",
                    flush=True,
                )

    selected_divergence_path = (
        provider_divergence_path
        if provider_divergence_path is not None
        else candle_cache_path.with_name("provider_divergence.sqlite3")
    )
    try:
        divergence = persist_provider_divergence_for_plan(
            plan=selected_plan,
            candle_cache_path=candle_cache_path,
            provider_divergence_path=selected_divergence_path,
            observed_at_ms=time.time_ns() // 1_000_000,
        )
    except (OSError, ValueError, sqlite3.Error) as exc:
        failures += 1
        print(
            "provider_divergence status=ERROR "
            f"error={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
    else:
        if divergence is None:
            print(
                "provider_divergence status=SKIPPED "
                "reason=no_shared_binance_bybit_15m_context "
                "CONSENSUS_NOT_INFERRED=YES REAL_CAPITAL=0",
                flush=True,
            )
        else:
            for snapshot in divergence.snapshots:
                print(
                    "provider_divergence "
                    f"symbol={snapshot.symbol} "
                    f"status=PERSISTED "
                    f"grid={snapshot.grid_state.value} "
                    f"overlap={snapshot.overlap_count} "
                    f"binance_stale={snapshot.left_quality.stale} "
                    f"bybit_stale={snapshot.right_quality.stale} "
                    f"snapshot={snapshot.snapshot_identity}",
                    flush=True,
                )
            print(
                "provider_divergence status=COMPLETE "
                f"snapshots={len(divergence.snapshots)} "
                "CONSENSUS_NOT_INFERRED=YES REAL_CAPITAL=0",
                flush=True,
            )

    return 1 if failures else 0


def _required_path(path: Path | None, label: str) -> Path:
    if path is None:
        raise ValueError(f"{label} path is required")
    return path


def main() -> int:
    args = parse_args()
    try:
        wc2_config = build_wc2_clock_config(args)
    except ValueError as exc:
        print(f"WC2_CLOCK_CONFIG_ERROR={exc}", file=sys.stderr, flush=True)
        return 2
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock_handle:
        try:
            fcntl.flock(
                lock_handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            print("LIVE_CLOCK_ALREADY_RUNNING", flush=True)
            return 0
        return asyncio.run(
            run(
                args.db,
                candle_cache_path=args.candle_cache,
                provider_divergence_path=args.provider_divergence,
                wc2_config=wc2_config,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
