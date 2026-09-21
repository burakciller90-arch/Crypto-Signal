from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_signal.alerts.models import DeliveryAttemptStatus
from crypto_signal.alerts.presentation import render_notification
from crypto_signal.alerts.store import (
    AlertOutboxConflictError,
    parse_alert_event_json,
)
from crypto_signal.confluence.models import ScoreSemantic
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.evaluation.aggregate import aggregate_segments
from crypto_signal.evaluation.models import EvaluatedSignal
from crypto_signal.outcomes.models import EvidenceClass
from crypto_signal.product.deserialization import (
    ProductDeserializationError,
    parse_outcome_evaluation,
    parse_signal_decision,
)
from crypto_signal.product.models import (
    AgreementRelationView,
    AlertCenterView,
    AlertEventView,
    AlertSinkDeliveryView,
    AssetCockpitView,
    CommandCenterView,
    EvidenceClassCount,
    EvidenceKeyLevelView,
    EvidenceMetricView,
    FrozenSignalCard,
    GeometryTargetView,
    MarketRadarItem,
    MarketRadarView,
    MethodologySelectionView,
    NavigationContext,
    NavigationView,
    PerformanceAvailabilityView,
    PerformanceSegmentGroup,
    ProductDataStatus,
    SelectedEvidenceView,
    SignalArchiveView,
    SignalDetailView,
    SignalEvidenceClassStatus,
    SignalGeometryView,
)
from crypto_signal.signals.models import ProbabilityStatus, SignalDirection, SignalState


class DashboardReadError(ValueError):
    """Raised when immutable product data is malformed or semantically inconsistent."""


class DashboardReader:
    def __init__(
        self,
        ledger_path: Path,
        alert_outbox_path: Path | None = None,
    ) -> None:
        self.ledger_path = ledger_path
        self.alert_outbox_path = alert_outbox_path

    @staticmethod
    def _connect_path(path: Path) -> sqlite3.Connection:
        uri = f"file:{path}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection

    def _connect(self) -> sqlite3.Connection:
        return self._connect_path(self.ledger_path)

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

    @classmethod
    def _optional_decimal(cls, value: Any, label: str) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(cls._require_str(value, label))
        except Exception as exc:
            raise DashboardReadError(f"{label} must be decimal text") from exc

    @classmethod
    def _bundle_root(cls, row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(str(row["bundle_json"]))
        except json.JSONDecodeError as exc:
            raise DashboardReadError("bundle_json is not valid JSON") from exc
        return cls._require_mapping(payload, "bundle_json")

    def _card_from_row(self, row: sqlite3.Row) -> FrozenSignalCard:
        root = self._bundle_root(row)
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

        where_sql = ""
        if clauses:
            where_sql = " WHERE " + " AND ".join(clauses)

        if limit is None:
            query = (
                "SELECT * FROM signal_freezes"
                + where_sql
                + " ORDER BY frozen_at_ms DESC, bundle_identity DESC"
            )
            return tuple(connection.execute(query, params).fetchall())

        key_query = (
            "SELECT bundle_identity FROM signal_freezes"
            + where_sql
            + " ORDER BY frozen_at_ms DESC, bundle_identity DESC"
            + " LIMIT ? OFFSET ?"
        )
        key_params = [*params, limit, offset]
        key_rows = tuple(connection.execute(key_query, key_params).fetchall())
        identities = tuple(
            self._require_str(
                key_row["bundle_identity"],
                "signal row bundle identity",
            )
            for key_row in key_rows
        )
        return self._rows_by_bundle_identities(
            connection,
            identities,
        )

    def _rows_by_bundle_identities(
        self,
        connection: sqlite3.Connection,
        identities: tuple[str, ...],
    ) -> tuple[sqlite3.Row, ...]:
        rows: list[sqlite3.Row] = []
        for identity in identities:
            row = connection.execute(
                """
                SELECT *
                FROM signal_freezes
                WHERE bundle_identity = ?
                """,
                (identity,),
            ).fetchone()
            if row is None:
                raise DashboardReadError(
                    "signal row disappeared during immutable read"
                )
            rows.append(row)
        return tuple(rows)

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

            summary = connection.execute(
                """
                SELECT
                    COUNT(*) AS freeze_count,
                    MAX(frozen_at_ms) AS latest_frozen_at_ms
                FROM signal_freezes
                """
            ).fetchone()
            if summary is None:
                raise DashboardReadError("command-center summary row missing")
            freeze_count = self._require_int(
                summary["freeze_count"],
                "command-center freeze count",
            )
            if freeze_count == 0:
                return CommandCenterView(
                    status=ProductDataStatus.EMPTY,
                    freeze_count=0,
                    latest_frozen_at_ms=None,
                    state_counts=(),
                    direction_counts=(),
                    recent_signals=(),
                )

            latest_frozen_at_ms = self._require_int(
                summary["latest_frozen_at_ms"],
                "command-center latest frozen at",
            )
            try:
                state_counts = tuple(
                    (
                        SignalState(
                            self._require_str(
                                row["signal_state"],
                                "command-center signal state",
                            )
                        ),
                        self._require_int(
                            row["freeze_count"],
                            "command-center state count",
                        ),
                    )
                    for row in connection.execute(
                        """
                        SELECT signal_state, COUNT(*) AS freeze_count
                        FROM signal_freezes
                        GROUP BY signal_state
                        ORDER BY signal_state
                        """
                    ).fetchall()
                )
                direction_counts = tuple(
                    (
                        SignalDirection(
                            self._require_str(
                                row["direction"],
                                "command-center direction",
                            )
                        ),
                        self._require_int(
                            row["freeze_count"],
                            "command-center direction count",
                        ),
                    )
                    for row in connection.execute(
                        """
                        SELECT direction, COUNT(*) AS freeze_count
                        FROM signal_freezes
                        GROUP BY direction
                        ORDER BY direction
                        """
                    ).fetchall()
                )
            except ValueError as exc:
                if isinstance(exc, DashboardReadError):
                    raise
                raise DashboardReadError(
                    "command-center aggregate row is semantically invalid"
                ) from exc

            recent_rows = self._signal_rows(
                connection,
                limit=recent_limit,
            )
            recent_cards = tuple(
                self._card_from_row(row) for row in recent_rows
            )
            return CommandCenterView(
                status=ProductDataStatus.READY,
                freeze_count=freeze_count,
                latest_frozen_at_ms=latest_frozen_at_ms,
                state_counts=state_counts,
                direction_counts=direction_counts,
                recent_signals=recent_cards,
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
            key_rows = tuple(
                connection.execute(
                    """
                    WITH ranked AS (
                        SELECT
                            bundle_identity,
                            ROW_NUMBER() OVER (
                                PARTITION BY
                                    exchange,
                                    market_type,
                                    symbol,
                                    timeframe
                                ORDER BY
                                    frozen_at_ms DESC,
                                    bundle_identity DESC
                            ) AS row_rank
                        FROM signal_freezes
                    )
                    SELECT bundle_identity
                    FROM ranked
                    WHERE row_rank = 1
                    """
                ).fetchall()
            )
            if not key_rows:
                return MarketRadarView(status=ProductDataStatus.EMPTY, items=())
            identities = tuple(
                self._require_str(
                    row["bundle_identity"],
                    "market-radar bundle identity",
                )
                for row in key_rows
            )
            cards = tuple(
                self._card_from_row(row)
                for row in self._rows_by_bundle_identities(
                    connection,
                    identities,
                )
            )
            items = tuple(
                MarketRadarItem(
                    exchange=card.exchange,
                    market_type=card.market_type,
                    symbol=card.symbol,
                    timeframe=card.timeframe,
                    latest=card,
                )
                for card in sorted(
                    cards,
                    key=lambda item: (
                        item.symbol,
                        item.timeframe,
                        item.exchange.value,
                        item.market_type.value,
                    ),
                )
            )
            return MarketRadarView(status=ProductDataStatus.READY, items=items)

    def navigation(self) -> NavigationView:
        if not self.ledger_path.exists():
            return NavigationView(status=ProductDataStatus.NO_LEDGER, contexts=())
        with self._connect() as connection:
            if not self._table_exists(connection, "signal_freezes"):
                return NavigationView(
                    status=ProductDataStatus.SCHEMA_UNAVAILABLE,
                    contexts=(),
                )
            rows = tuple(
                connection.execute(
                    """
                    SELECT exchange, market_type, symbol, timeframe,
                           COUNT(*) AS freeze_count,
                           MAX(frozen_at_ms) AS latest_frozen_at_ms
                    FROM signal_freezes
                    GROUP BY exchange, market_type, symbol, timeframe
                    ORDER BY symbol, timeframe, exchange, market_type
                    """
                ).fetchall()
            )
            if not rows:
                return NavigationView(status=ProductDataStatus.EMPTY, contexts=())
            try:
                contexts = tuple(
                    NavigationContext(
                        exchange=Exchange(
                            self._require_str(row["exchange"], "navigation exchange")
                        ),
                        market_type=MarketType(
                            self._require_str(
                                row["market_type"],
                                "navigation market type",
                            )
                        ),
                        symbol=self._require_str(
                            row["symbol"],
                            "navigation symbol",
                        ),
                        timeframe=self._require_str(
                            row["timeframe"],
                            "navigation timeframe",
                        ),
                        freeze_count=self._require_int(
                            row["freeze_count"],
                            "navigation freeze count",
                        ),
                        latest_frozen_at_ms=self._require_int(
                            row["latest_frozen_at_ms"],
                            "navigation latest frozen at",
                        ),
                    )
                    for row in rows
                )
            except ValueError as exc:
                raise DashboardReadError(
                    "navigation context is semantically invalid"
                ) from exc
            return NavigationView(
                status=ProductDataStatus.READY,
                contexts=contexts,
            )

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
            recent_rows = self._signal_rows(
                connection,
                symbol=symbol,
                timeframe=timeframe,
                limit=recent_limit,
            )
            if not recent_rows:
                return AssetCockpitView(
                    status=ProductDataStatus.EMPTY,
                    symbol=symbol,
                    timeframe=timeframe,
                    latest_by_provider=(),
                    recent_signals=(),
                )
            recent_cards = tuple(
                self._card_from_row(row) for row in recent_rows
            )
            provider_keys = tuple(
                connection.execute(
                    """
                    WITH ranked AS (
                        SELECT
                            bundle_identity,
                            ROW_NUMBER() OVER (
                                PARTITION BY exchange, market_type
                                ORDER BY
                                    frozen_at_ms DESC,
                                    bundle_identity DESC
                            ) AS row_rank
                        FROM signal_freezes
                        WHERE symbol = ? AND timeframe = ?
                    )
                    SELECT bundle_identity
                    FROM ranked
                    WHERE row_rank = 1
                    """,
                    (symbol, timeframe),
                ).fetchall()
            )
            provider_identities = tuple(
                self._require_str(
                    row["bundle_identity"],
                    "asset provider bundle identity",
                )
                for row in provider_keys
            )
            provider_cards = tuple(
                self._card_from_row(row)
                for row in self._rows_by_bundle_identities(
                    connection,
                    provider_identities,
                )
            )
            return AssetCockpitView(
                status=ProductDataStatus.READY,
                symbol=symbol,
                timeframe=timeframe,
                latest_by_provider=tuple(
                    sorted(
                        provider_cards,
                        key=lambda card: (
                            card.exchange.value,
                            card.market_type.value,
                        ),
                    )
                ),
                recent_signals=recent_cards,
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

    def _selected_evidence_view(self, value: Any) -> SelectedEvidenceView:
        item = self._require_mapping(value, "selected evidence")
        key_levels = tuple(
            EvidenceKeyLevelView(
                label=self._require_str(level.get("label"), "key level label"),
                price=Decimal(
                    self._require_str(level.get("price"), "key level price")
                ),
            )
            for raw_level in self._require_list(
                item.get("key_levels"),
                "selected evidence key levels",
            )
            for level in [self._require_mapping(raw_level, "key level")]
        )
        metrics = tuple(
            EvidenceMetricView(
                name=self._require_str(metric.get("name"), "metric name"),
                value=Decimal(
                    self._require_str(metric.get("value"), "metric value")
                ),
                unit=self._require_str(metric.get("unit"), "metric unit"),
            )
            for raw_metric in self._require_list(
                item.get("metrics"),
                "selected evidence metrics",
            )
            for metric in [self._require_mapping(raw_metric, "metric")]
        )
        return SelectedEvidenceView(
            evidence_id=self._require_str(
                item.get("evidence_id"),
                "selected evidence id",
            ),
            methodology=self._require_str(
                item.get("methodology"),
                "selected evidence methodology",
            ),
            setup_type=self._require_str(
                item.get("setup_type"),
                "selected evidence setup type",
            ),
            direction=self._require_str(
                item.get("direction"),
                "selected evidence direction",
            ),
            validity=self._require_str(
                item.get("validity"),
                "selected evidence validity",
            ),
            market_available_at_ms=self._require_int(
                item.get("market_available_at_ms"),
                "selected evidence market time",
            ),
            observed_at_ms=self._require_int(
                item.get("observed_at_ms"),
                "selected evidence observed time",
            ),
            evidence_summary=tuple(
                self._require_str(summary, "evidence summary")
                for summary in self._require_list(
                    item.get("evidence_summary"),
                    "evidence summary",
                )
            ),
            ambiguity_flags=tuple(
                self._require_str(flag, "ambiguity flag")
                for flag in self._require_list(
                    item.get("ambiguity_flags"),
                    "ambiguity flags",
                )
            ),
            contradiction_flags=tuple(
                self._require_str(flag, "contradiction flag")
                for flag in self._require_list(
                    item.get("contradiction_flags"),
                    "contradiction flags",
                )
            ),
            key_levels=key_levels,
            metrics=metrics,
            invalidation_price=self._optional_decimal(
                item.get("invalidation_price"),
                "selected evidence invalidation price",
            ),
            invalidation_trigger=(
                None
                if item.get("invalidation_trigger") is None
                else self._require_str(
                    item.get("invalidation_trigger"),
                    "selected evidence invalidation trigger",
                )
            ),
        )

    def _rich_detail(
        self,
        row: sqlite3.Row,
    ) -> SignalDetailView:
        root = self._bundle_root(row)
        signal = self._require_mapping(root.get("signal_decision"), "signal_decision")
        confluence = self._require_mapping(root.get("confluence"), "confluence")
        agreement = self._require_mapping(signal.get("agreement"), "signal agreement")
        selections = tuple(
            MethodologySelectionView(
                methodology=self._require_str(
                    selection.get("methodology"),
                    "selection methodology",
                ),
                source_count=self._require_int(
                    selection.get("source_count"),
                    "selection source count",
                ),
                selected_count=len(
                    self._require_list(
                        selection.get("selected"),
                        "selection selected evidence",
                    )
                ),
                latest_market_available_at_ms=(
                    None
                    if selection.get("latest_market_available_at_ms") is None
                    else self._require_int(
                        selection.get("latest_market_available_at_ms"),
                        "selection latest market time",
                    )
                ),
                resolved_direction=self._require_str(
                    selection.get("resolved_direction"),
                    "selection resolved direction",
                ),
                has_internal_direction_conflict=bool(
                    selection.get("has_internal_direction_conflict")
                ),
                selected=tuple(
                    self._selected_evidence_view(item)
                    for item in self._require_list(
                        selection.get("selected"),
                        "selection selected evidence",
                    )
                ),
            )
            for raw_selection in self._require_list(
                confluence.get("selections"),
                "confluence selections",
            )
            for selection in [
                self._require_mapping(raw_selection, "confluence selection")
            ]
        )
        pairwise = tuple(
            AgreementRelationView(
                left=self._require_str(item.get("left"), "pair left"),
                right=self._require_str(item.get("right"), "pair right"),
                relation=self._require_str(item.get("relation"), "pair relation"),
                left_direction=self._require_str(
                    item.get("left_direction"),
                    "pair left direction",
                ),
                right_direction=self._require_str(
                    item.get("right_direction"),
                    "pair right direction",
                ),
            )
            for raw_item in self._require_list(
                agreement.get("pairwise_relations"),
                "pairwise relations",
            )
            for item in [self._require_mapping(raw_item, "pair relation")]
        )

        geometry_raw = signal.get("geometry")
        geometry: SignalGeometryView | None = None
        if geometry_raw is not None:
            geometry_map = self._require_mapping(geometry_raw, "signal geometry")
            zone = self._require_mapping(
                geometry_map.get("entry_zone"),
                "signal geometry entry zone",
            )
            geometry = SignalGeometryView(
                source_evidence_id=self._require_str(
                    geometry_map.get("source_evidence_id"),
                    "geometry source evidence id",
                ),
                source_methodology=self._require_str(
                    geometry_map.get("source_methodology"),
                    "geometry source methodology",
                ),
                entry_zone_low=Decimal(
                    self._require_str(zone.get("low"), "entry zone low")
                ),
                entry_zone_high=Decimal(
                    self._require_str(zone.get("high"), "entry zone high")
                ),
                entry_reference_price=Decimal(
                    self._require_str(
                        geometry_map.get("entry_reference_price"),
                        "entry reference price",
                    )
                ),
                entry_reference_model=self._require_str(
                    geometry_map.get("entry_reference_model"),
                    "entry reference model",
                ),
                invalidation_price=Decimal(
                    self._require_str(
                        geometry_map.get("invalidation_price"),
                        "geometry invalidation price",
                    )
                ),
                invalidation_trigger=self._require_str(
                    geometry_map.get("invalidation_trigger"),
                    "geometry invalidation trigger",
                ),
                targets=tuple(
                    GeometryTargetView(
                        label=self._require_str(
                            target.get("label"),
                            "geometry target label",
                        ),
                        target_price=Decimal(
                            self._require_str(
                                target.get("target_price"),
                                "geometry target price",
                            )
                        ),
                        reference_rr=Decimal(
                            self._require_str(
                                target.get("reference_rr"),
                                "geometry target reference rr",
                            )
                        ),
                    )
                    for raw_target in self._require_list(
                        geometry_map.get("targets"),
                        "geometry targets",
                    )
                    for target in [
                        self._require_mapping(raw_target, "geometry target")
                    ]
                ),
            )

        candles = self._require_list(root.get("candles"), "frozen candles")
        candle_opens = tuple(
            self._require_int(
                self._require_mapping(candle, "frozen candle").get(
                    "open_time_ms"
                ),
                "frozen candle open time",
            )
            for candle in candles
        )
        return SignalDetailView(
            status=ProductDataStatus.READY,
            signal=self._card_from_row(row),
            bundle_json=str(row["bundle_json"]),
            methodologies=selections,
            pairwise_relations=pairwise,
            geometry=geometry,
            evidence_summary=tuple(
                self._require_str(item, "signal evidence summary")
                for item in self._require_list(
                    signal.get("evidence_summary"),
                    "signal evidence summary",
                )
            ),
            candle_count=len(candles),
            first_candle_open_time_ms=(
                None if not candle_opens else min(candle_opens)
            ),
            last_candle_open_time_ms=(
                None if not candle_opens else max(candle_opens)
            ),
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
            return self._rich_detail(row)

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
                    SELECT
                        o.*,
                        s.bundle_json AS signal_bundle_json
                    FROM outcome_evaluations AS o
                    JOIN signal_freezes AS s
                      ON s.signal_freeze_identity = o.signal_freeze_identity
                    ORDER BY
                        o.evidence_class ASC,
                        o.max_holding_bars ASC,
                        o.signal_freeze_identity ASC,
                        o.evaluated_as_of_ms DESC,
                        o.outcome_identity DESC
                    """
                ).fetchall()
            )
            if not rows:
                return PerformanceAvailabilityView(
                    status=ProductDataStatus.EMPTY,
                    outcome_snapshot_count=0,
                    evidence_class_counts=(),
                )

            class_counter: Counter[EvidenceClass] = Counter()
            grouped_rows: dict[
                tuple[EvidenceClass, int],
                list[sqlite3.Row],
            ] = defaultdict(list)
            for row in rows:
                try:
                    evidence_class = EvidenceClass(str(row["evidence_class"]))
                except ValueError as exc:
                    raise DashboardReadError(
                        "outcome_evaluations contains unknown evidence class"
                    ) from exc
                max_holding_bars = int(row["max_holding_bars"])
                if max_holding_bars <= 0:
                    raise DashboardReadError(
                        "outcome_evaluations contains invalid holding horizon"
                    )
                class_counter[evidence_class] += 1
                grouped_rows[(evidence_class, max_holding_bars)].append(row)

            groups: list[PerformanceSegmentGroup] = []
            for (evidence_class, max_holding_bars), group_rows in sorted(
                grouped_rows.items(),
                key=lambda item: (
                    item[0][0].value,
                    item[0][1],
                ),
            ):
                latest_by_signal: dict[str, sqlite3.Row] = {}
                for row in group_rows:
                    signal_identity = str(row["signal_freeze_identity"])
                    latest_by_signal.setdefault(signal_identity, row)

                evaluated: list[EvaluatedSignal] = []
                for row in latest_by_signal.values():
                    try:
                        signal_root = self._require_mapping(
                            json.loads(str(row["signal_bundle_json"])),
                            "signal bundle",
                        )
                        decision = parse_signal_decision(
                            signal_root.get("signal_decision")
                        )
                        outcome = parse_outcome_evaluation(
                            json.loads(str(row["outcome_json"]))
                        )
                    except (
                        json.JSONDecodeError,
                        ProductDeserializationError,
                    ) as exc:
                        raise DashboardReadError(
                            "performance snapshot cannot be reconstructed"
                        ) from exc
                    if decision.freeze_identity != str(
                        row["signal_freeze_identity"]
                    ):
                        raise DashboardReadError(
                            "performance signal identity mismatch"
                        )
                    if outcome.outcome_identity != str(row["outcome_identity"]):
                        raise DashboardReadError(
                            "performance outcome identity mismatch"
                        )
                    if outcome.evidence_class is not evidence_class:
                        raise DashboardReadError(
                            "performance evidence-class mismatch"
                        )
                    if outcome.max_holding_bars != max_holding_bars:
                        raise DashboardReadError(
                            "performance holding-horizon mismatch"
                        )
                    evaluated.append(
                        EvaluatedSignal(
                            decision=decision,
                            outcome=outcome,
                        )
                    )
                try:
                    segments = aggregate_segments(evaluated)
                except ValueError as exc:
                    raise DashboardReadError(
                        "historical evaluation projection failed"
                    ) from exc
                groups.append(
                    PerformanceSegmentGroup(
                        evidence_class=evidence_class,
                        max_holding_bars=max_holding_bars,
                        stored_snapshot_count=len(group_rows),
                        selected_latest_signal_count=len(latest_by_signal),
                        segments=segments,
                    )
                )

            return PerformanceAvailabilityView(
                status=ProductDataStatus.READY,
                outcome_snapshot_count=len(rows),
                evidence_class_counts=tuple(
                    EvidenceClassCount(
                        evidence_class=evidence_class,
                        count=count,
                    )
                    for evidence_class, count in sorted(
                        class_counter.items(),
                        key=lambda item: item[0].value,
                    )
                ),
                groups=tuple(groups),
            )


    def alert_center(
        self,
        *,
        limit: int = 100,
    ) -> AlertCenterView:
        if limit <= 0:
            raise ValueError("alert center limit must be positive")
        path = self.alert_outbox_path
        if path is None or not path.exists():
            return AlertCenterView(
                status=ProductDataStatus.NO_LEDGER,
                total_count=0,
                events=(),
            )

        with self._connect_path(path) as connection:
            if not self._table_exists(connection, "alert_events"):
                return AlertCenterView(
                    status=ProductDataStatus.SCHEMA_UNAVAILABLE,
                    total_count=0,
                    events=(),
                )
            if not self._table_exists(
                connection,
                "alert_delivery_attempts",
            ):
                return AlertCenterView(
                    status=ProductDataStatus.SCHEMA_UNAVAILABLE,
                    total_count=0,
                    events=(),
                )

            total_row = connection.execute(
                "SELECT COUNT(*) AS count FROM alert_events"
            ).fetchone()
            total = 0 if total_row is None else int(total_row["count"])
            if total == 0:
                return AlertCenterView(
                    status=ProductDataStatus.EMPTY,
                    total_count=0,
                    events=(),
                )

            event_rows = tuple(
                connection.execute(
                    """
                    SELECT event_identity, event_json, appended_at_ms
                    FROM alert_events
                    ORDER BY appended_at_ms DESC, event_identity DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            )
            identities = tuple(
                str(row["event_identity"])
                for row in event_rows
            )
            placeholders = ",".join("?" for _ in identities)
            attempt_rows = tuple(
                connection.execute(
                    f"""
                    SELECT *
                    FROM alert_delivery_attempts
                    WHERE event_identity IN ({placeholders})
                    ORDER BY
                        event_identity ASC,
                        sink_id ASC,
                        attempt_number ASC
                    """,
                    identities,
                ).fetchall()
            )

        attempts_by_event: dict[
            str,
            dict[str, list[sqlite3.Row]],
        ] = defaultdict(lambda: defaultdict(list))
        for row in attempt_rows:
            attempts_by_event[str(row["event_identity"])][
                str(row["sink_id"])
            ].append(row)

        projected: list[AlertEventView] = []
        for row in event_rows:
            try:
                event = parse_alert_event_json(str(row["event_json"]))
            except AlertOutboxConflictError as exc:
                raise DashboardReadError(
                    "alert event cannot be reconstructed"
                ) from exc
            if event.event_identity != str(row["event_identity"]):
                raise DashboardReadError(
                    "alert event row identity mismatch"
                )

            notification = render_notification(event)

            sink_views: list[AlertSinkDeliveryView] = []
            for sink_id, rows in sorted(
                attempts_by_event[event.event_identity].items(),
            ):
                latest = rows[-1]
                try:
                    status = DeliveryAttemptStatus(
                        str(latest["status"])
                    )
                except ValueError as exc:
                    raise DashboardReadError(
                        "alert attempt has unknown status"
                    ) from exc
                sink_views.append(
                    AlertSinkDeliveryView(
                        sink_id=sink_id,
                        attempts=len(rows),
                        latest_status=status,
                        latest_attempted_at_ms=int(
                            latest["attempted_at_ms"]
                        ),
                        terminal=status
                        in {
                            DeliveryAttemptStatus.DELIVERED,
                            DeliveryAttemptStatus.PERMANENT_FAILURE,
                        },
                        delivered=(
                            status
                            is DeliveryAttemptStatus.DELIVERED
                        ),
                        latest_receipt=(
                            None
                            if latest["receipt"] is None
                            else str(latest["receipt"])
                        ),
                    )
                )

            projected.append(
                AlertEventView(
                    event_identity=event.event_identity,
                    source_kind=event.source_kind,
                    signal_freeze_identity=(
                        event.signal_freeze_identity
                    ),
                    lifecycle_evaluation_identity=(
                        event.lifecycle_evaluation_identity
                    ),
                    transition_identity=event.transition_identity,
                    exchange=event.exchange,
                    market_type=event.market_type,
                    symbol=event.symbol,
                    timeframe=event.timeframe,
                    signal_state=event.signal_state,
                    direction=event.direction,
                    setup_type=event.setup_type,
                    decision_as_of_ms=event.decision_as_of_ms,
                    source_evaluated_as_of_ms=(
                        event.source_evaluated_as_of_ms
                    ),
                    confluence_score=event.confluence_score,
                    confluence_score_semantic=(
                        event.confluence_score_semantic
                    ),
                    probability_status=event.probability_status,
                    uncertainty_flags=event.uncertainty_flags,
                    notification_title=notification.title,
                    notification_body=notification.body,
                    appended_at_ms=int(row["appended_at_ms"]),
                    delivery_states=tuple(sink_views),
                )
            )

        return AlertCenterView(
            status=ProductDataStatus.READY,
            total_count=total,
            events=tuple(projected),
        )
