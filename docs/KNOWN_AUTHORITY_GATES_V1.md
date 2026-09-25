# Known Intentional Authority Gates v1

These gates are deliberate. They are not unfinished bugs.

## Real capital and exchange execution

- `REAL_CAPITAL=0`.
- No real exchange-order endpoint is authorized.
- No exchange credential authority is authorized.
- No workflow may reinterpret paper/simulation output as permission to trade
  real funds.

## Paper authority

Paper authority is epoch-specific and remains simulation-only.

- **Epoch 1** is the immutable historical 100 USDT paper record. It remains replayable history and is not canonical for new activity.
- **Epoch 2** is the current 1,000 USDT paper-program contract for new canonical activity, governed by `docs/PAPER_FUND_EPOCH2_V1_SPEC.md` and its later accepted runtime/activation evidence.
- Epoch 1 and Epoch 2 must never be silently merged, rescaled or presented as one unlabeled performance series.
- No paper epoch creates exchange-order, credential or real-money authority.

A non-activated/blocked paper state is valid. A paper candidate, simulated fill, paper NAV or Mission Control state is never real-money authority.

## Research authority

Stage 8/8.5, Alpha Factory, bounded ML, Learning Memory and Research Lab evidence
are research evidence.

Accepted research does not automatically gain production contribution,
production weights, champion status, deploy authority or order authority.

## ML promotion authority

The accepted ML promotion dossier can reach machine/supervisor review states but
does not contain an automatic `PROMOTED` state.

Any future champion/write/deploy authority requires a separate explicit,
mechanically tested policy.

## Meta-intelligence authority

The Stage 9 meta-intelligence policy is shadow-only.

- signed balance is not probability;
- correlation/regime weights are immutable policy inputs;
- policy gaps fail closed;
- production contribution remains 0.

## Probability claims

Do not label any of these as calibrated win probability without separately
accepted calibration evidence:

- confluence score;
- historical win rate;
- Research Lab score;
- bounded ML score;
- shadow meta-intelligence balance;
- benchmark comparison.

## Continuity authority

Wake/lease messages are state pointers, not execution authority.

User pause dominates. A paused system must not resume just because a scheduled
wake fired. Stale/duplicate wakes NOOP.

## Runtime authority

The canonical runtime lives under
`/Volumes/Crypto-504/Crypto-Signal`.

No removed internal Macintosh project/runtime path may become a silent fallback.

## Human-impact recovery boundary

Physical reboot/logout/SSD detach-remount are human-impact operations. R11/R13
did not execute them autonomously. They must not be represented as accepted
evidence unless a future explicit manual acceptance actually performs them.
