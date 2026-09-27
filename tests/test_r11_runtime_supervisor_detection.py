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
    ps = """78361 1 crypto-signal-agent /bin/bash /bin/bash /Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.sh
81786 81780 crypto-signal-agent /usr/bin/awk /usr/bin/awk -v needle /Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.sh
81826 78361 crypto-signal-agent Python /Volumes/Crypto-504/Crypto-Signal/Product/.venv/bin/python /Volumes/Crypto-504/Crypto-Signal/Product/ops/run_dashboard.py --host 127.0.0.1 --port 48700
81900 1 crypto-signal-agent Runner.Listener /Volumes/Crypto-504/Crypto-Signal/Runner/bin/Runner.Listener run --startuptype service"""
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


def test_runtime_watchdog_installer_falls_back_when_terminal_open_fails() -> None:
    text = Path("ops/r11/install_runtime_watchdog.sh").read_text(encoding="utf-8")

    assert 'if ! /usr/bin/open -gj -a Terminal "$LOCAL_ROOT/start-ssd-runtime.command"; then' in text
    assert 'R11_TERMINAL_OPEN_FAILED_FALLBACK_DIRECT=YES' in text
    assert '"$LOCAL_ROOT/start-ssd-runtime.command"' in text


def test_r11_installer_refreshes_existing_supervisor_before_start() -> None:
    text = Path("ops/r11/install_runtime_watchdog.sh").read_text(encoding="utf-8")

    assert "R11_REFRESHING_EXISTING_SUPERVISOR=YES" in text
    assert 'kill "$existing_sup"' in text or '/bin/kill "$existing_sup"' in text
    assert 'rm -f "$ROOT/ssd-service-supervisor.pid"' in text or '/bin/rm -f "$ROOT/ssd-service-supervisor.pid"' in text
    assert "R11_TERMINAL_START_MISSING_FALLBACK_DIRECT=YES" in text


def test_supervisor_requires_real_dashboard_health_before_reuse() -> None:
    text = Path("ops/ssd_runtime_supervisor.sh").read_text(encoding="utf-8")

    assert "dashboard_health_ok()" in text
    assert "dashboard_unhealthy pid=$pid action=restart" in text
    assert 'curl -fsS --max-time 3 http://127.0.0.1:48700/api/health' in text
    assert 'stop_dashboard_pid "$pid"' in text


def test_runtime_restart_bypasses_launchagent_installer() -> None:
    text = Path(".github/workflows/crypto-r11-runtime-recovery.yml").read_text(
        encoding="utf-8"
    )
    start = text.index("      - name: Runtime restart only")
    end = text.index("      - name: Runtime watchdog and recovery acceptance", start)
    block = text[start:end]

    assert 'START="$DEV/ops/r11/start_ssd_runtime.command"' in block
    assert 'cp "$DEV/ops/ssd_runtime_supervisor.sh" "$ROOT/ssd-service-supervisor.sh"' in block
    assert "install_runtime_watchdog.sh" not in block


def test_freshnessdiag_reads_canonical_product_page_items() -> None:
    text = Path(".github/workflows/crypto-mac-command.yml").read_text(
        encoding="utf-8"
    )
    start = text.index("      - name: FRESHNESS DIAG")
    end = text.index("      - name: SERVICES", start)
    block = text[start:end]

    assert 'page = payload.get("page", {})' in block
    assert 'items = page.get("items", []) if isinstance(page, dict) else []' in block
    assert 'payload.get("messages", [])' not in block


def test_runtime_restart_normalizes_duplicate_product_dashboard_owners() -> None:
    text = Path(".github/workflows/crypto-r11-runtime-recovery.yml").read_text(
        encoding="utf-8"
    )
    start = text.index("      - name: Runtime restart only")
    end = text.index("      - name: Runtime watchdog and recovery acceptance", start)
    block = text[start:end]

    assert "=== NORMALIZE DASHBOARD OWNERSHIP ===" in block
    assert '$ROOT/Product/ops/run_dashboard.py' in block
    assert 'index($0, "--port 48700") > 0' in block
    assert 'rm -f "$ROOT/dashboard.pid"' in block
