# R25 Slice 5 — Rich Accepted Evidence Adapters

Status: development candidate. REAL_CAPITAL=0.

This slice enriches the accepted M2–M5 bundle with deeper already-built evidence while preserving the Slice 3 directional constitution.

## Added evidence

- M2 Liquidity: persistent liquidity structure and bounded sweep candidates enrich `LIQUIDITY_MAP`.
- M2 Liquidation: observed liquidation heatmap enriches `LIQUIDATION_MAP`. It explicitly does not estimate future liquidation concentrations or claim retail stop locations.
- M3 Order Flow: price/CVD divergence and absorption freezes enrich the Order Flow proof. They do **not** create a new long/short vote by themselves; the accepted Slice 3 book+taker+CVD consensus remains the only directional shortcut permitted here.
- M4 Derivatives: crowding/squeeze/deleveraging context enriches `DERIVATIVES` without becoming a “funding high => short” or “crowding => trade” rule.
- M5 On-chain: measured wallet cohorts and large-transfer clusters enrich `ONCHAIN`. Registry-only cohorts may be visible proof context but do not count as measured M6 family evidence. No actor intent is inferred.

## Identity and freshness rules

All supplied freezes must match the exact requested market/asset and PIT cutoff. Rich source SHA256 identities are merged into the same M6 family source list and corresponding Decision Proof domain so the Unified Decision Runtime can verify exact source coverage.

Freshness is an explicit versioned adapter policy:
- liquidity/order flow: 30s;
- observed liquidation mark: 60s;
- derivatives: 30m;
- on-chain: 6h.

These are research adapter cutoffs, not universal exchange latency SLAs and not model accuracy.

When richer evidence replaces an earlier missing state, stale `missing_or_stale` / `no_exact_...` summary markers are removed rather than shown beside available proof.

## Authority

No live provider is activated. No exchange order, credential, leverage, canonical Epoch 2 mutation, production deployment, wake/lease resume or real capital is authorized.

Next: run exact composed replay with rich evidence, then build an idempotent shadow/paper writer around the accepted composition path before any separate production activation gate.