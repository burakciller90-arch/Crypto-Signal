from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.paper.instrument_fees_v2 import (
    InstrumentFeeProjectionStatus,
    InstrumentFeeRole,
    normalize_binance_spot_commission_snapshot,
    project_instrument_fee,
)
from crypto_signal.paper.models import PaperAction, PaperSymbol


def _payload():
    return {
        "symbol": "BTCUSDT",
        "standardCommission": {
            "maker": "0.0001",
            "taker": "0.0002",
            "buyer": "0.0003",
            "seller": "0.0004",
        },
        "specialCommission": {
            "maker": "0.0010",
            "taker": "0.0020",
            "buyer": "0.0030",
            "seller": "0.0040",
        },
        "taxCommission": {
            "maker": "0.00001",
            "taker": "0.00002",
            "buyer": "0.00003",
            "seller": "0.00004",
        },
        "discount": {
            "enabledForAccount": True,
            "enabledForSymbol": True,
            "discountAsset": "BNB",
            "discount": "0.25",
        },
    }


def _snapshot():
    return normalize_binance_spot_commission_snapshot(
        payload=_payload(),
        observed_at_ms=1_000,
        ingested_at_ms=1_001,
    )


def test_snapshot_exact_replay_identity_is_stable() -> None:
    first = _snapshot()
    replay = _snapshot()

    assert replay == first
    assert replay.snapshot_identity == first.snapshot_identity


def test_taker_buy_includes_standard_special_and_tax_without_discount_assumption() -> None:
    projection = project_instrument_fee(
        snapshot=_snapshot(),
        symbol=PaperSymbol.BTCUSDT,
        action=PaperAction.BUY,
        role=InstrumentFeeRole.TAKER,
        fill_notional_usdt=Decimal(1000),
        evaluation_cutoff_ms=1_001,
    )

    assert projection.status is InstrumentFeeProjectionStatus.PROVEN
    assert projection.standard_rate_before_discount == Decimal("0.0005")
    assert projection.standard_rate_after_discount == Decimal("0.0005")
    assert projection.special_rate == Decimal("0.0050")
    assert projection.tax_rate == Decimal("0.00005")
    assert projection.effective_fee_rate == Decimal("0.00555")
    assert projection.fee_usdt == Decimal("5.55000")
    assert projection.discount_applied is False


def test_maker_sell_selects_maker_plus_seller_components() -> None:
    projection = project_instrument_fee(
        snapshot=_snapshot(),
        symbol=PaperSymbol.BTCUSDT,
        action=PaperAction.EXIT,
        role=InstrumentFeeRole.MAKER,
        fill_notional_usdt=Decimal(1000),
        evaluation_cutoff_ms=1_001,
    )

    assert projection.standard_rate_before_discount == Decimal("0.0005")
    assert projection.special_rate == Decimal("0.0050")
    assert projection.tax_rate == Decimal("0.00005")


def test_discount_only_reduces_standard_when_payment_proof_is_explicit() -> None:
    projection = project_instrument_fee(
        snapshot=_snapshot(),
        symbol=PaperSymbol.BTCUSDT,
        action=PaperAction.BUY,
        role=InstrumentFeeRole.TAKER,
        fill_notional_usdt=Decimal(1000),
        evaluation_cutoff_ms=1_001,
        discount_payment_proof_identity="a" * 64,
    )

    assert projection.discount_applied is True
    assert projection.standard_rate_before_discount == Decimal("0.0005")
    assert projection.standard_rate_after_discount == Decimal("0.000125")
    assert projection.special_rate == Decimal("0.0050")
    assert projection.tax_rate == Decimal("0.00005")
    assert projection.effective_fee_rate == Decimal("0.005175")
    assert projection.fee_usdt == Decimal("5.175000")


def test_discount_proof_does_not_apply_when_schedule_disables_discount() -> None:
    payload = _payload()
    payload["discount"]["enabledForSymbol"] = False
    snapshot = normalize_binance_spot_commission_snapshot(
        payload=payload,
        observed_at_ms=1_000,
        ingested_at_ms=1_001,
    )

    projection = project_instrument_fee(
        snapshot=snapshot,
        symbol=PaperSymbol.BTCUSDT,
        action=PaperAction.BUY,
        role=InstrumentFeeRole.TAKER,
        fill_notional_usdt=Decimal(1000),
        evaluation_cutoff_ms=1_001,
        discount_payment_proof_identity="b" * 64,
    )

    assert projection.discount_applied is False
    assert projection.discount_payment_proof_identity is None
    assert projection.standard_rate_after_discount == Decimal("0.0005")


def test_missing_snapshot_is_fee_not_proven_and_has_no_cost() -> None:
    projection = project_instrument_fee(
        snapshot=None,
        symbol=PaperSymbol.BTCUSDT,
        action=PaperAction.BUY,
        role=InstrumentFeeRole.TAKER,
        fill_notional_usdt=Decimal(1000),
        evaluation_cutoff_ms=1_001,
    )

    assert projection.status is InstrumentFeeProjectionStatus.FEE_NOT_PROVEN
    assert projection.fee_usdt is None
    assert projection.effective_fee_rate is None


def test_future_fee_snapshot_is_rejected() -> None:
    with pytest.raises(ValueError, match="future fee snapshot"):
        project_instrument_fee(
            snapshot=_snapshot(),
            symbol=PaperSymbol.BTCUSDT,
            action=PaperAction.BUY,
            role=InstrumentFeeRole.TAKER,
            fill_notional_usdt=Decimal(1000),
            evaluation_cutoff_ms=1_000,
        )


def test_symbol_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="symbol mismatch"):
        project_instrument_fee(
            snapshot=_snapshot(),
            symbol=PaperSymbol.ETHUSDT,
            action=PaperAction.BUY,
            role=InstrumentFeeRole.TAKER,
            fill_notional_usdt=Decimal(1000),
            evaluation_cutoff_ms=1_001,
        )


def test_snapshot_payload_hash_changes_when_instrument_rates_change() -> None:
    first = _snapshot()
    payload = _payload()
    payload["standardCommission"]["taker"] = "0.00025"
    changed = normalize_binance_spot_commission_snapshot(
        payload=payload,
        observed_at_ms=1_000,
        ingested_at_ms=1_001,
    )

    assert changed.source_payload_sha256 != first.source_payload_sha256
    assert changed.snapshot_identity != first.snapshot_identity


def test_projection_exact_replay_identity_is_stable() -> None:
    kwargs = {
        "snapshot": _snapshot(),
        "symbol": PaperSymbol.BTCUSDT,
        "action": PaperAction.REDUCE,
        "role": InstrumentFeeRole.MAKER,
        "fill_notional_usdt": Decimal(1234),
        "evaluation_cutoff_ms": 1_001,
    }

    first = project_instrument_fee(**kwargs)
    replay = project_instrument_fee(**kwargs)

    assert replay == first
    assert replay.projection_identity == first.projection_identity


def test_discount_flags_must_be_real_booleans() -> None:
    payload = _payload()
    payload["discount"]["enabledForAccount"] = "true"

    with pytest.raises(TypeError, match="enabledForAccount"):
        normalize_binance_spot_commission_snapshot(
            payload=payload,
            observed_at_ms=1_000,
            ingested_at_ms=1_001,
        )
