from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.data.timeframes import spec

BASE_TIMEFRAME = "15m"
COVERAGE_PLAN_VERSION = "live-coverage-v1/3"
SUPPORTED_TARGET_TIMEFRAMES = ("15m", "1h", "4h", "1D", "1W")


class LiveCoverageSourceStrategy(StrEnum):
    DIRECT_CANONICAL_15M = "direct_canonical_15m"
    AGGREGATE_CANONICAL_15M = "aggregate_canonical_15m"


@dataclass(frozen=True, slots=True)
class LiveCoverageContext:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    source_strategy: LiveCoverageSourceStrategy
    freeze_limit: int = 500
    minimum_closed_candles: int = 100
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.market_type is not MarketType.SPOT:
            raise ValueError(
                "post-V1 live coverage currently supports Spot only"
            )
        if not self.symbol.strip():
            raise ValueError("live coverage symbol must be non-empty")
        if self.timeframe not in SUPPORTED_TARGET_TIMEFRAMES:
            raise ValueError("unsupported live coverage timeframe")
        if self.freeze_limit <= 0:
            raise ValueError("live coverage freeze limit must be positive")
        if self.minimum_closed_candles <= 0:
            raise ValueError(
                "live coverage minimum history must be positive"
            )
        if self.minimum_closed_candles > self.freeze_limit:
            raise ValueError(
                "live coverage minimum history cannot exceed freeze limit"
            )

        if self.timeframe == BASE_TIMEFRAME:
            if (
                self.source_strategy
                is not LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M
            ):
                raise ValueError(
                    "15m coverage must use direct canonical 15m source"
                )
        elif (
            self.source_strategy
            is not LiveCoverageSourceStrategy.AGGREGATE_CANONICAL_15M
        ):
            raise ValueError(
                "higher-timeframe coverage must aggregate canonical 15m"
            )

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            self.exchange.value,
            self.market_type.value,
            self.symbol,
            self.timeframe,
        )

    @property
    def base_15m_candles_for_freeze_limit(self) -> int:
        ratio = spec(self.timeframe).duration_ms // spec(BASE_TIMEFRAME).duration_ms
        return self.freeze_limit * ratio

    @property
    def base_15m_candles_for_minimum_history(self) -> int:
        ratio = spec(self.timeframe).duration_ms // spec(BASE_TIMEFRAME).duration_ms
        return self.minimum_closed_candles * ratio


@dataclass(frozen=True, slots=True)
class LiveCoveragePlan:
    version: str
    contexts: tuple[LiveCoverageContext, ...]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("live coverage plan version must be non-empty")
        if not self.contexts:
            raise ValueError("live coverage plan requires contexts")
        identities = [context.identity for context in self.contexts]
        if len(set(identities)) != len(identities):
            raise ValueError(
                "live coverage contexts must be unique by market identity"
            )

    @property
    def enabled_contexts(self) -> tuple[LiveCoverageContext, ...]:
        return tuple(context for context in self.contexts if context.enabled)

    @property
    def enabled_base_15m_budget_per_run(self) -> int:
        return sum(
            context.base_15m_candles_for_freeze_limit
            for context in self.enabled_contexts
        )

    @classmethod
    def current_pilot(cls) -> LiveCoveragePlan:
        contexts: list[LiveCoverageContext] = []
        for exchange in (Exchange.BYBIT, Exchange.BINANCE):
            for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
                contexts.append(
                    LiveCoverageContext(
                        exchange=exchange,
                        market_type=MarketType.SPOT,
                        symbol=symbol,
                        timeframe="15m",
                        source_strategy=(
                            LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M
                        ),
                    )
                )
                for timeframe in ("1h", "4h"):
                    contexts.append(
                        LiveCoverageContext(
                            exchange=exchange,
                            market_type=MarketType.SPOT,
                            symbol=symbol,
                            timeframe=timeframe,
                            source_strategy=(
                                LiveCoverageSourceStrategy.AGGREGATE_CANONICAL_15M
                            ),
                            freeze_limit=120,
                            minimum_closed_candles=100,
                        )
                    )
        return cls(
            version=COVERAGE_PLAN_VERSION,
            contexts=tuple(contexts),
        )

    @classmethod
    def post_v1_timeframe_candidates(cls) -> LiveCoveragePlan:
        contexts: list[LiveCoverageContext] = []
        for exchange in (Exchange.BYBIT, Exchange.BINANCE):
            for timeframe in SUPPORTED_TARGET_TIMEFRAMES:
                contexts.append(
                    LiveCoverageContext(
                        exchange=exchange,
                        market_type=MarketType.SPOT,
                        symbol="BTCUSDT",
                        timeframe=timeframe,
                        source_strategy=(
                            LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M
                            if timeframe == BASE_TIMEFRAME
                            else LiveCoverageSourceStrategy.AGGREGATE_CANONICAL_15M
                        ),
                        enabled=timeframe == BASE_TIMEFRAME,
                    )
                )
        return cls(
            version="post-v1-timeframe-candidates/1",
            contexts=tuple(contexts),
        )
