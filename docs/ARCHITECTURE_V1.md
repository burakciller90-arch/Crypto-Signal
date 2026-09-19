# V1 ARCHITECTURE BOUNDARIES

## Dependency direction
Exchange adapters -> Data Truth -> deterministic primitives -> independent methodology engines ->
Confluence -> Signal -> immutable ledger -> Outcome/Evaluation -> API/UI/Alerts.

## Mandatory independence
Price Action, Harmonic and Elliott must be independently testable.
Confluence consumes their structured outputs; it does not silently redo their analysis.
LLM/explanation layers may explain evidence but never create numeric truth.

## State classes
- Market data: append/correct only through explicit provenance rules.
- Analysis result: versioned deterministic/statistical output.
- Signal: decision-time object.
- Frozen signal: immutable decision snapshot.
- Outcome: appended later; never rewrites the frozen signal.
- Evidence class: RETROSPECTIVE, WALK_FORWARD, LIVE_UNTOUCHED_FORWARD.

## Runtime lanes
- LIVE/STABLE: ingestion, analysis, freezing, outcomes.
- INTELLIGENCE LAB: future bounded research; never silently promotes.
- PRODUCT/COMMAND CENTER: views over evidence and state.

## V1 boundary
No order execution service exists in V1.
