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
    assert "os.fork()" in source
    assert "os.setsid()" in source
    assert 'os.environ.pop("RUNNER_TRACKING_ID", None)' in source
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
    assert '"$PYTHON" "$SUPERVISOR" --daemonize' in source
    assert "nohup " not in source
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


def test_market_tape_supervisor_has_single_top_level_recovery_owner() -> None:
    ssd_supervisor = (ROOT / "ops/ssd_runtime_supervisor.sh").read_text()
    installer = (ROOT / "ops/install_market_tape_runtime.sh").read_text()

    assert "ensure_market_tape_supervisor" in ssd_supervisor
    assert "start_market_tape_supervisor.sh" in ssd_supervisor
    assert 'MARKET_TAPE_INSTALL_ENABLE_LAUNCHD:-0' in installer
    assert "MARKET_TAPE_LAUNCHAGENT_DISABLED_BY_DEFAULT=YES" in installer
