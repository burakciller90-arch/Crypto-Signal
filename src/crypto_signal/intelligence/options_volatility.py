from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.options import (
    OptionContractQuote,
    OptionSurfaceObservation,
    OptionType,
)
from crypto_signal.ledger.serialization import canonical_sha256

OPTIONS_VOLATILITY_ENGINE_VERSION = "options-volatility-v1/1"
OPTIONS_VOLATILITY_FREEZE_SCHEMA_VERSION = "options-volatility-freeze-v1/1"


class OptionsVolatilityStatus(StrEnum):
    MEASURED = "measured"
    PARTIAL = "partial"
    STALE = "stale"
    NOT_EVALUABLE = "not_evaluable"


class OptionsTermStructureShape(StrEnum):
    HIGHER_LATER_IV = "higher_later_iv"
    LOWER_LATER_IV = "lower_later_iv"
    FLAT = "flat"
    UNAVAILABLE = "unavailable"


class OptionsVolatilityIndexStatus(StrEnum):
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class OptionsVolatilityConfig:
    max_surface_age_ms: int = 120_000
    atm_target_abs_delta: Decimal = Decimal("0.50")
    atm_max_delta_distance: Decimal = Decimal("0.15")
    rr_target_abs_delta: Decimal = Decimal("0.25")
    rr_max_delta_distance: Decimal = Decimal("0.10")
    term_flat_tolerance: Decimal = Decimal("0.005")
    minimum_term_expiries: int = 2

    def __post_init__(self) -> None:
        if self.max_surface_age_ms <= 0:
            raise ValueError("options max surface age must be positive")
        if self.minimum_term_expiries < 2:
            raise ValueError("options term structure requires at least two expiries")
        for label, value in (
            ("atm_target_abs_delta", self.atm_target_abs_delta),
            ("atm_max_delta_distance", self.atm_max_delta_distance),
            ("rr_target_abs_delta", self.rr_target_abs_delta),
            ("rr_max_delta_distance", self.rr_max_delta_distance),
            ("term_flat_tolerance", self.term_flat_tolerance),
        ):
            if value.is_nan() or value.is_infinite() or value < Decimal(0):
                raise ValueError(f"{label} must be finite and non-negative")
        if not Decimal(0) < self.atm_target_abs_delta <= Decimal(1):
            raise ValueError("ATM delta target must be inside (0,1]")
        if not Decimal(0) < self.rr_target_abs_delta <= Decimal(1):
            raise ValueError("risk-reversal delta target must be inside (0,1]")
        if self.atm_max_delta_distance > Decimal(1):
            raise ValueError("ATM delta tolerance cannot exceed one")
        if self.rr_max_delta_distance > Decimal(1):
            raise ValueError("risk-reversal delta tolerance cannot exceed one")


DEFAULT_OPTIONS_VOLATILITY_CONFIG = OptionsVolatilityConfig()


@dataclass(frozen=True, slots=True)
class OptionsExpiryMetrics:
    expiry_at_ms: int
    contract_count: int
    atm_call_iv: Decimal | None
    atm_put_iv: Decimal | None
    atm_iv: Decimal | None
    call_25d_iv: Decimal | None
    put_25d_iv: Decimal | None
    risk_reversal_25d: Decimal | None
    call_open_interest: Decimal | None
    put_open_interest: Decimal | None
    call_volume_24h: Decimal | None
    put_volume_24h: Decimal | None

    def __post_init__(self) -> None:
        if self.expiry_at_ms < 0 or self.contract_count <= 0:
            raise ValueError("invalid options expiry metric bounds")
        for label, value in (
            ("atm_call_iv", self.atm_call_iv),
            ("atm_put_iv", self.atm_put_iv),
            ("atm_iv", self.atm_iv),
            ("call_25d_iv", self.call_25d_iv),
            ("put_25d_iv", self.put_25d_iv),
            ("call_open_interest", self.call_open_interest),
            ("put_open_interest", self.put_open_interest),
            ("call_volume_24h", self.call_volume_24h),
            ("put_volume_24h", self.put_volume_24h),
        ):
            _require_non_negative_optional(value, label)
        _require_finite_optional(
            self.risk_reversal_25d,
            "risk_reversal_25d",
        )


@dataclass(frozen=True, slots=True)
class OptionsVolatilityMetrics:
    expiries: tuple[OptionsExpiryMetrics, ...]
    front_atm_iv: Decimal | None
    next_atm_iv: Decimal | None
    term_structure_iv_change: Decimal | None
    term_structure_shape: OptionsTermStructureShape
    put_call_open_interest_ratio: Decimal | None
    put_call_volume_ratio: Decimal | None
    top_expiry_at_ms: int | None
    top_expiry_open_interest_share: Decimal | None
    total_open_interest: Decimal | None
    total_volume_24h: Decimal | None
    measured_atm_expiry_count: int
    measured_rr_expiry_count: int
    volatility_index_status: OptionsVolatilityIndexStatus

    def __post_init__(self) -> None:
        if not self.expiries:
            raise ValueError("options volatility metrics require expiry observations")
        if tuple(sorted(x.expiry_at_ms for x in self.expiries)) != tuple(
            x.expiry_at_ms for x in self.expiries
        ):
            raise ValueError("options expiry metrics must be canonical")
        if self.measured_atm_expiry_count < 0 or self.measured_rr_expiry_count < 0:
            raise ValueError("options measured metric counts cannot be negative")
        if self.measured_atm_expiry_count != sum(
            item.atm_iv is not None for item in self.expiries
        ):
            raise ValueError("ATM expiry metric count mismatch")
        if self.measured_rr_expiry_count != sum(
            item.risk_reversal_25d is not None for item in self.expiries
        ):
            raise ValueError("risk-reversal expiry metric count mismatch")
        for label, value in (
            ("front_atm_iv", self.front_atm_iv),
            ("next_atm_iv", self.next_atm_iv),
            ("total_open_interest", self.total_open_interest),
            ("total_volume_24h", self.total_volume_24h),
        ):
            _require_non_negative_optional(value, label)
        for label, value in (
            ("term_structure_iv_change", self.term_structure_iv_change),
            ("put_call_open_interest_ratio", self.put_call_open_interest_ratio),
            ("put_call_volume_ratio", self.put_call_volume_ratio),
            (
                "top_expiry_open_interest_share",
                self.top_expiry_open_interest_share,
            ),
        ):
            _require_finite_optional(value, label)
        for value in (
            self.put_call_open_interest_ratio,
            self.put_call_volume_ratio,
        ):
            if value is not None and value < Decimal(0):
                raise ValueError("put/call ratios cannot be negative")
        if (
            self.top_expiry_open_interest_share is not None
            and not Decimal(0)
            <= self.top_expiry_open_interest_share
            <= Decimal(1)
        ):
            raise ValueError("top expiry OI share must be inside [0,1]")
        if (
            self.top_expiry_at_ms is None
        ) != (
            self.top_expiry_open_interest_share is None
        ):
            raise ValueError("top expiry identity/share must appear together")
        if (
            self.term_structure_iv_change is None
            and self.term_structure_shape
            is not OptionsTermStructureShape.UNAVAILABLE
        ):
            raise ValueError("term structure shape requires measured change")
        if (
            self.term_structure_iv_change is not None
            and self.term_structure_shape
            is OptionsTermStructureShape.UNAVAILABLE
        ):
            raise ValueError("measured term change requires shape")


@dataclass(frozen=True, slots=True)
class OptionsVolatilityAnalysis:
    evidence_identity: str
    engine_version: str
    exchange: str
    base_coin: str
    as_of_ms: int
    observed_at_ms: int
    surface_identity: str
    instrument_metadata_identity: str
    surface_age_ms: int
    consumed_contract_count: int
    status: OptionsVolatilityStatus
    metrics: OptionsVolatilityMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "options volatility evidence identity")
        _require_sha256(self.surface_identity, "options surface identity")
        _require_sha256(
            self.instrument_metadata_identity,
            "options instrument metadata identity",
        )
        if self.engine_version != OPTIONS_VOLATILITY_ENGINE_VERSION:
            raise ValueError("unsupported options volatility engine version")
        if self.base_coin not in {"BTC", "ETH"}:
            raise ValueError("options volatility base coin must be BTC or ETH")
        if not 0 <= self.observed_at_ms <= self.as_of_ms:
            raise ValueError("options volatility observed_at outside PIT boundary")
        if self.surface_age_ms < 0:
            raise ValueError("options volatility surface age cannot be negative")
        if self.consumed_contract_count <= 0:
            raise ValueError("options volatility requires consumed contracts")
        if tuple(sorted(set(self.uncertainty_flags))) != self.uncertainty_flags:
            raise ValueError("options uncertainty flags must be canonical")
        if self.status in {
            OptionsVolatilityStatus.STALE,
            OptionsVolatilityStatus.NOT_EVALUABLE,
        }:
            if self.metrics is not None:
                raise ValueError("non-evaluable options state cannot expose metrics")
            if not self.uncertainty_flags:
                raise ValueError("non-evaluable options state requires uncertainty")
        elif self.metrics is None:
            raise ValueError("measured/partial options state requires metrics")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("options volatility evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class OptionsVolatilityEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: OptionsVolatilityAnalysis
    surface: OptionSurfaceObservation

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "options volatility freeze identity")
        if self.schema_version != OPTIONS_VOLATILITY_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported options volatility freeze schema")
        if self.surface.surface_identity != self.analysis.surface_identity:
            raise ValueError("options volatility freeze surface mismatch")
        if (
            self.surface.instrument_metadata_identity
            != self.analysis.instrument_metadata_identity
        ):
            raise ValueError("options volatility freeze metadata mismatch")
        if max(
            self.surface.source_timestamp_ms,
            self.surface.observed_at_ms,
            self.surface.ingested_at_ms,
        ) > self.analysis.as_of_ms:
            raise ValueError("options volatility freeze contains future evidence")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("options volatility freeze identity mismatch")


def analyze_options_volatility(
    surface: OptionSurfaceObservation,
    *,
    as_of_ms: int,
    config: OptionsVolatilityConfig = DEFAULT_OPTIONS_VOLATILITY_CONFIG,
) -> OptionsVolatilityAnalysis:
    _require_surface_pit(surface, as_of_ms=as_of_ms)
    surface_age_ms = as_of_ms - surface.source_timestamp_ms
    base_flags = _boundary_flags()

    if surface_age_ms > config.max_surface_age_ms:
        return _non_evaluable(
            surface,
            as_of_ms=as_of_ms,
            surface_age_ms=surface_age_ms,
            status=OptionsVolatilityStatus.STALE,
            flags=(*base_flags, "stale_options_surface"),
        )

    active = tuple(
        item for item in surface.contracts if item.expiry_at_ms > as_of_ms
    )
    if not active:
        return _non_evaluable(
            surface,
            as_of_ms=as_of_ms,
            surface_age_ms=surface_age_ms,
            status=OptionsVolatilityStatus.NOT_EVALUABLE,
            flags=(*base_flags, "no_active_option_contracts"),
        )

    flags: list[str] = list(base_flags)
    if len(active) != len(surface.contracts):
        flags.append("expired_option_contracts_excluded")

    expiries = _expiry_metrics(active, config=config)
    atm_expiries = tuple(x for x in expiries if x.atm_iv is not None)
    rr_expiries = tuple(
        x for x in expiries if x.risk_reversal_25d is not None
    )

    if not atm_expiries and not rr_expiries:
        return _non_evaluable(
            surface,
            as_of_ms=as_of_ms,
            surface_age_ms=surface_age_ms,
            status=OptionsVolatilityStatus.NOT_EVALUABLE,
            flags=(
                *flags,
                "no_evaluable_implied_volatility_structure",
            ),
        )

    if len(atm_expiries) < config.minimum_term_expiries:
        flags.append("atm_term_structure_insufficient_expiries")
    if not rr_expiries:
        flags.append("risk_reversal_25d_unavailable")

    if any(
        (item.atm_call_iv is None) != (item.atm_put_iv is None)
        for item in expiries
        if item.atm_iv is not None
    ):
        flags.append("atm_iv_one_sided_for_some_expiries")

    all_oi_complete = all(item.open_interest is not None for item in active)
    all_volume_complete = all(item.volume_24h is not None for item in active)
    if not all_oi_complete:
        flags.append("open_interest_coverage_incomplete")
    if not all_volume_complete:
        flags.append("volume_24h_coverage_incomplete")

    total_oi = _complete_sum(active, "open_interest")
    total_volume = _complete_sum(active, "volume_24h")
    call_oi = _complete_side_sum(
        active,
        side=OptionType.CALL,
        field="open_interest",
    )
    put_oi = _complete_side_sum(
        active,
        side=OptionType.PUT,
        field="open_interest",
    )
    call_volume = _complete_side_sum(
        active,
        side=OptionType.CALL,
        field="volume_24h",
    )
    put_volume = _complete_side_sum(
        active,
        side=OptionType.PUT,
        field="volume_24h",
    )
    put_call_oi_ratio = _ratio(put_oi, call_oi)
    put_call_volume_ratio = _ratio(put_volume, call_volume)
    if put_call_oi_ratio is None:
        flags.append("put_call_open_interest_ratio_unavailable")
    if put_call_volume_ratio is None:
        flags.append("put_call_volume_ratio_unavailable")

    top_expiry_at_ms: int | None = None
    top_expiry_share: Decimal | None = None
    if total_oi is not None and total_oi > Decimal(0):
        expiry_oi = tuple(
            (item.expiry_at_ms, _expiry_total_oi(item))
            for item in expiries
        )
        if all(value is not None for _, value in expiry_oi):
            measured_expiry_oi = tuple(
                (expiry, value)
                for expiry, value in expiry_oi
                if value is not None
            )
            top_expiry_at_ms, top_value = max(
                measured_expiry_oi,
                key=lambda item: (item[1], -item[0]),
            )
            top_expiry_share = top_value / total_oi
    if top_expiry_share is None:
        flags.append("top_expiry_open_interest_share_unavailable")

    front_atm_iv = (
        None if not atm_expiries else atm_expiries[0].atm_iv
    )
    next_atm_iv = (
        None if len(atm_expiries) < 2 else atm_expiries[1].atm_iv
    )
    term_change = (
        None
        if front_atm_iv is None or next_atm_iv is None
        else next_atm_iv - front_atm_iv
    )
    term_shape = _term_shape(term_change, config=config)

    metrics = OptionsVolatilityMetrics(
        expiries=expiries,
        front_atm_iv=front_atm_iv,
        next_atm_iv=next_atm_iv,
        term_structure_iv_change=term_change,
        term_structure_shape=term_shape,
        put_call_open_interest_ratio=put_call_oi_ratio,
        put_call_volume_ratio=put_call_volume_ratio,
        top_expiry_at_ms=top_expiry_at_ms,
        top_expiry_open_interest_share=top_expiry_share,
        total_open_interest=total_oi,
        total_volume_24h=total_volume,
        measured_atm_expiry_count=len(atm_expiries),
        measured_rr_expiry_count=len(rr_expiries),
        volatility_index_status=OptionsVolatilityIndexStatus.UNAVAILABLE,
    )
    status = (
        OptionsVolatilityStatus.MEASURED
        if (
            len(atm_expiries) >= config.minimum_term_expiries
            and bool(rr_expiries)
            and all_oi_complete
            and all_volume_complete
            and put_call_oi_ratio is not None
            and put_call_volume_ratio is not None
            and top_expiry_share is not None
        )
        else OptionsVolatilityStatus.PARTIAL
    )
    canonical_flags = tuple(sorted(set(flags)))
    payload = _analysis_values(
        surface=surface,
        as_of_ms=as_of_ms,
        surface_age_ms=surface_age_ms,
        status=status,
        metrics=metrics,
        flags=canonical_flags,
    )
    return OptionsVolatilityAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=OPTIONS_VOLATILITY_ENGINE_VERSION,
        exchange=surface.exchange.value,
        base_coin=surface.base_coin,
        as_of_ms=as_of_ms,
        observed_at_ms=surface.ingested_at_ms,
        surface_identity=surface.surface_identity,
        instrument_metadata_identity=surface.instrument_metadata_identity,
        surface_age_ms=surface_age_ms,
        consumed_contract_count=len(surface.contracts),
        status=status,
        metrics=metrics,
        uncertainty_flags=canonical_flags,
    )


def build_options_volatility_evidence_freeze(
    surface: OptionSurfaceObservation,
    *,
    as_of_ms: int,
    config: OptionsVolatilityConfig = DEFAULT_OPTIONS_VOLATILITY_CONFIG,
) -> OptionsVolatilityEvidenceFreeze:
    analysis = analyze_options_volatility(
        surface,
        as_of_ms=as_of_ms,
        config=config,
    )
    payload = {
        "analysis": analysis,
        "schema_version": OPTIONS_VOLATILITY_FREEZE_SCHEMA_VERSION,
        "surface": surface,
    }
    return OptionsVolatilityEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=OPTIONS_VOLATILITY_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        surface=surface,
    )


def _expiry_metrics(
    contracts: tuple[OptionContractQuote, ...],
    *,
    config: OptionsVolatilityConfig,
) -> tuple[OptionsExpiryMetrics, ...]:
    expiry_values = tuple(sorted({item.expiry_at_ms for item in contracts}))
    result: list[OptionsExpiryMetrics] = []
    for expiry_at_ms in expiry_values:
        window = tuple(
            item for item in contracts if item.expiry_at_ms == expiry_at_ms
        )
        atm_call = _nearest_iv(
            window,
            side=OptionType.CALL,
            target_delta=config.atm_target_abs_delta,
            tolerance=config.atm_max_delta_distance,
        )
        atm_put = _nearest_iv(
            window,
            side=OptionType.PUT,
            target_delta=-config.atm_target_abs_delta,
            tolerance=config.atm_max_delta_distance,
        )
        atm_iv = _mean_available(atm_call, atm_put)

        call_25d = _nearest_iv(
            window,
            side=OptionType.CALL,
            target_delta=config.rr_target_abs_delta,
            tolerance=config.rr_max_delta_distance,
        )
        put_25d = _nearest_iv(
            window,
            side=OptionType.PUT,
            target_delta=-config.rr_target_abs_delta,
            tolerance=config.rr_max_delta_distance,
        )
        rr = (
            None
            if call_25d is None or put_25d is None
            else call_25d - put_25d
        )
        result.append(
            OptionsExpiryMetrics(
                expiry_at_ms=expiry_at_ms,
                contract_count=len(window),
                atm_call_iv=atm_call,
                atm_put_iv=atm_put,
                atm_iv=atm_iv,
                call_25d_iv=call_25d,
                put_25d_iv=put_25d,
                risk_reversal_25d=rr,
                call_open_interest=_complete_side_sum(
                    window,
                    side=OptionType.CALL,
                    field="open_interest",
                ),
                put_open_interest=_complete_side_sum(
                    window,
                    side=OptionType.PUT,
                    field="open_interest",
                ),
                call_volume_24h=_complete_side_sum(
                    window,
                    side=OptionType.CALL,
                    field="volume_24h",
                ),
                put_volume_24h=_complete_side_sum(
                    window,
                    side=OptionType.PUT,
                    field="volume_24h",
                ),
            )
        )
    return tuple(result)


def _nearest_iv(
    contracts: tuple[OptionContractQuote, ...],
    *,
    side: OptionType,
    target_delta: Decimal,
    tolerance: Decimal,
) -> Decimal | None:
    candidates = tuple(
        item
        for item in contracts
        if (
            item.option_type is side
            and item.mark_iv is not None
            and item.delta is not None
            and abs(item.delta - target_delta) <= tolerance
        )
    )
    if not candidates:
        return None
    selected = min(
        candidates,
        key=lambda item: (
            abs(item.delta - target_delta)
            if item.delta is not None
            else Decimal(2),
            item.symbol,
            item.quote_identity,
        ),
    )
    return selected.mark_iv


def _mean_available(
    first: Decimal | None,
    second: Decimal | None,
) -> Decimal | None:
    if first is None:
        return second
    if second is None:
        return first
    return (first + second) / Decimal(2)


def _complete_sum(
    contracts: tuple[OptionContractQuote, ...],
    field: str,
) -> Decimal | None:
    values = tuple(getattr(item, field) for item in contracts)
    if not values or any(value is None for value in values):
        return None
    return sum(
        (value for value in values if value is not None),
        start=Decimal(0),
    )


def _complete_side_sum(
    contracts: tuple[OptionContractQuote, ...],
    *,
    side: OptionType,
    field: str,
) -> Decimal | None:
    selected = tuple(item for item in contracts if item.option_type is side)
    if not selected:
        return None
    return _complete_sum(selected, field)


def _ratio(
    numerator: Decimal | None,
    denominator: Decimal | None,
) -> Decimal | None:
    if numerator is None or denominator is None or denominator == Decimal(0):
        return None
    return numerator / denominator


def _expiry_total_oi(item: OptionsExpiryMetrics) -> Decimal | None:
    if item.call_open_interest is None or item.put_open_interest is None:
        return None
    return item.call_open_interest + item.put_open_interest


def _term_shape(
    change: Decimal | None,
    *,
    config: OptionsVolatilityConfig,
) -> OptionsTermStructureShape:
    if change is None:
        return OptionsTermStructureShape.UNAVAILABLE
    if change > config.term_flat_tolerance:
        return OptionsTermStructureShape.HIGHER_LATER_IV
    if change < -config.term_flat_tolerance:
        return OptionsTermStructureShape.LOWER_LATER_IV
    return OptionsTermStructureShape.FLAT


def _non_evaluable(
    surface: OptionSurfaceObservation,
    *,
    as_of_ms: int,
    surface_age_ms: int,
    status: OptionsVolatilityStatus,
    flags: tuple[str, ...],
) -> OptionsVolatilityAnalysis:
    canonical_flags = tuple(sorted(set(flags)))
    payload = _analysis_values(
        surface=surface,
        as_of_ms=as_of_ms,
        surface_age_ms=surface_age_ms,
        status=status,
        metrics=None,
        flags=canonical_flags,
    )
    return OptionsVolatilityAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=OPTIONS_VOLATILITY_ENGINE_VERSION,
        exchange=surface.exchange.value,
        base_coin=surface.base_coin,
        as_of_ms=as_of_ms,
        observed_at_ms=surface.ingested_at_ms,
        surface_identity=surface.surface_identity,
        instrument_metadata_identity=surface.instrument_metadata_identity,
        surface_age_ms=surface_age_ms,
        consumed_contract_count=len(surface.contracts),
        status=status,
        metrics=None,
        uncertainty_flags=canonical_flags,
    )


def _analysis_values(
    *,
    surface: OptionSurfaceObservation,
    as_of_ms: int,
    surface_age_ms: int,
    status: OptionsVolatilityStatus,
    metrics: OptionsVolatilityMetrics | None,
    flags: tuple[str, ...],
) -> dict[str, object]:
    return {
        "as_of_ms": as_of_ms,
        "base_coin": surface.base_coin,
        "consumed_contract_count": len(surface.contracts),
        "engine_version": OPTIONS_VOLATILITY_ENGINE_VERSION,
        "exchange": surface.exchange.value,
        "instrument_metadata_identity": surface.instrument_metadata_identity,
        "metrics": metrics,
        "observed_at_ms": surface.ingested_at_ms,
        "status": status,
        "surface_age_ms": surface_age_ms,
        "surface_identity": surface.surface_identity,
        "uncertainty_flags": flags,
    }


def _analysis_payload(
    analysis: OptionsVolatilityAnalysis,
) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "base_coin": analysis.base_coin,
        "consumed_contract_count": analysis.consumed_contract_count,
        "engine_version": analysis.engine_version,
        "exchange": analysis.exchange,
        "instrument_metadata_identity": analysis.instrument_metadata_identity,
        "metrics": analysis.metrics,
        "observed_at_ms": analysis.observed_at_ms,
        "status": analysis.status,
        "surface_age_ms": analysis.surface_age_ms,
        "surface_identity": analysis.surface_identity,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze_payload(
    freeze: OptionsVolatilityEvidenceFreeze,
) -> dict[str, object]:
    return {
        "analysis": freeze.analysis,
        "schema_version": freeze.schema_version,
        "surface": freeze.surface,
    }


def _require_surface_pit(
    surface: OptionSurfaceObservation,
    *,
    as_of_ms: int,
) -> None:
    if as_of_ms < 0:
        raise ValueError("options volatility as_of_ms must be non-negative")
    if surface.base_coin not in {"BTC", "ETH"}:
        raise ValueError("RDP6 options volatility supports BTC and ETH only")
    if max(
        surface.source_timestamp_ms,
        surface.observed_at_ms,
        surface.ingested_at_ms,
    ) > as_of_ms:
        raise ValueError("options volatility surface is future evidence")


def _boundary_flags() -> tuple[str, ...]:
    return (
        "dealer_gamma_position_not_inferred",
        "max_pain_not_estimated",
        "options_metrics_are_descriptive_not_directional",
        "volatility_index_unavailable_without_explicit_provider_source",
    )


def _require_non_negative_optional(
    value: Decimal | None,
    label: str,
) -> None:
    _require_finite_optional(value, label)
    if value is not None and value < Decimal(0):
        raise ValueError(f"{label} cannot be negative")


def _require_finite_optional(
    value: Decimal | None,
    label: str,
) -> None:
    if value is not None and (value.is_nan() or value.is_infinite()):
        raise ValueError(f"{label} must be finite")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
