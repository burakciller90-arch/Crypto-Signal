# Crypto Signal — Final F10 Authority Freeze / Closeout Preparation

Status: **PREP ONLY — NOT FINAL ACCEPTANCE**  
Roadmap: `CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ROADMAP.md`  
Phase: **F10 — Authority Freeze / Final Closeout**  
Safety: **REAL_CAPITAL=0**

---

## 1. Purpose

F10 is not another feature phase. It is the final authority freeze that may run only after F0-F9 are mechanically accepted.

This preparation exists so the final closeout is deterministic and does not depend on memory, prose interpretation or a last-minute manual checklist.

This branch deliberately does **not** edit:

- `READ_FIRST_CRYPTO_SIGNAL.md`;
- `CURRENT_STATUS.md`;
- `PROJECT_CHRONICLE.md`;
- `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`;
- the final roadmap status;
- production runtime wiring;
- Development/Product checkouts;
- any runtime database.

It also does not claim:

`INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ACCEPTED`.

---

## 2. Concurrency boundary

Prepared branch:

`stream/final-f10-closeout-prep`

The branch was created from the currently accepted F4 main frontier while later phases were being prepared independently.

F10 must not be merged or converted into final authority until the accepted main branch contains final evidence for F0-F9.

Before final F10 execution:

1. F5 must be merged/accepted on main;
2. F6 must be merged/accepted on main;
3. F7 must be merged/accepted on main;
4. F8 must contain genuine forward production E2E acceptance;
5. F9 must contain real desktop + mobile Product acceptance;
6. this F10 branch must be rebased/recreated on that exact accepted main;
7. the readiness audit must report `READY_FOR_AUTHORITY_MUTATION=YES`.

No F10 closeout commit should be used to resolve an unfinished F5-F9 defect.

---

## 3. Prepared mechanical gate

Added:

`ops/audit_stream_f10_final_closeout.py`

The audit is repository-read-only.

It discovers F0-F9 evidence using the canonical phase prefix:

`docs/CRYPTO_SIGNAL_STREAM_FINAL_F{N}_*.md`

A phase counts as accepted only when:

- its final evidence document contains a `Status:` line with `PASS` or `ACCEPTED`;
- the status is not PREP/PENDING/OPEN/BLOCKED/NOT ACCEPTED/DO NOT MERGE;
- `REAL_CAPITAL=0` is present.

F0 is special because its canonical product is the mechanical source-message inventory rather than a normal PASS document. It is accepted only from:

`docs/CRYPTO_SIGNAL_STREAM_FINAL_F0_SOURCE_MESSAGE_CLOSURE_LEDGER.md`

with the canonical inventory marker and `REAL_CAPITAL=0`.

---

## 4. Premature-authority protection

If F0-F9 are not all accepted, the audit fails closed if the final authority marker appears in any mutable authority record:

- `READ_FIRST_CRYPTO_SIGNAL.md`;
- `CURRENT_STATUS.md`;
- `PROJECT_CHRONICLE.md`;
- original Master Roadmap;
- final source-to-message ledger;
- final acceptance record.

Protected marker:

`INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ACCEPTED`

The final roadmap itself is not treated as a premature claim because it already contains that token as the roadmap-defined future status language.

---

## 5. Two audit modes

### Prep mode

Command:

```bash
python ops/audit_stream_f10_final_closeout.py \
  --repo-root . \
  --mode prep \
  --output /tmp/f10-readiness.json
```

Prep mode is allowed to report unfinished future phases without failing merely because F5-F9 are still in progress.

It does fail on:

- premature final authority;
- broken safety evidence;
- malformed accepted-phase evidence when strict readiness is requested.

Final readiness command:

```bash
python ops/audit_stream_f10_final_closeout.py \
  --repo-root . \
  --mode prep \
  --require-ready
```

This must pass before any authority file is changed.

### Closeout mode

After the actual final authority/doc changes are committed:

```bash
python ops/audit_stream_f10_final_closeout.py \
  --repo-root . \
  --mode closeout \
  --require-complete
```

Only this mode can produce:

`F10_CLOSEOUT_COMPLETE=YES`.

---

## 6. Required final F10 outputs

When F0-F9 are all accepted, F10 must add/update the following in one bounded authority-freeze change set.

### Existing authority files

Update:

1. `READ_FIRST_CRYPTO_SIGNAL.md`;
2. `CURRENT_STATUS.md`;
3. `PROJECT_CHRONICLE.md`;
4. `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`.

The historical S0-S16 acceptance must remain preserved as historical evidence.

### Final source-to-message ledger

Create:

`docs/CRYPTO_SIGNAL_STREAM_V1_FINAL_SOURCE_TO_MESSAGE_LEDGER.md`

It must describe the final production truth for every claimed-live or explicitly deferred source family, including at least:

- Market / Geometry;
- Liquidity;
- Order Flow;
- Derivatives;
- On-chain / unsupported provider-gated sources;
- Event Risk;
- Provider / Data Quality / System;
- Decision issuance;
- Outcome / resolution;
- Core/Tactical/Opportunity canonical Capital truth;
- exact evidence state;
- optional bounded local LLM state;
- real Product/browser acceptance reference.

It must separate:

- live and mechanically proven;
- supported but currently unavailable;
- research/deferred;
- exact proof available;
- identity-only exact;
- explicitly unavailable.

No source may become “live” merely because code exists.

### Final acceptance record

Create:

`docs/CRYPTO_SIGNAL_STREAM_V1_FINAL_ACCEPTANCE.md`

It must contain the final roadmap Definition of Done and the exact final status:

`INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ACCEPTED`

Only after all 28 final Definition-of-Done statements are supported at the same time.

---

## 7. Final authority language

The accepted final meaning is intentionally narrow.

It means:

- all currently claimed live source families have real production message projection;
- unsupported source families remain explicit rather than implied;
- production silence is diagnosable;
- three-vault canonical paper truth is narratable from exact lineage;
- exact proof is available or explicitly unavailable;
- optional Ollama/local rewrite is bounded and cannot create truth;
- LLM failure cannot stop publication;
- genuine production events have passed E2E browser acceptance;
- desktop and mobile real Product states have passed;
- no historical rich backfill was used;
- no policy was weakened to manufacture activity;
- no real-money authority was added;
- `REAL_CAPITAL=0`.

It does **not** authorize new pages, real-money trading, leverage, credentials, fabricated history or LLM decision authority.

---

## 8. Prepared UID504 gate

Added:

`.github/workflows/crypto-stream-final-f10-closeout-prep-uid504.yml`

Push behavior:

- exact branch source is checked;
- focused F10 tests run;
- ruff/compile checks run;
- repository authority audit runs in prep mode;
- Development and Product are proven clean and byte-positionally untouched at the Git HEAD level;
- evidence artifact is uploaded;
- `REAL_CAPITAL=0` remains binding.

Manual controls:

- `require_ready=true` requires F0-F9 final acceptance before authority mutation;
- `require_complete=true` runs the final closeout mode and requires the final authority/doc freeze to be complete.

---

## 9. Tests

Added:

`tests/test_stream_f10_final_closeout_audit.py`

Coverage includes:

- F0-F4 accepted + later phases still prep does not falsely claim completion;
- PREP documents do not count as accepted;
- accepted-looking evidence without `REAL_CAPITAL=0` does not count;
- premature final authority fails closed;
- F0-F9 acceptance enables authority mutation but does not itself mean F10 is closed;
- final source ledger + final acceptance + synchronized authority files are required for closeout complete.

---

## 10. Final execution sequence

When F9 is physically accepted:

1. fetch exact current main;
2. verify F5-F9 canonical acceptance evidence is on main;
3. rebase/recreate this F10 preparation on exact main;
4. run F10 prep audit with `--require-ready`;
5. if it fails, stop and fix the upstream phase rather than overriding the gate;
6. build the final source-to-message ledger from accepted production evidence;
7. build the final acceptance record covering all 28 DoD statements;
8. update the four authority files in one bounded closeout change;
9. run closeout audit with `--require-complete`;
10. run the UID504 final closeout workflow;
11. only then merge F10 and use the final accepted status.

No historical backfill.  
No synthetic activity.  
No scientific-policy loosening.  
No authority escalation.  
**REAL_CAPITAL=0.**
