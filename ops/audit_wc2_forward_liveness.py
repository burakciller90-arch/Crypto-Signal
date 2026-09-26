#!/usr/bin/env python3
"""Read-only WC2 forward-liveness audit.

This diagnostic never initializes or mutates a runtime database. It classifies
signal freezes after the latest accepted forecast using the same pre-receipt
eligibility conditions enforced by process_wc2_prepared_live_freeze().

It is intentionally not a market replay and has no authority to backfill,
change WC2 policy, create forecasts, mutate canonical paper capital, or send
orders. REAL_CAPITAL=0.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any

REAL_CAPITAL = 0

REASON_BEFORE_COLLECTION = "source_freeze_predates_collection_start"
REASON_BEFORE_ACTIVATION = "source_freeze_predates_epoch2_activation"
REASON_CONTEXT_NOT_AUTHORIZED = "coverage_context_not_authorized"
REASON_NO_SIGNAL = "source_no_signal"
REASON_NEUTRAL = "source_neutral"
REASON_STATE_NOT_ELIGIBLE = "source_state_not_watch_or_active"
REASON_NON_DIRECTIONAL = "source_non_directional"
REASON_MISSING_GEOMETRY = "source_missing_geometry"
REASON_MISSING_TARGET = "source_missing_geometry_target"
REASON_PREPARED_REQUIRED = "source_eligible_prepared_required"
REASON_ELIGIBLE_NO_RECEIPT = "eligible_without_prepared_receipt"
REASON_RECEIPT_NO_FORECAST = "prepared_receipt_without_forecast"
REASON_COMPLETED = "completed_forecast_exists"
REASON_INELIGIBLE_HAS_RECEIPT = "ineligible_source_has_prepared_receipt"
REASON_RECEIPT_DELAY_VIOLATION = "persisted_receipt_exceeds_issuance_delay"
REASON_ROW_BUNDLE_MISMATCH = "signal_row_bundle_context_mismatch"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def _connect_ro(
    path: Path,
    *,
    quick_check: bool = True,
) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    if quick_check:
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            connection.close()
            raise ValueError(f"SQLite quick_check failed: {path}")
    connection.execute("BEGIN")
    return connection


def _load_latest_policy(path: Path) -> dict[str, Any]:
    with closing(_connect_ro(path)) as connection:
        row = connection.execute(
            """
            SELECT policy_identity, payload_json
            FROM wc2_forward_policies
            ORDER BY sequence_id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        raise ValueError("WC2 policy missing")
    payload = _mapping(json.loads(str(row["payload_json"])), "WC2 policy")
    payload["policy_identity"] = str(row["policy_identity"])
    return payload


def _load_latest_protocol(path: Path) -> dict[str, Any]:
    with closing(_connect_ro(path)) as connection:
        row = connection.execute(
            """
            SELECT protocol_identity, payload_json
            FROM wc2_collection_protocols
            ORDER BY sequence_id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        raise ValueError("WC2 collection protocol missing")
    payload = _mapping(json.loads(str(row["payload_json"])), "WC2 protocol")
    payload["protocol_identity"] = str(row["protocol_identity"])
    return payload


def _decision_snapshot(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    with closing(_connect_ro(path)) as connection:
        latest = connection.execute(
            """
            SELECT forecast_identity, signal_freeze_identity, asset, symbol,
                   timeframe, issued_at_ms, source_as_of_ms
            FROM r20_forecasts
            ORDER BY issued_at_ms DESC, forecast_identity DESC
            LIMIT 1
            """
        ).fetchone()
        rows = connection.execute(
            """
            SELECT forecast_identity, signal_freeze_identity, asset, symbol,
                   timeframe, issued_at_ms, source_as_of_ms
            FROM r20_forecasts
            """
        ).fetchall()
    if latest is None:
        raise ValueError("WC2 decision ledger has no forecast")
    latest_payload = {key: latest[key] for key in latest.keys()}
    forecasts = {
        str(row["signal_freeze_identity"]): {
            key: row[key] for key in row.keys()
        }
        for row in rows
    }
    return latest_payload, forecasts


def _prepared_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    with closing(_connect_ro(path)) as connection:
        rows = connection.execute(
            """
            SELECT receipt_identity, policy_identity, activation_identity,
                   collection_protocol_identity, signal_freeze_identity,
                   bundle_identity, source_cutoff_open_time_ms, issued_at_ms,
                   previewed_at_ms, payload_json
            FROM wc2_prepared_cycle_receipts
            """
        ).fetchall()
    return {
        str(row["signal_freeze_identity"]): {
            key: row[key] for key in row.keys()
        }
        for row in rows
    }


def _post_forecast_freezes(
    path: Path,
    *,
    latest_forecast_ms: int,
    latest_forecast_signal_identity: str,
) -> list[dict[str, Any]]:
    # The canonical signal ledger is multi-GB and append-only.
    # signal_freeze_identity is unique/indexed, so anchor on the exact source
    # freeze rowid and inspect only later appends. Keep frozen_at_ms >
    # forecast-issued-at as the temporal gate; rowid is only a bounded scan
    # accelerator, not a replacement for time semantics.
    with closing(_connect_ro(path, quick_check=False)) as connection:
        anchor = connection.execute(
            """
            SELECT rowid
            FROM signal_freezes
            WHERE signal_freeze_identity = ?
            """,
            (latest_forecast_signal_identity,),
        ).fetchone()
        if anchor is None:
            raise ValueError(
                "latest forecast source freeze missing from signal ledger"
            )
        rows = connection.execute(
            """
            SELECT bundle_identity, signal_freeze_identity, exchange,
                   market_type, symbol, timeframe, as_of_ms,
                   source_cutoff_open_time_ms, signal_state, direction,
                   frozen_at_ms
            FROM signal_freezes
            WHERE rowid > ?
              AND frozen_at_ms > ?
            ORDER BY rowid
            """,
            (int(anchor["rowid"]), latest_forecast_ms),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def _coverage_contexts(protocol: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    raw = protocol.get("coverage_context_identities")
    if not isinstance(raw, list):
        raise TypeError("WC2 protocol coverage contexts must be list")
    result: set[tuple[str, str, str, str]] = set()
    for item in raw:
        if not isinstance(item, list) or len(item) != 4:
            raise TypeError("WC2 protocol coverage context must contain four items")
        values = tuple(str(value) for value in item)
        result.add((values[0], values[1], values[2], values[3]))
    return result


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be object")
    return value


def _candidate_signal_from_bundle(
    path: Path,
    row: dict[str, Any],
) -> dict[str, Any]:
    # Full freeze bundles contain consumed candle history and can be large.
    # Read them only for potential WATCH/ACTIVE directional candidates.
    with closing(_connect_ro(path, quick_check=False)) as connection:
        bundle_row = connection.execute(
            """
            SELECT bundle_json
            FROM signal_freezes
            WHERE signal_freeze_identity = ?
            """,
            (str(row["signal_freeze_identity"]),),
        ).fetchone()
    if bundle_row is None:
        raise ValueError("candidate signal freeze disappeared")
    bundle = _mapping(
        json.loads(str(bundle_row["bundle_json"])),
        "signal freeze bundle",
    )
    signal = _mapping(bundle.get("signal_decision"), "signal decision")
    expected = {
        "freeze_identity": str(row["signal_freeze_identity"]),
        "exchange": str(row["exchange"]),
        "market_type": str(row["market_type"]),
        "symbol": str(row["symbol"]),
        "timeframe": str(row["timeframe"]),
        "as_of_ms": int(row["as_of_ms"]),
        "state": str(row["signal_state"]),
        "direction": str(row["direction"]),
    }
    for key, value in expected.items():
        if signal.get(key) != value:
            raise ValueError(f"{REASON_ROW_BUNDLE_MISMATCH}:{key}")
    return signal


def _pre_receipt_reason(
    row: dict[str, Any],
    *,
    collection_start_ms: int,
    activation_ms: int,
    authorized_contexts: set[tuple[str, str, str, str]],
) -> str:
    if int(row["frozen_at_ms"]) < collection_start_ms:
        return REASON_BEFORE_COLLECTION
    if int(row["frozen_at_ms"]) < activation_ms:
        return REASON_BEFORE_ACTIVATION
    context = (
        str(row["exchange"]),
        str(row["market_type"]),
        str(row["symbol"]),
        str(row["timeframe"]),
    )
    if context not in authorized_contexts:
        return REASON_CONTEXT_NOT_AUTHORIZED

    state = str(row["signal_state"])
    direction = str(row["direction"])
    if state == "no_signal":
        return REASON_NO_SIGNAL
    if state == "neutral":
        return REASON_NEUTRAL
    if state not in {"watch", "active"}:
        return REASON_STATE_NOT_ELIGIBLE
    if direction == "none":
        return REASON_NON_DIRECTIONAL
    return REASON_PREPARED_REQUIRED


def audit(
    *,
    signal_path: Path,
    decision_path: Path,
    prepared_path: Path,
    policy_path: Path,
    protocol_path: Path,
) -> dict[str, Any]:
    policy = _load_latest_policy(policy_path)
    protocol = _load_latest_protocol(protocol_path)
    latest_forecast, forecasts = _decision_snapshot(decision_path)
    receipts = _prepared_snapshot(prepared_path)

    policy_start = int(policy["collection_start_ms"])
    protocol_start = int(protocol["collection_start_ms"])
    collection_start_ms = max(policy_start, protocol_start)
    activation_ms = int(protocol["epoch2_activated_at_ms"])
    maximum_delay_ms = int(protocol["maximum_issuance_delay_ms"])
    contexts = _coverage_contexts(protocol)

    latest_forecast_ms = int(latest_forecast["issued_at_ms"])
    rows = _post_forecast_freezes(
        signal_path,
        latest_forecast_ms=latest_forecast_ms,
        latest_forecast_signal_identity=str(
            latest_forecast["signal_freeze_identity"]
        ),
    )

    primary_reasons: Counter[str] = Counter()
    states: Counter[str] = Counter()
    directions: Counter[str] = Counter()
    timeframes: Counter[str] = Counter()
    symbols: Counter[str] = Counter()
    exchanges: Counter[str] = Counter()
    four_hour_reasons: Counter[str] = Counter()
    candidate_defects: list[dict[str, Any]] = []
    prepared_required_rows: list[dict[str, Any]] = []
    integrity_errors: list[dict[str, Any]] = []

    for row in rows:
        states[str(row["signal_state"])] += 1
        directions[str(row["direction"])] += 1
        timeframes[str(row["timeframe"])] += 1
        symbols[str(row["symbol"])] += 1
        exchanges[str(row["exchange"])] += 1
        signal_identity = str(row["signal_freeze_identity"])

        try:
            reason = _pre_receipt_reason(
                row,
                collection_start_ms=collection_start_ms,
                activation_ms=activation_ms,
                authorized_contexts=contexts,
            )
            if reason == REASON_PREPARED_REQUIRED:
                signal = _candidate_signal_from_bundle(signal_path, row)
                geometry = signal.get("geometry")
                if geometry is None:
                    reason = REASON_MISSING_GEOMETRY
                else:
                    geometry_map = _mapping(geometry, "signal geometry")
                    targets = geometry_map.get("targets")
                    if not isinstance(targets, list) or not targets:
                        reason = REASON_MISSING_TARGET
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            reason = REASON_ROW_BUNDLE_MISMATCH
            integrity_errors.append(
                {
                    "signal_freeze_identity": signal_identity,
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )

        receipt = receipts.get(signal_identity)
        forecast = forecasts.get(signal_identity)

        if reason == REASON_PREPARED_REQUIRED:
            detail = {
                "signal_freeze_identity": signal_identity,
                "exchange": str(row["exchange"]),
                "symbol": str(row["symbol"]),
                "timeframe": str(row["timeframe"]),
                "frozen_at_ms": int(row["frozen_at_ms"]),
                "source_cutoff_open_time_ms": int(row["source_cutoff_open_time_ms"]),
                "receipt_identity": (
                    None if receipt is None else str(receipt["receipt_identity"])
                ),
                "forecast_identity": (
                    None if forecast is None else str(forecast["forecast_identity"])
                ),
            }
            prepared_required_rows.append(detail)
            if receipt is None:
                reason = REASON_ELIGIBLE_NO_RECEIPT
                candidate_defects.append({**detail, "reason": reason})
            elif forecast is None:
                reason = REASON_RECEIPT_NO_FORECAST
                candidate_defects.append({**detail, "reason": reason})
            else:
                reason = REASON_COMPLETED

            if receipt is not None:
                payload = _mapping(
                    json.loads(str(receipt["payload_json"])),
                    "prepared receipt",
                )
                source_frozen_at_ms = int(payload["source_frozen_at_ms"])
                issued_at_ms = int(payload["issued_at_ms"])
                if issued_at_ms - source_frozen_at_ms > maximum_delay_ms:
                    reason = REASON_RECEIPT_DELAY_VIOLATION
                    candidate_defects.append(
                        {
                            **detail,
                            "reason": reason,
                            "source_frozen_at_ms": source_frozen_at_ms,
                            "issued_at_ms": issued_at_ms,
                            "maximum_issuance_delay_ms": maximum_delay_ms,
                        }
                    )
        elif receipt is not None:
            candidate_defects.append(
                {
                    "signal_freeze_identity": signal_identity,
                    "reason": REASON_INELIGIBLE_HAS_RECEIPT,
                    "pre_receipt_reason": reason,
                    "receipt_identity": str(receipt["receipt_identity"]),
                }
            )
            reason = REASON_INELIGIBLE_HAS_RECEIPT

        primary_reasons[reason] += 1
        if str(row["timeframe"]) == "4h":
            four_hour_reasons[reason] += 1

    correct_silence = (
        len(rows) > 0
        and not candidate_defects
        and not integrity_errors
        and not prepared_required_rows
    )

    return {
        "schema_version": "wc2-forward-liveness-audit-v1/1",
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "latest_forecast": latest_forecast,
        "policy_identity": str(policy["policy_identity"]),
        "protocol_identity": str(protocol["protocol_identity"]),
        "collection_start_ms": collection_start_ms,
        "epoch2_activated_at_ms": activation_ms,
        "maximum_issuance_delay_ms": maximum_delay_ms,
        "authorized_context_count": len(contexts),
        "post_latest_forecast_freeze_count": len(rows),
        "post_latest_forecast_4h_count": int(timeframes.get("4h", 0)),
        "reason_counts": dict(sorted(primary_reasons.items())),
        "four_hour_reason_counts": dict(sorted(four_hour_reasons.items())),
        "state_counts": dict(sorted(states.items())),
        "direction_counts": dict(sorted(directions.items())),
        "timeframe_counts": dict(sorted(timeframes.items())),
        "symbol_counts": dict(sorted(symbols.items())),
        "exchange_counts": dict(sorted(exchanges.items())),
        "prepared_required_count": len(prepared_required_rows),
        "prepared_required_rows": prepared_required_rows,
        "candidate_defect_count": len(candidate_defects),
        "candidate_defects": candidate_defects,
        "integrity_error_count": len(integrity_errors),
        "integrity_errors": integrity_errors,
        "correct_silence_pre_receipt_proven": correct_silence,
        "not_current_issuance_gates": [
            "dual_provider_pairing_or_consensus",
            "real_event_risk_source_state",
            "provider_divergence_state",
        ],
        "note": (
            "Current prepared issuance processes each pilot coverage context "
            "independently. adapt_same_cycle_legacy_bundle supplies a fail-closed "
            "DEGRADED_DATA missing-PIT Event Risk context; dual-provider and "
            "provider-divergence state are not pre-receipt issuance gates in "
            "the current code."
        ),
    }


def main() -> int:
    args = _parser().parse_args()
    payload = audit(
        signal_path=args.signal,
        decision_path=args.decision,
        prepared_path=args.prepared,
        policy_path=args.policy,
        protocol_path=args.protocol,
    )
    rendered = json.dumps(payload, sort_keys=True, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print("WC2_FORWARD_LIVENESS " + json.dumps(payload, sort_keys=True))
    if payload["correct_silence_pre_receipt_proven"]:
        print("WC2_FORWARD_LIVENESS_CORRECT_SILENCE_PRE_RECEIPT=YES")
    elif payload["candidate_defect_count"]:
        print("WC2_FORWARD_LIVENESS_CORRECTNESS_CANDIDATE=YES")
    else:
        print("WC2_FORWARD_LIVENESS_DEEPER_DIAG_REQUIRED=YES")
    print("REAL_CAPITAL=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
