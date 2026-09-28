from __future__ import annotations

import pytest

from crypto_signal.data.source_contract import (
    SourceContractStore,
    SourceCoverageState,
    SourceFreshnessState,
    SourceSequenceSemantics,
    SourceTransport,
    assess_source_freshness,
    build_source_capability,
    build_source_coverage_event,
    build_source_envelope,
)


def _capability():
    return build_source_capability(
        provider="bybit",
        source="market_tape_stream",
        channel="publicTrade",
        transport=SourceTransport.WEBSOCKET,
        sequence_semantics=SourceSequenceSemantics.MONOTONIC,
        supports_provider_event_id=True,
        freshness_budget_ms=60_000,
        symbols=("SOLUSDT", "BTCUSDT", "ETHUSDT"),
    )


def _envelope(
    *,
    capability=None,
    symbol: str = "BTCUSDT",
    provider_event_id: str = "trade-1",
    provider_sequence: int = 100,
    event_at_ms: int = 10_000,
    source_timestamp_ms: int = 10_010,
    observed_at_ms: int = 10_020,
    ingested_at_ms: int = 10_030,
    raw_identity: str = "a" * 64,
    normalized_identity: str | None = "b" * 64,
):
    source_capability = _capability() if capability is None else capability
    return build_source_envelope(
        capability=source_capability,
        symbol=symbol,
        provider_event_id=provider_event_id,
        provider_sequence=provider_sequence,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        raw_identity=raw_identity,
        normalized_identity=normalized_identity,
    )


def test_source_capability_and_envelope_are_canonical() -> None:
    capability = _capability()
    replay = _capability()

    assert capability == replay
    assert capability.symbols == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    assert capability.production_authority is False
    assert capability.real_capital == 0

    envelope = _envelope(capability=capability)
    replay_envelope = _envelope(capability=capability)

    assert envelope == replay_envelope
    assert envelope.capability_identity == capability.capability_identity
    assert envelope.raw_identity == "a" * 64
    assert envelope.normalized_identity == "b" * 64
    assert envelope.production_authority is False
    assert envelope.real_capital == 0


def test_source_envelope_fails_closed_outside_capability() -> None:
    capability = _capability()

    with pytest.raises(ValueError, match="outside capability"):
        _envelope(capability=capability, symbol="XRPUSDT")

    with pytest.raises(ValueError, match="requires provider event id"):
        build_source_envelope(
            capability=capability,
            symbol="BTCUSDT",
            provider_event_id=None,
            provider_sequence=100,
            event_at_ms=10_000,
            source_timestamp_ms=10_010,
            observed_at_ms=10_020,
            ingested_at_ms=10_030,
            raw_identity="a" * 64,
            normalized_identity="b" * 64,
        )

    with pytest.raises(ValueError, match="requires provider sequence"):
        build_source_envelope(
            capability=capability,
            symbol="BTCUSDT",
            provider_event_id="trade-1",
            provider_sequence=None,
            event_at_ms=10_000,
            source_timestamp_ms=10_010,
            observed_at_ms=10_020,
            ingested_at_ms=10_030,
            raw_identity="a" * 64,
            normalized_identity="b" * 64,
        )


def test_source_freshness_is_explicit_and_point_in_time_safe() -> None:
    capability = _capability()
    envelope = _envelope(capability=capability)

    not_ingested = assess_source_freshness(
        capability=capability,
        envelope=envelope,
        as_of_ms=10_025,
    )
    assert not_ingested.state is SourceFreshnessState.UNAVAILABLE
    assert not_ingested.reason_codes == ("not_ingested_as_of",)
    assert not_ingested.source_envelope_identity is None

    fresh = assess_source_freshness(
        capability=capability,
        envelope=envelope,
        as_of_ms=60_000,
    )
    assert fresh.state is SourceFreshnessState.FRESH
    assert fresh.source_age_ms == 49_990
    assert fresh.reason_codes == ("inside_freshness_budget",)

    stale = assess_source_freshness(
        capability=capability,
        envelope=envelope,
        as_of_ms=80_011,
    )
    assert stale.state is SourceFreshnessState.STALE
    assert stale.source_age_ms == 70_001
    assert stale.reason_codes == ("source_age_exceeded_budget",)

    gap = assess_source_freshness(
        capability=capability,
        envelope=envelope,
        as_of_ms=80_011,
        gap_open=True,
    )
    assert gap.state is SourceFreshnessState.GAP
    assert gap.reason_codes == ("open_gap",)

    unavailable = assess_source_freshness(
        capability=capability,
        envelope=None,
        as_of_ms=80_011,
    )
    assert unavailable.state is SourceFreshnessState.UNAVAILABLE
    assert unavailable.reason_codes == ("no_source_envelope_as_of",)


def test_source_contract_store_preserves_as_of_truth(tmp_path) -> None:
    store = SourceContractStore(tmp_path / "source_contract.sqlite3")
    capability = _capability()
    first = _envelope(
        capability=capability,
        provider_event_id="trade-1",
        provider_sequence=100,
        event_at_ms=1_000,
        source_timestamp_ms=1_010,
        observed_at_ms=1_020,
        ingested_at_ms=1_030,
        raw_identity="a" * 64,
        normalized_identity="b" * 64,
    )
    second = _envelope(
        capability=capability,
        provider_event_id="trade-2",
        provider_sequence=101,
        event_at_ms=3_000,
        source_timestamp_ms=3_010,
        observed_at_ms=3_020,
        ingested_at_ms=3_030,
        raw_identity="c" * 64,
        normalized_identity="d" * 64,
    )

    store.append_capability(capability)
    store.append_capability(capability)
    store.append_envelope(first)
    store.append_envelope(first)
    store.append_envelope(second)

    assert store.capability(capability.capability_identity) == capability
    assert (
        store.latest_envelope_at(
            provider="bybit",
            source="market_tape_stream",
            channel="publicTrade",
            symbol="BTCUSDT",
            as_of_ms=1_029,
        )
        is None
    )
    assert store.latest_envelope_at(
        provider="bybit",
        source="market_tape_stream",
        channel="publicTrade",
        symbol="BTCUSDT",
        as_of_ms=2_000,
    ) == first
    assert store.latest_envelope_at(
        provider="bybit",
        source="market_tape_stream",
        channel="publicTrade",
        symbol="BTCUSDT",
        as_of_ms=4_000,
    ) == second
    assert store.quick_check() is True


def test_source_coverage_chain_explains_observed_gap_and_unavailable(
    tmp_path,
) -> None:
    store = SourceContractStore(tmp_path / "source_contract.sqlite3")
    capability = _capability()
    envelope = _envelope(
        capability=capability,
        event_at_ms=1_000,
        source_timestamp_ms=1_010,
        observed_at_ms=1_020,
        ingested_at_ms=1_030,
    )
    store.append_capability(capability)
    store.append_envelope(envelope)

    observed = build_source_coverage_event(
        capability=capability,
        symbol="BTCUSDT",
        state=SourceCoverageState.OBSERVED,
        observed_at_ms=1_100,
        source_envelope_identity=envelope.envelope_identity,
        reason_codes=("source_evidence_observed",),
    )
    gap = build_source_coverage_event(
        capability=capability,
        symbol="BTCUSDT",
        state=SourceCoverageState.GAP,
        observed_at_ms=2_000,
        previous=observed,
        gap_event_identity="c" * 64,
        reason_codes=("ingestion_gap_open",),
    )
    unavailable = build_source_coverage_event(
        capability=capability,
        symbol="BTCUSDT",
        state=SourceCoverageState.UNAVAILABLE,
        observed_at_ms=3_000,
        previous=gap,
        reason_codes=("provider_unavailable",),
    )

    store.append_coverage(observed)
    store.append_coverage(observed)
    store.append_coverage(gap)
    store.append_coverage(unavailable)

    assert (
        store.coverage_at(
            provider="bybit",
            source="market_tape_stream",
            channel="publicTrade",
            symbol="BTCUSDT",
            as_of_ms=1_099,
        )
        is None
    )
    assert store.coverage_at(
        provider="bybit",
        source="market_tape_stream",
        channel="publicTrade",
        symbol="BTCUSDT",
        as_of_ms=1_500,
    ) == observed
    assert (
        store.coverage_at(
            provider="bybit",
            source="market_tape_stream",
            channel="publicTrade",
            symbol="BTCUSDT",
            as_of_ms=2_500,
        ).state
        is SourceCoverageState.GAP
    )
    assert (
        store.coverage_at(
            provider="bybit",
            source="market_tape_stream",
            channel="publicTrade",
            symbol="BTCUSDT",
            as_of_ms=3_500,
        ).state
        is SourceCoverageState.UNAVAILABLE
    )


def test_source_coverage_rejects_future_envelope_and_wrong_chain(tmp_path) -> None:
    store = SourceContractStore(tmp_path / "source_contract.sqlite3")
    capability = _capability()
    envelope = _envelope(
        capability=capability,
        event_at_ms=2_000,
        source_timestamp_ms=2_010,
        observed_at_ms=2_020,
        ingested_at_ms=2_030,
    )
    store.append_capability(capability)
    store.append_envelope(envelope)

    future_claim = build_source_coverage_event(
        capability=capability,
        symbol="BTCUSDT",
        state=SourceCoverageState.OBSERVED,
        observed_at_ms=2_025,
        source_envelope_identity=envelope.envelope_identity,
        reason_codes=("source_evidence_observed",),
    )
    with pytest.raises(ValueError, match="future ingestion"):
        store.append_coverage(future_claim)

    root = build_source_coverage_event(
        capability=capability,
        symbol="BTCUSDT",
        state=SourceCoverageState.OBSERVED,
        observed_at_ms=2_100,
        source_envelope_identity=envelope.envelope_identity,
        reason_codes=("source_evidence_observed",),
    )
    store.append_coverage(root)

    stale_root = build_source_coverage_event(
        capability=capability,
        symbol="BTCUSDT",
        state=SourceCoverageState.UNAVAILABLE,
        observed_at_ms=2_200,
        reason_codes=("manual_stale_root",),
    )
    with pytest.raises(ValueError, match="predecessor mismatch"):
        store.append_coverage(stale_root)
