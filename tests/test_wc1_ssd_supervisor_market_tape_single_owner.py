from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "ops" / "ssd_runtime_supervisor.sh"


def test_ssd_supervisor_owns_market_tape_stream_once() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "market_tape_pid_is_expected()" in text
    assert "adopt_market_tape_stream()" in text
    assert "start_market_tape_stream()" in text
    assert 'local runner="$DEV/ops/run_market_tape_stream.py"' in text
    assert 'local db="$runtime/market_tape.sqlite3"' in text
    assert 'local raw="$runtime/raw_market_tape.sqlite3"' in text
    assert 'local lock="$runtime/market_tape_stream.lock"' in text
    assert 'local collector_runtime="$runtime/collector_runtime.sqlite3"' in text
    assert 'local gaps="$runtime/market_data_gaps.sqlite3"' in text
    assert '/usr/sbin/lsof -t "$lock"' in text
    assert 'exec "$py" "$runner"' in text
    assert '--runtime-status-db "$collector_runtime"' in text
    assert '--gap-ledger-db "$gaps"' in text
    assert (
        'BYBIT_WS_URL="${CRYPTO_SIGNAL_BYBIT_WS_URL:-'
        'wss://stream.bybit.tr/v5/public/spot}"'
    ) in text
    assert '--bybit-ws-url "$BYBIT_WS_URL"' in text
    assert "--heartbeat-interval-ms 10000" in text
    assert "--max-ingestion-silence-ms 60000" in text
    assert "--max-events 0" in text
    assert 'echo "$pid" > "$ROOT/market-tape-stream.pid"' in text
    assert "start_market_tape_stream\n  now=" in text
    assert "FAIL_CLOSED=YES REAL_CAPITAL=0" in text
    assert "market_tape_started pid=$pid REAL_CAPITAL=0" in text


def test_market_tape_adoption_requires_lock_holder_uid_and_exact_runner() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert '/bin/ps -ww -p "$pid" -o uid=,args=' in text
    assert 'if ($1 != 504)' in text
    assert 'if ($i == runner)' in text
    assert 'comm=tolower($1)' not in text
    assert 'if ! market_tape_pid_is_expected "$pid"; then' in text
    assert 'market_tape_pid_is_owned "$pid"; then' in text
    assert 'market_tape_pid_is_expected "$pid"; then' in text


def test_market_tape_owner_requires_current_bybit_ws_endpoint() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "market_tape_pid_is_owned()" in text
    assert 'awk -v runner="$runner" -v ws="$BYBIT_WS_URL"' in text
    assert 'if ($i == "--bybit-ws-url" && i < NF && $(i + 1) == ws)' in text
    assert "market_tape_stale_config pid=$pid action=restart" in text
    assert 'stop_market_tape_pid "$pid"' in text


def test_live_clock_uses_region_appropriate_rest_endpoints() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert (
        'BYBIT_REST_BASE_URL="${CRYPTO_SIGNAL_BYBIT_REST_BASE_URL:-'
        'https://api.bybit.tr}"'
    ) in text
    assert (
        'BINANCE_REST_BASE_URL="${CRYPTO_SIGNAL_BINANCE_REST_BASE_URL:-'
        'https://api.binance.me}"'
    ) in text
    assert (
        'BINANCE_API_VARIANT="${CRYPTO_SIGNAL_BINANCE_API_VARIANT:-tr_main}"'
        in text
    )
    assert '--bybit-base-url "$BYBIT_REST_BASE_URL"' in text
    assert '--binance-base-url "$BINANCE_REST_BASE_URL"' in text
    assert '--binance-api-variant "$BINANCE_API_VARIANT"' in text


def test_market_tape_supervisor_requires_fresh_heartbeat_after_startup_grace() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "market_tape_pid_is_healthy()" in text
    assert "market_tape_pidfile_age_seconds()" in text
    assert 'if market_tape_pid_is_healthy "$pid"; then' in text
    assert 'if [ "$age" -le 45 ]; then' in text
    assert "market_tape_startup_grace pid=$pid age_s=$age" in text
    assert "market_tape_unhealthy pid=$pid age_s=$age action=restart" in text
    assert 'now_ms - observed_at_ms > 30_000' in text



def test_market_data_clocks_run_inside_closed_candle_freshness_budget() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "last_data_clock=0" in text
    assert "last_aux_clock=0" in text
    assert "if [ $((now-last_data_clock)) -ge 60 ]; then" in text
    assert "run_market_tape_snapshot_clock" in text
    assert "run_wc2_live_clock" in text
    assert 'last_data_clock="$now"' in text
    assert "if [ $((now-last_aux_clock)) -ge 120 ]; then" in text
    assert 'last_aux_clock="$now"' in text
