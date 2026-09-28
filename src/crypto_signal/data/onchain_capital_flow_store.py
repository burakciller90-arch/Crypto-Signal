from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_signal.data.exchange_flows import (
    ExchangeFlowObservation,
    build_exchange_flow_observation,
)
from crypto_signal.data.large_transfers import (
    LargeTransferObservation,
    TransferClusterRole,
    build_large_transfer_observation,
)
from crypto_signal.data.models import DataSource
from crypto_signal.data.onchain_capital_flow import (
    OnchainEventCoverage,
    OnchainEventCoverageState,
    StablecoinSupplyObservation,
    build_onchain_event_coverage,
    build_stablecoin_supply_observation,
)
from crypto_signal.data.wallet_cohorts import (
    WalletCohortAdmission,
    WalletCohortForwardObservation,
    build_wallet_cohort_admission,
    build_wallet_cohort_forward_observation,
)
from crypto_signal.ledger.serialization import canonical_json

ONCHAIN_CAPITAL_FLOW_STORE_VERSION = "onchain-capital-flow-store-v1/1"


@dataclass(frozen=True, slots=True)
class OnchainCapitalFlowStoreCounts:
    exchange_flow_observations: int
    large_transfer_observations: int
    event_coverage: int
    wallet_cohort_admissions: int
    wallet_cohort_forward_observations: int
    stablecoin_supply_observations: int

    @property
    def total(self) -> int:
        return sum(
            (
                self.exchange_flow_observations,
                self.large_transfer_observations,
                self.event_coverage,
                self.wallet_cohort_admissions,
                self.wallet_cohort_forward_observations,
                self.stablecoin_supply_observations,
            )
        )


class OnchainCapitalFlowStore:
    """Append-only PIT store for accepted on-chain/capital-flow observations."""

    _IMMUTABLE_TABLES = (
        "onchain_exchange_flow_observations",
        "onchain_large_transfer_observations",
        "onchain_event_coverage",
        "onchain_wallet_cohort_admissions",
        "onchain_wallet_cohort_forward_observations",
        "stablecoin_supply_observations",
    )

    def __init__(self, path: Path) -> None:
        self.path = path
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def _connect_ro(self) -> sqlite3.Connection:
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        db = sqlite3.connect(uri, uri=True, timeout=10.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        return db

    def initialize(self) -> None:
        if self._initialized:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS onchain_capital_flow_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS onchain_exchange_flow_observations (
                    observation_identity TEXT PRIMARY KEY,
                    asset TEXT NOT NULL,
                    exchange_scope TEXT NOT NULL,
                    window_start_ms INTEGER NOT NULL,
                    window_end_ms INTEGER NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS onchain_exchange_flow_pit
                    ON onchain_exchange_flow_observations(
                        asset, exchange_scope, ingested_at_ms,
                        source_timestamp_ms, window_end_ms
                    );

                CREATE TABLE IF NOT EXISTS onchain_large_transfer_observations (
                    transfer_identity TEXT PRIMARY KEY,
                    asset TEXT NOT NULL,
                    network TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS onchain_large_transfer_pit
                    ON onchain_large_transfer_observations(
                        asset, network, ingested_at_ms,
                        source_timestamp_ms, event_at_ms
                    );

                CREATE TABLE IF NOT EXISTS onchain_event_coverage (
                    coverage_identity TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    source TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    network TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    coverage_start_ms INTEGER NOT NULL,
                    coverage_end_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS onchain_event_coverage_pit
                    ON onchain_event_coverage(
                        event_kind, asset, network, ingested_at_ms,
                        observed_at_ms, coverage_end_ms
                    );

                CREATE TABLE IF NOT EXISTS onchain_wallet_cohort_admissions (
                    admission_identity TEXT PRIMARY KEY,
                    cohort_id TEXT NOT NULL,
                    cluster_id TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    network TEXT NOT NULL,
                    admitted_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS onchain_wallet_cohort_admission_pit
                    ON onchain_wallet_cohort_admissions(
                        asset, network, admitted_at_ms, admission_identity
                    );

                CREATE TABLE IF NOT EXISTS
                    onchain_wallet_cohort_forward_observations (
                    observation_identity TEXT PRIMARY KEY,
                    admission_identity TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    network TEXT NOT NULL,
                    measurement_end_ms INTEGER NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(admission_identity)
                        REFERENCES onchain_wallet_cohort_admissions(
                            admission_identity
                        )
                );
                CREATE INDEX IF NOT EXISTS onchain_wallet_cohort_forward_pit
                    ON onchain_wallet_cohort_forward_observations(
                        admission_identity, ingested_at_ms,
                        source_timestamp_ms, measurement_end_ms
                    );

                CREATE TABLE IF NOT EXISTS stablecoin_supply_observations (
                    observation_identity TEXT PRIMARY KEY,
                    asset TEXT NOT NULL,
                    network_scope TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS stablecoin_supply_pit
                    ON stablecoin_supply_observations(
                        asset, network_scope, provider, ingested_at_ms,
                        observed_at_ms, source_timestamp_ms
                    );
                """
            )
            for table in self._IMMUTABLE_TABLES:
                for operation in ("UPDATE", "DELETE"):
                    trigger = (
                        f"{table}_immutable_{operation.lower()}"
                    )
                    db.execute(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS {trigger}
                        BEFORE {operation} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'immutable on-chain capital-flow record'
                            );
                        END
                        """
                    )
            row = db.execute(
                "SELECT value FROM onchain_capital_flow_meta "
                "WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO onchain_capital_flow_meta(key, value) "
                    "VALUES (?, ?)",
                    ("schema_version", ONCHAIN_CAPITAL_FLOW_STORE_VERSION),
                )
            elif str(row["value"]) != ONCHAIN_CAPITAL_FLOW_STORE_VERSION:
                raise ValueError("on-chain capital-flow store schema mismatch")
        self._initialized = True

    def append_exchange_flow(
        self,
        observation: ExchangeFlowObservation,
    ) -> bool:
        payload = canonical_json(observation)
        return self._append(
            table="onchain_exchange_flow_observations",
            identity_column="observation_identity",
            identity=observation.observation_identity,
            columns=(
                "observation_identity",
                "asset",
                "exchange_scope",
                "window_start_ms",
                "window_end_ms",
                "source_timestamp_ms",
                "ingested_at_ms",
                "payload_json",
            ),
            values=(
                observation.observation_identity,
                observation.asset,
                observation.exchange_scope,
                observation.window_start_ms,
                observation.window_end_ms,
                observation.source_timestamp_ms,
                observation.ingested_at_ms,
                payload,
            ),
            payload=payload,
        )

    def append_large_transfer(
        self,
        observation: LargeTransferObservation,
    ) -> bool:
        payload = canonical_json(observation)
        return self._append(
            table="onchain_large_transfer_observations",
            identity_column="transfer_identity",
            identity=observation.transfer_identity,
            columns=(
                "transfer_identity",
                "asset",
                "network",
                "event_at_ms",
                "source_timestamp_ms",
                "ingested_at_ms",
                "payload_json",
            ),
            values=(
                observation.transfer_identity,
                observation.asset,
                observation.network,
                observation.event_at_ms,
                observation.source_timestamp_ms,
                observation.ingested_at_ms,
                payload,
            ),
            payload=payload,
        )

    def append_event_coverage(
        self,
        coverage: OnchainEventCoverage,
    ) -> bool:
        payload = canonical_json(coverage)
        return self._append(
            table="onchain_event_coverage",
            identity_column="coverage_identity",
            identity=coverage.coverage_identity,
            columns=(
                "coverage_identity",
                "provider",
                "source",
                "channel",
                "asset",
                "network",
                "event_kind",
                "coverage_start_ms",
                "coverage_end_ms",
                "observed_at_ms",
                "ingested_at_ms",
                "state",
                "payload_json",
            ),
            values=(
                coverage.coverage_identity,
                coverage.provider,
                coverage.source,
                coverage.channel,
                coverage.asset,
                coverage.network,
                coverage.event_kind,
                coverage.coverage_start_ms,
                coverage.coverage_end_ms,
                coverage.observed_at_ms,
                coverage.ingested_at_ms,
                coverage.state.value,
                payload,
            ),
            payload=payload,
        )

    def append_wallet_cohort_admission(
        self,
        admission: WalletCohortAdmission,
    ) -> bool:
        payload = canonical_json(admission)
        return self._append(
            table="onchain_wallet_cohort_admissions",
            identity_column="admission_identity",
            identity=admission.admission_identity,
            columns=(
                "admission_identity",
                "cohort_id",
                "cluster_id",
                "asset",
                "network",
                "admitted_at_ms",
                "payload_json",
            ),
            values=(
                admission.admission_identity,
                admission.cohort_id,
                admission.cluster_id,
                admission.asset,
                admission.network,
                admission.admitted_at_ms,
                payload,
            ),
            payload=payload,
        )

    def append_wallet_cohort_forward(
        self,
        observation: WalletCohortForwardObservation,
    ) -> bool:
        payload = canonical_json(observation)
        return self._append(
            table="onchain_wallet_cohort_forward_observations",
            identity_column="observation_identity",
            identity=observation.observation_identity,
            columns=(
                "observation_identity",
                "admission_identity",
                "asset",
                "network",
                "measurement_end_ms",
                "source_timestamp_ms",
                "ingested_at_ms",
                "payload_json",
            ),
            values=(
                observation.observation_identity,
                observation.admission_identity,
                observation.asset,
                observation.network,
                observation.measurement_end_ms,
                observation.source_timestamp_ms,
                observation.ingested_at_ms,
                payload,
            ),
            payload=payload,
        )

    def append_stablecoin_supply(
        self,
        observation: StablecoinSupplyObservation,
    ) -> bool:
        payload = canonical_json(observation)
        return self._append(
            table="stablecoin_supply_observations",
            identity_column="observation_identity",
            identity=observation.observation_identity,
            columns=(
                "observation_identity",
                "asset",
                "network_scope",
                "provider",
                "source_timestamp_ms",
                "observed_at_ms",
                "ingested_at_ms",
                "payload_json",
            ),
            values=(
                observation.observation_identity,
                observation.asset,
                observation.network_scope,
                observation.provider,
                observation.source_timestamp_ms,
                observation.observed_at_ms,
                observation.ingested_at_ms,
                payload,
            ),
            payload=payload,
        )

    def latest_exchange_flow_as_of(
        self,
        *,
        asset: str,
        exchange_scope: str,
        as_of_ms: int,
    ) -> ExchangeFlowObservation | None:
        _require_as_of(as_of_ms)
        if not self.path.is_file():
            return None
        with self._connect_ro() as db:
            row = db.execute(
                """
                SELECT payload_json
                FROM onchain_exchange_flow_observations
                WHERE asset=?
                  AND exchange_scope=?
                  AND window_end_ms<=?
                  AND source_timestamp_ms<=?
                  AND ingested_at_ms<=?
                ORDER BY window_end_ms DESC,
                         source_timestamp_ms DESC,
                         observation_identity DESC
                LIMIT 1
                """,
                (
                    asset,
                    exchange_scope,
                    as_of_ms,
                    as_of_ms,
                    as_of_ms,
                ),
            ).fetchone()
        if row is None:
            return None
        return _exchange_flow_from_payload(str(row["payload_json"]))

    def large_transfers_as_of(
        self,
        *,
        asset: str,
        network: str,
        start_ms: int,
        end_ms: int,
        as_of_ms: int,
    ) -> tuple[LargeTransferObservation, ...]:
        _require_window(start_ms, end_ms, as_of_ms)
        if not self.path.is_file():
            return ()
        with self._connect_ro() as db:
            rows = db.execute(
                """
                SELECT payload_json
                FROM onchain_large_transfer_observations
                WHERE asset=?
                  AND network=?
                  AND event_at_ms>=?
                  AND event_at_ms<=?
                  AND event_at_ms<=?
                  AND source_timestamp_ms<=?
                  AND ingested_at_ms<=?
                ORDER BY event_at_ms ASC, transfer_identity ASC
                """,
                (
                    asset,
                    network,
                    start_ms,
                    end_ms,
                    as_of_ms,
                    as_of_ms,
                    as_of_ms,
                ),
            ).fetchall()
        return tuple(
            _large_transfer_from_payload(str(row["payload_json"]))
            for row in rows
        )

    def latest_event_coverage_as_of(
        self,
        *,
        event_kind: str,
        asset: str,
        network: str,
        as_of_ms: int,
    ) -> OnchainEventCoverage | None:
        _require_as_of(as_of_ms)
        if not self.path.is_file():
            return None
        with self._connect_ro() as db:
            row = db.execute(
                """
                SELECT payload_json
                FROM onchain_event_coverage
                WHERE event_kind=?
                  AND asset=?
                  AND network=?
                  AND coverage_end_ms<=?
                  AND observed_at_ms<=?
                  AND ingested_at_ms<=?
                ORDER BY coverage_end_ms DESC,
                         observed_at_ms DESC,
                         coverage_identity DESC
                LIMIT 1
                """,
                (
                    event_kind,
                    asset,
                    network,
                    as_of_ms,
                    as_of_ms,
                    as_of_ms,
                ),
            ).fetchone()
        if row is None:
            return None
        return _event_coverage_from_payload(str(row["payload_json"]))

    def latest_stablecoin_supply_as_of(
        self,
        *,
        asset: str,
        network_scope: str,
        provider: str,
        as_of_ms: int,
    ) -> StablecoinSupplyObservation | None:
        _require_as_of(as_of_ms)
        if not self.path.is_file():
            return None
        with self._connect_ro() as db:
            row = db.execute(
                """
                SELECT payload_json
                FROM stablecoin_supply_observations
                WHERE asset=?
                  AND network_scope=?
                  AND provider=?
                  AND source_timestamp_ms<=?
                  AND observed_at_ms<=?
                  AND ingested_at_ms<=?
                ORDER BY source_timestamp_ms DESC,
                         observed_at_ms DESC,
                         observation_identity DESC
                LIMIT 1
                """,
                (
                    asset,
                    network_scope,
                    provider,
                    as_of_ms,
                    as_of_ms,
                    as_of_ms,
                ),
            ).fetchone()
        if row is None:
            return None
        return _stablecoin_supply_from_payload(str(row["payload_json"]))

    def stablecoin_supply_history_as_of(
        self,
        *,
        asset: str,
        network_scope: str,
        provider: str,
        as_of_ms: int,
        limit: int,
    ) -> tuple[StablecoinSupplyObservation, ...]:
        _require_as_of(as_of_ms)
        if limit <= 0:
            raise ValueError("stablecoin supply history limit must be positive")
        if not self.path.is_file():
            return ()
        with self._connect_ro() as db:
            rows = db.execute(
                """
                SELECT payload_json
                FROM stablecoin_supply_observations
                WHERE asset=?
                  AND network_scope=?
                  AND provider=?
                  AND source_timestamp_ms<=?
                  AND observed_at_ms<=?
                  AND ingested_at_ms<=?
                ORDER BY source_timestamp_ms DESC,
                         observed_at_ms DESC,
                         observation_identity DESC
                LIMIT ?
                """,
                (
                    asset,
                    network_scope,
                    provider,
                    as_of_ms,
                    as_of_ms,
                    as_of_ms,
                    limit,
                ),
            ).fetchall()
        return tuple(
            _stablecoin_supply_from_payload(str(row["payload_json"]))
            for row in reversed(rows)
        )

    def wallet_cohort_admission(
        self,
        admission_identity: str,
    ) -> WalletCohortAdmission | None:
        if not self.path.is_file():
            return None
        with self._connect_ro() as db:
            row = db.execute(
                """
                SELECT payload_json
                FROM onchain_wallet_cohort_admissions
                WHERE admission_identity=?
                """,
                (admission_identity,),
            ).fetchone()
        if row is None:
            return None
        return _wallet_admission_from_payload(str(row["payload_json"]))

    def wallet_cohort_forward_as_of(
        self,
        *,
        admission_identity: str,
        as_of_ms: int,
    ) -> tuple[WalletCohortForwardObservation, ...]:
        _require_as_of(as_of_ms)
        if not self.path.is_file():
            return ()
        with self._connect_ro() as db:
            rows = db.execute(
                """
                SELECT payload_json
                FROM onchain_wallet_cohort_forward_observations
                WHERE admission_identity=?
                  AND measurement_end_ms<=?
                  AND source_timestamp_ms<=?
                  AND ingested_at_ms<=?
                ORDER BY measurement_end_ms ASC, observation_identity ASC
                """,
                (
                    admission_identity,
                    as_of_ms,
                    as_of_ms,
                    as_of_ms,
                ),
            ).fetchall()
        return tuple(
            _wallet_forward_from_payload(str(row["payload_json"]))
            for row in rows
        )

    def counts(self) -> OnchainCapitalFlowStoreCounts:
        if not self.path.is_file():
            return OnchainCapitalFlowStoreCounts(0, 0, 0, 0, 0, 0)
        with self._connect_ro() as db:
            values = [
                int(
                    db.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                )
                for table in self._IMMUTABLE_TABLES
            ]
        return OnchainCapitalFlowStoreCounts(*values)

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        with self._connect_ro() as db:
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]) == "ok"

    def _append(
        self,
        *,
        table: str,
        identity_column: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        payload: str,
    ) -> bool:
        self.initialize()
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                f"SELECT payload_json FROM {table} "
                f"WHERE {identity_column}=?",
                (identity,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) != payload:
                    raise ValueError(
                        "on-chain capital-flow identity conflict"
                    )
                db.rollback()
                return False
            db.execute(
                f"INSERT INTO {table} ({column_sql}) "
                f"VALUES ({placeholders})",
                values,
            )
            db.commit()
        return True


def _exchange_flow_from_payload(payload_json: str) -> ExchangeFlowObservation:
    payload = _json_object(payload_json, "exchange flow")
    value = build_exchange_flow_observation(
        asset=str(payload["asset"]),
        exchange_scope=str(payload["exchange_scope"]),
        window_start_ms=int(payload["window_start_ms"]),
        window_end_ms=int(payload["window_end_ms"]),
        inflow_amount=Decimal(str(payload["inflow_amount"])),
        outflow_amount=Decimal(str(payload["outflow_amount"])),
        source_provider=str(payload["source_provider"]),
        attribution_method=str(payload["attribution_method"]),
        source=DataSource(str(payload["source"])),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        adapter_version=str(payload["adapter_version"]),
    )
    if value.observation_identity != str(payload["observation_identity"]):
        raise ValueError("stored exchange-flow identity mismatch")
    return value


def _large_transfer_from_payload(payload_json: str) -> LargeTransferObservation:
    payload = _json_object(payload_json, "large transfer")
    value = build_large_transfer_observation(
        asset=str(payload["asset"]),
        network=str(payload["network"]),
        provider_transfer_id=str(payload["provider_transfer_id"]),
        source_cluster_id=str(payload["source_cluster_id"]),
        destination_cluster_id=str(payload["destination_cluster_id"]),
        source_role=TransferClusterRole(str(payload["source_role"])),
        destination_role=TransferClusterRole(
            str(payload["destination_role"])
        ),
        amount=Decimal(str(payload["amount"])),
        event_at_ms=int(payload["event_at_ms"]),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        source_provider=str(payload["source_provider"]),
        attribution_method=str(payload["attribution_method"]),
        source=DataSource(str(payload["source"])),
        adapter_version=str(payload["adapter_version"]),
    )
    if value.transfer_identity != str(payload["transfer_identity"]):
        raise ValueError("stored large-transfer identity mismatch")
    return value


def _event_coverage_from_payload(payload_json: str) -> OnchainEventCoverage:
    payload = _json_object(payload_json, "on-chain event coverage")
    value = build_onchain_event_coverage(
        provider=str(payload["provider"]),
        source=str(payload["source"]),
        channel=str(payload["channel"]),
        asset=str(payload["asset"]),
        network=str(payload["network"]),
        event_kind=str(payload["event_kind"]),
        coverage_start_ms=int(payload["coverage_start_ms"]),
        coverage_end_ms=int(payload["coverage_end_ms"]),
        observed_at_ms=int(payload["observed_at_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        state=OnchainEventCoverageState(str(payload["state"])),
        source_envelope_identity=_optional_text(
            payload["source_envelope_identity"]
        ),
        raw_identity=_optional_text(payload["raw_identity"]),
        reason_codes=tuple(str(item) for item in payload["reason_codes"]),
    )
    if value.coverage_identity != str(payload["coverage_identity"]):
        raise ValueError("stored on-chain coverage identity mismatch")
    return value


def _stablecoin_supply_from_payload(
    payload_json: str,
) -> StablecoinSupplyObservation:
    payload = _json_object(payload_json, "stablecoin supply")
    value = build_stablecoin_supply_observation(
        asset=str(payload["asset"]),
        network_scope=str(payload["network_scope"]),
        provider=str(payload["provider"]),
        provider_metric_identity=str(payload["provider_metric_identity"]),
        circulating_amount=Decimal(str(payload["circulating_amount"])),
        usd_amount=(
            None
            if payload["usd_amount"] is None
            else Decimal(str(payload["usd_amount"]))
        ),
        source=DataSource(str(payload["source"])),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        observed_at_ms=int(payload["observed_at_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        adapter_version=str(payload["adapter_version"]),
        raw_identity=str(payload["raw_identity"]),
        source_envelope_identity=str(payload["source_envelope_identity"]),
    )
    if value.observation_identity != str(payload["observation_identity"]):
        raise ValueError("stored stablecoin supply identity mismatch")
    return value


def _wallet_admission_from_payload(payload_json: str) -> WalletCohortAdmission:
    payload = _json_object(payload_json, "wallet cohort admission")
    value = build_wallet_cohort_admission(
        cohort_id=str(payload["cohort_id"]),
        cluster_id=str(payload["cluster_id"]),
        asset=str(payload["asset"]),
        network=str(payload["network"]),
        admitted_at_ms=int(payload["admitted_at_ms"]),
        basis_available_at_ms=int(payload["basis_available_at_ms"]),
        source_provider=str(payload["source_provider"]),
        attribution_method=str(payload["attribution_method"]),
        admission_rule_version=str(payload["admission_rule_version"]),
        basis_evidence_identities=tuple(
            str(item) for item in payload["basis_evidence_identities"]
        ),
        source=DataSource(str(payload["source"])),
    )
    if value.admission_identity != str(payload["admission_identity"]):
        raise ValueError("stored wallet cohort admission identity mismatch")
    return value


def _wallet_forward_from_payload(
    payload_json: str,
) -> WalletCohortForwardObservation:
    payload = _json_object(payload_json, "wallet cohort forward")
    value = build_wallet_cohort_forward_observation(
        admission_identity=str(payload["admission_identity"]),
        cohort_id=str(payload["cohort_id"]),
        cluster_id=str(payload["cluster_id"]),
        asset=str(payload["asset"]),
        network=str(payload["network"]),
        measurement_start_ms=int(payload["measurement_start_ms"]),
        measurement_end_ms=int(payload["measurement_end_ms"]),
        metric_name=str(payload["metric_name"]),
        metric_value=Decimal(str(payload["metric_value"])),
        source_provider=str(payload["source_provider"]),
        source=DataSource(str(payload["source"])),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        adapter_version=str(payload["adapter_version"]),
    )
    if value.observation_identity != str(payload["observation_identity"]):
        raise ValueError("stored wallet cohort forward identity mismatch")
    return value


def _json_object(payload_json: str, label: str) -> dict[str, Any]:
    value = json.loads(payload_json)
    if not isinstance(value, dict):
        raise TypeError(f"{label} payload must decode to object")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _require_as_of(as_of_ms: int) -> None:
    if as_of_ms < 0:
        raise ValueError("on-chain store as-of cannot be negative")


def _require_window(start_ms: int, end_ms: int, as_of_ms: int) -> None:
    _require_as_of(as_of_ms)
    if min(start_ms, end_ms) < 0 or end_ms < start_ms:
        raise ValueError("invalid on-chain store event window")
