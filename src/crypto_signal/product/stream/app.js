"use strict";

const API = Object.freeze({
  messages: "/api/stream/messages",
  live: "/api/stream/live",
  detail: (identity) => `/api/stream/messages/${encodeURIComponent(identity)}/detail`,
  decisionProofForForecast: (identity) =>
    `/api/decision-proof/forecast/${encodeURIComponent(identity)}`,
  education: (concept) => `/api/education/${encodeURIComponent(concept)}`,
  detachedEvidence: (identity, kind) =>
    `/stream-evidence?narrative=${encodeURIComponent(identity)}&kind=${encodeURIComponent(kind)}`,
});

const ui = {
  viewport: document.getElementById("streamViewport"),
  list: document.getElementById("messageList"),
  empty: document.getElementById("emptyState"),
  emptyTitle: document.getElementById("emptyTitle"),
  emptyCopy: document.getElementById("emptyCopy"),
  loadOlder: document.getElementById("loadOlderButton"),
  newButton: document.getElementById("newMessageButton"),
  newCount: document.getElementById("newMessageCount"),
  connectionDot: document.getElementById("connectionDot"),
  connectionLabel: document.getElementById("connectionLabel"),
  connectionNote: document.getElementById("connectionNote"),
  transportMode: document.getElementById("transportMode"),
  fixtureBanner: document.getElementById("fixtureBanner"),
  discoveryDrawer: document.getElementById("discoveryDrawer"),
  settingsDrawer: document.getElementById("settingsDrawer"),
  backdrop: document.getElementById("drawerBackdrop"),
  searchButton: document.getElementById("searchButton"),
  filterButton: document.getElementById("filterButton"),
  soundButton: document.getElementById("soundButton"),
  settingsButton: document.getElementById("settingsButton"),
  searchInput: document.getElementById("searchInput"),
  symbolFilter: document.getElementById("symbolFilter"),
  timeframeFilter: document.getElementById("timeframeFilter"),
  clearFilters: document.getElementById("clearFiltersButton"),
  applyFilters: document.getElementById("applyFiltersButton"),
  floatingLayer: document.getElementById("floatingWindowLayer"),
  announcer: document.getElementById("liveAnnouncer"),
};

const state = {
  messages: [],
  ids: new Set(),
  beforeCursor: null,
  newestCursor: null,
  hasOlder: false,
  unread: 0,
  eventSource: null,
  pollingTimer: null,
  loadingHistory: false,
  expanded: new Set(),
  details: new Map(),
  detailRequests: new Set(),
  evidenceWindows: new Map(),
  evidenceWindowZ: 1,
  fixture: new URLSearchParams(window.location.search).get("fixture") || "",
  filters: {
    text: "",
    symbol: "",
    timeframe: "",
  },
};

const EVIDENCE_WINDOW_SESSION_KEY = "crypto-signal-stream-v1-s9-windows";
const EVIDENCE_WINDOW_KINDS = Object.freeze({
  liquidity: { label: "Likidite", family: "liquidity", concept: "liquidity_sweep" },
  order_flow: { label: "Emir Akışı", family: "order_flow", concept: "cvd" },
  derivatives: { label: "Türevler", family: "derivatives", concept: "liquidation_heatmap" },
  onchain: { label: "On-chain", family: "onchain", concept: null },
  geometry: { label: "Geometri", family: "geometry", concept: "invalidation" },
  decision: { label: "Karar", family: null, concept: "agreement_vs_probability" },
  capital: { label: "Sermaye", family: null, concept: "paper_trading" },
  event_risk: { label: "Event Risk", family: null, concept: "abstain" },
  proof: { label: "Proof", family: null, concept: "calibration" },
});

function text(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function formatTime(ms) {
  const n = Number(ms);
  if (!Number.isFinite(n)) return "ZAMAN YOK";
  try {
    return new Intl.DateTimeFormat("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "2-digit",
    }).format(new Date(n));
  } catch {
    return "ZAMAN YOK";
  }
}

function shortSource(value) {
  const raw = text(value, "deterministic");
  if (raw === "local_rewrite") return "YEREL ANLATIM";
  if (raw === "deterministic") return "DETERMİNİSTİK";
  return raw.replaceAll("_", " ").toUpperCase();
}

function isNearBottom() {
  if (!ui.viewport) return true;
  return ui.viewport.scrollHeight - ui.viewport.scrollTop - ui.viewport.clientHeight < 120;
}

function setConnection(kind, label, note) {
  if (!ui.connectionDot || !ui.connectionLabel || !ui.connectionNote) return;
  ui.connectionDot.className = "connection-dot";
  ui.connectionDot.classList.add(
    kind === "live"
      ? "is-live"
      : kind === "degraded"
        ? "is-degraded"
        : "is-connecting"
  );
  ui.connectionLabel.textContent = label;
  ui.connectionNote.textContent = note;
}

function queryParams({ after = null, before = null, limit = 50 } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (after) params.set("after", after);
  if (before) params.set("before", before);
  if (state.filters.text) params.set("text", state.filters.text);
  if (state.filters.symbol) params.set("symbol", state.filters.symbol);
  if (state.filters.timeframe) params.set("timeframe", state.filters.timeframe);
  return params;
}

async function fetchJson(url, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`${url} -> HTTP ${response.status}`);
    return await response.json();
  } finally {
    window.clearTimeout(timer);
  }
}

function buildChip(label, safe = false) {
  const chip = document.createElement("span");
  chip.className = "message-chip";
  if (safe) chip.classList.add("is-safe");
  chip.textContent = label;
  return chip;
}

function messageText(record) {
  const bundle = record && typeof record === "object" ? record.text : null;
  if (bundle && typeof bundle === "object" && typeof bundle.collapsed_text === "string") {
    return bundle.collapsed_text;
  }
  return "Bu mesajın kısa anlatımı mevcut değil.";
}

function messageState(record) {
  if (typeof record.__fixture_state === "string") return record.__fixture_state;
  return "ANALİZ";
}

function displayNumber(value, fallback = "—") {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 }).format(n);
}

function familyLabel(value) {
  const labels = {
    geometry: "Geometri",
    liquidity: "Likidite",
    order_flow: "Emir akışı",
    derivatives: "Türevler",
    onchain: "On-chain",
  };
  const key = text(value, "").toLowerCase();
  return labels[key] || text(value, "Kanıt");
}

function preserveMessageAnchor(item, mutate) {
  if (!ui.viewport) {
    mutate();
    return;
  }
  const beforeTop = item.getBoundingClientRect().top;
  mutate();
  window.requestAnimationFrame(() => {
    if (!ui.viewport || !item.isConnected) return;
    const afterTop = item.getBoundingClientRect().top;
    ui.viewport.scrollTop += afterTop - beforeTop;
  });
}

function depthSection(label, body, { className = "", content = null } = {}) {
  const section = document.createElement("section");
  section.className = `depth-section ${className}`.trim();

  const heading = document.createElement("div");
  heading.className = "depth-heading";
  const eyebrow = document.createElement("span");
  eyebrow.textContent = label;
  heading.append(eyebrow);
  section.append(heading);

  if (content) {
    section.append(content);
  } else {
    const paragraph = document.createElement("p");
    paragraph.textContent = text(body, "Bu bölüm için ek anlatım yok.");
    section.append(paragraph);
  }
  return section;
}

function evidenceFamilyGrid(fact) {
  const grid = document.createElement("div");
  grid.className = "family-grid";
  const families = Array.isArray(fact?.family_contributions)
    ? fact.family_contributions
    : [];
  for (const family of families) {
    const card = document.createElement("div");
    card.className = "family-card";
    const label = document.createElement("span");
    label.textContent = familyLabel(family?.family);
    const score = document.createElement("strong");
    score.textContent = `+${displayNumber(family?.support_points, "0")} / -${displayNumber(
      family?.opposition_points,
      "0"
    )}`;
    const note = document.createElement("small");
    const quality = Number(family?.evidence_quality_0_1);
    note.textContent = Number.isFinite(quality)
      ? `kanıt kalitesi %${Math.round(quality * 100)}`
      : text(family?.state, "ölçülmedi");
    card.append(label, score, note);
    grid.append(card);
  }
  if (!families.length) {
    const note = document.createElement("p");
    note.className = "depth-muted";
    note.textContent = "Beş-aile katkısı bu kayıtta mevcut değil.";
    grid.append(note);
  }
  return grid;
}

function geometryGrid(fact) {
  const grid = document.createElement("div");
  grid.className = "geometry-grid";
  const rows = [
    ["Tetik bölgesi", fact?.trigger_zone?.low, fact?.trigger_zone?.high],
    ["Hedef bölgesi", fact?.target_zone?.low, fact?.target_zone?.high],
    ["Geçersizleşme", fact?.invalidation_price, null],
  ];
  for (const [labelText, low, high] of rows) {
    const cell = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent =
      high === null
        ? displayNumber(low)
        : `${displayNumber(low)} – ${displayNumber(high)}`;
    cell.append(label, value);
    grid.append(cell);
  }
  return grid;
}

function proofPanel(fact) {
  const wrap = document.createElement("div");
  wrap.className = "proof-panel";
  const proofIdentity = text(fact?.proof_identity, "");
  const forecastIdentity = text(fact?.forecast_identity, "");

  const identity = document.createElement("code");
  identity.textContent = proofIdentity
    ? `${proofIdentity.slice(0, 12)}…${proofIdentity.slice(-8)}`
    : "kanıt kimliği yok";

  const action = document.createElement("button");
  action.type = "button";
  action.className = "proof-action";
  action.textContent = "Değiştirilemez kanıtı doğrula";
  action.disabled = !forecastIdentity;

  const result = document.createElement("span");
  result.className = "proof-result";
  result.textContent = "S10 görsel proof değil; exact persisted karar kanıtı kontrolü.";

  action.addEventListener("click", async () => {
    if (!forecastIdentity) return;
    action.disabled = true;
    result.textContent = "Kanıt okunuyor…";
    try {
      const payload = await fetchJson(API.decisionProofForForecast(forecastIdentity));
      if (payload.status === "ready") {
        result.textContent = "Persisted karar kanıtı doğrulandı.";
        result.dataset.state = "ready";
      } else if (payload.status === "empty") {
        result.textContent = "Bu forecast için persisted karar kanıtı bulunamadı.";
        result.dataset.state = "muted";
      } else {
        result.textContent = "Decision Evidence runtime şu anda bağlı değil.";
        result.dataset.state = "muted";
      }
    } catch {
      result.textContent = "Kanıt doğrulama isteği başarısız; veri uydurulmadı.";
      result.dataset.state = "risk";
    } finally {
      action.disabled = false;
    }
  });

  wrap.append(identity, action, result);
  return wrap;
}

function exactSha256(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function familyContribution(detail, family) {
  const fact = detail && typeof detail.fact_bundle === "object" ? detail.fact_bundle : {};
  const families = Array.isArray(fact?.family_contributions) ? fact.family_contributions : [];
  return families.find((item) => item && item.family === family) || null;
}

function evidenceWindowSpecificWhy(kind, detail) {
  const config = EVIDENCE_WINDOW_KINDS[kind];
  const fact = detail?.fact_bundle || {};
  const analytical = detail?.analytical_view || {};
  if (config?.family && kind !== "geometry") {
    const contribution = familyContribution(detail, config.family);
    if (!contribution) return "Bu exact mesajda bu aile için persisted katkı yok.";
    return `Bu mesajda destek +${displayNumber(contribution.support_points, "0")}, karşıt -${displayNumber(
      contribution.opposition_points,
      "0"
    )}. Pencere yalnız bu mesajın dondurulmuş katkısını gösterir.`;
  }
  if (kind === "geometry") {
    return `Tetik ${displayNumber(fact?.trigger_zone?.low)}–${displayNumber(
      fact?.trigger_zone?.high
    )}, hedef ${displayNumber(fact?.target_zone?.low)}–${displayNumber(
      fact?.target_zone?.high
    )}, geçersizleşme ${displayNumber(fact?.invalidation_price)}.`;
  }
  if (kind === "decision") {
    return `Stance ${text(analytical?.stance?.effective_stance)}, sonraki koşul ${text(
      analytical?.next_condition?.state
    )}. Bu pencere aynı immutable karar lineage'ına bağlıdır.`;
  }
  if (kind === "capital") {
    return `Capital consequence ${text(
      analytical?.capital_consequence?.state,
      "not_bound"
    )}. REAL_CAPITAL=0; burada gerçek para emri yoktur.`;
  }
  if (kind === "event_risk") {
    return `Event context ${text(fact?.event_context_state)}. Bu mevcut persisted karar bağlamıdır; yeni haber yorumu üretilmez.`;
  }
  if (kind === "proof") {
    return `Forecast ${text(fact?.forecast_identity, "").slice(0, 12)}… ve proof ${text(
      fact?.proof_identity,
      ""
    ).slice(0, 12)}… aynı exact mesaj lineage'ında doğrulanır.`;
  }
  return "Pencere yalnız exact persisted message detail üzerinden okunur.";
}

function evidenceMetric(label, value) {
  const cell = document.createElement("div");
  cell.className = "window-metric";
  const l = document.createElement("span");
  l.textContent = label;
  const v = document.createElement("strong");
  v.textContent = text(value);
  cell.append(l, v);
  return cell;
}

function evidenceWindowSection(label, body = "") {
  const section = document.createElement("section");
  section.className = "window-section";
  const heading = document.createElement("h4");
  heading.textContent = label;
  const paragraph = document.createElement("p");
  paragraph.textContent = text(body);
  section.append(heading, paragraph);
  return section;
}

function buildEvidenceWindowData(kind, detail) {
  const config = EVIDENCE_WINDOW_KINDS[kind];
  const narrative = detail?.narrative || {};
  const fact = detail?.fact_bundle || {};
  const analytical = detail?.analytical_view || {};
  const fragment = document.createDocumentFragment();

  const context = document.createElement("div");
  context.className = "window-context-grid";
  context.append(
    evidenceMetric("Varlık", narrative.symbol),
    evidenceMetric("TF", narrative.timeframe),
    evidenceMetric("Kaynak", narrative.source_kind)
  );
  fragment.append(context);

  if (kind === "geometry") {
    const geometry = document.createElement("div");
    geometry.className = "window-context-grid";
    geometry.append(
      evidenceMetric(
        "Tetik",
        `${displayNumber(fact?.trigger_zone?.low)}–${displayNumber(fact?.trigger_zone?.high)}`
      ),
      evidenceMetric(
        "Hedef",
        `${displayNumber(fact?.target_zone?.low)}–${displayNumber(fact?.target_zone?.high)}`
      ),
      evidenceMetric("Geçersiz", displayNumber(fact?.invalidation_price))
    );
    fragment.append(evidenceWindowSection("Exact trade geometry"));
    fragment.append(geometry);
    const family = familyContribution(detail, "geometry");
    if (family) {
      fragment.append(
        evidenceWindowSection(
          "Geometry contribution",
          `Destek +${displayNumber(family.support_points, "0")} / karşıt -${displayNumber(
            family.opposition_points,
            "0"
          )} · ${text(family.state)}`
        )
      );
    }
  } else if (config?.family) {
    const family = familyContribution(detail, config.family);
    if (family) {
      const quality = Number(family.evidence_quality_0_1);
      const freshness = Number(family.freshness_0_1);
      const grid = document.createElement("div");
      grid.className = "window-context-grid";
      grid.append(
        evidenceMetric("Destek", `+${displayNumber(family.support_points, "0")}`),
        evidenceMetric("Karşıt", `-${displayNumber(family.opposition_points, "0")}`),
        evidenceMetric(
          "Kalite",
          Number.isFinite(quality) ? `%${Math.round(quality * 100)}` : text(family.state)
        ),
        evidenceMetric(
          "Fresh",
          Number.isFinite(freshness) ? `%${Math.round(freshness * 100)}` : "—"
        )
      );
      fragment.append(grid);

      const refs = Array.isArray(family.source_evidence_identities)
        ? family.source_evidence_identities
        : [];
      const refsSection = evidenceWindowSection(
        "Exact source evidence identities",
        refs.length ? `${refs.length} persisted source identity bağlı.` : "Persisted source identity listesi yok."
      );
      for (const ref of refs) {
        const code = document.createElement("code");
        code.className = "window-identity";
        code.textContent = ref;
        refsSection.append(code);
      }
      fragment.append(refsSection);
    } else {
      fragment.append(
        evidenceWindowSection(
          "Persisted evidence",
          "Bu exact mesajda bu kanıt ailesi için katkı kaydı yok; veri uydurulmadı."
        )
      );
    }
  } else if (kind === "decision") {
    fragment.append(
      evidenceWindowSection(
        "Decision state",
        `Stance ${text(analytical?.stance?.effective_stance)} · strength ${text(
          analytical?.stance?.strength
        )} · support ${displayNumber(analytical?.stance?.support_score_0_100)} · opposition ${displayNumber(
          analytical?.stance?.opposition_score_0_100
        )}`
      ),
      evidenceWindowSection(
        "Next / invalidation",
        `${text(analytical?.next_condition?.state)} · ${displayNumber(
          analytical?.invalidation_condition?.price ?? fact?.invalidation_price
        )}`
      )
    );
  } else if (kind === "capital") {
    const capital = analytical?.capital_consequence || {};
    fragment.append(
      evidenceWindowSection(
        "Capital consequence",
        `${text(capital.state, "not_bound")} · current refs ${Array.isArray(
          capital.current_reference_identities
        ) ? capital.current_reference_identities.length : 0} · REAL_CAPITAL=0`
      )
    );
  } else if (kind === "event_risk") {
    fragment.append(
      evidenceWindowSection(
        "Event Risk",
        `Event context ${text(fact?.event_context_state)} · uncertainty ${(
          Array.isArray(fact?.uncertainty_flags) ? fact.uncertainty_flags : []
        ).join(", ") || "yok"}`
      )
    );
  } else if (kind === "proof") {
    const proof = evidenceWindowSection(
      "Exact proof lineage",
      "S9 exact identity penceresini sağlar. Frozen visual coordinates ve çizimler S10 kapsamıdır."
    );
    for (const [label, value] of [
      ["forecast", fact?.forecast_identity],
      ["proof", fact?.proof_identity],
    ]) {
      const code = document.createElement("code");
      code.className = "window-identity";
      code.textContent = `${label}: ${text(value)}`;
      proof.append(code);
    }
    const verify = document.createElement("button");
    verify.type = "button";
    verify.className = "window-primary-action";
    verify.textContent = "Persisted Decision Proof’u doğrula";
    const result = document.createElement("span");
    result.className = "window-action-result";
    verify.addEventListener("click", async () => {
      const forecastIdentity = text(fact?.forecast_identity, "");
      if (!exactSha256(forecastIdentity)) return;
      verify.disabled = true;
      result.textContent = "Doğrulanıyor…";
      try {
        const payload = await fetchJson(API.decisionProofForForecast(forecastIdentity));
        result.textContent =
          payload.status === "ready"
            ? "Persisted Decision Proof doğrulandı."
            : "Persisted Decision Proof bu runtime’da mevcut değil.";
      } catch {
        result.textContent = "Proof isteği başarısız; veri uydurulmadı.";
      } finally {
        verify.disabled = false;
      }
    });
    proof.append(verify, result);
    fragment.append(proof);
  }

  fragment.append(
    evidenceWindowSection(
      "Bu mesajda neden önemli?",
      evidenceWindowSpecificWhy(kind, detail)
    )
  );

  if (config?.concept) {
    const education = evidenceWindowSection(
      "Bu nedir?",
      "Deterministik eğitim açıklaması yalnız istek üzerine yüklenir."
    );
    const button = document.createElement("button");
    button.type = "button";
    button.className = "window-secondary-action";
    button.textContent = "Açıklamayı getir";
    const target = education.querySelector("p");
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const payload = await fetchJson(API.education(config.concept));
        if (target) {
          target.textContent = `${text(payload?.lesson?.beginner_tr)} ${text(
            payload?.lesson?.why_it_matters_tr,
            ""
          )}`.trim();
        }
      } catch {
        if (target) target.textContent = "Eğitim içeriği şu anda okunamadı.";
      } finally {
        button.disabled = false;
      }
    });
    education.append(button);
    fragment.append(education);
  }

  return fragment;
}

function evidenceWindowId(narrativeIdentity, kind) {
  return `${narrativeIdentity}:${kind}`;
}

function defaultEvidenceWindowGeometry(index) {
  const layer = ui.floatingLayer?.getBoundingClientRect();
  const layerWidth = layer?.width || window.innerWidth;
  const width = Math.min(470, Math.max(340, layerWidth - 32));
  return {
    x: Math.max(12, layerWidth - width - 26 - (index % 3) * 28),
    y: 18 + (index % 5) * 34,
    width,
    height: 520,
  };
}

function evidenceWindowSnapshot() {
  return [...state.evidenceWindows.values()].map((model) => ({
    id: model.id,
    narrativeIdentity: model.narrativeIdentity,
    kind: model.kind,
    x: Math.round(model.x),
    y: Math.round(model.y),
    width: Math.round(model.width),
    height: Math.round(model.height),
    minimized: Boolean(model.minimized),
    pinned: Boolean(model.pinned),
    z: Number(model.z) || 1,
  }));
}

function persistEvidenceWindows() {
  try {
    localStorage.setItem(
      EVIDENCE_WINDOW_SESSION_KEY,
      JSON.stringify(evidenceWindowSnapshot())
    );
  } catch {
    // Session persistence is best-effort; evidence truth remains server-side.
  }
}

function applyEvidenceWindowGeometry(model) {
  const node = model.element;
  if (!(node instanceof HTMLElement)) return;
  const layer = ui.floatingLayer?.getBoundingClientRect();
  if (layer) {
    const effectiveHeight = model.minimized ? 56 : model.height;
    model.width = Math.min(Math.max(320, model.width), Math.max(320, layer.width - 16));
    model.height = Math.min(Math.max(260, model.height), Math.max(260, layer.height - 16));
    model.x = Math.min(Math.max(8, model.x), Math.max(8, layer.width - model.width - 8));
    model.y = Math.min(Math.max(8, model.y), Math.max(8, layer.height - effectiveHeight - 8));
  }
  node.style.left = `${Math.round(model.x)}px`;
  node.style.top = `${Math.round(model.y)}px`;
  node.style.width = `${Math.round(model.width)}px`;
  node.style.height = `${Math.round(model.height)}px`;
  node.style.zIndex = String((model.pinned ? 5000 : 2000) + model.z);
  node.classList.toggle("is-minimized", Boolean(model.minimized));
  node.classList.toggle("is-pinned", Boolean(model.pinned));
  const pin = node.querySelector('[data-window-action="pin"]');
  if (pin instanceof HTMLButtonElement) {
    pin.setAttribute("aria-pressed", String(Boolean(model.pinned)));
    pin.title = model.pinned ? "Sabitlemeyi kaldır" : "Pencereyi sabitle";
  }
  const minimize = node.querySelector('[data-window-action="minimize"]');
  if (minimize instanceof HTMLButtonElement) {
    minimize.textContent = model.minimized ? "□" : "—";
    minimize.title = model.minimized ? "Geri aç" : "Küçült";
  }
}

function focusEvidenceWindow(id) {
  const model = state.evidenceWindows.get(id);
  if (!model) return;
  state.evidenceWindowZ += 1;
  model.z = state.evidenceWindowZ;
  applyEvidenceWindowGeometry(model);
  persistEvidenceWindows();
}

function closeEvidenceWindow(id, { persist = true } = {}) {
  const model = state.evidenceWindows.get(id);
  if (!model) return;
  model.element?.remove();
  state.evidenceWindows.delete(id);
  if (persist) persistEvidenceWindows();
}

function closeAllEvidenceWindows({ persist = true } = {}) {
  for (const id of [...state.evidenceWindows.keys()]) {
    closeEvidenceWindow(id, { persist: false });
  }
  if (persist) persistEvidenceWindows();
}

function startEvidenceWindowDrag(event, model) {
  if (!(event instanceof PointerEvent) || event.button !== 0) return;
  if (event.target instanceof Element && event.target.closest("button")) return;
  focusEvidenceWindow(model.id);
  const startX = event.clientX;
  const startY = event.clientY;
  const originX = model.x;
  const originY = model.y;

  const move = (moveEvent) => {
    model.x = originX + (moveEvent.clientX - startX);
    model.y = originY + (moveEvent.clientY - startY);
    applyEvidenceWindowGeometry(model);
  };
  const end = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
    persistEvidenceWindows();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end, { once: true });
  window.addEventListener("pointercancel", end, { once: true });
  event.preventDefault();
}

function startEvidenceWindowResize(event, model) {
  if (!(event instanceof PointerEvent) || event.button !== 0 || model.minimized) return;
  focusEvidenceWindow(model.id);
  const startX = event.clientX;
  const startY = event.clientY;
  const originWidth = model.width;
  const originHeight = model.height;

  const move = (moveEvent) => {
    model.width = originWidth + (moveEvent.clientX - startX);
    model.height = originHeight + (moveEvent.clientY - startY);
    applyEvidenceWindowGeometry(model);
  };
  const end = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
    persistEvidenceWindows();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end, { once: true });
  window.addEventListener("pointercancel", end, { once: true });
  event.preventDefault();
}

function renderEvidenceWindowBody(model, detail) {
  const body = model.element?.querySelector(".evidence-window-body");
  if (!(body instanceof HTMLElement)) return;
  body.replaceChildren(buildEvidenceWindowData(model.kind, detail));
  model.detail = detail;
  const narrative = detail?.narrative || {};
  const subtitle = model.element?.querySelector(".evidence-window-subtitle");
  if (subtitle) {
    subtitle.textContent = `${text(narrative.symbol, "PİYASA")} · ${text(
      narrative.timeframe
    )} · ${model.narrativeIdentity.slice(0, 8)}…`;
  }
}

async function hydrateEvidenceWindow(model, detail = null) {
  if (detail && typeof detail === "object") {
    renderEvidenceWindowBody(model, detail);
    return;
  }
  try {
    const payload = await fetchJson(API.detail(model.narrativeIdentity));
    if (payload.status === "ready" && payload.detail) {
      renderEvidenceWindowBody(model, payload.detail);
      return;
    }
    throw new Error("detail unavailable");
  } catch {
    const body = model.element?.querySelector(".evidence-window-body");
    if (body instanceof HTMLElement) {
      body.replaceChildren(
        detailPlaceholder("Exact persisted evidence detail okunamadı; veri uydurulmadı.")
      );
    }
  }
}

function createEvidenceWindowShell(model) {
  if (!ui.floatingLayer) return null;
  const config = EVIDENCE_WINDOW_KINDS[model.kind];
  if (!config) return null;

  const node = document.createElement("article");
  node.className = "evidence-window";
  node.dataset.windowId = model.id;
  node.dataset.kind = model.kind;
  node.dataset.narrativeIdentity = model.narrativeIdentity;
  node.setAttribute("role", "dialog");
  node.setAttribute("aria-label", `${config.label} kanıt penceresi`);

  const bar = document.createElement("header");
  bar.className = "evidence-window-bar evidence-window-drag";

  const heading = document.createElement("div");
  heading.className = "evidence-window-heading";
  const title = document.createElement("strong");
  title.textContent = config.label;
  const subtitle = document.createElement("span");
  subtitle.className = "evidence-window-subtitle";
  subtitle.textContent = `${model.narrativeIdentity.slice(0, 8)}…`;
  heading.append(title, subtitle);

  const controls = document.createElement("div");
  controls.className = "evidence-window-controls";
  const controlSpecs = [
    ["minimize", "—", "Küçült"],
    ["pin", "⌖", "Sabitle"],
    ["detach", "↗", "Ayrı pencereye al"],
    ["close", "×", "Kapat"],
  ];
  for (const [action, glyph, label] of controlSpecs) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.windowAction = action;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.textContent = glyph;
    if (action === "pin") button.setAttribute("aria-pressed", "false");
    controls.append(button);
  }
  bar.append(heading, controls);

  const body = document.createElement("div");
  body.className = "evidence-window-body";
  body.append(detailPlaceholder("Exact persisted evidence yükleniyor…"));

  const resize = document.createElement("button");
  resize.type = "button";
  resize.className = "evidence-window-resize";
  resize.setAttribute("aria-label", "Pencereyi yeniden boyutlandır");
  resize.title = "Yeniden boyutlandır";

  node.append(bar, body, resize);
  ui.floatingLayer.append(node);
  model.element = node;

  node.addEventListener("pointerdown", () => focusEvidenceWindow(model.id));
  bar.addEventListener("pointerdown", (event) => startEvidenceWindowDrag(event, model));
  resize.addEventListener("pointerdown", (event) => startEvidenceWindowResize(event, model));

  controls.addEventListener("click", (event) => {
    const button = event.target instanceof Element
      ? event.target.closest("button[data-window-action]")
      : null;
    if (!(button instanceof HTMLButtonElement)) return;
    const action = button.dataset.windowAction;
    if (action === "close") {
      closeEvidenceWindow(model.id);
    } else if (action === "minimize") {
      model.minimized = !model.minimized;
      button.textContent = model.minimized ? "□" : "—";
      applyEvidenceWindowGeometry(model);
      persistEvidenceWindows();
    } else if (action === "pin") {
      model.pinned = !model.pinned;
      focusEvidenceWindow(model.id);
    } else if (action === "detach") {
      const url = API.detachedEvidence(model.narrativeIdentity, model.kind);
      button.dataset.detachUrl = url;
      window.open(
        url,
        "_blank",
        "popup=yes,resizable=yes,scrollbars=yes,width=900,height=760"
      );
    }
    event.stopPropagation();
  });

  const detach = controls.querySelector('[data-window-action="detach"]');
  if (detach instanceof HTMLButtonElement) {
    detach.dataset.detachUrl = API.detachedEvidence(model.narrativeIdentity, model.kind);
  }

  applyEvidenceWindowGeometry(model);
  return node;
}

function openEvidenceWindow(record, detail, kind) {
  const config = EVIDENCE_WINDOW_KINDS[kind];
  const narrativeIdentity = text(record?.narrative_identity ?? detail?.narrative?.narrative_identity, "");
  if (!config || !exactSha256(narrativeIdentity)) return null;

  const id = evidenceWindowId(narrativeIdentity, kind);
  const existing = state.evidenceWindows.get(id);
  if (existing) {
    focusEvidenceWindow(id);
    if (detail) renderEvidenceWindowBody(existing, detail);
    return existing;
  }

  const geometry = defaultEvidenceWindowGeometry(state.evidenceWindows.size);
  const model = {
    id,
    narrativeIdentity,
    kind,
    ...geometry,
    minimized: false,
    pinned: false,
    z: ++state.evidenceWindowZ,
    element: null,
    detail: null,
  };
  state.evidenceWindows.set(id, model);
  createEvidenceWindowShell(model);
  persistEvidenceWindows();
  void hydrateEvidenceWindow(model, detail);
  return model;
}

function restoreEvidenceWindows() {
  let raw;
  try {
    raw = JSON.parse(localStorage.getItem(EVIDENCE_WINDOW_SESSION_KEY) || "[]");
  } catch {
    return;
  }
  if (!Array.isArray(raw)) return;
  for (const saved of raw.slice(0, 10)) {
    if (!saved || !exactSha256(saved.narrativeIdentity) || !EVIDENCE_WINDOW_KINDS[saved.kind]) {
      continue;
    }
    const id = evidenceWindowId(saved.narrativeIdentity, saved.kind);
    const defaults = defaultEvidenceWindowGeometry(state.evidenceWindows.size);
    const model = {
      id,
      narrativeIdentity: saved.narrativeIdentity,
      kind: saved.kind,
      x: Number.isFinite(Number(saved.x)) ? Number(saved.x) : defaults.x,
      y: Number.isFinite(Number(saved.y)) ? Number(saved.y) : defaults.y,
      width: Number.isFinite(Number(saved.width)) ? Number(saved.width) : defaults.width,
      height: Number.isFinite(Number(saved.height)) ? Number(saved.height) : defaults.height,
      minimized: Boolean(saved.minimized),
      pinned: Boolean(saved.pinned),
      z: Number.isFinite(Number(saved.z)) ? Number(saved.z) : ++state.evidenceWindowZ,
      element: null,
      detail: null,
    };
    state.evidenceWindowZ = Math.max(state.evidenceWindowZ, model.z);
    state.evidenceWindows.set(id, model);
    createEvidenceWindowShell(model);
    void hydrateEvidenceWindow(model);
  }
}

function evidenceWindowLauncher(record, detail) {
  const launcher = document.createElement("section");
  launcher.className = "evidence-launcher depth-wide";
  const heading = document.createElement("div");
  heading.className = "evidence-launcher-head";
  const title = document.createElement("strong");
  title.textContent = "KANIT PENCERELERİ";
  const note = document.createElement("span");
  note.textContent = "Akıştan ayrılmadan derinleş";
  heading.append(title, note);

  const actions = document.createElement("div");
  actions.className = "evidence-launcher-actions";
  for (const [kind, config] of Object.entries(EVIDENCE_WINDOW_KINDS)) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.evidenceKind = kind;
    button.textContent = config.label;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openEvidenceWindow(record, detail, kind);
    });
    actions.append(button);
  }
  launcher.append(heading, actions);
  return launcher;
}

function buildExpandedContent(record, detail) {
  const textBundle =
    record && typeof record.text === "object" && record.text ? record.text : {};
  const fact = detail && typeof detail.fact_bundle === "object"
    ? detail.fact_bundle
    : {};
  const analytical = detail && typeof detail.analytical_view === "object"
    ? detail.analytical_view
    : {};

  const grid = document.createElement("div");
  grid.className = "message-depth-grid";

  grid.append(
    depthSection("SIMPLE", textBundle.simple_text, { className: "depth-simple depth-wide" }),
    depthSection("PRO", textBundle.technical_text, { className: "depth-pro" })
  );

  const intelligence = document.createElement("div");
  intelligence.className = "depth-composite";
  const intelligenceCopy = document.createElement("p");
  intelligenceCopy.textContent = text(
    textBundle.intelligence_text,
    "Structured intelligence anlatımı mevcut değil."
  );
  intelligence.append(intelligenceCopy, evidenceFamilyGrid(fact));
  grid.append(
    depthSection("INTELLIGENCE", "", {
      className: "depth-intelligence depth-wide",
      content: intelligence,
    })
  );

  const decision = document.createElement("div");
  decision.className = "depth-composite";
  const decisionCopy = document.createElement("p");
  decisionCopy.textContent = text(
    textBundle.decision_text,
    "Karar anlatımı mevcut değil."
  );
  const conditions = document.createElement("div");
  conditions.className = "condition-row";
  const next = document.createElement("span");
  next.textContent = `Sonraki koşul · ${text(analytical?.next_condition?.state, "ölçülmedi")}`;
  const invalidation = document.createElement("span");
  invalidation.textContent = `Geçersizleşme · ${displayNumber(
    analytical?.invalidation_condition?.price ?? fact?.invalidation_price
  )}`;
  conditions.append(next, invalidation);
  decision.append(decisionCopy, conditions);
  grid.append(
    depthSection("DECISION", "", {
      className: "depth-decision",
      content: decision,
    }),
    depthSection("TRADE GEOMETRY", "", {
      className: "depth-geometry",
      content: geometryGrid(fact),
    })
  );

  const capital = document.createElement("div");
  capital.className = "depth-composite";
  const capitalCopy = document.createElement("p");
  capitalCopy.textContent = text(
    textBundle.capital_text,
    "Bu mesajda sermaye anlatımı mevcut değil."
  );
  const capitalState = document.createElement("span");
  capitalState.className = "capital-state";
  capitalState.textContent = `Sanal sermaye sonucu · ${text(
    analytical?.capital_consequence?.state,
    "not_bound"
  ).replaceAll("_", " ")} · REAL_CAPITAL=0`;
  capital.append(capitalCopy, capitalState);
  grid.append(
    depthSection("CAPITAL", "", {
      className: "depth-capital",
      content: capital,
    }),
    depthSection("PROOF", "", {
      className: "depth-proof",
      content: proofPanel(fact),
    })
  );

  grid.append(evidenceWindowLauncher(record, detail));
  return grid;
}

function detailPlaceholder(label) {
  const box = document.createElement("div");
  box.className = "message-depth-placeholder";
  box.textContent = label;
  return box;
}

function renderExpandedPanel(item, record, detail) {
  const panel = item.querySelector(".message-detail");
  if (!(panel instanceof HTMLElement)) return;
  preserveMessageAnchor(item, () => {
    panel.replaceChildren(buildExpandedContent(record, detail));
    panel.hidden = false;
  });
}

async function loadMessageDetail(item, record) {
  const identity = text(record?.narrative_identity, "");
  if (!identity || state.detailRequests.has(identity)) return;

  if (record.__fixture_detail && typeof record.__fixture_detail === "object") {
    state.details.set(identity, record.__fixture_detail);
    renderExpandedPanel(item, record, record.__fixture_detail);
    return;
  }

  state.detailRequests.add(identity);
  try {
    const payload = await fetchJson(API.detail(identity));
    if (payload.status === "ready" && payload.detail) {
      state.details.set(identity, payload.detail);
      if (state.expanded.has(identity)) {
        renderExpandedPanel(item, record, payload.detail);
      }
    } else {
      const panel = item.querySelector(".message-detail");
      if (panel instanceof HTMLElement && state.expanded.has(identity)) {
        preserveMessageAnchor(item, () => {
          panel.replaceChildren(
            detailPlaceholder(
              payload.status === "unavailable"
                ? "Structured detail runtime şu anda bağlı değil."
                : "Bu mesaj için structured detail bulunamadı."
            )
          );
        });
      }
    }
  } catch {
    const panel = item.querySelector(".message-detail");
    if (panel instanceof HTMLElement && state.expanded.has(identity)) {
      preserveMessageAnchor(item, () => {
        panel.replaceChildren(
          detailPlaceholder("Structured detail okunamadı; içerik uydurulmadı.")
        );
      });
    }
  } finally {
    state.detailRequests.delete(identity);
  }
}

function toggleMessageExpansion(item, record) {
  const identity = text(record?.narrative_identity, "");
  if (!identity) return;
  const summary = item.querySelector(".message-summary");
  const panel = item.querySelector(".message-detail");
  if (!(summary instanceof HTMLButtonElement) || !(panel instanceof HTMLElement)) return;

  const willOpen = !state.expanded.has(identity);
  if (
    willOpen
    && !state.details.has(identity)
    && record.__fixture_detail
    && typeof record.__fixture_detail === "object"
  ) {
    state.details.set(identity, record.__fixture_detail);
  }
  preserveMessageAnchor(item, () => {
    if (willOpen) {
      state.expanded.add(identity);
      item.classList.add("is-expanded");
      summary.setAttribute("aria-expanded", "true");
      const cue = summary.querySelector(".message-expand-cue");
      if (cue) cue.textContent = "Detayı kapat ↑";
      panel.hidden = false;
      const cached = state.details.get(identity);
      panel.replaceChildren(
        cached
          ? buildExpandedContent(record, cached)
          : detailPlaceholder("Exact persisted message depth okunuyor…")
      );
    } else {
      state.expanded.delete(identity);
      item.classList.remove("is-expanded");
      summary.setAttribute("aria-expanded", "false");
      const cue = summary.querySelector(".message-expand-cue");
      if (cue) cue.textContent = "Detayı aç ↓";
      panel.hidden = true;
    }
  });

  if (willOpen && !state.details.has(identity)) {
    void loadMessageDetail(item, record);
  }
}

function renderMessage(record, { isNew = false } = {}) {
  const item = document.createElement("li");
  item.className = "message";
  if (isNew) item.classList.add("is-new");
  const identity = text(record.narrative_identity, "");
  item.dataset.identity = identity;

  const summary = document.createElement("button");
  summary.type = "button";
  summary.className = "message-summary";
  summary.setAttribute("aria-expanded", String(state.expanded.has(identity)));

  const meta = document.createElement("div");
  meta.className = "message-meta";

  const time = document.createElement("span");
  time.textContent = formatTime(record.event_at_ms);
  const symbol = document.createElement("strong");
  symbol.textContent = text(record.symbol, "PİYASA");
  const timeframe = document.createElement("span");
  timeframe.textContent = text(record.timeframe, "—");
  const stateBadge = document.createElement("span");
  stateBadge.className = "message-state";
  stateBadge.textContent = messageState(record);
  meta.append(time, symbol, timeframe, stateBadge);

  const copy = document.createElement("p");
  copy.className = "message-copy";
  copy.textContent = messageText(record);

  const footer = document.createElement("div");
  footer.className = "message-summary-foot";
  const chips = document.createElement("div");
  chips.className = "message-chips";
  chips.append(buildChip(shortSource(record.source_kind)));
  if (record.original_text_preserved === true) chips.append(buildChip("ORİJİNAL METİN"));
  if (record.real_capital === 0) chips.append(buildChip("GERÇEK PARA KAPALI", true));
  const cue = document.createElement("span");
  cue.className = "message-expand-cue";
  cue.textContent = state.expanded.has(identity) ? "Detayı kapat ↑" : "Detayı aç ↓";
  footer.append(chips, cue);
  summary.append(meta, copy, footer);

  const detailPanel = document.createElement("div");
  detailPanel.className = "message-detail";
  detailPanel.hidden = !state.expanded.has(identity);
  const cached = state.details.get(identity);
  if (state.expanded.has(identity)) {
    detailPanel.append(
      cached
        ? buildExpandedContent(record, cached)
        : detailPlaceholder("Exact persisted message depth okunuyor…")
    );
    item.classList.add("is-expanded");
  }

  summary.addEventListener("click", () => toggleMessageExpansion(item, record));
  item.append(summary, detailPanel);
  if (state.expanded.has(identity) && !cached) void loadMessageDetail(item, record);
  return item;
}
function renderAll() {
  if (!ui.list || !ui.empty) return;
  ui.list.replaceChildren();
  for (const record of state.messages) {
    ui.list.append(renderMessage(record));
  }
  const isEmpty = state.messages.length === 0;
  ui.empty.hidden = !isEmpty;
  ui.list.hidden = isEmpty;
  if (ui.loadOlder) ui.loadOlder.hidden = !state.hasOlder || isEmpty;
  updateUnread();
}

function updateUnread() {
  if (!ui.newButton || !ui.newCount) return;
  ui.newCount.textContent = String(state.unread);
  ui.newButton.hidden = state.unread <= 0;
}

function scrollToBottom({ smooth = true } = {}) {
  if (!ui.viewport) return;
  ui.viewport.scrollTo({
    top: ui.viewport.scrollHeight,
    behavior: smooth ? "smooth" : "auto",
  });
  state.unread = 0;
  updateUnread();
}

function resetMessages() {
  state.messages = [];
  state.ids = new Set();
  state.beforeCursor = null;
  state.newestCursor = null;
  state.hasOlder = false;
  state.unread = 0;
  state.expanded = new Set();
  state.details = new Map();
  state.detailRequests = new Set();
  renderAll();
}

function mergeInitial(records) {
  const chronological = [...records].reverse();
  state.messages = [];
  state.ids = new Set();
  for (const record of chronological) {
    const id = text(record.narrative_identity, "");
    if (!id || state.ids.has(id)) continue;
    state.ids.add(id);
    state.messages.push(record);
  }
}

function appendRecord(record, cursor = null, { fixtureNew = false } = {}) {
  const id = text(record && record.narrative_identity, "");
  if (!id || state.ids.has(id)) return false;
  const stayAtBottom = isNearBottom();
  state.ids.add(id);
  state.messages.push(record);

  if (ui.list && !ui.list.hidden) {
    ui.list.append(renderMessage(record, { isNew: fixtureNew || stayAtBottom }));
  } else {
    renderAll();
  }

  if (cursor) state.newestCursor = cursor;
  if (stayAtBottom) {
    window.requestAnimationFrame(() => scrollToBottom({ smooth: !state.fixture }));
  } else {
    state.unread += 1;
    updateUnread();
    if (ui.announcer) ui.announcer.textContent = `${state.unread} yeni mesaj`;
  }
  return true;
}

async function loadInitial() {
  resetMessages();
  setConnection("connecting", "BAĞLANIYOR", "kalıcı mesajlar okunuyor");

  const params = queryParams({ limit: 50 });
  let payload;
  try {
    payload = await fetchJson(`${API.messages}?${params.toString()}`);
  } catch (error) {
    setConnection("degraded", "BAĞLANTI SINIRLI", "polling yanıtı alınamadı");
    if (ui.emptyTitle) ui.emptyTitle.textContent = "Akış şu anda okunamıyor";
    if (ui.emptyCopy) ui.emptyCopy.textContent = "Backend gerçeği uydurulmadı. Bağlantı yeniden denenecek.";
    renderAll();
    startPolling();
    return;
  }

  const page = payload && typeof payload.page === "object" ? payload.page : null;
  if (payload.status === "unavailable" || !page) {
    setConnection("degraded", "RUNTIME HAZIR DEĞİL", "mesaj deposu yapılandırılmamış");
    if (ui.emptyTitle) ui.emptyTitle.textContent = "Stream runtime hazır değil";
    if (ui.emptyCopy) ui.emptyCopy.textContent = "Eksik runtime, boş piyasa sinyali gibi gösterilmez.";
    renderAll();
    return;
  }

  const items = Array.isArray(page.items) ? page.items : [];
  mergeInitial(items);
  state.beforeCursor = typeof page.oldest_cursor === "string" ? page.oldest_cursor : null;
  state.newestCursor = typeof page.newest_cursor === "string" ? page.newest_cursor : null;
  state.hasOlder = Boolean(page.has_more);
  renderAll();
  window.requestAnimationFrame(() => scrollToBottom({ smooth: false }));
  connectLive();
}

async function loadOlder() {
  if (state.loadingHistory || !state.beforeCursor || !state.hasOlder) return;
  state.loadingHistory = true;
  if (ui.loadOlder) ui.loadOlder.textContent = "Yükleniyor…";
  const before = state.beforeCursor;
  const oldHeight = ui.viewport ? ui.viewport.scrollHeight : 0;
  const oldTop = ui.viewport ? ui.viewport.scrollTop : 0;

  try {
    const params = queryParams({ before, limit: 50 });
    const payload = await fetchJson(`${API.messages}?${params.toString()}`);
    const page = payload && typeof payload.page === "object" ? payload.page : null;
    const items = page && Array.isArray(page.items) ? [...page.items].reverse() : [];
    const additions = [];
    for (const record of items) {
      const id = text(record.narrative_identity, "");
      if (!id || state.ids.has(id)) continue;
      state.ids.add(id);
      additions.push(record);
    }
    state.messages = [...additions, ...state.messages];
    state.beforeCursor = page && typeof page.oldest_cursor === "string" ? page.oldest_cursor : state.beforeCursor;
    state.hasOlder = Boolean(page && page.has_more);
    renderAll();
    window.requestAnimationFrame(() => {
      if (!ui.viewport) return;
      const delta = ui.viewport.scrollHeight - oldHeight;
      ui.viewport.scrollTop = oldTop + delta;
    });
  } catch {
    setConnection("degraded", "GEÇMİŞ SINIRLI", "eski mesajlar yüklenemedi");
  } finally {
    state.loadingHistory = false;
    if (ui.loadOlder) ui.loadOlder.textContent = "↑ Daha eski mesajları yükle";
  }
}

function liveUrl() {
  const params = queryParams({ after: state.newestCursor, limit: 200 });
  params.delete("before");
  return `${API.live}?${params.toString()}`;
}

function connectLive() {
  if (state.fixture) return;
  if (state.eventSource) state.eventSource.close();
  if (!("EventSource" in window)) {
    setConnection("degraded", "POLLING", "EventSource yok; güvenli fallback");
    startPolling();
    return;
  }

  setConnection("connecting", "CANLI AKIŞ", "SSE bağlantısı kuruluyor");
  const source = new EventSource(liveUrl());
  state.eventSource = source;

  source.addEventListener("open", () => {
    setConnection("live", "CANLI", "SSE bağlı · yeni mesajlar otomatik");
    stopPolling();
    if (ui.transportMode) ui.transportMode.textContent = "SSE CANLI";
  });

  source.addEventListener("message", (event) => {
    try {
      const record = JSON.parse(event.data);
      appendRecord(record, event.lastEventId || null);
    } catch {
      setConnection("degraded", "AKIŞ HATASI", "geçersiz mesaj güvenle reddedildi");
    }
  });

  source.addEventListener("error", () => {
    setConnection("degraded", "YENİDEN BAĞLANIYOR", "SSE kesildi · polling fallback aktif");
    if (ui.transportMode) ui.transportMode.textContent = "POLLING FALLBACK";
    startPolling();
  });
}

async function pollCatchUp() {
  if (state.fixture) return;
  try {
    const params = queryParams({ after: state.newestCursor, limit: 100 });
    const payload = await fetchJson(`${API.messages}?${params.toString()}`);
    const page = payload && typeof payload.page === "object" ? payload.page : null;
    const items = page && Array.isArray(page.items) ? page.items : [];
    for (const record of items) appendRecord(record);
    if (page && typeof page.newest_cursor === "string" && items.length) {
      state.newestCursor = page.newest_cursor;
    }
  } catch {
    setConnection("degraded", "BAĞLANTI SINIRLI", "SSE ve polling yeniden denenecek");
  }
}

function startPolling() {
  if (state.pollingTimer) return;
  void pollCatchUp();
  state.pollingTimer = window.setInterval(() => void pollCatchUp(), 5000);
}

function stopPolling() {
  if (!state.pollingTimer) return;
  window.clearInterval(state.pollingTimer);
  state.pollingTimer = null;
}

function openDrawer(drawer) {
  if (!drawer || !ui.backdrop) return;
  for (const item of [ui.discoveryDrawer, ui.settingsDrawer]) {
    if (item && item !== drawer) item.hidden = true;
  }
  drawer.hidden = false;
  ui.backdrop.hidden = false;
  if (ui.searchButton) ui.searchButton.setAttribute("aria-expanded", String(drawer === ui.discoveryDrawer));
  if (ui.filterButton) ui.filterButton.setAttribute("aria-expanded", String(drawer === ui.discoveryDrawer));
  if (ui.soundButton) ui.soundButton.setAttribute("aria-expanded", String(drawer === ui.settingsDrawer));
  if (ui.settingsButton) ui.settingsButton.setAttribute("aria-expanded", String(drawer === ui.settingsDrawer));
}

function closeDrawers() {
  for (const drawer of [ui.discoveryDrawer, ui.settingsDrawer]) {
    if (drawer) drawer.hidden = true;
  }
  if (ui.backdrop) ui.backdrop.hidden = true;
  for (const button of [ui.searchButton, ui.filterButton, ui.soundButton, ui.settingsButton]) {
    if (button) button.setAttribute("aria-expanded", "false");
  }
}

function fixtureIdentity(index) {
  return index.toString(16).padStart(64, "0");
}

function fixtureRecord(index, symbol, timeframe, stateLabel, copy, minutesAgo, source = "deterministic") {
  const narrativeIdentity = fixtureIdentity(index + 1);
  const forecastIdentity = fixtureIdentity(700 + index);
  const proofIdentity = fixtureIdentity(800 + index);
  const familyNames = ["geometry", "liquidity", "order_flow", "derivatives", "onchain"];
  const familyContributions = familyNames.map((family, offset) => ({
    family,
    state: "observed",
    direction: offset === 3 ? "mixed" : "support",
    support_points: 74 - offset * 8,
    opposition_points: 8 + offset * 4,
    evidence_quality_0_1: 0.94 - offset * 0.07,
    freshness_0_1: 0.97 - offset * 0.06,
    material_conflict_count: offset === 3 ? 1 : 0,
  }));
  return {
    narrative_identity: narrativeIdentity,
    event_at_ms: Date.now() - minutesAgo * 60_000,
    symbol,
    timeframe,
    source_kind: source,
    original_text_preserved: true,
    real_capital: 0,
    __fixture_state: stateLabel,
    text: {
      collapsed_text: copy,
      simple_text: `${copy} Kısaca sistem yeni kanıt gelene kadar görüşünü kontrollü tutuyor.`,
      technical_text: "Trend yapısı, likidite davranışı ve emir akışı birlikte değerlendirildi; teyit eşiği henüz tam kapanmadı.",
      intelligence_text: "Beş-aile kanıtı aynı yönde değil. Geometri ve likidite destek verirken türev tarafı ana çelişkiyi taşıyor.",
      decision_text: "Yeni karar için tetik bölgesinin korunması ve emir akışının teyidi gerekiyor. Geçersizleşme seviyesi aşılırsa görüş bırakılır.",
      capital_text: "Bu mesaj yeni sanal sermaye hareketi üretmedi. Üç-vault davranışı S11’de canonical runtime ile tamamlanacak.",
    },
    __fixture_detail: {
      analytical_view: {
        stance: {
          effective_stance: stateLabel.toLowerCase(),
          strength: "moderate",
          support_score_0_100: 74,
          opposition_score_0_100: 19,
          net_support_points: 55,
        },
        next_condition: { state: "entry_zone_watch" },
        invalidation_condition: { price: 60750 },
        capital_consequence: { state: "not_bound" },
      },
      fact_bundle: {
        forecast_identity: forecastIdentity,
        proof_identity: proofIdentity,
        confluence_support_score_0_100: 74,
        confluence_opposition_score_0_100: 19,
        family_contributions: familyContributions,
        trigger_zone: { low: 62000, high: 62500 },
        target_zone: { low: 65000, high: 66000 },
        invalidation_price: 60750,
      },
      message_input: { importance: "important", category: "decision" },
      read_only: true,
      production_authority: false,
      real_capital: 0,
    },
  };
}

function fixtureMessages() {
  return [
    fixtureRecord(1, "BTCUSDT", "4h", "GÖRÜŞ KORUNUYOR", "Bitcoin tarafında ana yapı korunuyor. Likidite temizliği sonrası alıcı tepkisi var; sistem yeni teyit gelmeden pozisyon görüşünü büyütmüyor.", 48),
    fixtureRecord(2, "ETHUSDT", "1h", "BEKLİYORUM", "Ethereum kısa vadeli yapıda kararsız. Emir akışı toparlansa da türev tarafındaki teyit henüz yeterli değil; yeni karar üretmek için bekliyorum.", 31),
    fixtureRecord(3, "BTCUSDT", "15m", "GÖRÜŞ GÜÇLENİYOR", "Satış baskısının devam etmemesi ve emir akışındaki toparlanma önceki BTC görüşünü güçlendiriyor. Bir sonraki koşul henüz tamamlanmadı.", 18, "local_rewrite"),
    fixtureRecord(4, "SOLUSDT", "5m", "RİSK ARTTI", "SOL tarafında kısa vadeli hareket hızlandı ancak kanıt kalitesi aynı ölçüde artmadı. Sistem bu değişikliği fırsat değil, izlenmesi gereken risk olarak işaretliyor.", 11),
    fixtureRecord(5, "ETHUSDT", "4h", "SONUÇ KAYDI", "Önceki ETH beklentisinin sonucu değiştirilemez kayda eklendi. Eski mesaj korunuyor; yeni sonuç ayrı bir mesaj olarak tutuluyor.", 6),
    fixtureRecord(6, "BTCUSDT", "5m", "YENİ TEYİT", "Önce eksik olan teyitlerden biri geldi. Kısa vadeli emir akışı mevcut görüşü destekliyor, fakat sistem hâlâ tetik koşulunun tamamlanmasını bekliyor.", 1, "local_rewrite"),
  ];
}

function applyFixture(name) {
  state.fixture = name;
  if (ui.fixtureBanner) ui.fixtureBanner.hidden = false;
  resetMessages();
  const base = fixtureMessages();

  if (name === "empty") {
    setConnection("live", "HAZIR", "fixture · mesaj bekleniyor");
    if (ui.emptyTitle) ui.emptyTitle.textContent = "Henüz anlamlı değişiklik yok";
    if (ui.emptyCopy) ui.emptyCopy.textContent = "Sistem sessiz kalabiliyor. NO_SIGNAL ve bekleme geçerli durumlardır.";
    renderAll();
    return;
  }

  if (name === "degraded") {
    mergeInitial(base.slice(0, 3).reverse());
    renderAll();
    setConnection("degraded", "VERİ SINIRLI", "fixture · bağlantı bozulması");
    if (ui.transportMode) ui.transportMode.textContent = "POLLING FALLBACK";
    window.requestAnimationFrame(() => scrollToBottom({ smooth: false }));
    return;
  }

  const fixtureCount = name === "long" ? 36 : name === "history" ? 14 : 0;
  const records = fixtureCount
    ? Array.from({ length: fixtureCount }, (_, i) => {
        const seed = base[i % base.length];
        return {
          ...seed,
          narrative_identity: fixtureIdentity(100 + i),
          event_at_ms: Date.now() - (fixtureCount - i) * 4 * 60_000,
        };
      })
    : base;

  for (const record of records) {
    state.ids.add(record.narrative_identity);
    state.messages.push(record);
  }
  state.hasOlder = name === "history" || name === "long";
  if (name === "history") state.unread = 3;
  renderAll();
  setConnection("live", "CANLI", "fixture · Stream görsel kabul");
  if (ui.transportMode) ui.transportMode.textContent = "SSE CANLI · FIXTURE";

  window.requestAnimationFrame(() => {
    if (!ui.viewport) return;
    if (name === "history") {
      ui.viewport.scrollTop = Math.max(0, ui.viewport.scrollHeight * 0.18);
    } else {
      scrollToBottom({ smooth: false });
    }

    if (name === "incoming" && state.messages.length) {
      const last = ui.list ? ui.list.lastElementChild : null;
      if (last) last.classList.add("is-new");
    }
  });

  if (name === "expanded" || name === "windows") {
    window.requestAnimationFrame(() => {
      const target = ui.list?.children?.[2];
      const summary = target?.querySelector?.(".message-summary");
      if (summary instanceof HTMLButtonElement) summary.click();

      if (name === "windows") {
        closeAllEvidenceWindows({ persist: false });
        try {
          localStorage.removeItem(EVIDENCE_WINDOW_SESSION_KEY);
        } catch {
          // Deterministic fixture remains usable without storage.
        }
        const record = state.messages[2];
        const detail = record?.__fixture_detail;
        if (record && detail) {
          openEvidenceWindow(record, detail, "liquidity");
          openEvidenceWindow(record, detail, "geometry");
          const decisionWindow = openEvidenceWindow(record, detail, "decision");
          if (decisionWindow) {
            decisionWindow.pinned = true;
            decisionWindow.x = 44;
            decisionWindow.y = 70;
            applyEvidenceWindowGeometry(decisionWindow);
          }
          persistEvidenceWindows();
        }
      }
    });
  }

  if (name === "filters") {
    openDrawer(ui.discoveryDrawer);
    if (ui.searchInput) ui.searchInput.value = "likidite";
    if (ui.symbolFilter) ui.symbolFilter.value = "BTCUSDT";
  }
}

function wireUi() {
  ui.searchButton?.addEventListener("click", () => openDrawer(ui.discoveryDrawer));
  ui.filterButton?.addEventListener("click", () => openDrawer(ui.discoveryDrawer));
  ui.soundButton?.addEventListener("click", () => openDrawer(ui.settingsDrawer));
  ui.settingsButton?.addEventListener("click", () => openDrawer(ui.settingsDrawer));
  ui.backdrop?.addEventListener("click", closeDrawers);
  document.querySelectorAll("[data-close-drawer]").forEach((button) => {
    button.addEventListener("click", closeDrawers);
  });

  ui.loadOlder?.addEventListener("click", () => void loadOlder());
  ui.newButton?.addEventListener("click", () => scrollToBottom());

  ui.viewport?.addEventListener("scroll", () => {
    if (isNearBottom() && state.unread > 0) {
      state.unread = 0;
      updateUnread();
    }
    if (ui.viewport && ui.viewport.scrollTop < 70 && state.hasOlder && !state.fixture) {
      void loadOlder();
    }
  });

  ui.clearFilters?.addEventListener("click", () => {
    if (ui.searchInput) ui.searchInput.value = "";
    if (ui.symbolFilter) ui.symbolFilter.value = "";
    if (ui.timeframeFilter) ui.timeframeFilter.value = "";
  });

  ui.applyFilters?.addEventListener("click", () => {
    state.filters.text = ui.searchInput?.value.trim() || "";
    state.filters.symbol = ui.symbolFilter?.value || "";
    state.filters.timeframe = ui.timeframeFilter?.value || "";
    closeDrawers();
    if (!state.fixture) void loadInitial();
  });

  document.querySelectorAll('input[name="density"]').forEach((radio) => {
    radio.addEventListener("change", (event) => {
      const target = event.target;
      if (target instanceof HTMLInputElement && target.checked) {
        document.body.dataset.density = target.value;
      }
    });
  });

  window.addEventListener("resize", () => {
    for (const model of state.evidenceWindows.values()) {
      applyEvidenceWindowGeometry(model);
    }
    persistEvidenceWindows();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawers();
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openDrawer(ui.discoveryDrawer);
      ui.searchInput?.focus();
    }
  });
}

function init() {
  wireUi();
  if (state.fixture) {
    applyFixture(state.fixture);
    return;
  }
  restoreEvidenceWindows();
  void loadInitial();
}

window.__cryptoSignalStreamS9 = Object.freeze({
  openEvidenceWindow,
  closeAllEvidenceWindows,
  evidenceWindowSnapshot,
  persistEvidenceWindows,
});

window.addEventListener("beforeunload", () => {
  persistEvidenceWindows();
  state.eventSource?.close();
  stopPolling();
});

init();
