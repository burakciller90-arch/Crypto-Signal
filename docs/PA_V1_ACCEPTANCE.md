# PA / SMC / ICT V1 ACCEPTANCE

Status: ACCEPTED
Date: 2026-09-20
REAL_CAPITAL: 0

## Required evidence
- [x] PIT-safe confirmed swing geometry exists before PA logic.
- [x] HH/LH/EH and HL/LL/EL swing relations are structured.
- [x] BOS and CHOCH/MSB are close-based and cannot use unconfirmed pivots.
- [x] Wick-only swing penetration is not a structure break.
- [x] Strict bullish/bearish three-candle FVG detection exists.
- [x] FVG lifecycle records OPEN / MITIGATED / FILLED with PIT timestamps.
- [x] OHLC gap-through ambiguity never invents a fill path.
- [x] BPR requires valid opposing-FVG overlap and temporal validity.
- [x] EQH/EQL pools use explicit configurable tolerance.
- [x] Pool formation waits for the second anchor pivot confirmation.
- [x] Wick sweep + close back inside is SFP; close-through is distinct.
- [x] Previous Day/Week/Month high-low requires complete 15m truth.
- [x] Session levels require explicit IANA timezone and start/end.
- [x] Incomplete ranges suppress numeric high-low truth.
- [x] Displacement uses explicit prior-only rolling thresholds.
- [x] Reference levels carry market availability and local observation time.
- [x] Reclaim/rejection cannot occur before level availability.
- [x] Periodic opens preserve their PIT availability.
- [x] One integrated PA result shares exactly one as-of across all components.
- [x] Integrated PA does not create probability, win rate, confluence score, or order.
- [x] Harmonic and Elliott logic remain absent from PA.
- [x] Deterministic repeat equality is verified in live probes.
- [x] Final all-PA quality + live acceptance chain passes; integrated live gate independently reverified.

## Latest integrated live evidence
Bybit, 4,794 closed BTCUSDT 15m candles:
- current structure: bearish
- structure breaks: 848
- FVGs: 1,138
- BPRs: 92
- liquidity pools: 145
- SFP rejections: 57
- displacement events: 500
- reference levels: 11
- level interactions: 194

Binance, 4,794 closed BTCUSDT 15m candles:
- current structure: bearish
- structure breaks: 823
- FVGs: 1,195
- BPRs: 104
- liquidity pools: 121
- SFP rejections: 45
- displacement events: 506
- reference levels: 11
- level interactions: 189

These counts are descriptive evidence only. They are not a quality score, win probability, or recommendation.
