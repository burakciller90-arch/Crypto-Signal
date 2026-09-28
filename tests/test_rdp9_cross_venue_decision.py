from __future__ import annotations

from decimal import Decimal

import pytest
from test_immutable_forecast_stream import (
    AS_OF,
    HORIZON,
    ISSUED_AT,
    _event_context,
    _signal,
)
from test_unified_decision_runtime import (
    _family_evidence,
    _preflight,
)

from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.data.provider_divergence import (
    build_provider_divergence_snapshot,
)
from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceMatrixResolution,
    build_locked_m6_policy,
    evaluate_confluence_matrix,
)
from crypto_signal.intelligence.cross_venue_quality import (
    CrossVenueQualityState,
    assess_cross_venue_quality,
)
from crypto_signal.intelligence.meta_intelligence import MetaDirection
from crypto_signal.product.decision_proof import ProofEvidenceDomain
from crypto_signal.unified_decision_runtime import issue_unified_decision


def _candle(exchange: Exchange, close: str) -> Candle:
    value = Decimal(close)
    return Candle(
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=0,
        close_time_ms=899_999,
        open=value,
        high=value + Decimal(1),
        low=value - Decimal(1),
        close=value,
        volume=Decimal(2),
        quote_volume=Decimal(200),
        trade_count=10 if exchange is Exchange.BINANCE else None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=900_010,
        ingested_at_ms=900_020,
        adapter_version=f"{exchange.value}-rdp9-c-test/1",
    )


def _cross_venue(*, binance_close: str, bybit_close: str, as_of_ms: int = AS_OF):
    snapshot = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=as_of_ms,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=(_candle(Exchange.BINANCE, binance_close),),
        right_candles=(_candle(Exchange.BYBIT, bybit_close),),
        lookback_limit=96,
    )
    return assess_cross_venue_quality(snapshot)


def test_external_venue_conflict_changes_resolution_not_support_score() -> None:
    family = _family_evidence()
    conflict = _cross_venue(
        binance_close="101",
        bybit_close="100",
    )
    assert (
        conflict.state
        is CrossVenueQualityState.MATERIAL_PRICE_DISAGREEMENT
    )
    baseline = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        family,
        candidate_direction=MetaDirection.BULLISH,
    )
    conflicted = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        family,
        candidate_direction=MetaDirection.BULLISH,
        external_material_conflict_identities=(
            conflict.material_conflict_identities
        ),
    )

    assert baseline.resolution is ConfluenceMatrixResolution.MEASURED
    assert conflicted.resolution is ConfluenceMatrixResolution.CONFLICT
    assert conflicted.support_score_0_100 == baseline.support_score_0_100
    assert conflicted.opposition_score_0_100 == baseline.opposition_score_0_100
    assert conflicted.material_conflict_identities == (
        conflict.material_conflict_identities
    )


def test_unified_decision_freezes_material_cross_venue_conflict(
    tmp_path,
) -> None:
    signal = _signal()
    family = _family_evidence()
    event = _event_context()
    cross_venue = _cross_venue(
        binance_close="101",
        bybit_close="100",
    )

    result = issue_unified_decision(
        signal=signal,
        base_asset="BTC",
        regime="trend_up",
        family_evidence=family,
        event_context=event,
        preflight_proof_slices=_preflight(family, event),
        issued_at_ms=ISSUED_AT,
        horizon_bars=HORIZON,
        target_label="target_1",
        ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
        cross_venue_quality=cross_venue,
    )

    assert result.confluence.resolution is ConfluenceMatrixResolution.CONFLICT
    assert result.confluence.support_score_0_100 == Decimal("80.00")
    expected_lineage = {
        cross_venue.assessment_identity,
        cross_venue.provider_divergence_identity,
        *cross_venue.source_evidence_identities,
        *cross_venue.material_conflict_identities,
    }
    assert expected_lineage.issubset(
        set(result.forecast.source_evidence_identities)
    )
    methodology = next(
        item
        for item in result.proof.evidence_slices
        if item.domain is ProofEvidenceDomain.METHODOLOGY
    )
    assert expected_lineage.issubset(set(methodology.evidence_identities))
    assert result.production_authority is False
    assert result.real_capital == 0


def test_broad_cross_venue_context_is_lineage_only_not_score_authority(
    tmp_path,
) -> None:
    signal = _signal()
    family = _family_evidence()
    event = _event_context()
    cross_venue = _cross_venue(
        binance_close="100.10",
        bybit_close="100.00",
    )
    assert cross_venue.state is CrossVenueQualityState.TWO_VENUE_CONFIRMED

    result = issue_unified_decision(
        signal=signal,
        base_asset="BTC",
        regime="trend_up",
        family_evidence=family,
        event_context=event,
        preflight_proof_slices=_preflight(family, event),
        issued_at_ms=ISSUED_AT,
        horizon_bars=HORIZON,
        target_label="target_1",
        ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
        cross_venue_quality=cross_venue,
    )

    assert result.confluence.resolution is ConfluenceMatrixResolution.MEASURED
    assert result.confluence.support_score_0_100 == Decimal("80.00")
    assert cross_venue.material_conflict_identities == ()
    assert cross_venue.assessment_identity in (
        result.forecast.source_evidence_identities
    )
    assert cross_venue.score_authority is False
    assert cross_venue.directional_authority is False


def test_future_cross_venue_assessment_is_rejected(tmp_path) -> None:
    signal = _signal()
    family = _family_evidence()
    event = _event_context()
    cross_venue = _cross_venue(
        binance_close="101",
        bybit_close="100",
        as_of_ms=AS_OF + 1,
    )

    with pytest.raises(ValueError, match="future evidence"):
        issue_unified_decision(
            signal=signal,
            base_asset="BTC",
            regime="trend_up",
            family_evidence=family,
            event_context=event,
            preflight_proof_slices=_preflight(family, event),
            issued_at_ms=ISSUED_AT,
            horizon_bars=HORIZON,
            target_label="target_1",
            ledger=ImmutableDecisionEvidenceLedger(
                tmp_path / "decision.sqlite3"
            ),
            cross_venue_quality=cross_venue,
        )
