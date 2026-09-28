from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.provider_divergence_runtime import (
    ProviderDivergenceRuntimeTruth,
)

CROSS_VENUE_QUALITY_ENGINE_VERSION = "rdp9-cross-venue-quality-v1/1"


class CrossVenueQualityState(StrEnum):
    BROAD_COVERAGE = "broad_coverage"
    VENUE_LOCAL = "venue_local"
    MATERIAL_DISAGREEMENT = "material_disagreement"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class CrossVenueQualityConfig:
    max_snapshot_age_ms: int = 30 * 60_000
    material_close_spread_bps: Decimal = Decimal("50")
    version: str = "rdp9-cross-venue-quality-policy-v1/1"

    def __post_init__(self) -> None:
        if self.max_snapshot_age_ms <= 0:
            raise ValueError("cross-venue max snapshot age must be positive")
        if self.material_close_spread_bps <= Decimal(0):
            raise ValueError("cross-venue material spread must be positive")
        if not self.version.strip():
            raise ValueError("cross-venue quality policy version is required")


DEFAULT_CROSS_VENUE_QUALITY_CONFIG = CrossVenueQualityConfig()


@dataclass(frozen=True, slots=True)
class CrossVenueQualityAssessment:
    assessment_identity: str
    provider_snapshot_identity: str
    symbol: str
    timeframe: str
    as_of_ms: int
    state: CrossVenueQualityState
    left_exchange: str
    right_exchange: str
    grid_state: str
    latest_close_spread_bps: Decimal | None
    median_absolute_close_spread_bps: Decimal | None
    max_absolute_close_spread_bps: Decimal | None
    venue_local_exchange: str | None
    source_evidence_identities: tuple[str, ...]
    reason_codes: tuple[str, ...]
    policy_version: str
    engine_version: str = CROSS_VENUE_QUALITY_ENGINE_VERSION
    production_authority: bool = False
    real_capital: int = 0

    def __post_init__(self) -> None:
        _require_sha256(
            self.assessment_identity,
            "cross-venue assessment identity",
        )
        _require_sha256(
            self.provider_snapshot_identity,
            "cross-venue provider snapshot identity",
        )
        if self.engine_version != CROSS_VENUE_QUALITY_ENGINE_VERSION:
            raise ValueError("unsupported cross-venue quality engine")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("cross-venue symbol must be uppercase")
        if not self.timeframe.strip():
            raise ValueError("cross-venue timeframe is required")
        if self.as_of_ms < 0:
            raise ValueError("cross-venue as-of cannot be negative")
        if (self.left_exchange, self.right_exchange) != ("binance", "bybit"):
            raise ValueError("cross-venue exchange pair mismatch")
        if self.grid_state not in {
            "full_overlap",
            "partial_overlap",
            "no_overlap",
        }:
            raise ValueError("cross-venue grid state invalid")
        _require_identity_tuple(
            self.source_evidence_identities,
            "cross-venue source evidence",
        )
        _require_text_tuple(self.reason_codes, "cross-venue reason code")
        if not self.policy_version.strip():
            raise ValueError("cross-venue policy version is required")
        if self.state is CrossVenueQualityState.VENUE_LOCAL:
            if self.venue_local_exchange not in {
                self.left_exchange,
                self.right_exchange,
            }:
                raise ValueError("venue-local assessment requires one exchange")
        elif self.venue_local_exchange is not None:
            raise ValueError("non-local assessment cannot name venue-local exchange")
        if (
            self.state is CrossVenueQualityState.MATERIAL_DISAGREEMENT
            and self.max_absolute_close_spread_bps is None
        ):
            raise ValueError("material disagreement requires spread evidence")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("cross-venue quality has no production authority")
        if self.assessment_identity != canonical_sha256(
            _assessment_payload(self)
        ):
            raise ValueError("cross-venue assessment identity mismatch")

    @property
    def material_conflict_identity(self) -> str | None:
        if self.state is CrossVenueQualityState.MATERIAL_DISAGREEMENT:
            return self.assessment_identity
        return None


def assess_cross_venue_quality(
    truth: ProviderDivergenceRuntimeTruth,
    *,
    as_of_ms: int,
    config: CrossVenueQualityConfig = DEFAULT_CROSS_VENUE_QUALITY_CONFIG,
) -> CrossVenueQualityAssessment:
    if as_of_ms < truth.observed_at_ms:
        raise ValueError("cross-venue assessment cannot use future snapshot")
    age_ms = as_of_ms - truth.observed_at_ms
    left = truth.left_quality
    right = truth.right_quality
    source_ids = tuple(
        sorted(
            {
                truth.snapshot_identity,
                *truth.left_source_evidence_identities,
                *truth.right_source_evidence_identities,
            }
        )
    )
    reasons: set[str] = set()
    local: str | None = None

    left_healthy = (
        left.available
        and not left.stale
        and left.gap_count == 0
        and left.gap_missing_candles == 0
    )
    right_healthy = (
        right.available
        and not right.stale
        and right.gap_count == 0
        and right.gap_missing_candles == 0
    )

    if age_ms > config.max_snapshot_age_ms:
        state = CrossVenueQualityState.DEGRADED
        reasons.add("provider_divergence_snapshot_stale")
    elif not left_healthy and not right_healthy:
        state = CrossVenueQualityState.DEGRADED
        reasons.add("both_provider_quality_degraded")
    elif left_healthy != right_healthy:
        state = CrossVenueQualityState.VENUE_LOCAL
        local = truth.left_exchange if left_healthy else truth.right_exchange
        reasons.add("one_provider_only_healthy")
    elif truth.grid_state != "full_overlap":
        state = CrossVenueQualityState.VENUE_LOCAL
        if (
            len(truth.left_only_open_times_ms)
            > len(truth.right_only_open_times_ms)
        ):
            local = truth.left_exchange
        elif (
            len(truth.right_only_open_times_ms)
            > len(truth.left_only_open_times_ms)
        ):
            local = truth.right_exchange
        else:
            local = truth.right_exchange
        reasons.add(f"provider_grid_{truth.grid_state}")
    elif (
        truth.max_absolute_close_spread_bps is not None
        and truth.max_absolute_close_spread_bps
        >= config.material_close_spread_bps
    ):
        state = CrossVenueQualityState.MATERIAL_DISAGREEMENT
        reasons.add("material_cross_venue_close_spread")
    else:
        state = CrossVenueQualityState.BROAD_COVERAGE
        reasons.add("full_overlap_both_providers_healthy")

    payload = {
        "as_of_ms": as_of_ms,
        "engine_version": CROSS_VENUE_QUALITY_ENGINE_VERSION,
        "grid_state": truth.grid_state,
        "latest_close_spread_bps": truth.latest_close_spread_bps,
        "left_exchange": truth.left_exchange,
        "max_absolute_close_spread_bps": (
            truth.max_absolute_close_spread_bps
        ),
        "median_absolute_close_spread_bps": (
            truth.median_absolute_close_spread_bps
        ),
        "policy_version": config.version,
        "production_authority": False,
        "provider_snapshot_identity": truth.snapshot_identity,
        "real_capital": 0,
        "reason_codes": tuple(sorted(reasons)),
        "right_exchange": truth.right_exchange,
        "source_evidence_identities": source_ids,
        "state": state,
        "symbol": truth.symbol,
        "timeframe": truth.timeframe,
        "venue_local_exchange": local,
    }
    return CrossVenueQualityAssessment(
        assessment_identity=canonical_sha256(payload),
        provider_snapshot_identity=truth.snapshot_identity,
        symbol=truth.symbol,
        timeframe=truth.timeframe,
        as_of_ms=as_of_ms,
        state=state,
        left_exchange=truth.left_exchange,
        right_exchange=truth.right_exchange,
        grid_state=truth.grid_state,
        latest_close_spread_bps=truth.latest_close_spread_bps,
        median_absolute_close_spread_bps=truth.median_absolute_close_spread_bps,
        max_absolute_close_spread_bps=truth.max_absolute_close_spread_bps,
        venue_local_exchange=local,
        source_evidence_identities=source_ids,
        reason_codes=tuple(sorted(reasons)),
        policy_version=config.version,
    )


def _assessment_payload(
    assessment: CrossVenueQualityAssessment,
) -> dict[str, object]:
    return {
        "as_of_ms": assessment.as_of_ms,
        "engine_version": assessment.engine_version,
        "grid_state": assessment.grid_state,
        "latest_close_spread_bps": assessment.latest_close_spread_bps,
        "left_exchange": assessment.left_exchange,
        "max_absolute_close_spread_bps": (
            assessment.max_absolute_close_spread_bps
        ),
        "median_absolute_close_spread_bps": (
            assessment.median_absolute_close_spread_bps
        ),
        "policy_version": assessment.policy_version,
        "production_authority": assessment.production_authority,
        "provider_snapshot_identity": assessment.provider_snapshot_identity,
        "real_capital": assessment.real_capital,
        "reason_codes": assessment.reason_codes,
        "right_exchange": assessment.right_exchange,
        "source_evidence_identities": assessment.source_evidence_identities,
        "state": assessment.state,
        "symbol": assessment.symbol,
        "timeframe": assessment.timeframe,
        "venue_local_exchange": assessment.venue_local_exchange,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_text_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        if not value.strip():
            raise ValueError(f"{label} must be non-empty")
