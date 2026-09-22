from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_market_tape_supervisor_is_uid504_ssd_data_bound() -> None:
    source = (
        ROOT / "ops/market_tape/run_market_tape_supervisor.py"
    ).read_text()

    assert 'ROOT = Path("/Volumes/Crypto-504/Crypto-Signal")' in source
    assert 'Path("/Users/crypto-signal-agent/.crypto-signal-runtime")' in source
    assert "os.getuid() != 504" in source
    assert "fcntl.LOCK_EX | fcntl.LOCK_NB" in source
    assert 'environment.pop("RUNNER_TRACKING_ID", None)' in source
    assert 'str(PYTHON), str(RUNTIME)' in source
    assert 'ROOT / "ServiceLogs/market-tape-supervisor-runtime.out.log"' in source
    assert '"real_capital": 0' in source
    assert "RESTART_DELAY_SECONDS = 30" in source


def test_market_tape_supervisor_launcher_detaches_from_runner_cleanup() -> None:
    source = (
        ROOT / "ops/market_tape/start_market_tape_supervisor.sh"
    ).read_text()

    assert 'UID_EXPECTED="504"' in source
    assert 'ROOT="/Volumes/Crypto-504/Crypto-Signal"' in source
    assert "unset RUNNER_TRACKING_ID" in source
    assert 'nohup "$PYTHON" "$SUPERVISOR"' in source
    assert 'PID_FILE="$CONTROL/market-tape-supervisor.pid"' in source
    assert "REAL_CAPITAL=0" in source


def test_market_tape_supervisor_stop_is_bounded_and_explicit() -> None:
    source = (
        ROOT / "ops/market_tape/stop_market_tape_supervisor.sh"
    ).read_text()

    assert 'UID_EXPECTED="504"' in source
    assert 'STOP_FILE="$CONTROL/market-tape-supervisor.stop"' in source
    assert 'kill -TERM "$pid"' in source
    assert 'kill -KILL "$pid"' in source
    assert "REAL_CAPITAL=0" in source
