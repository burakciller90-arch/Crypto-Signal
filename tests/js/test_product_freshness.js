"use strict";

require("../../src/crypto_signal/product/static/freshness.js");

const { classifyRefreshFreshness } = globalThis.CryptoSignalFreshness;

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${expected}, got ${actual}`);
  }
}

assertEqual(
  classifyRefreshFreshness({
    online: true,
    lastSuccessfulRefreshAt: null,
    nowMs: 100000,
    staleAfterMs: 45000,
  }),
  "pending",
  "initial state"
);

assertEqual(
  classifyRefreshFreshness({
    online: true,
    lastSuccessfulRefreshAt: 60000,
    nowMs: 100000,
    staleAfterMs: 45000,
  }),
  "live",
  "fresh state"
);

assertEqual(
  classifyRefreshFreshness({
    online: true,
    lastSuccessfulRefreshAt: 50000,
    nowMs: 100000,
    staleAfterMs: 45000,
  }),
  "stale",
  "stale state"
);

assertEqual(
  classifyRefreshFreshness({
    online: false,
    lastSuccessfulRefreshAt: 99999,
    nowMs: 100000,
    staleAfterMs: 45000,
  }),
  "offline",
  "offline wins"
);

assertEqual(
  classifyRefreshFreshness({
    online: true,
    lastSuccessfulRefreshAt: 110000,
    nowMs: 100000,
    staleAfterMs: 45000,
  }),
  "live",
  "clock skew clamps to zero age"
);

let threw = false;
try {
  classifyRefreshFreshness({
    online: true,
    lastSuccessfulRefreshAt: 1,
    nowMs: 2,
    staleAfterMs: 0,
  });
} catch (error) {
  threw = error instanceof TypeError;
}
if (!threw) throw new Error("invalid stale threshold must fail closed");

console.log("PRODUCT_FRESHNESS_CONTRACT_PASS=YES");
