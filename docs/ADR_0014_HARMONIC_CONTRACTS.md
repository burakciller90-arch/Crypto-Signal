# ADR 0014 — Harmonic V1 Ratio and Geometry Contracts

Status: Accepted for Harmonic V1 implementation
Date: 2026-09-20

## Scope
Harmonic V1 recognizes deterministic XABCD candidates for:
- Gartley
- Bat
- Butterfly
- Crab
- Deep Crab

The engine consumes the existing PIT-safe alternating swing substrate.
It does not call PA conclusions, Elliott logic, Confluence, probability models, or execution.

## Ratio definitions
For X,A,B,C,D pivot prices:
- XA = abs(A - X)
- AB = abs(B - A)
- BC = abs(C - B)
- CD = abs(D - C)
- B/XA retracement = AB / XA
- C/AB retracement = BC / AB
- D/BC projection = CD / BC
- D/XA retracement-or-extension = abs(D - A) / XA
- CD/AB = CD / AB

All leg lengths must be positive.

## V1 ideal pattern contracts

### Gartley
- B/XA target 0.618, relative tolerance 3%
- C/AB 0.382-0.886
- D/BC 1.13-1.618
- D/XA target 0.786, relative tolerance 3%
- CD/AB 1.0-1.27
- invalidation limit: 1.0 XA beyond A in the D direction

### Bat
- B/XA 0.382-0.50 (ideal V1 contract)
- C/AB 0.382-0.886
- D/BC 1.618-2.618
- D/XA target 0.886, relative tolerance 3%
- CD/AB 1.0-1.618
- invalidation limit: 1.13 XA

### Butterfly
- B/XA target 0.786, relative tolerance 3%
- C/AB 0.382-0.886
- D/BC 1.618-2.618
- D/XA target 1.27, relative tolerance 3%
- CD/AB 1.0-1.27
- invalidation limit: 1.414 XA

### Crab
- B/XA 0.382-0.618
- C/AB 0.382-0.886
- D/BC 2.618-3.618
- D/XA target 1.618, relative tolerance 3%
- CD/AB 1.0-1.618
- invalidation limit: 2.0 XA

### Deep Crab
- B/XA target 0.886, relative tolerance 3%
- C/AB 0.382-0.886
- D/BC 2.24-3.618
- D/XA target 1.618, relative tolerance 3%
- CD/AB 1.0-1.618
- invalidation limit: 2.0 XA

These are explicit V1 ideal contracts. Wider discretionary variants are not silently accepted.

## Candidate geometry
Five consecutive deterministic alternating swings form one XABCD candidate.
Bullish candidate:
LOW X -> HIGH A -> LOW B -> HIGH C -> LOW D.
Bearish is the exact inverse.

Candidate market availability is the D pivot confirmation time.
Candidate local availability is the D pivot observation time.

## Potential Reversal Zone
For each validated candidate the engine computes three deterministic completion projections:
- pattern-specific D/XA target
- nearest permitted D/BC harmonic anchor
- nearest permitted CD/AB harmonic anchor

The PRZ is the min/max envelope of those projected D prices.
The result stores:
- PRZ low/high
- PRZ width in basis points
- individual projection prices
- actual D distance from each projection
- deterministic Fib clustering width

PRZ width is descriptive geometry, not a probability score.

## Ratio residual
Each candidate stores per-ratio residuals.
Target ratios use relative error to target.
Range ratios use zero residual while inside the permitted interval and normalized distance to the nearest boundary outside it.
A valid pattern must satisfy every mandatory constraint.

## Symmetry
AB/CD time symmetry is stored as:
abs(AB bar duration - CD bar duration) / max(AB bar duration, CD bar duration)

It is descriptive evidence in V1 and is not a hard validity gate.

## Invalidation and reaction targets
Invalidation uses the pattern-specific XA stop-limit ratio projected in the D direction.

V1 reaction objectives are deterministic descriptive levels:
- T1: 38.2% retracement of the A-D leg from D toward A
- T2: 61.8% retracement of the A-D leg from D toward A

These are evidence fields, not orders or guarantees.

## Point-in-time rule
No candidate exists before D is confirmed and locally observed.
No later candle may alter the frozen XABCD geometry at an earlier as-of.

REAL_CAPITAL remains 0.
