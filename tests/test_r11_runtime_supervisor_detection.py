from pathlib import Path

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



def _load_r11_acceptance_module():
    import importlib.util

    module_path = Path("ops/r11_runtime_acceptance.py")
    spec = importlib.util.spec_from_file_location("r11_runtime_acceptance_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r11_acceptance_rejects_transient_topology_probe_processes() -> None:
    module = _load_r11_acceptance_module()
    supervisor = "/Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.sh"
    dashboard = "/Volumes/Crypto-504/Crypto-Signal/Product/ops/run_dashboard.py"
    runner = (
        "/Volumes/Crypto-504/Crypto-Signal/Runner/bin/Runner.Listener "
        "run --startuptype service"
    )
    ps = "\n".join(
        (
            f"78361 1 crypto-signal-agent bash /bin/bash {supervisor}",
            (
                "81826 78361 crypto-signal-agent Python "
                f"/opt/python {dashboard} --host 127.0.0.1 --port 48700"
            ),
            f"44162 1 crypto-signal-agent Runner.Listener {runner}",
            (
                "81786 78361 crypto-signal-agent grep "
                f"/usr/bin/grep -F {supervisor}"
            ),
            (
                "84898 78361 crypto-signal-agent awk "
                f"/usr/bin/awk -v expected={runner} index($0, expected)"
            ),
            (
                "84901 78361 crypto-signal-agent grep "
                f"/usr/bin/grep -F {dashboard}"
            ),
        )
    )

    assert module._matching_supervisor_pids(ps, supervisor) == [78361]
    assert module._matching_dashboard_pids(ps, dashboard) == [81826]
    assert module._matching_runner_pids(ps, runner) == [44162]


def test_r11_acceptance_ps_exposes_executable_and_args() -> None:
    text = Path("ops/r11_runtime_acceptance.py").read_text(encoding="utf-8")
    assert '"pid=,ppid=,user=,comm=,args="' in text
    assert 'command_name != "bash"' in text
    assert 'command_name.lower().startswith("python")' in text
    assert "args.strip() == runner_needle" in text
