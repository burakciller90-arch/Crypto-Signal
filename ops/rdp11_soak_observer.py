from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path("/Volumes/Crypto-504/Crypto-Signal")
DEFAULT_SIDECAR_ROOT = DEFAULT_ROOT / "RDP11Soak"
EXPECTED_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
EXPECTED_RAW_CHANNELS = ("orderbook.50", "publicTrade")
REAL_CAPITAL = 0
SOAK_REQUIRED_MS = 72 * 60 * 60 * 1000
DEFAULT_MAX_INGESTION_AGE_MS = 120_000
SCHEMA_VERSION = "rdp11-soak-observation-v1/1"
ANCHOR_SCHEMA_VERSION = "rdp11-soak-anchor-v1/1"
INVALIDATION_SCHEMA_VERSION = "rdp11-soak-invalidation-v1/1"


class ObservationFailure(RuntimeError):
    """Raised when a mandatory RDP11 observation contract is violated."""


@dataclass(frozen=True, slots=True)
class GitState:
    head: str
    clean: bool


def _utc_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _observer_contract_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _git_state(path: Path) -> GitState:
    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return GitState(head=head, clean=not dirty.strip())


def _http_text(url: str, *, timeout: float = 8.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise ObservationFailure(f"HTTP status {response.status}: {url}")
        return response.read().decode("utf-8")


def _http_json(url: str, *, timeout: float = 8.0) -> dict[str, Any]:
    raw = json.loads(_http_text(url, timeout=timeout))
    if not isinstance(raw, dict):
        raise ObservationFailure(f"JSON object required: {url}")
    return {str(key): value for key, value in raw.items()}


def _ro_connect(path: Path, *, timeout: float = 5.0) -> sqlite3.Connection:
    if not path.is_file():
        raise ObservationFailure(f"required SQLite DB missing: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=timeout)
    db.row_factory = sqlite3.Row
    db.execute(f"PRAGMA busy_timeout={max(1, int(timeout * 1000))}")
    db.execute("PRAGMA query_only=ON")
    return db


def _quick_check(path: Path) -> dict[str, object]:
    started_ns = time.monotonic_ns()
    with _ro_connect(path) as db:
        row = db.execute("PRAGMA quick_check").fetchone()
        if row is None or str(row[0]).lower() != "ok":
            raise ObservationFailure(f"SQLite quick_check failed: {path}: {row!r}")
        table_count = int(
            db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
        )
    elapsed_ms = (time.monotonic_ns() - started_ns) // 1_000_000
    return {
        "path": str(path),
        "quick_check": "ok",
        "table_count": table_count,
        "elapsed_ms": elapsed_ms,
    }


def _bounded_market_tape_probe(path: Path) -> dict[str, object]:
    started_ns = time.monotonic_ns()
    required_tables = {
        "market_tape_meta",
        "market_tape_orderbooks",
        "market_tape_trades",
        "market_tape_derivatives",
        "market_tape_liquidations",
        "market_tape_liquidation_coverage",
    }
    with _ro_connect(path) as db:
        schema_row = db.execute(
            """
            SELECT value
            FROM market_tape_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if schema_row is None:
            raise ObservationFailure("Market Tape schema version missing")
        table_names = {
            str(row[0])
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = sorted(required_tables - table_names)
        if missing:
            raise ObservationFailure(
                f"Market Tape required tables missing: {missing!r}"
            )
        latest_orderbook = db.execute(
            """
            SELECT snapshot_identity, event_at_ms, ingested_at_ms
            FROM market_tape_orderbooks
            ORDER BY rowid DESC
            LIMIT 1
            """
        ).fetchone()
        latest_trade = db.execute(
            """
            SELECT trade_identity, event_at_ms, ingested_at_ms
            FROM market_tape_trades
            ORDER BY rowid DESC
            LIMIT 1
            """
        ).fetchone()
        if latest_orderbook is None or latest_trade is None:
            raise ObservationFailure(
                "Market Tape bounded read requires orderbook and trade rows"
            )
        page_count = int(db.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(db.execute("PRAGMA page_size").fetchone()[0])
    elapsed_ms = (time.monotonic_ns() - started_ns) // 1_000_000
    return {
        "path": str(path),
        "integrity_mode": "bounded_read_lock_schema",
        "schema_version": str(schema_row[0]),
        "required_tables_present": True,
        "latest_orderbook_identity": str(latest_orderbook["snapshot_identity"]),
        "latest_orderbook_event_at_ms": int(latest_orderbook["event_at_ms"]),
        "latest_orderbook_ingested_at_ms": int(latest_orderbook["ingested_at_ms"]),
        "latest_trade_identity": str(latest_trade["trade_identity"]),
        "latest_trade_event_at_ms": int(latest_trade["event_at_ms"]),
        "latest_trade_ingested_at_ms": int(latest_trade["ingested_at_ms"]),
        "page_count": page_count,
        "page_size": page_size,
        "elapsed_ms": elapsed_ms,
        "read_only": True,
    }


def _inspect_product(root: Path, expected_sha: str) -> dict[str, object]:
    dev = root / "Development"
    product = root / "Product"
    dev_state = _git_state(dev)
    product_state = _git_state(product)
    if dev_state.head != expected_sha or product_state.head != expected_sha:
        raise ObservationFailure(
            "runtime SHA drift: "
            f"development={dev_state.head} product={product_state.head} "
            f"expected={expected_sha}"
        )
    if not dev_state.clean or not product_state.clean:
        raise ObservationFailure(
            f"runtime checkout dirty: development_clean={dev_state.clean} "
            f"product_clean={product_state.clean}"
        )

    base = "http://127.0.0.1:48700"
    health = _http_json(f"{base}/api/health")
    if health.get("status") != "ok":
        raise ObservationFailure(f"Product health not ok: {health!r}")
    if health.get("real_capital") != REAL_CAPITAL:
        raise ObservationFailure("Product REAL_CAPITAL boundary violated")
    if health.get("read_only") is not True:
        raise ObservationFailure("Product is not read-only")
    if health.get("stream_root_active") is not True:
        raise ObservationFailure("Product Stream root is not active")
    if health.get("ledger_present") is not True:
        raise ObservationFailure("Product ledger is missing")
    if health.get("decision_evidence_present") is not True:
        raise ObservationFailure("Product decision evidence is missing")

    messages = _http_json(f"{base}/api/stream/messages?limit=5")
    if messages.get("status") not in {"ready", "empty"}:
        raise ObservationFailure(f"Stream messages unavailable: {messages!r}")
    if messages.get("read_only") is not True or messages.get("real_capital") != 0:
        raise ObservationFailure("Stream messages read-only/capital boundary violated")
    page = messages.get("page")
    if not isinstance(page, dict):
        raise ObservationFailure("Stream messages page missing")

    sse = _http_text(f"{base}/api/stream/live?batch_limit=5&follow=false")
    if "retry:" not in sse:
        raise ObservationFailure("finite Stream SSE contract is unavailable")

    intelligence = _http_json(f"{base}/api/intelligence-center", timeout=15.0)
    items = page.get("items", [])
    return {
        "development": {"head": dev_state.head, "clean": dev_state.clean},
        "product": {"head": product_state.head, "clean": product_state.clean},
        "health": health,
        "stream_messages": {
            "status": messages.get("status"),
            "item_count": len(items) if isinstance(items, list) else 0,
            "read_only": messages.get("read_only"),
            "real_capital": messages.get("real_capital"),
        },
        "stream_sse": {"finite_read_pass": True},
        "intelligence_center": {
            "reachable": True,
            "top_level_keys": sorted(intelligence),
        },
    }


def _inspect_collector(
    root: Path,
    *,
    max_ingestion_age_ms: int,
) -> dict[str, object]:
    runtime = root / "Development/runtime/market_tape"
    runtime_db = runtime / "collector_runtime.sqlite3"
    gaps_db = runtime / "market_data_gaps.sqlite3"
    raw_db = runtime / "raw_market_tape.sqlite3"
    market_db = runtime / "market_tape.sqlite3"

    runtime_check = _quick_check(runtime_db)
    gap_check = _quick_check(gaps_db)
    market_check = _bounded_market_tape_probe(market_db)

    with _ro_connect(runtime_db) as db:
        instance = db.execute(
            """
            SELECT instance_identity, started_at_ms, process_id
            FROM collector_instances
            WHERE provider='bybit' AND source='market_tape_stream'
            ORDER BY started_at_ms DESC, instance_identity DESC
            LIMIT 1
            """
        ).fetchone()
        if instance is None:
            raise ObservationFailure("Market Tape collector instance missing")
        heartbeat = db.execute(
            """
            SELECT heartbeat_identity, sequence_no, observed_at_ms,
                   last_successful_ingestion_ms
            FROM collector_heartbeats
            WHERE instance_identity=?
            ORDER BY sequence_no DESC
            LIMIT 1
            """,
            (str(instance["instance_identity"]),),
        ).fetchone()
        if heartbeat is None:
            raise ObservationFailure("Market Tape collector heartbeat missing")

    heartbeat_read_at_ms = time.time_ns() // 1_000_000
    heartbeat_ms = int(heartbeat["observed_at_ms"])
    ingestion_raw = heartbeat["last_successful_ingestion_ms"]
    if ingestion_raw is None:
        raise ObservationFailure("collector has no successful ingestion evidence")
    ingestion_ms = int(ingestion_raw)
    heartbeat_age_ms = heartbeat_read_at_ms - heartbeat_ms
    ingestion_age_ms = heartbeat_read_at_ms - ingestion_ms
    if min(heartbeat_age_ms, ingestion_age_ms) < 0:
        raise ObservationFailure("collector evidence timestamp is from the future")
    if heartbeat_age_ms > max_ingestion_age_ms:
        raise ObservationFailure(
            f"collector heartbeat stale: age_ms={heartbeat_age_ms}"
        )

    open_gaps: dict[tuple[str, str], dict[str, object]] = {}
    with _ro_connect(gaps_db) as db:
        rows = db.execute(
            """
            SELECT gap_identity, event_kind, channel, symbol,
                   observed_at_ms, payload_json
            FROM market_data_gap_events
            ORDER BY sequence_id
            """
        ).fetchall()
        latest: dict[str, sqlite3.Row] = {}
        for row in rows:
            latest[str(row["gap_identity"])] = row
        for row in latest.values():
            if str(row["event_kind"]) in {"recovered", "unrecovered"}:
                continue
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict):
                raise ObservationFailure("gap payload must be a JSON object")
            key = (str(row["channel"]), str(row["symbol"]))
            open_gaps[key] = {
                "gap_identity": str(row["gap_identity"]),
                "event_kind": str(row["event_kind"]),
                "observed_at_ms": int(row["observed_at_ms"]),
                "last_successful_ingestion_ms": payload.get(
                    "last_successful_ingestion_ms"
                ),
                "reason_codes": payload.get("reason_codes", []),
            }

    contexts: list[dict[str, object]] = []
    with _ro_connect(raw_db) as db:
        db.execute("SELECT 1 FROM raw_market_events LIMIT 1").fetchone()
        for symbol in EXPECTED_SYMBOLS:
            for channel in EXPECTED_RAW_CHANNELS:
                row = db.execute(
                    """
                    SELECT event_identity, event_at_ms, source_timestamp_ms,
                           ingested_at_ms, sequence
                    FROM raw_market_events
                    WHERE exchange='bybit' AND channel=? AND symbol=?
                    ORDER BY event_at_ms DESC, rowid DESC
                    LIMIT 1
                    """,
                    (channel, symbol),
                ).fetchone()
                if row is None:
                    raise ObservationFailure(
                        f"raw Market Tape context missing: {channel}/{symbol}"
                    )
                context_read_at_ms = time.time_ns() // 1_000_000
                ingested_at_ms = int(row["ingested_at_ms"])
                age_ms = context_read_at_ms - ingested_at_ms
                if age_ms < 0:
                    raise ObservationFailure(
                        f"raw Market Tape future ingestion: {channel}/{symbol}"
                    )
                gap = open_gaps.get((channel, symbol))
                if age_ms <= max_ingestion_age_ms:
                    state = "fresh"
                elif gap is not None:
                    state = "degraded_explicit"
                else:
                    raise ObservationFailure(
                        "silent stale Market Tape context: "
                        f"{channel}/{symbol} age_ms={age_ms}"
                    )
                contexts.append(
                    {
                        "channel": channel,
                        "symbol": symbol,
                        "event_identity": str(row["event_identity"]),
                        "event_at_ms": int(row["event_at_ms"]),
                        "source_timestamp_ms": int(row["source_timestamp_ms"]),
                        "ingested_at_ms": ingested_at_ms,
                        "freshness_sampled_at_ms": context_read_at_ms,
                        "sequence": int(row["sequence"]),
                        "age_ms": age_ms,
                        "state": state,
                        "open_gap": gap,
                    }
                )

    return {
        "sqlite": {
            "collector_runtime": runtime_check,
            "gap_ledger": gap_check,
            "market_tape": market_check,
            "raw_market_tape": {
                "path": str(raw_db),
                "bounded_read_pass": True,
            },
        },
        "collector": {
            "instance_identity": str(instance["instance_identity"]),
            "started_at_ms": int(instance["started_at_ms"]),
            "process_id": int(instance["process_id"]),
            "heartbeat_identity": str(heartbeat["heartbeat_identity"]),
            "sequence_no": int(heartbeat["sequence_no"]),
            "observed_at_ms": heartbeat_ms,
            "last_successful_ingestion_ms": ingestion_ms,
            "freshness_sampled_at_ms": heartbeat_read_at_ms,
            "heartbeat_age_ms": heartbeat_age_ms,
            "ingestion_age_ms": ingestion_age_ms,
        },
        "open_gap_count": len(open_gaps),
        "open_gaps": [
            {"channel": key[0], "symbol": key[1], **value}
            for key, value in sorted(open_gaps.items())
        ],
        "contexts": contexts,
        "explicit_degradation_count": sum(
            item["state"] == "degraded_explicit" for item in contexts
        ),
    }


def _inspect_stream(root: Path) -> dict[str, object]:
    path = root / "Development/runtime/stream/intelligence_stream.sqlite3"
    with _ro_connect(path) as db:
        quick = db.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            raise ObservationFailure(f"Stream quick_check failed: {quick!r}")
        activation_rows = db.execute(
            """
            SELECT activation_identity, activated_at_ms, payload_json
            FROM stream_activation
            ORDER BY activated_at_ms, activation_identity
            """
        ).fetchall()
        if len(activation_rows) != 1:
            raise ObservationFailure(
                f"Stream activation count invalid: {len(activation_rows)}"
            )
        activation = activation_rows[0]
        payload = json.loads(str(activation["payload_json"]))
        if not isinstance(payload, dict):
            raise ObservationFailure("Stream activation payload must be object")
        if payload.get("historical_rich_backfill_allowed") is not False:
            raise ObservationFailure("historical rich backfill boundary violated")
        if payload.get("read_only") is not True:
            raise ObservationFailure("Stream activation is not read-only")
        if payload.get("production_authority") is not False:
            raise ObservationFailure("Stream activation grants production authority")
        if payload.get("real_capital") != 0:
            raise ObservationFailure("Stream activation REAL_CAPITAL boundary violated")

        activated_at_ms = int(activation["activated_at_ms"])
        min_event = db.execute(
            "SELECT MIN(event_at_ms) FROM stream_source_events"
        ).fetchone()[0]
        if min_event is not None and int(min_event) < activated_at_ms:
            raise ObservationFailure(
                "Stream historical backfill boundary violated: "
                f"{min_event}<{activated_at_ms}"
            )
        meta = {
            str(row[0]): str(row[1])
            for row in db.execute("SELECT key, value FROM stream_meta")
        }
        if meta.get("real_capital") != "0":
            raise ObservationFailure("Stream real_capital metadata invalid")
        narrative_count = int(
            db.execute("SELECT COUNT(*) FROM stream_narrative_messages").fetchone()[0]
        )
        source_event_count = int(
            db.execute("SELECT COUNT(*) FROM stream_source_events").fetchone()[0]
        )
    return {
        "path": str(path),
        "quick_check": "ok",
        "activation_identity": str(activation["activation_identity"]),
        "activated_at_ms": activated_at_ms,
        "min_source_event_at_ms": None if min_event is None else int(min_event),
        "source_event_count": source_event_count,
        "narrative_count": narrative_count,
        "historical_rich_backfill_allowed": False,
        "read_only": True,
        "real_capital": 0,
    }


def _inspect_frozen_proofs(root: Path) -> dict[str, object]:
    path = root / "Development/runtime/stream/frozen_proofs.sqlite3"
    with _ro_connect(path, timeout=10.0) as db:
        quick = db.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            raise ObservationFailure(f"Frozen proof quick_check failed: {quick!r}")
        triggers = {
            str(row[0])
            for row in db.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='trigger' AND tbl_name='frozen_proof_objects'
                """
            )
        }
        required_suffixes = {"update", "delete"}
        found_suffixes = {
            suffix
            for suffix in required_suffixes
            if any(name.lower().endswith(suffix) for name in triggers)
        }
        if found_suffixes != required_suffixes:
            raise ObservationFailure(
                f"Frozen proof immutable triggers missing: {sorted(triggers)!r}"
            )

        rows = db.execute(
            """
            SELECT object_identity, analysis_identity, object_kind, family,
                   as_of_ms, market_available_at_ms, observed_at_ms,
                   persisted_at_ms, payload_sha256, object_json
            FROM frozen_proof_objects
            ORDER BY persisted_at_ms, object_identity
            """
        ).fetchall()
        if not rows:
            raise ObservationFailure("Frozen proof store is empty")

        latest_as_of_ms = 0
        families: set[str] = set()
        for row in rows:
            object_json = str(row["object_json"])
            raw = json.loads(object_json)
            if not isinstance(raw, dict):
                raise ObservationFailure("Frozen proof object JSON must be object")
            if _canonical_json(raw) != object_json:
                raise ObservationFailure(
                    f"Frozen proof JSON is not canonical: {row['object_identity']}"
                )
            for key in (
                "object_identity",
                "object_kind",
                "family",
                "as_of_ms",
                "market_available_at_ms",
                "observed_at_ms",
                "persisted_at_ms",
            ):
                if raw.get(key) != row[key]:
                    raise ObservationFailure(
                        f"Frozen proof row/object mismatch: {key}: "
                        f"{row['object_identity']}"
                    )
            if raw.get("analysis_identity") != row["analysis_identity"]:
                raise ObservationFailure(
                    "Frozen proof analysis identity row/object mismatch"
                )
            as_of_ms = int(row["as_of_ms"])
            available_ms = int(row["market_available_at_ms"])
            observed_ms = int(row["observed_at_ms"])
            persisted_ms = int(row["persisted_at_ms"])
            if available_ms > as_of_ms or observed_ms > as_of_ms:
                raise ObservationFailure(
                    f"Frozen proof contains future evidence: {row['object_identity']}"
                )
            if persisted_ms < max(available_ms, observed_ms):
                raise ObservationFailure(
                    f"Frozen proof persistence predates evidence: "
                    f"{row['object_identity']}"
                )
            if raw.get("production_authority") is not False:
                raise ObservationFailure("Frozen proof grants production authority")
            if raw.get("real_capital") != 0:
                raise ObservationFailure("Frozen proof REAL_CAPITAL boundary violated")
            payload_json = raw.get("payload_json")
            if not isinstance(payload_json, str):
                raise ObservationFailure("Frozen proof payload_json missing")
            if _sha256_text(payload_json) != str(row["payload_sha256"]):
                raise ObservationFailure(
                    f"Frozen proof payload hash mismatch: {row['object_identity']}"
                )
            latest_as_of_ms = max(latest_as_of_ms, as_of_ms)
            families.add(str(row["family"]))

    return {
        "path": str(path),
        "quick_check": "ok",
        "object_count": len(rows),
        "family_count": len(families),
        "families": sorted(families),
        "latest_as_of_ms": latest_as_of_ms,
        "immutable_update_delete_triggers": True,
        "all_objects_no_future_pass": True,
        "all_payload_hashes_pass": True,
        "real_capital": 0,
    }


def _inspect_supporting_sqlite(root: Path) -> dict[str, object]:
    runtime = root / "Development/runtime"
    paths = {
        "provider_divergence": runtime / "data/provider_divergence.sqlite3",
        "event_source": runtime / "events/event_source.sqlite3",
        "options_surface": runtime / "market_tape/options_surface.sqlite3",
        "onchain_capital_flow": runtime / "onchain/onchain_capital_flow.sqlite3",
        "onchain_source_contract": runtime / "onchain/source_contract.sqlite3",
    }
    return {name: _quick_check(path) for name, path in paths.items()}


def build_observation(
    *,
    root: Path,
    expected_runtime_sha: str,
    epoch_id: str,
    now_ms: int,
    max_ingestion_age_ms: int,
    observer_contract_sha256: str,
) -> dict[str, object]:
    if len(expected_runtime_sha) != 40 or any(
        ch not in "0123456789abcdef" for ch in expected_runtime_sha
    ):
        raise ValueError("expected runtime SHA must be a 40-char lowercase git SHA")
    if not epoch_id.strip():
        raise ValueError("epoch_id must be non-empty")
    if max_ingestion_age_ms <= 0:
        raise ValueError("max_ingestion_age_ms must be positive")

    product = _inspect_product(root, expected_runtime_sha)
    market_tape = _inspect_collector(
        root,
        max_ingestion_age_ms=max_ingestion_age_ms,
    )
    stream = _inspect_stream(root)
    frozen = _inspect_frozen_proofs(root)
    supporting = _inspect_supporting_sqlite(root)
    explicit_degradation_count = int(market_tape["explicit_degradation_count"])
    completed_at_ms = time.time_ns() // 1_000_000
    if completed_at_ms < now_ms:
        raise ObservationFailure("observation completion timestamp moved backwards")
    status = (
        "pass_with_explicit_degradation"
        if explicit_degradation_count > 0
        else "pass"
    )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "epoch_id": epoch_id,
        "expected_runtime_sha": expected_runtime_sha,
        "observer_contract_sha256": observer_contract_sha256,
        "started_at_ms": now_ms,
        "started_at_utc": _utc_iso(now_ms),
        "observed_at_ms": completed_at_ms,
        "observed_at_utc": _utc_iso(completed_at_ms),
        "status": status,
        "product": product,
        "market_tape": market_tape,
        "stream": stream,
        "frozen_proofs": frozen,
        "supporting_sqlite": supporting,
        "historical_backfill": "NO",
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    payload["observation_identity"] = _sha256_text(_canonical_json(payload))
    return payload


def _write_json_exclusive(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def _read_json_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ObservationFailure(f"JSON object required: {path}")
    return {str(key): value for key, value in raw.items()}


def _validate_anchor(
    anchor: dict[str, Any],
    *,
    epoch_id: str,
    expected_runtime_sha: str,
    observer_contract_sha256: str,
) -> None:
    expected = {
        "schema_version": ANCHOR_SCHEMA_VERSION,
        "epoch_id": epoch_id,
        "expected_runtime_sha": expected_runtime_sha,
        "observer_contract_sha256": observer_contract_sha256,
        "real_capital": 0,
        "historical_backfill": "NO",
    }
    for key, value in expected.items():
        if anchor.get(key) != value:
            raise ObservationFailure(
                f"soak anchor mismatch: {key}={anchor.get(key)!r} expected={value!r}"
            )


def _anchor_from_observation(
    observation: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": ANCHOR_SCHEMA_VERSION,
        "epoch_id": observation["epoch_id"],
        "expected_runtime_sha": observation["expected_runtime_sha"],
        "observer_contract_sha256": observation["observer_contract_sha256"],
        "started_at_ms": observation["observed_at_ms"],
        "started_at_utc": observation["observed_at_utc"],
        "first_observation_identity": observation["observation_identity"],
        "historical_backfill": "NO",
        "production_authority": False,
        "real_capital": 0,
    }


def _write_invalidation_once(
    epoch_dir: Path,
    *,
    epoch_id: str,
    expected_runtime_sha: str,
    observer_contract_sha256: str,
    observed_at_ms: int,
    error: Exception,
) -> None:
    path = epoch_dir / "invalidated.json"
    if path.exists():
        return
    value = {
        "schema_version": INVALIDATION_SCHEMA_VERSION,
        "epoch_id": epoch_id,
        "expected_runtime_sha": expected_runtime_sha,
        "observer_contract_sha256": observer_contract_sha256,
        "invalidated_at_ms": observed_at_ms,
        "invalidated_at_utc": _utc_iso(observed_at_ms),
        "reason_type": type(error).__name__,
        "reason": str(error),
        "historical_backfill": "NO",
        "production_authority": False,
        "real_capital": 0,
    }
    try:
        _write_json_exclusive(path, value)
    except FileExistsError:
        pass


def _write_optional_output(path: Path | None, value: object) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--sidecar-root", type=Path, default=DEFAULT_SIDECAR_ROOT)
    parser.add_argument("--expected-runtime-sha", required=True)
    parser.add_argument("--epoch-id", required=True)
    parser.add_argument(
        "--max-ingestion-age-ms",
        type=int,
        default=DEFAULT_MAX_INGESTION_AGE_MS,
    )
    parser.add_argument("--initialize-if-missing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now_ms = time.time_ns() // 1_000_000
    contract_sha = _observer_contract_sha256()
    epoch_dir = args.sidecar_root / args.epoch_id
    anchor_path = epoch_dir / "anchor.json"
    invalidated_path = epoch_dir / "invalidated.json"

    if not args.dry_run and invalidated_path.exists():
        invalidated = _read_json_object(invalidated_path)
        raise ObservationFailure(
            "soak epoch is already invalidated: "
            f"{invalidated.get('reason_type')}:{invalidated.get('reason')}"
        )

    anchor: dict[str, Any] | None = None
    if not args.dry_run and anchor_path.exists():
        anchor = _read_json_object(anchor_path)
        try:
            _validate_anchor(
                anchor,
                epoch_id=args.epoch_id,
                expected_runtime_sha=args.expected_runtime_sha,
                observer_contract_sha256=contract_sha,
            )
        except Exception as exc:
            _write_invalidation_once(
                epoch_dir,
                epoch_id=args.epoch_id,
                expected_runtime_sha=args.expected_runtime_sha,
                observer_contract_sha256=contract_sha,
                observed_at_ms=now_ms,
                error=exc,
            )
            raise

    try:
        observation = build_observation(
            root=args.root,
            expected_runtime_sha=args.expected_runtime_sha,
            epoch_id=args.epoch_id,
            now_ms=now_ms,
            max_ingestion_age_ms=args.max_ingestion_age_ms,
            observer_contract_sha256=contract_sha,
        )
    except Exception as exc:
        failure: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "epoch_id": args.epoch_id,
            "expected_runtime_sha": args.expected_runtime_sha,
            "observer_contract_sha256": contract_sha,
            "observed_at_ms": now_ms,
            "observed_at_utc": _utc_iso(now_ms),
            "status": "fail",
            "reason_type": type(exc).__name__,
            "reason": str(exc),
            "historical_backfill": "NO",
            "production_authority": False,
            "real_capital": 0,
        }
        failure["observation_identity"] = _sha256_text(_canonical_json(failure))
        _write_optional_output(args.output, failure)
        if not args.dry_run and anchor is not None:
            failure_path = (
                epoch_dir
                / "failures"
                / f"{now_ms}-{str(failure['observation_identity'])[:16]}.json"
            )
            try:
                _write_json_exclusive(failure_path, failure)
            except FileExistsError:
                pass
            _write_invalidation_once(
                epoch_dir,
                epoch_id=args.epoch_id,
                expected_runtime_sha=args.expected_runtime_sha,
                observer_contract_sha256=contract_sha,
                observed_at_ms=now_ms,
                error=exc,
            )
        raise

    if args.dry_run:
        _write_optional_output(args.output, observation)
        print("RDP11_SOAK_OBSERVER_DRY_RUN_PASS=YES")
        print(f"RDP11_RUNTIME_TARGET={args.expected_runtime_sha}")
        print(f"RDP11_OBSERVER_CONTRACT_SHA256={contract_sha}")
        print("HISTORICAL_BACKFILL=NO")
        print("REAL_CAPITAL=0")
        return 0

    if anchor is None:
        if not args.initialize_if_missing:
            raise ObservationFailure(
                "soak anchor missing; pass --initialize-if-missing only for "
                "the intended first successful observation"
            )
        anchor = _anchor_from_observation(observation)
        _write_json_exclusive(anchor_path, anchor)
        print("RDP11_SOAK_ANCHOR_CREATED=YES")
        print(f"RDP11_SOAK_START_UTC={anchor['started_at_utc']}")
    else:
        print("RDP11_SOAK_ANCHOR_REUSED=YES")

    observation_path = (
        epoch_dir
        / "observations"
        / f"{now_ms}-{str(observation['observation_identity'])[:16]}.json"
    )
    _write_json_exclusive(observation_path, observation)

    started_at_ms = int(anchor["started_at_ms"])
    elapsed_ms = max(0, now_ms - started_at_ms)
    status = {
        "epoch_id": args.epoch_id,
        "expected_runtime_sha": args.expected_runtime_sha,
        "observer_contract_sha256": contract_sha,
        "started_at_ms": started_at_ms,
        "started_at_utc": anchor["started_at_utc"],
        "latest_observed_at_ms": now_ms,
        "latest_observed_at_utc": _utc_iso(now_ms),
        "elapsed_ms": elapsed_ms,
        "required_ms": SOAK_REQUIRED_MS,
        "eligible_72h": elapsed_ms >= SOAK_REQUIRED_MS,
        "latest_observation_identity": observation["observation_identity"],
        "latest_status": observation["status"],
        "invalidated": False,
        "historical_backfill": "NO",
        "real_capital": 0,
    }
    _write_optional_output(args.output, {"observation": observation, "soak": status})
    print("RDP11_SOAK_OBSERVATION_PASS=YES")
    print(f"RDP11_SOAK_ELAPSED_MS={elapsed_ms}")
    print(
        "RDP11_SOAK_72H_ELIGIBLE="
        + ("YES" if status["eligible_72h"] else "NO")
    )
    print("RDP11_SOAK_SIDE_CAR_ONLY=YES")
    print("HISTORICAL_BACKFILL=NO")
    print("REAL_CAPITAL=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
