# Elliott Wave V1 Acceptance

Date: 2026-09-20
Status: ACCEPTED

## Scope accepted
Elliott V1 is a deterministic structural candidate engine that provides:
- partial impulse counts from Wave 1 through completed Wave 5
- standard impulse hard-price-rule evidence
- completed A-B-C endpoint candidates
- zigzag compatibility evidence
- competing counts rather than one forced count
- structural invalidation boundaries
- Wave 5 Fibonacci guideline projections
- C=A correction projection
- explicit truncation evidence
- ambiguity summaries
- descriptive rule-support fractions

REAL_CAPITAL remains 0.
## Hard-rule basis
For standard impulse price geometry, V1 enforces:
- Wave 2 does not retrace 100% of Wave 1.
- Wave 3 moves beyond the end of Wave 1.
- Wave 4 retraces less than 100% of Wave 3.
- Wave 4 does not overlap Wave 1 price territory.
- Wave 3 is not the shortest of Waves 1, 3 and 5 once Wave 5 exists.

Wave 5 failure to exceed Wave 3 is truncation evidence, not an automatic
hard-rule failure.

Rules not yet testable at a partial count are NOT_APPLICABLE rather than PASS.
## Correction boundary
Endpoint geometry alone cannot prove internal Elliott subdivisions.

Accordingly:
- every four alternating pivots may form a generic A-B-C endpoint candidate
- zigzag compatibility requires B to terminate before A origin and C to
  progress beyond A in the A direction
- V1 does not claim 5-3-5 subdivision proof
- V1 does not assert flat subtype certainty from endpoints alone
- diagonals, triangles, combinations and recursive degree resolution are out of scope

This prevents the engine from manufacturing textbook certainty from insufficient data.
## Mechanical quality evidence
Final repository gate:
- pytest: 127 passed
- Ruff: PASS
- mypy: PASS
- Elliott focused tests: 10 passed
- partial-wave NOT_APPLICABLE semantics: PASS
- Wave 4 overlap rejection: PASS
- Wave 3 shortest rejection: PASS
- truncated fifth retained without false invalidation: PASS
- competing counts preserved: PASS
- zigzag compatibility geometry: PASS
- Wave 5 candidate is unavailable before final pivot confirmation: PASS
- future candles do not change prior as-of Elliott result: PASS
## Long 15m live deterministic probe
Bybit BTCUSDT:
- closed candles: 4,798
- impulse candidates: 5,110
- completed impulse candidates: 1,020
- hard-price-rule-valid completed counts: 63
- valid counts with truncated fifth evidence: 33
- A-B-C candidates: 1,022
- zigzag-compatible endpoint geometries: 316
- end pivots with more than one valid competing count: 870

Binance BTCUSDT:
- closed candles: 4,798
- impulse candidates: 4,900
- completed impulse candidates: 978
- hard-price-rule-valid completed counts: 60
- valid counts with truncated fifth evidence: 28
- A-B-C candidates: 980
- zigzag-compatible endpoint geometries: 304
- end pivots with more than one valid competing count: 828
## Multi-timeframe live smoke
Bybit valid completed impulse / zigzag-compatible counts:
- 15m: 5 / 32
- 1h: 5 / 34
- 4h: 4 / 29
- 1D: 8 / 39
- 1W: 6 / 20

Binance:
- 15m: 5 / 29
- 1h: 5 / 33
- 4h: 4 / 28
- 1D: 8 / 39
- 1W: 10 / 28

All five V1 timeframes completed deterministically on both providers.
## Interpretation
The counts above do not mean the engine discovered that many uniquely correct
Elliott labels.

They mean the endpoint sequences satisfy the currently testable V1 structural
price rules. High competing-count counts are expected evidence of Elliott
ambiguity and are intentionally preserved.

rule_support_fraction is descriptive structural support only.
It is not calibrated confidence, probability, win rate or correctness.

## Canonical next frontier
Confluence + Signal Semantics:
- consume PA, Harmonic and Elliott as independent structured outputs
- preserve agreement and contradiction explicitly
- never turn confluence score into probability
- support NO_SIGNAL / NEUTRAL / WATCH / ACTIVE / INVALIDATED semantics
- establish deterministic signal-object contracts before immutable live freeze
