from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.data.options import (
    OptionContractQuote,
    OptionInstrumentSpec,
    OptionType,
    build_option_contract_quote,
    build_option_instrument_metadata_identity,
    build_option_instrument_spec,
    build_option_surface_observation,
)
from crypto_signal.data.options_surface_store import OptionsSurfaceStore
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.product.frozen_proof_store import FrozenProofStore
from crypto_signal.product.intelligence_stream_family_sources import (
    build_market_tape_family_snapshots,
)

AS_OF_MS = 2_000_000
BTC_SYMBOL = "BTCUSDT"
SOL_SYMBOL = "SOLUSDT"
ADAPTER = "rdp6-d-family-test/1"


def _seed_derivatives(path: Path, *, symbol: str) -> None:
    store = MarketTapeStore(path)
    for event_at_ms, funding, oi, mark in (
        (AS_OF_MS - 180_000, "0.00010", "100", "100"),
        (AS_OF_MS - 120_000, "0.00011", "101", "101"),
        (AS_OF_MS - 60_000, "0.00009", "102", "102"),
        (AS_OF_MS - 1_000, "0.00010", "103", "103"),
    ):
        store.append_derivatives(
            build_derivatives_observation(
                exchange=Exchange.BYBIT,
                instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
                symbol=symbol,
                event_at_ms=event_at_ms,
                funding_rate=Decimal(funding),
                open_interest=Decimal(oi),
                mark_price=Decimal(mark),
                index_price=Decimal(100),
                funding_interval_hours=8,
                source=DataSource.REST,
                source_timestamp_ms=event_at_ms + 1,
                ingested_at_ms=event_at_ms + 2,
                adapter_version=ADAPTER,
            )
        )


def _instrument(
    *,
    expiry_at_ms: int,
    strike: int,
    option_type: OptionType,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
) -> OptionInstrumentSpec:
    side = "C" if option_type is OptionType.CALL else "P"
    return build_option_instrument_spec(
        exchange=Exchange.BYBIT,
        symbol=f"BTC-{expiry_at_ms}-{strike}-{side}-USDT",
        base_coin="BTC",
        quote_coin="USDT",
        settle_coin="USDT",
        option_type=option_type,
        strike=Decimal(strike),
        expiry_at_ms=expiry_at_ms,
        status="Trading",
        source=DataSource.REST,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=ADAPTER,
    )


def _quote(
    instrument: OptionInstrumentSpec,
    *,
    delta: str,
    mark_iv: str,
    open_interest: int,
    volume_24h: int,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
) -> OptionContractQuote:
    return build_option_contract_quote(
        instrument=instrument,
        mark_iv=Decimal(mark_iv),
        bid_iv=None,
        ask_iv=None,
        mark_price=Decimal(100),
        index_price=Decimal(70_000),
        underlying_price=Decimal(70_050),
        delta=Decimal(delta),
        gamma=Decimal("0.0001"),
        vega=Decimal("12.5"),
        theta=Decimal("-2.5"),
        open_interest=Decimal(open_interest),
        volume_24h=Decimal(volume_24h),
        turnover_24h=None,
        source=DataSource.REST,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=ADAPTER,
    )


def _seed_options(
    path: Path,
    *,
    source_timestamp_ms: int = AS_OF_MS - 100,
    observed_at_ms: int = AS_OF_MS - 80,
    ingested_at_ms: int = AS_OF_MS - 60,
) -> None:
    expiries = (AS_OF_MS + 7_000_000, AS_OF_MS + 14_000_000)
    specs: list[OptionInstrumentSpec] = []
    quotes: list[OptionContractQuote] = []
    for expiry_index, expiry_at_ms in enumerate(expiries):
        for strike, side, delta, iv, oi, volume in (
            (70_000, OptionType.CALL, "0.50", "0.50", 100, 10),
            (70_000, OptionType.PUT, "-0.50", "0.52", 100, 10),
            (75_000, OptionType.CALL, "0.25", "0.48", 100, 10),
            (65_000, OptionType.PUT, "-0.25", "0.56", 100, 10),
        ):
            instrument = _instrument(
                expiry_at_ms=expiry_at_ms,
                strike=strike + expiry_index,
                option_type=side,
                source_timestamp_ms=source_timestamp_ms - 10,
                observed_at_ms=observed_at_ms - 10,
                ingested_at_ms=ingested_at_ms - 10,
            )
            specs.append(instrument)
            quotes.append(
                _quote(
                    instrument,
                    delta=delta,
                    mark_iv=str(Decimal(iv) + Decimal(expiry_index) / Decimal(20)),
                    open_interest=oi,
                    volume_24h=volume,
                    source_timestamp_ms=source_timestamp_ms,
                    observed_at_ms=observed_at_ms,
                    ingested_at_ms=ingested_at_ms,
                )
            )

    instrument_specs = tuple(specs)
    metadata_identity = build_option_instrument_metadata_identity(
        exchange=Exchange.BYBIT,
        base_coin="BTC",
        instrument_specs=instrument_specs,
    )
    surface = build_option_surface_observation(
        exchange=Exchange.BYBIT,
        base_coin="BTC",
        instrument_metadata_identity=metadata_identity,
        contracts=tuple(quotes),
        source=DataSource.REST,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=ADAPTER,
    )
    OptionsSurfaceStore(path).append_snapshot(
        instrument_specs=instrument_specs,
        surface=surface,
    )


def _derivatives_snapshot(
    market_path: Path,
    *,
    symbol: str,
    options_path: Path | None = None,
    proof_path: Path | None = None,
):
    snapshots = build_market_tape_family_snapshots(
        market_path,
        symbols=(symbol,),
        as_of_ms=AS_OF_MS,
        options_surface_path=options_path,
        frozen_proof_store_path=proof_path,
    )
    return next(
        item
        for item in snapshots
        if item.family is ConfluenceFamily.DERIVATIVES
    )


def _components(snapshot) -> dict[str, str]:
    return {
        item.name: item.value
        for item in snapshot.state_components
    }


def test_options_not_configured_preserves_rdp5_snapshot_exactly(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market.sqlite3"
    _seed_derivatives(market_path, symbol=BTC_SYMBOL)

    omitted = build_market_tape_family_snapshots(
        market_path,
        symbols=(BTC_SYMBOL,),
        as_of_ms=AS_OF_MS,
    )
    explicit_none = build_market_tape_family_snapshots(
        market_path,
        symbols=(BTC_SYMBOL,),
        as_of_ms=AS_OF_MS,
        options_surface_path=None,
    )

    assert omitted == explicit_none
    snapshot = next(
        item
        for item in omitted
        if item.family is ConfluenceFamily.DERIVATIVES
    )
    assert "options_status" not in _components(snapshot)
    assert "options_surface" not in snapshot.evidence_domains
    assert "options_volatility" not in snapshot.evidence_domains


def test_configured_missing_options_surface_is_explicitly_unavailable(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market.sqlite3"
    options_path = tmp_path / "missing-options.sqlite3"
    _seed_derivatives(market_path, symbol=BTC_SYMBOL)

    baseline = _derivatives_snapshot(market_path, symbol=BTC_SYMBOL)
    proof_path = tmp_path / "frozen_proofs.sqlite3"
    snapshot = _derivatives_snapshot(
        market_path,
        symbol=BTC_SYMBOL,
        options_path=options_path,
        proof_path=proof_path,
    )
    components = _components(snapshot)

    assert components["options_status"] == "unavailable"
    assert components["options_volatility_index_status"] == "unavailable"
    assert "options_surface_unavailable" in snapshot.uncertainty_flags
    assert "options_surface" not in snapshot.evidence_domains
    assert "options_volatility" not in snapshot.evidence_domains
    assert snapshot.source_event_identity != baseline.source_event_identity
    assert snapshot.direction is None


def test_fresh_btc_options_enrich_existing_derivatives_family(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market.sqlite3"
    options_path = tmp_path / "options.sqlite3"
    _seed_derivatives(market_path, symbol=BTC_SYMBOL)
    _seed_options(options_path)

    proof_path = tmp_path / "frozen_proofs.sqlite3"
    snapshot = _derivatives_snapshot(
        market_path,
        symbol=BTC_SYMBOL,
        options_path=options_path,
        proof_path=proof_path,
    )
    components = _components(snapshot)

    assert snapshot.family is ConfluenceFamily.DERIVATIVES
    assert snapshot.direction is None
    assert components["options_status"] == "measured"
    assert components["options_contract_count"] == "8"
    assert components["options_measured_atm_expiry_count"] == "2"
    assert components["options_measured_rr_expiry_count"] == "2"
    assert components["options_term_structure_shape"] == "higher_later_iv"
    assert components["options_volatility_index_status"] == "unavailable"
    assert components["options_front_atm_iv"] == "0.51"
    assert components["options_next_atm_iv"] == "0.56"
    assert components["options_term_structure_iv_change"] == "0.05"
    assert components["options_put_call_open_interest_ratio"] == "1"
    assert components["options_put_call_volume_ratio"] == "1"
    assert "options_surface" in snapshot.evidence_domains
    assert "options_volatility" in snapshot.evidence_domains
    assert "options_metrics_are_descriptive_not_directional" in (
        snapshot.uncertainty_flags
    )
    assert "dealer_gamma_position_not_inferred" in snapshot.uncertainty_flags
    assert "max_pain_not_estimated" in snapshot.uncertainty_flags

    surface_identity = next(
        identity
        for identity in snapshot.evidence_identities
        if (
            FrozenProofStore(proof_path).read_exact(identity) is not None
            and FrozenProofStore(proof_path).read_exact(identity).object_kind
            == "options_surface_snapshot"
        )
    )
    proof_store = FrozenProofStore(proof_path)
    surface_proof = proof_store.read_exact(surface_identity)
    assert surface_proof is not None
    volatility_proof = next(
        proof_store.read_exact(identity)
        for identity in snapshot.evidence_identities
        if (
            proof_store.read_exact(identity) is not None
            and proof_store.read_exact(identity).object_kind
            == "options_volatility_freeze"
        )
    )
    assert volatility_proof is not None
    assert surface_proof.object_kind == "options_surface_snapshot"
    assert volatility_proof.object_kind == "options_volatility_freeze"
    assert surface_proof.market_available_at_ms == surface_proof.as_of_ms
    assert surface_proof.source_object_identities
    assert surface_identity in volatility_proof.depends_on_evidence_identities
    assert volatility_proof.analysis_identity is not None
    assert volatility_proof.production_authority is False
    assert volatility_proof.real_capital == 0


def test_stale_options_surface_fails_closed_inside_derivatives_family(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market.sqlite3"
    options_path = tmp_path / "options.sqlite3"
    _seed_derivatives(market_path, symbol=BTC_SYMBOL)
    _seed_options(
        options_path,
        source_timestamp_ms=AS_OF_MS - 120_001,
        observed_at_ms=AS_OF_MS - 120_000,
        ingested_at_ms=AS_OF_MS - 119_999,
    )

    snapshot = _derivatives_snapshot(
        market_path,
        symbol=BTC_SYMBOL,
        options_path=options_path,
    )
    components = _components(snapshot)

    assert components["options_status"] == "stale"
    assert "options_front_atm_iv" not in components
    assert "options_term_structure_iv_change" not in components
    assert "stale_options_surface" in snapshot.uncertainty_flags
    assert "options_surface" in snapshot.evidence_domains
    assert "options_volatility" in snapshot.evidence_domains
    assert snapshot.direction is None


def test_non_btc_eth_symbol_preserves_rdp5_behavior_with_options_store(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market.sqlite3"
    options_path = tmp_path / "options.sqlite3"
    _seed_derivatives(market_path, symbol=SOL_SYMBOL)
    OptionsSurfaceStore(options_path).initialize()

    baseline = _derivatives_snapshot(market_path, symbol=SOL_SYMBOL)
    snapshot = _derivatives_snapshot(
        market_path,
        symbol=SOL_SYMBOL,
        options_path=options_path,
    )

    assert snapshot == baseline
    assert "options_status" not in _components(snapshot)
    assert snapshot.direction is None
