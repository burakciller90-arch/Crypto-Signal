from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.provider_divergence import (
    ProviderDivergenceSnapshot,
    ProviderGridState,
)
from crypto_signal.ledger.serialization import canonical_sha256

CROSS_VENUE_QUALITY_ENGINE_VERSION = "cross-venue-quality-v1/1"
REAL_CAPITAL = 0


class CrossVenueScope(StrEnum):
    BROAD_TWO_VENUE = "broad_two_venue"
    VENUE_LOCAL = "venue_local"
    UNAVAILABLE = "unavailable"


class CrossVenueQualityState(StrEnum):
    TWO_VENUE_CONFIRMED = "two_venue_confirmed"
    MATERIAL_PRICE_DISAGREEMENT = "material_price_disagreement"
    SINGLE_VENUE_ONLY = "single_venue_only"
    STALE_PROVIDER_SET = "stale_provider_set"
    NO_COMPARABLE_OVERLAP = "no_comparable_overlap"
    LATEST_GRID_MISMATCH = "latest_grid_mismatch"
    PROVIDERS_UNAVAILABLE = "providers_unavailable"


@dataclass(frozen=True, slots=True)
class CrossVenueQualityConfig:
    material_spread_bps: Decimal = Decimal("40")

    def __post_init__(self) -> None:
        if (
            self.material_spread_bps.is_nan()
            or self.material_spread_bps.is_infinite()
            or self.material_spread_bps <= Decimal(0)
        ):
            raise ValueError("cross-venue material spread must be finite and positive")


@dataclass(frozen=True, slots=True)
class CrossVenueQualityAssessment:
    assessment_identity: str
    engine_version: str
    provider_divergence_identity: str
    symbol: str
    timeframe: str
    as_of_ms: int
    scope: CrossVenueScope
    state: CrossVenueQualityState
    material_spread_bps: Decimal
    latest_absolute_spread_bps: Decimal | None
    median_absolute_spread_bps: Decimal | None
    source_evidence_identities: tuple[str, ...]
    material_conflict_identities: tuple[str, ...]
    uncertainty_flags: tuple[str, ...]
    directional_authority: bool = False
    score_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.assessment_identity, "cross-venue assessment identity")
        _require_sha256(
            self.provider_divergence_identity,
            "provider divergence identity",
        )
        if self.engine_version != CROSS_VENUE_QUALITY_ENGINE_VERSION:
            raise ValueError("unsupported cross-venue quality engine")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("cross-venue symbol must be uppercase")
        if not self.timeframe.strip():
            raise ValueError("cross-venue timeframe must be non-empty")
        if self.as_of_ms < 0:
            raise ValueError("cross-venue as-of cannot be negative")
        if (
            self.material_spread_bps.is_nan()
            or self.material_spread_bps.is_infinite()
            or self.material_spread_bps <= Decimal(0)
        ):
            raise ValueError("cross-venue material spread must be positive")
        for value, label in (
            (self.latest_absolute_spread_bps, "latest spread"),
            (self.median_absolute_spread_bps, "median spread"),
        ):
            if value is not None and (
                value.is_nan() or value.is_infinite() or value < Decimal(0)
            ):
                raise ValueError(f"cross-venue {label} must be finite and non-negative")
        _require_identity_tuple(
            self.source_evidence_identities,
            "cross-venue source evidence",
        )
        _require_identity_tuple(
            self.material_conflict_identities,
            "cross-venue conflict identity",
        )
        if self.uncertainty_flags != tuple(sorted(set(self.uncertainty_flags))):
            raise ValueError("cross-venue uncertainty flags must be canonical")
        if (
            self.directional_authority
            or self.score_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("cross-venue quality cannot grant authority")
        if (
            self.state is CrossVenueQualityState.MATERIAL_PRICE_DISAGREEMENT
            and not self.material_conflict_identities
        ):
            raise ValueError("material venue disagreement requires conflict identity")
        if (
            self.state is not CrossVenueQualityState.MATERIAL_PRICE_DISAGREEMENT
            and self.material_conflict_identities
        ):
            raise ValueError("non-conflict cross-venue state cannot carry conflict identity")
        if (
            self.scope is CrossVenueScope.BROAD_TWO_VENUE
            and self.state is not CrossVenueQualityState.TWO_VENUE_CONFIRMED
        ):
            raise ValueError("broad cross-venue scope requires two-venue confirmation")
        if self.assessment_identity != canonical_sha256(_assessment_payload(self)):
            raise ValueError("cross-venue assessment identity mismatch")


def assess_cross_venue_quality(
    snapshot: ProviderDivergenceSnapshot,
    *,
    config: CrossVenueQualityConfig = CrossVenueQualityConfig(),
) -> CrossVenueQualityAssessment:
    source_ids = tuple(
        sorted(
            set(snapshot.left_source_evidence_identities)
            | set(snapshot.right_source_evidence_identities)
        )
    )
    flags: set[str] = set()

    left_available = snapshot.left_quality.available
    right_available = snapshot.right_quality.available
    left_stale = snapshot.left_quality.stale
    right_stale = snapshot.right_quality.stale

    if not left_available and not right_available:
        scope = CrossVenueScope.UNAVAILABLE
        state = CrossVenueQualityState.PROVIDERS_UNAVAILABLE
        flags.add("both_providers_unavailable")
    elif left_stale and right_stale:
        scope = CrossVenueScope.UNAVAILABLE
        state = CrossVenueQualityState.STALE_PROVIDER_SET
        flags.add("both_providers_stale")
    elif not left_available or not right_available:
        scope = CrossVenueScope.VENUE_LOCAL
        state = CrossVenueQualityState.SINGLE_VENUE_ONLY
        flags.add("single_provider_only")
    elif left_stale or right_stale:
        scope = CrossVenueScope.VENUE_LOCAL
        state = CrossVenueQualityState.STALE_PROVIDER_SET
        flags.add("peer_provider_stale")
    elif snapshot.grid_state is ProviderGridState.NO_OVERLAP:
        scope = CrossVenueScope.VENUE_LOCAL
        state = CrossVenueQualityState.NO_COMPARABLE_OVERLAP
        flags.add("no_comparable_provider_grid")
    elif (
        snapshot.latest_overlap_open_time_ms
        != snapshot.left_quality.latest_open_time_ms
        or snapshot.latest_overlap_open_time_ms
        != snapshot.right_quality.latest_open_time_ms
    ):
        scope = CrossVenueScope.VENUE_LOCAL
        state = CrossVenueQualityState.LATEST_GRID_MISMATCH
        flags.add("latest_provider_grid_mismatch")
    else:
        latest_abs = (
            None
            if snapshot.latest_close_spread_bps is None
            else abs(snapshot.latest_close_spread_bps)
        )
        median_abs = snapshot.median_absolute_close_spread_bps
        if latest_abs is None or median_abs is None:
            raise ValueError("comparable provider grid requires spread metrics")
        if (
            latest_abs > config.material_spread_bps
            or median_abs > config.material_spread_bps
        ):
            scope = CrossVenueScope.VENUE_LOCAL
            state = CrossVenueQualityState.MATERIAL_PRICE_DISAGREEMENT
            flags.add("material_cross_venue_price_disagreement")
        else:
            scope = CrossVenueScope.BROAD_TWO_VENUE
            state = CrossVenueQualityState.TWO_VENUE_CONFIRMED
            if snapshot.grid_state is ProviderGridState.PARTIAL_OVERLAP:
                flags.add("partial_historical_provider_grid")

    conflicts: tuple[str, ...] = ()
    if state is CrossVenueQualityState.MATERIAL_PRICE_DISAGREEMENT:
        conflicts = (
            canonical_sha256(
                {
                    "provider_divergence_identity": snapshot.snapshot_identity,
                    "symbol": snapshot.symbol,
                    "timeframe": snapshot.timeframe,
                    "as_of_ms": snapshot.observed_at_ms,
                    "material_spread_bps": config.material_spread_bps,
                    "latest_absolute_spread_bps": (
                        None
                        if snapshot.latest_close_spread_bps is None
                        else abs(snapshot.latest_close_spread_bps)
                    ),
                    "median_absolute_spread_bps": (
                        snapshot.median_absolute_close_spread_bps
                    ),
                    "semantic": "material_cross_venue_price_disagreement",
                }
            ),
        )

    payload = {
        "engine_version": CROSS_VENUE_QUALITY_ENGINE_VERSION,
        "provider_divergence_identity": snapshot.snapshot_identity,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
        "as_of_ms": snapshot.observed_at_ms,
        "scope": scope,
        "state": state,
        "material_spread_bps": config.material_spread_bps,
        "latest_absolute_spread_bps": (
            None
            if snapshot.latest_close_spread_bps is None
            else abs(snapshot.latest_close_spread_bps)
        ),
        "median_absolute_spread_bps": snapshot.median_absolute_close_spread_bps,
        "source_evidence_identities": source_ids,
        "material_conflict_identities": conflicts,
        "uncertainty_flags": tuple(sorted(flags)),
        "directional_authority": False,
        "score_authority": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return CrossVenueQualityAssessment(
        assessment_identity=canonical_sha256(payload),
        engine_version=CROSS_VENUE_QUALITY_ENGINE_VERSION,
        provider_divergence_identity=snapshot.snapshot_identity,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        as_of_ms=snapshot.observed_at_ms,
        scope=scope,
        state=state,
        material_spread_bps=config.material_spread_bps,
        latest_absolute_spread_bps=(
            None
            if snapshot.latest_close_spread_bps is None
            else abs(snapshot.latest_close_spread_bps)
        ),
        median_absolute_spread_bps=snapshot.median_absolute_close_spread_bps,
        source_evidence_identities=source_ids,
        material_conflict_identities=conflicts,
        uncertainty_flags=tuple(sorted(flags)),
    )


def _assessment_payload(
    assessment: CrossVenueQualityAssessment,
) -> dict[str, object]:
    return {
        "engine_version": assessment.engine_version,
        "provider_divergence_identity": assessment.provider_divergence_identity,
        "symbol": assessment.symbol,
        "timeframe": assessment.timeframe,
        "as_of_ms": assessment.as_of_ms,
        "scope": assessment.scope,
        "state": assessment.state,
        "material_spread_bps": assessment.material_spread_bps,
        "latest_absolute_spread_bps": assessment.latest_absolute_spread_bps,
        "median_absolute_spread_bps": assessment.median_absolute_spread_bps,
        "source_evidence_identities": assessment.source_evidence_identities,
        "material_conflict_identities": assessment.material_conflict_identities,
        "uncertainty_flags": assessment.uncertainty_flags,
        "directional_authority": assessment.directional_authority,
        "score_authority": assessment.score_authority,
        "production_authority": assessment.production_authority,
        "real_capital": assessment.real_capital,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} must be sha256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be sha256") from exc


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be canonical")
    for value in values:
        _require_sha256(value, label)
