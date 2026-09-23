from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.confluence.models import PriceZone
from crypto_signal.forecast_stream import (
    ForecastResolution,
    ImmutableForecast,
)
from crypto_signal.ledger.serialization import canonical_sha256

DECISION_PROOF_ENGINE_VERSION = "r20.5-decision-proof-live-feed-v1-slice1/1"
DECISION_PROOF_SCHEMA_VERSION = "decision-proof-v1/1"
LIVE_FEED_SCHEMA_VERSION = "live-intelligence-feed-v1/1"
LIVE_FEED_SNAPSHOT_SCHEMA_VERSION = "live-intelligence-feed-snapshot-v1/1"
REAL_CAPITAL = 0


class ProofEvidenceDomain(StrEnum):
    FROZEN_CHART = "frozen_chart"
    CONSUMED_CANDLES = "consumed_candles"
    ORDER_BOOK = "order_book"
    LIQUIDITY_MAP = "liquidity_map"
    LIQUIDATION_MAP = "liquidation_map"
    ORDER_FLOW_CVD = "order_flow_cvd"
    DERIVATIVES = "derivatives"
    ONCHAIN = "onchain"
    EVENT_CONTEXT = "event_context"
    METHODOLOGY = "methodology"
    PROBABILITY_CALIBRATION = "probability_calibration"


class ProofEvidenceAvailability(StrEnum):
    AVAILABLE = "available"
    INSUFFICIENT = "insufficient"
    UNSUPPORTED = "unsupported"


class ProofEvidenceVerdict(StrEnum):
    SUPPORT = "support"
    CONTRADICT = "contradict"
    NEUTRAL = "neutral"
    INSUFFICIENT = "insufficient"


class LiveFeedEventKind(StrEnum):
    FORECAST_ISSUED = "forecast_issued"
    FORECAST_RESOLVED = "forecast_resolved"


@dataclass(frozen=True, slots=True)
class DecisionProofEvidenceSlice:
    slice_identity: str
    schema_version: str
    engine_version: str
    domain: ProofEvidenceDomain
    availability: ProofEvidenceAvailability
    verdict: ProofEvidenceVerdict
    evidence_identities: tuple[str, ...]
    market_available_at_ms: int | None
    observed_at_ms: int | None
    freshness_0_1: Decimal | None
    source_quality: str | None
    summary_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.slice_identity, "Decision Proof slice identity")
        if self.schema_version != DECISION_PROOF_SCHEMA_VERSION:
            raise ValueError("unsupported Decision Proof slice schema")
        if self.engine_version != DECISION_PROOF_ENGINE_VERSION:
            raise ValueError("unsupported Decision Proof slice engine")
        _require_identity_tuple(
            self.evidence_identities,
            "Decision Proof evidence identity",
        )
        _require_text_tuple(self.summary_codes, "Decision Proof summary code")
        if not self.summary_codes:
            raise ValueError("Decision Proof evidence slice requires summary code")

        if self.availability is ProofEvidenceAvailability.AVAILABLE:
            if not self.evidence_identities:
                raise ValueError("available Decision Proof slice requires evidence")
            if self.market_available_at_ms is None or self.observed_at_ms is None:
                raise ValueError("available Decision Proof slice requires timestamps")
            if min(self.market_available_at_ms, self.observed_at_ms) < 0:
                raise ValueError("Decision Proof evidence timestamps must be non-negative")
            if self.market_available_at_ms > self.observed_at_ms:
                raise ValueError(
                    "Decision Proof evidence cannot be observed before availability"
                )
            if self.freshness_0_1 is None:
                raise ValueError("available Decision Proof slice requires freshness")
            _require_unit_interval(
                self.freshness_0_1,
                "Decision Proof evidence freshness",
            )
            if self.source_quality is None or not self.source_quality.strip():
                raise ValueError("available Decision Proof slice requires source quality")
            if self.verdict is ProofEvidenceVerdict.INSUFFICIENT:
                raise ValueError(
                    "available Decision Proof slice cannot use INSUFFICIENT verdict"
                )
        else:
            if self.evidence_identities:
                raise ValueError(
                    "unavailable Decision Proof slice cannot carry evidence identities"
                )
            if self.market_available_at_ms is not None or self.observed_at_ms is not None:
                raise ValueError(
                    "unavailable Decision Proof slice cannot carry evidence timestamps"
                )
            if self.freshness_0_1 is not None or self.source_quality is not None:
                raise ValueError(
                    "unavailable Decision Proof slice cannot carry freshness/source quality"
                )
            if self.verdict is not ProofEvidenceVerdict.INSUFFICIENT:
                raise ValueError(
                    "unavailable Decision Proof slice must use INSUFFICIENT verdict"
                )

        if self.slice_identity != canonical_sha256(_slice_payload(self)):
            raise ValueError("Decision Proof slice identity mismatch")


@dataclass(frozen=True, slots=True)
class DecisionProofEvidenceSummary:
    support_count: int
    contradict_count: int
    neutral_count: int
    insufficient_count: int
    available_count: int
    total_domain_count: int

    def __post_init__(self) -> None:
        values = (
            self.support_count,
            self.contradict_count,
            self.neutral_count,
            self.insufficient_count,
            self.available_count,
            self.total_domain_count,
        )
        if min(values) < 0:
            raise ValueError("Decision Proof summary counts cannot be negative")
        if (
            self.support_count
            + self.contradict_count
            + self.neutral_count
            + self.insufficient_count
            != self.total_domain_count
        ):
            raise ValueError("Decision Proof verdict counts must equal domain count")
        if self.available_count > self.total_domain_count:
            raise ValueError("Decision Proof available count exceeds domain count")


@dataclass(frozen=True, slots=True)
class DecisionProofSnapshot:
    proof_identity: str
    schema_version: str
    engine_version: str
    forecast_identity: str
    signal_freeze_identity: str
    asset: str
    symbol: str
    timeframe: str
    issued_at_ms: int
    source_as_of_ms: int
    signal_state: str
    direction: str
    conditional_thesis: str
    trigger_zone: PriceZone
    target_zone: PriceZone
    invalidation_price: Decimal
    horizon_bars: int
    confluence_support_score_0_100: Decimal
    confluence_opposition_score_0_100: Decimal
    probability_status: str
    calibrated_probability_0_1: Decimal | None
    event_context_state: str
    authority: str
    freshness_0_1: Decimal | None
    uncertainty_flags: tuple[str, ...]
    forecast_source_evidence_identities: tuple[str, ...]
    evidence_slices: tuple[DecisionProofEvidenceSlice, ...]
    evidence_summary: DecisionProofEvidenceSummary
    private_reasoning_exposed: bool = False
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.proof_identity, "Decision Proof identity")
        _require_sha256(self.forecast_identity, "Decision Proof forecast identity")
        _require_sha256(
            self.signal_freeze_identity,
            "Decision Proof signal freeze identity",
        )
        if self.schema_version != DECISION_PROOF_SCHEMA_VERSION:
            raise ValueError("unsupported Decision Proof schema")
        if self.engine_version != DECISION_PROOF_ENGINE_VERSION:
            raise ValueError("unsupported Decision Proof engine")
        for value, label in (
            (self.asset, "Decision Proof asset"),
            (self.symbol, "Decision Proof symbol"),
            (self.timeframe, "Decision Proof timeframe"),
            (self.signal_state, "Decision Proof signal state"),
            (self.direction, "Decision Proof direction"),
            (self.conditional_thesis, "Decision Proof conditional thesis"),
            (self.probability_status, "Decision Proof probability status"),
            (self.event_context_state, "Decision Proof event state"),
            (self.authority, "Decision Proof authority"),
        ):
            _require_text(value, label)
        if min(self.issued_at_ms, self.source_as_of_ms) < 0:
            raise ValueError("Decision Proof timestamps must be non-negative")
        if self.issued_at_ms < self.source_as_of_ms:
            raise ValueError("Decision Proof issuance cannot predate source as-of")
        if self.horizon_bars <= 0:
            raise ValueError("Decision Proof horizon must be positive")
        if self.invalidation_price <= Decimal(0):
            raise ValueError("Decision Proof invalidation price must be positive")
        for value in (
            self.confluence_support_score_0_100,
            self.confluence_opposition_score_0_100,
        ):
            if value < Decimal(0) or value > Decimal(100):
                raise ValueError("Decision Proof confluence score outside [0,100]")
        if self.calibrated_probability_0_1 is not None:
            _require_unit_interval(
                self.calibrated_probability_0_1,
                "Decision Proof calibrated probability",
            )
        if self.freshness_0_1 is not None:
            _require_unit_interval(self.freshness_0_1, "Decision Proof freshness")
        _require_text_tuple(
            self.uncertainty_flags,
            "Decision Proof uncertainty flag",
        )
        _require_identity_tuple(
            self.forecast_source_evidence_identities,
            "Decision Proof forecast source evidence",
        )

        expected_domains = tuple(
            sorted(ProofEvidenceDomain, key=lambda item: item.value)
        )
        actual_domains = tuple(item.domain for item in self.evidence_slices)
        if actual_domains != expected_domains:
            raise ValueError(
                "Decision Proof requires exactly one canonical slice per domain"
            )
        slice_ids = tuple(item.slice_identity for item in self.evidence_slices)
        if len(set(slice_ids)) != len(slice_ids):
            raise ValueError("Decision Proof slice identities must be unique")
        for item in self.evidence_slices:
            if (
                item.availability is ProofEvidenceAvailability.AVAILABLE
                and item.observed_at_ms is not None
                and item.observed_at_ms > self.source_as_of_ms
            ):
                raise ValueError(
                    "Decision Proof cannot include evidence observed after source as-of"
                )

        evidence_union = {
            identity
            for item in self.evidence_slices
            for identity in item.evidence_identities
        }
        if not set(self.forecast_source_evidence_identities).issubset(evidence_union):
            raise ValueError(
                "Decision Proof does not cover all forecast source evidence identities"
            )

        event_slice = _slice_for(
            self.evidence_slices,
            ProofEvidenceDomain.EVENT_CONTEXT,
        )
        methodology_slice = _slice_for(
            self.evidence_slices,
            ProofEvidenceDomain.METHODOLOGY,
        )
        probability_slice = _slice_for(
            self.evidence_slices,
            ProofEvidenceDomain.PROBABILITY_CALIBRATION,
        )
        if self.forecast_source_evidence_identities:
            if not event_slice.evidence_identities:
                raise ValueError("Decision Proof event context evidence must be explicit")
            if not methodology_slice.evidence_identities:
                raise ValueError("Decision Proof methodology evidence must be explicit")

        calibrated = self.calibrated_probability_0_1 is not None
        if calibrated:
            if probability_slice.availability is not ProofEvidenceAvailability.AVAILABLE:
                raise ValueError(
                    "calibrated Decision Proof requires probability evidence slice"
                )
        elif probability_slice.availability is ProofEvidenceAvailability.AVAILABLE:
            raise ValueError(
                "uncalibrated Decision Proof cannot claim available probability evidence"
            )

        if self.private_reasoning_exposed:
            raise ValueError("Decision Proof must not expose private reasoning")
        if not self.read_only:
            raise ValueError("Decision Proof Slice1 must remain read-only")
        if self.production_authority:
            raise ValueError("Decision Proof has no production/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.proof_identity != canonical_sha256(_proof_payload(self)):
            raise ValueError("Decision Proof identity mismatch")


@dataclass(frozen=True, slots=True)
class LiveIntelligenceFeedEvent:
    event_identity: str
    schema_version: str
    engine_version: str
    kind: LiveFeedEventKind
    event_at_ms: int
    forecast_identity: str
    proof_identity: str
    resolution_identity: str | None
    state: str
    asset: str
    symbol: str
    timeframe: str
    conditional_thesis: str
    trigger_zone: PriceZone
    target_zone: PriceZone
    invalidation_price: Decimal
    evidence_summary: DecisionProofEvidenceSummary
    freshness_0_1: Decimal | None
    authority: str
    probability_status: str
    calibrated_probability_0_1: Decimal | None
    uncertainty_flags: tuple[str, ...]
    private_reasoning_exposed: bool = False
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.event_identity, "Live feed event identity"),
            (self.forecast_identity, "Live feed forecast identity"),
            (self.proof_identity, "Live feed proof identity"),
        ):
            _require_sha256(identity, label)
        if self.resolution_identity is not None:
            _require_sha256(
                self.resolution_identity,
                "Live feed resolution identity",
            )
        if self.schema_version != LIVE_FEED_SCHEMA_VERSION:
            raise ValueError("unsupported Live Intelligence Feed schema")
        if self.engine_version != DECISION_PROOF_ENGINE_VERSION:
            raise ValueError("unsupported Live Intelligence Feed engine")
        if self.event_at_ms < 0:
            raise ValueError("Live feed timestamp must be non-negative")
        for value, label in (
            (self.state, "Live feed state"),
            (self.asset, "Live feed asset"),
            (self.symbol, "Live feed symbol"),
            (self.timeframe, "Live feed timeframe"),
            (self.conditional_thesis, "Live feed thesis"),
            (self.authority, "Live feed authority"),
            (self.probability_status, "Live feed probability status"),
        ):
            _require_text(value, label)
        if self.invalidation_price <= Decimal(0):
            raise ValueError("Live feed invalidation must be positive")
        if self.freshness_0_1 is not None:
            _require_unit_interval(self.freshness_0_1, "Live feed freshness")
        if self.calibrated_probability_0_1 is not None:
            _require_unit_interval(
                self.calibrated_probability_0_1,
                "Live feed calibrated probability",
            )
        _require_text_tuple(self.uncertainty_flags, "Live feed uncertainty flag")
        if self.kind is LiveFeedEventKind.FORECAST_ISSUED:
            if self.resolution_identity is not None:
                raise ValueError("forecast issuance event cannot carry resolution identity")
        else:
            if self.resolution_identity is None:
                raise ValueError("forecast resolution event requires resolution identity")
        if self.private_reasoning_exposed:
            raise ValueError("Live feed must not expose private reasoning")
        if not self.read_only:
            raise ValueError("Live feed Slice1 must remain read-only")
        if self.production_authority:
            raise ValueError("Live feed has no production/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.event_identity != canonical_sha256(_feed_event_payload(self)):
            raise ValueError("Live feed event identity mismatch")


@dataclass(frozen=True, slots=True)
class LiveIntelligenceFeedSnapshot:
    snapshot_identity: str
    schema_version: str
    engine_version: str
    events: tuple[LiveIntelligenceFeedEvent, ...]
    append_only: bool = True
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "Live feed snapshot identity")
        if self.schema_version != LIVE_FEED_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported Live feed snapshot schema")
        if self.engine_version != DECISION_PROOF_ENGINE_VERSION:
            raise ValueError("unsupported Live feed snapshot engine")
        event_ids = tuple(item.event_identity for item in self.events)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("Live feed event identities must be unique")
        keys = tuple((item.event_at_ms, item.event_identity) for item in self.events)
        if keys != tuple(sorted(keys)):
            raise ValueError("Live feed events must be append-ordered")
        semantic_keys = tuple((item.forecast_identity, item.kind) for item in self.events)
        if len(set(semantic_keys)) != len(semantic_keys):
            raise ValueError(
                "Live feed permits at most one issuance and one resolution per forecast"
            )
        if not self.append_only or not self.read_only:
            raise ValueError("Live feed Slice1 must remain append-only/read-only")
        if self.production_authority:
            raise ValueError("Live feed has no production/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.snapshot_identity != canonical_sha256(_feed_snapshot_payload(self)):
            raise ValueError("Live feed snapshot identity mismatch")


def build_decision_proof_evidence_slice(
    *,
    domain: ProofEvidenceDomain,
    availability: ProofEvidenceAvailability,
    verdict: ProofEvidenceVerdict,
    evidence_identities: tuple[str, ...] = (),
    market_available_at_ms: int | None = None,
    observed_at_ms: int | None = None,
    freshness_0_1: Decimal | None = None,
    source_quality: str | None = None,
    summary_codes: tuple[str, ...],
) -> DecisionProofEvidenceSlice:
    identities = tuple(sorted(set(evidence_identities)))
    summaries = tuple(sorted(set(summary_codes)))
    payload = {
        "availability": availability,
        "domain": domain,
        "engine_version": DECISION_PROOF_ENGINE_VERSION,
        "evidence_identities": identities,
        "freshness_0_1": freshness_0_1,
        "market_available_at_ms": market_available_at_ms,
        "observed_at_ms": observed_at_ms,
        "schema_version": DECISION_PROOF_SCHEMA_VERSION,
        "source_quality": source_quality,
        "summary_codes": summaries,
        "verdict": verdict,
    }
    return DecisionProofEvidenceSlice(
        slice_identity=canonical_sha256(payload),
        schema_version=DECISION_PROOF_SCHEMA_VERSION,
        engine_version=DECISION_PROOF_ENGINE_VERSION,
        domain=domain,
        availability=availability,
        verdict=verdict,
        evidence_identities=identities,
        market_available_at_ms=market_available_at_ms,
        observed_at_ms=observed_at_ms,
        freshness_0_1=freshness_0_1,
        source_quality=source_quality,
        summary_codes=summaries,
    )


def build_decision_proof_snapshot(
    forecast: ImmutableForecast,
    evidence_slices: tuple[DecisionProofEvidenceSlice, ...],
) -> DecisionProofSnapshot:
    ordered = tuple(sorted(evidence_slices, key=lambda item: item.domain.value))
    expected_domains = tuple(sorted(ProofEvidenceDomain, key=lambda item: item.value))
    if tuple(item.domain for item in ordered) != expected_domains:
        raise ValueError("Decision Proof requires one evidence slice per domain")

    summary = _evidence_summary(ordered)
    thesis = _conditional_thesis(forecast)
    payload = {
        "asset": forecast.asset,
        "authority": forecast.authority.value,
        "calibrated_probability_0_1": forecast.calibrated_probability_0_1,
        "conditional_thesis": thesis,
        "confluence_opposition_score_0_100": (
            forecast.confluence_opposition_score_0_100
        ),
        "confluence_support_score_0_100": forecast.confluence_support_score_0_100,
        "direction": forecast.direction.value,
        "engine_version": DECISION_PROOF_ENGINE_VERSION,
        "event_context_state": forecast.event_context_state.value,
        "evidence_slices": ordered,
        "evidence_summary": summary,
        "forecast_identity": forecast.forecast_identity,
        "forecast_source_evidence_identities": forecast.source_evidence_identities,
        "freshness_0_1": forecast.freshness_0_1,
        "horizon_bars": forecast.horizon_bars,
        "invalidation_price": forecast.invalidation_price,
        "issued_at_ms": forecast.issued_at_ms,
        "private_reasoning_exposed": False,
        "probability_status": forecast.probability_status,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": DECISION_PROOF_SCHEMA_VERSION,
        "signal_freeze_identity": forecast.signal_freeze_identity,
        "signal_state": forecast.signal_state.value,
        "source_as_of_ms": forecast.source_as_of_ms,
        "symbol": forecast.symbol,
        "target_zone": forecast.target_zone,
        "timeframe": forecast.timeframe,
        "trigger_zone": forecast.trigger_zone,
        "uncertainty_flags": forecast.uncertainty_flags,
    }
    return DecisionProofSnapshot(
        proof_identity=canonical_sha256(payload),
        schema_version=DECISION_PROOF_SCHEMA_VERSION,
        engine_version=DECISION_PROOF_ENGINE_VERSION,
        forecast_identity=forecast.forecast_identity,
        signal_freeze_identity=forecast.signal_freeze_identity,
        asset=forecast.asset,
        symbol=forecast.symbol,
        timeframe=forecast.timeframe,
        issued_at_ms=forecast.issued_at_ms,
        source_as_of_ms=forecast.source_as_of_ms,
        signal_state=forecast.signal_state.value,
        direction=forecast.direction.value,
        conditional_thesis=thesis,
        trigger_zone=forecast.trigger_zone,
        target_zone=forecast.target_zone,
        invalidation_price=forecast.invalidation_price,
        horizon_bars=forecast.horizon_bars,
        confluence_support_score_0_100=forecast.confluence_support_score_0_100,
        confluence_opposition_score_0_100=forecast.confluence_opposition_score_0_100,
        probability_status=forecast.probability_status,
        calibrated_probability_0_1=forecast.calibrated_probability_0_1,
        event_context_state=forecast.event_context_state.value,
        authority=forecast.authority.value,
        freshness_0_1=forecast.freshness_0_1,
        uncertainty_flags=forecast.uncertainty_flags,
        forecast_source_evidence_identities=forecast.source_evidence_identities,
        evidence_slices=ordered,
        evidence_summary=summary,
    )


def build_live_intelligence_feed_event(
    proof: DecisionProofSnapshot,
    forecast: ImmutableForecast,
    *,
    resolution: ForecastResolution | None = None,
) -> LiveIntelligenceFeedEvent:
    if proof.forecast_identity != forecast.forecast_identity:
        raise ValueError("Live feed proof/forecast identity mismatch")
    if proof.signal_freeze_identity != forecast.signal_freeze_identity:
        raise ValueError("Live feed proof/forecast signal lineage mismatch")

    if resolution is None:
        kind = LiveFeedEventKind.FORECAST_ISSUED
        event_at_ms = forecast.issued_at_ms
        state = forecast.signal_state.value
        resolution_identity: str | None = None
    else:
        if resolution.forecast_identity != forecast.forecast_identity:
            raise ValueError("Live feed resolution/forecast identity mismatch")
        if resolution.signal_freeze_identity != forecast.signal_freeze_identity:
            raise ValueError("Live feed resolution/forecast signal lineage mismatch")
        if resolution.evaluated_at_ms < forecast.issued_at_ms:
            raise ValueError("Live feed resolution cannot predate forecast")
        kind = LiveFeedEventKind.FORECAST_RESOLVED
        event_at_ms = resolution.evaluated_at_ms
        state = resolution.state.value
        resolution_identity = resolution.resolution_identity

    payload = {
        "asset": proof.asset,
        "authority": proof.authority,
        "calibrated_probability_0_1": proof.calibrated_probability_0_1,
        "conditional_thesis": proof.conditional_thesis,
        "engine_version": DECISION_PROOF_ENGINE_VERSION,
        "event_at_ms": event_at_ms,
        "evidence_summary": proof.evidence_summary,
        "forecast_identity": forecast.forecast_identity,
        "freshness_0_1": proof.freshness_0_1,
        "invalidation_price": proof.invalidation_price,
        "kind": kind,
        "private_reasoning_exposed": False,
        "probability_status": proof.probability_status,
        "production_authority": False,
        "proof_identity": proof.proof_identity,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "resolution_identity": resolution_identity,
        "schema_version": LIVE_FEED_SCHEMA_VERSION,
        "state": state,
        "symbol": proof.symbol,
        "target_zone": proof.target_zone,
        "timeframe": proof.timeframe,
        "trigger_zone": proof.trigger_zone,
        "uncertainty_flags": proof.uncertainty_flags,
    }
    return LiveIntelligenceFeedEvent(
        event_identity=canonical_sha256(payload),
        schema_version=LIVE_FEED_SCHEMA_VERSION,
        engine_version=DECISION_PROOF_ENGINE_VERSION,
        kind=kind,
        event_at_ms=event_at_ms,
        forecast_identity=forecast.forecast_identity,
        proof_identity=proof.proof_identity,
        resolution_identity=resolution_identity,
        state=state,
        asset=proof.asset,
        symbol=proof.symbol,
        timeframe=proof.timeframe,
        conditional_thesis=proof.conditional_thesis,
        trigger_zone=proof.trigger_zone,
        target_zone=proof.target_zone,
        invalidation_price=proof.invalidation_price,
        evidence_summary=proof.evidence_summary,
        freshness_0_1=proof.freshness_0_1,
        authority=proof.authority,
        probability_status=proof.probability_status,
        calibrated_probability_0_1=proof.calibrated_probability_0_1,
        uncertainty_flags=proof.uncertainty_flags,
    )


def empty_live_intelligence_feed() -> LiveIntelligenceFeedSnapshot:
    return _feed_snapshot(())


def append_live_intelligence_feed_event(
    snapshot: LiveIntelligenceFeedSnapshot,
    event: LiveIntelligenceFeedEvent,
) -> LiveIntelligenceFeedSnapshot:
    if any(item.event_identity == event.event_identity for item in snapshot.events):
        raise ValueError("Live feed event already exists")
    if any(
        item.forecast_identity == event.forecast_identity and item.kind is event.kind
        for item in snapshot.events
    ):
        raise ValueError(
            "Live feed already contains this forecast event kind"
        )
    if snapshot.events:
        last = snapshot.events[-1]
        if (event.event_at_ms, event.event_identity) <= (
            last.event_at_ms,
            last.event_identity,
        ):
            raise ValueError("Live feed append would violate chronological order")
    return _feed_snapshot((*snapshot.events, event))


def _feed_snapshot(
    events: tuple[LiveIntelligenceFeedEvent, ...],
) -> LiveIntelligenceFeedSnapshot:
    payload = {
        "append_only": True,
        "engine_version": DECISION_PROOF_ENGINE_VERSION,
        "events": events,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": LIVE_FEED_SNAPSHOT_SCHEMA_VERSION,
    }
    return LiveIntelligenceFeedSnapshot(
        snapshot_identity=canonical_sha256(payload),
        schema_version=LIVE_FEED_SNAPSHOT_SCHEMA_VERSION,
        engine_version=DECISION_PROOF_ENGINE_VERSION,
        events=events,
    )


def _evidence_summary(
    slices: tuple[DecisionProofEvidenceSlice, ...],
) -> DecisionProofEvidenceSummary:
    return DecisionProofEvidenceSummary(
        support_count=sum(
            item.verdict is ProofEvidenceVerdict.SUPPORT for item in slices
        ),
        contradict_count=sum(
            item.verdict is ProofEvidenceVerdict.CONTRADICT for item in slices
        ),
        neutral_count=sum(
            item.verdict is ProofEvidenceVerdict.NEUTRAL for item in slices
        ),
        insufficient_count=sum(
            item.verdict is ProofEvidenceVerdict.INSUFFICIENT for item in slices
        ),
        available_count=sum(
            item.availability is ProofEvidenceAvailability.AVAILABLE
            for item in slices
        ),
        total_domain_count=len(slices),
    )


def _conditional_thesis(forecast: ImmutableForecast) -> str:
    direction = forecast.direction.value.upper()
    return (
        f"If {forecast.symbol} enters "
        f"{_decimal_text(forecast.trigger_zone.low)}-"
        f"{_decimal_text(forecast.trigger_zone.high)} while "
        f"{forecast.condition_code} remains valid, {direction} target "
        f"{_decimal_text(forecast.target_zone.high)} remains valid unless "
        f"invalidated at {_decimal_text(forecast.invalidation_price)} "
        f"within {forecast.horizon_bars} bars."
    )


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def _slice_for(
    slices: tuple[DecisionProofEvidenceSlice, ...],
    domain: ProofEvidenceDomain,
) -> DecisionProofEvidenceSlice:
    return next(item for item in slices if item.domain is domain)


def _slice_payload(item: DecisionProofEvidenceSlice) -> dict[str, object]:
    return {
        "availability": item.availability,
        "domain": item.domain,
        "engine_version": item.engine_version,
        "evidence_identities": item.evidence_identities,
        "freshness_0_1": item.freshness_0_1,
        "market_available_at_ms": item.market_available_at_ms,
        "observed_at_ms": item.observed_at_ms,
        "schema_version": item.schema_version,
        "source_quality": item.source_quality,
        "summary_codes": item.summary_codes,
        "verdict": item.verdict,
    }


def _proof_payload(proof: DecisionProofSnapshot) -> dict[str, object]:
    return {
        "asset": proof.asset,
        "authority": proof.authority,
        "calibrated_probability_0_1": proof.calibrated_probability_0_1,
        "conditional_thesis": proof.conditional_thesis,
        "confluence_opposition_score_0_100": (
            proof.confluence_opposition_score_0_100
        ),
        "confluence_support_score_0_100": proof.confluence_support_score_0_100,
        "direction": proof.direction,
        "engine_version": proof.engine_version,
        "event_context_state": proof.event_context_state,
        "evidence_slices": proof.evidence_slices,
        "evidence_summary": proof.evidence_summary,
        "forecast_identity": proof.forecast_identity,
        "forecast_source_evidence_identities": (
            proof.forecast_source_evidence_identities
        ),
        "freshness_0_1": proof.freshness_0_1,
        "horizon_bars": proof.horizon_bars,
        "invalidation_price": proof.invalidation_price,
        "issued_at_ms": proof.issued_at_ms,
        "private_reasoning_exposed": proof.private_reasoning_exposed,
        "probability_status": proof.probability_status,
        "production_authority": proof.production_authority,
        "read_only": proof.read_only,
        "real_capital": proof.real_capital,
        "schema_version": proof.schema_version,
        "signal_freeze_identity": proof.signal_freeze_identity,
        "signal_state": proof.signal_state,
        "source_as_of_ms": proof.source_as_of_ms,
        "symbol": proof.symbol,
        "target_zone": proof.target_zone,
        "timeframe": proof.timeframe,
        "trigger_zone": proof.trigger_zone,
        "uncertainty_flags": proof.uncertainty_flags,
    }


def _feed_event_payload(event: LiveIntelligenceFeedEvent) -> dict[str, object]:
    return {
        "asset": event.asset,
        "authority": event.authority,
        "calibrated_probability_0_1": event.calibrated_probability_0_1,
        "conditional_thesis": event.conditional_thesis,
        "engine_version": event.engine_version,
        "event_at_ms": event.event_at_ms,
        "evidence_summary": event.evidence_summary,
        "forecast_identity": event.forecast_identity,
        "freshness_0_1": event.freshness_0_1,
        "invalidation_price": event.invalidation_price,
        "kind": event.kind,
        "private_reasoning_exposed": event.private_reasoning_exposed,
        "probability_status": event.probability_status,
        "production_authority": event.production_authority,
        "proof_identity": event.proof_identity,
        "read_only": event.read_only,
        "real_capital": event.real_capital,
        "resolution_identity": event.resolution_identity,
        "schema_version": event.schema_version,
        "state": event.state,
        "symbol": event.symbol,
        "target_zone": event.target_zone,
        "timeframe": event.timeframe,
        "trigger_zone": event.trigger_zone,
        "uncertainty_flags": event.uncertainty_flags,
    }


def _feed_snapshot_payload(
    snapshot: LiveIntelligenceFeedSnapshot,
) -> dict[str, object]:
    return {
        "append_only": snapshot.append_only,
        "engine_version": snapshot.engine_version,
        "events": snapshot.events,
        "production_authority": snapshot.production_authority,
        "read_only": snapshot.read_only,
        "real_capital": snapshot.real_capital,
        "schema_version": snapshot.schema_version,
    }


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")


def _require_text_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_text(value, label)


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


def _require_unit_interval(value: Decimal, label: str) -> None:
    if (
        value.is_nan()
        or value.is_infinite()
        or value < Decimal(0)
        or value > Decimal(1)
    ):
        raise ValueError(f"{label} must be inside [0,1]")
