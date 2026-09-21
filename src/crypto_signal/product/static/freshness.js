(function attachFreshness(globalScope) {
  "use strict";

  function classifyRefreshFreshness({
    online,
    lastSuccessfulRefreshAt,
    nowMs,
    staleAfterMs,
  }) {
    if (!online) return "offline";
    if (lastSuccessfulRefreshAt === null || lastSuccessfulRefreshAt === undefined) {
      return "pending";
    }
    const now = Number(nowMs);
    const last = Number(lastSuccessfulRefreshAt);
    const staleAfter = Number(staleAfterMs);
    if (!Number.isFinite(now) || !Number.isFinite(last)) {
      throw new TypeError("freshness timestamps must be finite");
    }
    if (!Number.isFinite(staleAfter) || staleAfter <= 0) {
      throw new TypeError("staleAfterMs must be finite and positive");
    }
    const ageMs = Math.max(0, now - last);
    return ageMs > staleAfter ? "stale" : "live";
  }

  globalScope.CryptoSignalFreshness = Object.freeze({
    classifyRefreshFreshness,
  });
})(globalThis);
