from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256

EVIDENCE_OVERLAP_ENGINE_VERSION = "rdp9-evidence-overlap-v1/1"


class EvidenceOverlapRelationKind(StrEnum):
    EXACT_SOURCE_OVERLAP = "exact_source_overlap"
    SHARED_ENGINE_LINEAGE = "shared_engine_lineage"


@dataclass(frozen=True, slots=True)
class EvidenceOverlapNode:
    node_id: str
    source_engine_ids: tuple[str, ...]
    source_evidence_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise ValueError("overlap node id must be non-empty")
        _require_text_tuple(self.source_engine_ids, "overlap source engine")
        _require_identity_tuple(
            self.source_evidence_identities,
            "overlap source evidence identity",
        )


@dataclass(frozen=True, slots=True)
class EvidenceOverlapRelation:
    relation_identity: str
    left_node_id: str
    right_node_id: str
    kind: EvidenceOverlapRelationKind
    shared_source_engine_ids: tuple[str, ...]
    shared_source_evidence_identities: tuple[str, ...]
    engine_version: str = EVIDENCE_OVERLAP_ENGINE_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.relation_identity, "overlap relation identity")
        if self.engine_version != EVIDENCE_OVERLAP_ENGINE_VERSION:
            raise ValueError("unsupported overlap relation engine")
        if not self.left_node_id.strip() or not self.right_node_id.strip():
            raise ValueError("overlap relation node ids must be non-empty")
        if self.left_node_id >= self.right_node_id:
            raise ValueError("overlap relation node ids must be canonical")
        _require_text_tuple(
            self.shared_source_engine_ids,
            "overlap shared source engine",
        )
        _require_identity_tuple(
            self.shared_source_evidence_identities,
            "overlap shared source evidence identity",
        )
        if self.kind is EvidenceOverlapRelationKind.EXACT_SOURCE_OVERLAP:
            if not self.shared_source_evidence_identities:
                raise ValueError("exact overlap requires shared source evidence")
        elif not self.shared_source_engine_ids:
            raise ValueError("shared-engine overlap requires shared engine lineage")
        if self.relation_identity != canonical_sha256(_relation_payload(self)):
            raise ValueError("overlap relation identity mismatch")


@dataclass(frozen=True, slots=True)
class EvidenceOverlapReport:
    report_identity: str
    node_ids: tuple[str, ...]
    relation_identities: tuple[str, ...]
    exact_overlap_relation_identities: tuple[str, ...]
    shared_source_evidence_identities: tuple[str, ...]
    exact_overlap_components: tuple[tuple[str, ...], ...]
    engine_version: str = EVIDENCE_OVERLAP_ENGINE_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.report_identity, "overlap report identity")
        if self.engine_version != EVIDENCE_OVERLAP_ENGINE_VERSION:
            raise ValueError("unsupported overlap report engine")
        _require_text_tuple(self.node_ids, "overlap report node id")
        _require_identity_tuple(
            self.relation_identities,
            "overlap report relation identity",
        )
        _require_identity_tuple(
            self.exact_overlap_relation_identities,
            "overlap exact relation identity",
        )
        if not set(self.exact_overlap_relation_identities).issubset(
            self.relation_identities
        ):
            raise ValueError("exact overlap relation missing from report")
        _require_identity_tuple(
            self.shared_source_evidence_identities,
            "overlap report shared source evidence",
        )
        previous: tuple[str, ...] | None = None
        seen: set[str] = set()
        for component in self.exact_overlap_components:
            _require_text_tuple(component, "overlap component node")
            if len(component) < 2:
                raise ValueError("overlap component requires at least two nodes")
            if previous is not None and component <= previous:
                raise ValueError("overlap components must be canonical")
            if seen.intersection(component):
                raise ValueError("overlap components cannot share nodes")
            seen.update(component)
            previous = component
        if self.report_identity != canonical_sha256(_report_payload(self)):
            raise ValueError("overlap report identity mismatch")

    @property
    def has_exact_overlap(self) -> bool:
        return bool(self.exact_overlap_relation_identities)


def build_evidence_overlap_report(
    nodes: tuple[EvidenceOverlapNode, ...],
) -> tuple[EvidenceOverlapReport, tuple[EvidenceOverlapRelation, ...]]:
    ordered = tuple(sorted(nodes, key=lambda item: item.node_id))
    node_ids = tuple(item.node_id for item in ordered)
    if len(set(node_ids)) != len(node_ids):
        raise ValueError("overlap report node ids must be unique")

    relations: list[EvidenceOverlapRelation] = []
    exact_edges: set[tuple[str, str]] = set()
    shared_evidence: set[str] = set()
    for index, left in enumerate(ordered):
        left_engines = set(left.source_engine_ids)
        left_evidence = set(left.source_evidence_identities)
        for right in ordered[index + 1 :]:
            shared_ids = tuple(
                sorted(left_evidence.intersection(right.source_evidence_identities))
            )
            shared_engines = tuple(
                sorted(left_engines.intersection(right.source_engine_ids))
            )
            if shared_ids:
                kind = EvidenceOverlapRelationKind.EXACT_SOURCE_OVERLAP
                exact_edges.add((left.node_id, right.node_id))
                shared_evidence.update(shared_ids)
            elif shared_engines:
                kind = EvidenceOverlapRelationKind.SHARED_ENGINE_LINEAGE
            else:
                continue
            payload = {
                "engine_version": EVIDENCE_OVERLAP_ENGINE_VERSION,
                "kind": kind,
                "left_node_id": left.node_id,
                "right_node_id": right.node_id,
                "shared_source_engine_ids": shared_engines,
                "shared_source_evidence_identities": shared_ids,
            }
            relations.append(
                EvidenceOverlapRelation(
                    relation_identity=canonical_sha256(payload),
                    left_node_id=left.node_id,
                    right_node_id=right.node_id,
                    kind=kind,
                    shared_source_engine_ids=shared_engines,
                    shared_source_evidence_identities=shared_ids,
                )
            )

    ordered_relations = tuple(
        sorted(relations, key=lambda item: item.relation_identity)
    )
    exact_relation_ids = tuple(
        sorted(
            item.relation_identity
            for item in ordered_relations
            if item.kind is EvidenceOverlapRelationKind.EXACT_SOURCE_OVERLAP
        )
    )
    components = _connected_components(node_ids, exact_edges)
    payload = {
        "engine_version": EVIDENCE_OVERLAP_ENGINE_VERSION,
        "exact_overlap_components": components,
        "exact_overlap_relation_identities": exact_relation_ids,
        "node_ids": node_ids,
        "relation_identities": tuple(
            item.relation_identity for item in ordered_relations
        ),
        "shared_source_evidence_identities": tuple(sorted(shared_evidence)),
    }
    report = EvidenceOverlapReport(
        report_identity=canonical_sha256(payload),
        node_ids=node_ids,
        relation_identities=tuple(
            item.relation_identity for item in ordered_relations
        ),
        exact_overlap_relation_identities=exact_relation_ids,
        shared_source_evidence_identities=tuple(sorted(shared_evidence)),
        exact_overlap_components=components,
    )
    return report, ordered_relations


def _connected_components(
    node_ids: tuple[str, ...],
    edges: set[tuple[str, str]],
) -> tuple[tuple[str, ...], ...]:
    adjacency: dict[str, set[str]] = {node: set() for node in node_ids}
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    visited: set[str] = set()
    components: list[tuple[str, ...]] = []
    for node in node_ids:
        if node in visited or not adjacency[node]:
            continue
        stack = [node]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            stack.extend(sorted(adjacency[current] - visited, reverse=True))
        if len(component) >= 2:
            components.append(tuple(sorted(component)))
    return tuple(sorted(components))


def _relation_payload(
    relation: EvidenceOverlapRelation,
) -> dict[str, object]:
    return {
        "engine_version": relation.engine_version,
        "kind": relation.kind,
        "left_node_id": relation.left_node_id,
        "right_node_id": relation.right_node_id,
        "shared_source_engine_ids": relation.shared_source_engine_ids,
        "shared_source_evidence_identities": (
            relation.shared_source_evidence_identities
        ),
    }


def _report_payload(report: EvidenceOverlapReport) -> dict[str, object]:
    return {
        "engine_version": report.engine_version,
        "exact_overlap_components": report.exact_overlap_components,
        "exact_overlap_relation_identities": (
            report.exact_overlap_relation_identities
        ),
        "node_ids": report.node_ids,
        "relation_identities": report.relation_identities,
        "shared_source_evidence_identities": (
            report.shared_source_evidence_identities
        ),
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


def _require_text_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        if not value.strip():
            raise ValueError(f"{label} must be non-empty")


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)
