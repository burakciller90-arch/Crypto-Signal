from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_live_freeze_clock import market_candles

from crypto_signal.ledger.bundle import (
    DecisionFreezeBundle,
    bundle_json,
)
from crypto_signal.ledger.geometry_proof import (
    GeometryLayer,
    GeometryPrimitive,
    build_frozen_geometry_proof,
    geometry_proof_json,
)
from crypto_signal.ledger.live_clock import freeze_live_candles
from crypto_signal.ledger.serialization import sha256_text
from crypto_signal.ledger.store import ImmutableSignalLedger


def _bundle(tmp_path: Path) -> DecisionFreezeBundle:
    candles = market_candles()
    now_ms = max(item.ingested_at_ms for item in candles) + 1_000
    result = freeze_live_candles(
        candles=candles,
        ledger=ImmutableSignalLedger(tmp_path / "ledger.sqlite3"),
        minimum_closed_candles=100,
        now_ms=lambda: now_ms,
    )
    assert result.bundle is not None
    return result.bundle


def _rehash(bundle: DecisionFreezeBundle) -> DecisionFreezeBundle:
    draft = replace(bundle, bundle_identity="0" * 64)
    return replace(
        draft,
        bundle_identity=sha256_text(bundle_json(draft)),
    )


def test_frozen_geometry_proof_is_deterministic_and_parent_bound(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)

    first = build_frozen_geometry_proof(bundle)
    second = build_frozen_geometry_proof(bundle)

    assert first == second
    assert first.proof_identity == second.proof_identity
    assert geometry_proof_json(first) == geometry_proof_json(second)
    assert first.bundle_identity == bundle.bundle_identity
    assert first.signal_freeze_identity == (
        bundle.signal_decision.freeze_identity
    )
    assert first.as_of_ms == bundle.signal_decision.as_of_ms
    assert first.source_cutoff_open_time_ms == (
        bundle.source_cutoff_open_time_ms
    )
    assert first.consumed_candle_identities == tuple(
        candle.identity for candle in bundle.candles
    )


def test_frozen_geometry_proof_has_exact_layer_states_and_counts(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    proof = build_frozen_geometry_proof(bundle)

    states = {item.layer: item for item in proof.methodology_states}
    assert set(states) == set(GeometryLayer)
    assert states[GeometryLayer.HARMONIC].source_count == len(
        bundle.harmonic.candidates
    )
    assert states[GeometryLayer.ELLIOTT].source_count == (
        len(bundle.elliott.impulse_candidates)
        + len(bundle.elliott.abc_candidates)
    )
    assert states[GeometryLayer.SIGNAL].status == (
        "selected_geometry"
        if bundle.signal_decision.geometry is not None
        else "no_selected_geometry"
    )

    for layer in GeometryLayer:
        assert states[layer].rendered_count == sum(
            item.layer is layer for item in proof.annotations
        )

    harmonic_status = states[GeometryLayer.HARMONIC].status
    if not bundle.harmonic.candidates:
        assert harmonic_status == "no_candidate"
    elif not bundle.harmonic.valid_matches:
        assert harmonic_status == "candidates_no_valid_match"
    elif len(bundle.harmonic.valid_matches) == 1:
        assert harmonic_status == "one_valid_match"
    else:
        assert harmonic_status == "multiple_valid_matches"

    elliott_status = states[GeometryLayer.ELLIOTT].status
    if (
        not bundle.elliott.impulse_candidates
        and not bundle.elliott.abc_candidates
    ):
        assert elliott_status == "no_candidate"


def test_all_annotations_are_frozen_candle_scoped_and_sha_addressed(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    proof = build_frozen_geometry_proof(bundle)
    allowed = {candle.open_time_ms for candle in bundle.candles}

    for annotation in proof.annotations:
        assert len(annotation.annotation_identity) == 64
        assert len(annotation.source_reference) == 64
        assert all(
            point.open_time_ms in allowed for point in annotation.points
        )
        if annotation.start_open_time_ms is not None:
            assert annotation.start_open_time_ms in allowed
        if annotation.end_open_time_ms is not None:
            assert annotation.end_open_time_ms in allowed

        if annotation.primitive is GeometryPrimitive.POLYLINE:
            assert len(annotation.points) >= 2
        elif annotation.primitive is GeometryPrimitive.MARKER:
            assert len(annotation.points) == 1
        else:
            assert annotation.points == ()
            assert annotation.price_low is not None
            assert annotation.price_high is not None


def test_harmonic_and_elliott_render_counts_follow_frozen_results(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    proof = build_frozen_geometry_proof(bundle)

    harmonic = tuple(
        item
        for item in proof.annotations
        if item.layer is GeometryLayer.HARMONIC
    )
    assert len(harmonic) == 5 * len(bundle.harmonic.valid_matches)

    expected_elliott = 0
    for candidate in bundle.elliott.impulse_candidates:
        if candidate.valid_so_far:
            expected_elliott += 2
            expected_elliott += sum(
                projection.price > 0
                for projection in candidate.projections
            )
    for candidate in bundle.elliott.abc_candidates:
        expected_elliott += 1
        expected_elliott += int(
            candidate.c_equality_projection.price > 0
        )

    elliott = tuple(
        item
        for item in proof.annotations
        if item.layer is GeometryLayer.ELLIOTT
    )
    assert len(elliott) == expected_elliott


def test_signal_geometry_annotations_match_frozen_decision_exactly(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    proof = build_frozen_geometry_proof(bundle)
    geometry = bundle.signal_decision.geometry
    signal_annotations = tuple(
        item
        for item in proof.annotations
        if item.layer is GeometryLayer.SIGNAL
    )

    if geometry is None:
        assert signal_annotations == ()
        return

    by_label = {item.label: item for item in signal_annotations}
    entry = by_label["signal_entry_zone"]
    assert entry.price_low == geometry.entry_zone.low
    assert entry.price_high == geometry.entry_zone.high

    invalidation = by_label["signal_invalidation"]
    assert invalidation.price_low == geometry.invalidation_price
    assert invalidation.price_high == geometry.invalidation_price

    for target in geometry.targets:
        annotation = by_label[f"signal_target_{target.label}"]
        assert annotation.price_low == target.target_price
        assert annotation.price_high == target.target_price


def test_selected_evidence_lineage_drift_fails_closed(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    assert bundle.selected_evidence
    forged = replace(
        bundle.selected_evidence[0],
        evidence_id="forged:frozen:evidence",
    )
    inconsistent = _rehash(
        replace(
            bundle,
            selected_evidence=(
                forged,
                *bundle.selected_evidence[1:],
            ),
        )
    )

    with pytest.raises(
        ValueError,
        match="selected evidence is absent",
    ):
        build_frozen_geometry_proof(inconsistent)


def test_geometry_proof_builder_has_no_current_market_data_dependency() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "crypto_signal"
        / "ledger"
        / "geometry_proof.py"
    ).read_text(encoding="utf-8")

    assert "CandleStore" not in source
    assert "MarketTapeStore" not in source
    assert "fetch_candles" not in source
    assert "analyze_price_action" not in source
    assert "analyze_harmonics" not in source
    assert "analyze_elliott" not in source
    assert "DecisionFreezeBundle" in source
