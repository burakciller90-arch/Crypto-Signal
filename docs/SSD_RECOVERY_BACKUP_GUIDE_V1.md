# SSD Recovery & Backup Guide v1

## Scope

This guide covers the accepted non-destructive SSD/runtime recovery model for
Crypto Signal. It does not claim physical reboot/logout/SSD detach tests that
were intentionally not performed autonomously.

Canonical root:

`/Volumes/Crypto-504/Crypto-Signal`

## Fail-closed rule

If the canonical SSD runtime is unavailable, services must fail closed. They
must not silently fall back to removed internal Macintosh project/runtime
payloads.

The historical home-root skeleton may exist only for bounded continuity
compatibility. It is not runtime/database authority.

## Critical runtime data

The accepted R11/R13 chain mechanically covered the live runtime databases:

- live signal ledger;
- alert outbox;
- paper ledger;
- candle cache.

Backup/restore evidence is WAL-aware. A backup is not accepted merely because a
single `.sqlite3` file was copied while WAL state was ignored.

## Safe backup principles

1. keep the source database immutable during verification;
2. use SQLite-aware backup semantics;
3. include WAL state correctly;
4. verify restored database readability/integrity;
5. compare meaningful page/count evidence;
6. never overwrite the only known-good source during a proof;
7. keep backups on a destination with adequate free space.

## Recovery order

1. confirm SSD mount exists;
2. confirm free disk headroom;
3. confirm `Development` checkout is clean and exact current main;
4. confirm runtime DB files exist at canonical SSD locations;
5. run integrity/readability checks;
6. verify SSD supervisor state;
7. verify dashboard child;
8. verify runner listener;
9. verify live health;
10. verify continuity pause/queues;
11. run bounded product/full tests before declaring recovery complete.

## Stale PID handling

A PID file alone is never proof that a service is alive.

For supervisor/dashboard/runner:

- read the PID;
- verify the PID exists;
- verify owner UID;
- verify command path is under the canonical SSD root;
- replace stale PID state only through the accepted recovery path.

## Logs and disk

R11 accepted bounded log rotation and large free-space headroom. Operators should
still investigate unexpected log growth before deleting data.

Do not delete:

- evidence ledgers;
- paper ledger;
- accepted backups;
- current runner/service state

merely to recover disk space.

## Human-impact tests

These remain explicit manual/human-impact acceptance items:

- physical Mac reboot;
- logout/login interruption;
- physical SSD detach/remount.

They were not autonomously executed in R11 or R13 because they could sever the
active user/control session. Their absence is a documented limitation, not a
hidden PASS.

## No legacy fallback

A healthy recovery must not run live Product/Live/Alerts/Paper processes from
removed internal project paths. R13 explicitly guards legacy runtime DB,
component and process paths while allowing a harmless continuity skeleton when
needed by the accepted continuity boundary.
