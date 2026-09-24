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
