from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Protocol

from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_analytical import (
    StreamAnalyticalPublicationDisposition,
    StreamAnalyticalView,
    StreamCapitalConsequenceState,
    StreamEffectiveStance,
    StreamStanceStrength,
)
from crypto_signal.product.intelligence_stream_messages import StreamFactBundle
from crypto_signal.product.intelligence_stream_models import REAL_CAPITAL, STREAM_ENGINE_VERSION
from crypto_signal.product.intelligence_stream_story import StreamChangeSet

STREAM_NARRATIVE_PLAN_SCHEMA_VERSION = "intelligence-stream-narrative-plan-v1/1"
STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION = "intelligence-stream-narrative-message-v1/1"
STREAM_NARRATIVE_VOICE_VERSION = "crypto-signal-turkish-analyst-v1/1"
STREAM_NARRATIVE_RENDERER_VERSION = "crypto-signal-deterministic-tr-v1/1"
STREAM_NARRATIVE_VALIDATOR_VERSION = "crypto-signal-narrative-validator-v1/1"

COLLAPSED_MAX_CHARS = 420
SIMPLE_MAX_CHARS = 900
TECHNICAL_MAX_CHARS = 1200
INTELLIGENCE_MAX_CHARS = 1000
DECISION_MAX_CHARS = 900
CAPITAL_MAX_CHARS = 650

_NUMERIC_RE = re.compile(
    r"(?<![A-Za-z0-9_])\$?(-?\d[\d,]*(?:\.\d+)?)(?:%)?(?![A-Za-z_])"
)


class StreamNarrativeSourceKind(StrEnum):
    DETERMINISTIC = "deterministic"
    LOCAL_REWRITE = "local_rewrite"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


@dataclass(frozen=True, slots=True)
class StreamNarrativePlan:
    plan_identity: str
    analytical_view_identity: str
    fact_bundle_identity: str
    change_set_identity: str
    story_identity: str
    source_event_identity: str
    stream_event_identity: str
    symbol: str
    timeframe: str
    event_at_ms: int
    voice_variant: int
    story_awareness_codes: tuple[str, ...]
    changed_families: tuple[ConfluenceFamily, ...]
    include_uncertainty: bool
    include_capital: bool
    schema_version: str = STREAM_NARRATIVE_PLAN_SCHEMA_VERSION
    voice_version: str = STREAM_NARRATIVE_VOICE_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.plan_identity, "Stream narrative plan identity"),
            (self.analytical_view_identity, "Stream narrative analytical view identity"),
            (self.fact_bundle_identity, "Stream narrative fact bundle identity"),
            (self.change_set_identity, "Stream narrative change-set identity"),
            (self.story_identity, "Stream narrative story identity"),
            (self.source_event_identity, "Stream narrative source-event identity"),
            (self.stream_event_identity, "Stream narrative stream-event identity"),
        ):
            _require_sha256(value, label)
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("Stream narrative market context must be non-empty")
        if self.event_at_ms < 0:
            raise ValueError("Stream narrative event time must be non-negative")
        if self.voice_variant < 0 or self.voice_variant > 3:
            raise ValueError("Stream narrative voice variant outside 0..3")
        _require_text_tuple(self.story_awareness_codes, "Stream narrative story code")
        family_values = tuple(item.value for item in self.changed_families)
        if family_values != tuple(sorted(set(family_values))):
            raise ValueError("Stream narrative changed families must be canonical")
        _require_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_NARRATIVE_PLAN_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.voice_version != STREAM_NARRATIVE_VOICE_VERSION:
            raise ValueError("unsupported Stream narrative voice version")
        if self.plan_identity != canonical_sha256(_plan_payload(self)):
            raise ValueError("Stream narrative plan identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamNarrativeText:
    collapsed_text: str
    simple_text: str
    technical_text: str
    intelligence_text: str
    decision_text: str
    capital_text: str

    def __post_init__(self) -> None:
        limits = (
            (self.collapsed_text, COLLAPSED_MAX_CHARS, "collapsed"),
            (self.simple_text, SIMPLE_MAX_CHARS, "simple"),
            (self.technical_text, TECHNICAL_MAX_CHARS, "technical"),
            (self.intelligence_text, INTELLIGENCE_MAX_CHARS, "intelligence"),
            (self.decision_text, DECISION_MAX_CHARS, "decision"),
            (self.capital_text, CAPITAL_MAX_CHARS, "capital"),
        )
        for value, limit, label in limits:
            if not value.strip():
                raise ValueError(f"Stream narrative {label} text must be non-empty")
            if "\n" in value and label == "collapsed":
                raise ValueError("Stream collapsed narrative must remain one paragraph")
            if len(value) > limit:
                raise ValueError(f"Stream narrative {label} text exceeds length budget")


@dataclass(frozen=True, slots=True)
class StreamNarrativeValidation:
    valid: bool
    violation_codes: tuple[str, ...]
    observed_numeric_values: tuple[Decimal, ...]
    validator_version: str = STREAM_NARRATIVE_VALIDATOR_VERSION

    def __post_init__(self) -> None:
        _require_text_tuple(self.violation_codes, "Stream narrative violation")
        if self.valid == bool(self.violation_codes):
            raise ValueError("Stream narrative validation flag/codes mismatch")
        if self.validator_version != STREAM_NARRATIVE_VALIDATOR_VERSION:
            raise ValueError("unsupported Stream narrative validator version")


@dataclass(frozen=True, slots=True)
class StreamNarrativeMessage:
    narrative_identity: str
    plan_identity: str
    analytical_view_identity: str
    fact_bundle_identity: str
    change_set_identity: str
    story_identity: str
    source_event_identity: str
    stream_event_identity: str
    symbol: str
    timeframe: str
    event_at_ms: int
    source_kind: StreamNarrativeSourceKind
    fallback_reason_codes: tuple[str, ...]
    text: StreamNarrativeText
    validation: StreamNarrativeValidation
    original_text_preserved: bool = True
    schema_version: str = STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION
    renderer_version: str = STREAM_NARRATIVE_RENDERER_VERSION
    voice_version: str = STREAM_NARRATIVE_VOICE_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.narrative_identity, "Stream narrative identity"),
            (self.plan_identity, "Stream narrative plan identity"),
            (self.analytical_view_identity, "Stream narrative analytical identity"),
            (self.fact_bundle_identity, "Stream narrative fact identity"),
            (self.change_set_identity, "Stream narrative change identity"),
            (self.story_identity, "Stream narrative story identity"),
            (self.source_event_identity, "Stream narrative source-event identity"),
            (self.stream_event_identity, "Stream narrative stream-event identity"),
        ):
            _require_sha256(value, label)
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("Stream narrative message market context must be non-empty")
        if self.event_at_ms < 0:
            raise ValueError("Stream narrative message event time must be non-negative")
        _require_text_tuple(
            self.fallback_reason_codes,
            "Stream narrative fallback reason",
        )
        if self.source_kind is StreamNarrativeSourceKind.DETERMINISTIC_FALLBACK:
            if not self.fallback_reason_codes:
                raise ValueError("Stream narrative fallback requires reason code")
        elif self.fallback_reason_codes:
            raise ValueError("non-fallback Stream narrative cannot carry fallback reasons")
        if not self.validation.valid:
            raise ValueError("persistable Stream narrative must pass validation")
        if not self.original_text_preserved:
            raise ValueError("Stream original narrative text must remain preserved")
        _require_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.renderer_version != STREAM_NARRATIVE_RENDERER_VERSION:
            raise ValueError("unsupported Stream narrative renderer version")
        if self.voice_version != STREAM_NARRATIVE_VOICE_VERSION:
            raise ValueError("unsupported Stream narrative voice version")
        if self.narrative_identity != canonical_sha256(_message_payload(self)):
            raise ValueError("Stream narrative identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamNarrativeRewriteRequest:
    plan_identity: str
    analytical_view_identity: str
    deterministic_text: StreamNarrativeText
    protected_numeric_values: tuple[Decimal, ...]
    symbol: str
    timeframe: str


class StreamNarrativeRewriter(Protocol):
    def rewrite(self, request: StreamNarrativeRewriteRequest) -> StreamNarrativeText:
        ...


def build_stream_narrative_plan(
    view: StreamAnalyticalView,
    fact: StreamFactBundle,
    change_set: StreamChangeSet,
) -> StreamNarrativePlan:
    _validate_inputs(view, fact, change_set)
    if (
        view.materiality.disposition
        is not StreamAnalyticalPublicationDisposition.PUBLISH
    ):
        raise ValueError("silent Analytical View cannot produce customer narrative")

    story_codes = _story_awareness_codes(change_set)
    voice_variant = int(view.analytical_view_identity[:8], 16) % 4
    changed_families = tuple(
        sorted(
            {item.family for item in change_set.family_changes},
            key=lambda item: item.value,
        )
    )
    payload = {
        "analytical_view_identity": view.analytical_view_identity,
        "change_set_identity": change_set.change_set_identity,
        "changed_families": changed_families,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": view.event_at_ms,
        "fact_bundle_identity": fact.fact_bundle_identity,
        "include_capital": (
            view.capital_consequence.state
            is not StreamCapitalConsequenceState.NOT_BOUND
        ),
        "include_uncertainty": bool(view.uncertainty.codes),
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_NARRATIVE_PLAN_SCHEMA_VERSION,
        "source_event_identity": view.source_event_identity,
        "story_awareness_codes": story_codes,
        "story_identity": view.story_identity,
        "stream_event_identity": view.stream_event_identity,
        "symbol": view.symbol,
        "timeframe": view.timeframe,
        "voice_variant": voice_variant,
        "voice_version": STREAM_NARRATIVE_VOICE_VERSION,
    }
    return StreamNarrativePlan(
        plan_identity=canonical_sha256(payload),
        analytical_view_identity=view.analytical_view_identity,
        fact_bundle_identity=fact.fact_bundle_identity,
        change_set_identity=change_set.change_set_identity,
        story_identity=view.story_identity,
        source_event_identity=view.source_event_identity,
        stream_event_identity=view.stream_event_identity,
        symbol=view.symbol,
        timeframe=view.timeframe,
        event_at_ms=view.event_at_ms,
        voice_variant=voice_variant,
        story_awareness_codes=story_codes,
        changed_families=changed_families,
        include_uncertainty=bool(view.uncertainty.codes),
        include_capital=(
            view.capital_consequence.state
            is not StreamCapitalConsequenceState.NOT_BOUND
        ),
    )


def render_stream_narrative(
    plan: StreamNarrativePlan,
    view: StreamAnalyticalView,
    fact: StreamFactBundle,
    change_set: StreamChangeSet,
    *,
    rewriter: StreamNarrativeRewriter | None = None,
    recent_collapsed_texts: tuple[str, ...] = (),
) -> StreamNarrativeMessage:
    _validate_plan_inputs(plan, view, fact, change_set)
    deterministic = _render_deterministic(plan, view, fact, change_set)
    deterministic_validation = validate_stream_narrative(
        view,
        fact,
        deterministic,
    )
    if not deterministic_validation.valid:
        raise ValueError(
            "deterministic Stream narrative violated fact/voice contract"
        )

    if rewriter is None:
        return _build_message(
            plan=plan,
            text=deterministic,
            validation=deterministic_validation,
            source_kind=StreamNarrativeSourceKind.DETERMINISTIC,
            fallback_reason_codes=(),
        )

    request = StreamNarrativeRewriteRequest(
        plan_identity=plan.plan_identity,
        analytical_view_identity=view.analytical_view_identity,
        deterministic_text=deterministic,
        protected_numeric_values=_allowed_numeric_values(view, fact),
        symbol=view.symbol,
        timeframe=view.timeframe,
    )
    try:
        candidate = rewriter.rewrite(request)
    except Exception:
        return _build_message(
            plan=plan,
            text=deterministic,
            validation=deterministic_validation,
            source_kind=StreamNarrativeSourceKind.DETERMINISTIC_FALLBACK,
            fallback_reason_codes=("rewriter_exception",),
        )

    candidate_validation = validate_stream_narrative(view, fact, candidate)
    if not candidate_validation.valid:
        return _build_message(
            plan=plan,
            text=deterministic,
            validation=deterministic_validation,
            source_kind=StreamNarrativeSourceKind.DETERMINISTIC_FALLBACK,
            fallback_reason_codes=("rewriter_validation_rejected",),
        )
    if _too_similar(candidate.collapsed_text, recent_collapsed_texts):
        return _build_message(
            plan=plan,
            text=deterministic,
            validation=deterministic_validation,
            source_kind=StreamNarrativeSourceKind.DETERMINISTIC_FALLBACK,
            fallback_reason_codes=("rewriter_similarity_rejected",),
        )
    return _build_message(
        plan=plan,
        text=candidate,
        validation=candidate_validation,
        source_kind=StreamNarrativeSourceKind.LOCAL_REWRITE,
        fallback_reason_codes=(),
    )


def validate_stream_narrative(
    view: StreamAnalyticalView,
    fact: StreamFactBundle,
    text: StreamNarrativeText,
) -> StreamNarrativeValidation:
    violations: set[str] = set()
    combined = " ".join(
        (
            text.collapsed_text,
            text.simple_text,
            text.technical_text,
            text.intelligence_text,
            text.decision_text,
            text.capital_text,
        )
    )
    lowered = combined.casefold()
    for phrase in ("garanti", "risksiz", "mutlaka", "kesin olarak", "kesinlikle"):
        if phrase in lowered:
            violations.add("prohibited_certainty_language")

    observed = _extract_numeric_values(combined)
    allowed = set(_allowed_numeric_values(view, fact))
    if any(value not in allowed for value in observed):
        violations.add("invented_numeric_fact")

    if fact.calibrated_probability_0_1 is None:
        if re.search(r"\b(?:olasılık|ihtimal)\b[^.]{0,30}%", lowered):
            violations.add("uncalibrated_probability_language")

    if view.symbol not in text.collapsed_text:
        violations.add("collapsed_symbol_missing")
    if view.timeframe not in text.collapsed_text:
        violations.add("collapsed_timeframe_missing")

    return StreamNarrativeValidation(
        valid=not violations,
        violation_codes=tuple(sorted(violations)),
        observed_numeric_values=observed,
    )


def narrative_message_payload(value: StreamNarrativeMessage) -> dict[str, object]:
    return _message_payload(value)


def _render_deterministic(
    plan: StreamNarrativePlan,
    view: StreamAnalyticalView,
    fact: StreamFactBundle,
    change_set: StreamChangeSet,
) -> StreamNarrativeText:
    opening = _opening_sentence(plan.voice_variant, view)
    support = _support_sentence(view)
    change = _change_sentence(plan, change_set)
    uncertainty = _uncertainty_sentence(view)
    collapsed_parts = [f"{view.symbol} {view.timeframe}:", opening]
    if change:
        collapsed_parts.append(change)
    if support:
        collapsed_parts.append(support)
    if uncertainty:
        collapsed_parts.append(uncertainty)
    collapsed = " ".join(collapsed_parts)

    simple = " ".join(
        part
        for part in (
            opening,
            change,
            _simple_condition_sentence(fact),
            uncertainty,
        )
        if part
    )
    technical = _technical_sentence(view, fact)
    intelligence = " ".join(
        part
        for part in (
            _intelligence_sentence(view),
            _story_detail_sentence(change_set),
        )
        if part
    )
    decision = _decision_sentence(view, fact)
    capital = _capital_sentence(view)

    return StreamNarrativeText(
        collapsed_text=collapsed,
        simple_text=simple,
        technical_text=technical,
        intelligence_text=intelligence,
        decision_text=decision,
        capital_text=capital,
    )


def _opening_sentence(variant: int, view: StreamAnalyticalView) -> str:
    stance = view.stance.effective_stance
    strength = view.stance.strength
    if stance is StreamEffectiveStance.RESOLVED:
        options = (
            "Önceki piyasa görüşüm artık sonuçlandı; sonucu yeni bir kayıt olarak tutuyorum.",
            "Bu hikâyedeki önceki beklenti sonuçlandı; ilk görüşü değiştirmeden sonucu ayrı kaydediyorum.",
            "Önceki değerlendirme artık kapanmış durumda; sonuç geçmiş mesajı geriye dönük değiştirmiyor.",
            "Bu beklentinin sonucu belli oldu; ilk karar kaydı aynen korunuyor.",
        )
        return options[variant]
    if stance is StreamEffectiveStance.BLOCKED:
        options = (
            "Şu anda yeni işlem yönü üretmiyorum; risk veya veri koşulu kararı blokluyor.",
            "Piyasa görüşünü işlem kararına çevirmiyorum; mevcut risk durumu bloklayıcı.",
            "Şimdilik kenarda kalıyorum; karar katmanında bloklayıcı bir koşul var.",
            "Bu aşamada yönü işleme taşımıyorum; sistem bloklu durumda.",
        )
        return options[variant]
    if stance is StreamEffectiveStance.WATCH:
        options = (
            "Şimdilik izliyorum; yön fikri işlem için yeterince olgunlaşmış değil.",
            "Henüz acele etmiyorum; koşulların biraz daha netleşmesini bekliyorum.",
            "Şu anki duruşum izlemek; teyit tamamlanmadan görüşü işleme çevirmiyorum.",
            "Piyasayı takip ediyorum ama mevcut yapı henüz karar vermek için yeterince temiz değil.",
        )
        return options[variant]

    direction = "yukarı" if stance is StreamEffectiveStance.BULLISH else "aşağı"
    if strength is StreamStanceStrength.HIGH:
        options = (
            f"Görünümüm {direction} yönlü ve mevcut kanıt dengesi güçlü.",
            f"Şu anda {direction} yönü daha baskın görüyorum; destek yapısı güçlü.",
            f"Mevcut tablo beni {direction} yöne götürüyor ve kanıt desteği güçlü.",
            f"{direction.capitalize()} yönlü görüşüm güçlü; ana kanıt aileleri aynı tarafa ağırlık veriyor.",
        )
    elif strength is StreamStanceStrength.MODERATE:
        options = (
            f"Görünümüm {direction} yönlü, ancak destek seviyesi orta.",
            f"{direction.capitalize()} yön önde fakat teyit henüz güçlü seviyede değil.",
            f"Şimdilik {direction} tarafı tercih ediyorum; destek dengesi orta kuvvette.",
            f"{direction.capitalize()} yönlü fikrim var, fakat ek teyit hâlâ değerli.",
        )
    else:
        options = (
            f"Görünümüm {direction} yönlü olsa da destek zayıf; temkinliyim.",
            f"{direction.capitalize()} yön ihtimali önde ama kanıt desteği düşük.",
            f"Yön fikrim {direction}, fakat mevcut kanıt yapısı henüz güçlü değil.",
            f"{direction.capitalize()} tarafı izliyorum; destek düşük olduğu için acele etmiyorum.",
        )
    return options[variant]


def _support_sentence(view: StreamAnalyticalView) -> str:
    dominant = view.dominant_support
    secondary = view.secondary_support
    contradiction = view.main_contradiction
    if dominant is None:
        return ""
    first = _family_label(dominant.family)
    if secondary is not None:
        sentence = f"En belirgin destek {first} ve {_family_label(secondary.family)} tarafında."
    else:
        sentence = f"En belirgin destek {first} tarafında."
    if contradiction is not None:
        sentence += f" Ana karşı ağırlık {_family_label(contradiction.family)} tarafında."
    return sentence


def _change_sentence(
    plan: StreamNarrativePlan,
    change_set: StreamChangeSet,
) -> str:
    if "outcome_recorded" in plan.story_awareness_codes:
        return "Önceki beklentinin sonucu artık kayda geçti."
    if "missing_confirmation_arrived" in plan.story_awareness_codes:
        families = ", ".join(_family_label(item) for item in plan.changed_families)
        return f"Önce eksik olan teyitlerden biri geldi; değişim {families} tarafında."
    if "confirmation_weakened" in plan.story_awareness_codes:
        families = ", ".join(_family_label(item) for item in plan.changed_families)
        return f"Önceki teyitlerden biri zayıfladı; değişim {families} tarafında."
    if change_set.stance_changed:
        return "Önceki duruma göre yön duruşum değişti."
    if change_set.risk_changed:
        return "Önceki duruma göre risk koşulu değişti."
    if change_set.trigger_changed:
        return "Tetik koşulunun durumu değişti."
    if change_set.capital_changed:
        return "Sanal sermaye bağlantısında yeni bir değişim var."
    return ""


def _uncertainty_sentence(view: StreamAnalyticalView) -> str:
    codes = set(view.uncertainty.codes)
    parts: list[str] = []
    if "accepted_evidence_incomplete" in codes:
        parts.append("Bazı kabul edilmiş kanıt alanları hâlâ eksik.")
    if "accepted_evidence_contradiction" in codes:
        parts.append("Kanıt tarafında çelişki de var.")
    if "probability_not_calibrated" in codes:
        parts.append("Bu değerlendirme kalibre edilmiş bir olasılık yüzdesi değil.")
    return " ".join(parts)


def _simple_condition_sentence(fact: StreamFactBundle) -> str:
    trigger = _format_zone(fact.trigger_zone.low, fact.trigger_zone.high)
    target = _format_zone(fact.target_zone.low, fact.target_zone.high)
    invalidation = _format_price(fact.invalidation_price)
    return (
        f"Takip ettiğim tetik bölgesi {trigger}; hedef bölgesi {target}. "
        f"{invalidation} seviyesi görüşün geçersizlik sınırı."
    )


def _technical_sentence(
    view: StreamAnalyticalView,
    fact: StreamFactBundle,
) -> str:
    support = _format_decimal(view.stance.support_score_0_100)
    opposition = _format_decimal(view.stance.opposition_score_0_100)
    pieces = [
        f"Destek puanı {support}, karşı ağırlık {opposition}.",
    ]
    if view.dominant_support is not None:
        pieces.append(
            f"Birincil aile {_family_label(view.dominant_support.family)} "
            f"({_format_decimal(view.dominant_support.support_points)} destek puanı)."
        )
    if view.secondary_support is not None:
        pieces.append(
            f"İkincil aile {_family_label(view.secondary_support.family)} "
            f"({_format_decimal(view.secondary_support.support_points)} destek puanı)."
        )
    if view.main_contradiction is not None:
        pieces.append(
            f"Ana karşı aile {_family_label(view.main_contradiction.family)} "
            f"({_format_decimal(view.main_contradiction.opposition_points)} karşı puan)."
        )
    pieces.append(f"Event Risk durumu: {fact.event_context_state}.")
    return " ".join(pieces)


def _intelligence_sentence(view: StreamAnalyticalView) -> str:
    stance = view.stance.effective_stance.value
    strength = view.stance.strength.value
    return (
        f"Intelligence sonucu: duruş={stance}, güç={strength}. "
        "Bu görüş dondurulmuş Fact Bundle ve Story State üzerinden üretildi."
    )


def _story_detail_sentence(change_set: StreamChangeSet) -> str:
    if change_set.story_started:
        return "Bu, bu story için ilk analitik değerlendirme."
    codes = ", ".join(change_set.changed_codes)
    return f"Önceki state'e göre kaydedilen değişim kodları: {codes}."


def _decision_sentence(
    view: StreamAnalyticalView,
    fact: StreamFactBundle,
) -> str:
    trigger = _format_zone(fact.trigger_zone.low, fact.trigger_zone.high)
    target = _format_zone(fact.target_zone.low, fact.target_zone.high)
    invalidation = _format_price(fact.invalidation_price)
    if view.stance.effective_stance is StreamEffectiveStance.RESOLVED:
        return (
            "Bu karar artık tarihsel sonuç kaydıdır; ilk beklenti geriye dönük "
            "değiştirilmez."
        )
    return (
        f"Bir sonraki karar koşulu tetik bölgesi {trigger}. "
        f"Hedef bölgesi {target}; görüş {invalidation} seviyesinde geçersizleşir."
    )


def _capital_sentence(view: StreamAnalyticalView) -> str:
    state = view.capital_consequence.state
    if state is StreamCapitalConsequenceState.NOT_BOUND:
        return "Bu mesajda sanal sermayeye bağlı yeni bir referans yok."
    if state is StreamCapitalConsequenceState.BOUND_UNCHANGED:
        return "Sanal sermaye bağlantısı korunuyor; yeni bir referans değişimi yok."
    if state is StreamCapitalConsequenceState.REFERENCES_ADDED:
        return "Sanal sermaye tarafında yeni bir referans eklendi."
    if state is StreamCapitalConsequenceState.REFERENCES_REMOVED:
        return "Sanal sermaye tarafında önceki bir referans kaldırıldı."
    return "Sanal sermaye tarafında referans seti değişti."


def _story_awareness_codes(change_set: StreamChangeSet) -> tuple[str, ...]:
    codes: set[str] = set()
    if change_set.story_started:
        codes.add("story_started")
    if change_set.outcome_changed:
        codes.add("outcome_recorded")
    if any(
        item.previous_state != item.current_state
        and item.current_state == "observed"
        and item.previous_state != "observed"
        for item in change_set.family_changes
    ):
        codes.add("missing_confirmation_arrived")
    if any(
        item.previous_state == "observed"
        and item.current_state != "observed"
        for item in change_set.family_changes
    ):
        codes.add("confirmation_weakened")
    for code in (
        "stance_changed",
        "risk_changed",
        "trigger_changed",
        "capital_changed",
    ):
        if getattr(change_set, code):
            codes.add(code)
    return tuple(sorted(codes))


def _validate_inputs(
    view: StreamAnalyticalView,
    fact: StreamFactBundle,
    change_set: StreamChangeSet,
) -> None:
    if view.fact_bundle_identity != fact.fact_bundle_identity:
        raise ValueError("Stream narrative analytical/fact identity mismatch")
    if view.change_set_identity != change_set.change_set_identity:
        raise ValueError("Stream narrative analytical/change identity mismatch")
    if view.story_identity != fact.story_identity or view.story_identity != change_set.story_identity:
        raise ValueError("Stream narrative story lineage mismatch")
    if view.source_event_identity != fact.source_event_identity:
        raise ValueError("Stream narrative source-event lineage mismatch")
    if view.stream_event_identity != fact.stream_event_identity:
        raise ValueError("Stream narrative stream-event lineage mismatch")
    if (view.symbol, view.timeframe) != (fact.symbol, fact.timeframe):
        raise ValueError("Stream narrative market lineage mismatch")
    if view.event_at_ms != fact.event_at_ms:
        raise ValueError("Stream narrative event-time lineage mismatch")


def _validate_plan_inputs(
    plan: StreamNarrativePlan,
    view: StreamAnalyticalView,
    fact: StreamFactBundle,
    change_set: StreamChangeSet,
) -> None:
    _validate_inputs(view, fact, change_set)
    if plan.analytical_view_identity != view.analytical_view_identity:
        raise ValueError("Stream narrative plan/analytical identity mismatch")
    if plan.fact_bundle_identity != fact.fact_bundle_identity:
        raise ValueError("Stream narrative plan/fact identity mismatch")
    if plan.change_set_identity != change_set.change_set_identity:
        raise ValueError("Stream narrative plan/change identity mismatch")
    if plan.story_identity != view.story_identity:
        raise ValueError("Stream narrative plan/story identity mismatch")


def _allowed_numeric_values(
    view: StreamAnalyticalView,
    fact: StreamFactBundle,
) -> tuple[Decimal, ...]:
    values: set[Decimal] = {
        view.stance.support_score_0_100,
        view.stance.opposition_score_0_100,
        view.stance.net_support_points,
        fact.trigger_zone.low,
        fact.trigger_zone.high,
        fact.target_zone.low,
        fact.target_zone.high,
        fact.invalidation_price,
    }
    if fact.calibrated_probability_0_1 is not None:
        values.add(fact.calibrated_probability_0_1)
        values.add(fact.calibrated_probability_0_1 * Decimal(100))
    for item in fact.family_contributions:
        values.add(item.support_points)
        values.add(item.opposition_points)
        if item.evidence_quality_0_1 is not None:
            values.add(item.evidence_quality_0_1)
        if item.freshness_0_1 is not None:
            values.add(item.freshness_0_1)
    return tuple(sorted(values))


def _extract_numeric_values(text: str) -> tuple[Decimal, ...]:
    values: list[Decimal] = []
    for match in _NUMERIC_RE.finditer(text):
        raw = match.group(1).replace(",", "")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        values.append(value)
    return tuple(values)


def _too_similar(candidate: str, recent: tuple[str, ...]) -> bool:
    if not recent:
        return False
    candidate_tokens = _normalized_tokens(candidate)
    if not candidate_tokens:
        return False
    for previous in recent:
        previous_tokens = _normalized_tokens(previous)
        if not previous_tokens:
            continue
        union = candidate_tokens | previous_tokens
        if not union:
            continue
        similarity = Decimal(len(candidate_tokens & previous_tokens)) / Decimal(len(union))
        if similarity >= Decimal("0.92"):
            return True
    return False


def _normalized_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", text.casefold())
        if len(token) > 1
    }


def _build_message(
    *,
    plan: StreamNarrativePlan,
    text: StreamNarrativeText,
    validation: StreamNarrativeValidation,
    source_kind: StreamNarrativeSourceKind,
    fallback_reason_codes: tuple[str, ...],
) -> StreamNarrativeMessage:
    payload = {
        "analytical_view_identity": plan.analytical_view_identity,
        "change_set_identity": plan.change_set_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": plan.event_at_ms,
        "fact_bundle_identity": plan.fact_bundle_identity,
        "fallback_reason_codes": fallback_reason_codes,
        "original_text_preserved": True,
        "plan_identity": plan.plan_identity,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "renderer_version": STREAM_NARRATIVE_RENDERER_VERSION,
        "schema_version": STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION,
        "source_event_identity": plan.source_event_identity,
        "source_kind": source_kind,
        "story_identity": plan.story_identity,
        "stream_event_identity": plan.stream_event_identity,
        "symbol": plan.symbol,
        "text": text,
        "timeframe": plan.timeframe,
        "validation": validation,
        "voice_version": STREAM_NARRATIVE_VOICE_VERSION,
    }
    return StreamNarrativeMessage(
        narrative_identity=canonical_sha256(payload),
        plan_identity=plan.plan_identity,
        analytical_view_identity=plan.analytical_view_identity,
        fact_bundle_identity=plan.fact_bundle_identity,
        change_set_identity=plan.change_set_identity,
        story_identity=plan.story_identity,
        source_event_identity=plan.source_event_identity,
        stream_event_identity=plan.stream_event_identity,
        symbol=plan.symbol,
        timeframe=plan.timeframe,
        event_at_ms=plan.event_at_ms,
        source_kind=source_kind,
        fallback_reason_codes=fallback_reason_codes,
        text=text,
        validation=validation,
    )


def _family_label(family: ConfluenceFamily) -> str:
    labels = {
        ConfluenceFamily.GEOMETRY: "Geometri",
        ConfluenceFamily.LIQUIDITY: "Likidite",
        ConfluenceFamily.ORDER_FLOW: "Emir akışı",
        ConfluenceFamily.DERIVATIVES: "Türevler",
        ConfluenceFamily.ONCHAIN: "On-chain",
    }
    return labels[family]


def _format_zone(low: Decimal, high: Decimal) -> str:
    if low == high:
        return _format_price(low)
    return f"{_format_price(low)}–{_format_price(high)}"


def _format_price(value: Decimal) -> str:
    return f"${_format_decimal_grouped(value)}"


def _format_decimal_grouped(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        whole, fraction = normalized.split(".", 1)
    else:
        whole, fraction = normalized, ""
    sign = ""
    if whole.startswith("-"):
        sign, whole = "-", whole[1:]
    grouped = f"{int(whole):,}"
    return f"{sign}{grouped}.{fraction}" if fraction else f"{sign}{grouped}"


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _plan_payload(value: StreamNarrativePlan) -> dict[str, object]:
    return {
        "analytical_view_identity": value.analytical_view_identity,
        "change_set_identity": value.change_set_identity,
        "changed_families": value.changed_families,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "fact_bundle_identity": value.fact_bundle_identity,
        "include_capital": value.include_capital,
        "include_uncertainty": value.include_uncertainty,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
        "story_awareness_codes": value.story_awareness_codes,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
        "voice_variant": value.voice_variant,
        "voice_version": value.voice_version,
    }


def _message_payload(value: StreamNarrativeMessage) -> dict[str, object]:
    return {
        "analytical_view_identity": value.analytical_view_identity,
        "change_set_identity": value.change_set_identity,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "fact_bundle_identity": value.fact_bundle_identity,
        "fallback_reason_codes": value.fallback_reason_codes,
        "original_text_preserved": value.original_text_preserved,
        "plan_identity": value.plan_identity,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "renderer_version": value.renderer_version,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
        "source_kind": value.source_kind,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "symbol": value.symbol,
        "text": value.text,
        "timeframe": value.timeframe,
        "validation": value.validation,
        "voice_version": value.voice_version,
    }


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
        raise ValueError("unsupported Stream narrative schema")
    if engine_version != STREAM_ENGINE_VERSION:
        raise ValueError("unsupported Stream narrative engine")
    if not read_only:
        raise ValueError("Stream narrative must remain read-only")
    if production_authority:
        raise ValueError("Stream narrative cannot grant production authority")
    if real_capital != REAL_CAPITAL:
        raise ValueError("REAL_CAPITAL must remain 0")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
