#!/usr/bin/env python3
from __future__ import annotations

import json
import plistlib
import sqlite3
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

HOME = Path("/Users/crypto-signal-agent")
DEV = HOME / "Crypto-Signal"
LIVE = HOME / "Crypto-Signal-Live"
PRODUCT = HOME / "Crypto-Signal-Product"
ALERTS = HOME / "Crypto-Signal-Alerts"

LIVE_HEAD = "e53c5b29ffc9301fb36c89aa85ddc3677c4e64a1"
PRODUCT_ALERTS_HEAD = "1d8c8757fb825c8934229b454db49bf800f2b5cf"

LIVE_DB = DEV / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
ALERT_DB = DEV / "runtime" / "alerts" / "alert_outbox.sqlite3"

ACCEPTANCE_DOCS = (
    "docs/PHASE0_ACCEPTANCE.md",
    "docs/PHASE1_ACCEPTANCE.md",
    "docs/PA_V1_ACCEPTANCE.md",
    "docs/HARMONIC_V1_ACCEPTANCE.md",
    "docs/ELLIOTT_V1_ACCEPTANCE.md",
    "docs/SIGNAL_SEMANTICS_V1_ACCEPTANCE.md",
    "docs/IMMUTABLE_LIVE_LEDGER_ACCEPTANCE.md",
    "docs/OUTCOME_V1_ACCEPTANCE.md",
    "docs/HISTORICAL_EVALUATION_V1_ACCEPTANCE.md",
    "docs/DASHBOARD_V1_ACCEPTANCE.md",
    "docs/ALERTS_V1_ACCEPTANCE.md",
)

PLISTS = {
    "com.cryptosignal.liveevidenceclock": (
        DEV / "ops/ledger/launchd/com.cryptosignal.liveevidenceclock.plist"
    ),
    "com.cryptosignal.dashboard": (
        DEV / "ops/product/launchd/com.cryptosignal.dashboard.plist"
    ),
    "com.cryptosignal.alertclock": (
        DEV / "ops/alerts/launchd/com.cryptosignal.alertclock.plist"
    ),
}


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def run(*args: str) -> str:
    result = subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def git_head(path: Path) -> str:
    return run("git", "-C", str(path), "rev-parse", "HEAD").strip()


def git_clean(path: Path) -> bool:
    return not run(
        "git",
        "-C",
        str(path),
        "status",
        "--porcelain",
    ).strip()


def ancestor(older: str, newer: str) -> bool:
    result = subprocess.run(
        (
            "git",
            "-C",
            str(DEV),
            "merge-base",
            "--is-ancestor",
            older,
            newer,
        ),
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def http_json(path: str) -> dict[str, Any]:
    with urllib.request.urlopen(
        f"http://127.0.0.1:48700{path}",
        timeout=5,
    ) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise TypeError(f"HTTP {path} must return mapping")
    return value


def open_ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
        timeout=5,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def table_count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(
        f"SELECT COUNT(*) AS count FROM {table}"
    ).fetchone()
    assert row is not None
    return int(row["count"])


def trigger_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='trigger'
            """
        ).fetchall()
    }


def read_plist(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        value = plistlib.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"plist must be mapping: {path}")
    return value


def installed_plist(label: str) -> Path:
    return HOME / "Library" / "LaunchAgents" / f"{label}.plist"


def launchd_text(label: str) -> str:
    return run(
        "launchctl",
        "print",
        f"gui/{subprocess.check_output(['id', '-u'], text=True).strip()}/{label}",
    )


def main() -> int:
    print("V1_INTEGRATED_ACCEPTANCE_BEGIN")

    for relative in ACCEPTANCE_DOCS:
        path = DEV / relative
        check(path.is_file() and path.stat().st_size > 0, f"acceptance:{relative}")

    current = (DEV / "CURRENT_STATUS.md").read_text()
    check("REAL_CAPITAL: 0" in current, "current_status:real_capital_zero")

    dev_head = git_head(DEV)
    check(git_head(LIVE) == LIVE_HEAD, "live_stable:expected_head")
    check(
        git_head(PRODUCT) == PRODUCT_ALERTS_HEAD,
        "product_stable:expected_head",
    )
    check(
        git_head(ALERTS) == PRODUCT_ALERTS_HEAD,
        "alerts_stable:expected_head",
    )
    check(git_clean(LIVE), "live_stable:clean")
    check(git_clean(PRODUCT), "product_stable:clean")
    check(git_clean(ALERTS), "alerts_stable:clean")
    check(ancestor(LIVE_HEAD, dev_head), "live_stable:ancestor_of_dev")
    check(
        ancestor(PRODUCT_ALERTS_HEAD, dev_head),
        "product_stable:ancestor_of_dev",
    )
    check(
        ancestor(PRODUCT_ALERTS_HEAD, dev_head),
        "alerts_stable:ancestor_of_dev",
    )

    check((LIVE / ".venv/bin/python").is_file(), "live_stable:local_python")
    check(
        (PRODUCT / ".venv/bin/python").is_file(),
        "product_stable:local_python",
    )
    check(
        (ALERTS / ".venv/bin/python").is_file(),
        "alerts_stable:local_python",
    )

    for label, versioned in PLISTS.items():
        installed = installed_plist(label)
        check(versioned.is_file(), f"{label}:versioned_plist")
        check(installed.is_file(), f"{label}:installed_plist")
        check(
            versioned.read_bytes() == installed.read_bytes(),
            f"{label}:plist_exact_match",
        )
        launchd = launchd_text(label)
        check("last exit code = 0" in launchd or label == "com.cryptosignal.dashboard",
              f"{label}:last_exit_zero_or_daemon")
        plist = read_plist(versioned)
        args = tuple(str(item) for item in plist["ProgramArguments"])
        workdir = str(plist["WorkingDirectory"])
        if label == "com.cryptosignal.liveevidenceclock":
            check(
                args[0] == str(LIVE / ".venv/bin/python"),
                "live_launchd:local_venv",
            )
            check(
                args[1] == str(LIVE / "ops/run_live_evidence_clock.py"),
                "live_launchd:stable_source",
            )
            check(workdir == str(LIVE), "live_launchd:stable_workdir")
            check(plist.get("StartInterval") == 120, "live_launchd:interval")
        elif label == "com.cryptosignal.dashboard":
            check(
                args[0] == str(PRODUCT / ".venv/bin/python"),
                "dashboard_launchd:local_venv",
            )
            check(workdir == str(PRODUCT), "dashboard_launchd:stable_workdir")
            check("state = running" in launchd, "dashboard_launchd:running")
        else:
            check(
                args[0] == str(ALERTS / ".venv/bin/python"),
                "alert_launchd:local_venv",
            )
            check(workdir == str(ALERTS), "alert_launchd:stable_workdir")
            check(plist.get("StartInterval") == 120, "alert_launchd:interval")
            check(
                "--dispatch-local-noop" not in args,
                "alert_launchd:no_test_dispatch",
            )

    listener = run(
        "lsof",
        "-nP",
        "-iTCP:48700",
        "-sTCP:LISTEN",
    )
    check("127.0.0.1:48700" in listener, "dashboard:localhost_listener")
    check("*:48700" not in listener, "dashboard:no_wildcard_listener")

    health = http_json("/api/health")
    check(health.get("status") == "ok", "dashboard:health_ok")
    check(health.get("read_only") is True, "dashboard:read_only")
    check(health.get("real_capital") == 0, "dashboard:real_capital_zero")
    check(
        health.get("product_version") == "dashboard-v1-alert-center/1",
        "dashboard:accepted_version",
    )
    check(
        health.get("alert_outbox_present") is True,
        "dashboard:alert_outbox_present",
    )

    command = http_json("/api/command-center?recent_limit=1")
    navigation = http_json("/api/navigation")
    performance = http_json("/api/performance")
    alert_center = http_json("/api/alerts?limit=10")

    check(command.get("status") == "ready", "dashboard:command_center_ready")
    check(navigation.get("status") == "ready", "dashboard:navigation_ready")
    check(
        performance.get("status") in {"empty", "ready"},
        "dashboard:performance_truthful_status",
    )
    check(
        alert_center.get("status") in {"empty", "ready"},
        "dashboard:alert_center_truthful_status",
    )

    with open_ro(LIVE_DB) as connection:
        freezes = table_count(connection, "signal_freezes")
        lifecycle = table_count(connection, "lifecycle_evaluations")
        outcomes = table_count(connection, "outcome_evaluations")
        states = {
            str(row["signal_state"])
            for row in connection.execute(
                "SELECT DISTINCT signal_state FROM signal_freezes"
            ).fetchall()
        }
        exchanges = {
            str(row["exchange"])
            for row in connection.execute(
                "SELECT DISTINCT exchange FROM signal_freezes"
            ).fetchall()
        }
        expected_triggers = {
            f"{table}_reject_{operation}"
            for table in (
                "signal_freezes",
                "lifecycle_evaluations",
                "outcome_evaluations",
            )
            for operation in ("update", "delete")
        }
        check(
            expected_triggers <= trigger_names(connection),
            "live_ledger:immutability_triggers",
        )

    check(freezes > 0, "live_ledger:has_forward_freezes")
    check(lifecycle >= freezes, "live_ledger:lifecycle_coverage")
    check(states <= {"no_signal", "neutral", "watch", "active"}, "live_ledger:valid_states")
    check({"bybit", "binance"} <= exchanges, "live_ledger:dual_provider")
    check(
        command.get("freeze_count") == freezes,
        "dashboard:freeze_count_matches_ledger",
    )
    check(outcomes >= 0, "live_ledger:outcome_count_valid")

    with open_ro(ALERT_DB) as connection:
        alert_events = table_count(connection, "alert_events")
        attempts = table_count(connection, "alert_delivery_attempts")
        expected_alert_triggers = {
            f"{table}_reject_{operation}"
            for table in ("alert_events", "alert_delivery_attempts")
            for operation in ("update", "delete")
        }
        check(
            expected_alert_triggers <= trigger_names(connection),
            "alert_outbox:immutability_triggers",
        )

    check(
        alert_center.get("total_count") == alert_events,
        "dashboard:alert_count_matches_outbox",
    )
    check(attempts >= 0, "alert_outbox:attempt_count_valid")

    print(
        "V1_INTEGRATED_COUNTS "
        f"freezes={freezes} lifecycle={lifecycle} outcomes={outcomes} "
        f"alert_events={alert_events} alert_attempts={attempts}"
    )
    print("V1_INTEGRATED_ACCEPTANCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
