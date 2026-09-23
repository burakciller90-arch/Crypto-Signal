# GALACTECH Product Rail — Accessibility / Performance Polish Slice 8

Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`, Product path.
Predecessor: accepted GALACTECH Learn / System PR #930.
REAL_CAPITAL=0.

## Scope

This slice is deliberately a polish pass, not a new intelligence feature.

It strengthens the accepted GALACTECH surface before production UI cutover while
preserving all scientific and authority boundaries.

## Accessibility

### Navigation

- Every primary navigation control identifies the exact controlled route with
  `aria-controls`.
- Current route remains explicit with `aria-current="page"`.
- Arrow keys move focus through primary navigation without activating a route.
- Home/End move focus to the first/last primary navigation control.
- Route changes are announced through a polite screen-reader status region.
- Reduced-motion users receive immediate scroll positioning instead of smooth motion.

### Runtime state

- Main content starts `aria-busy=true` during cold boot.
- Read-only refreshes expose busy state without claiming LIVE or freshness.
- Visibility-return refresh is announced only when exact runtime evidence is re-read.
- The Evidence Room dialog binds its descriptive subtitle with `aria-describedby`.
- Proof Wall filters expose exact pressed state, not color alone.
- Learn search explicitly controls the result grid.

### Visual accessibility

- Focus-visible coverage includes buttons, links, selects, inputs and details summaries.
- Higher-contrast user preferences increase border/text contrast.
- Forced-colors mode does not depend on decorative translucent effects.
- Reduced-transparency removes backdrop blur.
- Existing reduced-motion behavior remains authoritative.

## Performance

### Refresh discipline

The 30-second read-only refresh loop is overlap-safe:

- a second refresh does not start while one is in flight;
- hidden tabs do not poll;
- returning to a visible tab performs one immediate exact refresh;
- API request timeouts remain bounded;
- no market data is delayed for animation.

### Rendering

- Heavy archive/performance/education cards may use browser
  `content-visibility:auto` with intrinsic-size placeholders.
- Active route layout is contained to reduce unnecessary style/layout invalidation.
- Numeric surfaces use tabular numerals for stable metric layout.

### Static budget

Hosted acceptance enforces coarse no-build budgets:

- HTML < 50 KB;
- JS < 120 KB;
- CSS < 85 KB;
- no external image or HTTP(S) dependency in the GALACTECH HTML shell.

These are regression guards, not claims of measured FPS or network latency.

## Truth boundaries

This polish does not:
- invent latency;
- invent universal freshness;
- invent probability;
- upgrade Product API health into Market Tape runtime health;
- add order/credential authority;
- mutate paper or evidence ledgers.

REAL_CAPITAL=0.

Status: CANDIDATE until exact-head hosted focused + whole-repository acceptance passes.
