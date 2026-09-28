from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
    DEFAULT_STABLECOIN_CAPITAL_FLOW_CONFIG,
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

RDP7_ONCHAIN_FAMILY_VERSION = "rdp7-stablecoin-onchain-family-v1/1"
RDP7_ONCHAIN_PROJECTOR_ID = "onchain_change"
RDP7_ONCHAIN_SUBTYPE = "onchain_material_change"
RDP7_ONCHAIN_TIMEFRAME = "slow_capital_context"
RDP7_ONCHAIN_SOURCE_SCOPE = "defillama:all_chains:stablecoin_capital_context"
RDP7_STABLECOIN_ASSETS = ("USDC", "USDT")


@dataclass(frozen=True, slots=True)
class _StablecoinRail:
    asset: str
    freeze: StablecoinCapitalFlowEvidenceFreeze | None
    envelope: SourceEnvelope | None
    coverage: SourceCoverageEvent | None
    lineage_accepted: bool

    @property
    def effective_status(self) -> str:
        if self.freeze is None:
            return StablecoinCapitalFlowStatus.UNAVAILABLE.value
        if not self.lineage_accepted:
            return StablecoinCapitalFlowStatus.UNAVAILABLE.value
        return self.freeze.analysis.status.value

    @property
    def accepted_fresh_context(self) -> bool:
        if self.freeze is None or not self.lineage_accepted:
            return False
        return self.freeze.analysis.status in {
            StablecoinCapitalFlowStatus.MEASURED,
            StablecoinCapitalFlowStatus.PARTIAL,
        }


def build_onchain_family_snapshots(
    onchain_path: Path,
    source_contract_path: Path,
    *,
    symbols: tuple[str, ...],
    as_of_ms: int,
) -> tuple[StreamFamilySnapshot, ...]:
    if as_of_ms < 0:
        raise ValueError("On-chain family as-of must be non-negative")
    normalized_symbols = tuple(
        sorted(
            {
                value.upper()
                for value in symbols
                if value.strip()
            }
        )
    )
    if not normalized_symbols:
        return ()
    if not onchain_path.is_file() or not source_contract_path.is_file():
        return ()

    onchain_store = OnchainCapitalFlowStore(onchain_path)
    source_store = SourceContractStore(source_contract_path)
    rails = tuple(
        _stablecoin_rail(
            asset=asset,
            onchain_store=onchain_store,
            source_store=source_store,
            as_of_ms=as_of_ms,
        )
        for asset in RDP7_STABLECOIN_ASSETS
    )
    if not any(item.freeze is not None for item in rails):
        return ()

    evidence = _evidence_identities(rails)
    if not evidence:
        return ()
    domains = _evidence_domains(rails)
    components = _state_components(rails)
    uncertainty = _uncertainty_flags(rails)
    source_quality, onchain_status = _family_quality_and_status(rails)

    snapshots = tuple(
        build_family_snapshot(
            projector_id=RDP7_ONCHAIN_PROJECTOR_ID,
            family=ConfluenceFamily.ONCHAIN,
            category=StreamCategory.INTELLIGENCE,
            subtype=RDP7_ONCHAIN_SUBTYPE,
            importance=StreamImportance.IMPORTANT,
            source_event_identity=canonical_sha256(
                {
                    "as_of_ms": as_of_ms,
                    "evidence_identities": evidence,
                    "onchain_status": onchain_status,
                    "source_quality": source_quality,
                    "symbol": symbol,
                    "version": RDP7_ONCHAIN_FAMILY_VERSION,
                }
            ),
            source_scope=RDP7_ONCHAIN_SOURCE_SCOPE,
            asset=_base_asset(symbol),
            symbol=symbol,
            market=symbol,
            timeframe=RDP7_ONCHAIN_TIMEFRAME,
            event_at_ms=as_of_ms,
            source_as_of_ms=as_of_ms,
            evidence_identities=evidence,
            evidence_domains=domains,
            state_label=onchain_status,
            state_components=components,
            direction=None,
            source_quality=source_quality,
            uncertainty_flags=uncertainty,
        )
        for symbol in normalized_symbols
    )
    return tuple(
        sorted(
            snapshots,
            key=lambda item: (
                item.symbol,
                item.source_event_identity,
            ),
        )
    )


def _stablecoin_rail(
    *,
    asset: str,
    onchain_store: OnchainCapitalFlowStore,
    source_store: SourceContractStore,
    as_of_ms: int,
) -> _StablecoinRail:
    observations = onchain_store.stablecoin_supply_history_as_of(
        asset=asset,
        network_scope=DEFILLAMA_STABLECOIN_NETWORK_SCOPE,
        provider=DEFILLAMA_STABLECOIN_PROVIDER,
        as_of_ms=as_of_ms,
        limit=DEFAULT_STABLECOIN_CAPITAL_FLOW_CONFIG.lookback_observations,
    )
    if not observations:
        return _StablecoinRail(
            asset=asset,
            freeze=None,
            envelope=None,
            coverage=None,
            lineage_accepted=False,
        )

    freeze = build_stablecoin_capital_flow_evidence_freeze(
        observations,
        as_of_ms=as_of_ms,
    )
    latest = freeze.observations[-1] if freeze.observations else None
    envelope = source_store.latest_envelope_at(
        provider=DEFILLAMA_STABLECOIN_PROVIDER,
        source=DEFILLAMA_STABLECOIN_SOURCE,
        channel=DEFILLAMA_STABLECOIN_CHANNEL,
        symbol=asset,
        as_of_ms=as_of_ms,
    )
    coverage = source_store.coverage_at(
        provider=DEFILLAMA_STABLECOIN_PROVIDER,
        source=DEFILLAMA_STABLECOIN_SOURCE,
        channel=DEFILLAMA_STABLECOIN_CHANNEL,
        symbol=asset,
        as_of_ms=as_of_ms,
    )
    lineage_accepted = (
        latest is not None
        and envelope is not None
        and coverage is not None
        and coverage.state is SourceCoverageState.OBSERVED
        and coverage.source_envelope_identity == envelope.envelope_identity
        and envelope.normalized_identity == latest.observation_identity
        and envelope.raw_identity == latest.raw_identity
        and envelope.ingested_at_ms <= as_of_ms
        and coverage.observed_at_ms <= as_of_ms
    )
    return _StablecoinRail(
        asset=asset,
        freeze=freeze,
        envelope=envelope,
        coverage=coverage,
        lineage_accepted=lineage_accepted,
    )


def _evidence_identities(
    rails: tuple[_StablecoinRail, ...],
) -> tuple[str, ...]:
    values: set[str] = set()
    for rail in rails:
        if rail.freeze is not None:
            values.add(rail.freeze.freeze_identity)
            values.add(rail.freeze.analysis.evidence_identity)
            for observation in rail.freeze.observations:
                values.add(observation.observation_identity)
                values.add(observation.raw_identity)
        if rail.envelope is not None:
            values.add(rail.envelope.envelope_identity)
        if rail.coverage is not None:
            values.add(rail.coverage.coverage_event_identity)
    return tuple(sorted(values))


def _evidence_domains(
    rails: tuple[_StablecoinRail, ...],
) -> tuple[str, ...]:
    domains = {
        "onchain",
        "stablecoin_capital_flow",
        "stablecoin_supply",
    }
    if any(
        rail.freeze is not None and rail.freeze.observations
        for rail in rails
    ):
        domains.add("source_raw_payload")
    if any(rail.envelope is not None for rail in rails):
        domains.add("source_envelope")
    if any(rail.coverage is not None for rail in rails):
        domains.add("source_coverage")
    return tuple(sorted(domains))


def _state_components(
    rails: tuple[_StablecoinRail, ...],
) -> tuple[tuple[str, str], ...]:
    components: list[tuple[str, str]] = [
        ("exchange_flow_status", "unavailable"),
        ("large_transfer_status", "unavailable"),
        ("stablecoin_bridge_status", "unavailable"),
        ("wallet_cohort_status", "unavailable"),
    ]
    for rail in rails:
        prefix = rail.asset.lower()
        components.extend(
            (
                (
                    f"{prefix}_source_coverage_status",
                    (
                        "unavailable"
                        if rail.coverage is None
                        else rail.coverage.state.value
                    ),
                ),
                (f"{prefix}_stablecoin_status", rail.effective_status),
            )
        )
        if rail.freeze is None:
            continue
        analysis = rail.freeze.analysis
        if analysis.latest_observation_age_ms is not None:
            components.append(
                (
                    f"{prefix}_stablecoin_latest_age_ms",
                    str(analysis.latest_observation_age_ms),
                )
            )
        if not rail.accepted_fresh_context or analysis.metrics is None:
            continue
        metrics = analysis.metrics
        components.append(
            (
                f"{prefix}_circulating_amount",
                str(metrics.current_circulating_amount),
            )
        )
        if metrics.supply_delta is not None:
            components.append(
                (f"{prefix}_supply_delta", str(metrics.supply_delta))
            )
        if metrics.supply_delta_ratio is not None:
            components.append(
                (
                    f"{prefix}_supply_delta_ratio",
                    str(metrics.supply_delta_ratio),
                )
            )
    source_quality, onchain_status = _family_quality_and_status(rails)
    components.extend(
        (
            ("onchain_status", onchain_status),
            ("stablecoin_context_source_quality", source_quality),
        )
    )
    return tuple(sorted(components))


def _uncertainty_flags(
    rails: tuple[_StablecoinRail, ...],
) -> tuple[str, ...]:
    flags = {
        "exchange_flow_provider_unavailable",
        "large_transfer_provider_unavailable",
        "stablecoin_bridge_provider_unavailable",
        "stablecoin_supply_context_not_directional",
        "wallet_cohort_provider_unavailable",
    }
    for rail in rails:
        if rail.freeze is None:
            flags.add(
                f"{rail.asset.lower()}_stablecoin_supply_unavailable"
            )
            continue
        flags.update(rail.freeze.analysis.uncertainty_flags)
        if not rail.lineage_accepted:
            flags.add(
                f"{rail.asset.lower()}_stablecoin_source_lineage_unavailable"
            )
    return tuple(sorted(flags))


def _family_quality_and_status(
    rails: tuple[_StablecoinRail, ...],
) -> tuple[str, str]:
    accepted = tuple(
        rail for rail in rails if rail.accepted_fresh_context
    )
    if not accepted:
        return "unavailable", "unavailable"
    if len(accepted) != len(rails):
        return "partial", "stablecoin_context_partial"
    if any(
        rail.freeze is not None
        and rail.freeze.analysis.status is StablecoinCapitalFlowStatus.PARTIAL
        for rail in accepted
    ):
        return "partial", "stablecoin_context_partial"
    return "measured", "stablecoin_context_measured"


def _base_asset(symbol: str) -> str:
    normalized = symbol.upper()
    for quote in ("USDT", "USDC", "USD"):
        if normalized.endswith(quote) and len(normalized) > len(quote):
            return normalized[: -len(quote)]
    return normalized
