from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import ops.run_live_evidence_clock as clock
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2PolicyStore,
    build_wc2_untouched_forward_policy,
)
from crypto_signal.ledger.coverage import (
    LiveCoverageContext,
    LiveCoveragePlan,
    LiveCoverageSourceStrategy,
)
from crypto_signal.ledger.live_clock import LiveFreezeResult, LiveFreezeStatus


def _context() -> LiveCoverageContext:
    return LiveCoverageContext(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        source_strategy=LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M,
        freeze_limit=120,
        minimum_closed_candles=100,
    )


def _plan() -> LiveCoveragePlan:
    return LiveCoveragePlan(
        version="wc2-clock-test/1",
        contexts=(_context(),),
    )


def _replay_result() -> LiveFreezeResult:
    return LiveFreezeResult(
        status=LiveFreezeStatus.ALREADY_FROZEN,
        source_cutoff_open_time_ms=123,
        signal_freeze_identity=None,
        bundle_identity=None,
        signal_state=None,
        confluence_score=None,
        lifecycle_disposition=None,
    )


def _args(**overrides):
    values = {
        "wc2_enabled": False,
        "wc2_policy": None,
        "wc2_decision_evidence": None,
        "wc2_cohort": None,
        "wc2_maximum_issuance_delay_ms": None,
        "wc2_horizon_bars": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _patch_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_freeze(**kwargs):
        return _replay_result()

    monkeypatch.setattr(clock, "freeze_coverage_context", fake_freeze)
    monkeypatch.setattr(
        clock,
        "persist_provider_divergence_for_plan",
        lambda **kwargs: None,
    )


def test_wc2_clock_is_disabled_by_default() -> None:
    config = clock.build_wc2_clock_config(_args())

    assert config == clock.WC2ClockConfig()
    assert config.enabled is False
    assert clock.load_wc2_policy(config) is None


def test_wc2_clock_rejects_partial_or_implicit_configuration(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="explicit --wc2-enabled"):
        clock.build_wc2_clock_config(
            _args(wc2_policy=tmp_path / "policy.sqlite3")
        )

    with pytest.raises(ValueError, match="requires policy"):
        clock.build_wc2_clock_config(
            _args(
                wc2_enabled=True,
                wc2_policy=tmp_path / "policy.sqlite3",
            )
        )

    with pytest.raises(ValueError, match="issuance delay"):
        clock.WC2ClockConfig(
            enabled=True,
            policy_path=tmp_path / "policy.sqlite3",
            decision_evidence_path=tmp_path / "decision.sqlite3",
            cohort_path=tmp_path / "cohort.sqlite3",
            maximum_issuance_delay_ms=0,
            horizon_bars=4,
        )


def test_disabled_clock_never_calls_wc2_or_creates_wc2_databases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_cycle(monkeypatch)
    decision_path = tmp_path / "decision.sqlite3"
    cohort_path = tmp_path / "cohort.sqlite3"

    def forbidden_wc2(**kwargs):
        raise AssertionError("WC2 processor must remain disabled")

    monkeypatch.setattr(clock, "process_wc2_live_freeze", forbidden_wc2)

    status = asyncio.run(
        clock.run(
            tmp_path / "signal.sqlite3",
            plan=_plan(),
            candle_cache_path=tmp_path / "candles.sqlite3",
            provider_divergence_path=tmp_path / "divergence.sqlite3",
            wc2_config=clock.WC2ClockConfig(),
        )
    )

    assert status == 0
    assert not decision_path.exists()
    assert not cohort_path.exists()


def test_enabled_clock_passes_exact_policy_and_runtime_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_cycle(monkeypatch)
    policy_path = tmp_path / "policy.sqlite3"
    decision_path = tmp_path / "decision.sqlite3"
    cohort_path = tmp_path / "cohort.sqlite3"
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=1_000,
        collection_start_ms=2_000,
    )
    assert WC2PolicyStore(policy_path).append(policy) is True
    captured = {}

    def fake_wc2(result, **kwargs):
        captured["result"] = result
        captured.update(kwargs)
        return SimpleNamespace(
            status=SimpleNamespace(value="no_persisted_issuance"),
            forecast_identity=None,
            cohort_forecast_identity=None,
        )

    monkeypatch.setattr(clock, "process_wc2_live_freeze", fake_wc2)
    config = clock.WC2ClockConfig(
        enabled=True,
        policy_path=policy_path,
        decision_evidence_path=decision_path,
        cohort_path=cohort_path,
        maximum_issuance_delay_ms=30_000,
        horizon_bars=4,
    )

    status = asyncio.run(
        clock.run(
            tmp_path / "signal.sqlite3",
            plan=_plan(),
            candle_cache_path=tmp_path / "candles.sqlite3",
            provider_divergence_path=tmp_path / "divergence.sqlite3",
            wc2_config=config,
        )
    )

    assert status == 0
    assert captured["result"].status is LiveFreezeStatus.ALREADY_FROZEN
    assert captured["policy"] == policy
    assert captured["maximum_issuance_delay_ms"] == 30_000
    assert captured["horizon_bars"] == 4
    assert captured["base_asset"] == "BTC"
    assert captured["decision_ledger"].path == decision_path
    assert captured["cohort_journal"].path == cohort_path
    assert not decision_path.exists()
    assert not cohort_path.exists()


def test_enabled_clock_missing_policy_fails_before_runtime_db_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_cycle(monkeypatch)
    policy_path = tmp_path / "missing-policy.sqlite3"
    decision_path = tmp_path / "decision.sqlite3"
    cohort_path = tmp_path / "cohort.sqlite3"
    config = clock.WC2ClockConfig(
        enabled=True,
        policy_path=policy_path,
        decision_evidence_path=decision_path,
        cohort_path=cohort_path,
        maximum_issuance_delay_ms=30_000,
        horizon_bars=4,
    )

    status = asyncio.run(
        clock.run(
            tmp_path / "signal.sqlite3",
            plan=_plan(),
            candle_cache_path=tmp_path / "candles.sqlite3",
            provider_divergence_path=tmp_path / "divergence.sqlite3",
            wc2_config=config,
        )
    )

    assert status == 1
    assert not policy_path.exists()
    assert not decision_path.exists()
    assert not cohort_path.exists()


def test_wc2_base_asset_is_explicit_usdt_only() -> None:
    assert clock.wc2_base_asset("BTCUSDT") == "BTC"

    with pytest.raises(ValueError, match="USDT"):
        clock.wc2_base_asset("BTCUSD")
