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
    assert 'RUNNER_HANG_CPU_MIN=50' in text
    assert 'RUNNER_HANG_MIN_AGE_SECONDS=600' in text
    assert 'RUNNER_HANG_STREAK_LIMIT=6' in text
    assert 'runner_worker_alive' in text
    assert 'runner_elapsed_seconds' in text
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
    start_index = block.index('request_terminal_runner_start')
    assert stop_index < start_index
    assert 'runner_worker_alive' in text
    assert 'crypto-signal-agent' in text


def test_r15_listener_detection_is_exact_and_self_match_safe() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("runner_listener_pid() {")
    end = text.index("runner_alive() {", start)
    block = text[start:end]
    assert 'expected="$RUNNER/bin/Runner.Listener run --startuptype service"' in block
    assert "if ($0 == expected)" in block
    assert "index($0, needle)" not in block

def test_r15_recovery_retires_legacy_runner_owners_before_bootstrap() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "com.cryptosignal.github-runner-terminal-watchdog" in text
    assert "com.cryptosignal.github-runner-ssd" in text
    assert "actions.runner.burakciller90-arch-Crypto-Signal.crypto-signal-uid504" in text
    assert 'launchctl disable "$legacy_target"' in text
    assert 'launchctl bootout "$legacy_target"' in text
    assert 'R15_SSD_HOTPLUG_RECOVERY_SINGLE_OWNER=YES' in text
    legacy = text.index('for legacy_label in "${LEGACY_RUNNER_LABELS[@]}"')
    bootstrap = text.index('/bin/launchctl bootstrap "gui/$(id -u)" "$PLIST"')
    assert legacy < bootstrap

def test_r15_orphan_parent_detection_is_exact_and_cwd_bound() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "process_cwd()" in text
    assert "runner_orphan_service_pids()" in text
    assert "/usr/sbin/lsof -a -p" in text
    assert './externals/node20/bin/node ./bin/RunnerService.js' in text
    assert '/bin/bash ./runsvc.sh' in text
    assert 'service_cwd="$(process_cwd "$service")"' in text
    assert 'runner_process_origin_ok "$service"' in text
    assert 'wrapper_cwd="$(process_cwd "$wrapper")"' in text
    assert 'runner_process_origin_ok "$wrapper"' in text
    assert "crypto-signal-agent" in text


def test_r15_orphan_parent_recovery_is_fail_closed() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "stop_orphan_runner_parent_tree()" in text
    assert 'RUNNER_ORPHAN_STOP_ABORT=ACTIVE_WORKER' in text
    assert 'RUNNER_ORPHAN_STOP_ABORT=AMBIGUOUS' in text
    assert 'RUNNER_ORPHAN_PARENT_DETECTED=YES' in text
    assert 'RUNNER_ORPHAN_PARENT_STOP_PASS=YES' in text
    assert 'RUNNER_ORPHAN_FORCE_ABORT=WORKER_APPEARED' in text


def test_r15_orphan_parent_is_stopped_before_new_runner_start() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("start_runner() {")
    end = text.index('mount_transition="NO"', start)
    block = text[start:end]
    orphan_index = block.index("runner_orphan_service_pids")
    stop_index = block.index("stop_orphan_runner_parent_tree")
    launch_index = block.index('request_terminal_runner_start')
    assert orphan_index < stop_index < launch_index

def test_r15_orphan_origin_accepts_only_canonical_or_exact_detach_stale_cwd() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "runner_process_origin_ok()" in text
    assert '[ "$cwd" = "$RUNNER" ]' in text
    assert '[ "$cwd" = "cwd|rtd info error: No such file or directory" ]' in text
    assert 'RUNNER_ORPHAN_STALE_CWD_ACCEPTED=YES' in text
    block_start = text.index("runner_process_origin_ok()")
    block_end = text.index("runner_orphan_service_pids()", block_start)
    block = text[block_start:block_end]
    assert "return 1" in block


def test_r15_orphan_stop_revalidates_origin_before_force_kill() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("stop_orphan_runner_parent_tree()")
    end = text.index("runner_service_tree()", start)
    block = text[start:end]
    assert block.count("runner_process_origin_ok") >= 4
    assert 'RUNNER_ORPHAN_FORCE_ABORT=WORKER_APPEARED' in block

def test_r15_orphan_candidate_count_is_self_contained() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("start_runner() {")
    end = text.index('mount_transition="NO"', start)
    block = text[start:end]
    assert "count_lines" not in block
    assert "/usr/bin/awk 'NF {n++} END {print n+0}'" in block
    assert 'RUNNER_ORPHAN_STOP_ABORT=AMBIGUOUS' in block

def test_r15_runner_restart_uses_health_aware_terminal_transport() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'RUNNER_TERMINAL_START="$LOCAL_ROOT/start-ssd-runner.command"' in text
    assert 'request_terminal_runner_start()' in text
    assert '/usr/bin/open -gj -a Terminal "$RUNNER_TERMINAL_START"' in text
    assert 'RUNNER_TERMINAL_START_SUPPRESSED=LOCK_ACTIVE' in text
    assert 'RUNNER_TERMINAL_START_REQUESTED=YES' in text
    assert 'R15_SSD_HOTPLUG_RECOVERY_RUNNER_TERMINAL_TRANSPORT=YES' in text

    start = text.index("start_runner() {")
    end = text.index('mount_transition="NO"', start)
    block = text[start:end]
    assert 'request_terminal_runner_start' in block
    assert 'launchctl kickstart -k "$RUNNER_SERVICE_TARGET"' not in block


def test_r15_terminal_transport_command_is_bounded_and_idempotent() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'cat > "$RUNNER_TERMINAL_START" <<\'RUNNERTERM\'' in text
    terminal_start = text.index('cat > "$RUNNER_TERMINAL_START" <<\'RUNNERTERM\'')
    plist_start = text.index('cat > "$PLIST" <<PLIST', terminal_start)
    block = text[terminal_start:plist_start]
    assert 'Runner.Listener run --startuptype service' in block
    assert 'RUNNER_ALREADY_ALIVE=YES' in block
    assert 'RUNNER_TERMINAL_START_ABORT=ACTIVE_WORKER' in block
    assert 'SSD_RUNNER_NOT_READY=YES' in block
    assert 'nohup ./runsvc.sh' in block
    assert 'terminal-start.lock' in text


def test_r15_terminal_transport_preserves_ssd_execution_boundary() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'ROOT="/Volumes/Crypto-504/Crypto-Signal"' in text
    assert 'RUNNER="$ROOT/Runner"' in text
    assert 'if [ ! -x "$RUNNER/runsvc.sh" ]; then' in text
    assert 'cd "$RUNNER" || exit 75' in text
    assert 'R15_SSD_HOTPLUG_RECOVERY_RUNNER_TERMINAL_TRANSPORT=YES' in text
    assert '/Users/crypto-signal-agent/Crypto-Signal' not in text

