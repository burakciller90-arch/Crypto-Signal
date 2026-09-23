from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceMatrixResolution,
    build_confluence_family_evidence,
    build_locked_m6_policy,
    evaluate_confluence_matrix,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory import confluence_threshold_research
from research.alpha_factory.confluence_threshold_research import (
    ThresholdResearchStatus,
    build_confluence_threshold_forward_observation,
    build_confluence_threshold_research_config,
    evaluate_confluence_threshold_hypotheses,
)
from research.alpha_factory.foundation import PartitionRole, build_research_partition

WINDOW_START = 1_000
WINDOW_END = 5_000
FAMILIES = tuple(sorted(ConfluenceFamily, key=lambda item: item.value))


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _snapshot(
    as_of_ms: int,
    support_strength: str,
    *,
    conflict: bool = False,
):
    conflict_ids = (_sha(f"conflict-{as_of_ms}"),) if conflict else ()
    evidence = tuple(
        build_confluence_family_evidence(
            family=family,
            asset="BTCUSDT",
            timeframe="4h",
            regime="trend_up",
            as_of_ms=as_of_ms,
            state=MetaEvidenceState.OBSERVED,
            direction=MetaDirection.BULLISH,
            directional_strength_0_1=Decimal(support_strength),
            evidence_quality_0_1=Decimal("0.90"),
            freshness_0_1=Decimal("0.95"),
            market_available_at_ms=as_of_ms - 20,
            observed_at_ms=as_of_ms - 10,
            source_engine_ids=(f"{family.value}-engine",),
            source_evidence_identities=(_sha(f"{family.value}-{as_of_ms}"),),
            material_conflict_identities=(
                conflict_ids if family is ConfluenceFamily.ONCHAIN else ()
            ),
            uncertainty_flags=(),
        )
        for family in FAMILIES
    )
    return evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )


def _snapshots():
    return (
        _snapshot(1_500, "0.72"),
        _snapshot(2_500, "0.77"),
        _snapshot(3_500, "0.82"),
        _snapshot(4_500, "0.90"),
    )


def _partition(snapshots, role: PartitionRole = PartitionRole.UNTOUCHED_FORWARD):
    return build_research_partition(
        dataset_identity=_sha("m6-threshold-forward-dataset"),
        role=role,
        start_ms=WINDOW_START,
        end_ms=WINDOW_END,
        row_count=len(snapshots),
        evidence_identities=tuple(
            sorted(item.snapshot_identity for item in snapshots)
        ),
    )


def _config():
    return build_confluence_threshold_research_config(
        build_locked_m6_policy(),
        created_at_ms=WINDOW_START - 1,
        window_start_ms=WINDOW_START,
        window_end_ms=WINDOW_END,
        outcome_definition="candidate-direction 4h net-R after explicit research cost",
    )


def _observations(snapshots):
    outcomes = (
        (Decimal("0.40"), Decimal("0.10")),
        (Decimal("-0.10"), Decimal("0.10")),
        (Decimal("0.60"), Decimal("0.10")),
        (Decimal("0.20"), Decimal("0.10")),
    )
    return tuple(
        build_confluence_threshold_forward_observation(
            snapshot,
            outcome_available_at_ms=snapshot.as_of_ms + 100,
            gross_outcome_r=gross,
            explicit_cost_r=cost,
            source_outcome_identity=_sha(f"outcome-{snapshot.as_of_ms}"),
        )
        for snapshot, (gross, cost) in zip(snapshots, outcomes, strict=True)
    )


def test_locked_thresholds_are_compared_in_one_frozen_forward_window() -> None:
    snapshots = _snapshots()
    partition = _partition(snapshots)
    observations = _observations(snapshots)

    results, manifest = evaluate_confluence_threshold_hypotheses(
        _config(),
        partition,
        observations,
        as_of_ms=WINDOW_END,
    )

    assert tuple(item.threshold for item in results) == (
        Decimal(70),
        Decimal(75),
        Decimal(80),
        Decimal(85),
    )
    assert tuple(item.activation_count for item in results) == (4, 3, 2, 1)
    assert tuple(item.blocked_count for item in results) == (0, 1, 2, 3)
    assert results[0].positive_net_count == 3
    assert results[0].negative_net_count == 1
    assert results[0].flat_net_count == 0
    assert results[0].gross_r_total == Decimal("1.1000")
    assert results[0].explicit_cost_r_total == Decimal("0.4000")
    assert results[0].net_r_total == Decimal("0.7000")
    assert results[0].mean_net_r == Decimal("0.1750")
    assert results[0].positive_net_fraction == Decimal("0.7500")

    assert manifest.status is ThresholdResearchStatus.EVALUATED
    assert manifest.threshold_winner is None
    assert manifest.automatic_winner_selection is False
    assert manifest.automatic_promotion is False
    assert manifest.calibrated_probability_claim is False
    assert manifest.production_authority is False
    assert manifest.real_capital == 0


def test_forward_comparison_is_permutation_invariant() -> None:
    snapshots = _snapshots()
    partition = _partition(snapshots)
    observations = _observations(snapshots)

    first = evaluate_confluence_threshold_hypotheses(
        _config(),
        partition,
        observations,
        as_of_ms=WINDOW_END,
    )
    second = evaluate_confluence_threshold_hypotheses(
        _config(),
        partition,
        tuple(reversed(observations)),
        as_of_ms=WINDOW_END,
    )

    assert first == second


def test_high_support_conflict_snapshot_remains_blocked_for_all_thresholds() -> None:
    clean = _snapshot(1_500, "0.90")
    conflict = _snapshot(2_500, "1.00", conflict=True)
    assert conflict.support_score_0_100 == Decimal("100.00")
    assert conflict.resolution is ConfluenceMatrixResolution.CONFLICT

    snapshots = (clean, conflict)
    partition = _partition(snapshots)
    observations = tuple(
        build_confluence_threshold_forward_observation(
            snapshot,
            outcome_available_at_ms=snapshot.as_of_ms + 100,
            gross_outcome_r=Decimal("0.50"),
            explicit_cost_r=Decimal("0.10"),
            source_outcome_identity=_sha(f"conflict-outcome-{snapshot.as_of_ms}"),
        )
        for snapshot in snapshots
    )
    results, manifest = evaluate_confluence_threshold_hypotheses(
        _config(),
        partition,
        observations,
        as_of_ms=WINDOW_END,
    )

    assert manifest.status is ThresholdResearchStatus.EVALUATED
    assert all(item.activation_count == 1 for item in results)
    assert all(item.blocked_count == 1 for item in results)


def test_forward_window_cannot_be_evaluated_early() -> None:
    snapshots = _snapshots()
    partition = _partition(snapshots)

    results, manifest = evaluate_confluence_threshold_hypotheses(
        _config(),
        partition,
        _observations(snapshots),
        as_of_ms=WINDOW_END - 1,
    )

    assert results == ()
    assert manifest.status is ThresholdResearchStatus.NOT_YET_EVALUABLE
    assert manifest.result_identities == ()
    assert manifest.observation_identities == ()


def test_closed_window_without_observations_is_explicit_no_evidence() -> None:
    snapshots = _snapshots()
    results, manifest = evaluate_confluence_threshold_hypotheses(
        _config(),
        _partition(snapshots),
        (),
        as_of_ms=WINDOW_END,
    )

    assert results == ()
    assert manifest.status is ThresholdResearchStatus.NO_EVIDENCE
    assert manifest.threshold_winner is None


def test_config_must_be_frozen_before_forward_window() -> None:
    with pytest.raises(ValueError, match="predate forward window"):
        build_confluence_threshold_research_config(
            build_locked_m6_policy(),
            created_at_ms=WINDOW_START,
            window_start_ms=WINDOW_START,
            window_end_ms=WINDOW_END,
            outcome_definition="4h net-R",
        )


def test_forward_partition_role_and_exact_evidence_membership_are_required() -> None:
    snapshots = _snapshots()
    config = _config()
    observations = _observations(snapshots)

    with pytest.raises(ValueError, match="UNTOUCHED_FORWARD"):
        evaluate_confluence_threshold_hypotheses(
            config,
            _partition(snapshots, role=PartitionRole.OUT_OF_SAMPLE),
            observations,
            as_of_ms=WINDOW_END,
        )

    wrong_partition = build_research_partition(
        dataset_identity=_sha("m6-threshold-forward-dataset"),
        role=PartitionRole.UNTOUCHED_FORWARD,
        start_ms=WINDOW_START,
        end_ms=WINDOW_END,
        row_count=len(snapshots),
        evidence_identities=tuple(
            sorted(
                (
                    *(item.snapshot_identity for item in snapshots[:-1]),
                    _sha("wrong-snapshot"),
                )
            )
        ),
    )
    with pytest.raises(ValueError, match="do not match partition evidence"):
        evaluate_confluence_threshold_hypotheses(
            config,
            wrong_partition,
            observations,
            as_of_ms=WINDOW_END,
        )


def test_outcome_must_mature_inside_frozen_forward_window() -> None:
    snapshots = _snapshots()
    observations = list(_observations(snapshots))
    last = snapshots[-1]
    observations[-1] = build_confluence_threshold_forward_observation(
        last,
        outcome_available_at_ms=WINDOW_END + 1,
        gross_outcome_r=Decimal("0.20"),
        explicit_cost_r=Decimal("0.10"),
        source_outcome_identity=_sha("late-outcome"),
    )

    with pytest.raises(ValueError, match="unavailable by forward window end"):
        evaluate_confluence_threshold_hypotheses(
            _config(),
            _partition(snapshots),
            tuple(observations),
            as_of_ms=WINDOW_END,
        )


def test_identity_tampering_and_winner_selection_fail_closed() -> None:
    snapshots = _snapshots()
    observations = _observations(snapshots)
    results, manifest = evaluate_confluence_threshold_hypotheses(
        _config(),
        _partition(snapshots),
        observations,
        as_of_ms=WINDOW_END,
    )

    with pytest.raises(ValueError, match="observation identity mismatch"):
        replace(
            observations[0],
            observation_identity="f" * 64,
        )
    with pytest.raises(ValueError, match="result identity mismatch"):
        replace(results[0], activation_count=results[0].activation_count + 1)
    with pytest.raises(ValueError, match="cannot select, promote, calibrate or deploy"):
        replace(manifest, threshold_winner=Decimal(80))


def test_threshold_research_has_no_execution_or_automatic_selection_surface() -> None:
    source = inspect.getsource(confluence_threshold_research).lower()

    forbidden = (
        "crypto_signal.paper",
        "crypto_signal.signals",
        "import httpx",
        "import requests",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "launchctl",
        "subprocess",
        "def promote",
        "def deploy",
        "winner_identity",
    )
    assert all(token not in source for token in forbidden)
    assert confluence_threshold_research.REAL_CAPITAL == 0
