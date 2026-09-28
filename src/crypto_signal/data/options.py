from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.ledger.serialization import canonical_sha256


class OptionType(StrEnum):
    CALL = "call"
    PUT = "put"


@dataclass(frozen=True, slots=True)
class OptionInstrumentSpec:
    instrument_identity: str
    exchange: Exchange
    symbol: str
    base_coin: str
    quote_coin: str
    settle_coin: str
    option_type: OptionType
    strike: Decimal
    expiry_at_ms: int
    status: str
    source: DataSource
    source_timestamp_ms: int
    observed_at_ms: int
    ingested_at_ms: int
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.instrument_identity, "option instrument identity")
        _require_uppercase(self.symbol, "option instrument symbol")
        _require_uppercase(self.base_coin, "option base coin")
        _require_uppercase(self.quote_coin, "option quote coin")
        _require_uppercase(self.settle_coin, "option settle coin")
        _require_positive(self.strike, "option strike")
        if min(
            self.expiry_at_ms,
            self.source_timestamp_ms,
            self.observed_at_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("option instrument timestamps must be non-negative")
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
    exchange: Exchange
    symbol: str
    base_coin: str
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
    source: DataSource
    source_timestamp_ms: int
    observed_at_ms: int
    ingested_at_ms: int
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.quote_identity, "option quote identity")
        _require_sha256(self.instrument_identity, "option quote instrument identity")
        _require_uppercase(self.symbol, "option quote symbol")
        _require_uppercase(self.base_coin, "option quote base coin")
        _require_positive(self.strike, "option quote strike")
        if min(
            self.expiry_at_ms,
            self.source_timestamp_ms,
            self.observed_at_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("option quote timestamps must be non-negative")
        if self.observed_at_ms > self.ingested_at_ms:
            raise ValueError("option quote observation cannot postdate ingestion")

        for label, value in (
            ("mark_iv", self.mark_iv),
            ("bid_iv", self.bid_iv),
            ("ask_iv", self.ask_iv),
            ("mark_price", self.mark_price),
            ("index_price", self.index_price),
            ("underlying_price", self.underlying_price),
            ("open_interest", self.open_interest),
            ("volume_24h", self.volume_24h),
            ("turnover_24h", self.turnover_24h),
        ):
            _require_non_negative_optional(value, label)
        for label, value in (
            ("delta", self.delta),
            ("gamma", self.gamma),
            ("vega", self.vega),
            ("theta", self.theta),
        ):
            _require_finite_optional(value, label)
        if self.delta is not None and not Decimal(-1) <= self.delta <= Decimal(1):
            raise ValueError("option delta must be inside [-1,1]")
        if all(
            value is None
            for value in (
                self.mark_iv,
                self.bid_iv,
                self.ask_iv,
                self.mark_price,
                self.index_price,
                self.underlying_price,
                self.open_interest,
                self.volume_24h,
            )
        ):
            raise ValueError("option quote requires at least one provider measurement")
        if not self.adapter_version.strip():
            raise ValueError("option quote adapter_version must be non-empty")
        if self.quote_identity != canonical_sha256(option_contract_quote_payload(self)):
            raise ValueError("option quote identity mismatch")


@dataclass(frozen=True, slots=True)
class OptionSurfaceObservation:
    surface_identity: str
    exchange: Exchange
    base_coin: str
    instrument_metadata_identity: str
    contracts: tuple[OptionContractQuote, ...]
    source: DataSource
    source_timestamp_ms: int
    observed_at_ms: int
    ingested_at_ms: int
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.surface_identity, "option surface identity")
        _require_sha256(
            self.instrument_metadata_identity,
            "option surface instrument metadata identity",
        )
        _require_uppercase(self.base_coin, "option surface base coin")
        if min(
            self.source_timestamp_ms,
            self.observed_at_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("option surface timestamps must be non-negative")
        if self.observed_at_ms > self.ingested_at_ms:
            raise ValueError("option surface observation cannot postdate ingestion")
        if not self.contracts:
            raise ValueError("option surface requires at least one contract quote")
        if self.contracts != _canonical_contracts(self.contracts):
            raise ValueError("option surface contract quotes must be canonical")

        symbols = tuple(item.symbol for item in self.contracts)
        instrument_identities = tuple(
            item.instrument_identity for item in self.contracts
        )
        if len(symbols) != len(set(symbols)):
            raise ValueError("option surface contains duplicate symbols")
        if len(instrument_identities) != len(set(instrument_identities)):
            raise ValueError("option surface contains duplicate instruments")
        for contract in self.contracts:
            if contract.exchange is not self.exchange:
                raise ValueError("option surface exchange mismatch")
            if contract.base_coin != self.base_coin:
                raise ValueError("option surface base coin mismatch")
            if (
                contract.source is not self.source
                or contract.source_timestamp_ms != self.source_timestamp_ms
                or contract.observed_at_ms != self.observed_at_ms
                or contract.ingested_at_ms != self.ingested_at_ms
            ):
                raise ValueError("option surface quote snapshot mismatch")
            if contract.adapter_version != self.adapter_version:
                raise ValueError("option surface adapter version mismatch")

        if not self.adapter_version.strip():
            raise ValueError("option surface adapter_version must be non-empty")
        if self.surface_identity != canonical_sha256(
            option_surface_observation_payload(self)
        ):
            raise ValueError("option surface identity mismatch")


def build_option_instrument_spec(
    *,
    exchange: Exchange,
    symbol: str,
    base_coin: str,
    quote_coin: str,
    settle_coin: str,
    option_type: OptionType,
    strike: Decimal,
    expiry_at_ms: int,
    status: str,
    source: DataSource,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    adapter_version: str,
) -> OptionInstrumentSpec:
    payload = {
        "adapter_version": adapter_version,
        "base_coin": base_coin,
        "exchange": exchange,
        "expiry_at_ms": expiry_at_ms,
        "ingested_at_ms": ingested_at_ms,
        "observed_at_ms": observed_at_ms,
        "option_type": option_type,
        "quote_coin": quote_coin,
        "settle_coin": settle_coin,
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
        base_coin=base_coin,
        quote_coin=quote_coin,
        settle_coin=settle_coin,
        option_type=option_type,
        strike=strike,
        expiry_at_ms=expiry_at_ms,
        status=status,
        source=source,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
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
    source: DataSource,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    adapter_version: str,
) -> OptionContractQuote:
    payload = {
        "adapter_version": adapter_version,
        "ask_iv": ask_iv,
        "base_coin": instrument.base_coin,
        "bid_iv": bid_iv,
        "delta": delta,
        "exchange": instrument.exchange,
        "expiry_at_ms": instrument.expiry_at_ms,
        "gamma": gamma,
        "index_price": index_price,
        "ingested_at_ms": ingested_at_ms,
        "instrument_identity": instrument.instrument_identity,
        "mark_iv": mark_iv,
        "mark_price": mark_price,
        "observed_at_ms": observed_at_ms,
        "open_interest": open_interest,
        "option_type": instrument.option_type,
        "source": source,
        "source_timestamp_ms": source_timestamp_ms,
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
        exchange=instrument.exchange,
        symbol=instrument.symbol,
        base_coin=instrument.base_coin,
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
        source=source,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=adapter_version,
    )


def build_option_instrument_metadata_identity(
    *,
    exchange: Exchange,
    base_coin: str,
    instrument_specs: tuple[OptionInstrumentSpec, ...],
) -> str:
    _require_uppercase(base_coin, "option metadata base coin")
    if not instrument_specs:
        raise ValueError("option metadata requires at least one instrument")

    identities: list[str] = []
    for instrument in instrument_specs:
        if instrument.exchange is not exchange or instrument.base_coin != base_coin:
            raise ValueError("option metadata instrument context mismatch")
        identities.append(instrument.instrument_identity)

    canonical_identities = tuple(sorted(set(identities)))
    if len(canonical_identities) != len(identities):
        raise ValueError("option metadata cannot contain duplicate instruments")
    return canonical_sha256(
        {
            "base_coin": base_coin,
            "exchange": exchange,
            "instrument_identities": canonical_identities,
            "version": "options-instrument-metadata-v1/1",
        }
    )


def build_option_surface_observation(
    *,
    exchange: Exchange,
    base_coin: str,
    instrument_metadata_identity: str,
    contracts: tuple[OptionContractQuote, ...],
    source: DataSource,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    adapter_version: str,
) -> OptionSurfaceObservation:
    canonical_contracts = _canonical_contracts(contracts)
    payload = {
        "adapter_version": adapter_version,
        "base_coin": base_coin,
        "contract_quote_identities": tuple(
            item.quote_identity for item in canonical_contracts
        ),
        "exchange": exchange,
        "ingested_at_ms": ingested_at_ms,
        "instrument_metadata_identity": instrument_metadata_identity,
        "observed_at_ms": observed_at_ms,
        "source": source,
        "source_timestamp_ms": source_timestamp_ms,
    }
    return OptionSurfaceObservation(
        surface_identity=canonical_sha256(payload),
        exchange=exchange,
        base_coin=base_coin,
        instrument_metadata_identity=instrument_metadata_identity,
        contracts=canonical_contracts,
        source=source,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=adapter_version,
    )


def option_instrument_spec_payload(
    instrument: OptionInstrumentSpec,
) -> dict[str, object]:
    return {
        "adapter_version": instrument.adapter_version,
        "base_coin": instrument.base_coin,
        "exchange": instrument.exchange,
        "expiry_at_ms": instrument.expiry_at_ms,
        "ingested_at_ms": instrument.ingested_at_ms,
        "observed_at_ms": instrument.observed_at_ms,
        "option_type": instrument.option_type,
        "quote_coin": instrument.quote_coin,
        "settle_coin": instrument.settle_coin,
        "source": instrument.source,
        "source_timestamp_ms": instrument.source_timestamp_ms,
        "status": instrument.status,
        "strike": instrument.strike,
        "symbol": instrument.symbol,
    }


def option_contract_quote_payload(quote: OptionContractQuote) -> dict[str, object]:
    return {
        "adapter_version": quote.adapter_version,
        "ask_iv": quote.ask_iv,
        "base_coin": quote.base_coin,
        "bid_iv": quote.bid_iv,
        "delta": quote.delta,
        "exchange": quote.exchange,
        "expiry_at_ms": quote.expiry_at_ms,
        "gamma": quote.gamma,
        "index_price": quote.index_price,
        "ingested_at_ms": quote.ingested_at_ms,
        "instrument_identity": quote.instrument_identity,
        "mark_iv": quote.mark_iv,
        "mark_price": quote.mark_price,
        "observed_at_ms": quote.observed_at_ms,
        "open_interest": quote.open_interest,
        "option_type": quote.option_type,
        "source": quote.source,
        "source_timestamp_ms": quote.source_timestamp_ms,
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
        "base_coin": surface.base_coin,
        "contract_quote_identities": tuple(
            item.quote_identity for item in surface.contracts
        ),
        "exchange": surface.exchange,
        "ingested_at_ms": surface.ingested_at_ms,
        "instrument_metadata_identity": surface.instrument_metadata_identity,
        "observed_at_ms": surface.observed_at_ms,
        "source": surface.source,
        "source_timestamp_ms": surface.source_timestamp_ms,
    }


def _canonical_contracts(
    contracts: tuple[OptionContractQuote, ...],
) -> tuple[OptionContractQuote, ...]:
    return tuple(
        sorted(
            contracts,
            key=lambda item: (
                item.expiry_at_ms,
                item.strike,
                item.option_type.value,
                item.symbol,
                item.quote_identity,
            ),
        )
    )


def _require_uppercase(value: str, label: str) -> None:
    if not value or value != value.upper():
        raise ValueError(f"{label} must be non-empty uppercase")


def _require_positive(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite() or value <= Decimal(0):
        raise ValueError(f"{label} must be finite and positive")


def _require_non_negative_optional(value: Decimal | None, label: str) -> None:
    if value is None:
        return
    _require_finite_optional(value, label)
    if value < Decimal(0):
        raise ValueError(f"{label} cannot be negative")


def _require_finite_optional(value: Decimal | None, label: str) -> None:
    if value is not None and (value.is_nan() or value.is_infinite()):
        raise ValueError(f"{label} must be finite")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
