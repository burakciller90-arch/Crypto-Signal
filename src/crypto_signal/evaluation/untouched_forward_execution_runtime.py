from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.untouched_forward_execution_journal import (
    WC2PaperExecutionDecision,
    WC2PaperExecutionDecisionStatus,
    WC2PaperExecutionJournal,
    build_wc2_paper_execution_decision,
    compute_wc2_cost_evidence_identity,
    compute_wc2_paper_execution_event_identity,
)
from crypto_signal.evaluation.untouched_forward_execution_protocol import (
    WC2PaperExecutionProtocol,
    WC2PaperExecutionProtocolStore,
)
from crypto_signal.evaluation.untouched_forward_journal import WC2CohortJournal
from crypto_signal.ledger.deserialization import parse_signal_decision
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.autonomy import (
    PAPER_AUTONOMY_POLICY_VERSION,
    evaluate_autonomy_policy,
)
from crypto_signal.paper.epoch2_accounting import (
    Epoch2VaultAccountingSnapshot,
    read_epoch2_state_read_only,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.execution import simulate_paper_fill
from crypto_signal.paper.execution_input import (
    PaperExecutionInputStatus,
    freeze_execution_input_from_cache,
)
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    PAPER_FUND_SCHEMA_VERSION,
    PAPER_RISK_POLICY_VERSION,
    REAL_CAPITAL,
    PaperAction,
    PaperSymbol,
    normalize_positions,
)
from crypto_signal.paper.pretrade import PaperPretradeStatus
from crypto_signal.paper.sizing import PaperPositionSizingStatus, size_paper_candidate
from crypto_signal.paper.state import PaperFundState
from crypto_signal.paper.venue_rules import (
    prepare_authoritative_paper_trade_plan,
    read_latest_binance_spot_venue_rules,
)
from crypto_signal.signals.models import SignalDecision

WC2_EXECUTION_RUNTIME_SCHEMA_VERSION = "wc2-paper-execution-runtime.v1"
WC2_EXECUTION_RUNTIME_ENGINE_VERSION = "wc2-paper-execution-runtime-v1/1"
WC2_EXECUTION_RUNTIME_SUFFIX = ".wc2-paper-execution-runtime.sqlite3"
WC2_EXECUTION_RUNTIME_MAX_DECISION_DELAY_MS = 15 * 60 * 1000

_META_TABLE = "wc2_paper_execution_runtime_meta"
_ACTIVATION_TABLE = "wc2_paper_execution_runtime_activation"
_ALLOWED_TABLES = {_META_TABLE, _ACTIVATION_TABLE}


@dataclass(frozen=True, slots=True)
class WC2PaperExecutionRuntimeActivation:
    activation_identity: str
    execution_protocol_identity: str
    registered_at_ms: int
    collection_start_ms: int
    maximum_decision_delay_ms: int = WC2_EXECUTION_RUNTIME_MAX_DECISION_DELAY_MS
    historical_backfill_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = WC2_EXECUTION_RUNTIME_SCHEMA_VERSION
    engine_version: str = WC2_EXECUTION_RUNTIME_ENGINE_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.activation_identity, "WC2 execution runtime activation")
        _require_sha256(self.execution_protocol_identity, "WC2 execution protocol")
        if min(self.registered_at_ms, self.collection_start_ms) < 0:
            raise ValueError("WC2 execution runtime timestamps cannot be negative")
        if self.collection_start_ms <= self.registered_at_ms:
            raise ValueError("WC2 execution runtime must start after registration")
        if self.maximum_decision_delay_ms <= 0:
            raise ValueError("WC2 execution runtime decision delay must be positive")
        if (
            self.historical_backfill_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("WC2 execution runtime cannot grant real/backfill authority")
        if self.schema_version != WC2_EXECUTION_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 execution runtime schema")
        if self.engine_version != WC2_EXECUTION_RUNTIME_ENGINE_VERSION:
            raise ValueError("unsupported WC2 execution runtime engine")
        if self.activation_identity != canonical_sha256(_activation_payload(self)):
            raise ValueError("WC2 execution runtime activation identity mismatch")


def build_wc2_execution_runtime_activation(
    *,
    protocol: WC2PaperExecutionProtocol,
    registered_at_ms: int,
    collection_start_ms: int,
) -> WC2PaperExecutionRuntimeActivation:
    if collection_start_ms < protocol.execution_start_ms:
        raise ValueError("WC2 runtime cannot predate execution protocol")
    values = {
        "execution_protocol_identity": protocol.protocol_identity,
        "registered_at_ms": registered_at_ms,
        "collection_start_ms": collection_start_ms,
        "maximum_decision_delay_ms": WC2_EXECUTION_RUNTIME_MAX_DECISION_DELAY_MS,
        "historical_backfill_authority": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": WC2_EXECUTION_RUNTIME_SCHEMA_VERSION,
        "engine_version": WC2_EXECUTION_RUNTIME_ENGINE_VERSION,
    }
    return WC2PaperExecutionRuntimeActivation(
        activation_identity=canonical_sha256(values),
        execution_protocol_identity=protocol.protocol_identity,
        registered_at_ms=registered_at_ms,
        collection_start_ms=collection_start_ms,
    )


class WC2PaperExecutionRuntimeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        if not str(path).endswith(WC2_EXECUTION_RUNTIME_SUFFIX):
            raise ValueError(
                "WC2 execution runtime path must end with "
                f"{WC2_EXECUTION_RUNTIME_SUFFIX}"
            )

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            existing = {
                str(row[0])
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
                ).fetchall()
            }
            if existing - _ALLOWED_TABLES:
                raise ValueError("WC2 execution runtime refuses unrelated tables")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )"""
            )
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_ACTIVATION_TABLE} (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    activation_identity TEXT UNIQUE NOT NULL,
                    execution_protocol_identity TEXT NOT NULL,
                    registered_at_ms INTEGER NOT NULL,
                    collection_start_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            expected = {
                "schema_version": WC2_EXECUTION_RUNTIME_SCHEMA_VERSION,
                "engine_version": WC2_EXECUTION_RUNTIME_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "semantic": "forward_only_operational_execution_watermark",
            }
            for key, value in expected.items():
                row = db.execute(
                    f"SELECT value FROM {_META_TABLE} WHERE key=?",
                    (key,),
                ).fetchone()
                if row is None:
                    db.execute(
                        f"INSERT INTO {_META_TABLE}(key,value) VALUES (?,?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise ValueError("WC2 execution runtime metadata mismatch")
            for table in (_META_TABLE, _ACTIVATION_TABLE):
                for action in ("UPDATE", "DELETE"):
                    db.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{action.lower()}
                        BEFORE {action} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'append-only WC2 paper execution runtime'
                            );
                        END"""
                    )

    def append(self, activation: WC2PaperExecutionRuntimeActivation) -> bool:
        self.initialize()
        payload = canonical_json(_activation_payload(activation))
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute(
                f"""SELECT activation_identity, payload_json
                FROM {_ACTIVATION_TABLE} WHERE singleton=1"""
            ).fetchone()
            if row is not None:
                if (
                    str(row[0]) == activation.activation_identity
                    and str(row[1]) == payload
                ):
                    return False
                raise ValueError("WC2 execution runtime activation is immutable")
            db.execute(
                f"""INSERT INTO {_ACTIVATION_TABLE}(
                    singleton,
                    activation_identity,
                    execution_protocol_identity,
                    registered_at_ms,
                    collection_start_ms,
                    payload_json
                ) VALUES (1,?,?,?,?,?)""",
                (
                    activation.activation_identity,
                    activation.execution_protocol_identity,
                    activation.registered_at_ms,
                    activation.collection_start_ms,
                    payload,
                ),
            )
        return True

    def latest(self) -> WC2PaperExecutionRuntimeActivation | None:
        if not self.path.is_file():
            return None
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                f"SELECT payload_json FROM {_ACTIVATION_TABLE} WHERE singleton=1"
            ).fetchone()
        return None if row is None else _activation_from_json(str(row[0]))


@dataclass(frozen=True, slots=True)
class WC2ExecutionSourceEvent:
    event_identity: str
    symbol: PaperSymbol
    source_cutoff_open_time_ms: int
    source_exchanges: tuple[str, str]
    source_freeze_identities: tuple[str, str]
    source_forecast_identities: tuple[str, str]
    source_cohort_forecast_identities: tuple[str, str]
    source_signal_as_of_ms: tuple[int, int]
    source_frozen_at_ms: tuple[int, int]
    source_forecast_issued_at_ms: tuple[int, int]
    signals: tuple[SignalDecision, SignalDecision]

    def __post_init__(self) -> None:
        if self.source_exchanges != (
            Exchange.BINANCE.value,
            Exchange.BYBIT.value,
        ):
            raise ValueError("WC2 runtime source order must be Binance then Bybit")
        if tuple(signal.exchange.value for signal in self.signals) != self.source_exchanges:
            raise ValueError("WC2 runtime signal/provider order mismatch")


@dataclass(frozen=True, slots=True)
class WC2PaperExecutionCycleResult:
    observed_at_ms: int
    scanned_pair_n: int
    eligible_event_n: int
    already_terminal_n: int
    expired_gap_n: int
    waiting_lineage_n: int
    waiting_execution_input_n: int
    waiting_venue_rules_n: int
    hold_cash_n: int
    sizing_rejected_n: int
    pretrade_rejected_n: int
    executed_n: int
    appended_record_identities: tuple[str, ...]
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        counts = (
            self.scanned_pair_n,
            self.eligible_event_n,
            self.already_terminal_n,
            self.expired_gap_n,
            self.waiting_lineage_n,
            self.waiting_execution_input_n,
            self.waiting_venue_rules_n,
            self.hold_cash_n,
            self.sizing_rejected_n,
            self.pretrade_rejected_n,
            self.executed_n,
        )
        if min(counts) < 0:
            raise ValueError("WC2 execution runtime counts cannot be negative")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 execution runtime cannot grant authority")
        for identity in self.appended_record_identities:
            _require_sha256(identity, "WC2 appended execution record")


def process_wc2_paper_execution_cycle(
    *,
    signal_ledger_path: Path,
    decision_evidence_path: Path,
    cohort_journal_path: Path,
    epoch2_path: Path,
    execution_protocol_path: Path,
    runtime_activation_path: Path,
    execution_journal_path: Path,
    candle_cache_path: Path,
    venue_rule_store_path: Path,
    observed_at_ms: int,
) -> WC2PaperExecutionCycleResult:
    if observed_at_ms < 0:
        raise ValueError("WC2 execution observation cannot be negative")
    protocol = WC2PaperExecutionProtocolStore(execution_protocol_path).latest()
    if protocol is None:
        raise ValueError("WC2 execution protocol is not registered")
    activation = WC2PaperExecutionRuntimeStore(runtime_activation_path).latest()
    if activation is None:
        raise ValueError("WC2 execution runtime is not activated")
    if activation.execution_protocol_identity != protocol.protocol_identity:
        raise ValueError("WC2 execution runtime/protocol lineage mismatch")
    if activation.collection_start_ms < protocol.execution_start_ms:
        raise ValueError("WC2 execution runtime predates protocol")
    if observed_at_ms < activation.collection_start_ms:
        return WC2PaperExecutionCycleResult(
            observed_at_ms=observed_at_ms,
            scanned_pair_n=0,
            eligible_event_n=0,
            already_terminal_n=0,
            expired_gap_n=0,
            waiting_lineage_n=0,
            waiting_execution_input_n=0,
            waiting_venue_rules_n=0,
            hold_cash_n=0,
            sizing_rejected_n=0,
            pretrade_rejected_n=0,
            executed_n=0,
            appended_record_identities=(),
        )

    epoch2 = read_epoch2_state_read_only(epoch2_path)
    if epoch2 is None:
        raise ValueError("WC2 execution requires canonical Epoch2 state")
    if epoch2.activation.activation_identity != protocol.epoch2_activation_identity:
        raise ValueError("WC2 execution Epoch2/protocol lineage mismatch")
    core = next(
        item
        for item in epoch2.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    journal = WC2PaperExecutionJournal(execution_journal_path)
    state = replay_wc2_execution_state(core, journal.read_records(), epoch2.activation.activated_at_ms)
    last_actions = _last_execution_times(journal.read_records())
    marks = _read_mark_prices(
        candle_cache_path=candle_cache_path,
        symbols=tuple(position.symbol for position in state.positions),
        observed_at_ms=observed_at_ms,
    )

    decision_ledger = ImmutableDecisionEvidenceLedger(decision_evidence_path)
    cohort_journal = WC2CohortJournal(cohort_journal_path)
    scanned, events, waiting_lineage, expired = _scan_events(
        signal_ledger_path=signal_ledger_path,
        decision_ledger=decision_ledger,
        cohort_journal=cohort_journal,
        protocol=protocol,
        activation=activation,
        execution_journal=journal,
        observed_at_ms=observed_at_ms,
    )

    already = scanned - len(events) - waiting_lineage - expired
    waiting_input = 0
    waiting_venue = 0
    hold = 0
    sizing_rejected = 0
    pretrade_rejected = 0
    executed = 0
    appended: list[str] = []

    for event in events:
        autonomy = evaluate_autonomy_policy(
            state=state,
            signals=event.signals,
            evaluated_at_ms=observed_at_ms,
            activation_cutoff_ms=activation.collection_start_ms,
            mark_prices=marks,
            last_action_at_ms=last_actions,
            provider_source_cutoff_open_time_ms={
                Exchange.BINANCE: event.source_cutoff_open_time_ms,
                Exchange.BYBIT: event.source_cutoff_open_time_ms,
            },
        )
        common = {
            "event_identity": event.event_identity,
            "execution_protocol_identity": protocol.protocol_identity,
            "execution_start_ms": activation.collection_start_ms,
            "source_exchanges": event.source_exchanges,
            "source_freeze_identities": event.source_freeze_identities,
            "source_forecast_identities": event.source_forecast_identities,
            "source_cohort_forecast_identities": event.source_cohort_forecast_identities,
            "source_signal_as_of_ms": event.source_signal_as_of_ms,
            "source_frozen_at_ms": event.source_frozen_at_ms,
            "source_forecast_issued_at_ms": event.source_forecast_issued_at_ms,
            "source_cutoff_open_time_ms": event.source_cutoff_open_time_ms,
            "symbol": event.symbol,
            "epoch2_core_snapshot_identity": core.snapshot_identity,
            "decided_at_ms": observed_at_ms,
            "autonomy_policy_version": PAPER_AUTONOMY_POLICY_VERSION,
        }

        if autonomy.candidate_action is PaperAction.HOLD_CASH:
            record = build_wc2_paper_execution_decision(
                **common,
                status=WC2PaperExecutionDecisionStatus.HOLD_CASH,
                action=PaperAction.HOLD_CASH,
                reason_code=autonomy.reason_code.value,
            )
            if journal.append(record):
                appended.append(record.record_identity)
            hold += 1
            continue

        execution_input_result = freeze_execution_input_from_cache(
            candle_cache_path=candle_cache_path,
            autonomy_decision=autonomy,
            observed_at_ms=observed_at_ms,
        )
        if execution_input_result.status is not PaperExecutionInputStatus.FROZEN:
            waiting_input += 1
            continue
        execution_input = execution_input_result.frozen_input
        if execution_input is None:
            raise ValueError("WC2 frozen execution input disappeared")

        venue_rules = read_latest_binance_spot_venue_rules(
            path=venue_rule_store_path,
            symbol=event.symbol,
            observed_at_ms=execution_input.observed_at_ms,
        )
        if venue_rules is None:
            waiting_venue += 1
            continue

        sizing = size_paper_candidate(
            state=state,
            autonomy_decision=autonomy,
            execution_input=execution_input,
            signals=event.signals,
        )
        if sizing.status is PaperPositionSizingStatus.REJECTED:
            record = build_wc2_paper_execution_decision(
                **common,
                status=WC2PaperExecutionDecisionStatus.SIZING_REJECTED,
                action=autonomy.candidate_action,
                reason_code=sizing.reason_code.value,
                execution_input_identity=execution_input.input_identity,
                sizing_identity=sizing.sizing_identity,
                venue_rule_snapshot_identity=venue_rules.snapshot_identity,
            )
            if journal.append(record):
                appended.append(record.record_identity)
            sizing_rejected += 1
            continue

        bound = prepare_authoritative_paper_trade_plan(
            state=state,
            sizing=sizing,
            execution_input=execution_input,
            venue_rules=venue_rules,
            planned_at_ms=observed_at_ms,
            mark_prices=marks,
        )
        pretrade = bound.pretrade
        if pretrade.status is PaperPretradeStatus.REJECTED:
            record = build_wc2_paper_execution_decision(
                **common,
                status=WC2PaperExecutionDecisionStatus.PRETRADE_REJECTED,
                action=autonomy.candidate_action,
                reason_code=pretrade.reason_code.value,
                execution_input_identity=execution_input.input_identity,
                sizing_identity=sizing.sizing_identity,
                venue_rule_snapshot_identity=venue_rules.snapshot_identity,
                pretrade_identity=pretrade.pretrade_identity,
            )
            if journal.append(record):
                appended.append(record.record_identity)
            pretrade_rejected += 1
            continue

        if pretrade.plan is None:
            raise ValueError("WC2 planned pretrade lost paper plan")
        simulation = simulate_paper_fill(
            plan=pretrade.plan,
            snapshot=bound.execution_snapshot,
            decision_identity=event.event_identity,
            filled_at_ms=observed_at_ms,
        )
        if simulation.fill is None or simulation.costs is None:
            raise ValueError("WC2 trade plan did not produce simulated fill")
        fill = simulation.fill
        costs = simulation.costs
        cost_identity = compute_wc2_cost_evidence_identity(
            fill_identity=fill.record_identity,
            fee_usdt=costs.fee_usdt,
            spread_usdt=costs.spread_usdt,
            slippage_usdt=costs.slippage_usdt,
            execution_policy_version=PAPER_EXECUTION_POLICY_VERSION,
            venue_reference=fill.venue_reference,
        )
        record = build_wc2_paper_execution_decision(
            **common,
            status=WC2PaperExecutionDecisionStatus.EXECUTED,
            action=fill.action,
            reason_code="paper_autonomy_trade_executed",
            execution_input_identity=execution_input.input_identity,
            sizing_identity=sizing.sizing_identity,
            venue_rule_snapshot_identity=venue_rules.snapshot_identity,
            pretrade_identity=pretrade.pretrade_identity,
            plan_identity=pretrade.plan.plan_identity,
            fill_identity=fill.record_identity,
            cost_evidence_identity=cost_identity,
            quantity=fill.quantity,
            reference_price=fill.reference_price,
            simulated_fill_price=fill.simulated_fill_price,
            fee_usdt=costs.fee_usdt,
            spread_usdt=costs.spread_usdt,
            slippage_usdt=costs.slippage_usdt,
            execution_policy_version=PAPER_EXECUTION_POLICY_VERSION,
            venue_reference=fill.venue_reference,
        )
        if journal.append(record):
            appended.append(record.record_identity)
        state = replay_wc2_execution_state(
            core,
            (*journal.read_records(),),
            epoch2.activation.activated_at_ms,
        )
        last_actions[event.symbol] = observed_at_ms
        marks[event.symbol] = fill.simulated_fill_price
        executed += 1

    return WC2PaperExecutionCycleResult(
        observed_at_ms=observed_at_ms,
        scanned_pair_n=scanned,
        eligible_event_n=len(events),
        already_terminal_n=max(0, already),
        expired_gap_n=expired,
        waiting_lineage_n=waiting_lineage,
        waiting_execution_input_n=waiting_input,
        waiting_venue_rules_n=waiting_venue,
        hold_cash_n=hold,
        sizing_rejected_n=sizing_rejected,
        pretrade_rejected_n=pretrade_rejected,
        executed_n=executed,
        appended_record_identities=tuple(appended),
    )


def replay_wc2_execution_state(
    core: Epoch2VaultAccountingSnapshot,
    records: tuple[WC2PaperExecutionDecision, ...],
    created_at_ms: int,
) -> PaperFundState:
    if core.vault_id is not PaperVaultId.CORE:
        raise ValueError("WC2 execution replay requires CORE snapshot")
    cash = core.cash_usdt
    positions = {item.symbol: item.quantity for item in core.positions}
    last_identity: str | None = None
    last_at: int | None = None
    replayed = 0
    for record in records:
        if record.epoch2_core_snapshot_identity != core.snapshot_identity:
            raise ValueError("WC2 execution replay CORE snapshot lineage mismatch")
        if record.status is not WC2PaperExecutionDecisionStatus.EXECUTED:
            continue
        if (
            record.quantity is None
            or record.simulated_fill_price is None
            or record.fee_usdt < 0
        ):
            raise ValueError("WC2 executed record lacks replay economics")
        quantity = record.quantity
        fill_notional = quantity * record.simulated_fill_price
        held = positions.get(record.symbol, Decimal(0))
        if record.action is PaperAction.BUY:
            debit = fill_notional + record.fee_usdt
            if debit > cash:
                raise ValueError("WC2 execution replay BUY exceeds cash")
            cash -= debit
            positions[record.symbol] = held + quantity
        elif record.action is PaperAction.EXIT:
            if quantity != held:
                raise ValueError("WC2 execution replay EXIT must close exact position")
            credit = fill_notional - record.fee_usdt
            if credit < 0:
                raise ValueError("WC2 execution replay EXIT fee exceeds proceeds")
            cash += credit
            positions[record.symbol] = Decimal(0)
        else:
            raise ValueError("WC2 execution replay supports BUY/EXIT only")
        last_identity = record.fill_identity
        last_at = record.decided_at_ms
        replayed += 1
    return PaperFundState(
        fund_identity=core.snapshot_identity,
        cash_usdt=cash,
        positions=normalize_positions(positions),
        real_capital=REAL_CAPITAL,
        created_at_ms=created_at_ms,
        schema_version=PAPER_FUND_SCHEMA_VERSION,
        execution_policy_version=PAPER_EXECUTION_POLICY_VERSION,
        risk_policy_version=PAPER_RISK_POLICY_VERSION,
        last_mutation_identity=last_identity,
        last_mutation_at_ms=last_at,
        latest_nav_snapshot=None,
        replayed_record_count=replayed,
    )


def _scan_events(
    *,
    signal_ledger_path: Path,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    protocol: WC2PaperExecutionProtocol,
    activation: WC2PaperExecutionRuntimeActivation,
    execution_journal: WC2PaperExecutionJournal,
    observed_at_ms: int,
) -> tuple[int, tuple[WC2ExecutionSourceEvent, ...], int, int]:
    if not signal_ledger_path.is_file():
        raise FileNotFoundError(signal_ledger_path)
    uri = f"{signal_ledger_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(
            """
            SELECT exchange, symbol, as_of_ms, source_cutoff_open_time_ms,
                   frozen_at_ms, signal_freeze_identity, bundle_json
            FROM signal_freezes
            WHERE market_type=?
              AND timeframe='4h'
              AND exchange IN (?,?)
              AND as_of_ms>=?
              AND frozen_at_ms>=?
              AND frozen_at_ms<=?
            ORDER BY source_cutoff_open_time_ms, symbol, exchange
            """,
            (
                MarketType.SPOT.value,
                Exchange.BINANCE.value,
                Exchange.BYBIT.value,
                activation.collection_start_ms,
                activation.collection_start_ms,
                observed_at_ms,
            ),
        ).fetchall()

    grouped: dict[tuple[str, int], dict[str, sqlite3.Row]] = {}
    for row in rows:
        key = (str(row["symbol"]), int(row["source_cutoff_open_time_ms"]))
        grouped.setdefault(key, {})[str(row["exchange"])] = row

    scanned = 0
    waiting_lineage = 0
    expired = 0
    events: list[WC2ExecutionSourceEvent] = []
    for (symbol_text, cutoff), providers in sorted(grouped.items()):
        if set(providers) != {Exchange.BINANCE.value, Exchange.BYBIT.value}:
            continue
        scanned += 1
        ordered_rows = (
            providers[Exchange.BINANCE.value],
            providers[Exchange.BYBIT.value],
        )
        symbol = PaperSymbol(symbol_text)
        freezes = tuple(str(row["signal_freeze_identity"]) for row in ordered_rows)
        event_identity = compute_wc2_paper_execution_event_identity(
            execution_protocol_identity=protocol.protocol_identity,
            symbol=symbol,
            source_cutoff_open_time_ms=cutoff,
            source_exchanges=(Exchange.BINANCE.value, Exchange.BYBIT.value),
            source_freeze_identities=(freezes[0], freezes[1]),
        )
        if execution_journal.contains_event(event_identity):
            continue

        signals: list[SignalDecision] = []
        forecasts: list[str] = []
        cohorts: list[str] = []
        forecast_times: list[int] = []
        lineage_missing = False
        for row in ordered_rows:
            root = json.loads(str(row["bundle_json"]))
            if not isinstance(root, dict) or "signal_decision" not in root:
                raise ValueError("WC2 source bundle lacks signal decision")
            signal = parse_signal_decision(root["signal_decision"])
            if signal.freeze_identity != str(row["signal_freeze_identity"]):
                raise ValueError("WC2 source bundle freeze identity mismatch")
            signals.append(signal)
            issuance = decision_ledger.read_issuance_for_signal(signal.freeze_identity)
            if issuance is None:
                lineage_missing = True
                break
            forecast, _proof = issuance
            forecast_identity = _required_sha(forecast, "forecast_identity")
            issued_at_ms = _required_int(forecast, "issued_at_ms")
            if issued_at_ms < activation.collection_start_ms:
                lineage_missing = True
                break
            cohort_identity = cohort_journal.find_forecast_identity(forecast_identity)
            if cohort_identity is None:
                lineage_missing = True
                break
            forecasts.append(forecast_identity)
            cohorts.append(cohort_identity)
            forecast_times.append(issued_at_ms)
        if lineage_missing:
            waiting_lineage += 1
            continue
        if observed_at_ms - max(forecast_times) > activation.maximum_decision_delay_ms:
            expired += 1
            continue
        events.append(
            WC2ExecutionSourceEvent(
                event_identity=event_identity,
                symbol=symbol,
                source_cutoff_open_time_ms=cutoff,
                source_exchanges=(Exchange.BINANCE.value, Exchange.BYBIT.value),
                source_freeze_identities=(freezes[0], freezes[1]),
                source_forecast_identities=(forecasts[0], forecasts[1]),
                source_cohort_forecast_identities=(cohorts[0], cohorts[1]),
                source_signal_as_of_ms=(
                    int(ordered_rows[0]["as_of_ms"]),
                    int(ordered_rows[1]["as_of_ms"]),
                ),
                source_frozen_at_ms=(
                    int(ordered_rows[0]["frozen_at_ms"]),
                    int(ordered_rows[1]["frozen_at_ms"]),
                ),
                source_forecast_issued_at_ms=(
                    forecast_times[0],
                    forecast_times[1],
                ),
                signals=(signals[0], signals[1]),
            )
        )
    return scanned, tuple(events), waiting_lineage, expired


def _read_mark_prices(
    *,
    candle_cache_path: Path,
    symbols: tuple[PaperSymbol, ...],
    observed_at_ms: int,
) -> dict[PaperSymbol, Decimal]:
    if not symbols:
        return {}
    if not candle_cache_path.is_file():
        return {}
    uri = f"{candle_cache_path.resolve().as_uri()}?mode=ro"
    result: dict[PaperSymbol, Decimal] = {}
    with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        for symbol in symbols:
            row = db.execute(
                """
                SELECT close
                FROM candles
                WHERE exchange=? AND market_type=? AND symbol=?
                  AND timeframe='15m' AND is_closed=1
                  AND close_time_ms<=? AND ingested_at_ms<=?
                  AND source_timestamp_ms<=?
                ORDER BY open_time_ms DESC LIMIT 1
                """,
                (
                    Exchange.BINANCE.value,
                    MarketType.SPOT.value,
                    symbol.value,
                    observed_at_ms,
                    observed_at_ms,
                    observed_at_ms,
                ),
            ).fetchone()
            if row is not None:
                price = Decimal(str(row["close"]))
                if price > 0:
                    result[symbol] = price
    return result


def _last_execution_times(
    records: tuple[WC2PaperExecutionDecision, ...],
) -> dict[PaperSymbol, int]:
    result: dict[PaperSymbol, int] = {}
    for record in records:
        if record.status is WC2PaperExecutionDecisionStatus.EXECUTED:
            previous = result.get(record.symbol)
            if previous is None or record.decided_at_ms > previous:
                result[record.symbol] = record.decided_at_ms
    return result


def _activation_payload(
    activation: WC2PaperExecutionRuntimeActivation,
) -> dict[str, object]:
    return {
        "execution_protocol_identity": activation.execution_protocol_identity,
        "registered_at_ms": activation.registered_at_ms,
        "collection_start_ms": activation.collection_start_ms,
        "maximum_decision_delay_ms": activation.maximum_decision_delay_ms,
        "historical_backfill_authority": activation.historical_backfill_authority,
        "production_authority": activation.production_authority,
        "real_capital": activation.real_capital,
        "schema_version": activation.schema_version,
        "engine_version": activation.engine_version,
    }


def _activation_from_json(payload_json: str) -> WC2PaperExecutionRuntimeActivation:
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("WC2 execution runtime activation must be object")
    activation = WC2PaperExecutionRuntimeActivation(
        activation_identity=canonical_sha256(raw),
        execution_protocol_identity=_required_text(raw, "execution_protocol_identity"),
        registered_at_ms=_required_int(raw, "registered_at_ms"),
        collection_start_ms=_required_int(raw, "collection_start_ms"),
        maximum_decision_delay_ms=_required_int(raw, "maximum_decision_delay_ms"),
        historical_backfill_authority=bool(raw.get("historical_backfill_authority")),
        production_authority=bool(raw.get("production_authority")),
        real_capital=_required_int(raw, "real_capital"),
        schema_version=_required_text(raw, "schema_version"),
        engine_version=_required_text(raw, "engine_version"),
    )
    if canonical_json(raw) != payload_json:
        raise ValueError("WC2 execution runtime activation JSON is not canonical")
    return activation


def _required_text(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be non-empty text")
    return value


def _required_sha(raw: dict[str, object], key: str) -> str:
    value = _required_text(raw, key)
    _require_sha256(value, key)
    return value


def _required_int(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{key} must be non-negative integer")
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
