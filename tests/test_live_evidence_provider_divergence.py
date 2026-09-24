from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.data.provider_divergence import ProviderDivergenceStore
from crypto_signal.data.store import CandleStore
from crypto_signal.ledger.coverage import (
    LiveCoverageContext,
    LiveCoveragePlan,
    LiveCoverageSourceStrategy,
)
from ops.run_live_evidence_clock import (
    persist_provider_divergence_for_plan,
    provider_divergence_symbols,
)


def _seed(
    store: CandleStore,
    *,
    exchange: Exchange,
    symbol: str,
    close: str,
) -> None:
    value = Decimal(close)
    store.upsert(
        Candle(
            exchange=exchange,
            market_type=MarketType.SPOT,
            symbol=symbol,
            timeframe="15m",
            open_time_ms=0,
            close_time_ms=899_999,
            open=value,
            high=value + Decimal(1),
            low=value - Decimal(1),
            close=value,
            volume=Decimal(1),
            quote_volume=Decimal(100),
            trade_count=1 if exchange is Exchange.BINANCE else None,
            is_closed=True,
            source=DataSource.REST,
            source_timestamp_ms=900_009,
            ingested_at_ms=900_019,
            adapter_version=f"{exchange.value}-test/1",
        )
    )


def test_live_clock_divergence_scope_uses_only_shared_15m_provider_contexts() -> None:
    plan = LiveCoveragePlan.current_pilot()

    assert provider_divergence_symbols(plan) == (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
    )


def test_live_clock_persists_divergence_after_canonical_cache_update(
    tmp_path: Path,
) -> None:
    candle_db = tmp_path / "live_base_15m_cache.sqlite3"
    divergence_db = tmp_path / "provider_divergence.sqlite3"
    store = CandleStore(candle_db)
    _seed(
        store,
        exchange=Exchange.BINANCE,
        symbol="BTCUSDT",
        close="100",
    )
    _seed(
        store,
        exchange=Exchange.BYBIT,
        symbol="BTCUSDT",
        close="100.1",
    )
    before = candle_db.read_bytes()

    result = persist_provider_divergence_for_plan(
        plan=LiveCoveragePlan.current_pilot(),
        candle_cache_path=candle_db,
        provider_divergence_path=divergence_db,
        observed_at_ms=1_000_000,
    )

    assert result is not None
    assert tuple(snapshot.symbol for snapshot in result.snapshots) == (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
    )
    assert result.snapshots[0].overlap_count == 1
    assert result.snapshots[0].production_authority is False
    assert result.snapshots[0].real_capital == 0
    assert result.snapshots[1].overlap_count == 0
    assert result.snapshots[2].overlap_count == 0
    assert candle_db.read_bytes() == before

    persisted = ProviderDivergenceStore(divergence_db)
    assert persisted.count() == 3
    assert persisted.quick_check() is True


def test_live_clock_single_provider_plan_does_not_infer_peer_or_consensus(
    tmp_path: Path,
) -> None:
    plan = LiveCoveragePlan(
        version="single-provider-test/1",
        contexts=(
            LiveCoverageContext(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol="BTCUSDT",
                timeframe="15m",
                source_strategy=(
                    LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M
                ),
            ),
        ),
    )
    divergence_db = tmp_path / "provider_divergence.sqlite3"

    assert provider_divergence_symbols(plan) == ()
    assert (
        persist_provider_divergence_for_plan(
            plan=plan,
            candle_cache_path=tmp_path / "missing.sqlite3",
            provider_divergence_path=divergence_db,
            observed_at_ms=1_000_000,
        )
        is None
    )
    assert not divergence_db.exists()
