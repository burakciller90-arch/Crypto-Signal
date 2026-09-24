from __future__ import annotations

from pathlib import Path

import ops.wc1_market_tape_restart_acceptance as acceptance


def test_parse_process_identity_accepts_macos_truncated_comm_shape() -> None:
    raw = (
        "504 /Volumes/Crypto-504/Crypto-Signal/Development/.venv/bin/python "
        "/Volumes/Crypto-504/Crypto-Signal/Development/ops/run_market_tape_stream.py "
        "--max-events 0\n"
    )

    uid, argv = acceptance._parse_process_identity(raw)

    assert uid == 504
    assert argv[:2] == (
        "/Volumes/Crypto-504/Crypto-Signal/Development/.venv/bin/python",
        "/Volumes/Crypto-504/Crypto-Signal/Development/ops/run_market_tape_stream.py",
    )


def test_expected_collector_requires_exact_uid_python_and_runner(monkeypatch) -> None:
    runner = Path(
        "/Volumes/Crypto-504/Crypto-Signal/Development/ops/run_market_tape_stream.py"
    )
    python = "/Volumes/Crypto-504/Crypto-Signal/Development/.venv/bin/python"

    monkeypatch.setattr(
        acceptance,
        "_process_identity",
        lambda _pid: (504, (python, str(runner), "--max-events", "0")),
    )
    assert acceptance._is_expected_collector(29407, runner) is True

    monkeypatch.setattr(
        acceptance,
        "_process_identity",
        lambda _pid: (
            504,
            (python, "/Volumes/Crypto-504/Crypto-Signal/MarketTape/ops/run_market_tape_runtime.py"),
        ),
    )
    assert acceptance._is_expected_collector(95968, runner) is False

    monkeypatch.setattr(
        acceptance,
        "_process_identity",
        lambda _pid: (501, (python, str(runner))),
    )
    assert acceptance._is_expected_collector(29407, runner) is False
