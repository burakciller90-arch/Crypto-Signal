from __future__ import annotations

from pathlib import Path

from ops.audit_stream_f10_final_closeout import (
    AUTHORITY_FILES,
    FINAL_ACCEPTANCE,
    FINAL_ACCEPTED,
    FINAL_DOD_PHRASES,
    FINAL_SOURCE_LEDGER,
    REAL_CAPITAL_MARKER,
    audit,
    main,
)


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _authority_files(root: Path, *, final: bool = False) -> None:
    for relative in AUTHORITY_FILES:
        marker = (
            f"\n{FINAL_ACCEPTED}\n{REAL_CAPITAL_MARKER}\n"
            if final and relative != AUTHORITY_FILES[-1]
            else f"\n{REAL_CAPITAL_MARKER}\n"
        )
        _write(root, relative, f"# {relative}\n{marker}")


def _accepted_f0(root: Path) -> None:
    _write(
        root,
        "docs/CRYPTO_SIGNAL_STREAM_FINAL_F0_SOURCE_MESSAGE_CLOSURE_LEDGER.md",
        (
            "# F0\n"
            "Status: **CANONICAL F0 MECHANICAL INVENTORY**\n"
            f"Safety: **{REAL_CAPITAL_MARKER}**\n"
        ),
    )


def _accepted_stage(root: Path, phase: int) -> None:
    _write(
        root,
        f"docs/CRYPTO_SIGNAL_STREAM_FINAL_F{phase}_ACCEPTANCE.md",
        (
            f"# F{phase}\n"
            "Status: **PASS — PHYSICALLY LIVE**\n"
            f"Safety: **{REAL_CAPITAL_MARKER}**\n"
        ),
    )


def _all_stages(root: Path) -> None:
    _accepted_f0(root)
    for phase in range(1, 10):
        _accepted_stage(root, phase)


def _final_outputs(root: Path) -> None:
    _write(
        root,
        FINAL_SOURCE_LEDGER,
        (
            "# Final source-to-message ledger\n"
            f"Status: **{FINAL_ACCEPTED}**\n"
            f"Safety: **{REAL_CAPITAL_MARKER}**\n"
        ),
    )
    coverage = "\n".join(f"- {item}" for item in FINAL_DOD_PHRASES)
    _write(
        root,
        FINAL_ACCEPTANCE,
        (
            "# Final acceptance\n"
            f"Status: **{FINAL_ACCEPTED}**\n"
            f"Safety: **{REAL_CAPITAL_MARKER}**\n"
            "## Final Definition of Done\n"
            f"{coverage}\n"
        ),
    )


def test_prep_mode_reports_future_stages_without_false_failure(
    tmp_path: Path,
) -> None:
    _authority_files(tmp_path)
    _accepted_f0(tmp_path)
    for phase in range(1, 5):
        _accepted_stage(tmp_path, phase)
    _write(
        tmp_path,
        "docs/CRYPTO_SIGNAL_STREAM_FINAL_F5_CAPITAL_PREP.md",
        (
            "# F5 prep\n"
            "Status: **PREP ONLY — DO NOT MERGE YET**\n"
            f"Safety: **{REAL_CAPITAL_MARKER}**\n"
        ),
    )

    result = audit(tmp_path, mode="prep")

    assert result.all_f0_f9_accepted is False
    assert result.ready_for_authority_mutation is False
    assert result.closeout_complete is False
    assert result.premature_final_claims == ()
    assert result.safety_real_capital_zero is True
    assert [item.status for item in result.stages[:5]] == [
        "ACCEPTED",
        "ACCEPTED",
        "ACCEPTED",
        "ACCEPTED",
        "ACCEPTED",
    ]
    assert result.stages[5].status == "BLOCKED"
    assert main(["--repo-root", str(tmp_path), "--mode", "prep"]) == 0


def test_prep_mode_fails_closed_on_premature_final_authority_claim(
    tmp_path: Path,
) -> None:
    _authority_files(tmp_path)
    _accepted_f0(tmp_path)
    for phase in range(1, 5):
        _accepted_stage(tmp_path, phase)
    _write(
        tmp_path,
        "CURRENT_STATUS.md",
        f"# Current\n{FINAL_ACCEPTED}\n{REAL_CAPITAL_MARKER}\n",
    )

    result = audit(tmp_path, mode="prep")

    assert result.ready_for_authority_mutation is False
    assert result.premature_final_claims == ("CURRENT_STATUS.md",)
    assert main(["--repo-root", str(tmp_path), "--mode", "prep"]) == 3


def test_accepted_status_without_real_capital_zero_does_not_count(
    tmp_path: Path,
) -> None:
    _authority_files(tmp_path)
    _accepted_f0(tmp_path)
    _write(
        tmp_path,
        "docs/CRYPTO_SIGNAL_STREAM_FINAL_F1_ACCEPTANCE.md",
        "# F1\nStatus: **PASS**\n",
    )

    result = audit(tmp_path, mode="prep")

    assert result.stages[1].status == "BLOCKED"
    assert "REAL_CAPITAL=0" in result.stages[1].reasons[0]


def test_all_f0_f9_enable_authority_mutation_but_not_closeout(
    tmp_path: Path,
) -> None:
    _authority_files(tmp_path)
    _all_stages(tmp_path)

    result = audit(tmp_path, mode="prep")

    assert result.all_f0_f9_accepted is True
    assert result.ready_for_authority_mutation is True
    assert result.closeout_complete is False
    assert result.final_source_ledger_present is False
    assert result.final_acceptance_present is False
    assert main(
        [
            "--repo-root",
            str(tmp_path),
            "--mode",
            "prep",
            "--require-ready",
        ]
    ) == 0


def test_closeout_requires_final_outputs_and_authority_freeze(
    tmp_path: Path,
) -> None:
    _authority_files(tmp_path, final=True)
    _all_stages(tmp_path)
    _final_outputs(tmp_path)

    result = audit(tmp_path, mode="closeout")

    assert result.all_f0_f9_accepted is True
    assert result.ready_for_authority_mutation is True
    assert result.final_authority_claim_consistent is True
    assert result.final_source_ledger_present is True
    assert result.final_acceptance_present is True
    assert result.closeout_complete is True
    assert result.blockers == ()
    assert main(
        [
            "--repo-root",
            str(tmp_path),
            "--mode",
            "closeout",
            "--require-complete",
        ]
    ) == 0
