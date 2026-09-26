"""Read-only F5 canonical Capital Story readiness audit.

The audit inspects snapshot copies of canonical R21/R22 Epoch 2 paper truth and
the Intelligence Stream ledger. It never initializes tables, mutates paper
capital, projects messages, backfills history, or grants production authority.

REAL_CAPITAL=0.
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

R21_REQUIRED_TABLES = (
    "r21_epoch2_activation",
    "r21_vault_snapshots",
    "r21_consolidated_snapshots",
)

CAPITAL_LIFECYCLE_TABLES = (
    "s11_vault_decisions",
    "s11_canonical_sizing_events",
    "r22_epoch2_intents",
    "r22_epoch2_fills",
    "r22_epoch2_bundles",
    "s11_capital_outcome_evidence",
)

EPOCH2_TABLES = R21_REQUIRED_TABLES + CAPITAL_LIFECYCLE_TABLES

STREAM_CAPITAL_TABLES = (
    "stream_capital_decision_messages",
    "stream_capital_sizing_messages",
    "stream_capital_messages",
    "stream_capital_lifecycle_messages",
)

CANONICAL_VAULTS = ("core", "opportunity_reserve", "tactical")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epoch2", type=Path, required=True)
    parser.add_argument("--stream", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def _connect_ro(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    quick = connection.execute("PRAGMA quick_check").fetchone()
    if quick is None or str(quick[0]).lower() != "ok":
        connection.close()
        raise ValueError(f"SQLite quick_check failed: {path}")
    connection.execute("BEGIN")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
    if row is None:
        raise ValueError(f"count failed: {table}")
    return int(row[0])


def _max_event(
    connection: sqlite3.Connection,
    table: str,
    column: str,
) -> int | None:
    row = connection.execute(
        f'SELECT MAX("{column}") FROM "{table}"'
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])


def _json_object(value: str, label: str) -> dict[str, Any]:
    raw = json.loads(value)
    if not isinstance(raw, dict):
        raise TypeError(f"{label} payload must be object")
    return raw


def _payload_rows(
    connection: sqlite3.Connection,
    table: str,
    *,
    order_column: str | None = None,
) -> list[dict[str, Any]]:
    suffix = "" if order_column is None else f' ORDER BY "{order_column}"'
    rows = connection.execute(
        f'SELECT payload_json FROM "{table}"{suffix}'
    ).fetchall()
    return [
        _json_object(str(row[0]), f"{table} row")
        for row in rows
    ]


def _counter_payload(
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(key)
        counter["none" if value is None else str(value)] += 1
    return dict(sorted(counter.items()))


def _event_at_ms(
    table: str,
    row: dict[str, Any],
) -> int | None:
    candidates = {
        "s11_vault_decisions": ("decided_at_ms", "assessed_at_ms", "candidate_as_of_ms"),
        "s11_canonical_sizing_events": ("selected_at_ms", "candidate_as_of_ms"),
        "r22_epoch2_intents": ("decided_at_ms", "event_at_ms"),
        "r22_epoch2_fills": ("filled_at_ms", "event_at_ms"),
        "r22_epoch2_bundles": ("snapshot_at_ms", "event_at_ms"),
        "s11_capital_outcome_evidence": ("filled_at_ms", "event_at_ms"),
    }.get(table, ("event_at_ms",))
    for key in candidates:
        value = row.get(key)
        if value is not None:
            return int(value)
    return None


def _stream_activation(
    connection: sqlite3.Connection,
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT activation_identity, activated_at_ms, payload_json
        FROM stream_activation
        ORDER BY activated_at_ms, activation_identity
        """
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("Stream ledger requires exactly one activation boundary")
    payload = _json_object(str(rows[0]["payload_json"]), "stream activation")
    if payload.get("activation_identity") != str(rows[0]["activation_identity"]):
        raise ValueError("Stream activation identity mismatch")
    if int(payload["activated_at_ms"]) != int(rows[0]["activated_at_ms"]):
        raise ValueError("Stream activation timestamp mismatch")
    return payload


def _latest_vault_state(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for vault in CANONICAL_VAULTS:
        row = connection.execute(
            """
            SELECT payload_json
            FROM r21_vault_snapshots
            WHERE vault_id = ?
            ORDER BY snapshot_at_ms DESC, snapshot_identity DESC
            LIMIT 1
            """,
            (vault,),
        ).fetchone()
        if row is None:
            continue
        raw = _json_object(str(row[0]), f"latest vault {vault}")
        result[vault] = {
            "snapshot_identity": raw.get("snapshot_identity"),
            "snapshot_at_ms": raw.get("snapshot_at_ms"),
            "cash_usdt": raw.get("cash_usdt"),
            "marked_exposure_usdt": raw.get("marked_exposure_usdt"),
            "nav_usdt": raw.get("nav_usdt"),
            "realized_pnl_usdt": raw.get("realized_pnl_usdt"),
            "unrealized_pnl_usdt": raw.get("unrealized_pnl_usdt"),
            "closed_trade_count": raw.get("closed_trade_count"),
            "metrics_status": raw.get("metrics_status"),
            "real_capital": raw.get("real_capital"),
        }
    return result


def _latest_consolidated_state(
    connection: sqlite3.Connection,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT payload_json
        FROM r21_consolidated_snapshots
        ORDER BY snapshot_at_ms DESC, snapshot_identity DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    raw = _json_object(str(row[0]), "latest consolidated")
    return {
        "snapshot_identity": raw.get("snapshot_identity"),
        "snapshot_at_ms": raw.get("snapshot_at_ms"),
        "cash_usdt": raw.get("cash_usdt"),
        "marked_exposure_usdt": raw.get("marked_exposure_usdt"),
        "nav_usdt": raw.get("nav_usdt"),
        "realized_pnl_usdt": raw.get("realized_pnl_usdt"),
        "unrealized_pnl_usdt": raw.get("unrealized_pnl_usdt"),
        "closed_trade_count": raw.get("closed_trade_count"),
        "metrics_status": raw.get("metrics_status"),
        "real_capital": raw.get("real_capital"),
    }


def _canonical_forward_counts(
    connection: sqlite3.Connection,
    *,
    activated_at_ms: int,
    existing_tables: set[str],
) -> dict[str, dict[str, int | bool]]:
    result: dict[str, dict[str, int | bool]] = {}
    for table in CAPITAL_LIFECYCLE_TABLES:
        if table not in existing_tables:
            result[table] = {
                "table_present": False,
                "before_stream_activation": 0,
                "at_or_after_stream_activation": 0,
                "unknown_event_time": 0,
            }
            continue
        rows = _payload_rows(connection, table)
        before = 0
        forward = 0
        unknown = 0
        for row in rows:
            event_at = _event_at_ms(table, row)
            if event_at is None:
                unknown += 1
            elif event_at < activated_at_ms:
                before += 1
            else:
                forward += 1
        result[table] = {
            "table_present": True,
            "before_stream_activation": before,
            "at_or_after_stream_activation": forward,
            "unknown_event_time": unknown,
        }
    return result


def _stream_capital_sources(
    connection: sqlite3.Connection,
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT subtype, event_at_ms, source_event_identity, stream_event_identity
        FROM stream_source_events
        WHERE category = 'CAPITAL'
        ORDER BY event_at_ms, stream_event_identity
        """
    ).fetchall()
    subtype_counts: Counter[str] = Counter(str(row["subtype"]) for row in rows)
    return {
        "count": len(rows),
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "max_event_at_ms": (
            None if not rows else max(int(row["event_at_ms"]) for row in rows)
        ),
    }


def _stream_specialized_counts(
    connection: sqlite3.Connection,
    tables: set[str],
) -> dict[str, int | None]:
    return {
        table: (_count(connection, table) if table in tables else None)
        for table in STREAM_CAPITAL_TABLES
    }


def audit(
    *,
    epoch2_path: Path,
    stream_path: Path,
) -> dict[str, Any]:
    with closing(_connect_ro(epoch2_path)) as epoch2, closing(
        _connect_ro(stream_path)
    ) as stream:
        epoch2_tables = _tables(epoch2)
        stream_tables = _tables(stream)
        missing_r21 = sorted(set(R21_REQUIRED_TABLES) - epoch2_tables)
        if missing_r21:
            raise ValueError(
                "canonical R21 Epoch2 schema incomplete: " + ",".join(missing_r21)
            )
        missing_lifecycle = sorted(
            set(CAPITAL_LIFECYCLE_TABLES) - epoch2_tables
        )
        if "stream_activation" not in stream_tables or "stream_source_events" not in stream_tables:
            raise ValueError("Stream schema incomplete for F5 audit")

        activation = _stream_activation(stream)
        activated_at_ms = int(activation["activated_at_ms"])

        decisions = (
            _payload_rows(
                epoch2,
                "s11_vault_decisions",
                order_column="event_at_ms",
            )
            if "s11_vault_decisions" in epoch2_tables
            else []
        )
        sizing = (
            _payload_rows(
                epoch2,
                "s11_canonical_sizing_events",
                order_column="event_at_ms",
            )
            if "s11_canonical_sizing_events" in epoch2_tables
            else []
        )
        intents = (
            _payload_rows(
                epoch2,
                "r22_epoch2_intents",
                order_column="event_at_ms",
            )
            if "r22_epoch2_intents" in epoch2_tables
            else []
        )
        fills = (
            _payload_rows(
                epoch2,
                "r22_epoch2_fills",
                order_column="event_at_ms",
            )
            if "r22_epoch2_fills" in epoch2_tables
            else []
        )
        bundles = (
            _payload_rows(
                epoch2,
                "r22_epoch2_bundles",
                order_column="event_at_ms",
            )
            if "r22_epoch2_bundles" in epoch2_tables
            else []
        )
        outcomes = (
            _payload_rows(
                epoch2,
                "s11_capital_outcome_evidence",
                order_column="event_at_ms",
            )
            if "s11_capital_outcome_evidence" in epoch2_tables
            else []
        )

        latest_vaults = _latest_vault_state(epoch2)
        latest_consolidated = _latest_consolidated_state(epoch2)

        epoch2_counts = {
            table: (_count(epoch2, table) if table in epoch2_tables else None)
            for table in EPOCH2_TABLES
        }
        forward = _canonical_forward_counts(
            epoch2,
            activated_at_ms=activated_at_ms,
            existing_tables=epoch2_tables,
        )
        stream_capital = _stream_capital_sources(stream)
        specialized = _stream_specialized_counts(stream, stream_tables)

        forward_total = sum(
            int(item["at_or_after_stream_activation"])
            for item in forward.values()
        )
        preactivation_total = sum(
            int(item["before_stream_activation"])
            for item in forward.values()
        )

        vault_real_capital_values = {
            str(item.get("real_capital"))
            for item in latest_vaults.values()
        }
        consolidated_real_capital = (
            None
            if latest_consolidated is None
            else latest_consolidated.get("real_capital")
        )
        real_capital_ok = (
            vault_real_capital_values.issubset({"0", "0.0", "None"})
            and str(consolidated_real_capital) in {"0", "0.0", "None"}
        )

        return {
            "schema_version": "stream-final-f5-capital-readiness-v1/1",
            "read_only": True,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
            "epoch2_quick_check": "ok",
            "stream_quick_check": "ok",
            "stream_activation_identity": activation["activation_identity"],
            "stream_activated_at_ms": activated_at_ms,
            "historical_backfill_allowed": bool(
                activation.get("historical_rich_backfill_allowed", False)
            ),
            "epoch2_table_counts": epoch2_counts,
            "missing_capital_lifecycle_tables": missing_lifecycle,
            "capital_lifecycle_schema_live": not missing_lifecycle,
            "decision_disposition_counts": _counter_payload(
                decisions,
                "disposition",
            ),
            "decision_vault_counts": _counter_payload(decisions, "vault_id"),
            "sizing_vault_counts": _counter_payload(sizing, "vault_id"),
            "intent_action_counts": _counter_payload(intents, "action"),
            "intent_vault_counts": _counter_payload(intents, "vault_id"),
            "fill_action_counts": _counter_payload(fills, "action"),
            "fill_vault_counts": _counter_payload(fills, "vault_id"),
            "bundle_vault_counts": _counter_payload(bundles, "vault_id"),
            "outcome_vault_counts": _counter_payload(outcomes, "vault_id"),
            "outcome_financial_counts": _counter_payload(
                outcomes,
                "financial_outcome",
            ),
            "canonical_forward_partition": forward,
            "canonical_forward_record_count": forward_total,
            "canonical_preactivation_record_count": preactivation_total,
            "latest_vaults": latest_vaults,
            "latest_consolidated": latest_consolidated,
            "three_vault_state_present": set(latest_vaults) == set(CANONICAL_VAULTS),
            "stream_capital_sources": stream_capital,
            "stream_specialized_table_counts": specialized,
            "stream_capital_projector_tables_present": all(
                table in stream_tables for table in STREAM_CAPITAL_TABLES
            ),
            "real_capital_zero_verified": real_capital_ok,
            "f5_current_classification": (
                "CANONICAL_CAPITAL_RUNTIME_NOT_LIVE"
                if missing_lifecycle
                else (
                    "CODE_EXISTS_NOT_LIVE"
                    if stream_capital["count"] == 0
                    else "PARTIALLY_OR_ALREADY_PROJECTED"
                )
            ),
            "f5_safe_next_action": (
                "ACTIVATE_CANONICAL_CAPITAL_RUNTIME_THEN_WIRE_FORWARD_PROJECTOR"
                if missing_lifecycle
                else "WIRE_POST_COMMIT_FORWARD_CALLER_ONLY_NO_BACKFILL"
            ),
        }


def main() -> int:
    args = _parser().parse_args()
    payload = audit(
        epoch2_path=args.epoch2,
        stream_path=args.stream,
    )
    rendered = json.dumps(payload, sort_keys=True, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print("STREAM_F5_CAPITAL_READINESS " + json.dumps(payload, sort_keys=True))
    print("STREAM_F5_CAPITAL_READINESS_PASS=YES")
    print("HISTORICAL_BACKFILL=NO")
    print("REAL_CAPITAL=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
