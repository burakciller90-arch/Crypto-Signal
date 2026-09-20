# PAPER POSITION SIZING POLICY V1

Status: candidate Stage 6C pure sizing layer. It does not activate PAPER/STABLE trading.

Policy version: `paper_position_sizing_policy.v1`.

BUY sizing requires the frozen Binance reference price to remain inside every provider's frozen entry zone and above every bullish invalidation. The policy chooses the lowest provider invalidation, producing the widest risk distance, then computes raw pre-venue quantity as autonomy max-position-risk USDT divided by that risk distance.

The quantity is intentionally not rounded to Binance lot size and does not include fee/spread/slippage yet. The result explicitly requires both venue-rule checking and cost adjustment downstream.

EXIT sizing uses the complete existing virtual long quantity. No automatic REDUCE or short sizing is created.

Signal, autonomy and execution-input identities must match exactly. This layer has no ledger mutation, exchange/network access or fill authority. Next gate is a frozen venue-rule/cost snapshot plus downward quantity rounding and existing planner validation.

REAL_CAPITAL remains 0.
