from __future__ import annotations

from pathlib import Path

import pytest

import ops.run_onchain_capital_flow_snapshot as runner

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "ops" / "ssd_runtime_supervisor.sh"
RUNNER = ROOT / "ops" / "run_onchain_capital_flow_snapshot.py"


def test_onchain_runner_uses_separate_canonical_runtime_boundary() -> None:
    assert str(runner.DEFAULT_ONCHAIN_DB).endswith(
        "/Development/runtime/onchain/onchain_capital_flow.sqlite3"
    )
    assert str(runner.DEFAULT_SOURCE_CONTRACT_DB).endswith(
        "/Development/runtime/onchain/source_contract.sqlite3"
    )
    assert str(runner.DEFAULT_LOCK).endswith(
        "/Development/runtime/onchain/onchain_capital_flow_snapshot.lock"
    )
    assert (
        runner.DEFAULT_DEFILLAMA_BASE_URL
        == "https://stablecoins.llama.fi"
    )


def test_onchain_runner_rejects_noncanonical_paths() -> None:
    with pytest.raises(ValueError, match="canonical SSD path"):
        runner._require_canonical_path(
            Path("/tmp/onchain.sqlite3"),
            label="onchain db",
        )


def test_onchain_runner_is_public_read_only_source_without_secret_contract() -> None:
    text = RUNNER.read_text(encoding="utf-8").lower()

    assert "defillamastablecoinsadapter" in text
    assert "persist_defillama_stablecoin_snapshot" in text
    assert "source=defillama_public_no_auth" in text
    assert "exchange_flow_provider=unavailable_explicit" in text
    for forbidden in (
        "api_key",
        "authorization:",
        "bearer ",
        "place_order",
        "submit_order",
        "real_capital=1",
    ):
        assert forbidden not in text
    assert "real_capital=0" in text


def test_supervisor_schedules_onchain_collector_every_300_seconds() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "run_onchain_capital_flow_snapshot_clock()" in text
    assert 'local runtime="$DEV/runtime/onchain"' in text
    assert 'local db="$runtime/onchain_capital_flow.sqlite3"' in text
    assert 'local source_contract="$runtime/source_contract.sqlite3"' in text
    assert 'last_onchain_clock=0' in text
    assert "if [ $((now-last_onchain_clock)) -ge 300 ]; then" in text
    assert "run_onchain_capital_flow_snapshot_clock" in text
    assert '>>"$LOGDIR/onchain-snapshot.out.log"' in text


def test_onchain_collector_does_not_replace_existing_market_tape_clock() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "run_market_tape_snapshot_clock" in text
    assert "if [ $((now-last_data_clock)) -ge 60 ]; then" in text
    assert "run_wc2_live_clock" in text
    assert "run_onchain_capital_flow_snapshot_clock" in text
