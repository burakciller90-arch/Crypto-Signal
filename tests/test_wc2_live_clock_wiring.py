from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_r22_intent_preview import _activation

import ops.run_live_evidence_clock as clock
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    WC2CollectionProtocolStore,
    build_wc2_collection_protocol,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2PolicyStore,
    build_wc2_untouched_forward_policy,
)
from crypto_signal.evaluation.untouched_forward_prepared_runtime import (
    WC2PreparedLiveStatus,
)
from crypto_signal.ledger.coverage import (
    LiveCoverageContext,
    LiveCoveragePlan,
    LiveCoverageSourceStrategy,
)
from crypto_signal.ledger.live_clock import LiveFreezeResult, LiveFreezeStatus


def _context(symbol: str = "BTCUSDT") -> LiveCoverageContext:
    return LiveCoverageContext(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
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


def _two_context_plan() -> LiveCoveragePlan:
    return LiveCoveragePlan(
        version="wc2-clock-test-two/1",
        contexts=(_context("BTCUSDT"), _context("ETHUSDT")),
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
        "wc2_epoch2": None,
        "wc2_collection_protocol": None,
        "wc2_prepared": None,
        "wc2_decision_evidence": None,
        "wc2_cohort": None,
        "wc2_shadow_intent": None,
        "wc2_shadow_cycle": None,
        "wc2_execution_enabled": False,
        "wc2_execution_protocol": None,
        "wc2_execution_runtime": None,
        "wc2_execution_journal": None,
        "wc2_venue_rules": None,
        "wc2_maximum_issuance_delay_ms": None,
        "wc2_horizon_bars": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "epoch2": tmp_path / "paper_fund_epoch2.sqlite3",
        "protocol": (
            tmp_path
            / "wc2_collection_protocol.wc2-collection-protocol.sqlite3"
        ),
        "prepared": tmp_path / "wc2.wc2-prepared.sqlite3",
        "decision": tmp_path / "decision.sqlite3",
        "cohort": tmp_path / "wc2_untouched_forward.sqlite3",
        "shadow_intent": tmp_path / "wc2.shadow-intent.sqlite3",
        "shadow_cycle": tmp_path / "wc2.shadow-cycle.sqlite3",
        "execution_protocol": tmp_path / "wc2_paper_execution_protocol.sqlite3",
        "execution_runtime": tmp_path / "wc2_paper_execution_runtime.sqlite3",
        "execution_journal": tmp_path / "wc2_paper_execution.sqlite3",
        "venue_rules": tmp_path / "paper_fund.sqlite3",
    }


def _config(
    tmp_path: Path,
    *,
    policy_path: Path,
    execution_enabled: bool = False,
) -> clock.WC2ClockConfig:
    paths = _paths(tmp_path)
    return clock.WC2ClockConfig(
        enabled=True,
        policy_path=policy_path,
        epoch2_path=paths["epoch2"],
        collection_protocol_path=paths["protocol"],
        prepared_path=paths["prepared"],
        decision_evidence_path=paths["decision"],
        cohort_path=paths["cohort"],
        shadow_intent_path=paths["shadow_intent"],
        shadow_cycle_path=paths["shadow_cycle"],
        execution_enabled=execution_enabled,
        execution_protocol_path=(
            paths["execution_protocol"] if execution_enabled else None
        ),
        execution_runtime_path=(
            paths["execution_runtime"] if execution_enabled else None
        ),
        execution_journal_path=(
            paths["execution_journal"] if execution_enabled else None
        ),
        venue_rule_store_path=paths["venue_rules"] if execution_enabled else None,
    )


def _patch_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_freeze(**kwargs):
        return _replay_result()

    monkeypatch.setattr(clock, "freeze_coverage_context", fake_freeze)
    monkeypatch.setattr(
        clock,
        "persist_provider_divergence_for_plan",
        lambda **kwargs: None,
    )


def _seed_policy(path: Path):
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=1_000,
        collection_start_ms=2_000,
    )
    assert WC2PolicyStore(path).append(policy) is True
    return policy


def _seed_protocol(
    path: Path,
    *,
    policy,
    activation,
):
    protocol = build_wc2_collection_protocol(
        review_policy=policy,
        activation=activation,
        preregistered_at_ms=max(
            policy.preregistered_at_ms + 1,
            activation.activated_at_ms + 1,
        ),
        collection_start_ms=max(
            policy.collection_start_ms,
            activation.activated_at_ms,
        )
        + 10_000,
    )
    assert WC2CollectionProtocolStore(path).append(protocol) is True
    return protocol


def _patch_epoch2(monkeypatch: pytest.MonkeyPatch):
    activation = _activation()
    monkeypatch.setattr(
        clock,
        "read_epoch2_state_read_only",
        lambda path: SimpleNamespace(activation=activation),
    )
    return activation


def test_wc2_clock_is_disabled_by_default() -> None:
    config = clock.build_wc2_clock_config(_args())

    assert config == clock.WC2ClockConfig()
    assert config.enabled is False
    assert clock.load_wc2_prerequisites(config) is None


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

    paths = _paths(tmp_path)
    with pytest.raises(ValueError, match="collection-protocol"):
        clock.WC2ClockConfig(
            enabled=True,
            policy_path=tmp_path / "policy.sqlite3",
            epoch2_path=paths["epoch2"],
            prepared_path=paths["prepared"],
            decision_evidence_path=paths["decision"],
            cohort_path=paths["cohort"],
            shadow_intent_path=paths["shadow_intent"],
            shadow_cycle_path=paths["shadow_cycle"],
        )

    with pytest.raises(ValueError, match="immutable collection-protocol"):
        clock.WC2ClockConfig(
            enabled=True,
            policy_path=tmp_path / "policy.sqlite3",
            epoch2_path=paths["epoch2"],
            collection_protocol_path=paths["protocol"],
            prepared_path=paths["prepared"],
            decision_evidence_path=paths["decision"],
            cohort_path=paths["cohort"],
            shadow_intent_path=paths["shadow_intent"],
            shadow_cycle_path=paths["shadow_cycle"],
            maximum_issuance_delay_ms=30_000,
            horizon_bars=4,
        )


def test_wc2_execution_requires_explicit_enable_and_complete_paths(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    with pytest.raises(ValueError, match="explicit --wc2-execution-enabled"):
        clock.WC2ClockConfig(
            enabled=True,
            policy_path=tmp_path / "policy.sqlite3",
            epoch2_path=paths["epoch2"],
            collection_protocol_path=paths["protocol"],
            prepared_path=paths["prepared"],
            decision_evidence_path=paths["decision"],
            cohort_path=paths["cohort"],
            shadow_intent_path=paths["shadow_intent"],
            shadow_cycle_path=paths["shadow_cycle"],
            execution_protocol_path=paths["execution_protocol"],
        )

    with pytest.raises(ValueError, match="enabled WC2 execution requires"):
        clock.WC2ClockConfig(
            enabled=True,
            policy_path=tmp_path / "policy.sqlite3",
            epoch2_path=paths["epoch2"],
            collection_protocol_path=paths["protocol"],
            prepared_path=paths["prepared"],
            decision_evidence_path=paths["decision"],
            cohort_path=paths["cohort"],
            shadow_intent_path=paths["shadow_intent"],
            shadow_cycle_path=paths["shadow_cycle"],
            execution_enabled=True,
            execution_protocol_path=paths["execution_protocol"],
        )


def test_enabled_execution_uses_existing_live_owner_and_exact_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_cycle(monkeypatch)
    policy_path = tmp_path / "policy.sqlite3"
    policy = _seed_policy(policy_path)
    activation = _patch_epoch2(monkeypatch)
    paths = _paths(tmp_path)
    _seed_protocol(paths["protocol"], policy=policy, activation=activation)
    captured: dict[str, object] = {}

    def fake_wc2(result, **kwargs):
        return SimpleNamespace(
            status=WC2PreparedLiveStatus.SKIPPED_BEFORE_ACTIVATION,
            receipt_identity=None,
            forecast_identity=None,
            cohort_forecast_identity=None,
            paper_intent_identity=None,
        )

    def fake_outcomes(**kwargs):
        return SimpleNamespace(
            scanned=0,
            pending=0,
            resolved_fresh=0,
            recovered=0,
            cohort_idempotent=0,
        )

    def fake_execution(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            scanned_pair_n=0,
            eligible_event_n=0,
            already_terminal_n=0,
            expired_gap_n=0,
            waiting_lineage_n=0,
            waiting_execution_input_n=0,
            waiting_venue_rules_n=0,
            hold_cash_n=0,
            sizing_rejected_n=0,
            pretrade_rejected_n=0,
            executed_n=0,
            appended_record_identities=(),
        )

    monkeypatch.setattr(clock, "process_wc2_prepared_live_freeze", fake_wc2)
    monkeypatch.setattr(clock, "resolve_wc2_outcomes_once", fake_outcomes)
    monkeypatch.setattr(clock, "process_wc2_paper_execution_cycle", fake_execution)

    signal = tmp_path / "signal.sqlite3"
    candles = tmp_path / "candles.sqlite3"
    status = asyncio.run(
        clock.run(
            signal,
            plan=LiveCoveragePlan.current_pilot(),
            candle_cache_path=candles,
            provider_divergence_path=tmp_path / "divergence.sqlite3",
            wc2_config=_config(
                tmp_path,
                policy_path=policy_path,
                execution_enabled=True,
            ),
        )
    )

    assert status == 0
    assert captured["signal_ledger_path"] == signal
    assert captured["decision_evidence_path"] == paths["decision"]
    assert captured["cohort_journal_path"] == paths["cohort"]
    assert captured["epoch2_path"] == paths["epoch2"]
    assert captured["execution_protocol_path"] == paths["execution_protocol"]
    assert captured["runtime_activation_path"] == paths["execution_runtime"]
    assert captured["execution_journal_path"] == paths["execution_journal"]
    assert captured["candle_cache_path"] == candles
    assert captured["venue_rule_store_path"] == paths["venue_rules"]
    assert isinstance(captured["observed_at_ms"], int)


def test_disabled_clock_never_calls_wc2_or_creates_wc2_databases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_cycle(monkeypatch)
    paths = _paths(tmp_path)

    def forbidden_wc2(*args, **kwargs):
        raise AssertionError("WC2 processor must remain disabled")

    monkeypatch.setattr(
        clock,
        "process_wc2_prepared_live_freeze",
        forbidden_wc2,
    )
    monkeypatch.setattr(
        clock,
        "process_wc2_paper_execution_cycle",
        forbidden_wc2,
    )

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
    assert all(not path.exists() for path in paths.values())


def test_enabled_clock_passes_exact_protocol_runtime_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_cycle(monkeypatch)
    policy_path = tmp_path / "policy.sqlite3"
    policy = _seed_policy(policy_path)
    activation = _patch_epoch2(monkeypatch)
    paths = _paths(tmp_path)
    protocol = _seed_protocol(
        paths["protocol"],
        policy=policy,
        activation=activation,
    )
    captured = []

    def fake_wc2(result, **kwargs):
        captured.append((result, kwargs))
        return SimpleNamespace(
            status=WC2PreparedLiveStatus.SKIPPED_BEFORE_ACTIVATION,
            receipt_identity=None,
            forecast_identity=None,
            cohort_forecast_identity=None,
            paper_intent_identity=None,
        )

    monkeypatch.setattr(
        clock,
        "process_wc2_prepared_live_freeze",
        fake_wc2,
    )
    config = _config(tmp_path, policy_path=policy_path)

    status = asyncio.run(
        clock.run(
            tmp_path / "signal.sqlite3",
            plan=LiveCoveragePlan.current_pilot(),
            candle_cache_path=tmp_path / "candles.sqlite3",
            provider_divergence_path=tmp_path / "divergence.sqlite3",
            wc2_config=config,
        )
    )

    assert status == 0
    assert len(captured) == len(
        LiveCoveragePlan.current_pilot().enabled_contexts
    )
    result, kwargs = captured[0]
    assert result.status is LiveFreezeStatus.ALREADY_FROZEN
    assert kwargs["policy"] == policy
    assert kwargs["activation"] == activation
    assert (
        kwargs["maximum_issuance_delay_ms"]
        == protocol.maximum_issuance_delay_ms
    )
    assert kwargs["horizon_bars"] == protocol.horizon_bars_for(
        _context().timeframe
    )
    assert kwargs["collection_start_ms"] == protocol.collection_start_ms
    assert kwargs["collection_protocol_identity"] == protocol.protocol_identity
    assert kwargs["base_asset"] == "BTC"
    assert kwargs["prepared_journal"].path == paths["prepared"]
    assert kwargs["decision_ledger"].path == paths["decision"]
    assert kwargs["cohort_journal"].path == paths["cohort"]
    assert kwargs["shadow_journal"].path == paths["shadow_intent"]
    assert kwargs["shadow_manifest"].path == paths["shadow_cycle"]


def test_collection_protocol_plan_mismatch_fails_before_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "policy.sqlite3"
    policy = _seed_policy(policy_path)
    activation = _patch_epoch2(monkeypatch)
    paths = _paths(tmp_path)
    _seed_protocol(
        paths["protocol"],
        policy=policy,
        activation=activation,
    )
    called = {"network": 0}

    async def forbidden_freeze(**kwargs):
        called["network"] += 1
        raise AssertionError("network must not start")

    monkeypatch.setattr(clock, "freeze_coverage_context", forbidden_freeze)

    status = asyncio.run(
        clock.run(
            tmp_path / "signal.sqlite3",
            plan=_plan(),
            candle_cache_path=tmp_path / "candles.sqlite3",
            provider_divergence_path=tmp_path / "divergence.sqlite3",
            wc2_config=_config(tmp_path, policy_path=policy_path),
        )
    )

    assert status == 1
    assert called["network"] == 0


def test_enabled_clock_missing_policy_fails_before_network_or_runtime_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "missing-policy.sqlite3"
    paths = _paths(tmp_path)
    called = {"network": 0}

    async def forbidden_freeze(**kwargs):
        called["network"] += 1
        raise AssertionError("network cycle must not start")

    monkeypatch.setattr(clock, "freeze_coverage_context", forbidden_freeze)
    status = asyncio.run(
        clock.run(
            tmp_path / "signal.sqlite3",
            plan=_plan(),
            candle_cache_path=tmp_path / "candles.sqlite3",
            provider_divergence_path=tmp_path / "divergence.sqlite3",
            wc2_config=_config(tmp_path, policy_path=policy_path),
        )
    )

    assert status == 1
    assert called["network"] == 0
    assert not policy_path.exists()
    assert all(not path.exists() for path in paths.values())


def test_enabled_clock_missing_epoch2_fails_before_network_or_runtime_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "policy.sqlite3"
    _seed_policy(policy_path)
    paths = _paths(tmp_path)
    paths["protocol"].touch()
    called = {"network": 0}

    async def forbidden_freeze(**kwargs):
        called["network"] += 1
        raise AssertionError("network cycle must not start")

    monkeypatch.setattr(clock, "freeze_coverage_context", forbidden_freeze)
    status = asyncio.run(
        clock.run(
            tmp_path / "signal.sqlite3",
            plan=_plan(),
            candle_cache_path=tmp_path / "candles.sqlite3",
            provider_divergence_path=tmp_path / "divergence.sqlite3",
            wc2_config=_config(tmp_path, policy_path=policy_path),
        )
    )

    assert status == 1
    assert called["network"] == 0
    assert not paths["epoch2"].exists()
    assert not paths["prepared"].exists()
    assert not paths["decision"].exists()
    assert not paths["cohort"].exists()
    assert not paths["shadow_intent"].exists()
    assert not paths["shadow_cycle"].exists()


def test_wc2_runtime_error_fail_stops_before_second_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "policy.sqlite3"
    policy = _seed_policy(policy_path)
    activation = _patch_epoch2(monkeypatch)
    paths = _paths(tmp_path)
    _seed_protocol(
        paths["protocol"],
        policy=policy,
        activation=activation,
    )
    calls = {"freeze": 0, "wc2": 0, "divergence": 0}

    async def fake_freeze(**kwargs):
        calls["freeze"] += 1
        return _replay_result()

    def fail_wc2(*args, **kwargs):
        calls["wc2"] += 1
        raise ValueError("forced prepared persistence failure")

    def divergence(**kwargs):
        calls["divergence"] += 1

    monkeypatch.setattr(clock, "freeze_coverage_context", fake_freeze)
    monkeypatch.setattr(
        clock,
        "process_wc2_prepared_live_freeze",
        fail_wc2,
    )
    monkeypatch.setattr(
        clock,
        "persist_provider_divergence_for_plan",
        divergence,
    )

    status = asyncio.run(
        clock.run(
            tmp_path / "signal.sqlite3",
            plan=LiveCoveragePlan.current_pilot(),
            candle_cache_path=tmp_path / "candles.sqlite3",
            provider_divergence_path=tmp_path / "divergence.sqlite3",
            wc2_config=_config(tmp_path, policy_path=policy_path),
        )
    )

    assert status == 1
    assert calls == {"freeze": 1, "wc2": 1, "divergence": 0}


def test_activation_post_receipt_gap_fails_cycle_but_continues_contexts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "policy.sqlite3"
    policy = _seed_policy(policy_path)
    activation = _patch_epoch2(monkeypatch)
    paths = _paths(tmp_path)
    _seed_protocol(
        paths["protocol"],
        policy=policy,
        activation=activation,
    )
    calls = {"freeze": 0, "wc2": 0, "divergence": 0}

    async def fake_freeze(**kwargs):
        calls["freeze"] += 1
        return _replay_result()

    def gap(*args, **kwargs):
        calls["wc2"] += 1
        return SimpleNamespace(
            status=WC2PreparedLiveStatus.NO_PREPARED_RECEIPT,
            receipt_identity=None,
            forecast_identity=None,
            cohort_forecast_identity=None,
            paper_intent_identity=None,
        )

    def divergence(**kwargs):
        calls["divergence"] += 1

    monkeypatch.setattr(clock, "freeze_coverage_context", fake_freeze)
    monkeypatch.setattr(clock, "process_wc2_prepared_live_freeze", gap)
    monkeypatch.setattr(clock, "persist_provider_divergence_for_plan", divergence)

    plan = LiveCoveragePlan.current_pilot()
    status = asyncio.run(
        clock.run(
            tmp_path / "signal.sqlite3",
            plan=plan,
            candle_cache_path=tmp_path / "candles.sqlite3",
            provider_divergence_path=tmp_path / "divergence.sqlite3",
            wc2_config=_config(tmp_path, policy_path=policy_path),
        )
    )

    assert status == 1
    assert calls == {
        "freeze": len(plan.enabled_contexts),
        "wc2": len(plan.enabled_contexts),
        "divergence": 1,
    }


def test_wc2_base_asset_is_explicit_usdt_only() -> None:
    assert clock.wc2_base_asset("BTCUSDT") == "BTC"

    with pytest.raises(ValueError, match="USDT"):
        clock.wc2_base_asset("BTCUSD")
