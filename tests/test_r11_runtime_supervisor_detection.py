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


def test_r11_acceptance_counts_only_real_bash_supervisor() -> None:
    import importlib.util

    module_path = Path("ops/r11_runtime_acceptance.py")
    spec = importlib.util.spec_from_file_location("r11_runtime_acceptance_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    supervisor = "/Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.sh"
    ps = "\n".join(
        (
            f"78361 1 crypto-signal-agent bash /bin/bash {supervisor}",
            (
                "81786 78361 crypto-signal-agent grep "
                f"/usr/bin/grep -F {supervisor}"
            ),
            (
                "81787 78361 crypto-signal-agent awk "
                f"/usr/bin/awk -v needle={supervisor} index($0, needle)"
            ),
        )
    )

    assert module._matching_supervisor_pids(ps, supervisor) == [78361]


def test_r11_acceptance_ps_exposes_executable_and_args() -> None:
    text = Path("ops/r11_runtime_acceptance.py").read_text(encoding="utf-8")
    assert '"pid=,ppid=,user=,comm=,args="' in text
    assert "Path(command_name).name != \"bash\"" in text
