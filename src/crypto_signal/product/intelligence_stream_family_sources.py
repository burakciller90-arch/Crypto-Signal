from __future__ import annotations

import json
from pathlib import Path

from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.liquidations import LiquidatedPositionSide
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.data.options_surface_store import OptionsSurfaceStore
from crypto_signal.data.store import CandleStore
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.intelligence.derivatives_context import (
    DerivativesContextLabel,
    build_derivatives_context_evidence_freeze,
)
from crypto_signal.intelligence.derivatives_crowding import (
    build_derivatives_crowding_evidence_freeze,
)
from crypto_signal.intelligence.derivatives_dynamics import (
    DerivativesDynamicsStatus,
    build_derivatives_dynamics_evidence_freeze,
)
from crypto_signal.intelligence.liquidation_heatmap import (
    DEFAULT_LIQUIDATION_HEATMAP_CONFIG,
    build_liquidation_heatmap_evidence_freeze,
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
from crypto_signal.intelligence.options_volatility import (
    build_options_volatility_evidence_freeze,
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
    options_surface_path: Path | None = None,
) -> tuple[StreamFamilySnapshot, ...]:
    store = MarketTapeStore(market_tape_path)
    options_store = (
        None
        if options_surface_path is None
        else OptionsSurfaceStore(options_surface_path)
    )
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

        structure = None
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
            if temporal is not None and structure is not None:
                absorption = build_absorption_freeze(
                    temporal,
                    structure,
                    as_of_ms=as_of_ms,
                )
                absorption_analysis = absorption.analysis
                order_flow_evidence.update(
                    {
                        absorption.freeze_identity,
                        absorption_analysis.evidence_identity,
                        structure.freeze_identity,
                        structure.analysis.evidence_identity,
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
            absorption_measured = (
                absorption is None
                or absorption.analysis.status is PatternStatus.MEASURED
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
                        if (
                            microstructure_measured
                            and temporal_measured
                            and absorption_measured
                        )
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
            dynamics_freeze = build_derivatives_dynamics_evidence_freeze(
                derivatives,
                as_of_ms=as_of_ms,
            )
            dynamics_analysis = dynamics_freeze.analysis
            derivatives_evidence = {
                derivatives_freeze.freeze_identity,
                derivatives_analysis.evidence_identity,
                dynamics_freeze.freeze_identity,
                dynamics_analysis.evidence_identity,
                *(
                    item.observation_identity
                    for item in derivatives_freeze.observations
                ),
                *(
                    item.observation_identity
                    for item in dynamics_freeze.observations
                ),
            }
            derivatives_domains = {
                "derivatives",
                "derivatives_context",
                "derivatives_dynamics",
            }
            derivatives_uncertainty = {
                *derivatives_analysis.uncertainty_flags,
                *dynamics_analysis.uncertainty_flags,
            }
            derivatives_components: list[tuple[str, str]] = [
                ("basis_state", derivatives_analysis.basis_state.value),
                (
                    "dynamics_latest_observation_age_ms",
                    str(dynamics_analysis.latest_observation_age_ms),
                ),
                (
                    "dynamics_oi_price_state",
                    dynamics_analysis.oi_price_state.value,
                ),
                ("dynamics_status", dynamics_analysis.status.value),
                ("funding_state", derivatives_analysis.funding_state.value),
                ("label", derivatives_analysis.label.value),
                (
                    "open_interest_state",
                    derivatives_analysis.open_interest_state.value,
                ),
            ]
            dynamics_metrics = dynamics_analysis.metrics
            if dynamics_metrics is not None:
                for name, value in (
                    (
                        "basis_change_bps",
                        dynamics_metrics.basis_change_bps,
                    ),
                    (
                        "funding_acceleration_bps",
                        dynamics_metrics.funding_acceleration_bps,
                    ),
                    (
                        "funding_percentile_0_1",
                        dynamics_metrics.funding_percentile_0_1,
                    ),
                    (
                        "latest_basis_bps",
                        dynamics_metrics.latest_basis_bps,
                    ),
                    (
                        "mark_price_change_fraction",
                        dynamics_metrics.mark_price_change_fraction,
                    ),
                    (
                        "open_interest_change_fraction",
                        dynamics_metrics.open_interest_change_fraction,
                    ),
                ):
                    if value is not None:
                        derivatives_components.append((name, str(value)))

            liquidation_lookback_ms = (
                DEFAULT_LIQUIDATION_HEATMAP_CONFIG.lookback_ms
            )
            liquidation_window_start_ms = max(
                0,
                as_of_ms - liquidation_lookback_ms,
            )
            liquidation_history_limit = 1000
            liquidation_history = store.recent_liquidations(
                exchange=Exchange.BYBIT,
                instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
                symbol=symbol,
                limit=liquidation_history_limit,
            )
            liquidation_history_truncated = (
                len(liquidation_history) >= liquidation_history_limit
            )
            recent_liquidations = tuple(
                item
                for item in liquidation_history
                if (
                    max(
                        item.event_at_ms,
                        item.source_timestamp_ms,
                        item.ingested_at_ms,
                    )
                    <= as_of_ms
                    and item.event_at_ms >= liquidation_window_start_ms
                )
            )
            if recent_liquidations:
                derivatives_domains.add("observed_liquidation_events")
                derivatives_evidence.update(
                    item.liquidation_identity
                    for item in recent_liquidations
                )
                if liquidation_history_truncated:
                    derivatives_uncertainty.add(
                        "observed_liquidation_event_history_truncated"
                    )
                derivatives_components.extend(
                    (
                        (
                            "observed_liquidation_event_count",
                            str(len(recent_liquidations)),
                        ),
                        (
                            "observed_liquidation_event_count_exact",
                            str(not liquidation_history_truncated).lower(),
                        ),
                        (
                            "observed_long_liquidation_count",
                            str(
                                sum(
                                    item.liquidated_position_side
                                    is LiquidatedPositionSide.LONG
                                    for item in recent_liquidations
                                )
                            ),
                        ),
                        (
                            "observed_short_liquidation_count",
                            str(
                                sum(
                                    item.liquidated_position_side
                                    is LiquidatedPositionSide.SHORT
                                    for item in recent_liquidations
                                )
                            ),
                        ),
                    )
                )

            eligible_coverages = tuple(
                coverage
                for coverage in store.recent_liquidation_coverage(
                    exchange=Exchange.BYBIT,
                    instrument_type=(
                        DerivativesInstrumentType.LINEAR_PERPETUAL
                    ),
                    symbol=symbol,
                    limit=100,
                )
                if (
                    coverage.observed_at_ms <= as_of_ms
                    and coverage.coverage_end_ms <= as_of_ms
                    and (
                        as_of_ms - coverage.coverage_end_ms
                        <= liquidation_lookback_ms
                    )
                )
            )

            heatmap_freeze = None
            crowding_freeze = None
            liquidation_coverage_identity = None
            liquidation_status = "unavailable"
            crowding_label = "unavailable"
            has_liquidation_extension = bool(
                recent_liquidations or eligible_coverages
            )

            if not has_liquidation_extension:
                pass
            elif not eligible_coverages:
                derivatives_components.extend(
                    (
                        ("crowding_status", "unavailable"),
                        ("liquidation_heatmap_status", "unavailable"),
                        ("liquidation_zero_event_claim", "unavailable"),
                    )
                )
                derivatives_uncertainty.add(
                    "liquidation_event_coverage_unavailable_or_stale"
                )
            else:
                selected_coverage = max(
                    eligible_coverages,
                    key=lambda item: (
                        item.coverage_end_ms,
                        -item.coverage_start_ms,
                        item.coverage_identity,
                    ),
                )
                liquidation_coverage_identity = (
                    selected_coverage.coverage_identity
                )
                # Provider coverage is only PIT-visible once its provider
                # batch has been observed locally. In live WS traffic,
                # observed_at_ms can be a few milliseconds after coverage_end_ms;
                # analyzing at coverage_end_ms would make the coverage itself
                # future evidence and cause liquidation_replay() to fail closed
                # with an exception instead of returning an unresolved analysis.
                liquidation_as_of_ms = selected_coverage.observed_at_ms
                historical_derivatives = tuple(
                    item
                    for item in derivatives
                    if max(
                        item.event_at_ms,
                        item.source_timestamp_ms,
                        item.ingested_at_ms,
                    )
                    <= liquidation_as_of_ms
                )
                historical_dynamics = (
                    None
                    if not historical_derivatives
                    else build_derivatives_dynamics_evidence_freeze(
                        historical_derivatives,
                        as_of_ms=liquidation_as_of_ms,
                    )
                )
                mark_reference = (
                    None
                    if historical_dynamics is None
                    else next(
                    (
                        item
                        for item in reversed(
                            historical_dynamics.observations
                        )
                        if item.mark_price is not None
                        ),
                        None,
                    )
                )
                if historical_dynamics is None:
                    derivatives_components.extend(
                        (
                            ("crowding_status", "unavailable"),
                            (
                                "liquidation_heatmap_status",
                                "unavailable",
                            ),
                            (
                                "liquidation_zero_event_claim",
                                "unavailable",
                            ),
                        )
                    )
                    derivatives_uncertainty.add(
                        "liquidation_historical_derivatives_unavailable"
                    )
                elif mark_reference is None:
                    derivatives_components.extend(
                        (
                            ("crowding_status", "unavailable"),
                            (
                                "liquidation_heatmap_status",
                                "unavailable",
                            ),
                            (
                                "liquidation_zero_event_claim",
                                "unavailable",
                            ),
                        )
                    )
                    derivatives_uncertainty.add(
                        "liquidation_mark_reference_unavailable"
                    )
                else:
                    liquidation_replay = store.liquidation_replay(
                        coverage_identity=selected_coverage.coverage_identity,
                        as_of_ms=liquidation_as_of_ms,
                    )
                    heatmap_freeze = (
                        build_liquidation_heatmap_evidence_freeze(
                            liquidation_replay.events,
                            coverage=liquidation_replay.coverage,
                            mark_reference=mark_reference,
                            as_of_ms=liquidation_as_of_ms,
                        )
                    )
                    heatmap_analysis = heatmap_freeze.analysis
                    crowding_freeze = (
                        build_derivatives_crowding_evidence_freeze(
                            historical_dynamics,
                            heatmap_freeze,
                        )
                    )
                    crowding_analysis = crowding_freeze.analysis
                    liquidation_status = heatmap_analysis.status.value
                    crowding_label = crowding_analysis.label.value

                    derivatives_domains.update(
                        {
                            "derivatives_crowding",
                            "liquidation_event_coverage",
                            "observed_liquidation_heatmap",
                        }
                    )
                    derivatives_evidence.update(
                        {
                            selected_coverage.coverage_identity,
                            historical_dynamics.freeze_identity,
                            historical_dynamics.analysis.evidence_identity,
                            heatmap_freeze.freeze_identity,
                            heatmap_analysis.evidence_identity,
                            mark_reference.observation_identity,
                            crowding_freeze.freeze_identity,
                            crowding_analysis.evidence_identity,
                        }
                    )
                    derivatives_uncertainty.update(
                        heatmap_analysis.uncertainty_flags
                    )
                    derivatives_uncertainty.update(
                        crowding_analysis.uncertainty_flags
                    )

                    zero_event_claim = (
                        "verified_complete_coverage"
                        if (
                            heatmap_analysis.status.value == "measured"
                            and heatmap_analysis.observed_state.value
                            == "none_observed"
                        )
                        else (
                            "not_applicable_observed_events"
                            if (
                                heatmap_analysis.status.value == "measured"
                                and heatmap_analysis.observed_state.value
                                == "observed"
                            )
                            else "unavailable_incomplete_coverage"
                        )
                    )
                    derivatives_components.extend(
                        (
                            (
                                "crowded_side",
                                crowding_analysis.crowded_side.value,
                            ),
                            (
                                "crowding_label",
                                crowding_analysis.label.value,
                            ),
                            (
                                "crowding_status",
                                crowding_analysis.status.value,
                            ),
                            (
                                "liquidation_analysis_as_of_ms",
                                str(liquidation_as_of_ms),
                            ),
                            (
                                "liquidation_cluster_count",
                                str(
                                    heatmap_analysis.observed_cluster_count
                                ),
                            ),
                            (
                                "liquidation_coverage_end_ms",
                                str(selected_coverage.coverage_end_ms),
                            ),
                            (
                                "liquidation_coverage_start_ms",
                                str(selected_coverage.coverage_start_ms),
                            ),
                            (
                                "liquidation_heatmap_status",
                                heatmap_analysis.status.value,
                            ),
                            (
                                "liquidation_observed_state",
                                heatmap_analysis.observed_state.value,
                            ),
                            (
                                "estimated_leverage_concentration_status",
                                (
                                    heatmap_analysis
                                    .estimated_leverage_concentration_status
                                    .value
                                ),
                            ),
                            (
                                "liquidation_risk_zone_status",
                                (
                                    heatmap_analysis
                                    .liquidation_risk_zone_status.value
                                ),
                            ),
                            (
                                "liquidation_zero_event_claim",
                                zero_event_claim,
                            ),
                            (
                                "squeeze_risk_side",
                                crowding_analysis.squeeze_risk_side.value,
                            ),
                        )
                    )

            options_status = "not_configured"
            options_freeze = None
            options_surface = None
            base_asset = _base_asset(symbol)
            has_options_extension = (
                options_store is not None and base_asset in {"BTC", "ETH"}
            )
            if has_options_extension:
                assert options_store is not None
                options_surface = options_store.latest_surface_as_of(
                    exchange=Exchange.BYBIT,
                    base_coin=base_asset,
                    as_of_ms=as_of_ms,
                )
                if options_surface is None:
                    options_status = "unavailable"
                    derivatives_components.extend(
                        (
                            ("options_status", options_status),
                            (
                                "options_volatility_index_status",
                                "unavailable",
                            ),
                        )
                    )
                    derivatives_uncertainty.add(
                        "options_surface_unavailable"
                    )
                else:
                    options_freeze = (
                        build_options_volatility_evidence_freeze(
                            options_surface,
                            as_of_ms=as_of_ms,
                        )
                    )
                    options_analysis = options_freeze.analysis
                    options_status = options_analysis.status.value
                    derivatives_domains.update(
                        {"options_surface", "options_volatility"}
                    )
                    derivatives_evidence.update(
                        {
                            options_surface.surface_identity,
                            options_surface.instrument_metadata_identity,
                            options_freeze.freeze_identity,
                            options_analysis.evidence_identity,
                            *(
                                item.quote_identity
                                for item in options_surface.contracts
                            ),
                        }
                    )
                    derivatives_uncertainty.update(
                        options_analysis.uncertainty_flags
                    )
                    derivatives_components.extend(
                        (
                            ("options_status", options_status),
                            (
                                "options_surface_age_ms",
                                str(options_analysis.surface_age_ms),
                            ),
                            (
                                "options_contract_count",
                                str(options_analysis.consumed_contract_count),
                            ),
                        )
                    )
                    options_metrics = options_analysis.metrics
                    if options_metrics is not None:
                        derivatives_components.extend(
                            (
                                (
                                    "options_measured_atm_expiry_count",
                                    str(
                                        options_metrics
                                        .measured_atm_expiry_count
                                    ),
                                ),
                                (
                                    "options_measured_rr_expiry_count",
                                    str(
                                        options_metrics
                                        .measured_rr_expiry_count
                                    ),
                                ),
                                (
                                    "options_term_structure_shape",
                                    options_metrics
                                    .term_structure_shape.value,
                                ),
                                (
                                    "options_volatility_index_status",
                                    options_metrics
                                    .volatility_index_status.value,
                                ),
                            )
                        )
                        for name, value in (
                            (
                                "options_front_atm_iv",
                                options_metrics.front_atm_iv,
                            ),
                            (
                                "options_next_atm_iv",
                                options_metrics.next_atm_iv,
                            ),
                            (
                                "options_term_structure_iv_change",
                                options_metrics.term_structure_iv_change,
                            ),
                            (
                                "options_put_call_open_interest_ratio",
                                options_metrics
                                .put_call_open_interest_ratio,
                            ),
                            (
                                "options_put_call_volume_ratio",
                                options_metrics.put_call_volume_ratio,
                            ),
                            (
                                "options_top_expiry_at_ms",
                                options_metrics.top_expiry_at_ms,
                            ),
                            (
                                "options_top_expiry_open_interest_share",
                                options_metrics
                                .top_expiry_open_interest_share,
                            ),
                        ):
                            if value is not None:
                                derivatives_components.append(
                                    (name, str(value))
                                )
                    else:
                        derivatives_components.append(
                            (
                                "options_volatility_index_status",
                                "unavailable",
                            )
                        )

            if has_options_extension:
                derivatives_source_event_identity = canonical_sha256(
                    {
                        "as_of_ms": as_of_ms,
                        "context_freeze_identity": (
                            derivatives_freeze.freeze_identity
                        ),
                        "crowding_freeze_identity": (
                            None
                            if crowding_freeze is None
                            else crowding_freeze.freeze_identity
                        ),
                        "dynamics_freeze_identity": (
                            dynamics_freeze.freeze_identity
                        ),
                        "heatmap_freeze_identity": (
                            None
                            if heatmap_freeze is None
                            else heatmap_freeze.freeze_identity
                        ),
                        "liquidation_coverage_identity": (
                            liquidation_coverage_identity
                        ),
                        "observed_liquidation_identities": tuple(
                            item.liquidation_identity
                            for item in recent_liquidations
                        ),
                        "options_freeze_identity": (
                            None
                            if options_freeze is None
                            else options_freeze.freeze_identity
                        ),
                        "options_status": options_status,
                        "options_surface_identity": (
                            None
                            if options_surface is None
                            else options_surface.surface_identity
                        ),
                        "symbol": symbol,
                        "version": "rdp6-options-derivatives-family-v1/1",
                    }
                )
                derivatives_state_label = (
                    f"{derivatives_analysis.label.value}:"
                    f"{dynamics_analysis.status.value}:"
                    f"{dynamics_analysis.oi_price_state.value}:"
                    f"{liquidation_status}:{crowding_label}:"
                    f"{options_status}"
                )
            elif has_liquidation_extension:
                derivatives_source_event_identity = canonical_sha256(
                    {
                        "as_of_ms": as_of_ms,
                        "context_freeze_identity": (
                            derivatives_freeze.freeze_identity
                        ),
                        "crowding_freeze_identity": (
                            None
                            if crowding_freeze is None
                            else crowding_freeze.freeze_identity
                        ),
                        "dynamics_freeze_identity": (
                            dynamics_freeze.freeze_identity
                        ),
                        "heatmap_freeze_identity": (
                            None
                            if heatmap_freeze is None
                            else heatmap_freeze.freeze_identity
                        ),
                        "liquidation_coverage_identity": (
                            liquidation_coverage_identity
                        ),
                        "observed_liquidation_identities": tuple(
                            item.liquidation_identity
                            for item in recent_liquidations
                        ),
                        "symbol": symbol,
                        "version": "rdp5-rich-derivatives-family-v2/1",
                    }
                )
                derivatives_state_label = (
                    f"{derivatives_analysis.label.value}:"
                    f"{dynamics_analysis.status.value}:"
                    f"{dynamics_analysis.oi_price_state.value}:"
                    f"{liquidation_status}:{crowding_label}"
                )
            else:
                derivatives_source_event_identity = canonical_sha256(
                    {
                        "as_of_ms": as_of_ms,
                        "context_freeze_identity": (
                            derivatives_freeze.freeze_identity
                        ),
                        "dynamics_freeze_identity": (
                            dynamics_freeze.freeze_identity
                        ),
                        "symbol": symbol,
                        "version": "rdp5-derivatives-dynamics-family-v1/1",
                    }
                )
                derivatives_state_label = (
                    f"{derivatives_analysis.label.value}:"
                    f"{dynamics_analysis.status.value}:"
                    f"{dynamics_analysis.oi_price_state.value}"
                )
            snapshots.append(
                build_family_snapshot(
                    projector_id="derivatives_change",
                    family=ConfluenceFamily.DERIVATIVES,
                    category=StreamCategory.INTELLIGENCE,
                    subtype="derivatives_material_change",
                    importance=StreamImportance.IMPORTANT,
                    source_event_identity=derivatives_source_event_identity,
                    source_scope=(
                        "bybit:linear_perpetual_plus_options:derivatives"
                        if has_options_extension
                        else "bybit:linear_perpetual:market_tape_derivatives"
                    ),
                    asset=_base_asset(symbol),
                    symbol=symbol,
                    market=symbol,
                    timeframe="15m",
                    event_at_ms=as_of_ms,
                    source_as_of_ms=as_of_ms,
                    evidence_identities=tuple(sorted(derivatives_evidence)),
                    evidence_domains=tuple(sorted(derivatives_domains)),
                    state_label=derivatives_state_label,
                    state_components=tuple(derivatives_components),
                    direction=None,
                    source_quality=(
                        "measured"
                        if (
                            derivatives_analysis.label
                            is not DerivativesContextLabel.UNRESOLVED
                            and dynamics_analysis.status
                            is DerivativesDynamicsStatus.MEASURED
                        )
                        else "unresolved"
                    ),
                    uncertainty_flags=tuple(
                        sorted(derivatives_uncertainty)
                    ),
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
