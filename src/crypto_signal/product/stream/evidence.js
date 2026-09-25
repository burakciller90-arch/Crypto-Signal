"use strict";

const params = new URLSearchParams(window.location.search);
const narrativeIdentity = params.get("narrative") || "";
const kind = params.get("kind") || "";

const KIND_CONFIG = Object.freeze({
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

function familyContribution(fact, family) {
  const items = Array.isArray(fact?.family_contributions) ? fact.family_contributions : [];
  return items.find((item) => item && item.family === family) || null;
}

function exactWhy(config, detail) {
  const fact = detail?.fact_bundle || {};
  const analytical = detail?.analytical_view || {};
  if (config.family) {
    const contribution = familyContribution(fact, config.family);
    if (!contribution) return "Bu mesajda bu aile için persisted katkı bulunmuyor.";
    return `Bu mesajda destek ${number(contribution.support_points, "0")}, karşıt ${number(
      contribution.opposition_points,
      "0"
    )}. Pencere yalnız bu exact message snapshot içindeki katkıyı gösterir.`;
  }
  if (kind === "geometry") {
    return `Tetik ${number(fact?.trigger_zone?.low)}–${number(
      fact?.trigger_zone?.high
    )}; geçersizleşme ${number(fact?.invalidation_price)}. Bu seviyeler mesaj yayınlandığı andaki persisted geometridir.`;
  }
  if (kind === "decision") {
    return `Effective stance: ${text(analytical?.stance?.effective_stance)}; sonraki koşul: ${text(
      analytical?.next_condition?.state
    )}. Pencere bu kararın exact lineage'ını korur.`;
  }
  if (kind === "capital") {
    return `Capital consequence: ${text(
      analytical?.capital_consequence?.state,
      "not_bound"
    )}. REAL_CAPITAL=0; bu yalnız sanal/analitik sermaye bağlamıdır.`;
  }
  if (kind === "event_risk") {
    return `Event context: ${text(fact?.event_context_state)}. Bu durum kararın event-risk bağlamını gösterir; yeni haber yorumu üretmez.`;
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
    const contribution = familyContribution(fact, config.family);
    if (contribution) {
      content.append(
        section(
          "Persisted aile katkısı",
          `Destek +${number(contribution.support_points, "0")} / karşıt -${number(
            contribution.opposition_points,
            "0"
          )} · durum ${text(contribution.state)} · yön ${text(contribution.direction)}`
        )
      );
      const refs = Array.isArray(contribution.source_evidence_identities)
        ? contribution.source_evidence_identities
        : [];
      const refsSection = section(
        "Exact source evidence identities",
        refs.length ? `${refs.length} kaynak identity bağlı.` : "Bu aile için source evidence identity listesi yok."
      );
      for (const ref of refs) {
        const code = document.createElement("code");
        code.textContent = ref;
        refsSection.append(code);
      }
      content.append(refsSection);
    } else {
      content.append(section("Persisted aile katkısı", "Bu exact mesajda bu aile için katkı kaydı yok."));
    }
  } else if (kind === "geometry") {
    content.append(
      section(
        "Trade geometry",
        `Tetik ${number(fact?.trigger_zone?.low)}–${number(
          fact?.trigger_zone?.high
        )} · hedef ${number(fact?.target_zone?.low)}–${number(
          fact?.target_zone?.high
        )} · geçersizleşme ${number(fact?.invalidation_price)}`
      )
    );
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
      "S9 bu pencereyi ve exact identity bağını sağlar. Frozen visual coordinates ve çizimler S10 kapsamıdır."
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
