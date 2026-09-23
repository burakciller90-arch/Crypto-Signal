# M5 Smart Money / On-chain 2.0 — Slice 2: PIT Wallet Cohort Registry

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Prevent hindsight/selection bias in wallet research by freezing cohort membership before
any forward performance observation is allowed to count.

This slice is a provider-neutral registry and measurement contract. It does **not**
claim that a wallet is smart money, institutional or insider, and it does not activate a
live wallet provider.

## Admission contract

Every cohort member freezes:

- cohort identity;
- provider-specific cluster identity;
- asset/network;
- immutable admission timestamp;
- latest basis-evidence availability timestamp;
- source provider;
- attribution methodology version;
- admission-rule version;
- exact admission-basis evidence identities.

Admission cannot be backdated before its basis evidence was available. A cluster may be
admitted only once inside one exact cohort context.

## Forward-only measurement

A forward observation references one immutable admission identity and must:

- use the same cohort/cluster/asset/network context;
- begin at or after the member's admission timestamp;
- end before its source timestamp;
- be ingested after source availability;
- be available by the requested PIT cutoff.

Historical measurements that began before admission are rejected rather than used to
justify the admission retrospectively.

For an as-of freeze, only the latest eligible forward observation per admitted member is
retained. Future or late-ingested observations cannot rewrite the historical freeze.

## Output semantics

- `REGISTRY_ONLY`: membership exists but no valid forward sample exists yet.
- `MEASURED`: at least one admitted member has a valid post-admission forward sample.
- `UNRESOLVED`: no admission was available at the PIT cutoff.

When measured, the engine exposes only descriptive cohort evidence:

- admitted member count;
- measured member count;
- measurement coverage;
- one exact provider-defined metric semantic;
- mean and median of the latest eligible per-member forward metric.

Different metric semantics are never silently aggregated.

## Scientific boundaries

- Cohort admission is not proof that a wallet is skilled.
- Forward performance is descriptive evidence, not a forecast of future return.
- Cluster attribution is provider evidence, not legal/person identity.
- No "insider" or institution label is inferred.
- No wallet is selected after seeing the measurement being reported.
- No probability, confluence weight, Smart Capital Allocator decision, Kelly sizing or
  trading command is produced.
- No live provider, credential or collector is activated.
- Existing Bitcoin network and exchange-flow engines remain unchanged.

## Acceptance checklist

1. Deterministic admission and forward-observation identities.
2. Admission basis must exist before admission.
3. Registry-only state is valid before a forward sample.
4. Forward measurements cannot start before admission.
5. Latest eligible measurement per member is deterministic under input reordering.
6. Future admissions and future/late observations cannot rewrite a historical freeze.
7. Unknown admissions, context mismatches, duplicate cohort members and mixed metric
   semantics fail closed.
8. Identity tampering fails closed.
9. Focused pytest/Ruff/mypy and full repository Python/JavaScript/freshness regression.
10. Temporary hosted workflow removed after PASS.

The user-requested wake/lease pause remains dominant and must not be re-armed by this work.
