# Dashboard Open & Recovery Guide v1

## Open the accepted dashboard

Primary URL:

`http://127.0.0.1:48700/`

On the Mac, the operator may open that localhost URL in the browser. The
dashboard is read-only with respect to real capital and must report
`REAL_CAPITAL=0`.

Expected Gift Edition shell markers include:

- `GIFT EDITION · SADE BAŞLANGIÇ`;
- `KISACA`;
- `İSTİHBARAT LABORATUVARI`.

## Fast health check

```bash
curl -fsS http://127.0.0.1:48700/api/health
curl -fsS http://127.0.0.1:48700/api/intelligence-center
```

Do not treat a rendered HTML page alone as proof of runtime health.

## If the page is unavailable

Check in this order:

1. SSD root exists at `/Volumes/Crypto-504/Crypto-Signal`;
2. supervisor PID file exists and PID is alive;
3. dashboard PID file exists and PID is alive;
4. dashboard process points to the SSD `Product` checkout;
5. dashboard command contains explicit SSD ledger/outbox/paper/cache paths;
6. `/api/health` returns clean read-only state.

The SSD supervisor is expected to restart a dead dashboard child. Do not
blindly revive the historical launchd dashboard path when the supervisor is the
current owner.

## If the page is old or missing new UI

Compare:

- `Product` HEAD;
- `Development` / `origin/main` HEAD;
- product/runtime diff only.

A docs/acceptance-only main advance does not necessarily require Product
redeploy. If product files differ, use the tested rollback-safe
`productdeploy` workflow; do not manually reset Product.

## Research Lab interpretation

An accepted research engine card means the engine/capability contract is
accepted. It does **not** mean:

- it is contributing to production weighting;
- it has a live runtime feed;
- it is calibrated probability;
- it can place an order.

The UI must explicitly show missing/unavailable evidence instead of fabricating
a result.

## Beginner view

The default Gift Edition view is intentionally beginner-first. Advanced
sections may be hidden until the user asks for details. Hiding a section is a UX
choice, not removal of the evidence.

## Rollback

The canonical Product deployment is rollback-safe. If health acceptance fails,
the workflow restores the previous Product commit and restarts through the
current runtime owner.

After any rollback or recovery, mechanically re-check:

- Product HEAD;
- `/api/health`;
- Research Lab endpoint;
- Gift Edition shell;
- `REAL_CAPITAL=0`.
