# V2+ BIRTHDAY EDITION — FOCUSED WORLD-CLASS ROADMAP

Status: governing post-V1 execution roadmap.
Created: 2026-09-20.
Purpose: finish a focused, Turkish-first, gift-ready Crypto Signal product without uncontrolled scope expansion.
REAL_CAPITAL=0.

## Release definition
The Birthday Edition is complete when a non-developer can open the platform, understand what matters now,
inspect why the system thinks it matters, see multi-timeframe context and chart evidence, review immutable history,
and receive useful alerts — without fabricated probability or performance claims.

## Execution order

### Stage 0 — Close the current canonical freeze frontier
- Finish freeze_live_candles() extraction.
- Preserve exact provider-path 15m semantics.
- Prove source-cutoff idempotence and direct/provider equivalence.
- Accept canonical aggregated candles through the same immutable freeze path.
- Keep higher-timeframe production disabled until the full gate passes.
- Run focused tests, Ruff, mypy, full pytest, uv lock and git diff checks.
Exit: clean accepted commit and documented checkpoint.

### Stage 1 — Multi-timeframe production truth
- Activate BTCUSDT 1h and 4h from canonical 15m aggregation first.
- Validate cache/backfill completeness, restart behavior and production isolation.
- Add 1D after 1h/4h evidence is stable; 1W remains optional for the Birthday Edition if operationally expensive.
- Present top-down timeframe context without synthesizing cross-provider candles.
Exit: stable live evidence for the selected timeframes with immutable freezes and no regression to 15m.

### Stage 2 — Focused multi-asset market coverage
- Expand from BTCUSDT to a deliberately small high-liquidity universe.
- Initial target set: BTC, ETH and SOL; add further assets only if reliability and UI density stay strong.
- Keep provider/market-type boundaries explicit.
- Make Market Radar genuinely useful by ranking attention, not by inventing certainty.
Exit: the user no longer needs to manually visit every tracked chart to discover notable structures.

### Stage 3 — Turkish premium Mission Control
- Rework information hierarchy around 'what matters now'.
- Turkish-first navigation and human-readable state labels.
- Home summary: monitored universe, attention candidates, strong methodology agreement, recent changes and system health.
- Make uncertainty and 'not enough evidence' first-class, not hidden.
- Preserve advanced technical detail behind drill-down.
Exit: a first-time user can understand the product without reading engineering documentation.

### Stage 4 — Visual chart intelligence
- Render canonical candles and evidence overlays.
- PA overlays: swings, BOS/CHoCH, liquidity pools/sweeps, FVG/BPR, periodic/reference levels and interactions.
- Harmonic overlays: XABCD/PRZ/invalidation/targets only from valid frozen evidence.
- Elliott overlays: competing structural candidates and invalidation, with ambiguity visibly preserved.
- Signal geometry appears only when the frozen signal really owns complete geometry.
Exit: the backend's analytical value is visually inspectable rather than hidden in JSON-like detail.

### Stage 5 — Decision-quality signal experience
- Build concise Turkish explanation from frozen evidence only.
- Show methodology agreement/contradiction, direction, timeframe context, invalidation, targets and uncertainty.
- Distinguish 'İzleniyor' from 'Aktif Sinyal' clearly.
- Add recent-change context so the user sees why an item moved in priority.
Exit: every surfaced candidate answers 'neden önemli, ne bozabilir, ne eksik?'.

### Stage 6 — Useful alerts
- Keep alert eligibility conservative and versioned.
- Produce Turkish notification presentation.
- Notify on meaningful ACTIVE/invalidation transitions; avoid WATCH spam.
- External provider integration requires explicit credential/provider choice and must be idempotent.
Exit: alerts reduce monitoring burden without becoming noisy or misleading.

### Stage 7 — Honest performance and learning surface
- Continue accumulating immutable forward evidence.
- Show no win-rate when decisive sample size is absent.
- Keep evidence classes separate.
- Add interpretable segmentation by asset, timeframe, setup, methodology geometry source and regime when available.
- Promote calibrated probability only after sufficient data and a separately accepted calibration design.
Exit: performance answers what is actually known, with sample size and evidence class visible.

### Stage 8 — Limited V2+ intelligence
Only add features that directly improve the focused product:
- deterministic market-regime labeling,
- bounded derivatives context such as funding/open interest when source contracts are reliable,
- stronger attention ranking using evidence, not fabricated probability,
- product/system health visibility.
Defer broad ML, order-book research, autonomous trading and large research automation until after Birthday Edition acceptance.

### Stage 9 — Gift-ready integrated acceptance
- Full repository quality gate.
- Stable worktree deployments for live/product/alerts.
- Restart and isolation tests.
- Turkish UX review across all primary surfaces.
- Empty/error/loading states reviewed.
- No mock data in runtime product truth.
- No write/order path exposed.
- A newcomer usability pass: important state understandable in 20-30 seconds.
Exit: immutable release checkpoint tagged as the Birthday Edition candidate.

## Scope discipline
Prefer fewer assets and timeframes with excellent reliability and presentation over wide but shallow coverage.
Every new feature must improve at least one of: scientific integrity, monitoring coverage, decision usefulness or product clarity.
If it does not, park it.

## Immediate next action
Resume the exact Stage 0 uncommitted freeze-path refactor from HEAD 5233193 after state-first verification.
Do not replay archived wake/lease events. New work starts only from current mechanical state.
