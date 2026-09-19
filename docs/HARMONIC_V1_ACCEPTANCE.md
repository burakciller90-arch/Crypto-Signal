# Harmonic V1 Acceptance

Date: 2026-09-20
Status: ACCEPTED

## Scope accepted
Harmonic V1 now provides deterministic point-in-time:
- alternating XABCD candidate enumeration
- Gartley, Bat, Butterfly, Crab and Deep Crab contracts
- per-ratio validity and residual evidence
- PRZ projections and clustering width
- AB/CD time-symmetry evidence
- pattern-specific invalidation geometry
- 38.2% and 61.8% reaction targets
- explicit valid versus invalid match semantics
- nonphysical projection handling without fabricated prices
## Contract corrections made during acceptance
The initial draft over-constrained Crab and Deep Crab CD/AB geometry.
V1 now treats AB=CD as a minimum completion component for Crab-family
patterns instead of imposing an incompatible hard upper bound.

The exact-D target tolerance used where a source does not publish one is
explicitly documented as an engineering tolerance, not source truth.

## Shared weekly-grid correction
Live multi-timeframe verification exposed a common primitive bug:
1W opens were validated against a Unix-epoch zero anchor instead of
Monday 00:00 UTC.

The canonical weekly anchor now lives in the shared timeframe contract
and is reused by aggregation, recovery, swing primitives and PA validators.
## Mechanical quality evidence
Final repository gate:
- pytest: 117 passed
- Ruff: PASS
- mypy: PASS
- deterministic Harmonic unit/PIT tests: PASS
- all five pattern fixtures validate in deterministic synthetic geometry
- bullish and bearish mirrored fixtures both validate
- future candles do not change a prior as-of result
- D candidate does not exist before its confirmation/observation time
- nonphysical theoretical projections invalidate geometry instead of crashing analysis

## Long 15m live deterministic probe
Bybit BTCUSDT:
- closed candles: 4,797
- XABCD candidates: 1,021
- pattern evaluations: 5,105
- valid matches: 0
- degenerate candidates: 0
- ambiguous swing sources: 21
Binance BTCUSDT:
- closed candles: 4,797
- XABCD candidates: 979
- pattern evaluations: 4,895
- valid matches: 0
- degenerate candidates: 0
- ambiguous swing sources: 18

Zero valid matches in this particular 15m sample is accepted.
The engine must not fabricate a Harmonic setup merely to produce output.

## Multi-timeframe live smoke
Bybit:
- 15m: 499 closed / 100 candidates / 0 valid
- 1h: 499 / 107 / 0
- 4h: 499 / 90 / 0
- 1D: 499 / 111 / 0
- 1W: 271 / 60 / 0

Binance:
- 15m: 499 closed / 96 candidates / 0 valid
- 1h: 499 / 107 / 0
- 4h: 499 / 88 / 0
- 1D: 499 / 111 / 1 valid
- 1W: 474 / 85 / 0
Weekly invalid candidates included nonphysical theoretical projections:
- Bybit 1W: 4 pattern evaluations
- Binance 1W: 31 pattern evaluations

Those evaluations remained invalid evidence and did not terminate analysis.

## Scientific interpretation
Candidate count, residual, PRZ width, symmetry and valid-match count are
descriptive evidence only. None is a probability, win rate or execution signal.

Harmonic V1 acceptance does not authorize Elliott, Confluence, signals,
portfolio actions or exchange execution by itself.
REAL_CAPITAL remains 0.

## Canonical next frontier
Elliott Wave V1:
- explicit wave-candidate structures
- impulse and ABC rule contracts
- competing counts rather than one forced count
- validity, invalidation, current wave and projection evidence
- ambiguity/confidence kept descriptive and non-probabilistic
- deterministic PIT and live validation
