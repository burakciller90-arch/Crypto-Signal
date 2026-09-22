from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_fallback_is_exact_owner_only_and_pause_dominant() -> None:
    recurring = _read("ops/continuity/recurring_wake.py")
    bridge = _read("ops/continuity/bridge_watchdog.py")
    arm = _read("ops/continuity/continuation_arm.sh")
    enqueue = _read("ops/continuity/wake_enqueue.sh")
    resume = _read("ops/continuity/resume_continuity.py")

    assert "WAKE_SKIPPED_NO_EXACT_CONTINUATION_OWNER=YES" in recurring
    assert "WAKE_SKIPPED_ACTIVE_WORKER_OWNER=YES" in recurring
    assert "WAKE_FAIL_MULTIPLE_CONTINUATION_OWNERS=YES" in recurring
    assert "CRYPTO_SIGNAL_CONTINUE_EXACT" in recurring
    assert "CRYPTO_SIGNAL_AUTONOMOUS_CONTINUE_V1" not in recurring
    assert 'SHARED_PAUSE_FILE = Path("/Users/Shared/.crypto-signal-wake-relay/user_pause")' in bridge
    assert 'SHARED_PAUSE_FILE="/Users/Shared/.crypto-signal-wake-relay/user_pause"' in arm
    assert 'SHARED_PAUSE_FILE="/Users/Shared/.crypto-signal-wake-relay/user_pause"' in enqueue
    assert "--dry-run" in resume
    assert "CONTINUITY_RESUME_PRECONDITION_FAILED=YES" in resume
    assert "ARCHIVED_STALE_REPLAY=NO" in resume


def test_relay_is_namespace_bound_and_never_stops_busy_chat() -> None:
    submit = _read("ops/continuity/relay_submit.py")
    daemon = _read("ops/continuity/relay_daemon.py")
    direct = _read("ops/continuity/wake_chatgpt.py")

    assert "encode_relay_event" in submit
    assert "PROJECT_NAMESPACE" in submit
    assert "RELAY_PROTOCOL" in submit
    assert "require_exact_binding" in submit
    assert "decode_relay_event" in daemon
    assert 'EXPECTED_TARGET_FILE = SHARED / "expected_chat_url"' in daemon
    assert "EXPECTED_TARGET_URL" not in daemon
    assert 'return False, "CHATGPT_BUSY"' in daemon
    assert "STOP_CLICKED" not in daemon
    assert "project_namespace={PROJECT_NAMESPACE}" in daemon
    assert "relay_protocol={RELAY_PROTOCOL}" in daemon
    assert "require_exact_binding" in direct
    assert "SHARED_PAUSE_FILE" in direct


def test_binding_writers_and_installers_use_ssd_canonical_state() -> None:
    bootstrap = _read("ops/continuity/bootstrap_continuity.command")
    contracts = _read("ops/continuity/continuity_contracts.py")
    installer = _read(".github/workflows/crypto-install-local-20m-wake.yml")
    diagnostic = _read(".github/workflows/crypto-wake-diagnostic.yml")
    plist = _read(
        "ops/continuity/launchd/com.cryptosignal.continuitybridge.plist"
    )
    timer_plist = _read(
        "ops/continuity/launchd/com.cryptosignal.autowake20m.plist"
    )

    assert 'SHARED_EXPECTED="$SHARED/expected_chat_url"' in bootstrap
    assert 'EXPECTED="$WAKE/expected_chat_url"' in bootstrap
    assert '"crypto-signal"' in bootstrap
    assert "continuity_contracts.py" in installer
    assert "slots=True" not in contracts
    assert 'launchctl kickstart -k "$DOMAIN/$LABEL"' in installer
    assert "recurring_wake_last_local_attempt" in installer
    assert "StandardOutPath" not in timer_plist
    assert "StandardErrorPath" not in timer_plist
    assert "StandardOutPath" not in plist
    assert "StandardErrorPath" not in plist

    legacy = "/Users/crypto-signal-agent/Crypto-Signal/"
    assert legacy not in installer
    assert legacy not in diagnostic
    assert legacy not in plist
    assert (
        "/Volumes/Crypto-504/Crypto-Signal/Development/ops/continuity/"
        "bridge_watchdog.py"
    ) in plist
