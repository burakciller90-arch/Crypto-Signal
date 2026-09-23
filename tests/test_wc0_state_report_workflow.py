from __future__ import annotations

from pathlib import Path


def test_wc0_state_report_is_read_only_and_issue_scoped() -> None:
    workflow = Path(
        ".github/workflows/crypto-wc0-state-report.yml"
    ).read_text(encoding="utf-8")

    assert "runs-on: [self-hosted, crypto-signal, uid504]" in workflow
    assert "issues: write" in workflow
    assert "contents: read" in workflow
    assert "startsWith(github.event.issue.title, '[WC0 REPORT] ')" in workflow
    assert "git -C \"$DEV\" status --short --branch" in workflow
    assert "git -C \"$PRODUCT\" status --short --branch" in workflow
    assert "/usr/sbin/lsof -nP -iTCP:48700 -sTCP:LISTEN" in workflow
    assert "/api/r25/operational-truth" in workflow
    assert "continuity_status.py" in workflow
    assert "WC0_STATE_REPORT_READONLY=YES" in workflow
    assert "productdeploy" not in workflow
    assert "git checkout" not in workflow
    assert "git merge" not in workflow
    assert "launchctl kickstart" not in workflow
    assert "kill " not in workflow
