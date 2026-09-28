from __future__ import annotations

from decimal import Decimal

from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.data.provider_divergence import (
    build_provider_divergence_snapshot,
)
from crypto_signal.intelligence.cross_venue_quality import (
    CrossVenueQualityConfig,
    CrossVenueQualityState,
    CrossVenueScope,
    assess_cross_venue_quality,
)


def _candle(
    exchange: Exchange,
    open_time_ms: int,
    close: str,
) -> Candle:
    value = Decimal(close)
    close_time_ms = open_time_ms + 899_999
    return Candle(
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=value,
        high=value + Decimal(1),
        low=value - Decimal(1),
        close=value,
        volume=Decimal(2),
        quote_volume=Decimal(200),
        trade_count=10 if exchange is Exchange.BINANCE else None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=close_time_ms + 10,
        ingested_at_ms=close_time_ms + 20,
        adapter_version=f"{exchange.value}-rdp9-test/1",
    )


def _snapshot(
    *,
    binance_closes: tuple[str, ...],
    bybit_closes: tuple[str, ...],
    observed_at_ms: int = 2_800_000,
):
    opens = (0, 900_000, 1_800_000)
    binance = tuple(
        _candle(Exchange.BINANCE, open_ms, close)
        for open_ms, close in zip(opens, binance_closes, strict=True)
    )
    bybit = tuple(
        _candle(Exchange.BYBIT, open_ms, close)
        for open_ms, close in zip(opens, bybit_closes, strict=True)
    )
    return build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=observed_at_ms,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=binance,
        right_candles=bybit,
        lookback_limit=96,
    )


def test_cross_venue_quality_marks_two_fresh_venues_as_broad() -> None:
    snapshot = _snapshot(
        binance_closes=("100.10", "101.05", "102.20"),
        bybit_closes=("100.00", "101.00", "102.00"),
    )

    assessment = assess_cross_venue_quality(snapshot)

    assert assessment.scope is CrossVenueScope.BROAD_TWO_VENUE
    assert assessment.state is CrossVenueQualityState.TWO_VENUE_CONFIRMED
    assert assessment.latest_absolute_spread_bps is not None
    assert assessment.latest_absolute_spread_bps < Decimal(40)
    assert assessment.material_conflict_identities == ()
    assert assessment.source_evidence_identities == tuple(
        sorted(
            set(snapshot.left_source_evidence_identities)
            | set(snapshot.right_source_evidence_identities)
        )
    )
    assert assessment.directional_authority is False
    assert assessment.score_authority is False
    assert assessment.production_authority is False
    assert assessment.real_capital == 0


def test_cross_venue_quality_exposes_material_price_disagreement() -> None:
    snapshot = _snapshot(
        binance_closes=("101.00", "102.00", "103.00"),
        bybit_closes=("100.00", "100.00", "100.00"),
    )
    config = CrossVenueQualityConfig(material_spread_bps=Decimal(40))

    assessment = assess_cross_venue_quality(snapshot, config=config)

    assert assessment.scope is CrossVenueScope.VENUE_LOCAL
    assert (
        assessment.state
        is CrossVenueQualityState.MATERIAL_PRICE_DISAGREEMENT
    )
    assert assessment.latest_absolute_spread_bps is not None
    assert assessment.latest_absolute_spread_bps > Decimal(40)
    assert len(assessment.material_conflict_identities) == 1
    assert (
        "material_cross_venue_price_disagreement"
        in assessment.uncertainty_flags
    )

    replay = assess_cross_venue_quality(snapshot, config=config)
    assert replay == assessment


def test_cross_venue_quality_single_provider_never_becomes_broad() -> None:
    binance = (_candle(Exchange.BINANCE, 0, "100"),)
    snapshot = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=1_000_000,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=binance,
        right_candles=(),
    )

    assessment = assess_cross_venue_quality(snapshot)

    assert assessment.scope is CrossVenueScope.VENUE_LOCAL
    assert assessment.state is CrossVenueQualityState.SINGLE_VENUE_ONLY
    assert assessment.material_conflict_identities == ()
    assert assessment.uncertainty_flags == ("single_provider_only",)


def test_cross_venue_quality_both_missing_is_explicit_unavailable() -> None:
    snapshot = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=1_000_000,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=(),
        right_candles=(),
    )

    assessment = assess_cross_venue_quality(snapshot)

    assert assessment.scope is CrossVenueScope.UNAVAILABLE
    assert assessment.state is CrossVenueQualityState.PROVIDERS_UNAVAILABLE
    assert assessment.source_evidence_identities == ()
    assert assessment.uncertainty_flags == ("both_providers_unavailable",)


def test_cross_venue_materiality_threshold_is_explicit_policy_input() -> None:
    snapshot = _snapshot(
        binance_closes=("100.30", "100.30", "100.30"),
        bybit_closes=("100.00", "100.00", "100.00"),
    )

    narrow = assess_cross_venue_quality(
        snapshot,
        config=CrossVenueQualityConfig(
            material_spread_bps=Decimal(20),
        ),
    )
    wide = assess_cross_venue_quality(
        snapshot,
        config=CrossVenueQualityConfig(
            material_spread_bps=Decimal(40),
        ),
    )

    assert narrow.scope is CrossVenueScope.VENUE_LOCAL
    assert (
        narrow.state
        is CrossVenueQualityState.MATERIAL_PRICE_DISAGREEMENT
    )
    assert wide.scope is CrossVenueScope.BROAD_TWO_VENUE
    assert wide.state is CrossVenueQualityState.TWO_VENUE_CONFIRMED
    assert narrow.assessment_identity != wide.assessment_identity
