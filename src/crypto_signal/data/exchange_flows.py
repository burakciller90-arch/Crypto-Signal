from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_sha256

EXCHANGE_FLOW_TEMPORAL_SEMANTIC = "provider_labeled_exchange_flow_window"


@dataclass(frozen=True, slots=True)
class ExchangeFlowObservation:
    observation_identity: str
    asset: str
    exchange_scope: str
    window_start_ms: int
    window_end_ms: int
    inflow_amount: Decimal
    outflow_amount: Decimal
    source_provider: str
    attribution_method: str
    source: DataSource
    source_timestamp_ms: int
    ingested_at_ms: int
    adapter_version: str
    temporal_semantic: str = EXCHANGE_FLOW_TEMPORAL_SEMANTIC

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "exchange-flow observation identity")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("exchange-flow asset must be non-empty uppercase")
        for value, label in (
            (self.exchange_scope, "exchange_scope"),
            (self.source_provider, "source_provider"),
            (self.attribution_method, "attribution_method"),
            (self.adapter_version, "adapter_version"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.temporal_semantic != EXCHANGE_FLOW_TEMPORAL_SEMANTIC:
            raise ValueError("unsupported exchange-flow temporal semantic")
        if min(
            self.window_start_ms,
            self.window_end_ms,
            self.source_timestamp_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("exchange-flow timestamps must be non-negative")
        if self.window_end_ms <= self.window_start_ms:
            raise ValueError("exchange-flow window end must follow start")
        if self.source_timestamp_ms < self.window_end_ms:
            raise ValueError("exchange-flow source timestamp cannot predate window end")
        if self.ingested_at_ms < self.source_timestamp_ms:
            raise ValueError("exchange-flow ingestion cannot predate source timestamp")
        for value, label in (
            (self.inflow_amount, "inflow_amount"),
            (self.outflow_amount, "outflow_amount"),
        ):
            if value.is_nan() or value.is_infinite() or value < Decimal(0):
                raise ValueError(f"{label} must be finite and non-negative")
        if self.observation_identity != canonical_sha256(exchange_flow_observation_payload(self)):
            raise ValueError("exchange-flow observation identity mismatch")

    @property
    def netflow_amount(self) -> Decimal:
        return self.inflow_amount - self.outflow_amount

    @property
    def gross_flow_amount(self) -> Decimal:
        return self.inflow_amount + self.outflow_amount

    @property
    def window_duration_ms(self) -> int:
        return self.window_end_ms - self.window_start_ms


def build_exchange_flow_observation(
    *,
    asset: str,
    exchange_scope: str,
    window_start_ms: int,
    window_end_ms: int,
    inflow_amount: Decimal,
    outflow_amount: Decimal,
    source_provider: str,
    attribution_method: str,
    source: DataSource,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    adapter_version: str,
) -> ExchangeFlowObservation:
    payload = {
        "adapter_version": adapter_version,
        "asset": asset,
        "attribution_method": attribution_method,
        "exchange_scope": exchange_scope,
        "inflow_amount": inflow_amount,
        "ingested_at_ms": ingested_at_ms,
        "outflow_amount": outflow_amount,
        "source": source,
        "source_provider": source_provider,
        "source_timestamp_ms": source_timestamp_ms,
        "temporal_semantic": EXCHANGE_FLOW_TEMPORAL_SEMANTIC,
        "window_end_ms": window_end_ms,
        "window_start_ms": window_start_ms,
    }
    return ExchangeFlowObservation(
        observation_identity=canonical_sha256(payload),
        asset=asset,
        exchange_scope=exchange_scope,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        inflow_amount=inflow_amount,
        outflow_amount=outflow_amount,
        source_provider=source_provider,
        attribution_method=attribution_method,
        source=source,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=adapter_version,
    )


def exchange_flow_observation_payload(
    observation: ExchangeFlowObservation,
) -> dict[str, object]:
    return {
        "adapter_version": observation.adapter_version,
        "asset": observation.asset,
        "attribution_method": observation.attribution_method,
        "exchange_scope": observation.exchange_scope,
        "inflow_amount": observation.inflow_amount,
        "ingested_at_ms": observation.ingested_at_ms,
        "outflow_amount": observation.outflow_amount,
        "source": observation.source,
        "source_provider": observation.source_provider,
        "source_timestamp_ms": observation.source_timestamp_ms,
        "temporal_semantic": observation.temporal_semantic,
        "window_end_ms": observation.window_end_ms,
        "window_start_ms": observation.window_start_ms,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
