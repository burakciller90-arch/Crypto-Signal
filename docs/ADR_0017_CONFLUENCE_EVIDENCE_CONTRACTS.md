# ADR 0017 — Methodology-Neutral Evidence Contracts

Status: Accepted for Confluence Slice 1 implementation
Date: 2026-09-20

## Purpose
Confluence must consume Price Action, Harmonic and Elliott outputs without
silently changing their meaning.

This slice defines one neutral evidence language.
It does not yet define evidence aging, current-evidence selection,
agreement scoring, signal state or probability.

## Core distinctions
- methodology validity remains owned by the source methodology
- confluence may only adapt already-valid source artifacts
- Price Action market structure is context evidence, not a complete trade setup
- Harmonic valid matches may carry PRZ entry zone, invalidation and reaction targets
- Elliott valid-so-far counts may carry structural invalidation and projection guidelines
- source ambiguity remains explicit
## Neutral evidence fields
Every MethodologyEvidence carries:
- methodology
- exchange / market type / symbol / timeframe
- one shared analysis as-of
- methodology version
- deterministic evidence identity
- setup type
- direction
- validity class
- market availability and local observation time
- optional entry zone
- optional invalidation
- zero or more named targets
- zero or more key levels
- descriptive metrics
- ambiguity flags
- contradiction flags
- short evidence summary

## Direction
Neutral direction vocabulary:
- BULLISH
- BEARISH
- NEUTRAL
- UNRESOLVED

No adapter may manufacture direction when the source methodology has none.
## Validity
Neutral validity vocabulary:
- CONTEXT
- VALID_SO_FAR
- VALID

CONTEXT is not weaker probability.
It means the source artifact describes market context rather than a completed setup.

VALID_SO_FAR means all currently applicable hard rules pass but the source structure is incomplete.

VALID means the source methodology itself marks the artifact complete/valid.

Invalid source artifacts never enter neutral confluence evidence.

## Metrics
EvidenceMetric values are intentionally not normalized in Slice 1.

Examples:
- break distance in bps
- Harmonic ratio residual
- PRZ width in bps
- Elliott rule-support fraction
- competing valid Elliott count

Different metrics are not directly comparable until a later explicit policy says how.
No metric is a calibrated probability.
## Adapter policy

### Price Action
The initial PA adapter emits only the current resolved market-structure context.
It requires a structure break matching the current PA direction.
It does not invent entry, invalidation or targets.

### Harmonic
Only valid HarmonicMatch objects are adapted.
PRZ becomes entry zone.
Pattern invalidation and T1/T2 are preserved exactly.
Ratio residual / PRZ / symmetry metrics remain descriptive.

### Elliott
Only valid-so-far impulse candidates are adapted.
Completed counts are VALID; partial counts are VALID_SO_FAR.
Structural invalidation and projection guidelines are preserved.
competing_valid_count becomes explicit ambiguity evidence.

## Point-in-time
Neutral evidence must satisfy:
market_available_at <= observed_at <= as_of.

Adapters may not move a source artifact earlier in time.

## Non-goals
This slice does not:
- choose the best evidence item
- suppress alternatives because another methodology disagrees
- compute confluence score
- compute win probability
- create Signal state
- create orders
- activate real capital

REAL_CAPITAL remains 0.
