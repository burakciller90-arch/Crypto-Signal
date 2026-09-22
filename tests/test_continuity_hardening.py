from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_locked_20m_fallback_is_state_first_and_pause_dominant() -> None:
    recurring = _read("ops/continuity/recurring_wake.py")
    bridge = _read("ops/continuity/bridge_watchdog.py")
    arm = _read("ops/continuity/continuation_arm.sh")
    enqueue = _read("ops/continuity/wake_enqueue.sh")
    resume = _read("ops/continuity/resume_continuity.py")

    assert "WAKE_MESSAGE =" in recurring
    assert "HAFIZANA GÜVENME" in recurring
    assert "docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md" in recurring
    assert "kullanıcı açıkça durdurmadıkça" in recurring
    assert "REAL_CAPITAL=0" in recurring
    assert "crypto-20m-locked-roadmap:" in recurring
    assert "CRYPTO_LOCKED_20M_WAKE_PASS=YES" in recurring
    assert "WAKE_SKIPPED_USER_PAUSE=YES" in recurring
    assert "WAKE_SKIPPED_NO_EXACT_CONTINUATION_OWNER=YES" not in recurring
    assert "WAKE_SKIPPED_ACTIVE_WORKER_OWNER=YES" not in recurring
    assert "WAKE_FAIL_MULTIPLE_CONTINUATION_OWNERS=YES" not in recurring
    assert "CRYPTO_SIGNAL_AUTONOMOUS_CONTINUE_V1" not in recurring
    assert 'SHARED_PAUSE_FILE = Path("/Users/Shared/.crypto-signal-wake-relay/user_pause")' in bridge
    assert 'SHARED_PAUSE_FILE="/Users/Shared/.crypto-signal-wake-relay/user_pause"' in arm
    assert 'SHARED_PAUSE_FILE="/Users/Shared/.crypto-signal-wake-relay/user_pause"' in enqueue
    assert "--dry-run" in resume
    assert "CONTINUITY_RESUME_PRECONDITION_FAILED=YES" in resume
    assert "ARCHIVED_STALE_REPLAY=NO" in resume


def test_relay_is_namespace_bound_and_stops_only_exact_locked_wake() -> None:
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
    assert "LOCKED_WAKE_MESSAGE =" in daemon
    assert "exact_locked_wake = message == LOCKED_WAKE_MESSAGE" in daemon
    assert 'if not exact_locked_wake:' in daemon
    assert 'return False, "CHATGPT_BUSY"' in daemon
    assert "STOP_CLICKED" in daemon
    assert "project_namespace={PROJECT_NAMESPACE}" in daemon
    assert "relay_protocol={RELAY_PROTOCOL}" in daemon
    assert "require_exact_binding" in direct
    assert "SHARED_PAUSE_FILE" in direct



def test_rolling_timer_requires_observed_receipt_and_relay_recovers_submitting() -> None:
    rolling = _read("ops/continuity/interval_wake_daemon.py")
    submit = _read("ops/continuity/relay_submit.py")
    daemon = _read("ops/continuity/relay_daemon.py")

    assert 'FINAL_RECEIPT_STATES = {"OBSERVED"}' in rolling
    assert '"SUBMITTED_UNCONFIRMED"' not in rolling
    assert "final_receipt(pending)" in rolling
    assert 'state["next_due_epoch"] = receipt_epoch + INTERVAL_SECONDS' in rolling
    assert "observed_only=message == LOCKED_WAKE_MESSAGE" in submit
    assert 'status != "OBSERVED"' in submit
    assert "baseline_exact_count" in daemon
    assert 'receipt_status == "OBSERVED"' in daemon
    assert "OBSERVED_RECOVERED" in daemon
    assert "AWAITING_EXACT_OBSERVATION" in daemon
    assert "receipt.unlink(missing_ok=True)" in daemon



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
    rolling = _read("ops/continuity/interval_wake_daemon.py")
    fallback = _read(".github/workflows/crypto-20m-continuity-wake.yml")
    assert "continuity_contracts.py" in installer
    assert 'DOMAIN="user/$(id -u)"' in installer
    assert 'DOMAIN="gui/$(id -u)"' not in installer
    acceptance = _read(".github/workflows/crypto-r12-continuity-acceptance.yml")
    assert 'DOMAIN="user/$(id -u)"' in acceptance
    assert 'DOMAIN="gui/$(id -u)"' not in acceptance
    assert "slots=True" not in contracts
    assert "INTERVAL_SECONDS = 20 * 60" in rolling
    assert "pending_event_id" in rolling
    assert "receipt_confirmed_countdown_reset" in rolling
    assert "WAITING_FOR_RUNTIME" in rolling
    assert "RETRY_SECONDS = 5" in rolling
    assert "interval_wake_daemon.py" in installer
    assert "--reset" in installer
    assert "LEGACY_CALENDAR_TIMERS_DISABLED=YES" in installer
    assert "LOCAL_20M_WAKE_MODE=rolling-daemon" in installer
    assert "GITHUB_20M_ROLE=watchdog-fallback" in installer
    assert "ROLLING_WAKE_IMMEDIATE_RECEIPT_PASS=YES" in installer
    assert 'cron: "*/5 * * * *"' in fallback
    assert 'if [ "${{ github.event_name }}" = "schedule" ]; then' in fallback
    assert r'if [ "\${{ github.event_name }}" = "schedule" ]; then' not in fallback
    assert "GITHUB_WATCHDOG_TIMER_HEALTHY=YES" in fallback
    assert "GITHUB_WATCHDOG_TIMER_RESTARTED=YES" in fallback
    assert "GITHUB_EMERGENCY_FALLBACK_WAKE_ATTEMPTED=YES" in fallback
    assert "R12_BRIDGE_LAUNCHD_UNAVAILABLE=YES" in acceptance
    assert 'BRIDGE_MODE="detached"' in acceptance
    assert "RUNNER_TRACKING_ID" in acceptance
    assert "R12_BRIDGE_RUNTIME_PASS=YES" in acceptance
    assert "R12_SHARED_GUI_TRANSPORT_OWNER_UID=" in acceptance
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
