from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from crypto_signal.data.onchain_capital_flow import StablecoinSupplyObservation
from crypto_signal.data.onchain_capital_flow_store import OnchainCapitalFlowStore
from crypto_signal.data.source_contract import (
    SourceContractStore,
    SourceCoverageEvent,
    SourceCoverageState,
    SourceEnvelope,
)
from crypto_signal.data.stablecoin_source_contract import (
    DEFILLAMA_STABLECOIN_CHANNEL,
    DEFILLAMA_STABLECOIN_NETWORK_SCOPE,
    DEFILLAMA_STABLECOIN_PROVIDER,
    DEFILLAMA_STABLECOIN_SOURCE,
)
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.intelligence.stablecoin_capital_flow import (
    StablecoinCapitalFlowEvidenceFreeze,
    StablecoinCapitalFlowStatus,
    build_stablecoin_capital_flow_evidence_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_family import (
    StreamFamilySnapshot,
    build_family_snapshot,
)
from crypto_signal.product.intelligence_stream_models import (
    StreamCategory,
    StreamImportance,
)

_TRACKED_STABLECOINS = ("USDC", "USDT")
_HISTORY_LIMIT = 8
_UNAVAILABLE_RAIL_FLAGS = (
    "exchange_flow_provider_unavailable",
    "large_transfer_provider_unavailable",
    "stablecoin_bridge_provider_unavailable",
    "stablecoin_exchange_flow_provider_unavailable",
    "wallet_cluster_provider_unavailable",
)


@dataclass(frozen=True, slots=True)
class _AcceptedStablecoinContext:
    asset: str
    freeze: StablecoinCapitalFlowEvidenceFreeze
    envelopes: tuple[SourceEnvelope, ...]
    coverage: tuple[SourceCoverageEvent, ...]


def build_onchain_family_snapshots(
    onchain_capital_flow_path: Path,
    source_contract_path: Path,
    *,
    symbols: tuple[str, ...],
    as_of_ms: int,
) -> tuple[StreamFamilySnapshot, ...]:
    """Project accepted stablecoin context into the existing On-chain family.

    This function is deliberately fail-closed. Missing stores, missing/gap source
    coverage, stale observations, or broken raw/envelope lineage produce no
    On-chain snapshot. Other Stream families can continue independently.
    """

    if as_of_ms < 0:
        raise ValueError("On-chain family as-of cannot be negative")
    if not symbols:
        return ()
    canonical_symbols = tuple(sorted(set(symbols)))
    if any(
        not symbol
        or symbol != symbol.upper()
        or not symbol.endswith("USDT")
        for symbol in canonical_symbols
    ):
        raise ValueError("On-chain family symbols must be uppercase USDT markets")
    if not onchain_capital_flow_path.is_file() or not source_contract_path.is_file():
        return ()

    onchain_store = OnchainCapitalFlowStore(onchain_capital_flow_path)
    source_store = SourceContractStore(source_contract_path)
    accepted: list[_AcceptedStablecoinContext] = []

    for asset in _TRACKED_STABLECOINS:
        history = onchain_store.stablecoin_supply_history_as_of(
            asset=asset,
            network_scope=DEFILLAMA_STABLECOIN_NETWORK_SCOPE,
            provider=DEFILLAMA_STABLECOIN_PROVIDER,
            as_of_ms=as_of_ms,
            limit=_HISTORY_LIMIT,
        )
        if not history:
            return ()
        freeze = build_stablecoin_capital_flow_evidence_freeze(
            history,
            as_of_ms=as_of_ms,
        )
        if freeze.analysis.status not in {
            StablecoinCapitalFlowStatus.MEASURED,
            StablecoinCapitalFlowStatus.PARTIAL,
        }:
            return ()

        lineage = _resolve_lineage(
            source_store=source_store,
            observations=freeze.observations,
        )
        if lineage is None:
            return ()
        envelopes, coverage = lineage
        accepted.append(
            _AcceptedStablecoinContext(
                asset=asset,
                freeze=freeze,
                envelopes=envelopes,
                coverage=coverage,
            )
        )

    if len(accepted) != len(_TRACKED_STABLECOINS):
        return ()

    stablecoin_status = (
        "measured"
        if all(
            item.freeze.analysis.status is StablecoinCapitalFlowStatus.MEASURED
            for item in accepted
        )
        else "partial"
    )
    evidence: set[str] = set()
    uncertainty = set(_UNAVAILABLE_RAIL_FLAGS)
    components: list[tuple[str, str]] = [
        ("exchange_flow_status", "unavailable"),
        ("large_transfer_coverage_status", "unavailable"),
        ("large_transfer_status", "unavailable"),
        ("onchain_status", stablecoin_status),
        ("stablecoin_bridge_status", "unavailable"),
        ("stablecoin_exchange_flow_status", "unavailable"),
        ("stablecoin_status", stablecoin_status),
        ("wallet_cohort_measurement_coverage", "unavailable"),
        ("wallet_cohort_status", "unavailable"),
    ]
    source_lineage: list[dict[str, object]] = []

    for item in accepted:
        analysis = item.freeze.analysis
        evidence.update(
            (
                item.freeze.freeze_identity,
                analysis.evidence_identity,
                *(obs.observation_identity for obs in item.freeze.observations),
                *(obs.raw_identity for obs in item.freeze.observations),
                *(envelope.envelope_identity for envelope in item.envelopes),
                *(envelope.capability_identity for envelope in item.envelopes),
                *(coverage.coverage_event_identity for coverage in item.coverage),
            )
        )
        uncertainty.update(analysis.uncertainty_flags)
        prefix = f"stablecoin_{item.asset.lower()}"
        components.extend(
            (
                (f"{prefix}_status", analysis.status.value),
                (
                    f"{prefix}_observation_count",
                    str(analysis.consumed_observation_count),
                ),
            )
        )
        metrics = analysis.metrics
        if metrics is not None:
            components.append(
                (
                    f"{prefix}_circulating_amount",
                    str(metrics.current_circulating_amount),
                )
            )
            components.append(
                (
                    f"{prefix}_supply_delta",
                    (
                        "unavailable_insufficient_history"
                        if metrics.supply_delta is None
                        else str(metrics.supply_delta)
                    ),
                )
            )
        source_lineage.append(
            {
                "asset": item.asset,
                "coverage_identities": tuple(
                    value.coverage_event_identity for value in item.coverage
                ),
                "envelope_identities": tuple(
                    value.envelope_identity for value in item.envelopes
                ),
                "freeze_identity": item.freeze.freeze_identity,
                "observation_identities": tuple(
                    value.observation_identity
                    for value in item.freeze.observations
                ),
                "status": analysis.status.value,
            }
        )

    source_event_identity = canonical_sha256(
        {
            "as_of_ms": as_of_ms,
            "exchange_flow_status": "unavailable",
            "large_transfer_status": "unavailable",
            "source_lineage": tuple(source_lineage),
            "stablecoin_status": stablecoin_status,
            "version": "rdp7-onchain-family-v1/1",
            "wallet_cohort_status": "unavailable",
        }
    )
    state_label = (
        f"stablecoin_supply:{stablecoin_status}:"
        "exchange_flow_unavailable:large_transfer_unavailable:"
        "wallet_cohort_unavailable"
    )

    return tuple(
        build_family_snapshot(
            projector_id="onchain_change",
            family=ConfluenceFamily.ONCHAIN,
            category=StreamCategory.INTELLIGENCE,
            subtype="onchain_material_change",
            importance=StreamImportance.IMPORTANT,
            source_event_identity=source_event_identity,
            source_scope="defillama:stablecoin_supply:capital_context",
            asset=_base_asset(symbol),
            symbol=symbol,
            market=symbol,
            timeframe="capital_context",
            event_at_ms=as_of_ms,
            source_as_of_ms=as_of_ms,
            evidence_identities=tuple(sorted(evidence)),
            evidence_domains=(
                "onchain",
                "stablecoin_capital_flow",
                "stablecoin_supply",
            ),
            state_label=state_label,
            state_components=tuple(components),
            direction=None,
            source_quality=stablecoin_status,
            uncertainty_flags=tuple(sorted(uncertainty)),
        )
        for symbol in canonical_symbols
    )


def _resolve_lineage(
    *,
    source_store: SourceContractStore,
    observations: tuple[StablecoinSupplyObservation, ...],
) -> tuple[tuple[SourceEnvelope, ...], tuple[SourceCoverageEvent, ...]] | None:
    envelopes: list[SourceEnvelope] = []
    coverage_events: list[SourceCoverageEvent] = []

    for observation in observations:
        envelope = source_store.latest_envelope_at(
            provider=DEFILLAMA_STABLECOIN_PROVIDER,
            source=DEFILLAMA_STABLECOIN_SOURCE,
            channel=DEFILLAMA_STABLECOIN_CHANNEL,
            symbol=observation.asset,
            as_of_ms=observation.ingested_at_ms,
        )
        if (
            envelope is None
            or envelope.normalized_identity != observation.observation_identity
            or envelope.raw_identity != observation.raw_identity
        ):
            return None
        raw = source_store.raw_payload(observation.raw_identity)
        capability = source_store.capability(envelope.capability_identity)
        if (
            raw is None
            or capability is None
            or raw.provider != DEFILLAMA_STABLECOIN_PROVIDER
            or raw.source != DEFILLAMA_STABLECOIN_SOURCE
            or raw.channel != DEFILLAMA_STABLECOIN_CHANNEL
            or raw.symbol != observation.asset
        ):
            return None
        coverage = source_store.coverage_at(
            provider=DEFILLAMA_STABLECOIN_PROVIDER,
            source=DEFILLAMA_STABLECOIN_SOURCE,
            channel=DEFILLAMA_STABLECOIN_CHANNEL,
            symbol=observation.asset,
            as_of_ms=observation.ingested_at_ms,
        )
        if (
            coverage is None
            or coverage.state is not SourceCoverageState.OBSERVED
            or coverage.source_envelope_identity != envelope.envelope_identity
            or coverage.capability_identity != envelope.capability_identity
        ):
            return None
        envelopes.append(envelope)
        coverage_events.append(coverage)

    return tuple(envelopes), tuple(coverage_events)


def _base_asset(symbol: str) -> str:
    return symbol[: -len("USDT")]
