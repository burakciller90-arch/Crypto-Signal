# PAPER/STABLE READ-ONLY DRY-RUN OBSERVATION CLOCK

Label: `com.cryptosignal.paperdryrun`

This LaunchAgent runs the already-accepted read-only activation dry-run command
every 120 seconds. It is intentionally separate from the paper account clock
and has no paper-trade write authority.

Inputs:
- immutable production signal ledger;
- persistent paper activation/processed-event tables;
- canonical 15m candle cache;
- cached authoritative Binance venue rules.

Output:
- stdout/stderr logs only under `runtime/paper/paper_dry_run_clock.*.log`.

Every successful invocation must include:
- `PAPER_DRY_RUN_OK`;
- `paper_db_unchanged=YES`;
- `trade_policy=NOT_ACTIVATED`;
- `REAL_CAPITAL=0`.

First installation uses the allowlisted `[PAPER] DRYRUNCLK` workflow surface
with `command: dryrunclockdeploy`.

The normal PAPER deploy path is hardened to stop an already-installed dry-run
clock before switching the stable worktree and to restore/update it atomically
on success or rollback. This prevents the observer from reading code while the
stable worktree is changing.

The observation clock does not authorize virtual trade writes. A future
activation step must be a separate bounded gate based on mechanically observed
post-watermark evidence.
