from __future__ import annotations

import json
from pathlib import Path

from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.data.store import CandleStore
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.intelligence.derivatives_context import (
    DerivativesContextLabel,
    build_derivatives_context_evidence_freeze,
)
from crypto_signal.intelligence.liquidity_dynamics import (
    build_liquidity_dynamics_evidence_freeze,
)
from crypto_signal.intelligence.liquidity_structure import (
    LiquidityLevelCandidate,
    build_liquidity_structure_evidence_freeze,
)
from crypto_signal.intelligence.liquidity_sweep import (
    build_liquidity_sweep_evidence_freeze,
)
from crypto_signal.intelligence.order_flow_microstructure import (
    OrderFlowMicrostructureLabel,
    build_order_flow_microstructure_evidence_freeze,
)
from crypto_signal.intelligence.order_flow_patterns import (
    PatternStatus,
    build_absorption_freeze,
    build_price_cvd_divergence_freeze,
)
from crypto_signal.intelligence.temporal_order_flow import (
    TemporalFlowStatus,
    build_temporal_order_flow_freeze,
)
from crypto_signal.ledger.bundle import DecisionFreezeBundle
from crypto_signal.ledger.deserialization import (
    parse_lifecycle_evaluation,
    parse_signal_decision,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.ledger.store import (
    FreezeRecord,
    LifecycleRecord,
    lifecycle_evaluation_identity,
)
from crypto_signal.product.intelligence_stream_family import (
    StreamFamilySnapshot,
    build_family_snapshot,
)
from crypto_signal.product.intelligence_stream_models import (
    StreamCategory,
    StreamImportance,
)
from crypto_signal.signals.models import SignalDecision


def build_geometry_family_snapshot(
    freeze: FreezeRecord,
) -> StreamFamilySnapshot:
    raw = json.loads(freeze.bundle_json)
    if not isinstance(raw, dict):
        raise TypeError("Stream geometry freeze bundle must decode to object")
    signal = parse_signal_decision(raw.get("signal_decision"))
    actual = (
        signal.freeze_identity,
        signal.exchange.value,
        signal.market_type.value,
        signal.symbol,
        signal.timeframe,
        signal.as_of_ms,
        signal.state.value,
        signal.direction.value,
    )
    expected = (
        freeze.signal_freeze_identity,
        freeze.exchange,
        freeze.market_type,
        freeze.symbol,
        freeze.timeframe,
        freeze.as_of_ms,
        freeze.signal_state,
        freeze.direction,
    )
    if actual != expected:
        raise ValueError("Stream geometry freeze row/bundle mismatch")
    return _build_geometry_snapshot(
        _bundle_identity=freeze.bundle_identity,
        bundle_signal=signal,
        frozen_at_ms=freeze.frozen_at_ms,
    )


def build_geometry_family_snapshot_from_bundle(
    bundle: DecisionFreezeBundle,
    *,
    frozen_at_ms: int,
) -> StreamFamilySnapshot:
    return _build_geometry_snapshot(
        _bundle_identity=bundle.bundle_identity,
        bundle_signal=bundle.signal_decision,
        frozen_at_ms=frozen_at_ms,
    )


def _build_geometry_snapshot(
    *,
    _bundle_identity: str,
    bundle_signal: SignalDecision,
    frozen_at_ms: int,
) -> StreamFamilySnapshot:
    signal = bundle_signal
    if frozen_at_ms < signal.as_of_ms:
        raise ValueError("Stream geometry freeze time predates signal as-of")

    geometry = signal.geometry
    components: list[tuple[str, str]] = [
        ("direction", signal.direction.value),
        ("geometry_present", "yes" if geometry is not None else "no"),
        ("setup_type", signal.setup_type),
        ("signal_state", signal.state.value),
    ]
    evidence = {
        _bundle_identity,
        signal.freeze_identity,
    }
    for index, source_reference in enumerate(
        signal.selected_evidence_ids,
        start=1,
    ):
        if _is_sha256(source_reference):
            evidence.add(source_reference)
        else:
            components.append(
                (
                    f"source_reference_{index:02d}",
                    source_reference,
                )
            )
    if geometry is not None:
        components.extend(
            (
                ("entry_reference_price", str(geometry.entry_reference_price)),
                ("entry_zone_high", str(geometry.entry_zone.high)),
                ("entry_zone_low", str(geometry.entry_zone.low)),
                ("geometry_methodology", geometry.source_methodology.value),
                ("invalidation_price", str(geometry.invalidation_price)),
                ("invalidation_trigger", geometry.invalidation_trigger.value),
                ("target_count", str(len(geometry.targets))),
            )
        )
        components.extend(
            (
                f"target_{index:02d}_{target.label}_price",
                str(target.target_price),
            )
            for index, target in enumerate(geometry.targets, start=1)
        )
        components.extend(
            (
                f"target_{index:02d}_{target.label}_rr",
                str(target.reference_rr),
            )
            for index, target in enumerate(geometry.targets, start=1)
        )
        if _is_sha256(geometry.source_evidence_id):
            evidence.add(geometry.source_evidence_id)
        else:
            components.append(
                ("geometry_source_reference", geometry.source_evidence_id)
            )
    state_label = (
        f"{signal.state.value}:{signal.direction.value}:"
        f"{'geometry' if geometry is not None else 'no_geometry'}"
    )
    return build_family_snapshot(
        projector_id="market_geometry_change",
        family=ConfluenceFamily.GEOMETRY,
        category=StreamCategory.MARKET,
        subtype="geometry_material_change",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=signal.freeze_identity,
        source_scope=(
            f"{signal.exchange.value}:{signal.market_type.value}:signal_geometry"
        ),
        asset=_base_asset(signal.symbol),
        symbol=signal.symbol,
        market=signal.symbol,
        timeframe=signal.timeframe,
        event_at_ms=frozen_at_ms,
        source_as_of_ms=signal.as_of_ms,
        evidence_identities=tuple(sorted(evidence)),
        evidence_domains=("frozen_chart", "geometry"),
        state_label=state_label,
        state_components=tuple(components),
        direction=signal.direction.value,
        source_quality="exact_immutable_signal_freeze",
        uncertainty_flags=signal.uncertainty_flags,
    )


def build_geometry_lifecycle_family_snapshot(
    freeze: FreezeRecord,
    lifecycle: LifecycleRecord,
) -> StreamFamilySnapshot | None:
    if lifecycle.signal_freeze_identity != freeze.signal_freeze_identity:
        raise ValueError("Stream lifecycle/freeze identity mismatch")
    raw = json.loads(freeze.bundle_json)
    if not isinstance(raw, dict):
        raise TypeError("Stream lifecycle freeze bundle must decode to object")
    signal = parse_signal_decision(raw.get("signal_decision"))

    evaluation_raw = json.loads(lifecycle.evaluation_json)
    evaluation = parse_lifecycle_evaluation(evaluation_raw)
    if lifecycle_evaluation_identity(evaluation) != lifecycle.evaluation_identity:
        raise ValueError("Stream lifecycle evaluation identity mismatch")
    if evaluation.signal_freeze_identity != signal.freeze_identity:
        raise ValueError("Stream lifecycle parent signal mismatch")
    if evaluation.evaluated_as_of_ms != lifecycle.evaluated_as_of_ms:
        raise ValueError("Stream lifecycle evaluated-as-of mismatch")
    if evaluation.current_state.value != lifecycle.current_state:
        raise ValueError("Stream lifecycle current-state mismatch")
    if evaluation.status.value != lifecycle.status:
        raise ValueError("Stream lifecycle status mismatch")
    transition = evaluation.transition
    if transition is None:
        return None
    if transition.signal_freeze_identity != signal.freeze_identity:
        raise ValueError("Stream lifecycle transition parent mismatch")
    if lifecycle.appended_at_ms < evaluation.evaluated_as_of_ms:
        raise ValueError("Stream lifecycle append predates evaluation")

    uncertainty = set(signal.uncertainty_flags)
    if not transition.first_trigger_candle_certain:
        uncertainty.add("first_trigger_candle_uncertain")
    trigger = "|".join(str(item) for item in transition.trigger_candle_identity)
    return build_family_snapshot(
        projector_id="market_geometry_change",
        family=ConfluenceFamily.GEOMETRY,
        category=StreamCategory.MARKET,
        subtype="trigger_transition",
        importance=StreamImportance.IMPORTANT,
        source_event_identity=lifecycle.evaluation_identity,
        source_scope=(
            f"{signal.exchange.value}:{signal.market_type.value}:signal_geometry"
        ),
        asset=_base_asset(signal.symbol),
        symbol=signal.symbol,
        market=signal.symbol,
        timeframe=signal.timeframe,
        event_at_ms=lifecycle.appended_at_ms,
        source_as_of_ms=evaluation.evaluated_as_of_ms,
        evidence_identities=(
            lifecycle.evaluation_identity,
            signal.freeze_identity,
            transition.transition_identity,
        ),
        evidence_domains=("frozen_chart", "geometry", "signal_lifecycle"),
        state_label=(
            f"{transition.to_state.value}:{transition.reason.value}"
        ),
        state_components=(
            ("first_trigger_candle_certain", str(transition.first_trigger_candle_certain).lower()),
            ("from_state", transition.from_state.value),
            ("lifecycle_reason", transition.reason.value),
            ("to_state", transition.to_state.value),
            ("trigger_candle_identity", trigger),
        ),
        direction=signal.direction.value,
        source_quality="exact_immutable_lifecycle_evaluation",
        uncertainty_flags=tuple(sorted(uncertainty)),
    )

def build_market_tape_family_snapshots(
    market_tape_path: Path,
    *,
    symbols: tuple[str, ...],
    as_of_ms: int,
    candle_cache_path: Path | None = None,
) -> tuple[StreamFamilySnapshot, ...]:
    store = MarketTapeStore(market_tape_path)
    candle_store = (
        None
        if candle_cache_path is None
        else CandleStore(candle_cache_path)
    )
    snapshots: list[StreamFamilySnapshot] = []
    for symbol in tuple(sorted({value.upper() for value in symbols})):
        orderbooks = store.recent_orderbooks(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol=symbol,
            limit=180,
        )
        trades = store.recent_trades(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol=symbol,
            limit=1200,
        )

        if orderbooks:
            liquidity = build_liquidity_dynamics_evidence_freeze(
                orderbooks,
                as_of_ms=as_of_ms,
            )
            structure = build_liquidity_structure_evidence_freeze(
                orderbooks,
                as_of_ms=as_of_ms,
            )
            sweep = build_liquidity_sweep_evidence_freeze(
                orderbooks,
                trades,
                as_of_ms=as_of_ms,
            )
            liquidity_analysis = liquidity.analysis
            structure_analysis = structure.analysis
            sweep_analysis = sweep.analysis
            liquidity_evidence = {
                liquidity.freeze_identity,
                liquidity_analysis.evidence_identity,
                structure.freeze_identity,
                structure_analysis.evidence_identity,
                sweep.freeze_identity,
                sweep_analysis.evidence_identity,
                *(item.snapshot_identity for item in liquidity.snapshots),
                *(item.snapshot_identity for item in structure.snapshots),
                *(item.snapshot_identity for item in sweep.snapshots),
                *(item.trade_identity for item in sweep.trades),
            }
            if sweep_analysis.structure_evidence_identity is not None:
                liquidity_evidence.add(
                    sweep_analysis.structure_evidence_identity
                )
            if sweep_analysis.structure_freeze_identity is not None:
                liquidity_evidence.add(
                    sweep_analysis.structure_freeze_identity
                )

            rich_levels = (
                *structure_analysis.bid_levels,
                *structure_analysis.ask_levels,
            )
            persistent_pool_count = sum(
                LiquidityLevelCandidate.PERSISTENT_POOL in item.candidates
                for item in rich_levels
            )
            spoofing_candidate_count = sum(
                LiquidityLevelCandidate.SPOOFING in item.candidates
                for item in rich_levels
            )
            hidden_liquidity_candidate_count = sum(
                LiquidityLevelCandidate.HIDDEN_LIQUIDITY
                in item.candidates
                for item in rich_levels
            )
            liquidity_source_event_identity = canonical_sha256(
                {
                    "as_of_ms": as_of_ms,
                    "dynamics_freeze_identity": liquidity.freeze_identity,
                    "structure_freeze_identity": structure.freeze_identity,
                    "sweep_freeze_identity": sweep.freeze_identity,
                    "symbol": symbol,
                    "version": "rdp4-rich-liquidity-family-v1/1",
                }
            )
            liquidity_quality = _rich_liquidity_quality(
                liquidity_analysis.source_quality.value,
                structure_analysis.source_quality.value,
                sweep_analysis.source_quality.value,
            )
            liquidity_uncertainty = tuple(
                sorted(
                    {
                        *liquidity_analysis.uncertainty_flags,
                        *structure_analysis.uncertainty_flags,
                        *sweep_analysis.uncertainty_flags,
                        *(
                            flag
                            for level in rich_levels
                            for flag in level.uncertainty_flags
                        ),
                        *(
                            flag
                            for candidate in sweep_analysis.candidates
                            for flag in candidate.uncertainty_flags
                        ),
                    }
                )
            )
            liquidity_domains = {
                "liquidity",
                "liquidity_structure",
                "liquidity_sweep",
                "order_book",
            }
            if sweep.trades:
                liquidity_domains.add("public_trades")
            snapshots.append(
                build_family_snapshot(
                    projector_id="liquidity_change",
                    family=ConfluenceFamily.LIQUIDITY,
                    category=StreamCategory.INTELLIGENCE,
                    subtype="liquidity_material_change",
                    importance=StreamImportance.IMPORTANT,
                    source_event_identity=liquidity_source_event_identity,
                    source_scope="bybit:spot:market_tape_liquidity",
                    asset=_base_asset(symbol),
                    symbol=symbol,
                    market=symbol,
                    timeframe="microstructure",
                    event_at_ms=as_of_ms,
                    source_as_of_ms=as_of_ms,
                    evidence_identities=tuple(sorted(liquidity_evidence)),
                    evidence_domains=tuple(sorted(liquidity_domains)),
                    state_label=(
                        f"{liquidity_analysis.status.value}:"
                        f"{liquidity_analysis.liquidity_take_candidate.value}:"
                        f"{structure_analysis.status.value}:"
                        f"{sweep_analysis.sweep_state.value}"
                    ),
                    state_components=(
                        (
                            "hidden_liquidity_candidate_count",
                            str(hidden_liquidity_candidate_count),
                        ),
                        (
                            "liquidity_take_candidate",
                            liquidity_analysis.liquidity_take_candidate.value,
                        ),
                        (
                            "persistent_pool_candidate_count",
                            str(persistent_pool_count),
                        ),
                        (
                            "spoofing_candidate_count",
                            str(spoofing_candidate_count),
                        ),
                        (
                            "structure_status",
                            structure_analysis.status.value,
                        ),
                        (
                            "sweep_candidate_count",
                            str(len(sweep_analysis.candidates)),
                        ),
                        ("sweep_state", sweep_analysis.sweep_state.value),
                        ("sweep_status", sweep_analysis.status.value),
                        ("status", liquidity_analysis.status.value),
                    ),
                    direction=None,
                    source_quality=liquidity_quality,
                    uncertainty_flags=liquidity_uncertainty,
                )
            )

        if orderbooks or trades:
            order_flow = build_order_flow_microstructure_evidence_freeze(
                orderbooks,
                trades,
                as_of_ms=as_of_ms,
            )
            order_flow_analysis = order_flow.analysis
            temporal = (
                None
                if not trades
                else build_temporal_order_flow_freeze(
                    trades,
                    as_of_ms=as_of_ms,
                )
            )
            temporal_analysis = None if temporal is None else temporal.analysis
            order_flow_evidence = {
                order_flow.freeze_identity,
                order_flow_analysis.evidence_identity,
                *(item.trade_identity for item in order_flow.trades),
            }
            if order_flow.orderbook is not None:
                order_flow_evidence.add(
                    order_flow.orderbook.snapshot_identity
                )
            temporal_components: list[tuple[str, str]] = []
            temporal_uncertainty: tuple[str, ...] = ()
            temporal_freeze_identity: str | None = None
            temporal_status = "unavailable"
            temporal_quality = "unavailable"
            if temporal is not None:
                temporal_freeze_identity = temporal.freeze_identity
                temporal_analysis = temporal.analysis
                temporal_status = temporal_analysis.status.value
                temporal_quality = temporal_analysis.quality.value
                order_flow_evidence.update(
                    {
                        temporal.freeze_identity,
                        temporal_analysis.evidence_identity,
                        *(item.trade_identity for item in temporal.trades),
                    }
                )
                temporal_uncertainty = temporal_analysis.uncertainty_flags
                metrics = temporal_analysis.metrics
                if metrics is not None:
                    temporal_components.extend(
                        (
                            (
                                "cvd_window_end_notional",
                                str(metrics.cvd_window_end_notional),
                            ),
                            ("delta_notional", str(metrics.delta_notional)),
                            (
                                "large_buy_candidate_count",
                                str(metrics.large_buy_count),
                            ),
                            (
                                "large_sell_candidate_count",
                                str(metrics.large_sell_count),
                            ),
                            (
                                "taker_imbalance",
                                str(metrics.taker_imbalance),
                            ),
                            (
                                "trade_velocity_per_second",
                                str(metrics.trade_velocity_per_second),
                            ),
                        )
                    )

            pattern_components: list[tuple[str, str]] = []
            pattern_uncertainty: set[str] = set()
            absorption = None
            divergence = None
            if temporal is not None and orderbooks:
                structure_for_order_flow = (
                    build_liquidity_structure_evidence_freeze(
                        orderbooks,
                        as_of_ms=as_of_ms,
                    )
                )
                absorption = build_absorption_freeze(
                    temporal,
                    structure_for_order_flow,
                    as_of_ms=as_of_ms,
                )
                absorption_analysis = absorption.analysis
                order_flow_evidence.update(
                    {
                        absorption.freeze_identity,
                        absorption_analysis.evidence_identity,
                        structure_for_order_flow.freeze_identity,
                        structure_for_order_flow.analysis.evidence_identity,
                    }
                )
                pattern_uncertainty.update(
                    absorption_analysis.uncertainty_flags
                )
                pattern_components.extend(
                    (
                        (
                            "absorption_candidate_count",
                            str(len(absorption_analysis.candidates)),
                        ),
                        (
                            "absorption_overlap_end_ms",
                            (
                                "-"
                                if absorption_analysis.overlap_end_ms is None
                                else str(absorption_analysis.overlap_end_ms)
                            ),
                        ),
                        (
                            "absorption_overlap_start_ms",
                            (
                                "-"
                                if absorption_analysis.overlap_start_ms is None
                                else str(absorption_analysis.overlap_start_ms)
                            ),
                        ),
                        (
                            "absorption_status",
                            absorption_analysis.status.value,
                        ),
                    )
                )

                if candle_store is not None:
                    candles = candle_store.list_candles_read_only(
                        exchange=Exchange.BYBIT,
                        market_type=MarketType.SPOT,
                        symbol=symbol,
                        timeframe="15m",
                    )
                    if candles:
                        divergence = build_price_cvd_divergence_freeze(
                            candles,
                            temporal,
                            as_of_ms=as_of_ms,
                        )
                        divergence_analysis = divergence.analysis
                        order_flow_evidence.update(
                            {
                                divergence.freeze_identity,
                                divergence_analysis.evidence_identity,
                            }
                        )
                        pattern_uncertainty.update(
                            divergence_analysis.uncertainty_flags
                        )
                        pattern_components.extend(
                            (
                                (
                                    "price_cvd_divergence_candidate_count",
                                    str(
                                        len(
                                            divergence_analysis.candidates
                                        )
                                    ),
                                ),
                                (
                                    "price_cvd_divergence_consumed_candle_count",
                                    str(
                                        divergence_analysis.consumed_candle_count
                                    ),
                                ),
                                (
                                    "price_cvd_divergence_status",
                                    divergence_analysis.status.value,
                                ),
                                (
                                    "price_cvd_divergence_timeframe",
                                    divergence_analysis.timeframe,
                                ),
                            )
                        )

            order_flow_direction = None
            if (
                order_flow_analysis.label
                is OrderFlowMicrostructureLabel.BUY_PRESSURE
            ):
                order_flow_direction = "buy_pressure"
            elif (
                order_flow_analysis.label
                is OrderFlowMicrostructureLabel.SELL_PRESSURE
            ):
                order_flow_direction = "sell_pressure"

            order_flow_domains = {"order_flow"}
            if order_flow.orderbook is not None:
                order_flow_domains.add("order_book")
            if order_flow.trades:
                order_flow_domains.add("public_trades")
            if temporal is not None:
                order_flow_domains.update(
                    {"temporal_order_flow", "window_local_cvd"}
                )
            if absorption is not None:
                order_flow_domains.add("absorption")
            if divergence is not None:
                order_flow_domains.update(
                    {"candle_15m", "price_cvd_divergence"}
                )

            order_flow_source_event_identity = canonical_sha256(
                {
                    "absorption_freeze_identity": (
                        None
                        if absorption is None
                        else absorption.freeze_identity
                    ),
                    "as_of_ms": as_of_ms,
                    "microstructure_freeze_identity": (
                        order_flow.freeze_identity
                    ),
                    "price_cvd_divergence_freeze_identity": (
                        None
                        if divergence is None
                        else divergence.freeze_identity
                    ),
                    "symbol": symbol,
                    "temporal_flow_freeze_identity": (
                        temporal_freeze_identity
                    ),
                    "version": "rdp4-rich-order-flow-family-v2/1",
                }
            )
            microstructure_measured = (
                order_flow_analysis.label
                is not OrderFlowMicrostructureLabel.UNRESOLVED
            )
            temporal_measured = (
                temporal_analysis is not None
                and temporal_analysis.status is TemporalFlowStatus.MEASURED
            )
            snapshots.append(
                build_family_snapshot(
                    projector_id="order_flow_change",
                    family=ConfluenceFamily.ORDER_FLOW,
                    category=StreamCategory.INTELLIGENCE,
                    subtype="order_flow_material_change",
                    importance=StreamImportance.IMPORTANT,
                    source_event_identity=order_flow_source_event_identity,
                    source_scope="bybit:spot:market_tape_order_flow",
                    asset=_base_asset(symbol),
                    symbol=symbol,
                    market=symbol,
                    timeframe="microstructure",
                    event_at_ms=as_of_ms,
                    source_as_of_ms=as_of_ms,
                    evidence_identities=tuple(sorted(order_flow_evidence)),
                    evidence_domains=tuple(sorted(order_flow_domains)),
                    state_label=(
                        f"{order_flow_analysis.label.value}:"
                        f"{temporal_status}"
                    ),
                    state_components=(
                        ("book_pressure", order_flow_analysis.book_pressure.value),
                        ("label", order_flow_analysis.label.value),
                        ("taker_flow", order_flow_analysis.taker_flow.value),
                        ("temporal_quality", temporal_quality),
                        ("temporal_status", temporal_status),
                        *temporal_components,
                        *pattern_components,
                    ),
                    direction=order_flow_direction,
                    source_quality=(
                        "measured"
                        if microstructure_measured and temporal_measured
                        else "unresolved"
                    ),
                    uncertainty_flags=tuple(
                        sorted(
                            {
                                *order_flow_analysis.uncertainty_flags,
                                *temporal_uncertainty,
                                *pattern_uncertainty,
                            }
                        )
                    ),
                )
            )

        derivatives = store.recent_derivatives(
            exchange=Exchange.BYBIT,
            instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
            symbol=symbol,
            limit=64,
        )
        if derivatives:
            derivatives_freeze = build_derivatives_context_evidence_freeze(
                derivatives,
                as_of_ms=as_of_ms,
            )
            derivatives_analysis = derivatives_freeze.analysis
            derivatives_evidence = {
                derivatives_freeze.freeze_identity,
                derivatives_analysis.evidence_identity,
                *(
                    item.observation_identity
                    for item in derivatives_freeze.observations
                ),
            }
            snapshots.append(
                build_family_snapshot(
                    projector_id="derivatives_change",
                    family=ConfluenceFamily.DERIVATIVES,
                    category=StreamCategory.INTELLIGENCE,
                    subtype="derivatives_material_change",
                    importance=StreamImportance.IMPORTANT,
                    source_event_identity=derivatives_freeze.freeze_identity,
                    source_scope=(
                        "bybit:linear_perpetual:market_tape_derivatives"
                    ),
                    asset=_base_asset(symbol),
                    symbol=symbol,
                    market=symbol,
                    timeframe="15m",
                    event_at_ms=as_of_ms,
                    source_as_of_ms=as_of_ms,
                    evidence_identities=tuple(sorted(derivatives_evidence)),
                    evidence_domains=("derivatives",),
                    state_label=derivatives_analysis.label.value,
                    state_components=(
                        ("basis_state", derivatives_analysis.basis_state.value),
                        (
                            "funding_state",
                            derivatives_analysis.funding_state.value,
                        ),
                        ("label", derivatives_analysis.label.value),
                        (
                            "open_interest_state",
                            derivatives_analysis.open_interest_state.value,
                        ),
                    ),
                    direction=None,
                    source_quality=(
                        "unresolved"
                        if derivatives_analysis.label
                        is DerivativesContextLabel.UNRESOLVED
                        else "measured"
                    ),
                    uncertainty_flags=derivatives_analysis.uncertainty_flags,
                )
            )

    return tuple(
        sorted(
            snapshots,
            key=lambda item: (
                item.event_at_ms,
                item.projector_id,
                item.symbol,
                item.source_event_identity,
            ),
        )
    )


def _rich_liquidity_quality(*qualities: str) -> str:
    if "unavailable" in qualities:
        return "unavailable"
    if "degraded" in qualities:
        return "degraded"
    return "good"


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        char in "0123456789abcdef" for char in value
    )

def _base_asset(symbol: str) -> str:
    normalized = symbol.upper()
    for quote in ("USDT", "USDC", "USD"):
        if normalized.endswith(quote) and len(normalized) > len(quote):
            return normalized[: -len(quote)]
    return normalized
