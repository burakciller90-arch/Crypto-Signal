from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from crypto_signal.data.event_risk import (
    EventCategory,
    EventSourceQuality,
    build_event_calendar_coverage,
    build_structured_event_observation,
    event_calendar_coverage_payload,
    structured_event_payload,
)
from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_json
from crypto_signal.product.intelligence_stream_family import (
    StreamFamilyProjectionDisposition,
)
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
)
from crypto_signal.product.intelligence_stream_production_projector import (
    IntelligenceStreamProductionProjector,
)
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
)
from crypto_signal.product.intelligence_stream_trust_sources import (
    build_event_risk_stream_snapshots,
    build_provider_quality_stream_snapshot,
)
from crypto_signal.product.provider_divergence_runtime import (
    ProviderDivergenceRuntimeTruth,
    ProviderQualityRuntimeTruth,
)


def _stream_path(tmp_path: Path) -> Path:
    path = tmp_path / "stream.sqlite3"
    IntelligenceStreamForwardRuntime(path).ensure_activated(activated_at_ms=1)
    return path


def _event_source_path(tmp_path: Path, *, base_ms: int) -> Path:
    path = tmp_path / "event_source.sqlite3"
    coverage = build_event_calendar_coverage(
        coverage_start_ms=base_ms - 3_600_000,
        coverage_end_ms=base_ms + 8 * 3_600_000,
        categories=(EventCategory.INFLATION,),
        source_provider="fred.test",
        source_quality=EventSourceQuality.SECONDARY_AGGREGATOR,
        source=DataSource.REST,
        observed_at_ms=base_ms - 60_000,
        adapter_version="test-calendar/1",
    )
    event = build_structured_event_observation(
        provider_event_id="cpi-test",
        title="CPI test event",
        category=EventCategory.INFLATION,
        scheduled_at_ms=base_ms + 45 * 60_000,
        affected_assets=(),
        source_provider="fred.test",
        source_quality=EventSourceQuality.SECONDARY_AGGREGATOR,
        source=DataSource.REST,
        source_timestamp_ms=base_ms - 120_000,
        ingested_at_ms=base_ms - 60_000,
        adapter_version="test-calendar/1",
    )
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE event_calendar_coverages (
                coverage_identity TEXT PRIMARY KEY,
                source_provider TEXT NOT NULL,
                observed_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE structured_event_observations (
                event_identity TEXT PRIMARY KEY,
                provider_event_id TEXT NOT NULL,
                source_provider TEXT NOT NULL,
                scheduled_at_ms INTEGER NOT NULL,
                ingested_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO event_calendar_coverages
            VALUES (?, ?, ?, ?)
            """,
            (
                coverage.coverage_identity,
                coverage.source_provider,
                coverage.observed_at_ms,
                canonical_json(event_calendar_coverage_payload(coverage)),
            ),
        )
        connection.execute(
            """
            INSERT INTO structured_event_observations
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_identity,
                event.provider_event_id,
                event.source_provider,
                event.scheduled_at_ms,
                event.ingested_at_ms,
                canonical_json(structured_event_payload(event)),
            ),
        )
    return path


def _provider_truth(
    *,
    snapshot_identity: str,
    observed_at_ms: int,
    observation_age_ms: int,
) -> ProviderDivergenceRuntimeTruth:
    left_id = "1" * 64
    right_id = "2" * 64
    left = ProviderQualityRuntimeTruth(
        exchange="binance",
        available=True,
        consumed_closed_candles=1,
        latest_open_time_ms=observed_at_ms - 900_000,
        latest_source_age_ms=100_000,
        latest_closed_age_ms=100_000,
        stale=False,
        freshness_reasons=(),
        gap_count=0,
        gap_missing_candles=0,
    )
    right = ProviderQualityRuntimeTruth(
        exchange="bybit",
        available=True,
        consumed_closed_candles=1,
        latest_open_time_ms=observed_at_ms - 900_000,
        latest_source_age_ms=100_000,
        latest_closed_age_ms=100_000,
        stale=False,
        freshness_reasons=(),
        gap_count=0,
        gap_missing_candles=0,
    )
    return ProviderDivergenceRuntimeTruth(
        snapshot_identity=snapshot_identity,
        semantic="spot_candle_close_grid_divergence",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=observed_at_ms,
        observation_age_ms=observation_age_ms,
        lookback_limit=1,
        left_exchange="binance",
        right_exchange="bybit",
        left_quality=left,
        right_quality=right,
        left_source_evidence_identities=(left_id,),
        right_source_evidence_identities=(right_id,),
        overlap_count=1,
        left_only_open_times_ms=(),
        right_only_open_times_ms=(),
        latest_overlap_open_time_ms=observed_at_ms - 900_000,
        latest_close_spread_bps=Decimal("0.4"),
        median_absolute_close_spread_bps=Decimal("0.4"),
        max_absolute_close_spread_bps=Decimal("0.4"),
        grid_state="full_overlap",
    )


def test_event_risk_source_scoped_transition_uses_canonical_story(
    tmp_path: Path,
) -> None:
    base_ms = 10_000_000
    source_path = _event_source_path(tmp_path, base_ms=base_ms)
    stream_path = _stream_path(tmp_path)
    projector = IntelligenceStreamProductionProjector(stream_path)
    projector.ensure_family_activation(
        "event_risk_change",
        activated_at_ms=base_ms - 1,
    )

    caution = build_event_risk_stream_snapshots(
        source_path,
        evaluated_at_ms=base_ms,
    )
    assert len(caution) == 1
    assert caution[0].state_label == "pre_event_caution"
    first = projector.project_family(
        caution[0],
        activated_at_ms=base_ms - 1,
    )

    block_time = base_ms + 35 * 60_000
    blocked = build_event_risk_stream_snapshots(
        source_path,
        evaluated_at_ms=block_time,
    )
    assert blocked[0].state_label == "event_block"
    second = projector.project_family(
        blocked[0],
        activated_at_ms=base_ms - 1,
    )

    assert first.story_identity == second.story_identity
    assert first.narrative_identity is not None
    assert second.narrative_identity is not None

    detail = IntelligenceStreamReadModel(stream_path).read_message_detail(
        second.narrative_identity
    )
    assert detail is not None
    text = detail["narrative"]["text"]
    assert "blokluyorum" in text["intelligence_text"]
    assert "normal" in text["intelligence_text"].lower()
    assert "yön" in text["decision_text"].lower()


def test_provider_quality_real_freshness_contract_drives_degrade_and_recover(
    tmp_path: Path,
) -> None:
    observed_ms = 20_000_000
    stream_path = _stream_path(tmp_path)
    projector = IntelligenceStreamProductionProjector(stream_path)
    projector.ensure_family_activation(
        "provider_quality_change",
        activated_at_ms=observed_ms - 1,
    )

    healthy_truth = _provider_truth(
        snapshot_identity="a" * 64,
        observed_at_ms=observed_ms,
        observation_age_ms=100_000,
    )
    healthy = build_provider_quality_stream_snapshot(
        healthy_truth,
        evaluated_at_ms=observed_ms + 100_000,
    )
    assert healthy.state_label == "healthy"
    first = projector.project_family(
        healthy,
        activated_at_ms=observed_ms - 1,
    )

    stale_truth = _provider_truth(
        snapshot_identity="a" * 64,
        observed_at_ms=observed_ms,
        observation_age_ms=1_800_001,
    )
    stale = build_provider_quality_stream_snapshot(
        stale_truth,
        evaluated_at_ms=observed_ms + 1_800_001,
    )
    assert stale.state_label == "degraded_provider_stale"
    second = projector.project_family(
        stale,
        activated_at_ms=observed_ms - 1,
    )

    recovered_truth = _provider_truth(
        snapshot_identity="b" * 64,
        observed_at_ms=observed_ms + 2_000_000,
        observation_age_ms=100_000,
    )
    recovered = build_provider_quality_stream_snapshot(
        recovered_truth,
        evaluated_at_ms=observed_ms + 2_100_000,
    )
    assert recovered.state_label == "healthy"
    third = projector.project_family(
        recovered,
        activated_at_ms=observed_ms - 1,
    )

    assert first.story_identity == second.story_identity == third.story_identity
    assert first.narrative_identity is not None
    assert second.narrative_identity is not None
    assert third.narrative_identity is not None


def test_live_trust_policy_silences_initial_healthy_baseline_then_recovers(
    tmp_path: Path,
) -> None:
    observed_ms = 30_000_000
    stream_path = _stream_path(tmp_path)
    projector = IntelligenceStreamProductionProjector(stream_path)
    projector.ensure_family_activation(
        "provider_quality_change",
        activated_at_ms=observed_ms - 1,
    )

    healthy = build_provider_quality_stream_snapshot(
        _provider_truth(
            snapshot_identity="c" * 64,
            observed_at_ms=observed_ms,
            observation_age_ms=100_000,
        ),
        evaluated_at_ms=observed_ms + 100_000,
    )
    baseline = projector.project_family(
        healthy,
        activated_at_ms=observed_ms - 1,
        silent_initial_state_labels=("healthy",),
    )
    assert (
        baseline.disposition
        is StreamFamilyProjectionDisposition.SILENT_INITIAL_BASELINE
    )
    assert baseline.narrative_identity is None

    degraded = build_provider_quality_stream_snapshot(
        _provider_truth(
            snapshot_identity="c" * 64,
            observed_at_ms=observed_ms,
            observation_age_ms=1_800_001,
        ),
        evaluated_at_ms=observed_ms + 1_800_001,
    )
    degraded_result = projector.project_family(
        degraded,
        activated_at_ms=observed_ms - 1,
        silent_initial_state_labels=("healthy",),
    )
    assert degraded_result.narrative_identity is not None

    recovered = build_provider_quality_stream_snapshot(
        _provider_truth(
            snapshot_identity="d" * 64,
            observed_at_ms=observed_ms + 2_000_000,
            observation_age_ms=100_000,
        ),
        evaluated_at_ms=observed_ms + 2_100_000,
    )
    recovered_result = projector.project_family(
        recovered,
        activated_at_ms=observed_ms - 1,
        silent_initial_state_labels=("healthy",),
    )
    assert recovered_result.narrative_identity is not None
    assert recovered_result.story_identity == degraded_result.story_identity

    read_model = IntelligenceStreamReadModel(stream_path)
    degraded_detail = read_model.read_message_detail(
        degraded_result.narrative_identity
    )
    recovered_detail = read_model.read_message_detail(
        recovered_result.narrative_identity
    )
    assert degraded_detail is not None
    assert recovered_detail is not None

    degraded_text = degraded_detail["narrative"]["text"]
    recovered_text = recovered_detail["narrative"]["text"]
    assert "yeterince güvenilir değil" in degraded_text["intelligence_text"]
    assert "teyit gücünü düşürüyorum" in degraded_text["intelligence_text"]
    assert "Piyasa verisi sağlıklı" in recovered_text["collapsed_text"]
    assert "normal" in recovered_text["intelligence_text"].lower()
    assert "REAL_CAPITAL=0" in recovered_text["capital_text"]
