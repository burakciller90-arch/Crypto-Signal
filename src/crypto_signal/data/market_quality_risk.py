from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.ledger.serialization import canonical_sha256

MARKET_QUALITY_RISK_SCHEMA_VERSION = "market-quality-risk-v1/1"


@dataclass(frozen=True, slots=True)
class MarketQualityRiskObservation:
    observation_identity: str
    schema_version: str
    asset: str
    observed_at_ms: int
    spread_bps: Decimal | None
    depth_loss_fraction: Decimal | None
    feed_delay_ms: int | None
    price_gap_fraction: Decimal | None
    provider_disagreement_bps: Decimal | None
    source_evidence_identities: tuple[str, ...]
    measurement_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "market-quality observation identity")
        if self.schema_version != MARKET_QUALITY_RISK_SCHEMA_VERSION:
            raise ValueError("unsupported market-quality risk schema")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("market-quality asset must be non-empty uppercase")
        if self.observed_at_ms < 0:
            raise ValueError("market-quality observed_at_ms must be non-negative")
        if not self.measurement_version.strip():
            raise ValueError("market-quality measurement_version must be non-empty")
        for value, label in (
            (self.spread_bps, "spread_bps"),
            (self.depth_loss_fraction, "depth_loss_fraction"),
            (self.price_gap_fraction, "price_gap_fraction"),
            (self.provider_disagreement_bps, "provider_disagreement_bps"),
        ):
            if value is not None and (
                value.is_nan() or value.is_infinite() or value < Decimal(0)
            ):
                raise ValueError(f"{label} must be finite and non-negative")
        if (
            self.depth_loss_fraction is not None
            and self.depth_loss_fraction > Decimal(1)
        ):
            raise ValueError("depth_loss_fraction must be inside [0,1]")
        if self.feed_delay_ms is not None and self.feed_delay_ms < 0:
            raise ValueError("feed_delay_ms must be non-negative")
        if tuple(sorted(set(self.source_evidence_identities))) != (
            self.source_evidence_identities
        ):
            raise ValueError(
                "market-quality source evidence identities must be unique and sorted"
            )
        for identity in self.source_evidence_identities:
            _require_sha256(identity, "market-quality source evidence identity")
        if self.observation_identity != canonical_sha256(
            market_quality_risk_payload(self)
        ):
            raise ValueError("market-quality observation identity mismatch")

    @property
    def complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.spread_bps,
                self.depth_loss_fraction,
                self.feed_delay_ms,
                self.price_gap_fraction,
                self.provider_disagreement_bps,
            )
        )


def build_market_quality_risk_observation(
    *,
    asset: str,
    observed_at_ms: int,
    spread_bps: Decimal | None,
    depth_loss_fraction: Decimal | None,
    feed_delay_ms: int | None,
    price_gap_fraction: Decimal | None,
    provider_disagreement_bps: Decimal | None,
    source_evidence_identities: tuple[str, ...],
    measurement_version: str,
) -> MarketQualityRiskObservation:
    evidence = tuple(sorted(set(source_evidence_identities)))
    payload = {
        "asset": asset,
        "depth_loss_fraction": depth_loss_fraction,
        "feed_delay_ms": feed_delay_ms,
        "measurement_version": measurement_version,
        "observed_at_ms": observed_at_ms,
        "price_gap_fraction": price_gap_fraction,
        "provider_disagreement_bps": provider_disagreement_bps,
        "schema_version": MARKET_QUALITY_RISK_SCHEMA_VERSION,
        "source_evidence_identities": evidence,
        "spread_bps": spread_bps,
    }
    return MarketQualityRiskObservation(
        observation_identity=canonical_sha256(payload),
        schema_version=MARKET_QUALITY_RISK_SCHEMA_VERSION,
        asset=asset,
        observed_at_ms=observed_at_ms,
        spread_bps=spread_bps,
        depth_loss_fraction=depth_loss_fraction,
        feed_delay_ms=feed_delay_ms,
        price_gap_fraction=price_gap_fraction,
        provider_disagreement_bps=provider_disagreement_bps,
        source_evidence_identities=evidence,
        measurement_version=measurement_version,
    )


def market_quality_risk_payload(
    observation: MarketQualityRiskObservation,
) -> dict[str, object]:
    return {
        "asset": observation.asset,
        "depth_loss_fraction": observation.depth_loss_fraction,
        "feed_delay_ms": observation.feed_delay_ms,
        "measurement_version": observation.measurement_version,
        "observed_at_ms": observation.observed_at_ms,
        "price_gap_fraction": observation.price_gap_fraction,
        "provider_disagreement_bps": observation.provider_disagreement_bps,
        "schema_version": observation.schema_version,
        "source_evidence_identities": observation.source_evidence_identities,
        "spread_bps": observation.spread_bps,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
