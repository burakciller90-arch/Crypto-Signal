from __future__ import annotations

from pathlib import Path

import pytest

import ops.run_live_evidence_clock as clock

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "ops" / "ssd_runtime_supervisor.sh"
LIVE_CLOCK = ROOT / "ops" / "run_live_evidence_clock.py"


def test_stream_onchain_paths_require_pair_and_explicit_stream() -> None:
    ledger = Path("/tmp/stream.sqlite3")
    onchain = Path("/tmp/onchain.sqlite3")
    source = Path("/tmp/source.sqlite3")
    market = Path("/tmp/market.sqlite3")

    with pytest.raises(ValueError, match="explicit --stream-enabled"):
        clock.StreamClockConfig(onchain_capital_flow_path=onchain)

    with pytest.raises(ValueError, match="requires both capital-flow"):
        clock.StreamClockConfig(
            enabled=True,
            ledger_path=ledger,
            market_tape_path=market,
            family_symbols=("BTCUSDT",),
            onchain_capital_flow_path=onchain,
        )

    config = clock.StreamClockConfig(
        enabled=True,
        ledger_path=ledger,
        market_tape_path=market,
        family_symbols=("BTCUSDT",),
        onchain_capital_flow_path=onchain,
        onchain_source_contract_path=source,
    )
    assert config.onchain_capital_flow_path == onchain
    assert config.onchain_source_contract_path == source


def test_live_clock_exposes_separate_rdp7_onchain_family_inputs() -> None:
    text = LIVE_CLOCK.read_text(encoding="utf-8")

    assert '"--stream-onchain-capital-flow"' in text
    assert '"--stream-onchain-source-contract"' in text
    assert "build_onchain_family_snapshots(" in text
    assert "ONCHAIN_FAMILY_PATH=RDP7_SEPARATE_SOURCE" in text
    assert "ONCHAIN_STANDALONE=DEFERRED_SOURCE" not in text
    assert "EXCHANGE_FLOW_PROVIDER=UNAVAILABLE_EXPLICIT" in text
    assert "LARGE_TRANSFER_PROVIDER=UNAVAILABLE_EXPLICIT" in text
    assert "WALLET_COHORT_PROVIDER=UNAVAILABLE_EXPLICIT" in text
    assert "STABLECOIN_DIRECTION=NONE" in text


def test_supervisor_passes_canonical_onchain_stores_without_new_clock() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert (
        'local onchain_capital_flow="$runtime/onchain/'
        'onchain_capital_flow.sqlite3"'
    ) in text
    assert (
        'local onchain_source_contract="$runtime/onchain/'
        'source_contract.sqlite3"'
    ) in text
    assert (
        '--stream-onchain-capital-flow "$onchain_capital_flow"'
        in text
    )
    assert (
        '--stream-onchain-source-contract "$onchain_source_contract"'
        in text
    )
    assert "if [ $((now-last_data_clock)) -ge 60 ]; then" in text
    assert "run_wc2_live_clock" in text
    assert "if [ $((now-last_onchain_clock)) -ge 300 ]; then" in text
    assert "run_onchain_capital_flow_snapshot_clock" in text


def test_rdp7_family_wiring_adds_no_trade_or_real_capital_authority() -> None:
    combined = (
        LIVE_CLOCK.read_text(encoding="utf-8")
        + SUPERVISOR.read_text(encoding="utf-8")
    ).lower()

    for forbidden in (
        "real_capital=1",
        "place_order",
        "submit_order",
        "private_key",
    ):
        assert forbidden not in combined
    assert "real_capital=0" in combined
