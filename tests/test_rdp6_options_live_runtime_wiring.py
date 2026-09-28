from __future__ import annotations

from pathlib import Path

import pytest

import ops.run_live_evidence_clock as clock

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "ops" / "ssd_runtime_supervisor.sh"
SNAPSHOT = ROOT / "ops" / "run_market_tape_snapshot.py"


def test_stream_options_surface_requires_market_tape_and_explicit_stream() -> None:
    options_path = Path("/tmp/options.sqlite3")
    market_path = Path("/tmp/market.sqlite3")
    ledger_path = Path("/tmp/stream.sqlite3")

    with pytest.raises(ValueError, match="explicit --stream-enabled"):
        clock.StreamClockConfig(options_surface_path=options_path)

    with pytest.raises(ValueError, match="requires --stream-market-tape"):
        clock.StreamClockConfig(
            enabled=True,
            ledger_path=ledger_path,
            options_surface_path=options_path,
        )

    config = clock.StreamClockConfig(
        enabled=True,
        ledger_path=ledger_path,
        market_tape_path=market_path,
        options_surface_path=options_path,
        family_symbols=("BTCUSDT", "ETHUSDT"),
    )
    assert config.options_surface_path == options_path
    assert config.market_tape_path == market_path


def test_live_clock_cli_exposes_options_surface_and_family_pass_through() -> None:
    text = (
        ROOT / "ops" / "run_live_evidence_clock.py"
    ).read_text(encoding="utf-8")

    assert '"--stream-options-surface"' in text
    assert (
        "options_surface_path=getattr(args, "
        '"stream_options_surface", None)'
    ) in text
    assert (
        "options_surface_path=selected_stream.options_surface_path"
        in text
    )


def test_market_tape_snapshot_collects_btc_eth_options_on_existing_clock() -> None:
    text = SNAPSHOT.read_text(encoding="utf-8")

    assert 'DEFAULT_OPTION_BASE_COINS = ("BTC", "ETH")' in text
    assert '"--options-db"' in text
    assert '"--bybit-options-base-url"' in text
    assert "BybitOptionsAdapter(base_url=options_base_url)" in text
    assert "options_store.initialize()" in text
    assert "await options.fetch_source_snapshot(" in text
    assert "persist_bybit_option_surface_snapshot(" in text
    assert "MARKET_TAPE_OPTIONS_OK" in text
    assert "MARKET_TAPE_OPTIONS_ERROR" in text
    assert "OPTIONS_SOURCE_CONTRACT=OBSERVED_OR_FAIL_CLOSED" in text


def test_supervisor_uses_proven_regional_options_source_and_same_60s_clock() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert (
        'BYBIT_OPTIONS_REST_BASE_URL="${CRYPTO_SIGNAL_BYBIT_OPTIONS_REST_BASE_URL:-'
        '$BYBIT_REST_BASE_URL}"'
    ) in text
    assert 'local options="$runtime/options_surface.sqlite3"' in text
    assert '--options-db "$options"' in text
    assert (
        '--bybit-options-base-url "$BYBIT_OPTIONS_REST_BASE_URL"'
        in text
    )
    assert 'local options_surface="$runtime/market_tape/options_surface.sqlite3"' in text
    assert '--stream-options-surface "$options_surface"' in text
    assert "if [ $((now-last_data_clock)) -ge 60 ]; then" in text
    assert "run_market_tape_snapshot_clock" in text
    assert "run_wc2_live_clock" in text


def test_options_runtime_wiring_does_not_add_trade_or_capital_authority() -> None:
    snapshot_text = SNAPSHOT.read_text(encoding="utf-8")
    supervisor_text = SUPERVISOR.read_text(encoding="utf-8")

    forbidden = (
        "place_order",
        "submit_order",
        "api_secret",
        "private_key",
        "real_capital=1",
    )
    combined = (snapshot_text + supervisor_text).lower()
    assert all(value not in combined for value in forbidden)
    assert "REAL_CAPITAL=0" in snapshot_text
    assert "REAL_CAPITAL=0" in supervisor_text
