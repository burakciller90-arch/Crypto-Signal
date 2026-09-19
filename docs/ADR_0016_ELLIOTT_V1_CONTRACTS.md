# ADR 0016 — Elliott Wave V1 Structural Contracts

Status: Accepted for V1 implementation
Date: 2026-09-20

## Scope
Elliott V1 is a deterministic structural candidate engine.
It consumes the existing PIT-safe alternating swing substrate.

V1 supports:
- standard impulse price-rule candidates
- partial impulse counts from Wave 1 through completed Wave 5
- generic completed A-B-C correction candidates
- zigzag compatibility evidence
- competing counts
- structural invalidation boundaries
- Fibonacci projection guidelines
- ambiguity and rule-support evidence

V1 does not support diagonals, triangles, double/triple corrections, or recursive degree resolution.
## Scientific boundary
Endpoint geometry cannot by itself prove textbook internal subdivisions such as
5-3-5 for zigzags or 3-3-5 for flats.

Therefore V1 never claims a fully proven correction subtype from same-degree
endpoints alone. It reports compatibility evidence and leaves internal
subdivision proof unresolved.

No Elliott result creates probability, win rate, execution authority or
Confluence by itself.

## Standard impulse hard price rules
For a bullish impulse 0-1-2-3-4-5, with bearish rules mirrored:
1. Wave 2 does not retrace 100% of Wave 1: P2 > P0.
2. Wave 3 moves beyond the end of Wave 1: P3 > P1.
3. Wave 4 retraces less than 100% of Wave 3: P4 > P2.
4. Standard impulse Wave 4 does not enter Wave 1 territory: P4 > P1.
5. When Wave 5 is available, Wave 3 is not the shortest of Waves 1, 3 and 5.

A Wave 5 failure to exceed Wave 3 is recorded as truncation evidence,
not an automatic hard-rule failure.
## Partial impulse counts
Every consecutive alternating prefix of 2 through 6 pivots may form a candidate:
- 2 pivots: Wave 1 complete
- 3 pivots: Wave 2 complete
- 4 pivots: Wave 3 complete
- 5 pivots: Wave 4 complete
- 6 pivots: Wave 5 complete

Only rules testable at the current prefix are evaluated.
A partial candidate is valid-so-far only if every applicable hard rule passes.

The candidate becomes available only when its latest pivot is confirmed and
locally observed.

## Competing counts and ambiguity
Multiple valid-so-far candidates may end at the same latest swing because they
start at different prior swings.

The engine preserves all such counts.
It reports the number of valid competing counts at each end pivot.
It never silently selects one count as uniquely correct.
## Structural invalidation
V1 reports a deterministic hard-rule boundary, not a trade stop.

For bullish counts, bearish mirrored:
- Wave 1 / Wave 2 / Wave 3: origin P0 is the conservative count boundary.
- Wave 4: Wave 1 end P1 is the no-overlap boundary.
- Wave 5 complete: origin P0 remains the completed-count boundary.

This field is descriptive structural invalidation only.

## Projection guidelines
Fibonacci projections are guidelines, not validity rules.

For an active/completed Wave 5:
- equality projection: Wave 5 length = Wave 1 length from P4
- secondary projection: 0.618 x Wave 1 from P4

For a completed A-B-C correction:
- C equality projection: Wave C length = Wave A length from B

Projection residuals are descriptive and never used as probability.
## A-B-C correction geometry
Any four consecutive alternating pivots form a generic completed A-B-C candidate.

Zigzag-compatible geometry requires:
- B terminates before the start of A
- C progresses beyond the end of A in the A direction

The engine stores zigzag compatibility but does not claim 5-3-5 subdivision
proof unless a future recursive lower-degree engine supplies it.

Flat compatibility is not asserted numerically in V1 because endpoint-only
geometry without lower-degree subdivision proof is insufficient for a robust
classification.

## Rule-support evidence
Each candidate stores explicit per-rule PASS / FAIL / NOT_APPLICABLE evidence.

Rule-support fraction =
passed applicable hard rules / applicable hard rules.

This is a descriptive structural-support measure only.
It is not calibrated confidence, probability or expected accuracy.

REAL_CAPITAL remains 0.
