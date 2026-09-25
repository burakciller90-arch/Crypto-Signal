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


def test_r14_root_release_surfaces_match_canonical_ssd_state() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    registry = (ROOT / "ENVIRONMENT_REGISTRY.md").read_text(encoding="utf-8")

    for text in (readme, registry):
        assert "REAL_CAPITAL=0" in text
        assert "/Volumes/Crypto-504/Crypto-Signal" in text
        assert "crypto-signal-full-version-v1.0.0" in text

    assert "The immutable release baseline is `crypto-signal-full-version-v1.0.0`" in readme
    assert "Intelligence Stream V1" in readme
    assert "S1 Stream-only backend capability audit is PASS" in readme
    assert "S2 Canonical Stream Event & Message Model is PASS" in readme
    assert "S3 Story Engine and Change Detection is ACTIVE" in readme
    assert "Runtime owner: `crypto-signal-agent`" in readme
    assert "self-hosted runner: `crypto-signal-uid504`" in registry
    assert "There is no accepted fallback" in registry


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


def test_root_release_docs_are_not_stale_bootstrap_state() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    env = (ROOT / "ENVIRONMENT_REGISTRY.md").read_text(encoding="utf-8")
    status = (ROOT / "CURRENT_STATUS.md").read_text(encoding="utf-8")
    audit = (
        ROOT / "docs" / "FULL_VERSION_ROADMAP_COMPLETENESS_AUDIT.md"
    ).read_text(encoding="utf-8")

    assert "Phase 0 bootstrap. No product code yet." not in readme
    assert "/Volumes/Crypto-504/Crypto-Signal" in readme
    assert "/Volumes/Crypto-504/Crypto-Signal" in env
    assert "Baseline: crypto-signal-full-version-v1.0.0 (immutable)" in status
    assert (
        "LOCKED_20M_CONTINUITY_ACTIVE" in status
        or "CONTINUITY_PAUSED_BY_USER" in status
    )
    assert "docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md" in status
    assert "R13 Full Version Integrated Acceptance v2 is PASS" in audit
    assert "Stage 8.5 Alpha Factory and Stage 8.75 Learning Memory" not in audit


def test_release_freeze_rechecks_uid504_runtime_before_tag() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "crypto-r14-release-freeze.yml"
    ).read_text(encoding="utf-8")

    assert "runs-on: [self-hosted, crypto-signal, uid504]" in workflow
    assert "R14_EXACT_MAIN_DEVELOPMENT_PASS=YES" in workflow
    assert "R14_PRODUCT_CODE_PARITY_PASS=YES" in workflow
    assert "R14_RELEASE_DOCUMENTATION_CONTRACT_PASS=YES" in workflow
    assert "R14_LIVE_SAFETY_CONTINUITY_PASS=YES" in workflow
    assert "CRYPTO_SIGNAL_FULL_VERSION_COMPLETE=YES" in workflow
    assert "productdeploy" not in workflow
    assert "wakeresume" not in workflow.lower()
