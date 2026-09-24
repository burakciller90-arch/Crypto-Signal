from __future__ import annotations

from pathlib import Path

import ops.wc1_market_tape_restart_acceptance as restart_acceptance


def test_expected_collector_uses_exact_uid_python_and_script(
    monkeypatch,
) -> None:
    runner = Path(
        "/Volumes/Crypto-504/Crypto-Signal/Development/"
        "ops/run_market_tape_stream.py"
    )
    python = str(
        Path("/Volumes/Crypto-504/Crypto-Signal/Development/")
        / ".venv"
        / "bin"
        / "python"
    )

    monkeypatch.setattr(
        restart_acceptance,
        "_process_identity",
        lambda _pid: (504, (python, str(runner))),
    )
    assert restart_acceptance._is_expected_collector(29407, runner) is True

    monkeypatch.setattr(
        restart_acceptance,
        "_process_identity",
        lambda _pid: (
            504,
            (
                python,
                "/Volumes/Crypto-504/Crypto-Signal/MarketTape/ops/run_market_tape_runtime.py",
            ),
        ),
    )
    assert restart_acceptance._is_expected_collector(95968, runner) is False

    monkeypatch.setattr(
        restart_acceptance,
        "_process_identity",
        lambda _pid: (501, (python, str(runner))),
    )
    assert restart_acceptance._is_expected_collector(29407, runner) is False


def test_process_identity_parser_does_not_depend_on_macos_comm(
    monkeypatch,
) -> None:
    class Result:
        stdout = (
            "  504 /Volumes/Crypto-504/Crypto-Signal/Development/.venv/bin/python "
            "/Volumes/Crypto-504/Crypto-Signal/Development/ops/run_market_tape_stream.py\n"
        )

    monkeypatch.setattr(
        restart_acceptance.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )

    uid, argv = restart_acceptance._process_identity(29407)

    assert uid == 504
    assert argv[0].endswith("/Development/.venv/bin/python")
    assert argv[1].endswith("/Development/ops/run_market_tape_stream.py")
