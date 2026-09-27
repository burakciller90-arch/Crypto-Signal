"use strict";

const params = new URLSearchParams(window.location.search);
const narrativeIdentity = params.get("narrative") || "";
const kind = params.get("kind") || "";

const KIND_CONFIG = Object.freeze({
  liquidity: {
    label: "Likidite",
    family: "liquidity",
    aliases: Object.freeze(["liquidity"]),
    weight: 25,
    concept: "liquidity_sweep",
  },
  order_flow: {
    label: "Emir Akışı",
    family: "order_flow_absorption",
    aliases: Object.freeze(["order_flow_absorption", "order_flow"]),
    weight: 25,
    concept: "cvd",
  },
  derivatives: {
    label: "Türevler",
    family: "derivatives",
    aliases: Object.freeze(["derivatives"]),
    weight: 15,
    concept: "liquidation_heatmap",
  },
  onchain: {
    label: "On-chain",
    family: "onchain_smart_money",
    aliases: Object.freeze(["onchain_smart_money", "onchain"]),
    weight: 15,
    concept: null,
  },
  geometry: {
    label: "Geometri",
    family: "geometry_pa_elliott_harmonic",
    aliases: Object.freeze(["geometry_pa_elliott_harmonic", "geometry"]),
    weight: 20,
    concept: "invalidation",
  },
  decision: { label: "Karar", family: null, concept: "agreement_vs_probability" },
  capital: { label: "Sermaye", family: null, concept: "paper_trading" },
  event_risk: { label: "Event Risk", family: null, concept: "abstain" },
  proof: { label: "Proof", family: null, concept: "calibration" },
});

const title = document.getElementById("evidenceTitle");
const identity = document.getElementById("evidenceIdentity");
const content = document.getElementById("evidenceContent");

function validSha256(value) {
  return /^[0-9a-f]{64}$/.test(value);
}

function text(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function number(value, fallback = "—") {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 }).format(n);
}

async function fetchJson(url) {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return await response.json();
}

function card(label, value) {
  const node = document.createElement("div");
  node.className = "evidence-popout-card";
  const l = document.createElement("span");
  l.textContent = label;
  const v = document.createElement("strong");
  v.textContent = text(value);
  node.append(l, v);
  return node;
}

function section(label, body) {
  const node = document.createElement("section");
  node.className = "evidence-popout-section";
  const h = document.createElement("h2");
  h.textContent = label;
  const p = document.createElement("p");
  p.textContent = text(body);
  node.append(h, p);
  return node;
}

function familyContribution(fact, config) {
  const items = Array.isArray(fact?.family_contributions) ? fact.family_contributions : [];
  const aliases = Array.isArray(config?.aliases) ? config.aliases : [];
  return items.find((item) =>
    item && aliases.includes(text(item.family, "").toLowerCase())
  ) || null;
}

function familyExplanation(config, fact) {
  const contribution = familyContribution(fact, config);
  const state = text(contribution?.state, "").toLowerCase();
  if (!contribution || ["no_evidence", "not_evaluable"].includes(state)) {
    return `${config.label} için bu mesajda kabul edilmiş exact kanıt yok. Yönlü katkı üretilmedi ve current data ile kanıt uydurulmadı.`;
  }
  if (state === "abstain") {
    return `${config.label} ölçüldü ancak bu mesajda yönlü katkı üretmedi.`;
  }
  const support = Number(contribution?.support_points);
  const opposition = Number(contribution?.opposition_points);
  const safeSupport = Number.isFinite(support) ? support : 0;
  const safeOpposition = Number.isFinite(opposition) ? opposition : 0;
  let sentence;
  if (safeSupport > safeOpposition && safeSupport > 0) {
    sentence = `${config.label}, mevcut karar yönünü ${number(safeSupport)} / ${number(config.weight)} puanla destekliyor.`;
  } else if (safeOpposition > safeSupport && safeOpposition > 0) {
    sentence = `${config.label}, mevcut karar yönüne ${number(safeOpposition)} / ${number(config.weight)} puanlık karşı ağırlık taşıyor.`;
  } else {
    sentence = `${config.label} ölçüldü ancak bu mesajda yönlü katkı üretmedi.`;
  }
  if (Number(contribution?.material_conflict_count) > 0) {
    sentence += " Bu ailede ayrıca persisted çelişki kaydı var.";
  }
  return sentence;
}

function exactWhy(config, detail) {
  const fact = detail?.fact_bundle || {};
  const analytical = detail?.analytical_view || {};
  if (config.family) return familyExplanation(config, fact);
  if (kind === "decision") {
    return `Karar durumu ${text(analytical?.stance?.effective_stance)}; sonraki koşul ${text(
      analytical?.next_condition?.state
    )}. Pencere bu kararın exact lineage'ını korur.`;
  }
  if (kind === "capital") {
    return `Sanal sermaye sonucu ${text(
      analytical?.capital_consequence?.state,
      "not_bound"
    )}. REAL_CAPITAL=0; bu yalnız sanal/analitik sermaye bağlamıdır.`;
  }
  if (kind === "event_risk") {
    return `Event Risk durumu ${text(fact?.event_context_state)}. Bu persisted bağlamdır; yeni haber yorumu üretmez.`;
  }
  if (kind === "proof") {
    return `Forecast ${text(fact?.forecast_identity).slice(0, 12)}… ve proof ${text(
      fact?.proof_identity
    ).slice(0, 12)}… aynı persisted message lineage'ına bağlıdır.`;
  }
  return "Bu pencere exact persisted message detail üzerinden okunur.";
}

function renderCore(config, detail) {
  const fact = detail.fact_bundle || {};
  const analytical = detail.analytical_view || {};
  const narrative = detail.narrative || {};

  const summary = document.createElement("div");
  summary.className = "evidence-popout-summary";
  summary.append(
    card("Varlık", narrative.symbol),
    card("Zaman", narrative.timeframe),
    card("Pencere", config.label)
  );
  content.append(summary);

  if (config.family) {
    const contribution = familyContribution(fact, config);
    content.append(
      section(
        "BU MESAJDA NE ANLAMA GELİYOR?",
        familyExplanation(config, fact)
      )
    );
    if (kind === "geometry") {
      content.append(
        section(
          "Exact trade geometry",
          `Tetik ${number(fact?.trigger_zone?.low)}–${number(
            fact?.trigger_zone?.high
          )} · hedef ${number(fact?.target_zone?.low)}–${number(
            fact?.target_zone?.high
          )} · geçersizleşme ${number(fact?.invalidation_price)}`
        )
      );
    }
    const refs = Array.isArray(contribution?.source_evidence_identities)
      ? contribution.source_evidence_identities
      : [];
    const refsSection = section(
      "EXACT SOURCE EVIDENCE",
      refs.length
        ? `${refs.length} persisted source identity bu aileye bağlı.`
        : "Bu aile için exact source identity yok; veri uydurulmadı."
    );
    for (const ref of refs) {
      const code = document.createElement("code");
      code.textContent = ref;
      refsSection.append(code);
    }
    content.append(refsSection);
  } else if (kind === "decision") {
    content.append(
      section(
        "Decision",
        `Stance ${text(analytical?.stance?.effective_stance)} · strength ${text(
          analytical?.stance?.strength
        )} · next ${text(analytical?.next_condition?.state)} · invalidation ${number(
          analytical?.invalidation_condition?.price ?? fact?.invalidation_price
        )}`
      )
    );
  } else if (kind === "capital") {
    content.append(
      section(
        "Capital consequence",
        `${text(analytical?.capital_consequence?.state, "not_bound")} · REAL_CAPITAL=0`
      )
    );
  } else if (kind === "event_risk") {
    content.append(
      section(
        "Event Risk",
        `Event context ${text(fact?.event_context_state)} · uncertainty ${(
          Array.isArray(fact?.uncertainty_flags) ? fact.uncertainty_flags : []
        ).join(", ") || "yok"}`
      )
    );
  } else if (kind === "proof") {
    const proof = section(
      "Exact proof lineage",
      "Bu pencere exact persisted lineage'ı korur. Frozen visual proof yalnız immutable karar freeze'i çözülebiliyorsa aşağıda çizilir."
    );
    const forecast = document.createElement("code");
    forecast.textContent = `forecast: ${text(fact?.forecast_identity)}`;
    const proofId = document.createElement("code");
    proofId.textContent = `proof: ${text(fact?.proof_identity)}`;
    proof.append(forecast, proofId);
    content.append(proof);

    const actions = document.createElement("div");
    actions.className = "evidence-popout-actions";
    const verify = document.createElement("button");
    verify.type = "button";
    verify.textContent = "Persisted Decision Proof’u doğrula";
    const result = document.createElement("span");
    result.className = "proof-result";
    verify.addEventListener("click", async () => {
      const forecastIdentity = text(fact?.forecast_identity, "");
      if (!validSha256(forecastIdentity)) return;
      verify.disabled = true;
      result.textContent = "Doğrulanıyor…";
      try {
        const payload = await fetchJson(
          `/api/decision-proof/forecast/${encodeURIComponent(forecastIdentity)}`
        );
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
    actions.append(verify, result);
    content.append(actions);
  }

  content.append(section("Bu mesajda neden önemli?", exactWhy(config, detail)));

  if (config.concept) {
    const lesson = document.createElement("section");
    lesson.className = "evidence-popout-section";
    const h = document.createElement("h2");
    h.textContent = "Bu nedir?";
    const p = document.createElement("p");
    p.textContent = "Deterministik eğitim açıklamasını aç.";
    const actions = document.createElement("div");
    actions.className = "evidence-popout-actions";
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Açıklamayı getir";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const payload = await fetchJson(`/api/education/${config.concept}`);
        const found = payload?.lesson || {};
        p.textContent = `${text(found.beginner_tr)} ${text(found.why_it_matters_tr, "")}`.trim();
      } catch {
        p.textContent = "Eğitim içeriği şu anda okunamadı.";
      } finally {
        button.disabled = false;
      }
    });
    actions.append(button);
    lesson.append(h, p, actions);
    content.append(lesson);
  }
}

function resolutionLabel(value) {
  const normalized = text(value, "UNAVAILABLE_EXPLICIT");
  if (
    ["READY_EXACT", "IDENTITY_ONLY_EXACT", "UNAVAILABLE_EXPLICIT"].includes(
      normalized
    )
  ) {
    return normalized;
  }
  return "UNAVAILABLE_EXPLICIT";
}

function renderExactEvidenceManifest(payload) {
  const root = document.createElement("section");
  root.className = "evidence-popout-section f6-exact-evidence-manifest";
  const heading = document.createElement("h2");
  heading.textContent = "Exact Frozen Evidence · F6";
  const intro = document.createElement("p");
  intro.textContent =
    "Her kanıt referansı yalnız üç mekanik durumda gösterilir: READY_EXACT, IDENTITY_ONLY_EXACT veya UNAVAILABLE_EXPLICIT. Current market verisiyle geçmiş kanıt yeniden kurulmaz.";
  root.append(heading, intro);

  const counts = payload?.resolution_counts || {};
  const countLine = document.createElement("p");
  countLine.textContent =
    `READY_EXACT ${number(counts.READY_EXACT, "0")} · IDENTITY_ONLY_EXACT ${number(
      counts.IDENTITY_ONLY_EXACT,
      "0"
    )} · UNAVAILABLE_EXPLICIT ${number(counts.UNAVAILABLE_EXPLICIT, "0")}`;
  root.append(countLine);

  const resolutions = Array.isArray(payload?.resolutions)
    ? payload.resolutions
    : [];
  for (const resolution of resolutions) {
    const item = document.createElement("div");
    item.className = "evidence-popout-card";
    item.dataset.resolutionState = resolutionLabel(
      resolution?.resolution_state
    );
    const label = document.createElement("span");
    label.textContent = text(resolution?.domain, "evidence").replaceAll("_", " ");
    const value = document.createElement("strong");
    value.textContent = resolutionLabel(resolution?.resolution_state);
    item.append(label, value);

    const reason = document.createElement("small");
    reason.textContent = text(
      resolution?.reason,
      "exact evidence resolution reason unavailable"
    );
    item.append(reason);

    const capabilities =
      resolution?.capabilities && typeof resolution.capabilities === "object"
        ? resolution.capabilities
        : {};
    for (const [capability, state] of Object.entries(capabilities)) {
      const cap = document.createElement("code");
      cap.textContent = `${capability}: ${resolutionLabel(state)}`;
      item.append(cap);
    }
    root.append(item);
  }

  const references = Array.isArray(payload?.reference_resolutions)
    ? payload.reference_resolutions
    : [];
  if (references.length) {
    const refsHeading = document.createElement("h3");
    refsHeading.textContent = "Clickable exact identities";
    root.append(refsHeading);
  }
  for (const reference of references.slice(0, 64)) {
    const row = document.createElement("div");
    row.className = "evidence-popout-actions";
    const button = document.createElement("button");
    button.type = "button";
    const identity = text(reference?.evidence_identity, "");
    button.textContent = validSha256(identity)
      ? `${identity.slice(0, 12)}… · ${resolutionLabel(
          reference?.resolution_state
        )}`
      : "Geçersiz evidence identity";
    button.disabled = !validSha256(identity);
    const result = document.createElement("span");
    result.className = "proof-result";
    button.addEventListener("click", async () => {
      button.disabled = true;
      result.textContent = "Exact persisted nesne doğrulanıyor…";
      try {
        const response = await fetchJson(
          `/api/stream/messages/${encodeURIComponent(
            narrativeIdentity
          )}/evidence/${encodeURIComponent(identity)}`
        );
        const found = response?.reference || {};
        const state = resolutionLabel(found?.resolution_state);
        result.textContent =
          state === "READY_EXACT"
            ? `READY_EXACT · ${text(found?.object_kind, "persisted object")}`
            : state === "IDENTITY_ONLY_EXACT"
              ? "IDENTITY_ONLY_EXACT · kimlik kesin, bağlı exact nesne resolver'ı yok."
              : "UNAVAILABLE_EXPLICIT · bu mesaj bu kimliği exact kanıt olarak bağlamıyor.";
      } catch {
        result.textContent =
          "Exact evidence isteği başarısız; current data ile ikame yapılmadı.";
      } finally {
        button.disabled = false;
      }
    });
    row.append(button, result);
    root.append(row);
  }
  if (references.length > 64) {
    const note = document.createElement("p");
    note.textContent = `${references.length - 64} ek exact identity manifestte kayıtlı; pencere performansı için burada daraltıldı.`;
    root.append(note);
  }
  return root;
}

async function renderDetachedExactEvidence() {
  if (!content) return;
  let exactEvidence;
  try {
    const payload = await fetchJson(
      `/api/stream/messages/${encodeURIComponent(
        narrativeIdentity
      )}/evidence`
    );
    exactEvidence =
      payload?.evidence && typeof payload.evidence === "object"
        ? payload.evidence
        : null;
  } catch {
    exactEvidence = null;
  }
  content.querySelector(".f6-exact-evidence-manifest")?.remove();
  if (!exactEvidence) {
    const unavailable = document.createElement("section");
    unavailable.className = "evidence-popout-section f6-exact-evidence-manifest";
    const h = document.createElement("h2");
    h.textContent = "Exact Frozen Evidence · F6";
    const p = document.createElement("p");
    p.textContent =
      "UNAVAILABLE_EXPLICIT · exact evidence manifest okunamadı; current data ile kanıt üretilmedi.";
    unavailable.append(h, p);
    content.append(unavailable);
    return;
  }
  content.append(renderExactEvidenceManifest(exactEvidence));
}

async function renderDetachedFamilyExactProof(detail) {
  if (!content) return;
  const config = KIND_CONFIG[kind];
  if (!config?.family) return;
  const renderer = window.CryptoSignalVisualProof?.renderFamilyExactEvidence;
  if (typeof renderer !== "function") return;

  let exactEvidence;
  try {
    const payload = await fetchJson(
      `/api/stream/messages/${encodeURIComponent(narrativeIdentity)}/evidence`
    );
    exactEvidence =
      payload?.evidence && typeof payload.evidence === "object"
        ? payload.evidence
        : null;
  } catch {
    exactEvidence = null;
  }

  content.querySelector(".frozen-visual-proof")?.remove();
  if (!exactEvidence) {
    const unavailable = document.createElement("section");
    unavailable.className = "frozen-visual-proof family-frozen-proof";
    unavailable.dataset.familyKind = kind;
    unavailable.dataset.resolutionState = "UNAVAILABLE_EXPLICIT";
    unavailable.textContent =
      "UNAVAILABLE_EXPLICIT · exact family source payload okunamadı; current data ile kanıt üretilmedi.";
    content.prepend(unavailable);
    return;
  }

  content.prepend(
    renderer(exactEvidence, {
      kind,
      contribution: familyContribution(detail?.fact_bundle || {}, config),
    })
  );
}

async function renderDetachedFrozenVisualProof(detail) {
  if (!content) return;
  const config = KIND_CONFIG[kind];
  const isFamily = Boolean(config?.family);
  if (!isFamily && kind !== "proof") return;

  const fullRenderer = window.CryptoSignalVisualProof?.renderFrozenVisualProof;
  const familyRenderer = window.CryptoSignalVisualProof?.renderFamilyFrozenProof;
  if (kind === "proof" && typeof fullRenderer !== "function") return;
  if (isFamily && typeof familyRenderer !== "function") return;

  let visualProof;
  try {
    const payload = await fetchJson(
      `/api/stream/messages/${encodeURIComponent(narrativeIdentity)}/visual-proof`
    );
    visualProof =
      payload?.visual_proof && typeof payload.visual_proof === "object"
        ? payload.visual_proof
        : {
            status: payload?.status || "unavailable",
            reason: payload?.reason || "exact_visual_proof_unavailable",
            narrative_identity: narrativeIdentity,
          };
  } catch {
    visualProof = {
      status: "unavailable",
      reason: "visual_proof_request_failed",
      narrative_identity: narrativeIdentity,
    };
  }
  content.querySelector(".frozen-visual-proof")?.remove();
  if (isFamily) {
    content.prepend(
      familyRenderer(visualProof, {
        kind,
        contribution: familyContribution(detail?.fact_bundle || {}, config),
      })
    );
  } else {
    content.prepend(fullRenderer(visualProof));
  }
}

async function init() {
  const config = KIND_CONFIG[kind];
  if (!validSha256(narrativeIdentity) || !config) {
    if (title) title.textContent = "Geçersiz kanıt penceresi";
    if (identity) identity.textContent = "Exact narrative identity veya pencere türü geçersiz.";
    if (content) {
      content.replaceChildren();
      const error = document.createElement("div");
      error.className = "evidence-error";
      error.textContent = "Bu pencere exact persisted mesaj kimliği olmadan kanıt göstermez.";
      content.append(error);
    }
    return;
  }

  document.body.dataset.windowKind = kind;
  document.body.dataset.narrativeIdentity = narrativeIdentity;
  if (title) title.textContent = config.label;
  if (identity) identity.textContent = narrativeIdentity;

  try {
    const payload = await fetchJson(
      `/api/stream/messages/${encodeURIComponent(narrativeIdentity)}/detail`
    );
    if (payload.status !== "ready" || !payload.detail) {
      throw new Error("detail unavailable");
    }
    if (content) content.replaceChildren();
    renderCore(config, payload.detail);
    if (config.family) {
      await renderDetachedFamilyExactProof(payload.detail);
    } else {
      await renderDetachedExactEvidence();
      await renderDetachedFrozenVisualProof(payload.detail);
    }
  } catch {
    if (content) {
      content.replaceChildren();
      const error = document.createElement("div");
      error.className = "evidence-error";
      error.textContent = "Exact persisted message detail okunamadı; pencere veri uydurmadı.";
      content.append(error);
    }
  }
}

void init();
