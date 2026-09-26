from __future__ import annotations

from enum import StrEnum


class StreamEvidenceResolutionState(StrEnum):
    """Canonical F6 proof-resolution states exposed to Product/UI."""

    READY_EXACT = "READY_EXACT"
    IDENTITY_ONLY_EXACT = "IDENTITY_ONLY_EXACT"
    UNAVAILABLE_EXPLICIT = "UNAVAILABLE_EXPLICIT"


def resolution_state_for_visual_state(
    visual_state: str,
) -> StreamEvidenceResolutionState:
    mapping = {
        "resolved_frozen_bundle": StreamEvidenceResolutionState.READY_EXACT,
        "identity_only": StreamEvidenceResolutionState.IDENTITY_ONLY_EXACT,
        "unavailable": StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT,
    }
    return mapping.get(
        visual_state,
        StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT,
    )
