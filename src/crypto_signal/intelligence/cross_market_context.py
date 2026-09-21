from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.cross_market import (
    CrossMarketSeries,
    CrossMarketWindowObservation,
)
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256

CROSS_MARKET_ENGINE_VERSION = "cross-market-context-v1/1"
CROSS_MARKET_FREEZE_SCHEMA_VERSION = "cross-market-context-freeze-v1/1"
_DAY_MS = 24 * 60 * 60 * 1000


class CryptoDirection(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    UNAVAILABLE = "unavailable"


class VixDirection(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    UNAVAILABLE = "unavailable"


class RatesDirection(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    UNAVAILABLE = "unavailable"


class CrossMarketLabel(StrEnum):
    BTC_VIX_RELIEF_ALIGNMENT = "btc_vix_relief_alignment"
    BTC_VIX_STRESS_ALIGNMENT = "btc_vix_stress_alignment"
    BTC_VIX_SAME_DIRECTION = "btc_vix_same_direction"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class CrossMarketConfig:
    common_sessions: int = 5
    max_observation_ingest_age_ms: int = 36 * 60 * 60_000
    max_macro_source_lag_ms: int = 5 * _DAY_MS
    btc_move_threshold_pct: Decimal = Decimal("1.5")
    vix_move_threshold_pct: Decimal = Decimal("8")
    treasury_move_threshold_bps: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        if not 3 <= self.common_sessions <= 20:
            raise ValueError("cross-market common_sessions must be between 3 and 20")
        if self.max_observation_ingest_age_ms <= 0:
            raise ValueError("max_observation_ingest_age_ms must be positive")
        if self.max_macro_source_lag_ms <= 0:
            raise ValueError("max_macro_source_lag_ms must be positive")
        for label, value in (
            ("btc_move_threshold_pct", self.btc_move_threshold_pct),
            ("vix_move_threshold_pct", self.vix_move_threshold_pct),
            ("treasury_move_threshold_bps", self.treasury_move_threshold_bps),
        ):
            if value <= Decimal(0):
                raise ValueError(f"{label} must be positive")


DEFAULT_CROSS_MARKET_CONFIG = CrossMarketConfig()


@dataclass(frozen=True, slots=True)
class CrossMarketMetrics:
    start_day_ms: int
    end_day_ms: int
    common_session_count: int
    btc_return_pct: Decimal
    vix_change_pct: Decimal
    treasury_10y_change_bps: Decimal

    def __post_init__(self) -> None:
        if self.start_day_ms < 0 or self.end_day_ms <= self.start_day_ms:
            raise ValueError("cross-market metric day range is invalid")
        if self.start_day_ms % _DAY_MS or self.end_day_ms % _DAY_MS:
            raise ValueError("cross-market metric days must be UTC-day aligned")
        if self.common_session_count < 2:
            raise ValueError("cross-market metric requires multiple common sessions")


@dataclass(frozen=True, slots=True)
class CrossMarketAnalysis:
    evidence_identity: str
    engine_version: str
    as_of_ms: int
    vix_observed_at_ms: int | None
    treasury_observed_at_ms: int | None
    label: CrossMarketLabel
    crypto_direction: CryptoDirection
    vix_direction: VixDirection
    rates_direction: RatesDirection
    metrics: CrossMarketMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "cross-market evidence identity")
        if self.engine_version != CROSS_MARKET_ENGINE_VERSION:
            raise ValueError("unsupported cross-market engine version")
        if self.as_of_ms < 0:
            raise ValueError("cross-market as_of_ms must be non-negative")
        for label, value in (
            ("vix_observed_at_ms", self.vix_observed_at_ms),
            ("treasury_observed_at_ms", self.treasury_observed_at_ms),
        ):
            if value is not None and not 0 <= value <= self.as_of_ms:
                raise ValueError(f"{label} must be available by as-of")
        if self.label is CrossMarketLabel.UNRESOLVED:
            if self.metrics is not None:
                raise ValueError("unresolved cross-market analysis cannot carry metrics")
            if self.crypto_direction is not CryptoDirection.UNAVAILABLE:
                raise ValueError("unresolved crypto direction must be unavailable")
            if self.vix_direction is not VixDirection.UNAVAILABLE:
                raise ValueError("unresolved VIX direction must be unavailable")
            if self.rates_direction is not RatesDirection.UNAVAILABLE:
                raise ValueError("unresolved rates direction must be unavailable")
            if not self.uncertainty_flags:
                raise ValueError("unresolved cross-market analysis requires uncertainty")
        else:
            if self.metrics is None:
                raise ValueError("resolved cross-market analysis requires metrics")
            if self.crypto_direction is CryptoDirection.UNAVAILABLE:
                raise ValueError("resolved crypto direction cannot be unavailable")
            if self.vix_direction is VixDirection.UNAVAILABLE:
                raise ValueError("resolved VIX direction cannot be unavailable")
            if self.rates_direction is RatesDirection.UNAVAILABLE:
                raise ValueError("resolved rates direction cannot be unavailable")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("cross-market evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class CrossMarketEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: CrossMarketAnalysis
    vix_observation: CrossMarketWindowObservation | None
    treasury_observation: CrossMarketWindowObservation | None
    btc_candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "cross-market freeze identity")
        if self.schema_version != CROSS_MARKET_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported cross-market freeze schema")
        if self.vix_observation is None:
            if self.analysis.vix_observed_at_ms is not None:
                raise ValueError("missing VIX observation cannot have observation time")
        elif self.analysis.vix_observed_at_ms != self.vix_observation.observed_at_ms:
            raise ValueError("VIX freeze observation time mismatch")
        if self.treasury_observation is None:
            if self.analysis.treasury_observed_at_ms is not None:
                raise ValueError(
                    "missing Treasury observation cannot have observation time"
                )
        elif (
            self.analysis.treasury_observed_at_ms
            != self.treasury_observation.observed_at_ms
        ):
            raise ValueError("Treasury freeze observation time mismatch")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("cross-market freeze identity mismatch")


def analyze_cross_market_context(
    btc_candles: Sequence[Candle],
    vix_observations: Sequence[CrossMarketWindowObservation],
    treasury_observations: Sequence[CrossMarketWindowObservation],
    *,
    as_of_ms: int,
    config: CrossMarketConfig = DEFAULT_CROSS_MARKET_CONFIG,
) -> CrossMarketAnalysis:
    return build_cross_market_evidence_freeze(
        btc_candles,
        vix_observations,
        treasury_observations,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_cross_market_evidence_freeze(
    btc_candles: Sequence[Candle],
    vix_observations: Sequence[CrossMarketWindowObservation],
    treasury_observations: Sequence[CrossMarketWindowObservation],
    *,
    as_of_ms: int,
    config: CrossMarketConfig = DEFAULT_CROSS_MARKET_CONFIG,
) -> CrossMarketEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("cross-market as_of_ms must be non-negative")

    _validate_observation_context(vix_observations, treasury_observations)
    _reject_duplicate_observations(vix_observations, treasury_observations)
    _validate_btc_context(btc_candles)

    safe_vix = tuple(
        sorted(
            (
                item
                for item in vix_observations
                if item.observed_at_ms <= as_of_ms
            ),
            key=lambda item: (item.observed_at_ms, item.observation_identity),
        )
    )
    safe_treasury = tuple(
        sorted(
            (
                item
                for item in treasury_observations
                if item.observed_at_ms <= as_of_ms
            ),
            key=lambda item: (item.observed_at_ms, item.observation_identity),
        )
    )
    vix = safe_vix[-1] if safe_vix else None
    treasury = safe_treasury[-1] if safe_treasury else None
    flags: list[str] = []

    if vix is None:
        flags.append("vix_observation_unavailable_at_as_of")
    else:
        if as_of_ms - vix.observed_at_ms > config.max_observation_ingest_age_ms:
            flags.append("stale_vix_observation")
        if (
            as_of_ms - (vix.records[-1].day_start_ms + _DAY_MS)
            > config.max_macro_source_lag_ms
        ):
            flags.append("stale_vix_source_window")

    if treasury is None:
        flags.append("treasury_observation_unavailable_at_as_of")
    else:
        if (
            as_of_ms - treasury.observed_at_ms
            > config.max_observation_ingest_age_ms
        ):
            flags.append("stale_treasury_observation")
        if (
            as_of_ms - (treasury.records[-1].day_start_ms + _DAY_MS)
            > config.max_macro_source_lag_ms
        ):
            flags.append("stale_treasury_source_window")

    if flags:
        analysis = _unresolved(
            as_of_ms=as_of_ms,
            vix=vix,
            treasury=treasury,
            flags=tuple(flags),
        )
        return _freeze(
            analysis=analysis,
            vix=vix,
            treasury=treasury,
            btc_candles=(),
        )

    assert vix is not None
    assert treasury is not None
    vix_by_day = {item.day_start_ms: item for item in vix.records}
    treasury_by_day = {item.day_start_ms: item for item in treasury.records}
    common_days = sorted(set(vix_by_day) & set(treasury_by_day))
    if len(common_days) < config.common_sessions:
        analysis = _unresolved(
            as_of_ms=as_of_ms,
            vix=vix,
            treasury=treasury,
            flags=("insufficient_common_macro_sessions",),
        )
        return _freeze(
            analysis=analysis,
            vix=vix,
            treasury=treasury,
            btc_candles=(),
        )

    selected_days = common_days[-config.common_sessions :]
    safe_btc_by_day: dict[int, Candle] = {}
    for candle in btc_candles:
        if (
            candle.close_time_ms <= as_of_ms
            and candle.source_timestamp_ms <= as_of_ms
            and candle.ingested_at_ms <= as_of_ms
            and candle.is_closed
        ):
            if candle.open_time_ms in safe_btc_by_day:
                raise ValueError("duplicate safe BTC candle open time")
            safe_btc_by_day[candle.open_time_ms] = candle

    missing_days = [day for day in selected_days if day not in safe_btc_by_day]
    if missing_days:
        analysis = _unresolved(
            as_of_ms=as_of_ms,
            vix=vix,
            treasury=treasury,
            flags=("incomplete_btc_macro_alignment",),
        )
        return _freeze(
            analysis=analysis,
            vix=vix,
            treasury=treasury,
            btc_candles=(),
        )

    consumed_btc = tuple(safe_btc_by_day[day] for day in selected_days)
    first_day = selected_days[0]
    last_day = selected_days[-1]
    first_btc = consumed_btc[0].close
    last_btc = consumed_btc[-1].close
    first_vix = vix_by_day[first_day].value
    last_vix = vix_by_day[last_day].value
    first_rate = treasury_by_day[first_day].value
    last_rate = treasury_by_day[last_day].value

    btc_return_pct = (last_btc / first_btc - Decimal(1)) * Decimal(100)
    vix_change_pct = (last_vix / first_vix - Decimal(1)) * Decimal(100)
    treasury_change_bps = (last_rate - first_rate) * Decimal(100)

    crypto_direction = _crypto_direction(
        btc_return_pct,
        config.btc_move_threshold_pct,
    )
    vix_direction = _vix_direction(
        vix_change_pct,
        config.vix_move_threshold_pct,
    )
    rates_direction = _rates_direction(
        treasury_change_bps,
        config.treasury_move_threshold_bps,
    )
    label = _cross_market_label(crypto_direction, vix_direction)
    metrics = CrossMarketMetrics(
        start_day_ms=first_day,
        end_day_ms=last_day,
        common_session_count=len(selected_days),
        btc_return_pct=btc_return_pct,
        vix_change_pct=vix_change_pct,
        treasury_10y_change_bps=treasury_change_bps,
    )
    payload = {
        "as_of_ms": as_of_ms,
        "crypto_direction": crypto_direction,
        "engine_version": CROSS_MARKET_ENGINE_VERSION,
        "label": label,
        "metrics": _metrics_payload(metrics),
        "rates_direction": rates_direction,
        "treasury_observed_at_ms": treasury.observed_at_ms,
        "uncertainty_flags": (),
        "vix_direction": vix_direction,
        "vix_observed_at_ms": vix.observed_at_ms,
    }
    analysis = CrossMarketAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=CROSS_MARKET_ENGINE_VERSION,
        as_of_ms=as_of_ms,
        vix_observed_at_ms=vix.observed_at_ms,
        treasury_observed_at_ms=treasury.observed_at_ms,
        label=label,
        crypto_direction=crypto_direction,
        vix_direction=vix_direction,
        rates_direction=rates_direction,
        metrics=metrics,
        uncertainty_flags=(),
    )
    return _freeze(
        analysis=analysis,
        vix=vix,
        treasury=treasury,
        btc_candles=consumed_btc,
    )


def _validate_observation_context(
    vix_observations: Sequence[CrossMarketWindowObservation],
    treasury_observations: Sequence[CrossMarketWindowObservation],
) -> None:
    for vix_item in vix_observations:
        if vix_item.series is not CrossMarketSeries.CBOE_VIX_CLOSE:
            raise ValueError("VIX input must use CBOE_VIX_CLOSE series")
    for treasury_item in treasury_observations:
        if (
            treasury_item.series
            is not CrossMarketSeries.US_TREASURY_10Y_YIELD
        ):
            raise ValueError(
                "Treasury input must use US_TREASURY_10Y_YIELD series"
            )


def _reject_duplicate_observations(
    vix_observations: Sequence[CrossMarketWindowObservation],
    treasury_observations: Sequence[CrossMarketWindowObservation],
) -> None:
    vix_ids = [item.observation_identity for item in vix_observations]
    treasury_ids = [item.observation_identity for item in treasury_observations]
    if len(vix_ids) != len(set(vix_ids)):
        raise ValueError("duplicate VIX observation identity")
    if len(treasury_ids) != len(set(treasury_ids)):
        raise ValueError("duplicate Treasury observation identity")


def _validate_btc_context(candles: Sequence[Candle]) -> None:
    for candle in candles:
        if candle.exchange is not Exchange.BYBIT:
            raise ValueError("cross-market v1 BTC candles require Bybit")
        if candle.market_type is not MarketType.SPOT:
            raise ValueError("cross-market v1 BTC candles require Spot")
        if candle.symbol != "BTCUSDT":
            raise ValueError("cross-market v1 BTC candles require BTCUSDT")
        if candle.timeframe != "1D":
            raise ValueError("cross-market v1 BTC candles require 1D timeframe")
        if candle.source is not DataSource.REST:
            raise ValueError("cross-market v1 BTC candles require REST source")


def _crypto_direction(
    value: Decimal,
    threshold: Decimal,
) -> CryptoDirection:
    if value >= threshold:
        return CryptoDirection.RISING
    if value <= -threshold:
        return CryptoDirection.FALLING
    return CryptoDirection.STABLE


def _vix_direction(value: Decimal, threshold: Decimal) -> VixDirection:
    if value >= threshold:
        return VixDirection.RISING
    if value <= -threshold:
        return VixDirection.FALLING
    return VixDirection.STABLE


def _rates_direction(value: Decimal, threshold: Decimal) -> RatesDirection:
    if value >= threshold:
        return RatesDirection.RISING
    if value <= -threshold:
        return RatesDirection.FALLING
    return RatesDirection.STABLE


def _cross_market_label(
    crypto: CryptoDirection,
    vix: VixDirection,
) -> CrossMarketLabel:
    if crypto is CryptoDirection.RISING and vix is VixDirection.FALLING:
        return CrossMarketLabel.BTC_VIX_RELIEF_ALIGNMENT
    if crypto is CryptoDirection.FALLING and vix is VixDirection.RISING:
        return CrossMarketLabel.BTC_VIX_STRESS_ALIGNMENT
    if (
        crypto is CryptoDirection.RISING
        and vix is VixDirection.RISING
    ) or (
        crypto is CryptoDirection.FALLING
        and vix is VixDirection.FALLING
    ):
        return CrossMarketLabel.BTC_VIX_SAME_DIRECTION
    return CrossMarketLabel.MIXED


def _unresolved(
    *,
    as_of_ms: int,
    vix: CrossMarketWindowObservation | None,
    treasury: CrossMarketWindowObservation | None,
    flags: tuple[str, ...],
) -> CrossMarketAnalysis:
    payload = {
        "as_of_ms": as_of_ms,
        "crypto_direction": CryptoDirection.UNAVAILABLE,
        "engine_version": CROSS_MARKET_ENGINE_VERSION,
        "label": CrossMarketLabel.UNRESOLVED,
        "metrics": None,
        "rates_direction": RatesDirection.UNAVAILABLE,
        "treasury_observed_at_ms": (
            None if treasury is None else treasury.observed_at_ms
        ),
        "uncertainty_flags": flags,
        "vix_direction": VixDirection.UNAVAILABLE,
        "vix_observed_at_ms": None if vix is None else vix.observed_at_ms,
    }
    return CrossMarketAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=CROSS_MARKET_ENGINE_VERSION,
        as_of_ms=as_of_ms,
        vix_observed_at_ms=None if vix is None else vix.observed_at_ms,
        treasury_observed_at_ms=(
            None if treasury is None else treasury.observed_at_ms
        ),
        label=CrossMarketLabel.UNRESOLVED,
        crypto_direction=CryptoDirection.UNAVAILABLE,
        vix_direction=VixDirection.UNAVAILABLE,
        rates_direction=RatesDirection.UNAVAILABLE,
        metrics=None,
        uncertainty_flags=flags,
    )


def _freeze(
    *,
    analysis: CrossMarketAnalysis,
    vix: CrossMarketWindowObservation | None,
    treasury: CrossMarketWindowObservation | None,
    btc_candles: tuple[Candle, ...],
) -> CrossMarketEvidenceFreeze:
    payload = {
        "analysis_identity": analysis.evidence_identity,
        "btc_candles": [_candle_payload(item) for item in btc_candles],
        "schema_version": CROSS_MARKET_FREEZE_SCHEMA_VERSION,
        "treasury_observation_identity": (
            None if treasury is None else treasury.observation_identity
        ),
        "vix_observation_identity": (
            None if vix is None else vix.observation_identity
        ),
    }
    return CrossMarketEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=CROSS_MARKET_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        vix_observation=vix,
        treasury_observation=treasury,
        btc_candles=btc_candles,
    )


def _candle_payload(candle: Candle) -> dict[str, object]:
    return {
        "adapter_version": candle.adapter_version,
        "close": candle.close,
        "close_time_ms": candle.close_time_ms,
        "exchange": candle.exchange,
        "high": candle.high,
        "ingested_at_ms": candle.ingested_at_ms,
        "is_closed": candle.is_closed,
        "low": candle.low,
        "market_type": candle.market_type,
        "open": candle.open,
        "open_time_ms": candle.open_time_ms,
        "quote_volume": candle.quote_volume,
        "source": candle.source,
        "source_timestamp_ms": candle.source_timestamp_ms,
        "symbol": candle.symbol,
        "timeframe": candle.timeframe,
        "trade_count": candle.trade_count,
        "volume": candle.volume,
    }


def _metrics_payload(metrics: CrossMarketMetrics) -> dict[str, object]:
    return {
        "btc_return_pct": metrics.btc_return_pct,
        "common_session_count": metrics.common_session_count,
        "end_day_ms": metrics.end_day_ms,
        "start_day_ms": metrics.start_day_ms,
        "treasury_10y_change_bps": metrics.treasury_10y_change_bps,
        "vix_change_pct": metrics.vix_change_pct,
    }


def _analysis_payload(analysis: CrossMarketAnalysis) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "crypto_direction": analysis.crypto_direction,
        "engine_version": analysis.engine_version,
        "label": analysis.label,
        "metrics": (
            None if analysis.metrics is None else _metrics_payload(analysis.metrics)
        ),
        "rates_direction": analysis.rates_direction,
        "treasury_observed_at_ms": analysis.treasury_observed_at_ms,
        "uncertainty_flags": analysis.uncertainty_flags,
        "vix_direction": analysis.vix_direction,
        "vix_observed_at_ms": analysis.vix_observed_at_ms,
    }


def _freeze_payload(freeze: CrossMarketEvidenceFreeze) -> dict[str, object]:
    return {
        "analysis_identity": freeze.analysis.evidence_identity,
        "btc_candles": [_candle_payload(item) for item in freeze.btc_candles],
        "schema_version": freeze.schema_version,
        "treasury_observation_identity": (
            None
            if freeze.treasury_observation is None
            else freeze.treasury_observation.observation_identity
        ),
        "vix_observation_identity": (
            None
            if freeze.vix_observation is None
            else freeze.vix_observation.observation_identity
        ),
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
