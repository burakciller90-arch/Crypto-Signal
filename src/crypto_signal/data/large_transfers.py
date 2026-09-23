from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_sha256


class TransferClusterRole(StrEnum):
    UNKNOWN = "unknown"
    EXCHANGE = "exchange"
    PROVIDER_KNOWN = "provider_known"


@dataclass(frozen=True, slots=True)
class LargeTransferObservation:
    transfer_identity: str
    asset: str
    network: str
    provider_transfer_id: str
    source_cluster_id: str
    destination_cluster_id: str
    source_role: TransferClusterRole
    destination_role: TransferClusterRole
    amount: Decimal
    event_at_ms: int
    source_timestamp_ms: int
    ingested_at_ms: int
    source_provider: str
    attribution_method: str
    source: DataSource
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.transfer_identity, "large-transfer identity")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("large-transfer asset must be non-empty uppercase")
        for value, label in (
            (self.network, "network"),
            (self.provider_transfer_id, "provider_transfer_id"),
            (self.source_cluster_id, "source_cluster_id"),
            (self.destination_cluster_id, "destination_cluster_id"),
            (self.source_provider, "source_provider"),
            (self.attribution_method, "attribution_method"),
            (self.adapter_version, "adapter_version"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.source_cluster_id == self.destination_cluster_id:
            raise ValueError("large-transfer source and destination clusters must differ")
        if self.amount.is_nan() or self.amount.is_infinite() or self.amount <= Decimal(0):
            raise ValueError("large-transfer amount must be finite and positive")
        if min(self.event_at_ms, self.source_timestamp_ms, self.ingested_at_ms) < 0:
            raise ValueError("large-transfer timestamps must be non-negative")
        if self.event_at_ms > self.source_timestamp_ms:
            raise ValueError("large-transfer event cannot postdate source timestamp")
        if self.ingested_at_ms < self.source_timestamp_ms:
            raise ValueError("large-transfer ingestion cannot predate source timestamp")
        if self.transfer_identity != canonical_sha256(large_transfer_payload(self)):
            raise ValueError("large-transfer identity mismatch")


def build_large_transfer_observation(
    *,
    asset: str,
    network: str,
    provider_transfer_id: str,
    source_cluster_id: str,
    destination_cluster_id: str,
    source_role: TransferClusterRole,
    destination_role: TransferClusterRole,
    amount: Decimal,
    event_at_ms: int,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    source_provider: str,
    attribution_method: str,
    source: DataSource,
    adapter_version: str,
) -> LargeTransferObservation:
    payload = {
        "adapter_version": adapter_version,
        "amount": amount,
        "asset": asset,
        "attribution_method": attribution_method,
        "destination_cluster_id": destination_cluster_id,
        "destination_role": destination_role,
        "event_at_ms": event_at_ms,
        "ingested_at_ms": ingested_at_ms,
        "network": network,
        "provider_transfer_id": provider_transfer_id,
        "source": source,
        "source_cluster_id": source_cluster_id,
        "source_provider": source_provider,
        "source_role": source_role,
        "source_timestamp_ms": source_timestamp_ms,
    }
    return LargeTransferObservation(
        transfer_identity=canonical_sha256(payload),
        asset=asset,
        network=network,
        provider_transfer_id=provider_transfer_id,
        source_cluster_id=source_cluster_id,
        destination_cluster_id=destination_cluster_id,
        source_role=source_role,
        destination_role=destination_role,
        amount=amount,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        source_provider=source_provider,
        attribution_method=attribution_method,
        source=source,
        adapter_version=adapter_version,
    )


def large_transfer_payload(observation: LargeTransferObservation) -> dict[str, object]:
    return {
        "adapter_version": observation.adapter_version,
        "amount": observation.amount,
        "asset": observation.asset,
        "attribution_method": observation.attribution_method,
        "destination_cluster_id": observation.destination_cluster_id,
        "destination_role": observation.destination_role,
        "event_at_ms": observation.event_at_ms,
        "ingested_at_ms": observation.ingested_at_ms,
        "network": observation.network,
        "provider_transfer_id": observation.provider_transfer_id,
        "source": observation.source,
        "source_cluster_id": observation.source_cluster_id,
        "source_provider": observation.source_provider,
        "source_role": observation.source_role,
        "source_timestamp_ms": observation.source_timestamp_ms,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
