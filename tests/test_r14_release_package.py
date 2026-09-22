from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_r14_release_documents_exist_and_preserve_hard_boundaries() -> None:
    paths = (
        ROOT / "docs" / "FINAL_RELEASE_MANIFEST_V1.md",
        ROOT / "docs" / "OPERATOR_RUNBOOK_FULL_VERSION_V1.md",
        ROOT / "docs" / "DASHBOARD_OPEN_RECOVERY_GUIDE_V1.md",
        ROOT / "docs" / "SSD_RECOVERY_BACKUP_GUIDE_V1.md",
        ROOT / "docs" / "KNOWN_AUTHORITY_GATES_V1.md",
    )
    for path in paths:
        assert path.is_file(), path
        text = path.read_text(encoding="utf-8")
        assert "REAL_CAPITAL=0" in text
        assert "/Volumes/Crypto-504/Crypto-Signal" in text or (
            path.name == "KNOWN_AUTHORITY_GATES_V1.md"
        )

    manifest = paths[0].read_text(encoding="utf-8")
    assert "35672790463" in manifest
    assert "crypto-signal-full-version-v1.0.0" in manifest
    assert "R14_FULL_VERSION_RELEASE_FREEZE_PASS=YES" in manifest
    assert "physical Mac reboot/logout" in manifest


def test_r14_release_freeze_is_exact_main_idempotent_and_never_force_pushes() -> None:
    path = ROOT / ".github" / "workflows" / "crypto-r14-release-freeze.yml"
    text = path.read_text(encoding="utf-8")

    assert "[R14] FREEZE FULL VERSION RELEASE" in text
    assert "permissions:" in text
    assert "contents: write" in text
    assert "crypto-signal-full-version-v1.0.0" in text
    assert "INVALID_R14_RELEASE_TARGET" in text
    assert 'test "$TARGET" = "$ORIGIN_MAIN"' in text
    assert 'git rev-list -n 1 "$RELEASE_TAG"' in text
    assert "R14_RELEASE_TAG_ALREADY_PRESENT_SAME_TARGET=YES" in text
    assert "R14_GITHUB_RELEASE_ALREADY_PRESENT=YES" in text
    assert "R14_FULL_VERSION_RELEASE_FREEZE_PASS=YES" in text
    assert "--force" not in text
    assert "REAL_CAPITAL=0" in text


def test_operator_docs_do_not_claim_human_impact_recovery_was_executed() -> None:
    manifest = (
        ROOT / "docs" / "FINAL_RELEASE_MANIFEST_V1.md"
    ).read_text(encoding="utf-8")
    recovery = (
        ROOT / "docs" / "SSD_RECOVERY_BACKUP_GUIDE_V1.md"
    ).read_text(encoding="utf-8")

    for text in (manifest, recovery):
        assert "not" in text.lower()
        assert "physical" in text.lower()
        assert "reboot" in text.lower()
        assert "SSD detach" in text or "SSD detach/remount" in text
