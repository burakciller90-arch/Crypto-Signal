from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REAL_CAPITAL = 0
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

REQUIRED_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("market_or_intelligence", ("market", "intelligence")),
    ("decision", ("decision",)),
    ("outcome", ("outcome",)),
    ("risk_or_system", ("risk", "system")),
)
CAPITAL_GROUP = ("capital", ("capital",))

EXACT_PROOF_STATUSES = {
    "ready",
    "ready_exact",
    "identity_only_exact",
    "unavailable_explicit",
}


class AuditError(RuntimeError):
    pass


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _require_sha256(value: object, label: str) -> str:
    text = str(value or "")
    if not SHA256_RE.fullmatch(text):
        raise AuditError(f"{label} is not lowercase SHA256")
    return text


def _require_read_only(payload: object, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AuditError(f"{label} must be an object")
    if payload.get("read_only") is not True:
        raise AuditError(f"{label} is not read-only")
    if int(payload.get("real_capital", -1)) != REAL_CAPITAL:
        raise AuditError(f"{label} crossed REAL_CAPITAL boundary")
    return payload


def _url(base_url: str, path: str, params: dict[str, object] | None = None) -> str:
    base = base_url.rstrip("/")
    url = f"{base}{path}"
    if params:
        encoded = urllib.parse.urlencode(
            [(key, str(value)) for key, value in params.items() if value is not None]
        )
        if encoded:
            url = f"{url}?{encoded}"
    return url


def _get_text(
    base_url: str,
    path: str,
    *,
    params: dict[str, object] | None = None,
    timeout_seconds: float = 8.0,
) -> str:
    request = urllib.request.Request(
        _url(base_url, path, params),
        headers={"Accept": "application/json,text/event-stream;q=0.9,*/*;q=0.1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise AuditError(f"GET {request.full_url} failed: {exc!r}") from exc
    return raw.decode("utf-8")


def _get_json(
    base_url: str,
    path: str,
    *,
    params: dict[str, object] | None = None,
    timeout_seconds: float = 8.0,
) -> dict[str, Any]:
    text = _get_text(
        base_url,
        path,
        params=params,
        timeout_seconds=timeout_seconds,
    )
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise AuditError(f"GET {path} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise AuditError(f"GET {path} did not return an object")
    return payload


def _walk_values(value: object, key: str) -> list[object]:
    found: list[object] = []
    if isinstance(value, dict):
        for current_key, current_value in value.items():
            if current_key == key:
                found.append(current_value)
            found.extend(_walk_values(current_value, key))
    elif isinstance(value, list):
        for current_value in value:
            found.extend(_walk_values(current_value, key))
    return found


def _first_text(value: object, key: str) -> str | None:
    for item in _walk_values(value, key):
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _page_items(payload: dict[str, Any], label: str) -> list[dict[str, Any]]:
    _require_read_only(payload, label)
    page = payload.get("page")
    if not isinstance(page, dict):
        raise AuditError(f"{label} missing page")
    if page.get("read_only") is not True:
        raise AuditError(f"{label} page is not read-only")
    if int(page.get("real_capital", -1)) != REAL_CAPITAL:
        raise AuditError(f"{label} page crossed REAL_CAPITAL boundary")
    raw_items = page.get("items", [])
    if not isinstance(raw_items, list):
        raise AuditError(f"{label} page items must be a list")
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise AuditError(f"{label} contains non-object item")
        items.append(raw)
    return items


def _proof_result(payload: dict[str, Any]) -> dict[str, object]:
    """Validate the accepted F6 exact-evidence contract.

    F8 is intentionally downstream of F6. The canonical proof surface is
    /api/stream/messages/<identity>/evidence, not the older decision-only
    /visual-proof endpoint.
    """

    _require_read_only(payload, "exact evidence response")
    if payload.get("status") != "ready":
        return {
            "status": str(payload.get("status") or "unknown").lower(),
            "reason": str(payload.get("reason") or "") or None,
            "accepted_fail_closed": False,
            "resolution_states": [],
        }

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        raise AuditError("exact evidence response missing evidence body")
    if evidence.get("read_only") is not True:
        raise AuditError("exact evidence body is not read-only")
    if evidence.get("production_authority") is not False:
        raise AuditError("exact evidence crossed production authority boundary")
    if int(evidence.get("real_capital", -1)) != REAL_CAPITAL:
        raise AuditError("exact evidence crossed REAL_CAPITAL boundary")
    if evidence.get("current_data_substitution") is True:
        raise AuditError("exact evidence substituted current data")

    resolutions = evidence.get("resolutions")
    if not isinstance(resolutions, (list, tuple)):
        raise AuditError("exact evidence resolutions must be a list")
    if not resolutions:
        return {
            "status": "ready",
            "reason": "no_exact_evidence_resolutions",
            "accepted_fail_closed": False,
            "resolution_states": [],
        }

    states: list[str] = []
    for row in resolutions:
        if not isinstance(row, dict):
            raise AuditError("exact evidence resolution must be an object")
        if row.get("current_data_substitution") is True:
            raise AuditError("exact evidence resolution substituted current data")
        state = str(row.get("resolution_state") or "").strip().lower()
        states.append(state)
        if state not in EXACT_PROOF_STATUSES:
            return {
                "status": "ready",
                "reason": f"unsupported_resolution_state:{state or 'missing'}",
                "accepted_fail_closed": False,
                "resolution_states": states,
            }

    return {
        "status": "ready",
        "reason": None,
        "accepted_fail_closed": True,
        "resolution_states": states,
    }

def _message_identity(item: dict[str, Any]) -> str:
    return _require_sha256(item.get("narrative_identity"), "narrative identity")


def _stable_exact_lookup(base_url: str, identity: str) -> tuple[dict[str, Any], bool]:
    path = f"/api/stream/messages/{identity}"
    first = _require_read_only(_get_json(base_url, path), "exact message response")
    second = _require_read_only(_get_json(base_url, path), "exact message response repeat")
    if first.get("status") != "ready" or second.get("status") != "ready":
        raise AuditError("exact persisted message lookup is not ready")
    message = first.get("message")
    repeated = second.get("message")
    if not isinstance(message, dict) or not isinstance(repeated, dict):
        raise AuditError("exact persisted message body missing")
    _require_sha256(message.get("narrative_identity"), "exact message identity")
    if message.get("narrative_identity") != identity:
        raise AuditError("exact lookup returned a different narrative identity")
    return message, _canonical(message) == _canonical(repeated)


def _detail_lookup(base_url: str, identity: str) -> dict[str, Any]:
    path = f"/api/stream/messages/{identity}/detail"
    payload = _require_read_only(_get_json(base_url, path), "message detail response")
    if payload.get("status") != "ready":
        raise AuditError("message detail is not ready")
    detail = payload.get("detail")
    if not isinstance(detail, dict):
        raise AuditError("message detail body missing")
    if detail.get("read_only") is not True:
        raise AuditError("message detail is not read-only")
    if detail.get("production_authority") is not False:
        raise AuditError("message detail crossed production authority boundary")
    if int(detail.get("real_capital", -1)) != REAL_CAPITAL:
        raise AuditError("message detail crossed REAL_CAPITAL boundary")
    narrative_values = {
        str(value)
        for value in _walk_values(detail, "narrative_identity")
        if isinstance(value, str) and SHA256_RE.fullmatch(value)
    }
    if identity not in narrative_values:
        raise AuditError("detail does not preserve narrative identity")
    return detail


def _filter_contains_identity(
    base_url: str,
    category: str,
    identity: str,
) -> bool:
    payload = _get_json(
        base_url,
        "/api/stream/messages",
        params={"category": category, "limit": 200},
    )
    return identity in {_message_identity(item) for item in _page_items(payload, "category filter")}


def _search_contains_identity(
    base_url: str,
    search_text: str | None,
    identity: str,
) -> bool | None:
    if not search_text:
        return None
    payload = _get_json(
        base_url,
        "/api/stream/messages",
        params={"text": search_text, "limit": 200},
    )
    return identity in {_message_identity(item) for item in _page_items(payload, "text search")}


def _inspect_message(
    base_url: str,
    *,
    category: str,
    item: dict[str, Any],
) -> dict[str, object]:
    identity = _message_identity(item)
    exact, stable = _stable_exact_lookup(base_url, identity)
    if not stable:
        raise AuditError("repeated exact lookup changed immutable message")

    detail = _detail_lookup(base_url, identity)
    proof = _proof_result(
        _get_json(base_url, f"/api/stream/messages/{identity}/evidence")
    )

    story_values = {
        str(value)
        for value in _walk_values(detail, "story_identity")
        if isinstance(value, str) and SHA256_RE.fullmatch(value)
    }
    source_values = {
        str(value)
        for value in _walk_values(detail, "source_event_identity")
        if isinstance(value, str) and SHA256_RE.fullmatch(value)
    }

    message_input_categories = {
        str(value).lower()
        for value in _walk_values(detail, "category")
        if isinstance(value, str)
    }
    if category != "capital" and message_input_categories and category not in message_input_categories:
        raise AuditError(
            f"detail category mismatch: expected {category}, got {sorted(message_input_categories)}"
        )

    if category != "capital":
        if not story_values:
            raise AuditError("regular Stream message lacks exact story identity")
        if not source_values:
            raise AuditError("regular Stream message lacks exact source-event identity")

    capital_lineage = {
        key: sorted(
            {
                str(value)
                for value in _walk_values(detail, key)
                if isinstance(value, str) and SHA256_RE.fullmatch(value)
            }
        )
        for key in ("bundle_identity", "intent_identity", "fill_identity")
    }

    search_text = (
        _first_text(exact, "symbol")
        or _first_text(detail, "symbol")
        or _first_text(exact, "asset")
        or _first_text(detail, "asset")
    )

    return {
        "category": category,
        "narrative_identity": identity,
        "event_at_ms": item.get("event_at_ms"),
        "story_identities": sorted(story_values),
        "source_event_identities": sorted(source_values),
        "source_kind": _first_text(detail, "source_kind") or _first_text(exact, "source_kind"),
        "subtype": _first_text(detail, "subtype") or _first_text(exact, "subtype"),
        "search_text": search_text,
        "filter_exact": _filter_contains_identity(base_url, category, identity),
        "search_exact": _search_contains_identity(base_url, search_text, identity),
        "immutable_repeat": stable,
        "proof": proof,
        "capital_lineage": capital_lineage,
        "read_only": True,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }


def _category_candidates(
    base_url: str,
    category: str,
    *,
    min_event_ms: int | None,
) -> list[dict[str, Any]]:
    params: dict[str, object] = {"category": category, "limit": 200}
    if min_event_ms is not None:
        params["from_ms"] = min_event_ms
    payload = _get_json(
        base_url,
        "/api/stream/messages",
        params=params,
    )
    return _page_items(payload, f"category={category}")


def _inspect_group(
    base_url: str,
    name: str,
    categories: Iterable[str],
    *,
    min_event_ms: int | None,
) -> dict[str, object]:
    errors: list[str] = []
    observed_counts: dict[str, int] = {}
    for category in categories:
        try:
            items = _category_candidates(
                base_url,
                category,
                min_event_ms=min_event_ms,
            )
            observed_counts[category] = len(items)
        except AuditError as exc:
            errors.append(f"{category}: {exc}")
            observed_counts[category] = 0
            continue
        for item in items:
            try:
                event = _inspect_message(base_url, category=category, item=item)
            except AuditError as exc:
                errors.append(f"{category}/{item.get('narrative_identity')}: {exc}")
                continue
            proof = event.get("proof")
            proof_ok = (
                isinstance(proof, dict)
                and proof.get("accepted_fail_closed") is True
            )
            filter_ok = event.get("filter_exact") is True
            search_value = event.get("search_exact")
            search_ok = search_value is None or search_value is True
            if proof_ok and filter_ok and search_ok:
                return {
                    "name": name,
                    "status": "ACCEPTED_CANDIDATE",
                    "observed_counts": observed_counts,
                    "representative": event,
                    "errors": errors,
                }
            errors.append(
                f"{category}/{event.get('narrative_identity')}: "
                f"proof_ok={proof_ok} filter_ok={filter_ok} search_ok={search_ok}"
            )
    return {
        "name": name,
        "status": "OPEN_NO_ACCEPTABLE_REAL_EVENT",
        "observed_counts": observed_counts,
        "representative": None,
        "errors": errors,
    }


def _parse_sse_identities(raw: str) -> list[str]:
    identities: list[str] = []
    for line in raw.splitlines():
        if not line.startswith("id:"):
            continue
        value = line.partition(":")[2].strip()
        if value:
            identities.append(value)
    return identities


def _audit_sse(base_url: str) -> dict[str, object]:
    page_payload = _get_json(
        base_url,
        "/api/stream/messages",
        params={"limit": 200},
    )
    page = page_payload.get("page")
    if not isinstance(page, dict):
        raise AuditError("SSE audit page missing")
    oldest_cursor = page.get("oldest_cursor")
    if not isinstance(oldest_cursor, str) or not oldest_cursor:
        return {
            "status": "DEFERRED_NO_STREAM_CURSOR",
            "event_ids": [],
            "duplicate_event_ids": [],
        }
    raw = _get_text(
        base_url,
        "/api/stream/live",
        params={
            "after": oldest_cursor,
            "batch_limit": 200,
            "follow": "false",
        },
        timeout_seconds=12.0,
    )
    ids = _parse_sse_identities(raw)
    duplicates = sorted({identity for identity in ids if ids.count(identity) > 1})
    return {
        "status": "PASS" if not duplicates else "FAIL_DUPLICATE_EVENT_ID",
        "event_ids": ids,
        "duplicate_event_ids": duplicates,
    }


def _audit_stream_ledger(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise AuditError(f"Stream ledger missing: {path}")
    uri = f"file:{path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("PRAGMA query_only = ON")
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            if quick_check != "ok":
                raise AuditError(f"Stream ledger quick_check failed: {quick_check}")
            activation_rows = connection.execute(
                "SELECT activated_at_ms FROM stream_activation "
                "ORDER BY activated_at_ms"
            ).fetchall()
            if len(activation_rows) != 1:
                raise AuditError("Stream ledger must contain exactly one activation boundary")
            activation_ms = int(activation_rows[0][0])
            historical_source_rows = int(
                connection.execute(
                    "SELECT COUNT(*) FROM stream_source_events WHERE event_at_ms < ?",
                    (activation_ms,),
                ).fetchone()[0]
            )
            duplicate_source_rows = int(
                connection.execute(
                    "SELECT COUNT(*) FROM ("
                    "SELECT source_event_identity FROM stream_source_events "
                    "GROUP BY source_event_identity HAVING COUNT(*) > 1"
                    ")"
                ).fetchone()[0]
            )
            duplicate_narrative_rows = int(
                connection.execute(
                    "SELECT COUNT(*) FROM ("
                    "SELECT narrative_identity FROM stream_narrative_messages "
                    "GROUP BY narrative_identity HAVING COUNT(*) > 1"
                    ")"
                ).fetchone()[0]
            )
            multi_narrative_source_rows = int(
                connection.execute(
                    "SELECT COUNT(*) FROM ("
                    "SELECT source_event_identity FROM stream_narrative_messages "
                    "GROUP BY source_event_identity HAVING COUNT(*) > 1"
                    ")"
                ).fetchone()[0]
            )
            source_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM stream_source_events"
                ).fetchone()[0]
            )
            narrative_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM stream_narrative_messages"
                ).fetchone()[0]
            )
    except sqlite3.Error as exc:
        raise AuditError(f"Stream ledger read-only audit failed: {exc}") from exc

    status = (
        "PASS"
        if (
            historical_source_rows == 0
            and duplicate_source_rows == 0
            and duplicate_narrative_rows == 0
            and multi_narrative_source_rows == 0
        )
        else "FAIL"
    )
    return {
        "status": status,
        "path": str(path),
        "quick_check": "ok",
        "activation_ms": activation_ms,
        "source_count": source_count,
        "narrative_count": narrative_count,
        "historical_source_rows_before_activation": historical_source_rows,
        "duplicate_source_identity_rows": duplicate_source_rows,
        "duplicate_narrative_identity_rows": duplicate_narrative_rows,
        "multi_narrative_rows_for_one_source": multi_narrative_source_rows,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
    }


def run_audit(
    base_url: str,
    *,
    require_capital: bool,
    min_event_ms: int | None,
    stream_ledger: Path | None,
) -> dict[str, object]:
    health = _get_json(base_url, "/api/health")
    if health.get("status") != "ok":
        raise AuditError("Product health is not ok")
    if health.get("read_only") is not True:
        raise AuditError("Product is not read-only")
    if int(health.get("real_capital", -1)) != REAL_CAPITAL:
        raise AuditError("Product health crossed REAL_CAPITAL boundary")
    if health.get("stream_root_active") is not True:
        raise AuditError("Intelligence Stream is not the active Product root")

    groups = [
        _inspect_group(
            base_url,
            name,
            categories,
            min_event_ms=min_event_ms,
        )
        for name, categories in REQUIRED_GROUPS
    ]
    capital = _inspect_group(
        base_url,
        *CAPITAL_GROUP,
        min_event_ms=min_event_ms,
    )
    capital["required"] = require_capital
    groups.append(capital)

    sse = _audit_sse(base_url)
    ledger_audit = (
        None if stream_ledger is None else _audit_stream_ledger(stream_ledger)
    )
    required_open = [
        str(group["name"])
        for group in groups
        if (
            group.get("status") != "ACCEPTED_CANDIDATE"
            and (group.get("name") != "capital" or require_capital)
        )
    ]
    if sse.get("status") not in {"PASS", "DEFERRED_NO_STREAM_CURSOR"}:
        required_open.append("sse_duplicate_audit")
    if ledger_audit is not None and ledger_audit.get("status") != "PASS":
        required_open.append("stream_ledger_negative_acceptance")

    return {
        "schema_version": "stream-final-f8-production-e2e-audit-v1/1",
        "base_url": base_url.rstrip("/"),
        "health": {
            "status": health.get("status"),
            "product_root": health.get("product_root"),
            "stream_root_active": health.get("stream_root_active"),
            "read_only": health.get("read_only"),
            "real_capital": health.get("real_capital"),
        },
        "observation_min_event_ms": min_event_ms,
        "groups": groups,
        "sse": sse,
        "stream_ledger_negative_acceptance": ledger_audit,
        "open_requirements": required_open,
        "status": "PASS_CANDIDATES_PRESENT" if not required_open else "OPEN",
        "historical_backfill_used": False,
        "synthetic_activity_used": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:48700")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-capital", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--min-event-ms", type=int, default=None)
    parser.add_argument("--stream-ledger", type=Path, default=None)
    args = parser.parse_args()

    try:
        if args.min_event_ms is not None and args.min_event_ms < 0:
            raise AuditError("--min-event-ms must be non-negative")
        report = run_audit(
            args.base_url,
            require_capital=args.require_capital,
            min_event_ms=args.min_event_ms,
            stream_ledger=args.stream_ledger,
        )
    except AuditError as exc:
        report = {
            "schema_version": "stream-final-f8-production-e2e-audit-v1/1",
            "base_url": args.base_url.rstrip("/"),
            "status": "ERROR",
            "error": str(exc),
            "historical_backfill_used": False,
            "synthetic_activity_used": False,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
        }
        _write_report(args.output, report)
        print(f"F8_PRODUCTION_E2E_AUDIT_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    _write_report(args.output, report)
    print(f"F8_PRODUCTION_E2E_STATUS={report['status']}")
    print(f"F8_OPEN_REQUIREMENTS={','.join(report.get('open_requirements', [])) or 'NONE'}")
    print("HISTORICAL_BACKFILL=NO")
    print("SYNTHETIC_ACTIVITY=NO")
    print("REAL_CAPITAL=0")
    if args.require_complete and report["status"] != "PASS_CANDIDATES_PRESENT":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
