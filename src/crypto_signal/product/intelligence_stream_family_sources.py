from __future__ import annotations

import json
from pathlib import Path

from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.intelligence.derivatives_context import (
    DerivativesContextLabel,
    build_derivatives_context_evidence_freeze,
)
from crypto_signal.intelligence.liquidity_dynamics import (
    build_liquidity_dynamics_evidence_freeze,
)
from crypto_signal.intelligence.order_flow_microstructure import (
    OrderFlowMicrostructureLabel,
    build_order_flow_microstructure_evidence_freeze,
)
from crypto_signal.ledger.bundle import DecisionFreezeBundle
from crypto_signal.ledger.deserialization import (
    parse_lifecycle_evaluation,
    parse_signal_decision,
)
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
        *signal.selected_evidence_ids,
    }
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
        evidence.add(geometry.source_evidence_id)
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
) -> tuple[StreamFamilySnapshot, ...]:
    store = MarketTapeStore(market_tape_path)
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
            liquidity_analysis = liquidity.analysis
            liquidity_evidence = {
                liquidity.freeze_identity,
                liquidity_analysis.evidence_identity,
                *(item.snapshot_identity for item in liquidity.snapshots),
            }
            snapshots.append(
                build_family_snapshot(
                    projector_id="liquidity_change",
                    family=ConfluenceFamily.LIQUIDITY,
                    category=StreamCategory.INTELLIGENCE,
                    subtype="liquidity_material_change",
                    importance=StreamImportance.IMPORTANT,
                    source_event_identity=liquidity.freeze_identity,
                    source_scope="bybit:spot:market_tape_liquidity",
                    asset=_base_asset(symbol),
                    symbol=symbol,
                    market=symbol,
                    timeframe="microstructure",
                    event_at_ms=as_of_ms,
                    source_as_of_ms=as_of_ms,
                    evidence_identities=tuple(sorted(liquidity_evidence)),
                    evidence_domains=("liquidity", "order_book"),
                    state_label=(
                        f"{liquidity_analysis.status.value}:"
                        f"{liquidity_analysis.liquidity_take_candidate.value}"
                    ),
                    state_components=(
                        (
                            "liquidity_take_candidate",
                            liquidity_analysis.liquidity_take_candidate.value,
                        ),
                        ("source_quality", liquidity_analysis.source_quality.value),
                        ("status", liquidity_analysis.status.value),
                    ),
                    direction=None,
                    source_quality=liquidity_analysis.source_quality.value,
                    uncertainty_flags=liquidity_analysis.uncertainty_flags,
                )
            )

        if orderbooks or trades:
            order_flow = build_order_flow_microstructure_evidence_freeze(
                orderbooks,
                trades,
                as_of_ms=as_of_ms,
            )
            order_flow_analysis = order_flow.analysis
            order_flow_evidence = {
                order_flow.freeze_identity,
                order_flow_analysis.evidence_identity,
                *(item.trade_identity for item in order_flow.trades),
            }
            if order_flow.orderbook is not None:
                order_flow_evidence.add(order_flow.orderbook.snapshot_identity)
            order_flow_direction = None
            if order_flow_analysis.label is OrderFlowMicrostructureLabel.BUY_PRESSURE:
                order_flow_direction = "buy_pressure"
            elif order_flow_analysis.label is OrderFlowMicrostructureLabel.SELL_PRESSURE:
                order_flow_direction = "sell_pressure"

            snapshots.append(
                build_family_snapshot(
                    projector_id="order_flow_change",
                    family=ConfluenceFamily.ORDER_FLOW,
                    category=StreamCategory.INTELLIGENCE,
                    subtype="order_flow_material_change",
                    importance=StreamImportance.IMPORTANT,
                    source_event_identity=order_flow.freeze_identity,
                    source_scope="bybit:spot:market_tape_order_flow",
                    asset=_base_asset(symbol),
                    symbol=symbol,
                    market=symbol,
                    timeframe="microstructure",
                    event_at_ms=as_of_ms,
                    source_as_of_ms=as_of_ms,
                    evidence_identities=tuple(sorted(order_flow_evidence)),
                    evidence_domains=(
                        "order_book",
                        "order_flow",
                        "public_trades",
                    ),
                    state_label=order_flow_analysis.label.value,
                    state_components=(
                        ("book_pressure", order_flow_analysis.book_pressure.value),
                        ("label", order_flow_analysis.label.value),
                        ("taker_flow", order_flow_analysis.taker_flow.value),
                    ),
                    direction=order_flow_direction,
                    source_quality=(
                        "unresolved"
                        if order_flow_analysis.label
                        is OrderFlowMicrostructureLabel.UNRESOLVED
                        else "measured"
                    ),
                    uncertainty_flags=order_flow_analysis.uncertainty_flags,
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

def _base_asset(symbol: str) -> str:
    normalized = symbol.upper()
    for quote in ("USDT", "USDC", "USD"):
        if normalized.endswith(quote) and len(normalized) > len(quote):
            return normalized[: -len(quote)]
    return normalized
