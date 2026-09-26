"use strict";

(() => {
  const STORAGE_KEY = "crypto-signal-stream-v1-s13-notifications";
  const MODES = Object.freeze([
    "all",
    "important",
    "decision_capital",
    "silent",
  ]);
  const DEFAULTS = Object.freeze({
    enabled: false,
    volume: 0.55,
    mode: "important",
    desktopEnabled: false,
  });

  let settings = loadSettings();
  let audioContext = null;
  let unlocked = false;
  const delivered = new Set();
  const audit = {
    routed: 0,
    eligible: 0,
    chimeDispatches: 0,
    chimePlayed: 0,
    browserDispatches: 0,
    suppressedDelivery: 0,
    suppressedMode: 0,
    duplicate: 0,
    unlockAttempts: 0,
    permissionRequests: 0,
    previews: 0,
    lastIdentity: "",
    lastDelivery: "",
    lastReason: "",
  };

  function safeParse(raw) {
    try {
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }

  function clampVolume(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return DEFAULTS.volume;
    return Math.min(1, Math.max(0, n));
  }

  function normalizeMode(value) {
    return MODES.includes(value) ? value : DEFAULTS.mode;
  }

  function normalizeSettings(value) {
    const source = value && typeof value === "object" ? value : {};
    return {
      enabled: source.enabled === true,
      volume: clampVolume(source.volume),
      mode: normalizeMode(source.mode),
      desktopEnabled: source.desktopEnabled === true,
    };
  }

  function loadSettings() {
    try {
      return normalizeSettings(safeParse(localStorage.getItem(STORAGE_KEY) || "{}"));
    } catch {
      return { ...DEFAULTS };
    }
  }

  function persistSettings() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
      return true;
    } catch {
      return false;
    }
  }

  function updateSettings(patch) {
    settings = normalizeSettings({ ...settings, ...(patch || {}) });
    persistSettings();
    return snapshot();
  }

  function identityOf(record) {
    const value = record?.narrative_identity;
    return typeof value === "string" ? value : "";
  }

  function categoryOf(record) {
    const direct = record?.category;
    if (typeof direct === "string" && direct) return direct;
    const fixture = record?.__fixture_detail?.message_input?.category;
    return typeof fixture === "string" ? fixture : "";
  }

  function importanceOf(record) {
    const direct = record?.importance;
    if (typeof direct === "string" && direct) return direct;
    const fixture = record?.__fixture_detail?.message_input?.importance;
    return typeof fixture === "string" ? fixture : "";
  }

  function modeAllows(record) {
    if (!settings.enabled || settings.mode === "silent") return false;
    if (settings.mode === "all") return true;
    if (settings.mode === "decision_capital") {
      const category = categoryOf(record);
      return category === "decision" || category === "capital";
    }
    if (settings.mode === "important") {
      const importance = importanceOf(record);
      return importance === "important" || importance === "critical";
    }
    return false;
  }

  function audioCtor() {
    return window.AudioContext || window.webkitAudioContext || null;
  }

  async function unlock({ preview = false } = {}) {
    audit.unlockAttempts += 1;
    const AudioCtor = audioCtor();
    if (!AudioCtor) {
      unlocked = false;
      audit.lastReason = "audio_context_unavailable";
      return false;
    }
    try {
      if (!audioContext) audioContext = new AudioCtor();
      if (audioContext.state === "suspended") await audioContext.resume();
      unlocked = audioContext.state === "running";
      audit.lastReason = unlocked ? "audio_unlocked" : "audio_not_running";
      if (unlocked && preview) {
        audit.previews += 1;
        playChime({ preview: true });
      }
      return unlocked;
    } catch {
      unlocked = false;
      audit.lastReason = "audio_unlock_failed";
      return false;
    }
  }

  function tone(ctx, destination, start, frequency, duration, level) {
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(frequency, start);
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(level, start + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    oscillator.connect(gain);
    gain.connect(destination);
    oscillator.start(start);
    oscillator.stop(start + duration + 0.01);
  }

  function playChime({ preview = false } = {}) {
    audit.chimeDispatches += preview ? 0 : 1;
    if (!unlocked || !audioContext || audioContext.state !== "running") {
      audit.lastReason = "audio_locked";
      return false;
    }
    const now = audioContext.currentTime + 0.008;
    const level = Math.max(0.0001, 0.14 * settings.volume);
    tone(audioContext, audioContext.destination, now, 659.25, 0.12, level);
    tone(audioContext, audioContext.destination, now + 0.105, 880.0, 0.15, level * 0.9);
    tone(audioContext, audioContext.destination, now + 0.22, 1174.66, 0.2, level * 0.75);
    audit.chimePlayed += preview ? 0 : 1;
    audit.lastReason = preview ? "preview_played" : "chime_played";
    return true;
  }

  function notificationTitle(record) {
    const symbol = typeof record?.symbol === "string" && record.symbol
      ? record.symbol
      : "Crypto Signal";
    const category = categoryOf(record);
    return category === "capital"
      ? `Crypto Signal · ${symbol} · Sermaye`
      : `Crypto Signal · ${symbol}`;
  }

  function notificationBody(record) {
    const collapsed = record?.text?.collapsed_text;
    return typeof collapsed === "string" && collapsed
      ? collapsed.slice(0, 220)
      : "Yeni Intelligence Stream mesajı";
  }

  function maybeDesktop(record) {
    if (!settings.desktopEnabled) return false;
    if (!("Notification" in window) || Notification.permission !== "granted") {
      return false;
    }
    try {
      const notification = new Notification(notificationTitle(record), {
        body: notificationBody(record),
        tag: `crypto-signal-${identityOf(record)}`,
        renotify: false,
      });
      notification.onclick = () => {
        window.focus();
        notification.close();
      };
      audit.browserDispatches += 1;
      return true;
    } catch {
      return false;
    }
  }

  async function requestDesktopPermission() {
    audit.permissionRequests += 1;
    if (!("Notification" in window)) {
      audit.lastReason = "notification_api_unavailable";
      return "unsupported";
    }
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted" && settings.desktopEnabled) {
        updateSettings({ desktopEnabled: false });
      }
      audit.lastReason = `notification_permission_${permission}`;
      return permission;
    } catch {
      audit.lastReason = "notification_permission_failed";
      return "error";
    }
  }

  function route(record, delivery = "silent") {
    audit.routed += 1;
    audit.lastDelivery = delivery;
    const identity = identityOf(record);
    audit.lastIdentity = identity;

    if (delivery !== "live_new") {
      audit.suppressedDelivery += 1;
      audit.lastReason = "delivery_silent";
      return Object.freeze({ eligible: false, sounded: false, reason: "delivery_silent" });
    }
    if (!identity) {
      audit.suppressedDelivery += 1;
      audit.lastReason = "identity_missing";
      return Object.freeze({ eligible: false, sounded: false, reason: "identity_missing" });
    }
    if (delivered.has(identity)) {
      audit.duplicate += 1;
      audit.lastReason = "duplicate";
      return Object.freeze({ eligible: false, sounded: false, reason: "duplicate" });
    }
    if (!modeAllows(record)) {
      audit.suppressedMode += 1;
      audit.lastReason = "mode_filtered";
      return Object.freeze({ eligible: false, sounded: false, reason: "mode_filtered" });
    }

    delivered.add(identity);
    audit.eligible += 1;
    const sounded = playChime();
    maybeDesktop(record);
    return Object.freeze({
      eligible: true,
      sounded,
      reason: sounded ? "chime_played" : "audio_locked",
    });
  }

  function resetSessionAudit() {
    delivered.clear();
    for (const key of Object.keys(audit)) {
      if (typeof audit[key] === "number") audit[key] = 0;
      else audit[key] = "";
    }
  }

  function snapshot() {
    return Object.freeze({
      settings: { ...settings },
      unlocked,
      audioState: audioContext?.state || "not_created",
      notificationPermission:
        "Notification" in window ? Notification.permission : "unsupported",
      deliveredCount: delivered.size,
      audit: { ...audit },
      storageKey: STORAGE_KEY,
    });
  }

  window.CryptoSignalNotifications = Object.freeze({
    modes: MODES,
    snapshot,
    updateSettings,
    unlock,
    playPreview: () => playChime({ preview: true }),
    requestDesktopPermission,
    route,
    resetSessionAudit,
  });
})();
