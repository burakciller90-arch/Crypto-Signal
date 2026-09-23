from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.event_risk import (
    EventCategory,
    EventSourceQuality,
    build_event_calendar_coverage,
    build_structured_event_observation,
)
from crypto_signal.data.market_quality_risk import (
    build_market_quality_risk_observation,
)
from crypto_signal.data.models import DataSource
from crypto_signal.data.news_events import build_news_event_observation
from crypto_signal.intelligence.event_risk import (
    DEFAULT_REQUIRED_EVENT_CATEGORIES,
    EventRiskState,
    build_event_risk_evidence_freeze,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerState,
    evaluate_circuit_breaker,
)
from crypto_signal.intelligence.news_event_risk import (
    NewsEvidenceState,
    build_news_evidence_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256

AS_OF = 1_000_000_000
MINUTE = 60_000


def _coverage():
    return build_event_calendar_coverage(
        coverage_start_ms=AS_OF - 60 * MINUTE,
        coverage_end_ms=AS_OF + 90 * MINUTE,
        categories=DEFAULT_REQUIRED_EVENT_CATEGORIES,
        source_provider="calendar-provider",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.AGGREGATED,
        observed_at_ms=AS_OF - 1_000,
        adapter_version="circuit-breaker-test/1",
    )


def _event_risk(delta_minutes: int | None):
    events = ()
    if delta_minutes is not None:
        event = build_structured_event_observation(
            provider_event_id=f"event-{delta_minutes}",
            title="Scheduled event",
            category=EventCategory.CENTRAL_BANK,
            scheduled_at_ms=AS_OF + delta_minutes * MINUTE,
            affected_assets=("BTC",),
            source_provider="calendar-provider",
            source_quality=EventSourceQuality.OFFICIAL,
            source=DataSource.AGGREGATED,
            source_timestamp_ms=AS_OF - 10_000,
            ingested_at_ms=AS_OF - 9_000,
            adapter_version="circuit-breaker-test/1",
        )
        events = (event,)
    return build_event_risk_evidence_freeze(
        events,
        coverage=_coverage(),
        asset="BTC",
        as_of_ms=AS_OF,
    ).analysis


def _news(
    *,
    multi: bool = True,
    disagreement: bool = False,
    low_confidence: bool = False,
):
    first = build_news_event_observation(
        provider_article_id="a1",
        event_cluster_key="cluster-1",
        headline="Provider A",
        category=EventCategory.REGULATORY,
        affected_assets=("BTC",),
        published_at_ms=AS_OF - 10 * MINUTE,
        source_provider="provider-a",
        source_quality=EventSourceQuality.PRIMARY_PROVIDER,
        source=DataSource.AGGREGATED,
        source_timestamp_ms=AS_OF - 10 * MINUTE + 1_000,
        ingested_at_ms=AS_OF - 10 * MINUTE + 2_000,
        extraction_method="provider-metadata-plus-nlp",
        extraction_version="circuit-breaker-test/1",
        relevance_confidence_0_1=(
            Decimal("0.40") if low_confidence else Decimal("0.90")
        ),
        adapter_version="circuit-breaker-test/1",
    )
    rows = [first]
    if multi:
        rows.append(
            build_news_event_observation(
                provider_article_id="b1",
                event_cluster_key="cluster-1",
                headline="Provider B",
                category=(
                    EventCategory.EXCHANGE_SECURITY
                    if disagreement
                    else EventCategory.REGULATORY
                ),
                affected_assets=("BTC",),
                published_at_ms=AS_OF - 9 * MINUTE,
                source_provider="provider-b",
                source_quality=EventSourceQuality.PRIMARY_PROVIDER,
                source=DataSource.AGGREGATED,
                source_timestamp_ms=AS_OF - 9 * MINUTE + 1_000,
                ingested_at_ms=AS_OF - 9 * MINUTE + 2_000,
                extraction_method="provider-metadata-plus-nlp",
                extraction_version="circuit-breaker-test/1",
                relevance_confidence_0_1=Decimal("0.90"),
                adapter_version="circuit-breaker-test/1",
            )
        )
    return build_news_evidence_freeze(
        tuple(rows),
        asset="BTC",
        as_of_ms=AS_OF,
    ).analysis


def _market_quality(
    *,
    spread: str | None = "5",
    depth_loss: str | None = "0.10",
    delay_ms: int | None = 1_000,
    price_gap: str | None = "0.01",
    disagreement_bps: str | None = "10",
    observed_at_ms: int = AS_OF - 1_000,
):
    def dec(value: str | None) -> Decimal | None:
        return None if value is None else Decimal(value)

    return build_market_quality_risk_observation(
        asset="BTC",
        observed_at_ms=observed_at_ms,
        spread_bps=dec(spread),
        depth_loss_fraction=dec(depth_loss),
        feed_delay_ms=delay_ms,
        price_gap_fraction=dec(price_gap),
        provider_disagreement_bps=dec(disagreement_bps),
        source_evidence_identities=(
            canonical_sha256({"quality": "test-source"}),
        ),
        measurement_version="market-quality-test/1",
    )


def _config() -> CircuitBreakerConfig:
    return CircuitBreakerConfig(
        policy_version="event-risk-circuit-policy-test/1",
        max_market_quality_age_ms=2 * MINUTE,
        max_spread_bps=Decimal(20),
        max_depth_loss_fraction=Decimal("0.40"),
        max_feed_delay_ms=5_000,
        max_price_gap_fraction=Decimal("0.05"),
        max_provider_disagreement_bps=Decimal(40),
    )


def test_clear_requires_clear_calendar_multi_source_news_and_good_market_quality() -> None:
    result = evaluate_circuit_breaker(
        _event_risk(None),
        _news(multi=True),
        _market_quality(),
        config=_config(),
    )

    assert result.state is CircuitBreakerState.CLEAR
    assert result.triggers == ()
    assert result.real_capital == 0
    assert len(result.evidence_identity) == 64


def test_calendar_caution_and_event_block_remain_distinct() -> None:
    caution = evaluate_circuit_breaker(
        _event_risk(30),
        _news(multi=True),
        _market_quality(),
        config=_config(),
    )
    block = evaluate_circuit_breaker(
        _event_risk(5),
        _news(multi=True),
        _market_quality(),
        config=_config(),
    )

    assert caution.state is CircuitBreakerState.CAUTION
    assert "structured_event_pre_caution" in caution.triggers
    assert block.state is CircuitBreakerState.EVENT_BLOCK
    assert "structured_event_block" in block.triggers


def test_single_source_news_is_caution_not_confirmation() -> None:
    news = _news(multi=False)
    assert news.state is NewsEvidenceState.SINGLE_SOURCE_CONTEXT

    result = evaluate_circuit_breaker(
        _event_risk(None),
        news,
        _market_quality(),
        config=_config(),
    )

    assert result.state is CircuitBreakerState.CAUTION
    assert "news_single_source_context" in result.triggers


def test_news_provider_disagreement_forces_abstain() -> None:
    news = _news(multi=True, disagreement=True)
    assert news.state is NewsEvidenceState.PROVIDER_DISAGREEMENT

    result = evaluate_circuit_breaker(
        _event_risk(None),
        news,
        _market_quality(),
        config=_config(),
    )

    assert result.state is CircuitBreakerState.ABSTAIN
    assert "news_provider_disagreement" in result.triggers


@pytest.mark.parametrize(
    ("kwargs", "trigger"),
    [
        ({"spread": "21"}, "abnormal_spread"),
        ({"depth_loss": "0.41"}, "depth_loss"),
        ({"delay_ms": 5_001}, "feed_delay"),
        ({"price_gap": "0.051"}, "price_gap"),
        ({"disagreement_bps": "41"}, "market_provider_disagreement"),
    ],
)
def test_each_versioned_market_quality_breach_forces_abstain(
    kwargs: dict[str, object],
    trigger: str,
) -> None:
    result = evaluate_circuit_breaker(
        _event_risk(None),
        _news(multi=True),
        _market_quality(**kwargs),
        config=_config(),
    )

    assert result.state is CircuitBreakerState.ABSTAIN
    assert trigger in result.triggers


def test_abstain_precedes_event_block_when_market_quality_also_breaches() -> None:
    result = evaluate_circuit_breaker(
        _event_risk(5),
        _news(multi=True),
        _market_quality(spread="25"),
        config=_config(),
    )

    assert result.state is CircuitBreakerState.ABSTAIN
    assert "structured_event_block" in result.triggers
    assert "abnormal_spread" in result.triggers


def test_missing_incomplete_stale_or_degraded_inputs_fail_closed() -> None:
    missing = evaluate_circuit_breaker(
        _event_risk(None),
        _news(multi=True),
        None,
        config=_config(),
    )
    incomplete = evaluate_circuit_breaker(
        _event_risk(None),
        _news(multi=True),
        _market_quality(spread=None),
        config=_config(),
    )
    stale = evaluate_circuit_breaker(
        _event_risk(None),
        _news(multi=True),
        _market_quality(observed_at_ms=AS_OF - 3 * MINUTE),
        config=_config(),
    )
    degraded_news = evaluate_circuit_breaker(
        _event_risk(None),
        _news(multi=False, low_confidence=True),
        _market_quality(),
        config=_config(),
    )

    for result in (missing, incomplete, stale, degraded_news):
        assert result.state is CircuitBreakerState.DEGRADED_DATA

    assert "market_quality_unavailable" in missing.triggers
    assert "market_quality_incomplete" in incomplete.triggers
    assert "market_quality_stale" in stale.triggers
    assert "news_evidence_degraded_data" in degraded_news.triggers


def test_unresolved_news_fails_closed_in_safety_composition() -> None:
    unresolved_news = build_news_evidence_freeze(
        (),
        asset="BTC",
        as_of_ms=AS_OF,
    ).analysis
    assert unresolved_news.state is NewsEvidenceState.UNRESOLVED

    result = evaluate_circuit_breaker(
        _event_risk(None),
        unresolved_news,
        _market_quality(),
        config=_config(),
    )

    assert result.state is CircuitBreakerState.DEGRADED_DATA
    assert "news_evidence_unresolved" in result.triggers


def test_context_mismatch_future_quality_tampering_and_invalid_policy_fail_closed() -> None:
    event = _event_risk(None)
    news = _news(multi=True)
    quality = _market_quality()

    wrong_news = replace(news, asset="ETH")
    with pytest.raises(ValueError, match="source assets must match"):
        evaluate_circuit_breaker(
            event,
            wrong_news,
            quality,
            config=_config(),
        )

    future_quality = _market_quality(observed_at_ms=AS_OF + 1)
    with pytest.raises(ValueError, match="from the future"):
        evaluate_circuit_breaker(
            event,
            news,
            future_quality,
            config=_config(),
        )

    result = evaluate_circuit_breaker(
        event,
        news,
        quality,
        config=_config(),
    )
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(result, evidence_identity="f" * 64)

    with pytest.raises(ValueError, match="positive"):
        CircuitBreakerConfig(
            policy_version="bad",
            max_market_quality_age_ms=0,
            max_spread_bps=Decimal(20),
            max_depth_loss_fraction=Decimal("0.40"),
            max_feed_delay_ms=5_000,
            max_price_gap_fraction=Decimal("0.05"),
            max_provider_disagreement_bps=Decimal(40),
        )
