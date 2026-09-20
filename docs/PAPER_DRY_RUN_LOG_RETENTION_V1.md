# PAPER DRY-RUN LOG RETENTION V1

The read-only PAPER/STABLE dry-run observation clock runs every 120 seconds, so
its stdout/stderr must not grow without bound.

V1 keeps the paper database completely outside the retention path. Before each
clock execution a tiny launcher checks only:
- paper_dry_run_clock.out.log;
- paper_dry_run_clock.err.log.

If a current log is larger than 5 MiB, the previous .1 backup is removed and
the current file is atomically renamed to .1. The new run then opens a fresh
current log. At most one backup per stream is retained.

The launcher then execs the existing read-only dry-run process with its fixed
paper/signal/candle paths and max-events=100. It emits one
PAPER_DRY_RUN_LOG_RETENTION line before the normal dry-run output.

The launchd plist no longer uses StandardOutPath/StandardErrorPath; the launcher
owns those two bounded observation logs directly. PAPER STATE reads both the
current log and .1 backup when looking for recent PRETRADE_READY attention
evidence.

This feature never opens or mutates the paper SQLite database itself.
trade_policy remains NOT_ACTIVATED and REAL_CAPITAL remains 0.
