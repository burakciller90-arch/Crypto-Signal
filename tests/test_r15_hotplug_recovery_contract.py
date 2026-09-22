from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path("ops/install_ssd_hotplug_recovery.sh")


def test_r15_hotplug_installer_shell_syntax() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_r15_hotplug_recovery_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '/Volumes/Crypto-504/Crypto-Signal' in text
    assert 'CryptoSignalRecovery' in text
    assert 'com.cryptosignal.ssd-hotplug-recovery' in text
    assert 'PRAGMA quick_check;' in text
    assert 'ssd-service-supervisor.sh' in text
    assert 'Runner.Listener run --startuptype service' in text
    assert 'R15_SSD_HOTPLUG_RECOVERY_REAL_CAPITAL=0' in text
    assert 'R15_SSD_HOTPLUG_RECOVERY_NO_INTERNAL_RUNTIME_FALLBACK=YES' in text
    assert '/Users/crypto-signal-agent/Crypto-Signal' not in text


def test_r15_hotplug_recovery_is_transition_aware() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'SSD_STATE=MISSING' in text
    assert 'SSD_STATE=REMOUNTED' in text
    assert 'mount_transition="YES"' in text
    assert 'start_runner "$mount_transition"' in text
    assert 'SSD_HOTPLUG_RECOVERY_PASS=YES' in text



def test_r15_runner_hang_detection_is_bounded() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'RUNNER_HANG_CPU_MIN=90' in text
    assert 'RUNNER_HANG_STREAK_LIMIT=3' in text
    assert 'runner_worker_alive' in text
    assert 'if runner_worker_alive; then' in text
    assert 'reset_runner_hang_state' in text
    assert 'RUNNER_HANG_DETECTED=YES' in text
    assert 'RUNNER_HANG_RECOVERY_REQUESTED=YES' in text


def test_r15_runner_hang_recovery_never_uses_process_existence_alone() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index('start_runner() {')
    end = text.index('mount_transition="NO"', start)
    block = text[start:end]
    assert 'runner_hang_detected' in block
    assert 'force_restart="YES"' in block
    assert 'runner_worker_alive' in text



def test_r15_runner_restart_verifies_service_ancestry() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'runner_service_tree()' in text
    assert 'stop_runner_service_tree()' in text
    assert 'RunnerService.js' in text
    assert '/bin/bash ./runsvc.sh' in text
    assert 'RUNNER_TREE_STOP_ABORT=ACTIVE_WORKER' in text
    assert 'RUNNER_TREE_STOP_ABORT=UNVERIFIED_ANCESTRY' in text
    assert 'RUNNER_TREE_STOP_PASS=YES' in text


def test_r15_runner_restart_stops_parent_tree_before_new_start() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index('start_runner() {')
    end = text.index('mount_transition="NO"', start)
    block = text[start:end]
    stop_index = block.index('stop_runner_service_tree')
    start_index = block.index('nohup ./runsvc.sh')
    assert stop_index < start_index
    assert 'runner_worker_alive' in text
    assert 'crypto-signal-agent' in text
