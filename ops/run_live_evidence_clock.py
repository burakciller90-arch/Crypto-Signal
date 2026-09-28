#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import fcntl
import os
import sqlite3
import sys
import time
from collections import Counter
from collections.abc import Mapping
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
from crypto_signal.data.source_contract import SourceContractStore
from crypto_signal.data.store import CandleStore
from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    WC2CollectionProtocol,
    WC2CollectionProtocolStore,
)
from crypto_signal.evaluation.untouched_forward_execution_runtime import (
    process_wc2_paper_execution_cycle,
)
from crypto_signal.evaluation.untouched_forward_journal import WC2CohortJournal
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2PolicyStore,
    WC2UntouchedForwardPolicy,
)
from crypto_signal.evaluation.untouched_forward_prepared import (
    WC2PreparedCycleJournal,
)
from crypto_signal.evaluation.untouched_forward_prepared_runtime import (
    WC2PreparedLiveStatus,
    process_wc2_prepared_live_freeze,
)
from crypto_signal.evaluation.untouched_forward_resolution_runtime import (
    resolve_wc2_outcomes_once,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerAnalysis
from crypto_signal.ledger.coverage import (
    LiveCoveragePlan,
)
from crypto_signal.ledger.live_coverage import freeze_coverage_context
from crypto_signal.ledger.store import (
    ImmutableSignalLedger,
    LedgerConflictError,
)
from crypto_signal.paper.epoch2_accounting import (
    Epoch2ActivationRecord,
    read_epoch2_state_read_only,
)
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.product.intelligence_stream_capital_forward_runtime import (
    IntelligenceStreamCapitalForwardRuntime,
    StreamCapitalForwardResult,
)
from crypto_signal.product.intelligence_stream_family import StreamFamilySnapshot
from crypto_signal.product.intelligence_stream_family_sources import (
    build_geometry_family_snapshot_from_bundle,
    build_geometry_lifecycle_family_snapshot,
    build_market_tape_family_snapshots,
)
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
)
from crypto_signal.product.intelligence_stream_local_rewriter import (
    LocalNarrativeRewriteConfig,
    OpenAICompatibleLocalNarrativeRewriter,
)
from crypto_signal.product.intelligence_stream_production_projector import (
    IntelligenceStreamProductionProjector,
)
from crypto_signal.product.intelligence_stream_system_view import (
    IntelligenceStreamSystemViewRuntime,
)
from crypto_signal.product.intelligence_stream_trust_sources import (
    build_event_risk_stream_snapshots,
    build_provider_quality_stream_snapshots,
)
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_DB = BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
DEFAULT_CANDLE_CACHE = BASE / "runtime" / "data" / "live_base_15m_cache.sqlite3"
DEFAULT_SOURCE_CONTRACT = BASE / "runtime" / "data" / "source_contract.sqlite3"
PROVIDER_DIVERGENCE_LOOKBACK = 96
STREAM_LOCAL_REWRITE_ENABLED_ENV = "CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_ENABLED"
STREAM_LOCAL_REWRITE_MODEL_ENV = "CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_MODEL"
STREAM_LOCAL_REWRITE_BASE_URL_ENV = "CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_BASE_URL"
STREAM_LOCAL_REWRITE_TIMEOUT_ENV = "CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_TIMEOUT_SECONDS"
STREAM_LOCAL_REWRITE_TEMPERATURE_ENV = "CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_TEMPERATURE"
STREAM_LOCAL_REWRITE_MAX_TOKENS_ENV = "CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_MAX_TOKENS"


@dataclass(frozen=True, slots=True)
class WC2ClockConfig:
    enabled: bool = False
    policy_path: Path | None = None
    epoch2_path: Path | None = None
    collection_protocol_path: Path | None = None
    prepared_path: Path | None = None
    decision_evidence_path: Path | None = None
    cohort_path: Path | None = None
    shadow_intent_path: Path | None = None
    shadow_cycle_path: Path | None = None
    execution_enabled: bool = False
    execution_protocol_path: Path | None = None
    execution_runtime_path: Path | None = None
    execution_journal_path: Path | None = None
    venue_rule_store_path: Path | None = None
    maximum_issuance_delay_ms: int | None = None
    horizon_bars: int | None = None

    def __post_init__(self) -> None:
        required_values = (
            self.policy_path,
            self.epoch2_path,
            self.collection_protocol_path,
            self.prepared_path,
            self.decision_evidence_path,
            self.cohort_path,
            self.shadow_intent_path,
            self.shadow_cycle_path,
        )
        execution_values = (
            self.execution_protocol_path,
            self.execution_runtime_path,
            self.execution_journal_path,
            self.venue_rule_store_path,
        )
        optional_legacy_values = (
            self.maximum_issuance_delay_ms,
            self.horizon_bars,
        )
        if not self.enabled:
            if self.execution_enabled or any(
                value is not None
                for value in (
                    *required_values,
                    *execution_values,
                    *optional_legacy_values,
                )
            ):
                raise ValueError(
                    "WC2 clock options require explicit --wc2-enabled"
                )
            return
        if any(value is None for value in required_values):
            raise ValueError(
                "enabled WC2 clock requires policy, Epoch2, collection-"
                "protocol, prepared, decision, cohort, shadow-intent and "
                "shadow-cycle inputs"
            )
        if any(value is not None for value in optional_legacy_values):
            raise ValueError(
                "WC2 issuance delay and horizon are immutable collection-"
                "protocol values, not runtime CLI inputs"
            )
        if self.execution_enabled:
            if any(value is None for value in execution_values):
                raise ValueError(
                    "enabled WC2 execution requires execution protocol, "
                    "runtime activation, execution journal and venue rules"
                )
        elif any(value is not None for value in execution_values):
            raise ValueError(
                "WC2 execution paths require explicit "
                "--wc2-execution-enabled"
            )


@dataclass(frozen=True, slots=True)
class StreamClockConfig:
    enabled: bool = False
    ledger_path: Path | None = None
    market_tape_path: Path | None = None
    event_source_path: Path | None = None
    family_symbols: tuple[str, ...] = ()
    local_rewrite_config: LocalNarrativeRewriteConfig | None = None

    def __post_init__(self) -> None:
        if self.enabled and self.ledger_path is None:
            raise ValueError("enabled Stream clock requires ledger path")
        if not self.enabled and (
            self.ledger_path is not None
            or self.market_tape_path is not None
            or self.event_source_path is not None
            or self.family_symbols
            or self.local_rewrite_config is not None
        ):
            raise ValueError(
                "Stream options require explicit --stream-enabled"
            )
        if self.market_tape_path is None and self.family_symbols:
            raise ValueError(
                "Stream family symbols require --stream-market-tape"
            )
        if self.market_tape_path is not None and not self.family_symbols:
            raise ValueError(
                "Stream Market Tape projection requires family symbols"
            )


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
        "--source-contract",
        type=Path,
        default=DEFAULT_SOURCE_CONTRACT,
        help="canonical candle source envelope/coverage SQLite path",
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
        "--bybit-base-url",
        default=None,
        help=(
            "explicit Bybit REST base URL for the deployment region; "
            "defaults to the adapter global endpoint"
        ),
    )
    parser.add_argument(
        "--binance-base-url",
        default=None,
        help=(
            "explicit Binance REST base URL for the deployment region; "
            "defaults to the adapter global endpoint"
        ),
    )
    parser.add_argument(
        "--binance-api-variant",
        choices=("global", "tr_main"),
        default="global",
        help="response contract for the selected Binance REST endpoint",
    )
    parser.add_argument(
        "--stream-enabled",
        action="store_true",
        help="enable forward-only Intelligence Stream production projection",
    )
    parser.add_argument(
        "--stream-ledger",
        type=Path,
        default=None,
        help="append-only Intelligence Stream SQLite path",
    )
    parser.add_argument(
        "--stream-market-tape",
        type=Path,
        default=None,
        help="persisted Market Tape source for live Stream intelligence families",
    )
    parser.add_argument(
        "--stream-family-symbols",
        nargs="+",
        default=None,
        help="symbols projected from persisted Market Tape into Stream",
    )
    parser.add_argument(
        "--stream-event-source",
        type=Path,
        default=None,
        help="persisted Event Source SQLite path for Event Risk projection",
    )
    parser.add_argument(
        "--wc2-enabled",
        action="store_true",
        help="explicitly enable preregistered WC2 untouched-forward indexing",
    )
    parser.add_argument("--wc2-policy", type=Path, default=None)
    parser.add_argument("--wc2-epoch2", type=Path, default=None)
    parser.add_argument(
        "--wc2-collection-protocol",
        type=Path,
        default=None,
    )
    parser.add_argument("--wc2-prepared", type=Path, default=None)
    parser.add_argument("--wc2-decision-evidence", type=Path, default=None)
    parser.add_argument("--wc2-cohort", type=Path, default=None)
    parser.add_argument("--wc2-shadow-intent", type=Path, default=None)
    parser.add_argument("--wc2-shadow-cycle", type=Path, default=None)
    parser.add_argument(
        "--wc2-execution-enabled",
        action="store_true",
        help="enable preregistered forward-only WC2 paper execution writer",
    )
    parser.add_argument("--wc2-execution-protocol", type=Path, default=None)
    parser.add_argument("--wc2-execution-runtime", type=Path, default=None)
    parser.add_argument("--wc2-execution-journal", type=Path, default=None)
    parser.add_argument("--wc2-venue-rules", type=Path, default=None)
    parser.add_argument(
        "--wc2-maximum-issuance-delay-ms",
        type=int,
        default=None,
        help="rejected when WC2 is enabled; collection protocol owns this",
    )
    parser.add_argument(
        "--wc2-horizon-bars",
        type=int,
        default=None,
        help="rejected when WC2 is enabled; collection protocol owns this",
    )
    return parser.parse_args()


def build_stream_local_rewrite_config(
    environ: Mapping[str, str],
) -> LocalNarrativeRewriteConfig | None:
    enabled_raw = environ.get(STREAM_LOCAL_REWRITE_ENABLED_ENV, "").strip().lower()
    if enabled_raw in {"", "0", "false", "no", "off"}:
        return None
    if enabled_raw not in {"1", "true", "yes", "on"}:
        raise ValueError(
            "Stream local rewrite enable flag must be an explicit boolean"
        )

    model = environ.get(STREAM_LOCAL_REWRITE_MODEL_ENV, "").strip()
    if not model:
        raise ValueError(
            "enabled Stream local rewrite requires explicit local model"
        )
    base_url = environ.get(
        STREAM_LOCAL_REWRITE_BASE_URL_ENV,
        "http://127.0.0.1:11434/v1",
    ).strip()
    try:
        timeout_seconds = float(
            environ.get(STREAM_LOCAL_REWRITE_TIMEOUT_ENV, "8.0")
        )
        temperature = float(
            environ.get(STREAM_LOCAL_REWRITE_TEMPERATURE_ENV, "0.25")
        )
        max_tokens = int(
            environ.get(STREAM_LOCAL_REWRITE_MAX_TOKENS_ENV, "1400")
        )
    except ValueError as exc:
        raise ValueError(
            "invalid Stream local rewrite numeric configuration"
        ) from exc
    if temperature > 0.3:
        raise ValueError(
            "Stream local rewrite runtime temperature must remain <= 0.3"
        )
    return LocalNarrativeRewriteConfig(
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def build_stream_clock_config(
    args: argparse.Namespace,
    *,
    environ: Mapping[str, str] | None = None,
) -> StreamClockConfig:
    selected_environ: Mapping[str, str] = {} if environ is None else environ
    local_rewrite_config = build_stream_local_rewrite_config(selected_environ)
    family_symbols_raw = getattr(args, "stream_family_symbols", None)
    family_symbols = (
        ()
        if family_symbols_raw is None
        else tuple(
            sorted(
                {
                    str(value).upper()
                    for value in family_symbols_raw
                    if str(value).strip()
                }
            )
        )
    )
    return StreamClockConfig(
        enabled=bool(getattr(args, "stream_enabled", False)),
        ledger_path=getattr(args, "stream_ledger", None),
        market_tape_path=getattr(args, "stream_market_tape", None),
        event_source_path=getattr(args, "stream_event_source", None),
        family_symbols=family_symbols,
        local_rewrite_config=local_rewrite_config,
    )


def build_wc2_clock_config(args: argparse.Namespace) -> WC2ClockConfig:
    return WC2ClockConfig(
        enabled=bool(args.wc2_enabled),
        policy_path=args.wc2_policy,
        epoch2_path=args.wc2_epoch2,
        collection_protocol_path=args.wc2_collection_protocol,
        prepared_path=args.wc2_prepared,
        decision_evidence_path=args.wc2_decision_evidence,
        cohort_path=args.wc2_cohort,
        shadow_intent_path=args.wc2_shadow_intent,
        shadow_cycle_path=args.wc2_shadow_cycle,
        execution_enabled=bool(args.wc2_execution_enabled),
        execution_protocol_path=args.wc2_execution_protocol,
        execution_runtime_path=args.wc2_execution_runtime,
        execution_journal_path=args.wc2_execution_journal,
        venue_rule_store_path=args.wc2_venue_rules,
        maximum_issuance_delay_ms=args.wc2_maximum_issuance_delay_ms,
        horizon_bars=args.wc2_horizon_bars,
    )


def load_wc2_prerequisites(
    config: WC2ClockConfig,
) -> tuple[
    WC2UntouchedForwardPolicy,
    Epoch2ActivationRecord,
    WC2CollectionProtocol,
] | None:
    if not config.enabled:
        return None
    assert config.policy_path is not None
    assert config.epoch2_path is not None
    assert config.collection_protocol_path is not None
    policy = WC2PolicyStore(config.policy_path).latest()
    if policy is None:
        raise ValueError("WC2 clock enabled but preregistered policy is missing")
    epoch2 = read_epoch2_state_read_only(config.epoch2_path)
    if epoch2 is None:
        raise ValueError(
            "WC2 clock enabled but canonical Epoch2 activation is missing"
        )
    protocol = WC2CollectionProtocolStore(
        config.collection_protocol_path
    ).latest()
    if protocol is None:
        raise ValueError(
            "WC2 clock enabled but collection protocol is missing"
        )
    if protocol.review_policy_identity != policy.policy_identity:
        raise ValueError("WC2 collection protocol/review policy mismatch")
    if (
        protocol.epoch2_activation_identity
        != epoch2.activation.activation_identity
    ):
        raise ValueError("WC2 collection protocol/Epoch2 mismatch")
    return policy, epoch2.activation, protocol


def wc2_base_asset(symbol: str) -> str:
    if not symbol.endswith("USDT") or len(symbol) <= len("USDT"):
        raise ValueError("WC2 live clock requires explicit USDT coverage symbol")
    asset = symbol[: -len("USDT")]
    if not asset or asset != asset.upper():
        raise ValueError("WC2 live clock base asset must be uppercase")
    return asset


def validate_wc2_collection_plan(
    protocol: WC2CollectionProtocol,
    plan: LiveCoveragePlan,
) -> None:
    if protocol.coverage_plan_version != plan.version:
        raise ValueError("WC2 collection protocol/live plan version mismatch")
    identities = tuple(sorted(context.identity for context in plan.enabled_contexts))
    if protocol.coverage_context_identities != identities:
        raise ValueError("WC2 collection protocol/live contexts mismatch")


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
    source_contract_path: Path | None = None,
    provider_divergence_path: Path | None = None,
    wc2_config: WC2ClockConfig | None = None,
    stream_config: StreamClockConfig | None = None,
    bybit_base_url: str | None = None,
    binance_base_url: str | None = None,
    binance_api_variant: str = "global",
) -> int:
    ledger = ImmutableSignalLedger(db_path)
    candle_store = CandleStore(candle_cache_path)
    source_store = (
        None
        if source_contract_path is None
        else SourceContractStore(source_contract_path)
    )
    failures = 0
    selected_wc2 = wc2_config or WC2ClockConfig()
    selected_stream = stream_config or StreamClockConfig()
    selected_plan = LiveCoveragePlan.current_pilot() if plan is None else plan
    if selected_stream.enabled and not selected_wc2.enabled:
        print(
            "stream status=ERROR error=StreamRequiresWC2 "
            "PRE_NETWORK_FAIL_CLOSED=YES REAL_CAPITAL=0",
            file=sys.stderr,
            flush=True,
        )
        return 1
    try:
        prerequisites = load_wc2_prerequisites(selected_wc2)
        if prerequisites is None:
            wc2_policy = None
            wc2_activation = None
            wc2_protocol = None
            wc2_prepared = None
            wc2_decision = None
            wc2_cohort = None
            wc2_shadow_intent = None
            wc2_shadow_cycle = None
        else:
            wc2_policy, wc2_activation, wc2_protocol = prerequisites
            validate_wc2_collection_plan(wc2_protocol, selected_plan)
            wc2_prepared = WC2PreparedCycleJournal(
                _required_path(selected_wc2.prepared_path, "WC2 prepared")
            )
            wc2_decision = ImmutableDecisionEvidenceLedger(
                _required_path(
                    selected_wc2.decision_evidence_path,
                    "WC2 decision evidence",
                )
            )
            wc2_cohort = WC2CohortJournal(
                _required_path(selected_wc2.cohort_path, "WC2 cohort")
            )
            wc2_shadow_intent = R25ShadowIntentJournal(
                _required_path(
                    selected_wc2.shadow_intent_path,
                    "WC2 shadow intent",
                )
            )
            wc2_shadow_cycle = R25ShadowCycleManifest(
                _required_path(
                    selected_wc2.shadow_cycle_path,
                    "WC2 shadow cycle",
                )
            )
    except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
        print(
            f"wc2 status=ERROR error={type(exc).__name__}:{exc} "
            "PRE_NETWORK_FAIL_CLOSED=YES REAL_CAPITAL=0",
            file=sys.stderr,
            flush=True,
        )
        return 1
    stream_runtime: IntelligenceStreamForwardRuntime | None = None
    stream_family_projector: IntelligenceStreamProductionProjector | None = None
    stream_system_view_runtime: IntelligenceStreamSystemViewRuntime | None = None
    stream_capital_runtime: IntelligenceStreamCapitalForwardRuntime | None = None
    stream_capital_activation_identity: str | None = None
    if selected_stream.enabled:
        assert selected_stream.ledger_path is not None
        local_rewriter = (
            None
            if selected_stream.local_rewrite_config is None
            else OpenAICompatibleLocalNarrativeRewriter(
                selected_stream.local_rewrite_config
            )
        )
        try:
            stream_runtime = IntelligenceStreamForwardRuntime(
                selected_stream.ledger_path,
                rewriter=local_rewriter,
            )
            stream_family_projector = IntelligenceStreamProductionProjector(
                selected_stream.ledger_path,
                rewriter=local_rewriter,
            )
            stream_system_view_runtime = IntelligenceStreamSystemViewRuntime(
                selected_stream.ledger_path
            )
            stream_system_view_runtime.initialize()
            stream_activation_at_ms = time.time_ns() // 1_000_000
            stream_activation = stream_runtime.ensure_activated(
                activated_at_ms=stream_activation_at_ms
            )
            family_projector_ids: list[str] = []
            if selected_stream.market_tape_path is not None:
                family_projector_ids.extend(
                    (
                        "market_geometry_change",
                        "liquidity_change",
                        "order_flow_change",
                        "derivatives_change",
                    )
                )
            family_projector_ids.append("provider_quality_change")
            if selected_stream.event_source_path is not None:
                family_projector_ids.append("event_risk_change")
            for family_projector_id in family_projector_ids:
                stream_family_projector.ensure_family_activation(
                    family_projector_id,
                    activated_at_ms=stream_activation_at_ms,
                )
            if selected_wc2.enabled:
                assert selected_wc2.epoch2_path is not None
                stream_capital_runtime = IntelligenceStreamCapitalForwardRuntime(
                    epoch2_path=selected_wc2.epoch2_path,
                    stream_path=selected_stream.ledger_path,
                )
                stream_capital_activation_identity = (
                    stream_capital_runtime.ensure_activated(
                        activated_at_ms=stream_activation_at_ms,
                    )
                )
        except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
            print(
                "stream status=ERROR "
                f"error={type(exc).__name__}:{exc} "
                "PRE_NETWORK_FAIL_CLOSED=YES HISTORICAL_BACKFILL=NO "
                "REAL_CAPITAL=0",
                file=sys.stderr,
                flush=True,
            )
            return 1
        print(
            "stream status=ACTIVATED "
            f"activation={stream_activation.activation_identity} "
            f"activated_at_ms={stream_activation.activated_at_ms} "
            f"ledger={selected_stream.ledger_path} "
            "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
            flush=True,
        )
        if local_rewriter is None:
            print(
                "stream_rewrite status=DISABLED mode=deterministic "
                "REAL_CAPITAL=0",
                flush=True,
            )
        else:
            print(
                "stream_rewrite status=ENABLED transport=loopback "
                f"rewriter_identity={local_rewriter.rewriter_identity} "
                f"rewriter_version={local_rewriter.rewriter_version} "
                "DETERMINISTIC_FALLBACK=YES REAL_CAPITAL=0",
                flush=True,
            )

        if stream_capital_activation_identity is not None:
            assert selected_wc2.epoch2_path is not None
            print(
                "stream_capital status=ACTIVATED "
                f"activation={stream_capital_activation_identity} "
                f"epoch2={selected_wc2.epoch2_path} "
                f"ledger={selected_stream.ledger_path} "
                "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                flush=True,
            )

    def project_stream_capital(
        issuance: UnifiedDecisionIssuance,
        *,
        event_context: CircuitBreakerAnalysis,
        base_asset: str,
        assessed_at_ms: int,
    ) -> StreamCapitalForwardResult:
        if stream_capital_runtime is None:
            raise RuntimeError("Stream Capital runtime is not activated")
        projection = stream_capital_runtime.project_issuance(
            issuance,
            event_context=event_context,
            base_asset=base_asset,
            assessed_at_ms=assessed_at_ms,
        )
        print(
            "stream_capital status=PROJECTED "
            f"disposition={projection.disposition.value} "
            f"forecast={projection.forecast_identity} "
            f"candidate={projection.allocator_candidate_identity or '-'} "
            f"assessment={projection.allocator_assessment_identity or '-'} "
            f"decisions={len(projection.decision_identities)} "
            f"decision_inserts={projection.inserted_decision_count} "
            f"hold_intents={projection.hold_intent_count} "
            f"messages={projection.projected_message_count} "
            "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
            flush=True,
        )
        return projection

    adapters: dict[Exchange, MarketDataAdapter] = {
        Exchange.BYBIT: BybitSpotAdapter(base_url=bybit_base_url),
        Exchange.BINANCE: BinanceSpotAdapter(
            base_url=binance_base_url,
            api_variant=binance_api_variant,
        ),
    }
    wc2_status_counts: Counter[str] = Counter()
    wc2_reason_counts: Counter[str] = Counter()
    system_view_family_snapshots: list[StreamFamilySnapshot] = []
    system_view_trust_snapshots: list[StreamFamilySnapshot] = []

    for context in selected_plan.enabled_contexts:
        name = context.exchange.value
        adapter = adapters[context.exchange]
        try:
            result = await freeze_coverage_context(
                context=context,
                adapter=adapter,
                ledger=ledger,
                candle_store=candle_store,
                source_store=source_store,
            )
        except (
            LedgerConflictError,
            OSError,
            TypeError,
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

        if stream_family_projector is not None and result.bundle is not None:
            assert result.frozen_at_ms is not None
            try:
                geometry_snapshot = build_geometry_family_snapshot_from_bundle(
                    result.bundle,
                    frozen_at_ms=result.frozen_at_ms,
                )
                system_view_family_snapshots.append(geometry_snapshot)
                geometry_projection = stream_family_projector.project_family(
                    geometry_snapshot,
                    activated_at_ms=result.frozen_at_ms,
                )
            except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
                print(
                    f"stream_family projector=market_geometry_change "
                    f"provider={name} symbol={context.symbol} "
                    f"timeframe={context.timeframe} status=ERROR "
                    f"error={type(exc).__name__}:{exc} "
                    "FAIL_STOP=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                    file=sys.stderr,
                    flush=True,
                )
                return 1
            print(
                f"stream_family projector={geometry_projection.projector_id} "
                f"provider={name} symbol={context.symbol} "
                f"timeframe={context.timeframe} "
                f"status={geometry_projection.disposition.value} "
                f"source={geometry_projection.source_event_identity} "
                f"narrative={geometry_projection.narrative_identity or '-'} "
                "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                flush=True,
            )

        if selected_wc2.enabled:
            assert wc2_policy is not None
            assert wc2_activation is not None
            assert wc2_protocol is not None
            assert wc2_prepared is not None
            assert wc2_decision is not None
            assert wc2_cohort is not None
            assert wc2_shadow_intent is not None
            assert wc2_shadow_cycle is not None
            try:
                wc2_result = process_wc2_prepared_live_freeze(
                    result,
                    context=context,
                    signal_ledger=ledger,
                    policy=wc2_policy,
                    activation=wc2_activation,
                    prepared_journal=wc2_prepared,
                    decision_ledger=wc2_decision,
                    cohort_journal=wc2_cohort,
                    shadow_journal=wc2_shadow_intent,
                    shadow_manifest=wc2_shadow_cycle,
                    observed_at_ms=time.time_ns() // 1_000_000,
                    maximum_issuance_delay_ms=(
                        wc2_protocol.maximum_issuance_delay_ms
                    ),
                    horizon_bars=wc2_protocol.horizon_bars_for(
                        context.timeframe
                    ),
                    base_asset=wc2_base_asset(context.symbol),
                    collection_protocol_identity=(
                        wc2_protocol.protocol_identity
                    ),
                    collection_start_ms=wc2_protocol.collection_start_ms,
                    issuance_hook=(
                        None
                        if stream_runtime is None
                        else stream_runtime.project_issuance
                    ),
                    capital_hook=(
                        None
                        if stream_capital_runtime is None
                        else project_stream_capital
                    ),
                )
            except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
                print(
                    f"wc2 provider={name} symbol={context.symbol} "
                    f"timeframe={context.timeframe} status=ERROR "
                    f"error={type(exc).__name__}:{exc} "
                    "FAIL_STOP=YES REAL_CAPITAL=0",
                    file=sys.stderr,
                    flush=True,
                )
                return 1

            reason_codes = tuple(
                sorted(set(getattr(wc2_result, "reason_codes", ())))
            )
            wc2_status_counts[wc2_result.status.value] += 1
            wc2_reason_counts.update(reason_codes)
            reasons_text = ",".join(reason_codes) if reason_codes else "-"
            print(
                f"wc2 provider={name} symbol={context.symbol} "
                f"timeframe={context.timeframe} "
                f"status={wc2_result.status.value} "
                f"reasons={reasons_text} "
                f"receipt={wc2_result.receipt_identity or '-'} "
                f"forecast={wc2_result.forecast_identity or '-'} "
                f"cohort={wc2_result.cohort_forecast_identity or '-'} "
                f"intent={wc2_result.paper_intent_identity or '-'} "
                f"protocol={wc2_protocol.protocol_identity} "
                f"collection_start_ms={wc2_protocol.collection_start_ms} "
                "HISTORICAL_FORECAST_BACKFILL=NO REAL_CAPITAL=0",
                flush=True,
            )
            if wc2_result.status is WC2PreparedLiveStatus.NO_PREPARED_RECEIPT:
                failures += 1
                print(
                    f"wc2 provider={name} symbol={context.symbol} "
                    f"timeframe={context.timeframe} "
                    "status=EVIDENCE_GAP FAIL_STOP=YES CYCLE_CONTINUES=YES "
                    "HISTORICAL_FORECAST_BACKFILL=NO REAL_CAPITAL=0",
                    file=sys.stderr,
                    flush=True,
                )
                continue

    if selected_wc2.enabled:
        status_summary = ",".join(
            f"{key}:{value}" for key, value in sorted(wc2_status_counts.items())
        ) or "-"
        reason_summary = ",".join(
            f"{key}:{value}" for key, value in sorted(wc2_reason_counts.items())
        ) or "-"
        print(
            "wc2_liveness status=SUMMARY "
            f"contexts={sum(wc2_status_counts.values())} "
            f"status_counts={status_summary} "
            f"reason_counts={reason_summary} "
            "POLICY_UNCHANGED=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
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
            f"error={type(exc).__name__}:{exc} "
            "F4_TRUST_SOURCE_DEGRADED=YES REAL_CAPITAL=0",
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

    if stream_family_projector is not None:
        trust_observed_at_ms = time.time_ns() // 1_000_000
        try:
            trust_snapshots = list(
                build_provider_quality_stream_snapshots(
                    selected_divergence_path,
                    evaluated_at_ms=trust_observed_at_ms,
                )
            )
            if selected_stream.event_source_path is not None:
                trust_snapshots.extend(
                    build_event_risk_stream_snapshots(
                        selected_stream.event_source_path,
                        evaluated_at_ms=trust_observed_at_ms,
                    )
                )
            system_view_trust_snapshots.extend(trust_snapshots)
            trust_dispositions: Counter[str] = Counter()
            trust_projectors: Counter[str] = Counter()
            for trust_snapshot in sorted(
                trust_snapshots,
                key=lambda item: (
                    item.projector_id,
                    item.source_scope,
                    item.source_event_identity,
                ),
            ):
                silent_initial_states = (
                    ("healthy",)
                    if trust_snapshot.projector_id == "provider_quality_change"
                    else ("clear",)
                    if trust_snapshot.projector_id == "event_risk_change"
                    else ()
                )
                trust_projection = stream_family_projector.project_family(
                    trust_snapshot,
                    activated_at_ms=trust_observed_at_ms,
                    silent_initial_state_labels=silent_initial_states,
                )
                trust_dispositions[
                    trust_projection.disposition.value
                ] += 1
                trust_projectors[trust_projection.projector_id] += 1
                print(
                    "stream_trust "
                    f"projector={trust_projection.projector_id} "
                    f"symbol={trust_snapshot.symbol} "
                    f"timeframe={trust_snapshot.timeframe} "
                    f"state={trust_snapshot.state_label} "
                    f"status={trust_projection.disposition.value} "
                    f"source={trust_projection.source_event_identity} "
                    f"narrative={trust_projection.narrative_identity or '-'} "
                    "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                    flush=True,
                )
        except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
            print(
                "stream_trust status=ERROR "
                f"error={type(exc).__name__}:{exc} "
                "FAIL_STOP=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                file=sys.stderr,
                flush=True,
            )
            return 1
        trust_projector_summary = ",".join(
            f"{key}:{value}"
            for key, value in sorted(trust_projectors.items())
        ) or "-"
        trust_disposition_summary = ",".join(
            f"{key}:{value}"
            for key, value in sorted(trust_dispositions.items())
        ) or "-"
        print(
            "stream_trust status=SUMMARY "
            f"snapshots={len(trust_snapshots)} "
            f"projectors={trust_projector_summary} "
            f"dispositions={trust_disposition_summary} "
            "CONSENSUS_NOT_INFERRED=YES "
            "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
            flush=True,
        )

    if (
        stream_family_projector is not None
        and selected_stream.market_tape_path is not None
    ):
        try:
            geometry_activation_ms = stream_family_projector.family_activation_ms(
                "market_geometry_change"
            )
            lifecycle_dispositions: Counter[str] = Counter()
            lifecycle_transition_n = 0
            for lifecycle_record in ledger.list_lifecycle_evaluations():
                if lifecycle_record.appended_at_ms < geometry_activation_ms:
                    continue
                freeze_record = ledger.read_freeze_by_signal(
                    lifecycle_record.signal_freeze_identity
                )
                if freeze_record is None:
                    raise ValueError(
                        "Stream lifecycle projection lost parent signal freeze"
                    )
                lifecycle_snapshot = build_geometry_lifecycle_family_snapshot(
                    freeze_record,
                    lifecycle_record,
                )
                if lifecycle_snapshot is None:
                    continue
                lifecycle_transition_n += 1
                lifecycle_projection = stream_family_projector.project_family(
                    lifecycle_snapshot,
                    activated_at_ms=geometry_activation_ms,
                )
                lifecycle_dispositions[
                    lifecycle_projection.disposition.value
                ] += 1
                print(
                    "stream_family projector=market_geometry_change "
                    f"symbol={lifecycle_snapshot.symbol} "
                    f"timeframe={lifecycle_snapshot.timeframe} "
                    f"state={lifecycle_snapshot.state_label} "
                    f"status={lifecycle_projection.disposition.value} "
                    f"source={lifecycle_projection.source_event_identity} "
                    f"narrative={lifecycle_projection.narrative_identity or '-'} "
                    "LIFECYCLE_TRANSITION=YES "
                    "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                    flush=True,
                )
        except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
            print(
                "stream_family lifecycle_status=ERROR "
                f"error={type(exc).__name__}:{exc} "
                "FAIL_STOP=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                file=sys.stderr,
                flush=True,
            )
            return 1
        lifecycle_summary = ",".join(
            f"{key}:{value}"
            for key, value in sorted(lifecycle_dispositions.items())
        ) or "-"
        print(
            "stream_family lifecycle_status=SUMMARY "
            f"transitions={lifecycle_transition_n} "
            f"dispositions={lifecycle_summary} "
            f"activation_ms={geometry_activation_ms} "
            "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
            flush=True,
        )

    if (
        stream_family_projector is not None
        and selected_stream.market_tape_path is not None
    ):
        market_tape_path = selected_stream.market_tape_path
        if not market_tape_path.is_file():
            print(
                "stream_family status=ERROR "
                f"error=MarketTapeMissing:{market_tape_path} "
                "FAIL_STOP=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                file=sys.stderr,
                flush=True,
            )
            return 1
        family_observed_at_ms = time.time_ns() // 1_000_000
        try:
            family_snapshots = build_market_tape_family_snapshots(
                market_tape_path,
                symbols=selected_stream.family_symbols,
                as_of_ms=family_observed_at_ms,
                candle_cache_path=candle_cache_path,
            )
            system_view_family_snapshots.extend(family_snapshots)
            family_dispositions: Counter[str] = Counter()
            family_projectors: Counter[str] = Counter()
            for family_snapshot in family_snapshots:
                family_projection = stream_family_projector.project_family(
                    family_snapshot,
                    activated_at_ms=family_observed_at_ms,
                )
                family_dispositions[
                    family_projection.disposition.value
                ] += 1
                family_projectors[family_projection.projector_id] += 1
                print(
                    f"stream_family projector={family_projection.projector_id} "
                    f"symbol={family_snapshot.symbol} "
                    f"timeframe={family_snapshot.timeframe} "
                    f"state={family_snapshot.state_label} "
                    f"status={family_projection.disposition.value} "
                    f"source={family_projection.source_event_identity} "
                    f"narrative={family_projection.narrative_identity or '-'} "
                    "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                    flush=True,
                )
        except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
            print(
                "stream_family status=ERROR "
                f"error={type(exc).__name__}:{exc} "
                "FAIL_STOP=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                file=sys.stderr,
                flush=True,
            )
            return 1
        projector_summary = ",".join(
            f"{key}:{value}"
            for key, value in sorted(family_projectors.items())
        ) or "-"
        disposition_summary = ",".join(
            f"{key}:{value}"
            for key, value in sorted(family_dispositions.items())
        ) or "-"
        print(
            "stream_family status=SUMMARY "
            f"snapshots={len(family_snapshots)} "
            f"projectors={projector_summary} "
            f"dispositions={disposition_summary} "
            "ONCHAIN_STANDALONE=DEFERRED_SOURCE "
            "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
            flush=True,
        )


    if stream_system_view_runtime is not None and system_view_family_snapshots:
        system_view_event_at_ms = time.time_ns() // 1_000_000
        try:
            for system_view_symbol in selected_stream.family_symbols:
                if not any(
                    item.symbol == system_view_symbol
                    for item in system_view_family_snapshots
                ):
                    continue
                system_view_result = stream_system_view_runtime.compose_and_append(
                    symbol=system_view_symbol,
                    event_at_ms=system_view_event_at_ms,
                    family_snapshots=tuple(system_view_family_snapshots),
                    trust_snapshots=tuple(system_view_trust_snapshots),
                )
                print(
                    "stream_system_view "
                    f"symbol={system_view_result.symbol} "
                    f"stance={system_view_result.stance} "
                    f"status={system_view_result.disposition.value} "
                    f"semantic={system_view_result.semantic_identity} "
                    f"narrative={system_view_result.narrative_identity or '-'} "
                    "FORECAST_AUTHORITY=NO PROBABILITY=NO "
                    "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                    flush=True,
                )
        except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
            print(
                "stream_system_view status=ERROR "
                f"error={type(exc).__name__}:{exc} "
                "FAIL_STOP=YES FORECAST_AUTHORITY=NO "
                "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                file=sys.stderr,
                flush=True,
            )
            return 1

    if selected_wc2.enabled:
        assert wc2_decision is not None
        assert wc2_cohort is not None
        try:
            outcome_cycle = resolve_wc2_outcomes_once(
                signal_ledger=ledger,
                candle_store=candle_store,
                decision_ledger=wc2_decision,
                cohort_journal=wc2_cohort,
                observed_at_ms=time.time_ns() // 1_000_000,
                resolution_hook=(
                    None
                    if stream_runtime is None
                    else stream_runtime.project_resolution
                ),
            )
        except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
            print(
                "wc2_outcomes status=ERROR "
                f"error={type(exc).__name__}:{exc} "
                "FAIL_STOP=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                file=sys.stderr,
                flush=True,
            )
            return 1
        print(
            "wc2_outcomes status=COMPLETE "
            f"scanned={outcome_cycle.scanned} "
            f"pending={outcome_cycle.pending} "
            f"resolved_fresh={outcome_cycle.resolved_fresh} "
            f"recovered={outcome_cycle.recovered} "
            f"cohort_idempotent={outcome_cycle.cohort_idempotent} "
            "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
            flush=True,
        )

    if selected_wc2.execution_enabled:
        assert selected_wc2.decision_evidence_path is not None
        assert selected_wc2.cohort_path is not None
        assert selected_wc2.epoch2_path is not None
        assert selected_wc2.execution_protocol_path is not None
        assert selected_wc2.execution_runtime_path is not None
        assert selected_wc2.execution_journal_path is not None
        assert selected_wc2.venue_rule_store_path is not None
        try:
            execution_cycle = process_wc2_paper_execution_cycle(
                signal_ledger_path=db_path,
                decision_evidence_path=selected_wc2.decision_evidence_path,
                cohort_journal_path=selected_wc2.cohort_path,
                epoch2_path=selected_wc2.epoch2_path,
                execution_protocol_path=selected_wc2.execution_protocol_path,
                runtime_activation_path=selected_wc2.execution_runtime_path,
                execution_journal_path=selected_wc2.execution_journal_path,
                candle_cache_path=candle_cache_path,
                venue_rule_store_path=selected_wc2.venue_rule_store_path,
                observed_at_ms=time.time_ns() // 1_000_000,
            )
        except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
            print(
                "wc2_execution status=ERROR "
                f"error={type(exc).__name__}:{exc} "
                "FAIL_STOP=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
                file=sys.stderr,
                flush=True,
            )
            return 1
        print(
            "wc2_execution status=COMPLETE "
            f"scanned_pair_n={execution_cycle.scanned_pair_n} "
            f"eligible_event_n={execution_cycle.eligible_event_n} "
            f"already_terminal_n={execution_cycle.already_terminal_n} "
            f"expired_gap_n={execution_cycle.expired_gap_n} "
            f"waiting_lineage_n={execution_cycle.waiting_lineage_n} "
            f"waiting_execution_input_n={execution_cycle.waiting_execution_input_n} "
            f"waiting_venue_rules_n={execution_cycle.waiting_venue_rules_n} "
            f"hold_cash_n={execution_cycle.hold_cash_n} "
            f"sizing_rejected_n={execution_cycle.sizing_rejected_n} "
            f"pretrade_rejected_n={execution_cycle.pretrade_rejected_n} "
            f"executed_n={execution_cycle.executed_n} "
            f"appended_n={len(execution_cycle.appended_record_identities)} "
            "PERSISTENT_SINGLE_OWNER=YES "
            "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
            flush=True,
        )


    return 1 if failures else 0


def _required_path(path: Path | None, label: str) -> Path:
    if path is None:
        raise ValueError(f"{label} path is required")
    return path


def live_clock_lock_path(db_path: Path) -> Path:
    return db_path.with_name("live_clock.lock")


def main() -> int:
    args = parse_args()
    try:
        wc2_config = build_wc2_clock_config(args)
        stream_config = build_stream_clock_config(args, environ=os.environ)
    except ValueError as exc:
        print(f"LIVE_CLOCK_CONFIG_ERROR={exc}", file=sys.stderr, flush=True)
        return 2
    lock_path = live_clock_lock_path(args.db)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_handle:
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
                source_contract_path=args.source_contract,
                provider_divergence_path=args.provider_divergence,
                wc2_config=wc2_config,
                stream_config=stream_config,
                bybit_base_url=args.bybit_base_url,
                binance_base_url=args.binance_base_url,
                binance_api_variant=args.binance_api_variant,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
