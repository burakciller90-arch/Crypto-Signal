from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

FINAL_ACCEPTED = "INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ACCEPTED"
REAL_CAPITAL_MARKER = "REAL_CAPITAL=0"

AUTHORITY_FILES = (
    "READ_FIRST_CRYPTO_SIGNAL.md",
    "CURRENT_STATUS.md",
    "PROJECT_CHRONICLE.md",
    "docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md",
    "docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ROADMAP.md",
)
FINAL_SOURCE_LEDGER = "docs/CRYPTO_SIGNAL_STREAM_V1_FINAL_SOURCE_TO_MESSAGE_LEDGER.md"
FINAL_ACCEPTANCE = "docs/CRYPTO_SIGNAL_STREAM_V1_FINAL_ACCEPTANCE.md"

FINAL_DOD_PHRASES = (
    "one primary Stream surface",
    "real backend material events",
    "production silence",
    "Market/Geometry",
    "Liquidity",
    "Order Flow",
    "Derivatives",
    "Event Risk",
    "On-chain",
    "Decision issuance",
    "Core",
    "Tactical",
    "Opportunity",
    "append-only",
    "Story",
    "SIMPLE",
    "PRO",
    "INTELLIGENCE",
    "DECISION",
    "CAPITAL",
    "exact identity",
    "current data",
    "unavailable proof",
    "search",
    "SSE",
    "Ollama",
    "real production",
    "desktop",
    "mobile",
    "historical",
    "scientific policy",
    "real-money",
    REAL_CAPITAL_MARKER,
)

BLOCKED_STATUS_TOKENS = (
    "PREP",
    "PENDING",
    "OPEN",
    "BLOCKED",
    "NOT ACCEPTED",
    "NOT PASS",
    "DO NOT MERGE",
)


@dataclass(frozen=True)
class StageEvidence:
    phase: str
    status: str
    files: tuple[str, ...]
    accepted_file: str | None
    accepted_status_line: str | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CloseoutAudit:
    schema_version: str
    mode: str
    repo_root: str
    stages: tuple[StageEvidence, ...]
    all_f0_f9_accepted: bool
    authority_files_present: bool
    premature_final_claims: tuple[str, ...]
    final_source_ledger_present: bool
    final_acceptance_present: bool
    final_authority_claim_consistent: bool
    ready_for_authority_mutation: bool
    closeout_complete: bool
    blockers: tuple[str, ...]
    safety_real_capital_zero: bool


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _status_line(text: str) -> str | None:
    match = re.search(r"^Status:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    return None if match is None else match.group(1).strip()


def _accepted_status(status_line: str | None) -> bool:
    if status_line is None:
        return False
    normalized = re.sub(r"[*_]", "", status_line).upper()
    if any(token in normalized for token in BLOCKED_STATUS_TOKENS):
        return False
    return "PASS" in normalized or "ACCEPTED" in normalized


def _candidate_stage_files(root: Path, phase: str) -> tuple[Path, ...]:
    docs = root / "docs"
    if not docs.is_dir():
        return ()
    return tuple(sorted(docs.glob(f"CRYPTO_SIGNAL_STREAM_FINAL_{phase}_*.md")))


def _stage_evidence(root: Path, phase_number: int) -> StageEvidence:
    phase = f"F{phase_number}"
    candidates = _candidate_stage_files(root, phase)
    files = tuple(str(path.relative_to(root)) for path in candidates)
    reasons: list[str] = []

    if phase_number == 0:
        canonical = root / "docs" / "CRYPTO_SIGNAL_STREAM_FINAL_F0_SOURCE_MESSAGE_CLOSURE_LEDGER.md"
        if not canonical.is_file():
            return StageEvidence(
                phase=phase,
                status="MISSING",
                files=files,
                accepted_file=None,
                accepted_status_line=None,
                reasons=("canonical F0 closure ledger missing",),
            )
        text = _read(canonical)
        accepted = (
            "CANONICAL F0 MECHANICAL INVENTORY" in text
            and REAL_CAPITAL_MARKER in text
        )
        if not accepted:
            reasons.append("F0 ledger lacks canonical inventory or REAL_CAPITAL=0")
        return StageEvidence(
            phase=phase,
            status="ACCEPTED" if accepted else "BLOCKED",
            files=files,
            accepted_file=str(canonical.relative_to(root)) if accepted else None,
            accepted_status_line=_status_line(text),
            reasons=tuple(reasons),
        )

    accepted_file: Path | None = None
    accepted_status_line: str | None = None
    for path in candidates:
        text = _read(path)
        status = _status_line(text)
        if not _accepted_status(status):
            continue
        if REAL_CAPITAL_MARKER not in text:
            reasons.append(f"{path.name}: accepted status lacks REAL_CAPITAL=0")
            continue
        accepted_file = path
        accepted_status_line = status
        break

    if accepted_file is None:
        if not candidates:
            reasons.append(f"no {phase} final evidence document exists")
        else:
            reasons.append(
                f"{phase} has documents, but none carries a final PASS/ACCEPTED status with REAL_CAPITAL=0"
            )
        return StageEvidence(
            phase=phase,
            status="BLOCKED",
            files=files,
            accepted_file=None,
            accepted_status_line=None,
            reasons=tuple(reasons),
        )

    return StageEvidence(
        phase=phase,
        status="ACCEPTED",
        files=files,
        accepted_file=str(accepted_file.relative_to(root)),
        accepted_status_line=accepted_status_line,
        reasons=(),
    )


def _authority_presence(root: Path) -> tuple[bool, tuple[str, ...]]:
    missing = tuple(
        path for path in AUTHORITY_FILES if not (root / path).is_file()
    )
    return (not missing, missing)


def _premature_claims(
    root: Path,
    *,
    all_stages_accepted: bool,
) -> tuple[str, ...]:
    if all_stages_accepted:
        return ()
    claims: list[str] = []
    for relative in AUTHORITY_FILES[:-1]:
        path = root / relative
        if path.is_file() and FINAL_ACCEPTED in _read(path):
            claims.append(relative)
    for relative in (FINAL_SOURCE_LEDGER, FINAL_ACCEPTANCE):
        path = root / relative
        if path.is_file() and FINAL_ACCEPTED in _read(path):
            claims.append(relative)
    return tuple(sorted(set(claims)))


def _final_output_valid(path: Path, *, require_dod: bool) -> tuple[bool, tuple[str, ...]]:
    if not path.is_file():
        return False, ("missing",)
    text = _read(path)
    problems: list[str] = []
    if FINAL_ACCEPTED not in text:
        problems.append("final acceptance marker missing")
    if REAL_CAPITAL_MARKER not in text:
        problems.append("REAL_CAPITAL=0 missing")
    if require_dod:
        missing = tuple(item for item in FINAL_DOD_PHRASES if item not in text)
        if missing:
            problems.append(
                "final Definition of Done coverage incomplete: " + ", ".join(missing)
            )
    return not problems, tuple(problems)


def _final_authority_consistent(root: Path, *, all_stages_accepted: bool) -> bool:
    if not all_stages_accepted:
        return False
    required = AUTHORITY_FILES[:-1]
    return all(
        (root / relative).is_file()
        and FINAL_ACCEPTED in _read(root / relative)
        and REAL_CAPITAL_MARKER in _read(root / relative)
        for relative in required
    )


def audit(root: Path, *, mode: str) -> CloseoutAudit:
    root = root.resolve()
    stages = tuple(_stage_evidence(root, index) for index in range(10))
    all_stages_accepted = all(item.status == "ACCEPTED" for item in stages)
    authority_files_present, missing_authority = _authority_presence(root)
    premature = _premature_claims(
        root,
        all_stages_accepted=all_stages_accepted,
    )

    final_ledger_valid, final_ledger_problems = _final_output_valid(
        root / FINAL_SOURCE_LEDGER,
        require_dod=False,
    )
    final_acceptance_valid, final_acceptance_problems = _final_output_valid(
        root / FINAL_ACCEPTANCE,
        require_dod=True,
    )

    authority_consistent = _final_authority_consistent(
        root,
        all_stages_accepted=all_stages_accepted,
    )
    safety_real_capital_zero = all(
        item.status != "ACCEPTED"
        or (
            item.accepted_file is not None
            and REAL_CAPITAL_MARKER in _read(root / item.accepted_file)
        )
        for item in stages
    )

    blockers: list[str] = []
    for item in stages:
        if item.status != "ACCEPTED":
            blockers.append(f"{item.phase}: " + "; ".join(item.reasons))
    blockers.extend(f"authority file missing: {item}" for item in missing_authority)
    blockers.extend(f"premature final authority claim: {item}" for item in premature)

    ready_for_authority_mutation = (
        all_stages_accepted
        and authority_files_present
        and not premature
        and safety_real_capital_zero
    )

    if mode == "closeout":
        if not final_ledger_valid:
            blockers.append(
                f"{FINAL_SOURCE_LEDGER}: " + "; ".join(final_ledger_problems)
            )
        if not final_acceptance_valid:
            blockers.append(
                f"{FINAL_ACCEPTANCE}: " + "; ".join(final_acceptance_problems)
            )
        if not authority_consistent:
            blockers.append(
                "READ_FIRST/CURRENT_STATUS/PROJECT_CHRONICLE/master roadmap "
                "do not all carry the final accepted marker with REAL_CAPITAL=0"
            )

    closeout_complete = (
        ready_for_authority_mutation
        and final_ledger_valid
        and final_acceptance_valid
        and authority_consistent
    )

    return CloseoutAudit(
        schema_version="intelligence-stream-final-f10-closeout-audit-v1/1",
        mode=mode,
        repo_root=str(root),
        stages=stages,
        all_f0_f9_accepted=all_stages_accepted,
        authority_files_present=authority_files_present,
        premature_final_claims=premature,
        final_source_ledger_present=(root / FINAL_SOURCE_LEDGER).is_file(),
        final_acceptance_present=(root / FINAL_ACCEPTANCE).is_file(),
        final_authority_claim_consistent=authority_consistent,
        ready_for_authority_mutation=ready_for_authority_mutation,
        closeout_complete=closeout_complete,
        blockers=tuple(blockers),
        safety_real_capital_zero=safety_real_capital_zero,
    )


def _render_text(result: CloseoutAudit) -> str:
    lines = [
        f"F10_MODE={result.mode}",
        f"F0_F9_ACCEPTED={'YES' if result.all_f0_f9_accepted else 'NO'}",
        f"READY_FOR_AUTHORITY_MUTATION={'YES' if result.ready_for_authority_mutation else 'NO'}",
        f"F10_CLOSEOUT_COMPLETE={'YES' if result.closeout_complete else 'NO'}",
        f"PREMATURE_FINAL_CLAIMS={len(result.premature_final_claims)}",
        f"REAL_CAPITAL_ZERO={'YES' if result.safety_real_capital_zero else 'NO'}",
    ]
    for stage in result.stages:
        suffix = (
            f" file={stage.accepted_file}"
            if stage.accepted_file is not None
            else ""
        )
        lines.append(f"{stage.phase}_STATUS={stage.status}{suffix}")
    for blocker in result.blockers:
        lines.append(f"BLOCKER={blocker}")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only F10 final closeout authority audit."
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--mode",
        choices=("prep", "closeout"),
        default="prep",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Fail unless F0-F9 are accepted and authority mutation may begin.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail unless final F10 authority/doc closeout is complete.",
    )
    args = parser.parse_args(tuple(argv) if argv is not None else None)

    result = audit(args.repo_root, mode=args.mode)
    print(_render_text(result))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(asdict(result), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if result.premature_final_claims:
        return 3
    if not result.safety_real_capital_zero:
        return 4
    if args.require_complete and not result.closeout_complete:
        return 2
    if args.require_ready and not result.ready_for_authority_mutation:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
