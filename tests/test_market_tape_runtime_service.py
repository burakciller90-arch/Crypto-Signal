import pathlib
import plistlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_market_tape_launchagent_is_ssd_only_and_keepalive() -> None:
    path = (
        ROOT
        / "ops/market_tape/launchd/com.cryptosignal.markettape.plist"
    )
    payload = plistlib.loads(path.read_bytes())

    assert payload["Label"] == "com.cryptosignal.markettape"
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert payload["ThrottleInterval"] == 30
    assert "WorkingDirectory" not in payload
    arguments = payload["ProgramArguments"]
    assert arguments == [
        "/bin/bash",
        (
            "/Volumes/Crypto-504/Crypto-Signal/MarketTape/"
            "ops/market_tape/run_market_tape_launchd.sh"
        ),
    ]
    assert payload["StandardOutPath"].startswith("/Volumes/Crypto-504/")
    assert payload["StandardErrorPath"].startswith("/Volumes/Crypto-504/")


def test_market_tape_installer_preserves_uid504_boundary() -> None:
    source = (ROOT / "ops/install_market_tape_runtime.sh").read_text()

    assert 'UID_EXPECTED="504"' in source
    assert 'ROOT="/Volumes/Crypto-504/Crypto-Signal"' in source
    assert 'STABLE="$ROOT/MarketTape"' in source
    assert "com.cryptosignal.markettape" in source
    assert "run_market_tape_launchd.sh" in source
    assert "archive_hot_to_parquet.py" in source
    assert 'RuntimeEnvs/market-tape-cold' in source
    assert 'PYARROW_VERSION="22.0.0"' in source
    assert "launchctl bootstrap" in source
    assert "MARKET_TAPE_INSTALL_NO_START" in source
    assert "MARKET_TAPE_LAUNCHAGENT_PREPARE_ONLY_PASS=YES" in source
    assert "REAL_CAPITAL=0" in source


def test_market_tape_runtime_has_no_internal_disk_data_fallback() -> None:
    source = (ROOT / "ops/run_market_tape_runtime.py").read_text()

    assert 'ROOT = Path("/Volumes/Crypto-504/Crypto-Signal")' in source
    assert 'VOLUME = Path("/Volumes/Crypto-504")' in source
    assert "Development/runtime/market_tape" in source
    assert 'COLD_DIR = ROOT / "MarketTapeCold"' in source
    assert 'COLD_PYTHON = ROOT / "RuntimeEnvs/market-tape-cold/bin/python"' in source
    assert "REAL_CAPITAL=0" in source

def test_market_tape_launchd_wrapper_is_uid504_and_ssd_bound() -> None:
    source = (
        ROOT / "ops/market_tape/run_market_tape_launchd.sh"
    ).read_text()

    assert 'ROOT="/Volumes/Crypto-504/Crypto-Signal"' in source
    assert 'PYTHON="$ROOT/Development/.venv/bin/python"' in source
    assert 'RUNTIME="$STABLE/ops/run_market_tape_runtime.py"' in source
    assert 'COLD_PYTHON="$ROOT/RuntimeEnvs/market-tape-cold/bin/python"' in source
    assert 'COLD_ARCHIVER="$STABLE/ops/market_tape/archive_hot_to_parquet.py"' in source
    assert 'if [ "$(id -u)" != "504" ]' in source
    assert 'export PYTHONPATH="$STABLE/src"' in source
    assert 'exec "$PYTHON" "$RUNTIME"' in source



def test_market_tape_runtime_archives_before_collecting_and_never_prunes_cold() -> None:
    source = (ROOT / "ops/run_market_tape_runtime.py").read_text()

    assert "_run_cold_archive()" in source
    assert "evaluate_archive_headroom" in source
    assert "MarketTapeCold" in source
    assert "RuntimeEnvs/market-tape-cold/bin/python" in source
    assert "enforce_generation_retention" not in source
    assert "reclaim_for_capacity" not in source
