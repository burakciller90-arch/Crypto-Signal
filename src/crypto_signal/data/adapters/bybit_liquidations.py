from __future__ import annotations

import time
from decimal import Decimal
from typing import cast

from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.liquidations import (
    LiquidatedPositionSide,
    LiquidationObservation,
    build_liquidation_observation,
)
from crypto_signal.data.models import DataSource, Exchange

BYBIT_ALL_LIQUIDATION_ADAPTER_VERSION = "bybit-v5-all-liquidation/1"


def parse_bybit_all_liquidation_payload(
    payload: dict[str, object],
    *,
    expected_symbol: str,
    ingested_at_ms: int | None = None,
    adapter_version: str = BYBIT_ALL_LIQUIDATION_ADAPTER_VERSION,
) -> tuple[LiquidationObservation, ...]:
    if not expected_symbol or expected_symbol != expected_symbol.upper():
        raise ValueError("Bybit liquidation symbol must be non-empty uppercase")
    if not adapter_version.strip():
        raise ValueError("Bybit liquidation adapter_version must be non-empty")
    if payload.get("topic") != f"allLiquidation.{expected_symbol}":
        raise ValueError("unexpected Bybit all-liquidation topic")
    if payload.get("type") != "snapshot":
        raise ValueError("Bybit all-liquidation message type must be snapshot")

    source_timestamp_ms = int(cast(int | str, payload["ts"]))
    rows = cast(list[dict[str, object]], payload["data"])
    seen_at_ms = (
        time.time_ns() // 1_000_000
        if ingested_at_ms is None
        else ingested_at_ms
    )
    observations: list[LiquidationObservation] = []
    for row_index, row in enumerate(rows):
        if row.get("s") != expected_symbol:
            raise ValueError("Bybit all-liquidation symbol mismatch")
        provider_side = str(row.get("S", ""))
        if provider_side == "Buy":
            liquidated_side = LiquidatedPositionSide.LONG
        elif provider_side == "Sell":
            liquidated_side = LiquidatedPositionSide.SHORT
        else:
            raise ValueError("Bybit liquidation position side must be Buy or Sell")

        observations.append(
            build_liquidation_observation(
                exchange=Exchange.BYBIT,
                instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
                symbol=expected_symbol,
                liquidated_position_side=liquidated_side,
                size=Decimal(str(row["v"])),
                bankruptcy_price=Decimal(str(row["p"])),
                event_at_ms=int(cast(int | str, row["T"])),
                source_timestamp_ms=source_timestamp_ms,
                ingested_at_ms=seen_at_ms,
                source_row_index=row_index,
                source=DataSource.WEBSOCKET,
                adapter_version=adapter_version,
            )
        )
    return tuple(observations)
