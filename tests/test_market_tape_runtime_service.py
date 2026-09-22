from __future__ import annotations

import plistlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
    assert payload["WorkingDirectory"] == (
        "/Volumes/Crypto-504/Crypto-Signal/MarketTape"
    )
    arguments = payload["ProgramArguments"]
    assert arguments == [
        "/Volumes/Crypto-504/Crypto-Signal/MarketTape/.venv/bin/python",
        (
            "/Volumes/Crypto-504/Crypto-Signal/MarketTape/"
            "ops/run_market_tape_runtime.py"
        ),
    ]
    assert payload["EnvironmentVariables"]["PYTHONPATH"] == (
        "/Volumes/Crypto-504/Crypto-Signal/MarketTape/src"
    )
    assert payload["StandardOutPath"].startswith("/Volumes/Crypto-504/")
    assert payload["StandardErrorPath"].startswith("/Volumes/Crypto-504/")


def test_market_tape_installer_preserves_uid504_boundary() -> None:
    source = (ROOT / "ops/install_market_tape_runtime.sh").read_text()

    assert 'UID_EXPECTED="504"' in source
    assert 'ROOT="/Volumes/Crypto-504/Crypto-Signal"' in source
    assert 'STABLE="$ROOT/MarketTape"' in source
    assert "com.cryptosignal.markettape" in source
    assert "launchctl bootstrap" in source
    assert "REAL_CAPITAL=0" in source


def test_market_tape_runtime_has_no_internal_disk_data_fallback() -> None:
    source = (ROOT / "ops/run_market_tape_runtime.py").read_text()

    assert 'ROOT = Path("/Volumes/Crypto-504/Crypto-Signal")' in source
    assert 'VOLUME = Path("/Volumes/Crypto-504")' in source
    assert "Development/runtime/market_tape" in source
    assert "/Users/" not in source
    assert "REAL_CAPITAL=0" in source
