from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyContribution,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_messages import (
    StreamFactBundle,
    StreamMessageInput,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
)

STREAM_STORY_OBSERVATION_SCHEMA_VERSION = "intelligence-stream-story-observation-v1/1"
STREAM_STORY_STATE_SCHEMA_VERSION = "intelligence-stream-story-state-v1/1"
STREAM_CHANGE_SET_SCHEMA_VERSION = "intelligence-stream-change-set-v1/1"


@dataclass(frozen=True, slots=True)
class StreamStoryObservation:
    observation_identity: str
    story_identity: str
    source_event_identity: str
    stream_event_identity: str
    message_identity: str | None
    previous_state_identity: str | None
    asset: str
    symbol: str
    timeframe: str
    event_at_ms: int
    decision_state: str
    direction: str
    source_stance_key: str
    support_score_0_100: Decimal
    opposition_score_0_100: Decimal
    family_contributions: tuple[ConfluenceFamilyContribution, ...]
    event_risk_state: str
    trigger_state: str | None
    capital_reference_identities: tuple[str, ...]
    outcome_state: str | None
    schema_version: str = STREAM_STORY_OBSERVATION_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.observation_identity, "Stream story observation identity"),
            (self.story_identity, "Stream story identity"),
            (self.source_event_identity, "Stream story source-event identity"),
            (self.stream_event_identity, "Stream story stream-event identity"),
        ):
            _require_sha256(value, label)
        for optional_identity, label in (
            (self.message_identity, "Stream story message identity"),
            (self.previous_state_identity, "Stream previous story-state identity"),
        ):
            if optional_identity is not None:
                _require_sha256(optional_identity, label)
        _require_identity_tuple(
            self.capital_reference_identities,
            "Stream story capital reference",
        )
        for value, label in (
            (self.asset, "Stream story asset"),
            (self.symbol, "Stream story symbol"),
            (self.timeframe, "Stream story timeframe"),
            (self.decision_state, "Stream story decision state"),
            (self.direction, "Stream story direction"),
            (self.source_stance_key, "Stream story stance key"),
            (self.event_risk_state, "Stream story Event Risk state"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.event_at_ms < 0:
            raise ValueError("Stream story observation time must be non-negative")
        for score in (self.support_score_0_100, self.opposition_score_0_100):
            if score < Decimal(0) or score > Decimal(100):
                raise ValueError("Stream story score outside [0,100]")
        _require_family_contributions(self.family_contributions)
        if self.trigger_state is not None and not self.trigger_state.strip():
            raise ValueError("Stream trigger state cannot be blank")
        if self.outcome_state is not None and not self.outcome_state.strip():
            raise ValueError("Stream outcome state cannot be blank")
        if self.source_stance_key != f"{self.direction}:{self.decision_state}":
            raise ValueError("Stream story stance key mismatch")
        _require_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_STORY_OBSERVATION_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.observation_identity != canonical_sha256(_observation_payload(self)):
            raise ValueError("Stream story observation identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamStoryState:
    state_identity: str
    story_identity: str
    observation_identity: str
    source_event_identity: str
    current_stream_event_identity: str
    current_message_identity: str | None
    previous_state_identity: str | None
    previous_message_identity: str | None
    asset: str
    symbol: str
    timeframe: str
    event_at_ms: int
    decision_state: str
    direction: str
    source_stance_key: str
    support_score_0_100: Decimal
    opposition_score_0_100: Decimal
    family_contributions: tuple[ConfluenceFamilyContribution, ...]
    event_risk_state: str
    trigger_state: str | None
    capital_reference_identities: tuple[str, ...]
    outcome_state: str | None
    schema_version: str = STREAM_STORY_STATE_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.state_identity, "Stream story state identity"),
            (self.story_identity, "Stream story state story identity"),
            (self.observation_identity, "Stream story state observation identity"),
            (self.source_event_identity, "Stream story state source-event identity"),
            (
                self.current_stream_event_identity,
                "Stream story current stream-event identity",
            ),
        ):
            _require_sha256(value, label)
        for optional_identity, label in (
            (self.current_message_identity, "Stream current message identity"),
            (self.previous_state_identity, "Stream previous story state identity"),
            (self.previous_message_identity, "Stream previous message identity"),
        ):
            if optional_identity is not None:
                _require_sha256(optional_identity, label)
        _require_identity_tuple(
            self.capital_reference_identities,
            "Stream story state capital reference",
        )
        for value, label in (
            (self.asset, "Stream story state asset"),
            (self.symbol, "Stream story state symbol"),
            (self.timeframe, "Stream story state timeframe"),
            (self.decision_state, "Stream story state decision state"),
            (self.direction, "Stream story state direction"),
            (self.source_stance_key, "Stream story state stance"),
            (self.event_risk_state, "Stream story state Event Risk"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.event_at_ms < 0:
            raise ValueError("Stream story state time must be non-negative")
        for score in (self.support_score_0_100, self.opposition_score_0_100):
            if score < Decimal(0) or score > Decimal(100):
                raise ValueError("Stream story state score outside [0,100]")
        _require_family_contributions(self.family_contributions)
        if self.source_stance_key != f"{self.direction}:{self.decision_state}":
            raise ValueError("Stream story state stance key mismatch")
        _require_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_STORY_STATE_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.state_identity != canonical_sha256(_state_payload(self)):
            raise ValueError("Stream story state identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamFamilyChange:
    family: ConfluenceFamily
    previous_state: str
    current_state: str
    previous_direction: str | None
    current_direction: str | None
    support_delta: Decimal
    opposition_delta: Decimal
    previous_quality_0_1: Decimal | None
    current_quality_0_1: Decimal | None
    previous_freshness_0_1: Decimal | None
    current_freshness_0_1: Decimal | None
    previous_material_conflict_count: int
    current_material_conflict_count: int

    def __post_init__(self) -> None:
        if not self.previous_state.strip() or not self.current_state.strip():
            raise ValueError("Stream family change states must be non-empty")
        if min(
            self.previous_material_conflict_count,
            self.current_material_conflict_count,
        ) < 0:
            raise ValueError("Stream family conflict count cannot be negative")


@dataclass(frozen=True, slots=True)
class StreamChangeSet:
    change_set_identity: str
    story_identity: str
    previous_state_identity: str | None
    current_state_identity: str
    previous_message_identity: str | None
    current_message_identity: str | None
    story_started: bool
    stance_changed: bool
    previous_stance_key: str | None
    current_stance_key: str
    support_score_delta: Decimal | None
    opposition_score_delta: Decimal | None
    family_changes: tuple[StreamFamilyChange, ...]
    risk_changed: bool
    previous_risk_state: str | None
    current_risk_state: str
    trigger_changed: bool
    previous_trigger_state: str | None
    current_trigger_state: str | None
    capital_changed: bool
    capital_reference_added: tuple[str, ...]
    capital_reference_removed: tuple[str, ...]
    outcome_changed: bool
    previous_outcome_state: str | None
    current_outcome_state: str | None
    changed_codes: tuple[str, ...]
    schema_version: str = STREAM_CHANGE_SET_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.change_set_identity, "Stream change-set identity"),
            (self.story_identity, "Stream change-set story identity"),
            (self.current_state_identity, "Stream current story-state identity"),
        ):
            _require_sha256(value, label)
        for optional_identity, label in (
            (self.previous_state_identity, "Stream previous change-state identity"),
            (self.previous_message_identity, "Stream previous change message"),
            (self.current_message_identity, "Stream current change message"),
        ):
            if optional_identity is not None:
                _require_sha256(optional_identity, label)
        if self.story_started != (self.previous_state_identity is None):
            raise ValueError("Stream story-start flag does not match previous state")
        if not self.current_stance_key.strip() or not self.current_risk_state.strip():
            raise ValueError("Stream change current state text must be non-empty")
        _require_identity_tuple(
            self.capital_reference_added,
            "Stream capital reference added",
        )
        _require_identity_tuple(
            self.capital_reference_removed,
            "Stream capital reference removed",
        )
        if tuple(item.family.value for item in self.family_changes) != tuple(
            sorted(item.family.value for item in self.family_changes)
        ):
            raise ValueError("Stream family changes must be canonical")
        _require_text_tuple(self.changed_codes, "Stream changed code")
        if not self.changed_codes:
            raise ValueError("Stream change set requires at least one change code")
        if self.story_started:
            if self.previous_stance_key is not None:
                raise ValueError("new story cannot have previous stance")
            if self.support_score_delta is not None or self.opposition_score_delta is not None:
                raise ValueError("new story cannot have score deltas")
            if self.family_changes:
                raise ValueError("new story cannot have family deltas")
            if self.previous_risk_state is not None:
                raise ValueError("new story cannot have previous risk")
            if self.previous_trigger_state is not None:
                raise ValueError("new story cannot have previous trigger")
            if self.previous_outcome_state is not None:
                raise ValueError("new story cannot have previous outcome")
        _require_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_CHANGE_SET_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.change_set_identity != canonical_sha256(_change_payload(self)):
            raise ValueError("Stream change-set identity mismatch")


def build_story_observation(
    message: StreamMessageInput,
    fact_bundle: StreamFactBundle,
    *,
    previous_state_identity: str | None = None,
) -> StreamStoryObservation:
    if message.fact_bundle_identity != fact_bundle.fact_bundle_identity:
        raise ValueError("Stream story message/fact identity mismatch")
    if message.story_identity != fact_bundle.story_identity:
        raise ValueError("Stream story message/fact story mismatch")
    if message.stream_event_identity != fact_bundle.stream_event_identity:
        raise ValueError("Stream story message/fact event mismatch")
    return build_story_observation_snapshot(
        story_identity=message.story_identity,
        source_event_identity=fact_bundle.source_event_identity,
        stream_event_identity=message.stream_event_identity,
        message_identity=message.message_identity,
        previous_state_identity=previous_state_identity,
        asset=fact_bundle.asset,
        symbol=fact_bundle.symbol,
        timeframe=fact_bundle.timeframe,
        event_at_ms=fact_bundle.event_at_ms,
        decision_state=fact_bundle.decision_state,
        direction=fact_bundle.direction,
        support_score_0_100=fact_bundle.confluence_support_score_0_100,
        opposition_score_0_100=fact_bundle.confluence_opposition_score_0_100,
        family_contributions=fact_bundle.family_contributions,
        event_risk_state=fact_bundle.event_context_state,
        trigger_state=None,
        capital_reference_identities=message.capital_reference_identities,
        outcome_state=(
            None
            if fact_bundle.resolution_state is None
            else fact_bundle.resolution_state.value
        ),
    )


def build_story_observation_snapshot(
    *,
    story_identity: str,
    source_event_identity: str,
    stream_event_identity: str,
    message_identity: str | None,
    previous_state_identity: str | None,
    asset: str,
    symbol: str,
    timeframe: str,
    event_at_ms: int,
    decision_state: str,
    direction: str,
    support_score_0_100: Decimal,
    opposition_score_0_100: Decimal,
    family_contributions: tuple[ConfluenceFamilyContribution, ...],
    event_risk_state: str,
    trigger_state: str | None,
    capital_reference_identities: tuple[str, ...],
    outcome_state: str | None,
) -> StreamStoryObservation:
    capital_refs = tuple(sorted(set(capital_reference_identities)))
    payload = {
        "asset": asset,
        "capital_reference_identities": capital_refs,
        "decision_state": decision_state,
        "direction": direction,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": event_at_ms,
        "event_risk_state": event_risk_state,
        "family_contributions": family_contributions,
        "message_identity": message_identity,
        "opposition_score_0_100": opposition_score_0_100,
        "outcome_state": outcome_state,
        "previous_state_identity": previous_state_identity,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_STORY_OBSERVATION_SCHEMA_VERSION,
        "source_event_identity": source_event_identity,
        "source_stance_key": f"{direction}:{decision_state}",
        "story_identity": story_identity,
        "stream_event_identity": stream_event_identity,
        "support_score_0_100": support_score_0_100,
        "symbol": symbol,
        "timeframe": timeframe,
        "trigger_state": trigger_state,
    }
    return StreamStoryObservation(
        observation_identity=canonical_sha256(payload),
        story_identity=story_identity,
        source_event_identity=source_event_identity,
        stream_event_identity=stream_event_identity,
        message_identity=message_identity,
        previous_state_identity=previous_state_identity,
        asset=asset,
        symbol=symbol,
        timeframe=timeframe,
        event_at_ms=event_at_ms,
        decision_state=decision_state,
        direction=direction,
        source_stance_key=f"{direction}:{decision_state}",
        support_score_0_100=support_score_0_100,
        opposition_score_0_100=opposition_score_0_100,
        family_contributions=family_contributions,
        event_risk_state=event_risk_state,
        trigger_state=trigger_state,
        capital_reference_identities=capital_refs,
        outcome_state=outcome_state,
    )


def build_story_state(
    observation: StreamStoryObservation,
    *,
    previous_state: StreamStoryState | None = None,
) -> StreamStoryState:
    if previous_state is None:
        if observation.previous_state_identity is not None:
            raise ValueError("root Stream story observation cannot name previous state")
        previous_state_identity = None
        previous_message_identity = None
    else:
        if observation.previous_state_identity != previous_state.state_identity:
            raise ValueError("Stream story observation previous-state mismatch")
        if observation.story_identity != previous_state.story_identity:
            raise ValueError("Stream story state cannot join unrelated story")
        if (observation.asset, observation.symbol, observation.timeframe) != (
            previous_state.asset,
            previous_state.symbol,
            previous_state.timeframe,
        ):
            raise ValueError("Stream story state market context changed unexpectedly")
        if (
            observation.event_at_ms,
            observation.stream_event_identity,
        ) <= (
            previous_state.event_at_ms,
            previous_state.current_stream_event_identity,
        ):
            raise ValueError("Stream story state append would backfill or fork")
        previous_state_identity = previous_state.state_identity
        previous_message_identity = previous_state.current_message_identity

    payload = {
        "asset": observation.asset,
        "capital_reference_identities": observation.capital_reference_identities,
        "current_message_identity": observation.message_identity,
        "current_stream_event_identity": observation.stream_event_identity,
        "decision_state": observation.decision_state,
        "direction": observation.direction,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": observation.event_at_ms,
        "event_risk_state": observation.event_risk_state,
        "family_contributions": observation.family_contributions,
        "observation_identity": observation.observation_identity,
        "opposition_score_0_100": observation.opposition_score_0_100,
        "outcome_state": observation.outcome_state,
        "previous_message_identity": previous_message_identity,
        "previous_state_identity": previous_state_identity,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_STORY_STATE_SCHEMA_VERSION,
        "source_event_identity": observation.source_event_identity,
        "source_stance_key": observation.source_stance_key,
        "story_identity": observation.story_identity,
        "support_score_0_100": observation.support_score_0_100,
        "symbol": observation.symbol,
        "timeframe": observation.timeframe,
        "trigger_state": observation.trigger_state,
    }
    return StreamStoryState(
        state_identity=canonical_sha256(payload),
        story_identity=observation.story_identity,
        observation_identity=observation.observation_identity,
        source_event_identity=observation.source_event_identity,
        current_stream_event_identity=observation.stream_event_identity,
        current_message_identity=observation.message_identity,
        previous_state_identity=previous_state_identity,
        previous_message_identity=previous_message_identity,
        asset=observation.asset,
        symbol=observation.symbol,
        timeframe=observation.timeframe,
        event_at_ms=observation.event_at_ms,
        decision_state=observation.decision_state,
        direction=observation.direction,
        source_stance_key=observation.source_stance_key,
        support_score_0_100=observation.support_score_0_100,
        opposition_score_0_100=observation.opposition_score_0_100,
        family_contributions=observation.family_contributions,
        event_risk_state=observation.event_risk_state,
        trigger_state=observation.trigger_state,
        capital_reference_identities=observation.capital_reference_identities,
        outcome_state=observation.outcome_state,
    )


def build_change_set(
    current_state: StreamStoryState,
    *,
    previous_state: StreamStoryState | None = None,
) -> StreamChangeSet:
    if previous_state is None:
        if current_state.previous_state_identity is not None:
            raise ValueError("Stream initial change set requires root story state")
        payload = _change_payload_values(
            story_identity=current_state.story_identity,
            previous_state_identity=None,
            current_state_identity=current_state.state_identity,
            previous_message_identity=None,
            current_message_identity=current_state.current_message_identity,
            story_started=True,
            stance_changed=False,
            previous_stance_key=None,
            current_stance_key=current_state.source_stance_key,
            support_score_delta=None,
            opposition_score_delta=None,
            family_changes=(),
            risk_changed=False,
            previous_risk_state=None,
            current_risk_state=current_state.event_risk_state,
            trigger_changed=False,
            previous_trigger_state=None,
            current_trigger_state=current_state.trigger_state,
            capital_changed=False,
            capital_reference_added=(),
            capital_reference_removed=(),
            outcome_changed=False,
            previous_outcome_state=None,
            current_outcome_state=current_state.outcome_state,
            changed_codes=("story_started",),
        )
        return StreamChangeSet(
            change_set_identity=canonical_sha256(payload),
            story_identity=current_state.story_identity,
            previous_state_identity=None,
            current_state_identity=current_state.state_identity,
            previous_message_identity=None,
            current_message_identity=current_state.current_message_identity,
            story_started=True,
            stance_changed=False,
            previous_stance_key=None,
            current_stance_key=current_state.source_stance_key,
            support_score_delta=None,
            opposition_score_delta=None,
            family_changes=(),
            risk_changed=False,
            previous_risk_state=None,
            current_risk_state=current_state.event_risk_state,
            trigger_changed=False,
            previous_trigger_state=None,
            current_trigger_state=current_state.trigger_state,
            capital_changed=False,
            capital_reference_added=(),
            capital_reference_removed=(),
            outcome_changed=False,
            previous_outcome_state=None,
            current_outcome_state=current_state.outcome_state,
            changed_codes=("story_started",),
        )

    if current_state.story_identity != previous_state.story_identity:
        raise ValueError("Stream change set cannot compare unrelated stories")
    if current_state.previous_state_identity != previous_state.state_identity:
        raise ValueError("Stream change set previous-state identity mismatch")
    if current_state.previous_message_identity != previous_state.current_message_identity:
        raise ValueError("Stream change set previous-message identity mismatch")

    stance_changed = current_state.source_stance_key != previous_state.source_stance_key
    support_delta = (
        current_state.support_score_0_100 - previous_state.support_score_0_100
    )
    opposition_delta = (
        current_state.opposition_score_0_100
        - previous_state.opposition_score_0_100
    )
    family_changes = _family_changes(previous_state, current_state)
    risk_changed = current_state.event_risk_state != previous_state.event_risk_state
    trigger_changed = current_state.trigger_state != previous_state.trigger_state
    previous_capital = set(previous_state.capital_reference_identities)
    current_capital = set(current_state.capital_reference_identities)
    capital_added = tuple(sorted(current_capital - previous_capital))
    capital_removed = tuple(sorted(previous_capital - current_capital))
    capital_changed = bool(capital_added or capital_removed)
    outcome_changed = current_state.outcome_state != previous_state.outcome_state

    codes: set[str] = set()
    if stance_changed:
        codes.add("stance_changed")
    if support_delta != 0 or opposition_delta != 0:
        codes.add("score_changed")
    if family_changes:
        codes.add("evidence_family_changed")
    if risk_changed:
        codes.add("risk_changed")
    if trigger_changed:
        codes.add("trigger_changed")
    if capital_changed:
        codes.add("capital_changed")
    if outcome_changed:
        codes.add("outcome_changed")
    if not codes:
        codes.add("no_story_state_change")
    changed_codes = tuple(sorted(codes))

    payload = _change_payload_values(
        story_identity=current_state.story_identity,
        previous_state_identity=previous_state.state_identity,
        current_state_identity=current_state.state_identity,
        previous_message_identity=previous_state.current_message_identity,
        current_message_identity=current_state.current_message_identity,
        story_started=False,
        stance_changed=stance_changed,
        previous_stance_key=previous_state.source_stance_key,
        current_stance_key=current_state.source_stance_key,
        support_score_delta=support_delta,
        opposition_score_delta=opposition_delta,
        family_changes=family_changes,
        risk_changed=risk_changed,
        previous_risk_state=previous_state.event_risk_state,
        current_risk_state=current_state.event_risk_state,
        trigger_changed=trigger_changed,
        previous_trigger_state=previous_state.trigger_state,
        current_trigger_state=current_state.trigger_state,
        capital_changed=capital_changed,
        capital_reference_added=capital_added,
        capital_reference_removed=capital_removed,
        outcome_changed=outcome_changed,
        previous_outcome_state=previous_state.outcome_state,
        current_outcome_state=current_state.outcome_state,
        changed_codes=changed_codes,
    )
    return StreamChangeSet(
        change_set_identity=canonical_sha256(payload),
        story_identity=current_state.story_identity,
        previous_state_identity=previous_state.state_identity,
        current_state_identity=current_state.state_identity,
        previous_message_identity=previous_state.current_message_identity,
        current_message_identity=current_state.current_message_identity,
        story_started=False,
        stance_changed=stance_changed,
        previous_stance_key=previous_state.source_stance_key,
        current_stance_key=current_state.source_stance_key,
        support_score_delta=support_delta,
        opposition_score_delta=opposition_delta,
        family_changes=family_changes,
        risk_changed=risk_changed,
        previous_risk_state=previous_state.event_risk_state,
        current_risk_state=current_state.event_risk_state,
        trigger_changed=trigger_changed,
        previous_trigger_state=previous_state.trigger_state,
        current_trigger_state=current_state.trigger_state,
        capital_changed=capital_changed,
        capital_reference_added=capital_added,
        capital_reference_removed=capital_removed,
        outcome_changed=outcome_changed,
        previous_outcome_state=previous_state.outcome_state,
        current_outcome_state=current_state.outcome_state,
        changed_codes=changed_codes,
    )


def _family_changes(
    previous: StreamStoryState,
    current: StreamStoryState,
) -> tuple[StreamFamilyChange, ...]:
    before_by_family = {item.family: item for item in previous.family_contributions}
    after_by_family = {item.family: item for item in current.family_contributions}
    if set(before_by_family) != set(after_by_family):
        raise ValueError("Stream story family set changed unexpectedly")

    changes: list[StreamFamilyChange] = []
    for family in sorted(ConfluenceFamily, key=lambda item: item.value):
        before = before_by_family[family]
        after = after_by_family[family]
        if before == after:
            continue
        changes.append(
            StreamFamilyChange(
                family=family,
                previous_state=before.state.value,
                current_state=after.state.value,
                previous_direction=(
                    None if before.direction is None else before.direction.value
                ),
                current_direction=(
                    None if after.direction is None else after.direction.value
                ),
                support_delta=after.support_points - before.support_points,
                opposition_delta=after.opposition_points - before.opposition_points,
                previous_quality_0_1=before.evidence_quality_0_1,
                current_quality_0_1=after.evidence_quality_0_1,
                previous_freshness_0_1=before.freshness_0_1,
                current_freshness_0_1=after.freshness_0_1,
                previous_material_conflict_count=before.material_conflict_count,
                current_material_conflict_count=after.material_conflict_count,
            )
        )
    return tuple(changes)


def _change_payload_values(
    *,
    story_identity: str,
    previous_state_identity: str | None,
    current_state_identity: str,
    previous_message_identity: str | None,
    current_message_identity: str | None,
    story_started: bool,
    stance_changed: bool,
    previous_stance_key: str | None,
    current_stance_key: str,
    support_score_delta: Decimal | None,
    opposition_score_delta: Decimal | None,
    family_changes: tuple[StreamFamilyChange, ...],
    risk_changed: bool,
    previous_risk_state: str | None,
    current_risk_state: str,
    trigger_changed: bool,
    previous_trigger_state: str | None,
    current_trigger_state: str | None,
    capital_changed: bool,
    capital_reference_added: tuple[str, ...],
    capital_reference_removed: tuple[str, ...],
    outcome_changed: bool,
    previous_outcome_state: str | None,
    current_outcome_state: str | None,
    changed_codes: tuple[str, ...],
) -> dict[str, object]:
    return {
        "capital_changed": capital_changed,
        "capital_reference_added": capital_reference_added,
        "capital_reference_removed": capital_reference_removed,
        "changed_codes": changed_codes,
        "current_message_identity": current_message_identity,
        "current_outcome_state": current_outcome_state,
        "current_risk_state": current_risk_state,
        "current_stance_key": current_stance_key,
        "current_state_identity": current_state_identity,
        "current_trigger_state": current_trigger_state,
        "engine_version": STREAM_ENGINE_VERSION,
        "family_changes": family_changes,
        "opposition_score_delta": opposition_score_delta,
        "outcome_changed": outcome_changed,
        "previous_message_identity": previous_message_identity,
        "previous_outcome_state": previous_outcome_state,
        "previous_risk_state": previous_risk_state,
        "previous_stance_key": previous_stance_key,
        "previous_state_identity": previous_state_identity,
        "previous_trigger_state": previous_trigger_state,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "risk_changed": risk_changed,
        "schema_version": STREAM_CHANGE_SET_SCHEMA_VERSION,
        "stance_changed": stance_changed,
        "story_identity": story_identity,
        "story_started": story_started,
        "support_score_delta": support_score_delta,
        "trigger_changed": trigger_changed,
    }


def _observation_payload(value: StreamStoryObservation) -> dict[str, object]:
    return {
        "asset": value.asset,
        "capital_reference_identities": value.capital_reference_identities,
        "decision_state": value.decision_state,
        "direction": value.direction,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "event_risk_state": value.event_risk_state,
        "family_contributions": value.family_contributions,
        "message_identity": value.message_identity,
        "opposition_score_0_100": value.opposition_score_0_100,
        "outcome_state": value.outcome_state,
        "previous_state_identity": value.previous_state_identity,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
        "source_stance_key": value.source_stance_key,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "support_score_0_100": value.support_score_0_100,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
        "trigger_state": value.trigger_state,
    }


def _state_payload(value: StreamStoryState) -> dict[str, object]:
    return {
        "asset": value.asset,
        "capital_reference_identities": value.capital_reference_identities,
        "current_message_identity": value.current_message_identity,
        "current_stream_event_identity": value.current_stream_event_identity,
        "decision_state": value.decision_state,
        "direction": value.direction,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "event_risk_state": value.event_risk_state,
        "family_contributions": value.family_contributions,
        "observation_identity": value.observation_identity,
        "opposition_score_0_100": value.opposition_score_0_100,
        "outcome_state": value.outcome_state,
        "previous_message_identity": value.previous_message_identity,
        "previous_state_identity": value.previous_state_identity,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
        "source_stance_key": value.source_stance_key,
        "story_identity": value.story_identity,
        "support_score_0_100": value.support_score_0_100,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
        "trigger_state": value.trigger_state,
    }


def _change_payload(value: StreamChangeSet) -> dict[str, object]:
    return _change_payload_values(
        story_identity=value.story_identity,
        previous_state_identity=value.previous_state_identity,
        current_state_identity=value.current_state_identity,
        previous_message_identity=value.previous_message_identity,
        current_message_identity=value.current_message_identity,
        story_started=value.story_started,
        stance_changed=value.stance_changed,
        previous_stance_key=value.previous_stance_key,
        current_stance_key=value.current_stance_key,
        support_score_delta=value.support_score_delta,
        opposition_score_delta=value.opposition_score_delta,
        family_changes=value.family_changes,
        risk_changed=value.risk_changed,
        previous_risk_state=value.previous_risk_state,
        current_risk_state=value.current_risk_state,
        trigger_changed=value.trigger_changed,
        previous_trigger_state=value.previous_trigger_state,
        current_trigger_state=value.current_trigger_state,
        capital_changed=value.capital_changed,
        capital_reference_added=value.capital_reference_added,
        capital_reference_removed=value.capital_reference_removed,
        outcome_changed=value.outcome_changed,
        previous_outcome_state=value.previous_outcome_state,
        current_outcome_state=value.current_outcome_state,
        changed_codes=value.changed_codes,
    )


def _require_family_contributions(
    values: tuple[ConfluenceFamilyContribution, ...],
) -> None:
    if len(values) != len(ConfluenceFamily):
        raise ValueError("Stream story requires all five family contributions")
    families = tuple(item.family for item in values)
    if families != tuple(sorted(ConfluenceFamily, key=lambda item: item.value)):
        raise ValueError("Stream story family contributions must be canonical")


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_text_tuple(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be unique and sorted")
    if any(not value.strip() for value in values):
        raise ValueError(f"{label} cannot contain blank values")


def _require_authority(
    *,
    schema_version: str,
    expected_schema: str,
    engine_version: str,
    read_only: bool,
    production_authority: bool,
    real_capital: int,
) -> None:
    if schema_version != expected_schema:
        raise ValueError("unsupported Stream story schema")
    if engine_version != STREAM_ENGINE_VERSION:
        raise ValueError("unsupported Stream story engine")
    if not read_only:
        raise ValueError("Stream story truth must remain read-only")
    if production_authority:
        raise ValueError("Stream story cannot grant production authority")
    if real_capital != REAL_CAPITAL:
        raise ValueError("REAL_CAPITAL must remain 0")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
