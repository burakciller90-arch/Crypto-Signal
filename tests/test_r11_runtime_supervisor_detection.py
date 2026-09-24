from pathlib import Path

import ops.r11_runtime_acceptance as runtime_acceptance

SCRIPT = Path("ops/r11/start_ssd_runtime.command")


def test_runtime_start_detects_only_real_bash_supervisor_process() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("find_supervisor_pid()")
    end = text.index("\npid=", start)
    block = text[start:end]

    assert "/bin/ps -axo pid=,comm=,args=" in block
    assert '($2 == "bash" || $2 == "/bin/bash")' in block
    assert 'index($0, needle) > 0' in block
    assert "pid=,command=" not in block


def test_r11_acceptance_ignores_helper_process_with_supervisor_path(
    monkeypatch,
) -> None:
    root = Path("/Volumes/Crypto-504/Crypto-Signal")
    ps = "\n".join(
        (
            "78361 1 crypto-signal-agent /bin/bash "
            "/bin/bash /Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.sh",
            "81786 81780 crypto-signal-agent /usr/bin/awk "
            "/usr/bin/awk -v needle "
            "/Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.sh",
            "81826 78361 crypto-signal-agent Python "
            "/Volumes/Crypto-504/Crypto-Signal/Product/.venv/bin/python "
            "/Volumes/Crypto-504/Crypto-Signal/Product/ops/run_dashboard.py "
            "--host 127.0.0.1 --port 48700",
            "81900 1 crypto-signal-agent Runner.Listener "
            "/Volumes/Crypto-504/Crypto-Signal/Runner/bin/Runner.Listener "
            "run --startuptype service",
        )
    )
    monkeypatch.setattr(runtime_acceptance, "_ps_text", lambda: ps)

    topology = runtime_acceptance._assert_process_topology(root)

    assert topology == {
        "supervisor_pid": 78361,
        "dashboard_pid": 81826,
        "runner_listener_pid": 81900,
    }


def test_r11_acceptance_ps_contract_exposes_comm_and_args() -> None:
    text = Path("ops/r11_runtime_acceptance.py").read_text(encoding="utf-8")
    assert '"pid=,ppid=,user=,comm=,args="' in text
    assert 'frozenset({"bash", "/bin/bash"})' in text
