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


def test_market_tape_adoption_requires_lock_holder_and_exact_python_script() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert 'local py="$DEV/.venv/bin/python"' in text
    assert '/bin/ps -ww -p "$pid" -o uid=,args=' in text
    assert 'exit($1 == 504 && $2 == py && $3 == runner ? 0 : 1)' in text
    assert 'comm=tolower($1)' not in text
    assert 'market_tape_pid_is_expected "$pid" || return 1' in text
    assert 'market_tape_pid_is_expected "$pid"; then' in text


def test_market_tape_owner_requires_current_bybit_ws_endpoint() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "market_tape_pid_is_owned()" in text
    assert 'awk -v py="$py" -v runner="$runner" -v ws="$BYBIT_WS_URL"' in text
    assert 'if ($i == "--bybit-ws-url" && $(i + 1) == ws)' in text
    assert "market_tape_stale_config pid=$pid action=restart" in text
    assert 'stop_market_tape_pid "$pid"' in text
