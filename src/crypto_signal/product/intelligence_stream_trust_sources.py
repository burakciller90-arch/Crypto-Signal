from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from crypto_signal.data.event_risk import (
    EventCalendarCoverage,
    EventCategory,
    EventSourceQuality,
    StructuredEventObservation,
)
from crypto_signal.data.models import DataSource
from crypto_signal.data.timeframes import spec as timeframe_spec
from crypto_signal.intelligence.event_risk import (
    EventRiskConfig,
    EventRiskState,
    build_event_risk_evidence_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_family import (
    StreamFamilySnapshot,
    StreamTrustDomain,
    build_family_snapshot,
)
from crypto_signal.product.intelligence_stream_models import (
    StreamCategory,
    StreamImportance,
)
from crypto_signal.product.provider_divergence_runtime import (
    ProviderDivergenceRuntimeTruth,
    read_provider_divergence_runtime_truth,
)

EVENT_RISK_PROJECTOR_ID = "event_risk_change"
PROVIDER_QUALITY_PROJECTOR_ID = "provider_quality_change"
GLOBAL_RISK_ASSET = "CRYPTO"


def build_event_risk_stream_snapshots(
    event_source_path: Path,
    *,
    evaluated_at_ms: int,
) -> tuple[StreamFamilySnapshot, ...]:
    """Project exact provider-scoped structured-event risk state.

    Each calendar provider remains source-scoped. We do not merge independent
    provider coverages into synthetic global coverage.
    """
    if evaluated_at_ms < 0:
        raise ValueError("event-risk Stream evaluation time cannot be negative")
    coverages, events_by_provider = _read_event_calendar_truth(
        event_source_path,
        evaluated_at_ms=evaluated_at_ms,
    )
    snapshots: list[StreamFamilySnapshot] = []
    for coverage in coverages:
        provider_events = events_by_provider.get(coverage.source_provider, ())
        config = EventRiskConfig(required_categories=coverage.categories)
        freeze = build_event_risk_evidence_freeze(
            provider_events,
            coverage=coverage,
            asset=GLOBAL_RISK_ASSET,
            as_of_ms=evaluated_at_ms,
            config=config,
        )
        analysis = freeze.analysis
        subtype = (
            "event_risk_block"
            if analysis.state is EventRiskState.EVENT_BLOCK
            else "event_risk_change"
        )
        evidence = {
            freeze.freeze_identity,
            coverage.coverage_identity,
            *analysis.consumed_event_identities,
        }
        components: list[tuple[str, str]] = [
            ("risk_state", analysis.state.value),
            ("coverage_provider", coverage.source_provider),
            ("coverage_quality", coverage.source_quality.value),
            (
                "nearest_event_identity",
                analysis.nearest_event_identity or "none",
            ),
            (
                "nearest_event_scheduled_at_ms",
                str(analysis.nearest_event_scheduled_at_ms)
                if analysis.nearest_event_scheduled_at_ms is not None
                else "none",
            ),
        ]
        snapshots.append(
            build_family_snapshot(
                projector_id=EVENT_RISK_PROJECTOR_ID,
                family=StreamTrustDomain.EVENT_RISK,
                category=StreamCategory.RISK,
                subtype=subtype,
                importance=StreamImportance.IMPORTANT,
                source_event_identity=freeze.freeze_identity,
                source_scope=(
                    f"{coverage.source_provider}:"
                    f"{','.join(item.value for item in coverage.categories)}:"
                    "event_risk"
                ),
                asset=GLOBAL_RISK_ASSET,
                symbol=GLOBAL_RISK_ASSET,
                market="GLOBAL",
                timeframe="event_window",
                event_at_ms=evaluated_at_ms,
                source_as_of_ms=evaluated_at_ms,
                evidence_identities=tuple(sorted(evidence)),
                evidence_domains=("event_calendar", "event_risk"),
                state_label=analysis.state.value,
                state_components=tuple(components),
                direction=None,
                source_quality=coverage.source_quality.value,
                uncertainty_flags=analysis.uncertainty_flags,
            )
        )
    return tuple(
        sorted(
            snapshots,
            key=lambda item: (
                item.source_scope,
                item.source_event_identity,
            ),
        )
    )


def build_provider_quality_stream_snapshots(
    provider_divergence_path: Path,
    *,
    evaluated_at_ms: int,
) -> tuple[StreamFamilySnapshot, ...]:
    """Project only discrete provider/data-quality trust states.

    Spread values are preserved by the referenced immutable divergence snapshot
    but are deliberately not thresholded here.
    """
    truths = read_provider_divergence_runtime_truth(
        provider_divergence_path,
        observed_at_ms=evaluated_at_ms,
    )
    return tuple(
        build_provider_quality_stream_snapshot(
            item,
            evaluated_at_ms=evaluated_at_ms,
        )
        for item in truths
    )


def build_provider_quality_stream_snapshot(
    truth: ProviderDivergenceRuntimeTruth,
    *,
    evaluated_at_ms: int,
) -> StreamFamilySnapshot:
    freshness_limit_ms = 2 * timeframe_spec(truth.timeframe).duration_ms
    snapshot_stale = truth.observation_age_ms > freshness_limit_ms
    left = truth.left_quality
    right = truth.right_quality
    unavailable = not left.available or not right.available
    source_stale = left.stale or right.stale
    has_gaps = (
        left.gap_count > 0
        or right.gap_count > 0
        or left.gap_missing_candles > 0
        or right.gap_missing_candles > 0
    )

    if unavailable:
        state_label = "degraded_provider_unavailable"
    elif snapshot_stale or source_stale:
        state_label = "degraded_provider_stale"
    elif truth.grid_state == "no_overlap":
        state_label = "degraded_no_overlap"
    elif has_gaps or truth.grid_state == "partial_overlap":
        state_label = "caution_partial_coverage"
    else:
        state_label = "healthy"

    subtype = (
        "data_quality_recovered"
        if state_label == "healthy"
        else "data_quality_degraded"
    )
    uncertainty: set[str] = set()
    if snapshot_stale:
        uncertainty.add("provider_divergence_snapshot_stale")
    for quality, prefix in ((left, "left"), (right, "right")):
        if not quality.available:
            uncertainty.add(f"{prefix}_provider_unavailable")
        if quality.stale:
            uncertainty.add(f"{prefix}_provider_stale")
        if quality.gap_count > 0 or quality.gap_missing_candles > 0:
            uncertainty.add(f"{prefix}_provider_gap")
        uncertainty.update(
            f"{prefix}_{reason}" for reason in quality.freshness_reasons
        )
    if truth.grid_state != "full_overlap":
        uncertainty.add(f"provider_grid_{truth.grid_state}")

    source_event_identity = canonical_sha256(
        {
            "evaluated_at_ms": evaluated_at_ms,
            "projector_id": PROVIDER_QUALITY_PROJECTOR_ID,
            "snapshot_identity": truth.snapshot_identity,
            "state_label": state_label,
            "version": "stream-final-f4-provider-trust-source-v1/1",
        }
    )
    return build_family_snapshot(
        projector_id=PROVIDER_QUALITY_PROJECTOR_ID,
        family=StreamTrustDomain.PROVIDER_QUALITY,
        category=StreamCategory.SYSTEM,
        subtype=subtype,
        importance=StreamImportance.IMPORTANT,
        source_event_identity=source_event_identity,
        source_scope=(
            f"{truth.left_exchange}:{truth.right_exchange}:"
            f"{truth.market_type}:provider_divergence"
        ),
        asset=_base_asset(truth.symbol),
        symbol=truth.symbol,
        market=truth.symbol,
        timeframe=truth.timeframe,
        event_at_ms=evaluated_at_ms,
        source_as_of_ms=truth.observed_at_ms,
        evidence_identities=(truth.snapshot_identity,),
        evidence_domains=("data_quality", "provider_divergence"),
        state_label=state_label,
        state_components=(
            ("grid_state", truth.grid_state),
            ("left_available", _yes_no(left.available)),
            ("left_gap", _yes_no(left.gap_count > 0)),
            ("left_stale", _yes_no(left.stale)),
            ("right_available", _yes_no(right.available)),
            ("right_gap", _yes_no(right.gap_count > 0)),
            ("right_stale", _yes_no(right.stale)),
            ("snapshot_stale", _yes_no(snapshot_stale)),
        ),
        direction=None,
        source_quality=state_label,
        uncertainty_flags=tuple(sorted(uncertainty)),
    )


def _read_event_calendar_truth(
    path: Path,
    *,
    evaluated_at_ms: int,
) -> tuple[
    tuple[EventCalendarCoverage, ...],
    dict[str, tuple[StructuredEventObservation, ...]],
]:
    if not path.is_file():
        raise ValueError("event source runtime database missing")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            raise ValueError("event source SQLite quick_check failed")

        coverage_rows = connection.execute(
            """
            SELECT coverage_identity, source_provider, observed_at_ms, payload_json
            FROM event_calendar_coverages AS c
            WHERE c.observed_at_ms <= ?
              AND c.rowid = (
                SELECT candidate.rowid
                FROM event_calendar_coverages AS candidate
                WHERE candidate.source_provider = c.source_provider
                  AND candidate.observed_at_ms <= ?
                ORDER BY candidate.observed_at_ms DESC, candidate.rowid DESC
                LIMIT 1
              )
            ORDER BY source_provider
            """,
            (evaluated_at_ms, evaluated_at_ms),
        ).fetchall()
        event_rows = connection.execute(
            """
            SELECT event_identity, source_provider, payload_json
            FROM structured_event_observations
            WHERE ingested_at_ms <= ?
            ORDER BY source_provider, scheduled_at_ms, event_identity
            """,
            (evaluated_at_ms,),
        ).fetchall()

    coverages = tuple(_coverage_from_row(row) for row in coverage_rows)
    events: dict[str, list[StructuredEventObservation]] = {}
    for row in event_rows:
        item = _event_from_row(row)
        events.setdefault(item.source_provider, []).append(item)
    return (
        coverages,
        {
            provider: tuple(items)
            for provider, items in sorted(events.items())
        },
    )


def _coverage_from_row(row: sqlite3.Row) -> EventCalendarCoverage:
    payload = _json_object(str(row["payload_json"]))
    identity = str(row["coverage_identity"])
    if str(payload.get("source_provider")) != str(row["source_provider"]):
        raise ValueError("event coverage provider row/payload mismatch")
    if int(payload["observed_at_ms"]) != int(row["observed_at_ms"]):
        raise ValueError("event coverage time row/payload mismatch")
    return EventCalendarCoverage(
        coverage_identity=identity,
        schema_version=str(payload["schema_version"]),
        coverage_start_ms=int(payload["coverage_start_ms"]),
        coverage_end_ms=int(payload["coverage_end_ms"]),
        categories=tuple(
            EventCategory(str(value))
            for value in _string_list(payload["categories"])
        ),
        source_provider=str(payload["source_provider"]),
        source_quality=EventSourceQuality(str(payload["source_quality"])),
        source=DataSource(str(payload["source"])),
        observed_at_ms=int(payload["observed_at_ms"]),
        adapter_version=str(payload["adapter_version"]),
    )


def _event_from_row(row: sqlite3.Row) -> StructuredEventObservation:
    payload = _json_object(str(row["payload_json"]))
    identity = str(row["event_identity"])
    if str(payload.get("source_provider")) != str(row["source_provider"]):
        raise ValueError("structured event provider row/payload mismatch")
    return StructuredEventObservation(
        event_identity=identity,
        schema_version=str(payload["schema_version"]),
        provider_event_id=str(payload["provider_event_id"]),
        title=str(payload["title"]),
        category=EventCategory(str(payload["category"])),
        scheduled_at_ms=int(payload["scheduled_at_ms"]),
        affected_assets=tuple(_string_list(payload["affected_assets"])),
        source_provider=str(payload["source_provider"]),
        source_quality=EventSourceQuality(str(payload["source_quality"])),
        source=DataSource(str(payload["source"])),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        adapter_version=str(payload["adapter_version"]),
    )


def _json_object(value: str) -> dict[str, Any]:
    raw = json.loads(value)
    if not isinstance(raw, dict):
        raise TypeError("persisted source payload must be an object")
    return raw


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise TypeError("persisted source list must be an array")
    return [str(item) for item in value]


def _base_asset(symbol: str) -> str:
    normalized = symbol.upper()
    for quote in ("USDT", "USDC", "USD"):
        if normalized.endswith(quote) and len(normalized) > len(quote):
            return normalized[: -len(quote)]
    return normalized


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
