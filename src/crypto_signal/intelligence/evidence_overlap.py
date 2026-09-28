from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import TYPE_CHECKING

from crypto_signal.ledger.serialization import canonical_sha256

if TYPE_CHECKING:
    from crypto_signal.intelligence.confluence_matrix_v2 import (
        ConfluenceFamily,
        ConfluenceFamilyEvidence,
    )

RDP9_EVIDENCE_OVERLAP_ENGINE_VERSION = "rdp9-evidence-overlap-v1/1"
RDP9_EVIDENCE_OVERLAP_SCHEMA_VERSION = "rdp9-evidence-overlap-analysis-v1/1"
_ATTRIBUTION_QUANTUM = Decimal("0.000000000001")
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class EvidenceOverlapRelation:
    relation_identity: str
    source_evidence_identity: str
    family_values: tuple[str, ...]
    attribution_per_family_0_1: Decimal
    schema_version: str = RDP9_EVIDENCE_OVERLAP_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.relation_identity, "RDP9 overlap relation identity")
        _require_sha256(
            self.source_evidence_identity,
            "RDP9 shared source evidence identity",
        )
        if len(self.family_values) < 2:
            raise ValueError("RDP9 overlap relation requires at least two families")
        if self.family_values != tuple(sorted(set(self.family_values))):
            raise ValueError("RDP9 overlap relation families must be canonical")
        if not Decimal(0) < self.attribution_per_family_0_1 <= Decimal(1):
            raise ValueError("RDP9 overlap attribution must be inside (0,1]")
        if self.schema_version != RDP9_EVIDENCE_OVERLAP_SCHEMA_VERSION:
            raise ValueError("unsupported RDP9 overlap relation schema")
        if self.relation_identity != canonical_sha256(_relation_payload(self)):
            raise ValueError("RDP9 overlap relation identity mismatch")


@dataclass(frozen=True, slots=True)
class FamilyEvidenceAttribution:
    family_value: str
    source_evidence_count: int
    shared_source_evidence_count: int
    attribution_factor_0_1: Decimal

    def __post_init__(self) -> None:
        if not self.family_value.strip():
            raise ValueError("RDP9 family attribution requires family value")
        if self.source_evidence_count < 0 or self.shared_source_evidence_count < 0:
            raise ValueError("RDP9 family attribution counts cannot be negative")
        if self.shared_source_evidence_count > self.source_evidence_count:
            raise ValueError("RDP9 shared evidence count exceeds source count")
        if not Decimal(0) <= self.attribution_factor_0_1 <= Decimal(1):
            raise ValueError("RDP9 family attribution factor must be inside [0,1]")
        if self.source_evidence_count == 0 and (
            self.attribution_factor_0_1 != Decimal(1)
        ):
            raise ValueError("RDP9 empty family source set must retain factor 1")


@dataclass(frozen=True, slots=True)
class EvidenceOverlapAnalysis:
    analysis_identity: str
    engine_version: str
    schema_version: str
    family_evidence_identities: tuple[str, ...]
    relations: tuple[EvidenceOverlapRelation, ...]
    attributions: tuple[FamilyEvidenceAttribution, ...]
    shared_source_evidence_identities: tuple[str, ...]
    policy_semantic: str = "equal_attribution_per_exact_shared_source_identity"
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.analysis_identity, "RDP9 overlap analysis identity")
        if self.engine_version != RDP9_EVIDENCE_OVERLAP_ENGINE_VERSION:
            raise ValueError("unsupported RDP9 overlap analysis engine")
        if self.schema_version != RDP9_EVIDENCE_OVERLAP_SCHEMA_VERSION:
            raise ValueError("unsupported RDP9 overlap analysis schema")
        _require_identity_tuple(
            self.family_evidence_identities,
            "RDP9 family evidence identity",
        )
        _require_identity_tuple(
            self.shared_source_evidence_identities,
            "RDP9 shared evidence identity",
        )
        if tuple(item.relation_identity for item in self.relations) != tuple(
            sorted(item.relation_identity for item in self.relations)
        ):
            raise ValueError("RDP9 overlap relations must be canonical")
        if tuple(item.family_value for item in self.attributions) != tuple(
            sorted(item.family_value for item in self.attributions)
        ):
            raise ValueError("RDP9 family attributions must be canonical")
        relation_sources = tuple(
            sorted(item.source_evidence_identity for item in self.relations)
        )
        if relation_sources != self.shared_source_evidence_identities:
            raise ValueError("RDP9 overlap relation/source set mismatch")
        if (
            self.policy_semantic
            != "equal_attribution_per_exact_shared_source_identity"
        ):
            raise ValueError("unsupported RDP9 overlap policy semantic")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("RDP9 overlap analysis cannot grant authority")
        if self.analysis_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("RDP9 overlap analysis identity mismatch")

    @property
    def has_overlap(self) -> bool:
        return bool(self.relations)

    def attribution_factor(
        self,
        family: ConfluenceFamily,
    ) -> Decimal:
        value = family.value
        for item in self.attributions:
            if item.family_value == value:
                return item.attribution_factor_0_1
        raise ValueError("RDP9 overlap analysis missing family attribution")

    @property
    def lineage_identities(self) -> tuple[str, ...]:
        if not self.has_overlap:
            return ()
        return tuple(
            sorted(
                (
                    self.analysis_identity,
                    *(item.relation_identity for item in self.relations),
                )
            )
        )


def analyze_confluence_evidence_overlap(
    evidence: tuple[ConfluenceFamilyEvidence, ...],
) -> EvidenceOverlapAnalysis:
    if not evidence:
        raise ValueError("RDP9 overlap analysis requires family evidence")
    by_family = {item.family.value: item for item in evidence}
    if len(by_family) != len(evidence):
        raise ValueError("RDP9 overlap analysis requires unique families")

    source_to_families: dict[str, set[str]] = {}
    for item in evidence:
        for source_identity in item.source_evidence_identities:
            source_to_families.setdefault(source_identity, set()).add(
                item.family.value
            )

    relations: list[EvidenceOverlapRelation] = []
    for source_identity, families in sorted(source_to_families.items()):
        ordered_families = tuple(sorted(families))
        if len(ordered_families) < 2:
            continue
        with localcontext() as ctx:
            ctx.prec = 36
            attribution = _q(Decimal(1) / Decimal(len(ordered_families)))
        relation_payload = {
            "attribution_per_family_0_1": attribution,
            "family_values": ordered_families,
            "schema_version": RDP9_EVIDENCE_OVERLAP_SCHEMA_VERSION,
            "source_evidence_identity": source_identity,
        }
        relations.append(
            EvidenceOverlapRelation(
                relation_identity=canonical_sha256(relation_payload),
                source_evidence_identity=source_identity,
                family_values=ordered_families,
                attribution_per_family_0_1=attribution,
            )
        )

    relations_tuple = tuple(
        sorted(relations, key=lambda item: item.relation_identity)
    )
    shared = tuple(
        sorted(item.source_evidence_identity for item in relations_tuple)
    )
    relation_by_source = {
        item.source_evidence_identity: item for item in relations_tuple
    }

    attributions: list[FamilyEvidenceAttribution] = []
    for family_value, item in sorted(by_family.items()):
        identities = item.source_evidence_identities
        if not identities:
            factor = Decimal(1)
            shared_count = 0
        else:
            with localcontext() as ctx:
                ctx.prec = 36
                credits = tuple(
                    relation_by_source[identity].attribution_per_family_0_1
                    if identity in relation_by_source
                    else Decimal(1)
                    for identity in identities
                )
                factor = _q(
                    sum(credits, start=Decimal(0))
                    / Decimal(len(identities))
                )
            shared_count = sum(
                1 for identity in identities if identity in relation_by_source
            )
        attributions.append(
            FamilyEvidenceAttribution(
                family_value=family_value,
                source_evidence_count=len(identities),
                shared_source_evidence_count=shared_count,
                attribution_factor_0_1=factor,
            )
        )

    evidence_ids = tuple(sorted(item.evidence_identity for item in evidence))
    attributions_tuple = tuple(
        sorted(attributions, key=lambda item: item.family_value)
    )
    payload = {
        "attributions": attributions_tuple,
        "engine_version": RDP9_EVIDENCE_OVERLAP_ENGINE_VERSION,
        "family_evidence_identities": evidence_ids,
        "policy_semantic": "equal_attribution_per_exact_shared_source_identity",
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "relations": relations_tuple,
        "schema_version": RDP9_EVIDENCE_OVERLAP_SCHEMA_VERSION,
        "shared_source_evidence_identities": shared,
    }
    return EvidenceOverlapAnalysis(
        analysis_identity=canonical_sha256(payload),
        engine_version=RDP9_EVIDENCE_OVERLAP_ENGINE_VERSION,
        schema_version=RDP9_EVIDENCE_OVERLAP_SCHEMA_VERSION,
        family_evidence_identities=evidence_ids,
        relations=relations_tuple,
        attributions=attributions_tuple,
        shared_source_evidence_identities=shared,
    )


def _q(value: Decimal) -> Decimal:
    return value.quantize(_ATTRIBUTION_QUANTUM, rounding=ROUND_HALF_UP)


def _relation_payload(relation: EvidenceOverlapRelation) -> dict[str, object]:
    return {
        "attribution_per_family_0_1": relation.attribution_per_family_0_1,
        "family_values": relation.family_values,
        "schema_version": relation.schema_version,
        "source_evidence_identity": relation.source_evidence_identity,
    }


def _analysis_payload(analysis: EvidenceOverlapAnalysis) -> dict[str, object]:
    return {
        "attributions": analysis.attributions,
        "engine_version": analysis.engine_version,
        "family_evidence_identities": analysis.family_evidence_identities,
        "policy_semantic": analysis.policy_semantic,
        "production_authority": analysis.production_authority,
        "real_capital": analysis.real_capital,
        "relations": analysis.relations,
        "schema_version": analysis.schema_version,
        "shared_source_evidence_identities": (
            analysis.shared_source_evidence_identities
        ),
    }


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be sorted and unique")
    for value in values:
        _require_sha256(value, label)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
