from __future__ import annotations

from decimal import Decimal

from crypto_signal.confluence.models import EvidenceDirection
from crypto_signal.evaluation.calibration import CalibratedProbability
from crypto_signal.ledger.bundle import (
    DecisionFreezeBundle,
    verify_bundle_identity,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.outcomes.evaluator import verify_outcome_identity
from crypto_signal.outcomes.models import OutcomeEvaluation
from crypto_signal.signals.models import SignalDirection, SignalState

from crypto_signal.forecast.models import (
    ConditionalForecast,
    DecisionProof,
    DecisionProofAuthority,
    ForecastResolution,
    ForecastTriggerKind,
)


FORECAST_VERSION = "conditional-forecast-v1/1"
PROOF_VERSION = "decision-proof-v1/1"
RESOLUTION_VERSION = "forecast-resolution-v1/1"


def conditional_forecast_payload(
    forecast: ConditionalForecast,
) -> dict[str, object]:
    return {
        "forecast_version": forecast.forecast_version,
        "signal_freeze_identity": forecast.signal_freeze_identity,
        "bundle_identity": forecast.bundle_identity,
        "issued_at_ms": forecast.issued_at_ms,
        "signal_as_of_ms": forecast.signal_as_of_ms,
        "exchange": forecast.exchange,
        "market_type": forecast.market_type,
        "symbol": forecast.symbol,
        "timeframe": forecast.timeframe,
        "signal_state": forecast.signal_state,
        "direction": forecast.direction,
        "setup_type": forecast.setup_type,
        "trigger_kind": forecast.trigger_kind,
        "trigger_zone": forecast.trigger_zone,
        "target_label": forecast.target_label,
        "target_price": forecast.target_price,
        "invalidation_price": forecast.invalidation_price,
        "invalidation_trigger": forecast.invalidation_trigger,
        "horizon_bars": forecast.horizon_bars,
        "confluence_score": forecast.confluence_score,
        "confluence_semantic": forecast.confluence_semantic,
        "calibrated_probability": forecast.calibrated_probability,
        "probability_semantic": forecast.probability_semantic,
        "probability_model_version": forecast.probability_model_version,
        "probability_train_n": forecast.probability_train_n,
        "probability_holdout_n": forecast.probability_holdout_n,
        "probability_brier_score": forecast.probability_brier_score,
        "probability_brier_skill_score": forecast.probability_brier_skill_score,
        "probability_expected_calibration_error": (
            forecast.probability_expected_calibration_error
        ),
        "probability_trained_through_as_of_ms": (
            forecast.probability_trained_through_as_of_ms
        ),
        "probability_evaluated_through_as_of_ms": (
            forecast.probability_evaluated_through_as_of_ms
        ),
        "uncertainty_flags": forecast.uncertainty_flags,
    }


def verify_forecast_identity(forecast: ConditionalForecast) -> None:
    if forecast.forecast_identity != canonical_sha256(
        conditional_forecast_payload(forecast)
    ):
        raise ValueError("forecast identity mismatch")


def build_conditional_forecast(
    bundle: DecisionFreezeBundle,
    *,
    issued_at_ms: int,
    horizon_bars: int,
    target_label: str,
    calibrated_probability: CalibratedProbability | None = None,
    forecast_version: str = FORECAST_VERSION,
) -> ConditionalForecast:
    verify_bundle_identity(bundle)
    decision = bundle.signal_decision
    geometry = decision.geometry
    if decision.state not in {SignalState.WATCH, SignalState.ACTIVE}:
        raise ValueError("forecast requires WATCH or ACTIVE frozen signal")
    if geometry is None:
        raise ValueError("forecast requires frozen signal geometry")
    if geometry.source_evidence_id not in decision.selected_evidence_ids:
        raise ValueError("forecast geometry must reference selected frozen evidence")
    target = next(
        (item for item in geometry.targets if item.label == target_label),
        None,
    )
    if target is None:
        raise ValueError("forecast target must exist in frozen signal geometry")
    if issued_at_ms < decision.as_of_ms:
        raise ValueError("forecast issue time cannot precede signal as-of")
    if horizon_bars <= 0:
        raise ValueError("forecast horizon must be positive")

    probability_values: dict[str, object | None] = {
        "calibrated_probability": None,
        "probability_semantic": None,
        "probability_model_version": None,
        "probability_train_n": None,
        "probability_holdout_n": None,
        "probability_brier_score": None,
        "probability_brier_skill_score": None,
        "probability_expected_calibration_error": None,
        "probability_trained_through_as_of_ms": None,
        "probability_evaluated_through_as_of_ms": None,
    }
    if calibrated_probability is not None:
        if decision.state is not SignalState.ACTIVE:
            raise ValueError("calibrated probability may attach only to ACTIVE signal")
        scope = calibrated_probability.scope
        if (
            scope.symbol != decision.symbol
            or scope.timeframe != decision.timeframe
            or scope.direction is not decision.direction
            or scope.setup_type != decision.setup_type
            or scope.max_holding_bars != horizon_bars
        ):
            raise ValueError("calibrated probability scope does not match forecast")
        if calibrated_probability.trained_through_as_of_ms > decision.as_of_ms:
            raise ValueError("probability training cutoff postdates frozen signal")
        if calibrated_probability.evaluated_through_as_of_ms > decision.as_of_ms:
            raise ValueError("probability evaluation cutoff postdates frozen signal")
        probability_values = {
            "calibrated_probability": calibrated_probability.probability,
            "probability_semantic": calibrated_probability.semantic,
            "probability_model_version": calibrated_probability.model_version,
            "probability_train_n": calibrated_probability.train_n,
            "probability_holdout_n": calibrated_probability.holdout_n,
            "probability_brier_score": calibrated_probability.brier_score,
            "probability_brier_skill_score": calibrated_probability.brier_skill_score,
            "probability_expected_calibration_error": (
                calibrated_probability.expected_calibration_error
            ),
            "probability_trained_through_as_of_ms": (
                calibrated_probability.trained_through_as_of_ms
            ),
            "probability_evaluated_through_as_of_ms": (
                calibrated_probability.evaluated_through_as_of_ms
            ),
        }

    draft = ConditionalForecast(
        forecast_identity="0" * 64,
        forecast_version=forecast_version,
        signal_freeze_identity=decision.freeze_identity,
        bundle_identity=bundle.bundle_identity,
        issued_at_ms=issued_at_ms,
        signal_as_of_ms=decision.as_of_ms,
        exchange=decision.exchange,
        market_type=decision.market_type,
        symbol=decision.symbol,
        timeframe=decision.timeframe,
        signal_state=decision.state,
        direction=decision.direction,
        setup_type=decision.setup_type,
        trigger_kind=ForecastTriggerKind.GEOMETRY_ENTRY_ZONE,
        trigger_zone=geometry.entry_zone,
        target_label=target.label,
        target_price=target.target_price,
        invalidation_price=geometry.invalidation_price,
        invalidation_trigger=geometry.invalidation_trigger,
        horizon_bars=horizon_bars,
        confluence_score=decision.agreement.confluence_score,
        confluence_semantic=decision.agreement.score_semantic,
        uncertainty_flags=decision.uncertainty_flags,
        **probability_values,
    )
    forecast = ConditionalForecast(
        **{
            **draft.__dict__,
            "forecast_identity": canonical_sha256(
                conditional_forecast_payload(draft)
            ),
        }
    )
    verify_forecast_identity(forecast)
    return forecast


def decision_proof_payload(proof: DecisionProof) -> dict[str, object]:
    return {
        "proof_version": proof.proof_version,
        "forecast_identity": proof.forecast_identity,
        "signal_freeze_identity": proof.signal_freeze_identity,
        "bundle_identity": proof.bundle_identity,
        "created_at_ms": proof.created_at_ms,
        "authority": proof.authority,
        "supporting_evidence_ids": proof.supporting_evidence_ids,
        "opposing_evidence_ids": proof.opposing_evidence_ids,
        "ambiguous_evidence_ids": proof.ambiguous_evidence_ids,
        "contradiction_flags": proof.contradiction_flags,
        "uncertainty_flags": proof.uncertainty_flags,
        "simple_explanation_tr": proof.simple_explanation_tr,
        "technical_explanation": proof.technical_explanation,
        "snapshot_refs": proof.snapshot_refs,
    }


def verify_decision_proof_identity(proof: DecisionProof) -> None:
    if proof.proof_identity != canonical_sha256(decision_proof_payload(proof)):
        raise ValueError("Decision Proof identity mismatch")


def build_decision_proof(
    bundle: DecisionFreezeBundle,
    forecast: ConditionalForecast,
    *,
    authority: DecisionProofAuthority,
    created_at_ms: int,
    snapshot_refs: tuple[str, ...] = (),
    proof_version: str = PROOF_VERSION,
) -> DecisionProof:
    verify_bundle_identity(bundle)
    verify_forecast_identity(forecast)
    decision = bundle.signal_decision
    if forecast.signal_freeze_identity != decision.freeze_identity:
        raise ValueError("Decision Proof forecast/signal identity mismatch")
    if forecast.bundle_identity != bundle.bundle_identity:
        raise ValueError("Decision Proof forecast/bundle identity mismatch")
    if created_at_ms < forecast.issued_at_ms:
        raise ValueError("Decision Proof cannot predate forecast issuance")

    expected_direction = _evidence_direction(decision.direction)
    supporting: list[str] = []
    opposing: list[str] = []
    ambiguous: list[str] = []
    contradiction_flags: set[str] = set(bundle.confluence.flags)
    uncertainty_flags: set[str] = set(decision.uncertainty_flags)

    for evidence in bundle.selected_evidence:
        contradiction_flags.update(evidence.contradiction_flags)
        uncertainty_flags.update(evidence.ambiguity_flags)
        if evidence.direction is expected_direction:
            supporting.append(evidence.evidence_id)
        elif evidence.direction in {
            EvidenceDirection.BULLISH,
            EvidenceDirection.BEARISH,
        }:
            opposing.append(evidence.evidence_id)
        else:
            ambiguous.append(evidence.evidence_id)

    supporting_ids = tuple(sorted(supporting))
    opposing_ids = tuple(sorted(opposing))
    ambiguous_ids = tuple(sorted(ambiguous))
    contradiction_tuple = tuple(sorted(contradiction_flags))
    uncertainty_tuple = tuple(sorted(uncertainty_flags))

    simple = _simple_explanation(
        forecast,
        supporting_n=len(supporting_ids),
        opposing_n=len(opposing_ids),
        ambiguous_n=len(ambiguous_ids),
    )
    technical = _technical_explanation(
        forecast,
        supporting_ids=supporting_ids,
        opposing_ids=opposing_ids,
        ambiguous_ids=ambiguous_ids,
        contradiction_flags=contradiction_tuple,
        uncertainty_flags=uncertainty_tuple,
    )
    refs = tuple(dict.fromkeys((bundle.bundle_identity, *snapshot_refs)))

    draft = DecisionProof(
        proof_identity="0" * 64,
        proof_version=proof_version,
        forecast_identity=forecast.forecast_identity,
        signal_freeze_identity=forecast.signal_freeze_identity,
        bundle_identity=forecast.bundle_identity,
        created_at_ms=created_at_ms,
        authority=authority,
        supporting_evidence_ids=supporting_ids,
        opposing_evidence_ids=opposing_ids,
        ambiguous_evidence_ids=ambiguous_ids,
        contradiction_flags=contradiction_tuple,
        uncertainty_flags=uncertainty_tuple,
        simple_explanation_tr=simple,
        technical_explanation=technical,
        snapshot_refs=refs,
    )
    proof = DecisionProof(
        **{
            **draft.__dict__,
            "proof_identity": canonical_sha256(decision_proof_payload(draft)),
        }
    )
    verify_decision_proof_identity(proof)
    return proof


def forecast_resolution_payload(
    resolution: ForecastResolution,
) -> dict[str, object]:
    return {
        "resolution_version": resolution.resolution_version,
        "forecast_identity": resolution.forecast_identity,
        "signal_freeze_identity": resolution.signal_freeze_identity,
        "outcome_identity": resolution.outcome_identity,
        "evidence_class": resolution.evidence_class,
        "evaluated_as_of_ms": resolution.evaluated_as_of_ms,
        "resolution_status": resolution.resolution_status,
        "outcome_state": resolution.outcome_state,
        "horizon_bars": resolution.horizon_bars,
    }


def verify_forecast_resolution_identity(
    resolution: ForecastResolution,
) -> None:
    if resolution.resolution_identity != canonical_sha256(
        forecast_resolution_payload(resolution)
    ):
        raise ValueError("forecast resolution identity mismatch")


def build_forecast_resolution(
    forecast: ConditionalForecast,
    outcome: OutcomeEvaluation,
    *,
    resolution_version: str = RESOLUTION_VERSION,
) -> ForecastResolution:
    verify_forecast_identity(forecast)
    verify_outcome_identity(outcome)
    if outcome.signal_freeze_identity != forecast.signal_freeze_identity:
        raise ValueError("forecast/outcome signal identity mismatch")
    if outcome.max_holding_bars != forecast.horizon_bars:
        raise ValueError("forecast/outcome horizon mismatch")
    if outcome.evaluated_as_of_ms < forecast.signal_as_of_ms:
        raise ValueError("forecast outcome cannot predate frozen signal")

    draft = ForecastResolution(
        resolution_identity="0" * 64,
        resolution_version=resolution_version,
        forecast_identity=forecast.forecast_identity,
        signal_freeze_identity=forecast.signal_freeze_identity,
        outcome_identity=outcome.outcome_identity,
        evidence_class=outcome.evidence_class,
        evaluated_as_of_ms=outcome.evaluated_as_of_ms,
        resolution_status=outcome.resolution_status,
        outcome_state=outcome.outcome_state,
        horizon_bars=outcome.max_holding_bars,
    )
    resolution = ForecastResolution(
        **{
            **draft.__dict__,
            "resolution_identity": canonical_sha256(
                forecast_resolution_payload(draft)
            ),
        }
    )
    verify_forecast_resolution_identity(resolution)
    return resolution


def _evidence_direction(direction: SignalDirection) -> EvidenceDirection:
    if direction is SignalDirection.BULLISH:
        return EvidenceDirection.BULLISH
    if direction is SignalDirection.BEARISH:
        return EvidenceDirection.BEARISH
    raise ValueError("Decision Proof requires directional signal")


def _simple_explanation(
    forecast: ConditionalForecast,
    *,
    supporting_n: int,
    opposing_n: int,
    ambiguous_n: int,
) -> str:
    direction = "yukarı" if forecast.direction is SignalDirection.BULLISH else "aşağı"
    state = (
        "aktif koşullu senaryo"
        if forecast.signal_state is SignalState.ACTIVE
        else "izlenen koşullu senaryo"
    )
    probability = (
        " Kalibre edilmiş olasılık henüz yok."
        if forecast.calibrated_probability is None
        else (
            " Kalibre edilmiş hedef-başarı olasılığı "
            f"%{_percent_text(forecast.calibrated_probability)}."
        )
    )
    return (
        f"{forecast.symbol} {forecast.timeframe} için {direction} yönlü {state}. "
        f"{supporting_n} kanıt destekliyor, {opposing_n} kanıt karşı çıkıyor, "
        f"{ambiguous_n} kanıt belirsiz. "
        f"Tetik bölgesi {_decimal_text(forecast.trigger_zone.low)}–"
        f"{_decimal_text(forecast.trigger_zone.high)}; "
        f"hedef {forecast.target_label}={_decimal_text(forecast.target_price)}; "
        f"geçersizlik {_decimal_text(forecast.invalidation_price)}. "
        f"Uyum puanı {_decimal_text(forecast.confluence_score)}/100 ve olasılık değildir."
        f"{probability}"
    )


def _technical_explanation(
    forecast: ConditionalForecast,
    *,
    supporting_ids: tuple[str, ...],
    opposing_ids: tuple[str, ...],
    ambiguous_ids: tuple[str, ...],
    contradiction_flags: tuple[str, ...],
    uncertainty_flags: tuple[str, ...],
) -> str:
    probability = (
        "probability=NOT_CALIBRATED"
        if forecast.calibrated_probability is None
        else (
            f"probability={_decimal_text(forecast.calibrated_probability)} "
            f"semantic={forecast.probability_semantic.value} "
            f"model={forecast.probability_model_version}"
        )
    )
    return (
        f"signal={forecast.signal_state.value}/{forecast.direction.value}; "
        f"confluence={_decimal_text(forecast.confluence_score)} "
        f"semantic={forecast.confluence_semantic.value}; "
        f"trigger={forecast.trigger_kind.value}:"
        f"{_decimal_text(forecast.trigger_zone.low)}-"
        f"{_decimal_text(forecast.trigger_zone.high)}; "
        f"target={forecast.target_label}:{_decimal_text(forecast.target_price)}; "
        f"invalidation={forecast.invalidation_trigger.value}:"
        f"{_decimal_text(forecast.invalidation_price)}; "
        f"horizon_bars={forecast.horizon_bars}; "
        f"support={','.join(supporting_ids) or '-'}; "
        f"oppose={','.join(opposing_ids) or '-'}; "
        f"ambiguous={','.join(ambiguous_ids) or '-'}; "
        f"contradictions={','.join(contradiction_flags) or '-'}; "
        f"uncertainty={','.join(uncertainty_flags) or '-'}; "
        f"{probability}"
    )


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _percent_text(probability: Decimal) -> str:
    return format(probability * Decimal(100), ".2f")
