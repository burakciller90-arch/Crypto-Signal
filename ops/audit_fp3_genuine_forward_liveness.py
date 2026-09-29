#!/usr/bin/env python3
"""FP3-D genuine-forward liveness acceptance over live immutable source truth.

Live Development SQLite files are opened only in read-only/query-only mode.
Any FP3/Capital writes happen only against SQLite-consistent snapshots under
an explicit output directory (normally $RUNNER_TEMP). Fixtures cannot satisfy
this audit. REAL_CAPITAL=0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from crypto_signal.decision_ledger import (
    DecisionLedgerWriteDisposition,
    ImmutableDecisionEvidenceLedger,
)
from crypto_signal.evaluation.live_untouched_forward_operational import (
    issue_accepted_wc2_live_source,
)
from crypto_signal.evaluation.untouched_forward_prepared import (
    WC2PreparedCycleJournal,
)
from crypto_signal.paper.autopilot_forward_runtime import (
    CanonicalPaperAutopilotForwardRuntime,
    FP3AutopilotProcessDisposition,
)
from crypto_signal.product.intelligence_stream_capital_forward_runtime import (
    IntelligenceStreamCapitalForwardRuntime,
)

REAL_CAPITAL = 0
_PREPARED_TABLE = "wc2_prepared_cycle_receipts"
_SIGNAL_TABLE = "signal_freezes"
_FP3_SUFFIX = ".fp3-paper-autopilot.sqlite3"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--epoch2", type=Path, required=True)
    parser.add_argument("--stream", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--observed-at-ms", type=int, default=None)
    return parser


def _connect_ro(path: Path, *, quick_check: bool = True) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
        timeout=10,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    if quick_check:
        row = connection.execute("PRAGMA quick_check").fetchone()
        if row is None or str(row[0]).lower() != "ok":
            connection.close()
            raise ValueError(f"SQLite quick_check failed: {path}")
    return connection


def snapshot_sqlite_read_only(source: Path, destination: Path) -> None:
    """Create a committed SQLite snapshot without granting source write access."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with closing(_connect_ro(source)) as source_db:
        with closing(sqlite3.connect(destination)) as destination_db:
            source_db.backup(destination_db)
    with closing(sqlite3.connect(destination)) as copied:
        row = copied.execute("PRAGMA quick_check").fetchone()
        if row is None or str(row[0]).lower() != "ok":
            raise ValueError(f"SQLite snapshot quick_check failed: {destination}")


def candidate_signal_identities(
    prepared_path: Path,
    *,
    activated_at_ms: int,
) -> tuple[str, ...]:
    """Newest-first prepared signals whose immutable issuance is post activation."""
    with closing(_connect_ro(prepared_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT signal_freeze_identity
            FROM {_PREPARED_TABLE}
            WHERE issued_at_ms >= ?
            ORDER BY issued_at_ms DESC, sequence_id DESC
            """,
            (activated_at_ms,),
        ).fetchall()
    return tuple(str(row[0]) for row in rows)


def verify_live_signal_source(
    signal_path: Path,
    *,
    signal_freeze_identity: str,
    bundle_identity: str,
    frozen_at_ms: int,
) -> None:
    """Bind selected prepared truth back to the real immutable signal ledger."""
    with closing(_connect_ro(signal_path, quick_check=False)) as connection:
        row = connection.execute(
            f"""
            SELECT bundle_identity, frozen_at_ms
            FROM {_SIGNAL_TABLE}
            WHERE signal_freeze_identity = ?
            LIMIT 1
            """,
            (signal_freeze_identity,),
        ).fetchone()
    if row is None:
        raise ValueError("FP3-D genuine source signal is missing from live signal ledger")
    if str(row[0]) != bundle_identity:
        raise ValueError("FP3-D prepared/live signal bundle identity mismatch")
    if int(row[1]) != frozen_at_ms:
        raise ValueError("FP3-D prepared/live signal frozen-at mismatch")


def _file_set_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    for candidate in (
        path,
        Path(f"{path}-wal"),
        Path(f"{path}-shm"),
    ):
        digest.update(candidate.name.encode("utf-8"))
        if not candidate.exists():
            digest.update(b"<missing>")
            continue
        with candidate.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _front_activation(
    *,
    epoch2_path: Path,
    stream_path: Path,
) -> dict[str, object]:
    return IntelligenceStreamCapitalForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
    ).activation()


def _choose_genuine_candidate(
    *,
    prepared_path: Path,
    decision_path: Path,
    activated_at_ms: int,
):
    prepared = WC2PreparedCycleJournal(prepared_path)
    decision = ImmutableDecisionEvidenceLedger(decision_path)
    for signal_identity in candidate_signal_identities(
        prepared_path,
        activated_at_ms=activated_at_ms,
    ):
        persisted = decision.read_issuance_for_signal(signal_identity)
        if persisted is None:
            continue
        receipt = prepared.read_for_signal(signal_identity)
        if receipt is None:
            raise ValueError("FP3-D selected prepared signal lost its receipt")
        if receipt.capital_assessed_at_ms < activated_at_ms:
            continue
        forecast, proof = persisted
        if int(forecast["issued_at_ms"]) != receipt.issued_at_ms:
            raise ValueError("FP3-D prepared/persisted issuance time mismatch")
        if forecast["forecast_identity"] != proof["forecast_identity"]:
            raise ValueError("FP3-D persisted forecast/proof lineage mismatch")
        return receipt, forecast, proof
    return None


def _emit(report: dict[str, Any]) -> None:
    status = str(report["status"])
    print(f"FP3D_GENUINE_FORWARD_STATUS={status}")
    print(
        "FP3D_GENUINE_POST_ACTIVATION_CANDIDATE="
        + ("YES" if status == "PASS" else "NO")
    )
    print(
        "FP3D_REPLAY_IDEMPOTENCE_PASS="
        + ("YES" if report.get("replay_idempotent") is True else "NO")
    )
    print(
        "FP3D_ACTIVATION_IMMUTABLE_PASS="
        + ("YES" if report.get("activation_immutable") is True else "NO")
    )
    print("FP3D_LIVE_SOURCE_QUERY_ONLY=YES")
    print("FP3D_HISTORICAL_BACKFILL=NO")
    print(f"REAL_CAPITAL={REAL_CAPITAL}")


def audit(
    *,
    signal_path: Path,
    prepared_path: Path,
    decision_path: Path,
    epoch2_path: Path,
    stream_path: Path,
    output_dir: Path,
    observed_at_ms: int,
) -> dict[str, Any]:
    if observed_at_ms < 0:
        raise ValueError("FP3-D observed-at must be non-negative")
    for path in (signal_path, prepared_path, decision_path, epoch2_path, stream_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    output_dir.mkdir(parents=True, exist_ok=True)
    copies = {
        "prepared": output_dir / "prepared.wc2-prepared.sqlite3",
        "decision": output_dir / "decision.sqlite3",
        "epoch2": output_dir / "paper_fund_epoch2.sqlite3",
        "stream": output_dir / "intelligence_stream.sqlite3",
    }
    snapshot_sqlite_read_only(prepared_path, copies["prepared"])
    snapshot_sqlite_read_only(decision_path, copies["decision"])
    snapshot_sqlite_read_only(epoch2_path, copies["epoch2"])
    snapshot_sqlite_read_only(stream_path, copies["stream"])

    front_activation = _front_activation(
        epoch2_path=copies["epoch2"],
        stream_path=copies["stream"],
    )
    activated_at_ms = int(front_activation["activated_at_ms"])
    candidate = _choose_genuine_candidate(
        prepared_path=copies["prepared"],
        decision_path=copies["decision"],
        activated_at_ms=activated_at_ms,
    )
    if candidate is None:
        report = {
            "status": "WAITING_NO_POST_ACTIVATION_ISSUANCE",
            "activated_at_ms": activated_at_ms,
            "read_only_live_sources": True,
            "historical_backfill": False,
            "real_capital": REAL_CAPITAL,
        }
        _emit(report)
        return report

    receipt, persisted_forecast, persisted_proof = candidate
    verify_live_signal_source(
        signal_path,
        signal_freeze_identity=receipt.signal.freeze_identity,
        bundle_identity=receipt.source_inputs.bundle_identity,
        frozen_at_ms=receipt.source_frozen_at_ms,
    )
    if receipt.issued_at_ms < activated_at_ms:
        raise ValueError("FP3-D genuine issuance predates capital activation")

    issuance = issue_accepted_wc2_live_source(
        receipt.signal,
        receipt.source_inputs,
        issued_at_ms=receipt.issued_at_ms,
        horizon_bars=receipt.horizon_bars,
        target_label=receipt.target_label,
        base_asset=receipt.base_asset,
        ledger=ImmutableDecisionEvidenceLedger(copies["decision"]),
        collection_protocol_identity=receipt.collection_protocol_identity,
    )
    if issuance.ledger_disposition is not DecisionLedgerWriteDisposition.UNCHANGED:
        raise ValueError("FP3-D recovery created new decision truth instead of exact replay")
    if issuance.forecast.forecast_identity != persisted_forecast["forecast_identity"]:
        raise ValueError("FP3-D recovered forecast differs from persisted genuine forecast")
    if issuance.proof.proof_identity != persisted_proof["proof_identity"]:
        raise ValueError("FP3-D recovered proof differs from persisted genuine proof")

    autopilot_path = output_dir / f"observation{_FP3_SUFFIX}"
    runtime = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=copies["epoch2"],
        stream_path=copies["stream"],
        autopilot_path=autopilot_path,
    )
    activation_identity = runtime.ensure_activated(activated_at_ms=activated_at_ms)
    first = runtime.process_issuance(
        issuance,
        event_context=receipt.source_inputs.event_context,
        base_asset=receipt.base_asset,
        assessed_at_ms=receipt.capital_assessed_at_ms,
        processed_at_ms=max(observed_at_ms, receipt.indexed_at_ms),
    )
    if first.receipt is None:
        raise ValueError("FP3-D genuine post-activation issuance produced no FP3 receipt")
    if first.disposition not in {
        FP3AutopilotProcessDisposition.INSERTED,
        FP3AutopilotProcessDisposition.RECOVERED,
    }:
        raise ValueError("FP3-D first genuine observation was not inserted/recovered")

    fingerprints_before_replay = {
        "epoch2": _file_set_fingerprint(copies["epoch2"]),
        "stream": _file_set_fingerprint(copies["stream"]),
        "autopilot": _file_set_fingerprint(autopilot_path),
    }

    restarted = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=copies["epoch2"],
        stream_path=copies["stream"],
        autopilot_path=autopilot_path,
    )
    replay = restarted.process_issuance(
        issuance,
        event_context=receipt.source_inputs.event_context,
        base_asset=receipt.base_asset,
        assessed_at_ms=receipt.capital_assessed_at_ms,
        processed_at_ms=max(observed_at_ms, receipt.indexed_at_ms) + 1,
    )
    if replay.disposition is not FP3AutopilotProcessDisposition.REPLAYED:
        raise ValueError("FP3-D restart did not replay the exact FP3 receipt")
    if replay.receipt != first.receipt:
        raise ValueError("FP3-D restart replay changed the FP3 receipt")

    fingerprints_after_replay = {
        "epoch2": _file_set_fingerprint(copies["epoch2"]),
        "stream": _file_set_fingerprint(copies["stream"]),
        "autopilot": _file_set_fingerprint(autopilot_path),
    }
    replay_idempotent = fingerprints_before_replay == fingerprints_after_replay
    if not replay_idempotent:
        raise ValueError("FP3-D replay changed copied canonical/FP3 SQLite state")

    same_activation = restarted.ensure_activated(activated_at_ms=activated_at_ms)
    if same_activation != activation_identity:
        raise ValueError("FP3-D activation identity changed on exact replay")
    try:
        restarted.ensure_activated(activated_at_ms=activated_at_ms + 1)
    except ValueError:
        activation_immutable = True
    else:
        activation_immutable = False
    if not activation_immutable:
        raise ValueError("FP3-D activation accepted a different activation watermark")

    decision_states = tuple(first.receipt.decision_states)
    eligible_count = sum(1 for _, state in decision_states if state == "eligible")
    hold_or_block_count = sum(
        1 for _, state in decision_states if state in {"hold", "blocked"}
    )
    report = {
        "status": "PASS",
        "activation_identity": activation_identity,
        "activated_at_ms": activated_at_ms,
        "signal_freeze_identity": receipt.signal.freeze_identity,
        "prepared_receipt_identity": receipt.receipt_identity,
        "forecast_identity": issuance.forecast.forecast_identity,
        "proof_identity": issuance.proof.proof_identity,
        "source_frozen_at_ms": receipt.source_frozen_at_ms,
        "issued_at_ms": receipt.issued_at_ms,
        "assessed_at_ms": receipt.capital_assessed_at_ms,
        "fp3_receipt_identity": first.receipt.receipt_identity,
        "first_disposition": first.disposition.value,
        "replay_disposition": replay.disposition.value,
        "decision_states": decision_states,
        "eligible_vault_count": eligible_count,
        "hold_or_block_count": hold_or_block_count,
        "replay_idempotent": replay_idempotent,
        "activation_immutable": activation_immutable,
        "read_only_live_sources": True,
        "historical_backfill": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    _emit(report)
    return report


def main() -> int:
    args = _parser().parse_args()
    observed_at_ms = (
        time.time_ns() // 1_000_000
        if args.observed_at_ms is None
        else args.observed_at_ms
    )
    report = audit(
        signal_path=args.signal,
        prepared_path=args.prepared,
        decision_path=args.decision,
        epoch2_path=args.epoch2,
        stream_path=args.stream,
        output_dir=args.output_dir,
        observed_at_ms=observed_at_ms,
    )
    report_path = args.output_dir / "fp3d-genuine-forward-report.json"
    report_path.write_text(
        json.dumps(report, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
