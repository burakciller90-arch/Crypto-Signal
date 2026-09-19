from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from crypto_signal.data.models import Candle, Exchange, MarketType

BASE_TIMEFRAME = "15m"
BASE_DURATION_MS = 15 * 60_000
METHODOLOGY_VERSION = "price-action-levels/1"


class PreviousPeriodKind(StrEnum):
    DAY = "previous_day"
    WEEK = "previous_week"
    MONTH = "previous_month"


@dataclass(frozen=True, slots=True)
class SessionSpec:
    name: str
    timezone: str
    start_local: time
    end_local: time

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("session name must be non-empty")
        if self.start_local == self.end_local:
            raise ValueError("session start and end must differ")
        for value in (self.start_local, self.end_local):
            if value.second != 0 or value.microsecond != 0 or value.minute % 15 != 0:
                raise ValueError("session boundaries must use 15-minute clock alignment")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown session timezone: {self.timezone}") from exc


@dataclass(frozen=True, slots=True)
class HighLowRangeEvidence:
    label: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    start_ms: int
    end_exclusive_ms: int
    expected_count: int
    observed_count: int
    missing_open_times_ms: tuple[int, ...]
    complete: bool
    high: Decimal | None
    low: Decimal | None
    high_candle_identity: tuple[str, str, str, str, int] | None
    low_candle_identity: tuple[str, str, str, str, int] | None
    market_complete_at_ms: int
    observed_at_ms: int | None


@dataclass(frozen=True, slots=True)
class PeriodSessionLevelsResult:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    methodology_version: str
    previous_periods: tuple[tuple[PreviousPeriodKind, HighLowRangeEvidence], ...]
    sessions: tuple[HighLowRangeEvidence, ...]


def _validate_source(candles: Sequence[Candle]) -> None:
    if not candles:
        return

    first = candles[0]
    if first.timeframe != BASE_TIMEFRAME:
        raise ValueError("period/session levels require canonical 15m candles")

    previous_open_ms: int | None = None
    for candle in candles:
        if (
            candle.exchange != first.exchange
            or candle.market_type != first.market_type
            or candle.symbol != first.symbol
            or candle.timeframe != first.timeframe
        ):
            raise ValueError("period/session levels cannot mix candle semantics")
        if not candle.is_closed:
            raise ValueError("period/session levels require closed candles")
        if candle.open_time_ms % BASE_DURATION_MS != 0:
            raise ValueError("period/session candle is off canonical 15m grid")
        if candle.close_time_ms != candle.open_time_ms + BASE_DURATION_MS - 1:
            raise ValueError("period/session candle bounds are invalid")
        if previous_open_ms is not None and candle.open_time_ms <= previous_open_ms:
            raise ValueError("period/session source candles must be strictly chronological")
        previous_open_ms = candle.open_time_ms


def _range_evidence(
    candles: Sequence[Candle],
    *,
    label: str,
    start_ms: int,
    end_exclusive_ms: int,
    as_of_ms: int,
) -> HighLowRangeEvidence:
    if not candles:
        raise ValueError("range evidence requires source candles")
    if start_ms < 0 or end_exclusive_ms <= start_ms:
        raise ValueError("invalid range boundaries")
    if start_ms % BASE_DURATION_MS != 0 or end_exclusive_ms % BASE_DURATION_MS != 0:
        raise ValueError("range boundaries must align to canonical 15m grid")
    if end_exclusive_ms - 1 > as_of_ms:
        raise ValueError("range has not completed by as_of_ms")

    expected_opens = tuple(range(start_ms, end_exclusive_ms, BASE_DURATION_MS))
    in_range = [
        candle
        for candle in candles
        if start_ms <= candle.open_time_ms < end_exclusive_ms
        and candle.close_time_ms <= as_of_ms
        and candle.ingested_at_ms <= as_of_ms
    ]
    by_open = {candle.open_time_ms: candle for candle in in_range}
    if len(by_open) != len(in_range):
        raise ValueError("duplicate candle open time in range evidence")

    missing = tuple(open_ms for open_ms in expected_opens if open_ms not in by_open)
    complete = not missing and len(by_open) == len(expected_opens)
    ordered = [by_open[open_ms] for open_ms in expected_opens if open_ms in by_open]

    high: Decimal | None = None
    low: Decimal | None = None
    high_identity: tuple[str, str, str, str, int] | None = None
    low_identity: tuple[str, str, str, str, int] | None = None
    observed_at_ms: int | None = None

    if complete:
        high_candle = max(ordered, key=lambda candle: (candle.high, -candle.open_time_ms))
        low_candle = min(ordered, key=lambda candle: (candle.low, candle.open_time_ms))
        high = high_candle.high
        low = low_candle.low
        high_identity = high_candle.identity
        low_identity = low_candle.identity
        observed_at_ms = max(candle.ingested_at_ms for candle in ordered)

    first = candles[0]
    return HighLowRangeEvidence(
        label=label,
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        start_ms=start_ms,
        end_exclusive_ms=end_exclusive_ms,
        expected_count=len(expected_opens),
        observed_count=len(by_open),
        missing_open_times_ms=missing,
        complete=complete,
        high=high,
        low=low,
        high_candle_identity=high_identity,
        low_candle_identity=low_identity,
        market_complete_at_ms=end_exclusive_ms - 1,
        observed_at_ms=observed_at_ms,
    )


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _previous_period_bounds(
    kind: PreviousPeriodKind,
    as_of_ms: int,
) -> tuple[int, int]:
    current = datetime.fromtimestamp(as_of_ms / 1000, tz=UTC)
    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)

    if kind is PreviousPeriodKind.DAY:
        end = day_start
        start = end - timedelta(days=1)
    elif kind is PreviousPeriodKind.WEEK:
        end = day_start - timedelta(days=day_start.weekday())
        start = end - timedelta(days=7)
    elif kind is PreviousPeriodKind.MONTH:
        end = day_start.replace(day=1)
        if end.month == 1:
            start = end.replace(year=end.year - 1, month=12)
        else:
            start = end.replace(month=end.month - 1)
    else:
        raise ValueError(f"unsupported previous period: {kind}")

    return _ms(start), _ms(end)


def resolve_previous_periods(
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
) -> tuple[tuple[PreviousPeriodKind, HighLowRangeEvidence], ...]:
    _validate_source(candles)
    if not candles:
        raise ValueError("previous-period levels require candles")

    output: list[tuple[PreviousPeriodKind, HighLowRangeEvidence]] = []
    for kind in PreviousPeriodKind:
        start_ms, end_ms = _previous_period_bounds(kind, as_of_ms)
        output.append(
            (
                kind,
                _range_evidence(
                    candles,
                    label=kind.value,
                    start_ms=start_ms,
                    end_exclusive_ms=end_ms,
                    as_of_ms=as_of_ms,
                ),
            )
        )
    return tuple(output)


def _session_window_for_date(
    local_date: date,
    session: SessionSpec,
) -> tuple[int, int]:
    zone = ZoneInfo(session.timezone)
    start_local = datetime.combine(local_date, session.start_local, tzinfo=zone)
    end_date = (
        local_date + timedelta(days=1)
        if session.end_local < session.start_local
        else local_date
    )
    end_local = datetime.combine(end_date, session.end_local, tzinfo=zone)

    start_ms = _ms(start_local.astimezone(UTC))
    end_ms = _ms(end_local.astimezone(UTC))
    if end_ms <= start_ms:
        raise ValueError("resolved session duration must be positive")
    if start_ms % BASE_DURATION_MS != 0 or end_ms % BASE_DURATION_MS != 0:
        raise ValueError("resolved session window is off canonical 15m grid")
    if (end_ms - start_ms) % BASE_DURATION_MS != 0:
        raise ValueError("resolved session duration is not divisible by 15m")
    return start_ms, end_ms


def latest_completed_session_window(
    *,
    session: SessionSpec,
    as_of_ms: int,
) -> tuple[int, int]:
    zone = ZoneInfo(session.timezone)
    local_now = datetime.fromtimestamp(as_of_ms / 1000, tz=UTC).astimezone(zone)
    candidates: list[tuple[int, int]] = []

    for days_back in range(3):
        candidate_date = local_now.date() - timedelta(days=days_back)
        start_ms, end_ms = _session_window_for_date(candidate_date, session)
        if end_ms - 1 <= as_of_ms:
            candidates.append((start_ms, end_ms))

    if not candidates:
        raise ValueError("no completed session found near as_of_ms")
    return max(candidates, key=lambda item: item[1])


def resolve_latest_completed_session(
    candles: Sequence[Candle],
    *,
    session: SessionSpec,
    as_of_ms: int,
) -> HighLowRangeEvidence:
    _validate_source(candles)
    if not candles:
        raise ValueError("session levels require candles")

    start_ms, end_ms = latest_completed_session_window(
        session=session,
        as_of_ms=as_of_ms,
    )
    return _range_evidence(
        candles,
        label=f"session:{session.name}",
        start_ms=start_ms,
        end_exclusive_ms=end_ms,
        as_of_ms=as_of_ms,
    )


def analyze_period_session_levels(
    candles: Sequence[Candle],
    *,
    sessions: Sequence[SessionSpec] = (),
    as_of_ms: int | None = None,
) -> PeriodSessionLevelsResult:
    if not candles:
        raise ValueError("period/session analysis requires candles")

    effective_as_of_ms = (
        max(candle.ingested_at_ms for candle in candles)
        if as_of_ms is None
        else as_of_ms
    )
    observed = tuple(
        candle
        for candle in candles
        if candle.close_time_ms <= effective_as_of_ms
        and candle.ingested_at_ms <= effective_as_of_ms
    )
    if not observed:
        raise ValueError("no candles were both closed and observed by as_of_ms")

    _validate_source(observed)
    previous_periods = resolve_previous_periods(
        observed,
        as_of_ms=effective_as_of_ms,
    )
    session_ranges = tuple(
        resolve_latest_completed_session(
            observed,
            session=session,
            as_of_ms=effective_as_of_ms,
        )
        for session in sessions
    )

    first = observed[0]
    return PeriodSessionLevelsResult(
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=effective_as_of_ms,
        methodology_version=METHODOLOGY_VERSION,
        previous_periods=previous_periods,
        sessions=session_ranges,
    )
