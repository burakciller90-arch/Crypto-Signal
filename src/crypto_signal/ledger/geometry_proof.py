from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.confluence.adapters import (
    elliott_result_evidence,
    harmonic_result_evidence,
    price_action_structure_evidence,
)
from crypto_signal.confluence.models import PairRelation
from crypto_signal.ledger.bundle import (
    DecisionFreezeBundle,
    verify_bundle_identity,
)
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.methodologies.price_action.models import (
    StructureDirection,
)
from crypto_signal.primitives.models import ConfirmedPivot

GEOMETRY_PROOF_SCHEMA_VERSION = "frozen-geometry-proof-v1/1"


class GeometryLayer(StrEnum):
    PRICE_ACTION = "price_action"
    HARMONIC = "harmonic"
    ELLIOTT = "elliott"
    SIGNAL = "signal"


class GeometryPrimitive(StrEnum):
    POLYLINE = "polyline"
    HORIZONTAL_LEVEL = "horizontal_level"
    PRICE_ZONE = "price_zone"
    MARKER = "marker"


@dataclass(frozen=True, slots=True)
class GeometryPoint:
    open_time_ms: int
    price: Decimal
    label: str

    def __post_init__(self) -> None:
        if self.open_time_ms < 0:
            raise ValueError("geometry point time cannot be negative")
        if self.price <= 0:
            raise ValueError("geometry point price must be positive")
        if not self.label.strip():
            raise ValueError("geometry point label must be non-empty")


@dataclass(frozen=True, slots=True)
class FrozenGeometryAnnotation:
    annotation_identity: str
    layer: GeometryLayer
    primitive: GeometryPrimitive
    label: str
    source_reference: str
    points: tuple[GeometryPoint, ...]
    start_open_time_ms: int | None
    end_open_time_ms: int | None
    price_low: Decimal | None
    price_high: Decimal | None
    direction: str | None
    status: str
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require_sha256(self.annotation_identity, "geometry annotation identity")
        _require_sha256(self.source_reference, "geometry source reference")
        if not self.label.strip() or not self.status.strip():
            raise ValueError("geometry annotation label/status must be non-empty")
        if self.direction is not None and not self.direction.strip():
            raise ValueError("geometry annotation direction cannot be blank")
        if tuple(sorted(set(self.metadata))) != self.metadata:
            raise ValueError("geometry annotation metadata must be sorted unique")

        if self.primitive is GeometryPrimitive.POLYLINE:
            if len(self.points) < 2:
                raise ValueError("geometry polyline requires at least two points")
            _require_no_range(self)
        elif self.primitive is GeometryPrimitive.MARKER:
            if len(self.points) != 1:
                raise ValueError("geometry marker requires exactly one point")
            _require_no_range(self)
        elif self.primitive in {
            GeometryPrimitive.HORIZONTAL_LEVEL,
            GeometryPrimitive.PRICE_ZONE,
        }:
            if self.points:
                raise ValueError("geometry range annotation cannot carry points")
            if self.start_open_time_ms is None or self.end_open_time_ms is None:
                raise ValueError("geometry range annotation requires time bounds")
            if self.start_open_time_ms > self.end_open_time_ms:
                raise ValueError("geometry annotation time bounds are reversed")
            if self.price_low is None or self.price_high is None:
                raise ValueError("geometry range annotation requires prices")
            if self.price_low <= 0 or self.price_high < self.price_low:
                raise ValueError("geometry annotation price range is invalid")
            if (
                self.primitive is GeometryPrimitive.HORIZONTAL_LEVEL
                and self.price_low != self.price_high
            ):
                raise ValueError("horizontal level requires one exact price")
            if (
                self.primitive is GeometryPrimitive.PRICE_ZONE
                and self.price_low == self.price_high
            ):
                raise ValueError("price zone requires positive width")
        else:
            raise ValueError("unsupported geometry annotation primitive")

        expected = canonical_sha256(_annotation_payload(self))
        if self.annotation_identity != expected:
            raise ValueError("geometry annotation identity mismatch")


@dataclass(frozen=True, slots=True)
class GeometryMethodologyState:
    layer: GeometryLayer
    status: str
    source_count: int
    rendered_count: int
    ambiguity_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.status.strip():
            raise ValueError("geometry methodology status must be non-empty")
        if self.source_count < 0 or self.rendered_count < 0:
            raise ValueError("geometry methodology counts cannot be negative")
        if tuple(sorted(set(self.ambiguity_flags))) != self.ambiguity_flags:
            raise ValueError(
                "geometry methodology ambiguity flags must be sorted unique"
            )


@dataclass(frozen=True, slots=True)
class FrozenGeometryProof:
    proof_identity: str
    schema_version: str
    bundle_identity: str
    signal_freeze_identity: str
    exchange: str
    market_type: str
    symbol: str
    timeframe: str
    as_of_ms: int
    source_cutoff_open_time_ms: int
    consumed_candle_identities: tuple[tuple[str, str, str, str, int], ...]
    methodology_states: tuple[GeometryMethodologyState, ...]
    annotations: tuple[FrozenGeometryAnnotation, ...]
    conflict_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.proof_identity, "geometry proof identity")
        _require_sha256(self.bundle_identity, "geometry proof bundle identity")
        _require_sha256(
            self.signal_freeze_identity,
            "geometry proof signal identity",
        )
        if self.schema_version != GEOMETRY_PROOF_SCHEMA_VERSION:
            raise ValueError("unsupported geometry proof schema")
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("geometry proof market identity must be non-empty")
        if self.as_of_ms < 0 or self.source_cutoff_open_time_ms < 0:
            raise ValueError("geometry proof timestamps cannot be negative")
        if not self.consumed_candle_identities:
            raise ValueError("geometry proof requires consumed candle identities")
        opens = tuple(item[-1] for item in self.consumed_candle_identities)
        if tuple(sorted(opens)) != opens or len(set(opens)) != len(opens):
            raise ValueError(
                "geometry proof candle identities must be chronological unique"
            )
        if opens[-1] != self.source_cutoff_open_time_ms:
            raise ValueError("geometry proof source cutoff mismatch")
        layers = tuple(item.layer for item in self.methodology_states)
        if set(layers) != set(GeometryLayer) or len(layers) != len(
            GeometryLayer
        ):
            raise ValueError(
                "geometry proof requires one state per geometry layer"
            )
        identities = tuple(item.annotation_identity for item in self.annotations)
        if len(set(identities)) != len(identities):
            raise ValueError("geometry proof annotation identities must be unique")
        if tuple(sorted(set(self.conflict_flags))) != self.conflict_flags:
            raise ValueError("geometry proof conflict flags must be sorted unique")

        expected = canonical_sha256(_proof_payload(self))
        if self.proof_identity != expected:
            raise ValueError("geometry proof identity mismatch")


def build_frozen_geometry_proof(
    bundle: DecisionFreezeBundle,
) -> FrozenGeometryProof:
    verify_bundle_identity(bundle)
    _validate_selected_evidence_lineage(bundle)
    decision = bundle.signal_decision
    first_open = bundle.candles[0].open_time_ms
    last_open = bundle.candles[-1].open_time_ms
    annotations: list[FrozenGeometryAnnotation] = []

    annotations.extend(
        _price_action_annotations(
            bundle,
            first_open=first_open,
            last_open=last_open,
        )
    )
    annotations.extend(
        _harmonic_annotations(bundle, last_open=last_open)
    )
    annotations.extend(
        _elliott_annotations(bundle, last_open=last_open)
    )
    annotations.extend(
        _signal_annotations(
            bundle,
            first_open=first_open,
            last_open=last_open,
        )
    )
    ordered_annotations = tuple(
        sorted(
            annotations,
            key=lambda item: (
                item.layer.value,
                item.primitive.value,
                _annotation_start(item),
                item.label,
                item.annotation_identity,
            ),
        )
    )

    pa_source_count = (
        len(bundle.price_action.structure.structure_breaks)
        + len(bundle.price_action.imbalances.fair_value_gaps)
        + len(bundle.price_action.imbalances.balanced_price_ranges)
        + len(bundle.price_action.liquidity.pools)
        + len(bundle.price_action.reference_levels)
        + len(bundle.price_action.level_interactions.events)
        + len(bundle.price_action.displacement.events)
    )
    harmonic_source_count = len(bundle.harmonic.candidates)
    elliott_source_count = (
        len(bundle.elliott.impulse_candidates)
        + len(bundle.elliott.abc_candidates)
    )

    pa_flags: list[str] = []
    if bundle.price_action.structure.ambiguous_swing_source_indices:
        pa_flags.append("ambiguous_swing_source")
    if bundle.price_action.liquidity.ambiguous_swing_source_indices:
        pa_flags.append("liquidity_ambiguous_swing_source")

    harmonic_flags: list[str] = []
    if bundle.harmonic.ambiguous_swing_source_indices:
        harmonic_flags.append("ambiguous_swing_source")
    if _has_duplicate_harmonic_geometry(bundle):
        harmonic_flags.append("multiple_valid_patterns_same_xabcd")

    elliott_flags: list[str] = []
    if bundle.elliott.ambiguous_swing_source_indices:
        elliott_flags.append("ambiguous_swing_source")
    if any(
        item.competing_valid_count > 1
        for item in bundle.elliott.impulse_candidates
    ):
        elliott_flags.append("competing_valid_impulse_counts")

    states = (
        GeometryMethodologyState(
            layer=GeometryLayer.PRICE_ACTION,
            status=(
                "unresolved_structure"
                if bundle.price_action.structure.current_direction
                is StructureDirection.UNKNOWN
                else "resolved_structure"
            ),
            source_count=pa_source_count,
            rendered_count=_layer_count(
                ordered_annotations,
                GeometryLayer.PRICE_ACTION,
            ),
            ambiguity_flags=tuple(sorted(set(pa_flags))),
        ),
        GeometryMethodologyState(
            layer=GeometryLayer.HARMONIC,
            status=_harmonic_status(bundle),
            source_count=harmonic_source_count,
            rendered_count=_layer_count(
                ordered_annotations,
                GeometryLayer.HARMONIC,
            ),
            ambiguity_flags=tuple(sorted(set(harmonic_flags))),
        ),
        GeometryMethodologyState(
            layer=GeometryLayer.ELLIOTT,
            status=_elliott_status(bundle),
            source_count=elliott_source_count,
            rendered_count=_layer_count(
                ordered_annotations,
                GeometryLayer.ELLIOTT,
            ),
            ambiguity_flags=tuple(sorted(set(elliott_flags))),
        ),
        GeometryMethodologyState(
            layer=GeometryLayer.SIGNAL,
            status=(
                "selected_geometry"
                if decision.geometry is not None
                else "no_selected_geometry"
            ),
            source_count=1 if decision.geometry is not None else 0,
            rendered_count=_layer_count(
                ordered_annotations,
                GeometryLayer.SIGNAL,
            ),
            ambiguity_flags=tuple(
                sorted(
                    flag
                    for flag in decision.uncertainty_flags
                    if "geometry" in flag
                )
            ),
        ),
    )

    _validate_annotation_candle_scope(bundle, ordered_annotations)

    conflicts = {
        *bundle.confluence.flags,
        *(
            f"{relation.left.value}:{relation.right.value}:"
            f"{relation.relation.value}"
            for relation in bundle.confluence.pairwise_relations
            if relation.relation
            in {
                PairRelation.CONTRADICT,
                PairRelation.INTERNAL_AMBIGUITY,
            }
        ),
    }
    draft = FrozenGeometryProof(
        proof_identity="0" * 64,
        schema_version=GEOMETRY_PROOF_SCHEMA_VERSION,
        bundle_identity=bundle.bundle_identity,
        signal_freeze_identity=decision.freeze_identity,
        exchange=decision.exchange.value,
        market_type=decision.market_type.value,
        symbol=decision.symbol,
        timeframe=decision.timeframe,
        as_of_ms=decision.as_of_ms,
        source_cutoff_open_time_ms=bundle.source_cutoff_open_time_ms,
        consumed_candle_identities=tuple(
            candle.identity for candle in bundle.candles
        ),
        methodology_states=states,
        annotations=ordered_annotations,
        conflict_flags=tuple(sorted(conflicts)),
    )
    return FrozenGeometryProof(
        proof_identity=canonical_sha256(_proof_payload(draft)),
        schema_version=draft.schema_version,
        bundle_identity=draft.bundle_identity,
        signal_freeze_identity=draft.signal_freeze_identity,
        exchange=draft.exchange,
        market_type=draft.market_type,
        symbol=draft.symbol,
        timeframe=draft.timeframe,
        as_of_ms=draft.as_of_ms,
        source_cutoff_open_time_ms=draft.source_cutoff_open_time_ms,
        consumed_candle_identities=draft.consumed_candle_identities,
        methodology_states=draft.methodology_states,
        annotations=draft.annotations,
        conflict_flags=draft.conflict_flags,
    )


def geometry_proof_json(proof: FrozenGeometryProof) -> str:
    return canonical_json(_proof_payload(proof))


def _validate_selected_evidence_lineage(
    bundle: DecisionFreezeBundle,
) -> None:
    available: set[str] = set()
    pa = price_action_structure_evidence(bundle.price_action)
    if pa is not None:
        available.add(pa.evidence_id)
    available.update(
        item.evidence_id for item in harmonic_result_evidence(bundle.harmonic)
    )
    available.update(
        item.evidence_id for item in elliott_result_evidence(bundle.elliott)
    )
    selected = {
        item.evidence_id for item in bundle.selected_evidence
    }
    missing = tuple(sorted(selected - available))
    if missing:
        raise ValueError(
            "frozen Geometry Proof selected evidence is absent from "
            f"frozen methodology results: {missing!r}"
        )
    geometry = bundle.signal_decision.geometry
    if (
        geometry is not None
        and geometry.source_evidence_id not in selected
    ):
        raise ValueError(
            "frozen Geometry Proof signal geometry source is not selected"
        )


def _validate_annotation_candle_scope(
    bundle: DecisionFreezeBundle,
    annotations: tuple[FrozenGeometryAnnotation, ...],
) -> None:
    allowed = {candle.open_time_ms for candle in bundle.candles}
    for annotation in annotations:
        for point in annotation.points:
            if point.open_time_ms not in allowed:
                raise ValueError(
                    "frozen Geometry Proof point is outside consumed candles"
                )
        for boundary in (
            annotation.start_open_time_ms,
            annotation.end_open_time_ms,
        ):
            if boundary is not None and boundary not in allowed:
                raise ValueError(
                    "frozen Geometry Proof range is outside consumed candles"
                )


def _price_action_annotations(
    bundle: DecisionFreezeBundle,
    *,
    first_open: int,
    last_open: int,
) -> tuple[FrozenGeometryAnnotation, ...]:
    result = bundle.price_action
    output: list[FrozenGeometryAnnotation] = []

    for item in result.structure.structure_breaks:
        output.append(
            _level(
                layer=GeometryLayer.PRICE_ACTION,
                label=f"structure_{item.kind.value}",
                source=item,
                start=item.broken_pivot.open_time_ms,
                end=item.break_candle_identity[-1],
                price=item.level_price,
                direction=item.direction.value,
                status="confirmed",
                metadata=(
                    ("break_close", str(item.break_close)),
                    ("distance_bps", str(item.distance_bps)),
                ),
            )
        )
        output.append(
            _marker(
                layer=GeometryLayer.PRICE_ACTION,
                label=f"structure_break_{item.kind.value}",
                source=item,
                open_time_ms=item.break_candle_identity[-1],
                price=item.break_close,
                direction=item.direction.value,
                status="confirmed",
            )
        )

    for item in result.imbalances.fair_value_gaps:
        output.append(
            _zone(
                layer=GeometryLayer.PRICE_ACTION,
                label=f"fvg_{item.direction.value}",
                source=item,
                start=item.confirmation_candle_identity[-1],
                end=last_open,
                low=item.zone_low,
                high=item.zone_high,
                direction=item.direction.value,
                status=item.status.value,
                metadata=(
                    ("max_fill_fraction", str(item.max_fill_fraction)),
                    ("size_bps", str(item.size_bps)),
                ),
            )
        )

    for item in result.imbalances.balanced_price_ranges:
        start = bundle.candles[item.later_confirmation_index].open_time_ms
        output.append(
            _zone(
                layer=GeometryLayer.PRICE_ACTION,
                label="balanced_price_range",
                source=item,
                start=start,
                end=last_open,
                low=item.zone_low,
                high=item.zone_high,
                direction=None,
                status=item.status.value,
                metadata=(("size_bps", str(item.size_bps)),),
            )
        )

    for item in result.liquidity.pools:
        output.append(
            _zone(
                layer=GeometryLayer.PRICE_ACTION,
                label=f"liquidity_{item.kind.value}",
                source=item,
                start=item.second_anchor.open_time_ms,
                end=last_open,
                low=item.zone_low,
                high=item.zone_high,
                direction=None,
                status=item.status.value,
                metadata=(
                    ("level_price", str(item.level_price)),
                    ("pair_distance_bps", str(item.pair_distance_bps)),
                ),
            )
        )
        if item.event is not None:
            output.append(
                _marker(
                    layer=GeometryLayer.PRICE_ACTION,
                    label=f"liquidity_{item.event.kind.value}",
                    source=item.event,
                    open_time_ms=item.event.candle_identity[-1],
                    price=item.event.extreme_price,
                    direction=item.event.implication_direction.value,
                    status="confirmed",
                )
            )

    for item in result.reference_levels:
        output.append(
            _level(
                layer=GeometryLayer.PRICE_ACTION,
                label=f"reference_{item.label}",
                source=item,
                start=_open_at_or_after(bundle, item.available_at_market_ms),
                end=last_open,
                price=item.price,
                direction=None,
                status="available",
                metadata=(("source", item.source_description),),
            )
        )

    for item in result.level_interactions.events:
        output.append(
            _marker(
                layer=GeometryLayer.PRICE_ACTION,
                label=f"level_{item.kind.value}",
                source=item,
                open_time_ms=item.candle_identity[-1],
                price=item.level.price,
                direction=item.implication_direction.value,
                status="confirmed",
            )
        )

    candle_by_open = {candle.open_time_ms: candle for candle in bundle.candles}
    for item in result.displacement.events:
        candle = candle_by_open.get(item.candle_identity[-1])
        if candle is None:
            raise ValueError(
                "frozen PA displacement references missing consumed candle"
            )
        output.append(
            _marker(
                layer=GeometryLayer.PRICE_ACTION,
                label="displacement",
                source=item,
                open_time_ms=candle.open_time_ms,
                price=candle.close,
                direction=item.direction.value,
                status="confirmed",
            )
        )

    return tuple(output)


def _harmonic_annotations(
    bundle: DecisionFreezeBundle,
    *,
    last_open: int,
) -> tuple[FrozenGeometryAnnotation, ...]:
    output: list[FrozenGeometryAnnotation] = []
    for match in bundle.harmonic.valid_matches:
        candidate = match.candidate
        output.append(
            _polyline(
                layer=GeometryLayer.HARMONIC,
                label=f"harmonic_{match.pattern.value}_xabcd",
                source=match,
                pivots=candidate.pivots,
                labels=("X", "A", "B", "C", "D"),
                direction=candidate.direction.value,
                status="valid",
                metadata=(
                    ("mean_ratio_residual", str(match.mean_ratio_residual)),
                    ("max_ratio_residual", str(match.max_ratio_residual)),
                ),
            )
        )
        output.append(
            _zone(
                layer=GeometryLayer.HARMONIC,
                label=f"harmonic_{match.pattern.value}_prz",
                source=match,
                start=candidate.d.open_time_ms,
                end=last_open,
                low=match.prz_low,
                high=match.prz_high,
                direction=candidate.direction.value,
                status="valid",
                metadata=(("prz_width_bps", str(match.prz_width_bps)),),
            )
        )
        output.append(
            _level(
                layer=GeometryLayer.HARMONIC,
                label=f"harmonic_{match.pattern.value}_invalidation",
                source=match,
                start=candidate.d.open_time_ms,
                end=last_open,
                price=match.invalidation_price,
                direction=candidate.direction.value,
                status="valid",
            )
        )
        for label, price in (
            ("target_1", match.target_1_price),
            ("target_2", match.target_2_price),
        ):
            output.append(
                _level(
                    layer=GeometryLayer.HARMONIC,
                    label=f"harmonic_{match.pattern.value}_{label}",
                    source=match,
                    start=candidate.d.open_time_ms,
                    end=last_open,
                    price=price,
                    direction=candidate.direction.value,
                    status="valid",
                )
            )
    return tuple(output)


def _elliott_annotations(
    bundle: DecisionFreezeBundle,
    *,
    last_open: int,
) -> tuple[FrozenGeometryAnnotation, ...]:
    output: list[FrozenGeometryAnnotation] = []
    for candidate in bundle.elliott.impulse_candidates:
        if not candidate.valid_so_far:
            continue
        labels = tuple(
            str(index) for index in range(len(candidate.points))
        )
        output.append(
            _polyline(
                layer=GeometryLayer.ELLIOTT,
                label=f"elliott_impulse_wave_{candidate.current_wave}",
                source=candidate,
                pivots=candidate.points,
                labels=labels,
                direction=candidate.direction.value,
                status=(
                    "complete" if candidate.complete else "valid_so_far"
                ),
                metadata=(
                    (
                        "competing_valid_count",
                        str(candidate.competing_valid_count),
                    ),
                    (
                        "rule_support_fraction",
                        str(candidate.rule_support_fraction),
                    ),
                ),
            )
        )
        output.append(
            _level(
                layer=GeometryLayer.ELLIOTT,
                label="elliott_structural_invalidation",
                source=candidate,
                start=candidate.end.open_time_ms,
                end=last_open,
                price=candidate.structural_invalidation_price,
                direction=candidate.direction.value,
                status=(
                    "complete" if candidate.complete else "valid_so_far"
                ),
            )
        )
        for projection in candidate.projections:
            if projection.price <= 0:
                continue
            output.append(
                _level(
                    layer=GeometryLayer.ELLIOTT,
                    label=f"elliott_projection_{projection.name}",
                    source=candidate,
                    start=candidate.end.open_time_ms,
                    end=last_open,
                    price=projection.price,
                    direction=candidate.direction.value,
                    status="projection",
                )
            )

    for candidate in bundle.elliott.abc_candidates:
        output.append(
            _polyline(
                layer=GeometryLayer.ELLIOTT,
                label="elliott_abc",
                source=candidate,
                pivots=(
                    candidate.start,
                    candidate.a,
                    candidate.b,
                    candidate.c,
                ),
                labels=("S", "A", "B", "C"),
                direction=candidate.direction.value,
                status=(
                    "zigzag_compatible"
                    if candidate.zigzag_compatible
                    else "candidate"
                ),
                metadata=(
                    (
                        "rule_support_fraction",
                        str(candidate.rule_support_fraction),
                    ),
                ),
            )
        )
        if candidate.c_equality_projection.price > 0:
            output.append(
                _level(
                    layer=GeometryLayer.ELLIOTT,
                    label="elliott_abc_c_equality",
                    source=candidate,
                    start=candidate.c.open_time_ms,
                    end=last_open,
                    price=candidate.c_equality_projection.price,
                    direction=candidate.direction.value,
                    status="projection",
                )
            )
    return tuple(output)


def _signal_annotations(
    bundle: DecisionFreezeBundle,
    *,
    first_open: int,
    last_open: int,
) -> tuple[FrozenGeometryAnnotation, ...]:
    geometry = bundle.signal_decision.geometry
    if geometry is None:
        return ()
    source = bundle.signal_decision
    output = [
        _zone(
            layer=GeometryLayer.SIGNAL,
            label="signal_entry_zone",
            source=source,
            start=first_open,
            end=last_open,
            low=geometry.entry_zone.low,
            high=geometry.entry_zone.high,
            direction=bundle.signal_decision.direction.value,
            status="selected",
            metadata=(
                (
                    "entry_reference_price",
                    str(geometry.entry_reference_price),
                ),
                ("source_methodology", geometry.source_methodology.value),
            ),
        ),
        _level(
            layer=GeometryLayer.SIGNAL,
            label="signal_invalidation",
            source=source,
            start=first_open,
            end=last_open,
            price=geometry.invalidation_price,
            direction=bundle.signal_decision.direction.value,
            status="selected",
            metadata=(
                ("trigger", geometry.invalidation_trigger.value),
            ),
        ),
    ]
    for target in geometry.targets:
        output.append(
            _level(
                layer=GeometryLayer.SIGNAL,
                label=f"signal_target_{target.label}",
                source=source,
                start=first_open,
                end=last_open,
                price=target.target_price,
                direction=bundle.signal_decision.direction.value,
                status="selected",
                metadata=(("reference_rr", str(target.reference_rr)),),
            )
        )
    return tuple(output)


def _polyline(
    *,
    layer: GeometryLayer,
    label: str,
    source: object,
    pivots: tuple[ConfirmedPivot, ...],
    labels: tuple[str, ...],
    direction: str | None,
    status: str,
    metadata: tuple[tuple[str, str], ...] = (),
) -> FrozenGeometryAnnotation:
    if len(pivots) != len(labels):
        raise ValueError("geometry polyline point/label count mismatch")
    return _annotation(
        layer=layer,
        primitive=GeometryPrimitive.POLYLINE,
        label=label,
        source_reference=canonical_sha256(source),
        points=tuple(
            GeometryPoint(
                open_time_ms=pivot.open_time_ms,
                price=pivot.price,
                label=point_label,
            )
            for pivot, point_label in zip(pivots, labels, strict=True)
        ),
        start=None,
        end=None,
        low=None,
        high=None,
        direction=direction,
        status=status,
        metadata=metadata,
    )


def _level(
    *,
    layer: GeometryLayer,
    label: str,
    source: object,
    start: int,
    end: int,
    price: Decimal,
    direction: str | None,
    status: str,
    metadata: tuple[tuple[str, str], ...] = (),
) -> FrozenGeometryAnnotation:
    return _annotation(
        layer=layer,
        primitive=GeometryPrimitive.HORIZONTAL_LEVEL,
        label=label,
        source_reference=canonical_sha256(source),
        points=(),
        start=start,
        end=end,
        low=price,
        high=price,
        direction=direction,
        status=status,
        metadata=metadata,
    )


def _zone(
    *,
    layer: GeometryLayer,
    label: str,
    source: object,
    start: int,
    end: int,
    low: Decimal,
    high: Decimal,
    direction: str | None,
    status: str,
    metadata: tuple[tuple[str, str], ...] = (),
) -> FrozenGeometryAnnotation:
    if low == high:
        return _level(
            layer=layer,
            label=label,
            source=source,
            start=start,
            end=end,
            price=low,
            direction=direction,
            status=status,
            metadata=metadata,
        )
    return _annotation(
        layer=layer,
        primitive=GeometryPrimitive.PRICE_ZONE,
        label=label,
        source_reference=canonical_sha256(source),
        points=(),
        start=start,
        end=end,
        low=low,
        high=high,
        direction=direction,
        status=status,
        metadata=metadata,
    )


def _marker(
    *,
    layer: GeometryLayer,
    label: str,
    source: object,
    open_time_ms: int,
    price: Decimal,
    direction: str | None,
    status: str,
    metadata: tuple[tuple[str, str], ...] = (),
) -> FrozenGeometryAnnotation:
    return _annotation(
        layer=layer,
        primitive=GeometryPrimitive.MARKER,
        label=label,
        source_reference=canonical_sha256(source),
        points=(
            GeometryPoint(
                open_time_ms=open_time_ms,
                price=price,
                label=label,
            ),
        ),
        start=None,
        end=None,
        low=None,
        high=None,
        direction=direction,
        status=status,
        metadata=metadata,
    )


def _annotation(
    *,
    layer: GeometryLayer,
    primitive: GeometryPrimitive,
    label: str,
    source_reference: str,
    points: tuple[GeometryPoint, ...],
    start: int | None,
    end: int | None,
    low: Decimal | None,
    high: Decimal | None,
    direction: str | None,
    status: str,
    metadata: tuple[tuple[str, str], ...],
) -> FrozenGeometryAnnotation:
    canonical_metadata = tuple(sorted(set(metadata)))
    draft = FrozenGeometryAnnotation(
        annotation_identity="0" * 64,
        layer=layer,
        primitive=primitive,
        label=label,
        source_reference=source_reference,
        points=points,
        start_open_time_ms=start,
        end_open_time_ms=end,
        price_low=low,
        price_high=high,
        direction=direction,
        status=status,
        metadata=canonical_metadata,
    )
    return FrozenGeometryAnnotation(
        annotation_identity=canonical_sha256(_annotation_payload(draft)),
        layer=draft.layer,
        primitive=draft.primitive,
        label=draft.label,
        source_reference=draft.source_reference,
        points=draft.points,
        start_open_time_ms=draft.start_open_time_ms,
        end_open_time_ms=draft.end_open_time_ms,
        price_low=draft.price_low,
        price_high=draft.price_high,
        direction=draft.direction,
        status=draft.status,
        metadata=draft.metadata,
    )


def _annotation_payload(
    annotation: FrozenGeometryAnnotation,
) -> dict[str, object]:
    return {
        "layer": annotation.layer,
        "primitive": annotation.primitive,
        "label": annotation.label,
        "source_reference": annotation.source_reference,
        "points": annotation.points,
        "start_open_time_ms": annotation.start_open_time_ms,
        "end_open_time_ms": annotation.end_open_time_ms,
        "price_low": annotation.price_low,
        "price_high": annotation.price_high,
        "direction": annotation.direction,
        "status": annotation.status,
        "metadata": annotation.metadata,
    }


def _proof_payload(proof: FrozenGeometryProof) -> dict[str, object]:
    return {
        "schema_version": proof.schema_version,
        "bundle_identity": proof.bundle_identity,
        "signal_freeze_identity": proof.signal_freeze_identity,
        "exchange": proof.exchange,
        "market_type": proof.market_type,
        "symbol": proof.symbol,
        "timeframe": proof.timeframe,
        "as_of_ms": proof.as_of_ms,
        "source_cutoff_open_time_ms": proof.source_cutoff_open_time_ms,
        "consumed_candle_identities": proof.consumed_candle_identities,
        "methodology_states": proof.methodology_states,
        "annotations": proof.annotations,
        "conflict_flags": proof.conflict_flags,
    }


def _harmonic_status(bundle: DecisionFreezeBundle) -> str:
    if not bundle.harmonic.candidates:
        return "no_candidate"
    if not bundle.harmonic.valid_matches:
        return "candidates_no_valid_match"
    if len(bundle.harmonic.valid_matches) == 1:
        return "one_valid_match"
    return "multiple_valid_matches"


def _elliott_status(bundle: DecisionFreezeBundle) -> str:
    if not bundle.elliott.impulse_candidates and not bundle.elliott.abc_candidates:
        return "no_candidate"
    valid = sum(
        item.valid_so_far for item in bundle.elliott.impulse_candidates
    )
    compatible = sum(
        item.zigzag_compatible for item in bundle.elliott.abc_candidates
    )
    if valid == 0 and compatible == 0:
        return "candidates_no_valid_count"
    if valid + compatible == 1:
        return "one_valid_count"
    return "multiple_valid_counts"


def _has_duplicate_harmonic_geometry(
    bundle: DecisionFreezeBundle,
) -> bool:
    identities = tuple(
        item.candidate.identity for item in bundle.harmonic.valid_matches
    )
    return len(set(identities)) != len(identities)


def _layer_count(
    annotations: tuple[FrozenGeometryAnnotation, ...],
    layer: GeometryLayer,
) -> int:
    return sum(item.layer is layer for item in annotations)


def _annotation_start(annotation: FrozenGeometryAnnotation) -> int:
    if annotation.points:
        return annotation.points[0].open_time_ms
    if annotation.start_open_time_ms is None:
        raise AssertionError("geometry annotation has no sortable start")
    return annotation.start_open_time_ms


def _open_at_or_after(
    bundle: DecisionFreezeBundle,
    available_at_ms: int,
) -> int:
    for candle in bundle.candles:
        if candle.close_time_ms >= available_at_ms:
            return candle.open_time_ms
    return bundle.candles[-1].open_time_ms


def _require_no_range(annotation: FrozenGeometryAnnotation) -> None:
    if (
        annotation.start_open_time_ms is not None
        or annotation.end_open_time_ms is not None
        or annotation.price_low is not None
        or annotation.price_high is not None
    ):
        raise ValueError("point geometry annotation cannot carry range fields")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be lowercase SHA256")
