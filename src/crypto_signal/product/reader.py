from __future__ import annotations

import json
import sqlite3
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_signal.confluence.models import ScoreSemantic
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.outcomes.models import EvidenceClass
from crypto_signal.product.models import (
    AssetCockpitView,
    CommandCenterView,
    EvidenceClassCount,
    FrozenSignalCard,
    MarketRadarItem,
    MarketRadarView,
    PerformanceAvailabilityView,
    ProductDataStatus,
    SignalArchiveView,
    SignalDetailView,
    SignalEvidenceClassStatus,
)
from crypto_signal.signals.models import ProbabilityStatus, SignalDirection, SignalState


class DashboardReadError(ValueError):
    """Raised when immutable product data is malformed or semantically inconsistent."""


class DashboardReader:
    def __init__(self, ledger_path: Path) -> None:
        self.ledger_path = ledger_path

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.ledger_path}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _require_mapping(value: Any, label: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise DashboardReadError(f"{label} must be a mapping")
        return value

    @staticmethod
    def _require_list(value: Any, label: str) -> list[Any]:
        if not isinstance(value, list):
            raise DashboardReadError(f"{label} must be a list")
        return value

    @staticmethod
    def _require_str(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DashboardReadError(f"{label} must be a non-empty string")
        return value

    @staticmethod
    def _require_int(value: Any, label: str) -> int:
        if not isinstance(value, int):
            raise DashboardReadError(f"{label} must be an integer")
        return value

    def _card_from_row(self, row: sqlite3.Row) -> FrozenSignalCard:
        try:
            payload = json.loads(str(row["bundle_json"]))
        except json.JSONDecodeError as exc:
            raise DashboardReadError("bundle_json is not valid JSON") from exc
        root = self._require_mapping(payload, "bundle_json")
        signal = self._require_mapping(root.get("signal_decision"), "signal_decision")
        agreement = self._require_mapping(signal.get("agreement"), "signal agreement")
        flags = self._require_list(signal.get("uncertainty_flags"), "uncertainty_flags")

        try:
            return FrozenSignalCard(
                bundle_identity=self._require_str(
                    row["bundle_identity"],
                    "bundle_identity",
                ),
                signal_freeze_identity=self._require_str(
                    row["signal_freeze_identity"],
                    "signal_freeze_identity",
                ),
                exchange=Exchange(self._require_str(row["exchange"], "exchange")),
                market_type=MarketType(
                    self._require_str(row["market_type"], "market_type")
                ),
                symbol=self._require_str(row["symbol"], "symbol"),
                timeframe=self._require_str(row["timeframe"], "timeframe"),
                as_of_ms=self._require_int(row["as_of_ms"], "as_of_ms"),
                frozen_at_ms=self._require_int(row["frozen_at_ms"], "frozen_at_ms"),
                source_cutoff_open_time_ms=self._require_int(
                    row["source_cutoff_open_time_ms"],
                    "source_cutoff_open_time_ms",
                ),
                state=SignalState(self._require_str(signal.get("state"), "signal state")),
                direction=SignalDirection(
                    self._require_str(signal.get("direction"), "signal direction")
                ),
                setup_type=self._require_str(signal.get("setup_type"), "setup_type"),
                confluence_score=Decimal(
                    self._require_str(
                        agreement.get("confluence_score"),
                        "confluence_score",
                    )
                ),
                confluence_score_semantic=ScoreSemantic(
                    self._require_str(
                        agreement.get("score_semantic"),
                        "score_semantic",
                    )
                ),
                probability_status=ProbabilityStatus(
                    self._require_str(
                        signal.get("probability_status"),
                        "probability_status",
                    )
                ),
                uncertainty_flags=tuple(
                    self._require_str(value, "uncertainty flag")
                    for value in flags
                ),
                evidence_class_status=(
                    SignalEvidenceClassStatus.NOT_EXPLICIT_AT_FREEZE_LEVEL
                ),
            )
        except (ValueError, TypeError) as exc:
            if isinstance(exc, DashboardReadError):
                raise
            raise DashboardReadError("frozen signal row is semantically invalid") from exc

    def _signal_rows(
        self,
        connection: sqlite3.Connection,
        *,
        limit: int | None = None,
        offset: int = 0,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> tuple[sqlite3.Row, ...]:
        clauses: list[str] = []
        params: list[object] = []
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(symbol)
        if timeframe is not None:
            clauses.append("timeframe = ?")
            params.append(timeframe)

        query = "SELECT * FROM signal_freezes"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY frozen_at_ms DESC, bundle_identity DESC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        return tuple(connection.execute(query, params).fetchall())

    def command_center(self, *, recent_limit: int = 8) -> CommandCenterView:
        if recent_limit <= 0:
            raise ValueError("recent_limit must be positive")
        if not self.ledger_path.exists():
            return CommandCenterView(
                status=ProductDataStatus.NO_LEDGER,
                freeze_count=0,
                latest_frozen_at_ms=None,
                state_counts=(),
                direction_counts=(),
                recent_signals=(),
            )
        with self._connect() as connection:
            if not self._table_exists(connection, "signal_freezes"):
                return CommandCenterView(
                    status=ProductDataStatus.SCHEMA_UNAVAILABLE,
                    freeze_count=0,
                    latest_frozen_at_ms=None,
                    state_counts=(),
                    direction_counts=(),
                    recent_signals=(),
                )
            all_rows = self._signal_rows(connection)
            if not all_rows:
                return CommandCenterView(
                    status=ProductDataStatus.EMPTY,
                    freeze_count=0,
                    latest_frozen_at_ms=None,
                    state_counts=(),
                    direction_counts=(),
                    recent_signals=(),
                )
            cards = tuple(self._card_from_row(row) for row in all_rows)
            states = Counter(card.state for card in cards)
            directions = Counter(card.direction for card in cards)
            return CommandCenterView(
                status=ProductDataStatus.READY,
                freeze_count=len(cards),
                latest_frozen_at_ms=max(card.frozen_at_ms for card in cards),
                state_counts=tuple(
                    sorted(states.items(), key=lambda item: item[0].value)
                ),
                direction_counts=tuple(
                    sorted(directions.items(), key=lambda item: item[0].value)
                ),
                recent_signals=cards[:recent_limit],
            )

    def market_radar(self) -> MarketRadarView:
        if not self.ledger_path.exists():
            return MarketRadarView(status=ProductDataStatus.NO_LEDGER, items=())
        with self._connect() as connection:
            if not self._table_exists(connection, "signal_freezes"):
                return MarketRadarView(
                    status=ProductDataStatus.SCHEMA_UNAVAILABLE,
                    items=(),
                )
            rows = self._signal_rows(connection)
            if not rows:
                return MarketRadarView(status=ProductDataStatus.EMPTY, items=())
            latest: dict[
                tuple[Exchange, MarketType, str, str],
                FrozenSignalCard,
            ] = {}
            for row in rows:
                card = self._card_from_row(row)
                key = (
                    card.exchange,
                    card.market_type,
                    card.symbol,
                    card.timeframe,
                )
                latest.setdefault(key, card)
            items = tuple(
                MarketRadarItem(
                    exchange=key[0],
                    market_type=key[1],
                    symbol=key[2],
                    timeframe=key[3],
                    latest=card,
                )
                for key, card in sorted(
                    latest.items(),
                    key=lambda item: (
                        item[0][2],
                        item[0][3],
                        item[0][0].value,
                        item[0][1].value,
                    ),
                )
            )
            return MarketRadarView(status=ProductDataStatus.READY, items=items)

    def asset_cockpit(
        self,
        *,
        symbol: str,
        timeframe: str,
        recent_limit: int = 20,
    ) -> AssetCockpitView:
        if not symbol.strip() or not timeframe.strip():
            raise ValueError("symbol/timeframe must be non-empty")
        if recent_limit <= 0:
            raise ValueError("recent_limit must be positive")
        if not self.ledger_path.exists():
            return AssetCockpitView(
                status=ProductDataStatus.NO_LEDGER,
                symbol=symbol,
                timeframe=timeframe,
                latest_by_provider=(),
                recent_signals=(),
            )
        with self._connect() as connection:
            if not self._table_exists(connection, "signal_freezes"):
                return AssetCockpitView(
                    status=ProductDataStatus.SCHEMA_UNAVAILABLE,
                    symbol=symbol,
                    timeframe=timeframe,
                    latest_by_provider=(),
                    recent_signals=(),
                )
            rows = self._signal_rows(
                connection,
                symbol=symbol,
                timeframe=timeframe,
            )
            if not rows:
                return AssetCockpitView(
                    status=ProductDataStatus.EMPTY,
                    symbol=symbol,
                    timeframe=timeframe,
                    latest_by_provider=(),
                    recent_signals=(),
                )
            cards = tuple(self._card_from_row(row) for row in rows)
            provider_latest: dict[
                tuple[Exchange, MarketType],
                FrozenSignalCard,
            ] = {}
            for card in cards:
                provider_latest.setdefault((card.exchange, card.market_type), card)
            return AssetCockpitView(
                status=ProductDataStatus.READY,
                symbol=symbol,
                timeframe=timeframe,
                latest_by_provider=tuple(
                    card
                    for _, card in sorted(
                        provider_latest.items(),
                        key=lambda item: (
                            item[0][0].value,
                            item[0][1].value,
                        ),
                    )
                ),
                recent_signals=cards[:recent_limit],
            )

    def signal_archive(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> SignalArchiveView:
        if limit <= 0 or offset < 0:
            raise ValueError("archive limit must be positive and offset non-negative")
        if not self.ledger_path.exists():
            return SignalArchiveView(
                status=ProductDataStatus.NO_LEDGER,
                total_count=0,
                offset=offset,
                limit=limit,
                signals=(),
            )
        with self._connect() as connection:
            if not self._table_exists(connection, "signal_freezes"):
                return SignalArchiveView(
                    status=ProductDataStatus.SCHEMA_UNAVAILABLE,
                    total_count=0,
                    offset=offset,
                    limit=limit,
                    signals=(),
                )
            total_row = connection.execute(
                "SELECT COUNT(*) AS count FROM signal_freezes"
            ).fetchone()
            total = 0 if total_row is None else int(total_row["count"])
            rows = self._signal_rows(
                connection,
                limit=limit,
                offset=offset,
            )
            cards = tuple(self._card_from_row(row) for row in rows)
            return SignalArchiveView(
                status=(
                    ProductDataStatus.EMPTY
                    if total == 0
                    else ProductDataStatus.READY
                ),
                total_count=total,
                offset=offset,
                limit=limit,
                signals=cards,
            )

    def signal_detail(self, signal_freeze_identity: str) -> SignalDetailView:
        if len(signal_freeze_identity) != 64:
            raise ValueError("signal freeze identity must be SHA256")
        if not self.ledger_path.exists():
            return SignalDetailView(
                status=ProductDataStatus.NO_LEDGER,
                signal=None,
                bundle_json=None,
            )
        with self._connect() as connection:
            if not self._table_exists(connection, "signal_freezes"):
                return SignalDetailView(
                    status=ProductDataStatus.SCHEMA_UNAVAILABLE,
                    signal=None,
                    bundle_json=None,
                )
            row = connection.execute(
                """
                SELECT * FROM signal_freezes
                WHERE signal_freeze_identity = ?
                """,
                (signal_freeze_identity,),
            ).fetchone()
            if row is None:
                return SignalDetailView(
                    status=ProductDataStatus.EMPTY,
                    signal=None,
                    bundle_json=None,
                )
            return SignalDetailView(
                status=ProductDataStatus.READY,
                signal=self._card_from_row(row),
                bundle_json=str(row["bundle_json"]),
            )

    def performance_availability(self) -> PerformanceAvailabilityView:
        if not self.ledger_path.exists():
            return PerformanceAvailabilityView(
                status=ProductDataStatus.NO_LEDGER,
                outcome_snapshot_count=0,
                evidence_class_counts=(),
            )
        with self._connect() as connection:
            if not self._table_exists(connection, "outcome_evaluations"):
                return PerformanceAvailabilityView(
                    status=ProductDataStatus.SCHEMA_UNAVAILABLE,
                    outcome_snapshot_count=0,
                    evidence_class_counts=(),
                )
            rows = tuple(
                connection.execute(
                    """
                    SELECT evidence_class, COUNT(*) AS count
                    FROM outcome_evaluations
                    GROUP BY evidence_class
                    ORDER BY evidence_class ASC
                    """
                ).fetchall()
            )
            counts: list[EvidenceClassCount] = []
            total = 0
            for row in rows:
                try:
                    evidence_class = EvidenceClass(str(row["evidence_class"]))
                except ValueError as exc:
                    raise DashboardReadError(
                        "outcome_evaluations contains unknown evidence class"
                    ) from exc
                count = int(row["count"])
                total += count
                counts.append(
                    EvidenceClassCount(
                        evidence_class=evidence_class,
                        count=count,
                    )
                )
            return PerformanceAvailabilityView(
                status=(
                    ProductDataStatus.EMPTY
                    if total == 0
                    else ProductDataStatus.READY
                ),
                outcome_snapshot_count=total,
                evidence_class_counts=tuple(counts),
            )
