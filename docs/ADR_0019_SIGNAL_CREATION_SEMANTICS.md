# ADR 0019 — Signal Creation Semantics and Freeze-Ready Contract

Status: Accepted for Signal Slice 1 implementation
Date: 2026-09-20

## Purpose
Signal creation converts one deterministic ConfluenceAnalysisResult into one
freeze-ready SignalDecision.

The initial decision may be:
- NO_SIGNAL
- NEUTRAL
- WATCH
- ACTIVE

INVALIDATED is never created retroactively at decision time.
It is a later lifecycle state produced only from new point-in-time market evidence.

## Direction
Signal direction vocabulary:
- BULLISH
- BEARISH
- NONE

NO_SIGNAL and NEUTRAL always use NONE.
WATCH and ACTIVE use the resolved Confluence dominant direction.

## State creation rules

### NO_SIGNAL
Use when there is no resolved directional methodology vote and no selected
bullish/bearish evidence artifact.

### NEUTRAL
Use when directional evidence exists but Confluence has no dominant direction,
including directional ties or internal source conflicts that prevent resolution.

### WATCH
Use when Confluence has a resolved dominant direction but ACTIVE requirements
are not all met.

Examples:
- only one methodology votes
- an opposing methodology vote exists
- no complete entry/invalidation/target geometry exists
- more than one distinct complete geometry candidate exists

WATCH may preserve one complete geometry if exactly one exists, but it remains
non-active because the independent-methodology activation rule is not met.

### ACTIVE
ACTIVE requires all of:
1. resolved BULLISH or BEARISH Confluence direction
2. at least two independent methodologies vote for that direction
3. zero methodology votes against that direction
4. exactly one selected evidence artifact in the dominant direction provides:
   - entry zone
   - invalidation price + invalidation trigger
   - at least one target

No arbitrary score threshold is used.
Under the V1 score formula these requirements imply at least 66.67, but the
state rule is expressed in methodology counts and geometry, not by threshold.

## Geometry source
Signal creation never combines entry from one methodology with invalidation or
targets from another.

One complete MethodologyEvidence item supplies the entire SignalGeometry.

If more than one distinct complete geometry candidate is selected, signal state
is WATCH and geometry is left unresolved rather than silently picking a winner.

## Entry reference and expected R/R
The signal preserves the full entry zone.

For descriptive expected-R/R only, V1 uses the zone midpoint as a reference:
entry_reference_model = ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION

This is not an execution instruction or fill assumption.

For bullish:
- risk = entry midpoint - invalidation
- reward = target - entry midpoint

For bearish:
- risk = invalidation - entry midpoint
- reward = entry midpoint - target

Risk and reward must both be strictly positive before an R/R value is emitted.

## Invalidation trigger
Neutral evidence now preserves an invalidation trigger.

V1 source mappings:
- Harmonic hard boundary -> TOUCH_OR_CROSS
- Elliott hard structural boundary -> TOUCH_OR_CROSS
- Price Action context has no signal invalidation in the initial adapter

Signal creation copies the source trigger unchanged.

## Scientific separation
The SignalDecision stores:
- confluence score and its agreement-index semantic
- calibrated probability status
- historical-analogue status

V1 values:
- calibrated probability: NOT_CALIBRATED
- historical analogue statistics: NOT_EVALUATED

No numeric probability is fabricated.

Confluence score remains separate from probability, historical success rate,
confidence and expected return.

## Freeze identity
Every SignalDecision receives a deterministic SHA256 freeze identity from its
canonical decision-time fields:
- schema version
- market identity
- as-of
- initial state/direction
- setup/geometry
- selected evidence identities
- methodology versions
- confluence counts/score semantic
- uncertainty flags

A lifecycle transition never rewrites this identity.

## REAL_CAPITAL
SignalDecision is analysis output only.
REAL_CAPITAL remains 0.
