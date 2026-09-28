from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.ledger.serialization import canonical_sha256

OPTIONS_CONTRACT_VERSION = "options-contract-v1/1"


class OptionType(StrEnum):
    CALL = "call"
    PUT = "put"


@dataclass(frozen=True, slots=True)
class OptionInstrumentSpec:
    instrument_identity: str
    exchange: Exchange
    symbol: str
    base_asset: str
    quote_asset: str
    settle_asset: str
    option_type: OptionType
    strike: Decimal
    expiry_at_ms: int
    status: str
    source_timestamp_ms: int
    observed_at_ms: int
    ingested_at_ms: int
    source: DataSource
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.instrument_identity, "option instrument identity")
        for label, value in (
            ("symbol", self.symbol),
            ("base_asset", self.base_asset),
            ("quote_asset", self.quote_asset),
            ("settle_asset", self.settle_asset),
        ):
            _require_uppercase(value, label)
        _require_positive_decimal(self.strike, "option strike")
        if min(
            self.expiry_at_ms,
            self.source_timestamp_ms,
            self.observed_at_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("option instrument timestamps cannot be negative")
        if self.observed_at_ms > self.ingested_at_ms:
            raise ValueError("option instrument observation cannot postdate ingestion")
        if not self.status.strip():
            raise ValueError("option instrument status must be non-empty")
        if not self.adapter_version.strip():
            raise ValueError("option instrument adapter_version must be non-empty")
        if self.instrument_identity != canonical_sha256(
            option_instrument_spec_payload(self)
        ):
            raise ValueError("option instrument identity mismatch")


@dataclass(frozen=True, slots=True)
class OptionContractQuote:
    quote_identity: str
    instrument_identity: str
    symbol: str
    option_type: OptionType
    strike: Decimal
    expiry_at_ms: int
    mark_iv: Decimal | None
    bid_iv: Decimal | None
    ask_iv: Decimal | None
    mark_price: Decimal | None
    index_price: Decimal | None
    underlying_price: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    vega: Decimal | None
    theta: Decimal | None
    open_interest: Decimal | None
    volume_24h: Decimal | None
    turnover_24h: Decimal | None

    def __post_init__(self) -> None:
        _require_sha256(self.quote_identity, "option quote identity")
        _require_sha256(self.instrument_identity, "option instrument identity")
        _require_uppercase(self.symbol, "option quote symbol")
        _require_positive_decimal(self.strike, "option quote strike")
        if self.expiry_at_ms < 0:
            raise ValueError("option quote expiry cannot be negative")

        for label, value in (
            ("mark_iv", self.mark_iv),
            ("bid_iv", self.bid_iv),
            ("ask_iv", self.ask_iv),
        ):
            _require_non_negative_decimal_or_none(value, label)
        for label, value in (
            ("mark_price", self.mark_price),
            ("index_price", self.index_price),
            ("underlying_price", self.underlying_price),
        ):
            _require_positive_decimal_or_none(value, label)
        for label, value in (
            ("open_interest", self.open_interest),
            ("volume_24h", self.volume_24h),
            ("turnover_24h", self.turnover_24h),
        ):
            _require_non_negative_decimal_or_none(value, label)
        for label, value in (
            ("delta", self.delta),
            ("gamma", self.gamma),
            ("vega", self.vega),
            ("theta", self.theta),
        ):
            _require_finite_decimal_or_none(value, label)
        if self.delta is not None and not Decimal(-1) <= self.delta <= Decimal(1):
            raise ValueError("option delta must be inside [-1, 1]")

        if self.quote_identity != canonical_sha256(option_contract_quote_payload(self)):
            raise ValueError("option quote identity mismatch")


@dataclass(frozen=True, slots=True)
class OptionSurfaceObservation:
    surface_identity: str
    exchange: Exchange
    base_asset: str
    source_timestamp_ms: int
    observed_at_ms: int
    ingested_at_ms: int
    source: DataSource
    adapter_version: str
    instrument_metadata_identity: str
    quotes: tuple[OptionContractQuote, ...]
    contract_version: str = OPTIONS_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.surface_identity, "option surface identity")
        _require_sha256(
            self.instrument_metadata_identity,
            "option instrument metadata identity",
        )
        _require_uppercase(self.base_asset, "option surface base_asset")
        if self.contract_version != OPTIONS_CONTRACT_VERSION:
            raise ValueError("unsupported options contract version")
        if min(
            self.source_timestamp_ms,
            self.observed_at_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("option surface timestamps cannot be negative")
        if self.observed_at_ms > self.ingested_at_ms:
            raise ValueError("option surface observation cannot postdate ingestion")
        if not self.adapter_version.strip():
            raise ValueError("option surface adapter_version must be non-empty")

        canonical_quotes = tuple(
            sorted(
                self.quotes,
                key=lambda item: (item.symbol, item.quote_identity),
            )
        )
        if canonical_quotes != self.quotes:
            raise ValueError("option surface quotes must be canonical")
        symbols = tuple(item.symbol for item in self.quotes)
        if len(set(symbols)) != len(symbols):
            raise ValueError("option surface cannot contain duplicate symbols")
        instrument_ids = tuple(item.instrument_identity for item in self.quotes)
        if len(set(instrument_ids)) != len(instrument_ids):
            raise ValueError("option surface cannot contain duplicate instruments")

        if self.surface_identity != canonical_sha256(
            option_surface_observation_payload(self)
        ):
            raise ValueError("option surface identity mismatch")


def build_option_instrument_spec(
    *,
    exchange: Exchange,
    symbol: str,
    base_asset: str,
    quote_asset: str,
    settle_asset: str,
    option_type: OptionType,
    strike: Decimal,
    expiry_at_ms: int,
    status: str,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    source: DataSource,
    adapter_version: str,
) -> OptionInstrumentSpec:
    payload = {
        "adapter_version": adapter_version,
        "base_asset": base_asset,
        "exchange": exchange,
        "expiry_at_ms": expiry_at_ms,
        "ingested_at_ms": ingested_at_ms,
        "observed_at_ms": observed_at_ms,
        "option_type": option_type,
        "quote_asset": quote_asset,
        "settle_asset": settle_asset,
        "source": source,
        "source_timestamp_ms": source_timestamp_ms,
        "status": status,
        "strike": strike,
        "symbol": symbol,
    }
    return OptionInstrumentSpec(
        instrument_identity=canonical_sha256(payload),
        exchange=exchange,
        symbol=symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        settle_asset=settle_asset,
        option_type=option_type,
        strike=strike,
        expiry_at_ms=expiry_at_ms,
        status=status,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        source=source,
        adapter_version=adapter_version,
    )


def build_option_contract_quote(
    *,
    instrument: OptionInstrumentSpec,
    mark_iv: Decimal | None,
    bid_iv: Decimal | None,
    ask_iv: Decimal | None,
    mark_price: Decimal | None,
    index_price: Decimal | None,
    underlying_price: Decimal | None,
    delta: Decimal | None,
    gamma: Decimal | None,
    vega: Decimal | None,
    theta: Decimal | None,
    open_interest: Decimal | None,
    volume_24h: Decimal | None,
    turnover_24h: Decimal | None,
) -> OptionContractQuote:
    payload = {
        "ask_iv": ask_iv,
        "bid_iv": bid_iv,
        "delta": delta,
        "expiry_at_ms": instrument.expiry_at_ms,
        "gamma": gamma,
        "index_price": index_price,
        "instrument_identity": instrument.instrument_identity,
        "mark_iv": mark_iv,
        "mark_price": mark_price,
        "open_interest": open_interest,
        "option_type": instrument.option_type,
        "strike": instrument.strike,
        "symbol": instrument.symbol,
        "theta": theta,
        "turnover_24h": turnover_24h,
        "underlying_price": underlying_price,
        "vega": vega,
        "volume_24h": volume_24h,
    }
    return OptionContractQuote(
        quote_identity=canonical_sha256(payload),
        instrument_identity=instrument.instrument_identity,
        symbol=instrument.symbol,
        option_type=instrument.option_type,
        strike=instrument.strike,
        expiry_at_ms=instrument.expiry_at_ms,
        mark_iv=mark_iv,
        bid_iv=bid_iv,
        ask_iv=ask_iv,
        mark_price=mark_price,
        index_price=index_price,
        underlying_price=underlying_price,
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        open_interest=open_interest,
        volume_24h=volume_24h,
        turnover_24h=turnover_24h,
    )


def build_option_surface_observation(
    *,
    exchange: Exchange,
    base_asset: str,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    source: DataSource,
    adapter_version: str,
    instrument_specs: tuple[OptionInstrumentSpec, ...],
    quotes: tuple[OptionContractQuote, ...],
) -> OptionSurfaceObservation:
    _require_uppercase(base_asset, "option surface base_asset")
    if not instrument_specs:
        raise ValueError("option surface requires instrument metadata")

    specs_by_identity: dict[str, OptionInstrumentSpec] = {}
    for spec in instrument_specs:
        if spec.exchange is not exchange or spec.base_asset != base_asset:
            raise ValueError("option surface instrument metadata context mismatch")
        if spec.instrument_identity in specs_by_identity:
            raise ValueError("option surface instrument metadata contains duplicates")
        specs_by_identity[spec.instrument_identity] = spec

    for quote in quotes:
        spec = specs_by_identity.get(quote.instrument_identity)
        if spec is None:
            raise ValueError("option quote is missing exact instrument metadata")
        if (
            quote.symbol != spec.symbol
            or quote.option_type is not spec.option_type
            or quote.strike != spec.strike
            or quote.expiry_at_ms != spec.expiry_at_ms
        ):
            raise ValueError("option quote conflicts with instrument metadata")

    metadata_identity = build_option_instrument_metadata_identity(
        exchange=exchange,
        base_asset=base_asset,
        instrument_specs=instrument_specs,
    )
    canonical_quotes = tuple(
        sorted(quotes, key=lambda item: (item.symbol, item.quote_identity))
    )
    payload = {
        "adapter_version": adapter_version,
        "base_asset": base_asset,
        "contract_version": OPTIONS_CONTRACT_VERSION,
        "exchange": exchange,
        "ingested_at_ms": ingested_at_ms,
        "instrument_metadata_identity": metadata_identity,
        "observed_at_ms": observed_at_ms,
        "quotes": canonical_quotes,
        "source": source,
        "source_timestamp_ms": source_timestamp_ms,
    }
    return OptionSurfaceObservation(
        surface_identity=canonical_sha256(payload),
        exchange=exchange,
        base_asset=base_asset,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        source=source,
        adapter_version=adapter_version,
        instrument_metadata_identity=metadata_identity,
        quotes=canonical_quotes,
    )


def build_option_instrument_metadata_identity(
    *,
    exchange: Exchange,
    base_asset: str,
    instrument_specs: tuple[OptionInstrumentSpec, ...],
) -> str:
    _require_uppercase(base_asset, "option metadata base_asset")
    if not instrument_specs:
        raise ValueError("option metadata requires at least one instrument")
    identities: list[str] = []
    for spec in instrument_specs:
        if spec.exchange is not exchange or spec.base_asset != base_asset:
            raise ValueError("option metadata context mismatch")
        identities.append(spec.instrument_identity)
    canonical_identities = tuple(sorted(set(identities)))
    if len(canonical_identities) != len(identities):
        raise ValueError("option metadata cannot contain duplicate instruments")
    return canonical_sha256(
        {
            "base_asset": base_asset,
            "exchange": exchange,
            "instrument_identities": canonical_identities,
            "version": "options-instrument-metadata-v1/1",
        }
    )


def option_instrument_spec_payload(
    spec: OptionInstrumentSpec,
) -> dict[str, object]:
    return {
        "adapter_version": spec.adapter_version,
        "base_asset": spec.base_asset,
        "exchange": spec.exchange,
        "expiry_at_ms": spec.expiry_at_ms,
        "ingested_at_ms": spec.ingested_at_ms,
        "observed_at_ms": spec.observed_at_ms,
        "option_type": spec.option_type,
        "quote_asset": spec.quote_asset,
        "settle_asset": spec.settle_asset,
        "source": spec.source,
        "source_timestamp_ms": spec.source_timestamp_ms,
        "status": spec.status,
        "strike": spec.strike,
        "symbol": spec.symbol,
    }


def option_contract_quote_payload(
    quote: OptionContractQuote,
) -> dict[str, object]:
    return {
        "ask_iv": quote.ask_iv,
        "bid_iv": quote.bid_iv,
        "delta": quote.delta,
        "expiry_at_ms": quote.expiry_at_ms,
        "gamma": quote.gamma,
        "index_price": quote.index_price,
        "instrument_identity": quote.instrument_identity,
        "mark_iv": quote.mark_iv,
        "mark_price": quote.mark_price,
        "open_interest": quote.open_interest,
        "option_type": quote.option_type,
        "strike": quote.strike,
        "symbol": quote.symbol,
        "theta": quote.theta,
        "turnover_24h": quote.turnover_24h,
        "underlying_price": quote.underlying_price,
        "vega": quote.vega,
        "volume_24h": quote.volume_24h,
    }


def option_surface_observation_payload(
    surface: OptionSurfaceObservation,
) -> dict[str, object]:
    return {
        "adapter_version": surface.adapter_version,
        "base_asset": surface.base_asset,
        "contract_version": surface.contract_version,
        "exchange": surface.exchange,
        "ingested_at_ms": surface.ingested_at_ms,
        "instrument_metadata_identity": surface.instrument_metadata_identity,
        "observed_at_ms": surface.observed_at_ms,
        "quotes": surface.quotes,
        "source": surface.source,
        "source_timestamp_ms": surface.source_timestamp_ms,
    }


def _require_uppercase(value: str, label: str) -> None:
    if not value or value != value.upper():
        raise ValueError(f"{label} must be non-empty uppercase")


def _require_positive_decimal(value: Decimal, label: str) -> None:
    _require_finite_decimal(value, label)
    if value <= Decimal(0):
        raise ValueError(f"{label} must be positive")


def _require_positive_decimal_or_none(
    value: Decimal | None,
    label: str,
) -> None:
    if value is None:
        return
    _require_positive_decimal(value, label)


def _require_non_negative_decimal_or_none(
    value: Decimal | None,
    label: str,
) -> None:
    if value is None:
        return
    _require_finite_decimal(value, label)
    if value < Decimal(0):
        raise ValueError(f"{label} cannot be negative")


def _require_finite_decimal_or_none(
    value: Decimal | None,
    label: str,
) -> None:
    if value is not None:
        _require_finite_decimal(value, label)


def _require_finite_decimal(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
