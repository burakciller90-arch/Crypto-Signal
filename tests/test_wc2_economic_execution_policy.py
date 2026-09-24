from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_signal.evaluation.untouched_forward_economic_policy import (
    WC2_CORRELATION_MINIMUM_RETURN_PAIRS,
    WC2_CORRELATION_WINDOW_15M_BARS,
    WC2_ECONOMIC_PAPER_MODE,
    WC2_MARKET_REFERENCE_MAX_DELAY_MS,
    WC2_MINIMUM_ACTUAL_PAPER_TRADES_FOR_ECONOMIC_REVIEW,
    WC2EconomicExecutionPolicyStore,
    build_wc2_economic_execution_policy,
    build_wc2_fixed_fractional_sizing_policy,
)
from crypto_signal.paper.position_sizing_intelligence import SizingMethod


def _policy(*, preregistered: int = 1_000, start: int = 2_000):
    return build_wc2_economic_execution_policy(
        preregistered_at_ms=preregistered,
        collection_start_ms=start,
        review_policy_identity="a" * 64,
        collection_protocol_identity="b" * 64,
        epoch2_activation_identity="c" * 64,
    )


def test_economic_policy_is_forward_only_fixed_fractional_and_authority_closed() -> None:
    policy = _policy()
    sizing = build_wc2_fixed_fractional_sizing_policy()

    assert policy.sizing_policy_identity == sizing.policy_identity
    assert policy.reviewed_sizing_method is SizingMethod.FIXED_FRACTIONAL
    assert policy.paper_mode == WC2_ECONOMIC_PAPER_MODE
    assert policy.correlation_window_15m_bars == WC2_CORRELATION_WINDOW_15M_BARS
    assert (
        policy.correlation_minimum_return_pairs
        == WC2_CORRELATION_MINIMUM_RETURN_PAIRS
    )
    assert policy.market_reference_max_delay_ms == WC2_MARKET_REFERENCE_MAX_DELAY_MS
    assert (
        policy.minimum_actual_paper_trades_for_economic_review
        == WC2_MINIMUM_ACTUAL_PAPER_TRADES_FOR_ECONOMIC_REVIEW
        == 30
    )
    assert policy.require_all_risk_domains_predecision is True
    assert policy.require_simulated_execution_for_every_trade is True
    assert policy.require_explicit_cost_evidence_for_every_trade is True
    assert policy.automatic_promotion is False
    assert policy.canonical_epoch2_write_authority is False
    assert policy.production_authority is False
    assert policy.real_capital == 0


def test_economic_policy_rejects_backdating_and_policy_mutation() -> None:
    with pytest.raises(ValueError, match="preregistered before collection"):
        _policy(preregistered=2_000, start=2_000)

    policy = _policy()
    with pytest.raises(ValueError, match="fixed fractional only"):
        replace(policy, reviewed_sizing_method=SizingMethod.KELLY_HALF)
    with pytest.raises(ValueError, match="thresholds are immutable"):
        replace(policy, minimum_actual_paper_trades_for_economic_review=1)
    with pytest.raises(ValueError, match="authority boundary"):
        replace(policy, production_authority=True)


def test_economic_policy_store_is_append_only_idempotent_and_read_only_latest(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2.wc2-economic-execution-policy.sqlite3"
    store = WC2EconomicExecutionPolicyStore(path)
    first = _policy()

    assert store.append(first) is True
    before = path.read_bytes()
    assert store.append(first) is False
    assert path.read_bytes() == before
    assert store.count() == 1
    assert store.latest() == first

    second = _policy(preregistered=3_000, start=4_000)
    assert store.append(second) is True
    assert store.count() == 2
    assert store.latest() == second

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                """
                UPDATE wc2_economic_execution_policies
                SET collection_start_ms = collection_start_ms + 1
                """
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("DELETE FROM wc2_economic_execution_policies")


def test_economic_policy_store_refuses_non_wc2_database(tmp_path: Path) -> None:
    path = tmp_path / "bad.wc2-economic-execution-policy.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated_truth(id TEXT)")

    with pytest.raises(ValueError, match="other tables"):
        WC2EconomicExecutionPolicyStore(path).initialize()
