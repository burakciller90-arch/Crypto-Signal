# PAPER STABLE ACTIVATION WATERMARK INIT V1

This operation persists only the immutable activation watermark. It does not
enable the paper trade policy.

The initializer requires the current paper fund to remain pristine:
- exactly one replay record (fund creation);
- 100 USDT cash;
- zero positions;
- therefore no decision/fill/mutation/NAV history.

Signal baseline capture is performed from the production signal ledger in
SQLite `mode=ro`, `query_only`, inside one explicit read transaction. It
captures:
- total signal freeze count;
- latest signal freeze identity;
- latest frozen_at timestamp.

On first invocation, the current timestamp becomes both `activated_at_ms`
and `activation_cutoff_ms`. The latest observed freeze must not postdate that
timestamp.

On any later invocation, the existing immutable activation singleton is
returned with `UNCHANGED`. The cutoff/baseline is never rebased even if new
signal freezes have arrived.

The stable workflow runs the operation twice and requires the second call to
be `UNCHANGED` with the exact same activation identity. It then rechecks the
paper zero-trade invariant.

`trade_policy=NOT_ACTIVATED` and `REAL_CAPITAL=0` remain mandatory.
