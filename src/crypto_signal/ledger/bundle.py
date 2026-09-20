from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from crypto_signal.confluence.models import (
    ConfluenceAnalysisResult,
    MethodologyEvidence,
)
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle
from crypto_signal.ledger.serialization import canonical_json, sha256_text
from crypto_signal.methodologies.elliott.models import ElliottAnalysisResult
from crypto_signal.methodologies.harmonic.models import HarmonicAnalysisResult
from crypto_signal.methodologies.price_action.analysis import PriceActionAnalysisResult
from crypto_signal.signals.models import SignalDecision

FREEZE_SCHEMA_VERSION = "decision-freeze-v1/1"


@dataclass(frozen=True, slots=True)
class DecisionFreezeBundle:
    bundle_identity: str
    schema_version: str
    source_cutoff_open_time_ms: int
    signal_decision: SignalDecision
    confluence: ConfluenceAnalysisResult
    selected_evidence: tuple[MethodologyEvidence, ...]
    price_action: PriceActionAnalysisResult
    harmonic: HarmonicAnalysisResult
    elliott: ElliottAnalysisResult
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        if len(self.bundle_identity) != 64:
            raise ValueError("bundle identity must be SHA256")
        try:
            int(self.bundle_identity, 16)
        except ValueError as exc:
            raise ValueError("bundle identity must be hexadecimal") from exc
        if self.schema_version != FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported decision-freeze schema version")
        if not self.candles:
            raise ValueError("decision freeze requires consumed candles")
        if self.source_cutoff_open_time_ms != self.candles[-1].open_time_ms:
            raise ValueError("source cutoff must equal newest frozen candle")


ContextValue = (
    ConfluenceAnalysisResult
    | MethodologyEvidence
    | PriceActionAnalysisResult
    | HarmonicAnalysisResult
    | ElliottAnalysisResult
)


def _context_tuple(value: ContextValue) -> tuple[object, ...]:
    return (
        value.exchange,
        value.market_type,
        value.symbol,
        value.timeframe,
        value.as_of_ms,
    )


def _selected_evidence(
    confluence: ConfluenceAnalysisResult,
) -> tuple[MethodologyEvidence, ...]:
    return tuple(
        sorted(
            (
                item
                for selection in confluence.selections
                for item in selection.selected
            ),
            key=lambda item: item.evidence_id,
        )
    )


def _eligible_candles(
    decision: SignalDecision,
    candles: Sequence[Candle],
) -> tuple[Candle, ...]:
    eligible = tuple(
        sorted(
            (
                candle
                for candle in candles
                if candle.is_closed
                and candle.close_time_ms <= decision.as_of_ms
                and candle.ingested_at_ms <= decision.as_of_ms
            ),
            key=lambda candle: candle.open_time_ms,
        )
    )
    if not eligible:
        raise ValueError("decision freeze has no closed observed candles")

    seen: set[int] = set()
    for candle in eligible:
        if (
            candle.exchange != decision.exchange
            or candle.market_type != decision.market_type
            or candle.symbol != decision.symbol
            or candle.timeframe != decision.timeframe
        ):
            raise ValueError("decision freeze candle context mismatch")
        if candle.open_time_ms in seen:
            raise ValueError("decision freeze candle opens must be unique")
        seen.add(candle.open_time_ms)

    gaps = detect_gaps(eligible, decision.timeframe)
    if gaps:
        raise ValueError("decision freeze refuses candle gaps")

    return eligible


def bundle_payload(bundle: DecisionFreezeBundle) -> dict[str, object]:
    return {
        "schema_version": bundle.schema_version,
        "source_cutoff_open_time_ms": bundle.source_cutoff_open_time_ms,
        "signal_decision": bundle.signal_decision,
        "confluence": bundle.confluence,
        "selected_evidence": bundle.selected_evidence,
        "price_action": bundle.price_action,
        "harmonic": bundle.harmonic,
        "elliott": bundle.elliott,
        "candles": bundle.candles,
    }


def bundle_json(bundle: DecisionFreezeBundle) -> str:
    return canonical_json(bundle_payload(bundle))


def verify_bundle_identity(bundle: DecisionFreezeBundle) -> None:
    expected = sha256_text(bundle_json(bundle))
    if bundle.bundle_identity != expected:
        raise ValueError("decision freeze bundle identity mismatch")


def build_decision_freeze_bundle(
    *,
    decision: SignalDecision,
    confluence: ConfluenceAnalysisResult,
    price_action: PriceActionAnalysisResult,
    harmonic: HarmonicAnalysisResult,
    elliott: ElliottAnalysisResult,
    candles: Sequence[Candle],
) -> DecisionFreezeBundle:
    decision_context = (
        decision.exchange,
        decision.market_type,
        decision.symbol,
        decision.timeframe,
        decision.as_of_ms,
    )
    if _context_tuple(confluence) != decision_context:
        raise ValueError("confluence context does not match signal decision")
    for name, result in (
        ("price_action", price_action),
        ("harmonic", harmonic),
        ("elliott", elliott),
    ):
        if _context_tuple(result) != decision_context:
            raise ValueError(
                f"{name} context does not match signal decision"
            )

    selected = _selected_evidence(confluence)
    selected_ids = tuple(sorted(item.evidence_id for item in selected))
    if selected_ids != decision.selected_evidence_ids:
        raise ValueError(
            "selected confluence evidence does not match signal decision"
        )
    for item in selected:
        if _context_tuple(item) != decision_context:
            raise ValueError("selected evidence context mismatch")

    frozen_candles = _eligible_candles(decision, candles)
    draft = DecisionFreezeBundle(
        bundle_identity="0" * 64,
        schema_version=FREEZE_SCHEMA_VERSION,
        source_cutoff_open_time_ms=frozen_candles[-1].open_time_ms,
        signal_decision=decision,
        confluence=confluence,
        selected_evidence=selected,
        price_action=price_action,
        harmonic=harmonic,
        elliott=elliott,
        candles=frozen_candles,
    )
    identity = sha256_text(bundle_json(draft))
    bundle = DecisionFreezeBundle(
        bundle_identity=identity,
        schema_version=draft.schema_version,
        source_cutoff_open_time_ms=draft.source_cutoff_open_time_ms,
        signal_decision=draft.signal_decision,
        confluence=draft.confluence,
        selected_evidence=draft.selected_evidence,
        price_action=draft.price_action,
        harmonic=draft.harmonic,
        elliott=draft.elliott,
        candles=draft.candles,
    )
    verify_bundle_identity(bundle)
    return bundle
