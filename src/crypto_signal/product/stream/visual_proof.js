"use strict";

(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";

  const FAMILY_PROOF_CONFIG = Object.freeze({
    geometry: Object.freeze({
      label: "Geometri",
      aliases: Object.freeze(["geometry", "geometry_pa_elliott_harmonic"]),
      domains: Object.freeze(["geometry", "frozen_chart", "consumed_candles"]),
      visual: true,
    }),
    liquidity: Object.freeze({
      label: "Likidite",
      aliases: Object.freeze(["liquidity"]),
      domains: Object.freeze(["liquidity", "order_book", "liquidity_map", "liquidation_map"]),
      visual: false,
    }),
    order_flow: Object.freeze({
      label: "Emir Akışı",
      aliases: Object.freeze(["order_flow", "order_flow_absorption"]),
      domains: Object.freeze(["order_flow", "order_book", "public_trades", "order_flow_cvd"]),
      visual: false,
    }),
    derivatives: Object.freeze({
      label: "Türevler",
      aliases: Object.freeze(["derivatives"]),
      domains: Object.freeze(["derivatives"]),
      visual: false,
    }),
    onchain: Object.freeze({
      label: "On-chain",
      aliases: Object.freeze(["onchain", "onchain_smart_money"]),
      domains: Object.freeze(["onchain"]),
      visual: false,
    }),
  });

  function text(value, fallback = "—") {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  }

  function number(value, fallback = null) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function formatNumber(value, fallback = "—") {
    const parsed = number(value);
    if (parsed === null) return fallback;
    return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 }).format(parsed);
  }

  function formatTime(value) {
    const parsed = number(value);
    if (parsed === null) return "—";
    try {
      return new Intl.DateTimeFormat("tr-TR", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(parsed));
    } catch {
      return "—";
    }
  }

  function svgElement(name, attrs = {}) {
    const node = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attrs)) {
      node.setAttribute(key, String(value));
    }
    return node;
  }

  function proofSection(label, body = "") {
    const section = document.createElement("section");
    section.className = "frozen-proof-section";
    const heading = document.createElement("h5");
    heading.textContent = label;
    const paragraph = document.createElement("p");
    paragraph.textContent = text(body);
    section.append(heading, paragraph);
    return section;
  }

  function priceExtent(candles, annotations) {
    const prices = [];
    for (const candle of candles) {
      for (const key of ["open", "high", "low", "close"]) {
        const value = number(candle?.[key]);
        if (value !== null) prices.push(value);
      }
    }
    for (const annotation of annotations) {
      for (const key of ["low", "high", "price"]) {
        const value = number(annotation?.[key]);
        if (value !== null) prices.push(value);
      }
    }
    if (!prices.length) return [0, 1];
    let low = Math.min(...prices);
    let high = Math.max(...prices);
    if (high <= low) high = low + 1;
    const pad = Math.max((high - low) * 0.08, high * 0.002);
    low -= pad;
    high += pad;
    return [low, high];
  }

  function renderChart(payload) {
    const candles = Array.isArray(payload?.candles) ? payload.candles : [];
    const annotations = Array.isArray(payload?.annotations) ? payload.annotations : [];
    const shell = document.createElement("div");
    shell.className = "frozen-proof-chart-shell";

    if (!candles.length) {
      const empty = document.createElement("div");
      empty.className = "frozen-proof-unavailable";
      empty.textContent = "Dondurulmuş OHLC payload bulunamadı; current data ile yeniden üretilmedi.";
      shell.append(empty);
      return shell;
    }

    const width = 900;
    const height = 420;
    const left = 62;
    const right = 20;
    const top = 24;
    const bottom = 42;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const [minPrice, maxPrice] = priceExtent(candles, annotations);
    const y = (price) => top + ((maxPrice - price) / (maxPrice - minPrice)) * plotHeight;
    const step = plotWidth / Math.max(candles.length, 1);
    const bodyWidth = Math.max(3, Math.min(14, step * 0.55));

    const svg = svgElement("svg", {
      class: "frozen-proof-chart",
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": "Karar anında dondurulmuş OHLC ve exact kanıt işaretleri",
      preserveAspectRatio: "xMidYMid meet",
    });

    const grid = svgElement("g", { class: "proof-chart-grid" });
    for (let index = 0; index <= 4; index += 1) {
      const yy = top + (plotHeight / 4) * index;
      const line = svgElement("line", {
        x1: left,
        x2: width - right,
        y1: yy,
        y2: yy,
      });
      grid.append(line);
      const price = maxPrice - ((maxPrice - minPrice) / 4) * index;
      const label = svgElement("text", {
        x: left - 9,
        y: yy + 4,
        "text-anchor": "end",
      });
      label.textContent = formatNumber(price);
      grid.append(label);
    }
    svg.append(grid);

    const entry = annotations.find((item) => item?.kind === "entry_zone");
    if (entry) {
      const low = number(entry.low);
      const high = number(entry.high);
      if (low !== null && high !== null) {
        const yHigh = y(Math.max(low, high));
        const yLow = y(Math.min(low, high));
        const zone = svgElement("rect", {
          class: "proof-entry-zone",
          x: left,
          y: yHigh,
          width: plotWidth,
          height: Math.max(1, yLow - yHigh),
          "data-annotation-identity": text(entry.annotation_identity, ""),
        });
        svg.append(zone);
      }
    }

    const candleGroup = svgElement("g", { class: "proof-candles" });
    candles.forEach((candle, index) => {
      const open = number(candle.open);
      const high = number(candle.high);
      const low = number(candle.low);
      const close = number(candle.close);
      if ([open, high, low, close].some((value) => value === null)) return;
      const x = left + step * index + step / 2;
      const up = close >= open;
      const identity = Array.isArray(candle.candle_identity)
        ? candle.candle_identity.join(":")
        : text(candle.candle_identity, "");
      const group = svgElement("g", {
        class: `proof-candle ${up ? "is-up" : "is-down"}`,
        "data-candle-identity": identity,
      });
      group.append(
        svgElement("line", {
          class: "proof-candle-wick",
          x1: x,
          x2: x,
          y1: y(high),
          y2: y(low),
        })
      );
      const bodyTop = Math.min(y(open), y(close));
      const bodyHeight = Math.max(2, Math.abs(y(open) - y(close)));
      group.append(
        svgElement("rect", {
          class: "proof-candle-body",
          x: x - bodyWidth / 2,
          y: bodyTop,
          width: bodyWidth,
          height: bodyHeight,
          rx: 1.5,
        })
      );
      candleGroup.append(group);
    });
    svg.append(candleGroup);

    const markGroup = svgElement("g", { class: "proof-annotations" });
    for (const annotation of annotations) {
      if (annotation?.kind === "entry_zone") continue;
      const price = number(annotation?.price);
      if (price === null) continue;
      const group = svgElement("g", {
        class: `proof-annotation proof-annotation-${text(annotation.kind, "mark")}`,
        "data-annotation-identity": text(annotation.annotation_identity, ""),
        "data-source-evidence-identity": text(annotation.source_evidence_identity, ""),
      });
      const line = svgElement("line", {
        x1: left,
        x2: width - right,
        y1: y(price),
        y2: y(price),
      });
      const label = svgElement("text", {
        x: width - right - 5,
        y: y(price) - 5,
        "text-anchor": "end",
      });
      label.textContent = `${text(annotation.label, annotation.kind)} · ${formatNumber(price)}`;
      group.append(line, label);
      markGroup.append(group);
    }
    svg.append(markGroup);

    const axis = svgElement("g", { class: "proof-chart-axis" });
    const firstTime = candles[0]?.open_time_ms;
    const lastTime = candles[candles.length - 1]?.open_time_ms;
    const leftLabel = svgElement("text", {
      x: left,
      y: height - 14,
      "text-anchor": "start",
    });
    leftLabel.textContent = formatTime(firstTime);
    const rightLabel = svgElement("text", {
      x: width - right,
      y: height - 14,
      "text-anchor": "end",
    });
    rightLabel.textContent = formatTime(lastTime);
    axis.append(leftLabel, rightLabel);
    svg.append(axis);

    shell.append(svg);
    return shell;
  }

  function renderProvenance(payload) {
    const provenance = payload?.provenance || {};
    const lineage = payload?.lineage || {};
    const section = proofSection(
      "PROVENANCE",
      `Karar kaynağı: ${text(provenance.candle_source)} · source as-of ${formatTime(
        provenance.source_as_of_ms
      )} · freeze ${formatTime(provenance.frozen_at_ms)}. Current-data substitution: ${provenance.current_data_substitution === false ? "YOK" : "BİLİNMİYOR"}.`
    );
    const identities = document.createElement("div");
    identities.className = "frozen-proof-identities";
    for (const [label, value] of [
      ["message", lineage.narrative_identity],
      ["forecast", lineage.forecast_identity],
      ["proof", lineage.proof_identity],
      ["signal", lineage.signal_freeze_identity],
      ["bundle", lineage.decision_freeze_bundle_identity],
    ]) {
      if (!value) continue;
      const code = document.createElement("code");
      code.dataset.identityKind = label;
      code.textContent = `${label}: ${value}`;
      identities.append(code);
    }
    section.append(identities);
    return section;
  }

  function renderScoreComponents(payload) {
    const components = payload?.score_components || {};
    const families = Array.isArray(components.family_contributions)
      ? components.family_contributions
      : [];
    const section = proofSection(
      "SCORE COMPONENTS",
      `Confluence support ${formatNumber(
        components.confluence_support_score_0_100
      )} · opposition ${formatNumber(
        components.confluence_opposition_score_0_100
      )}. Bu skor olasılık değildir.`
    );
    const grid = document.createElement("div");
    grid.className = "frozen-proof-score-grid";
    for (const family of families) {
      const item = document.createElement("div");
      item.className = "frozen-proof-score";
      item.dataset.family = text(family?.family, "");
      const label = document.createElement("span");
      label.textContent = text(family?.family, "family").replaceAll("_", " ");
      const values = document.createElement("strong");
      values.textContent = `+${formatNumber(family?.support_points, "0")} / -${formatNumber(
        family?.opposition_points,
        "0"
      )}`;
      item.append(label, values);
      grid.append(item);
    }
    section.append(grid);
    return section;
  }

  function canonicalResolutionState(domain) {
    const explicit = text(domain?.resolution_state, "");
    if (
      ["READY_EXACT", "IDENTITY_ONLY_EXACT", "UNAVAILABLE_EXPLICIT"].includes(
        explicit
      )
    ) {
      return explicit;
    }
    const visual = text(domain?.visual_state, "unavailable");
    if (visual === "resolved_frozen_bundle") return "READY_EXACT";
    if (visual === "identity_only") return "IDENTITY_ONLY_EXACT";
    return "UNAVAILABLE_EXPLICIT";
  }

  function renderDomainManifest(payload, allowedDomains = null) {
    const allDomains = Array.isArray(payload?.domain_evidence) ? payload.domain_evidence : [];
    const allowed = Array.isArray(allowedDomains) ? new Set(allowedDomains) : null;
    const domains = allowed
      ? allDomains.filter((domain) => allowed.has(text(domain?.domain, "")))
      : allDomains;
    const section = proofSection(
      "EVIDENCE DOMAINS",
      "Görsel payload yalnız exact bound store varsa çizilir; identity-only kanıt current data ile yeniden kurulmaz."
    );
    const grid = document.createElement("div");
    grid.className = "frozen-proof-domain-grid";
    for (const domain of domains) {
      const item = document.createElement("div");
      item.className = "frozen-proof-domain";
      item.dataset.domain = text(domain?.domain, "");
      item.dataset.visualState = text(domain?.visual_state, "unavailable");
      item.dataset.resolutionState = canonicalResolutionState(domain);
      const head = document.createElement("div");
      const label = document.createElement("strong");
      label.textContent = text(domain?.domain, "domain").replaceAll("_", " ");
      const state = document.createElement("span");
      state.textContent = canonicalResolutionState(domain);
      head.append(label, state);
      const note = document.createElement("p");
      const resolutionState = canonicalResolutionState(domain);
      note.textContent =
        resolutionState === "READY_EXACT"
          ? "Exact immutable/persisted kanıt çözüldü."
          : resolutionState === "IDENTITY_ONLY_EXACT"
            ? "Exact evidence identity var; bound visual payload yok, çizim yapılmadı."
            : "UNAVAILABLE_EXPLICIT: exact görsel kanıt yok; current data ile ikame yapılmadı.";
      item.append(head, note);
      const identities = Array.isArray(domain?.evidence_identities)
        ? domain.evidence_identities
        : [];
      for (const identity of identities.slice(0, 3)) {
        const code = document.createElement("code");
        code.textContent = identity;
        item.append(code);
      }
      grid.append(item);
    }
    section.append(grid);
    return section;
  }

  function familyContributionForProof(payload, config, explicitContribution = null) {
    if (explicitContribution && typeof explicitContribution === "object") {
      return explicitContribution;
    }
    const families = Array.isArray(payload?.score_components?.family_contributions)
      ? payload.score_components.family_contributions
      : [];
    return families.find((item) =>
      config.aliases.includes(text(item?.family, "").toLowerCase())
    ) || null;
  }

  function familyProofResolution(payload, config, contribution) {
    const domains = Array.isArray(payload?.domain_evidence)
      ? payload.domain_evidence.filter((domain) =>
          config.domains.includes(text(domain?.domain, ""))
        )
      : [];
    const states = domains.map(canonicalResolutionState);
    if (
      config.visual
      && payload?.status === "ready"
      && states.includes("READY_EXACT")
    ) {
      return "READY_EXACT";
    }
    if (states.includes("READY_EXACT")) return "READY_EXACT";
    const refs = Array.isArray(contribution?.source_evidence_identities)
      ? contribution.source_evidence_identities
      : [];
    if (states.includes("IDENTITY_ONLY_EXACT") || refs.length) {
      return "IDENTITY_ONLY_EXACT";
    }
    return "UNAVAILABLE_EXPLICIT";
  }

  function familyProofIdentitySection(payload, config, contribution) {
    const section = proofSection(
      "EXACT KANIT KİMLİKLERİ",
      "Yalnız bu kanıt ailesine bağlı persisted kimlikler gösterilir."
    );
    const identities = new Set(
      Array.isArray(contribution?.source_evidence_identities)
        ? contribution.source_evidence_identities
        : []
    );
    const domains = Array.isArray(payload?.domain_evidence)
      ? payload.domain_evidence
      : [];
    for (const domain of domains) {
      if (!config.domains.includes(text(domain?.domain, ""))) continue;
      for (const identity of Array.isArray(domain?.evidence_identities)
        ? domain.evidence_identities
        : []) {
        identities.add(identity);
      }
    }
    if (!identities.size) {
      const note = document.createElement("p");
      note.textContent =
        "Bu aile için exact source identity yok; kanıt uydurulmadı.";
      section.append(note);
      return section;
    }
    const list = document.createElement("div");
    list.className = "frozen-proof-identities";
    for (const identity of [...identities].slice(0, 12)) {
      const code = document.createElement("code");
      code.textContent = identity;
      list.append(code);
    }
    section.append(list);
    return section;
  }

  function exactFamilyResolutions(payload, config) {
    const items = Array.isArray(payload?.resolutions) ? payload.resolutions : [];
    return items.filter((item) => config.domains.includes(text(item?.domain, "")));
  }

  function exactFamilyObjects(payload, config) {
    const objects = [];
    const seen = new Set();
    for (const resolution of exactFamilyResolutions(payload, config)) {
      const projection = resolution?.customer_projection || {};
      const candidates = Array.isArray(projection.exact_source_objects)
        ? projection.exact_source_objects
        : [];
      for (const candidate of candidates) {
        if (!candidate || typeof candidate !== "object") continue;
        const key = text(
          candidate.snapshot_identity || candidate.trade_identity ||
            candidate.observation_identity || candidate.signal_freeze_identity ||
            candidate.decision_freeze_bundle_identity,
          JSON.stringify(candidate)
        );
        if (seen.has(key)) continue;
        seen.add(key);
        objects.push(candidate);
      }
    }
    return objects.sort((left, right) =>
      number(right?.event_at_ms ?? right?.as_of_ms, 0) -
      number(left?.event_at_ms ?? left?.as_of_ms, 0)
    );
  }

  function exactFamilyComponents(payload, config) {
    for (const resolution of exactFamilyResolutions(payload, config)) {
      const components = resolution?.customer_projection?.state_components;
      if (components && typeof components === "object") return components;
    }
    return {};
  }

  function exactFamilyResolution(payload, config, contribution) {
    const states = exactFamilyResolutions(payload, config).map((item) =>
      text(item?.resolution_state, "UNAVAILABLE_EXPLICIT")
    );
    if (states.includes("READY_EXACT")) return "READY_EXACT";
    const refs = Array.isArray(contribution?.source_evidence_identities)
      ? contribution.source_evidence_identities
      : [];
    if (states.includes("IDENTITY_ONLY_EXACT") || refs.length) {
      return "IDENTITY_ONLY_EXACT";
    }
    return "UNAVAILABLE_EXPLICIT";
  }

  function renderExactOrderBook(objects) {
    const snapshot = objects.find((item) => Array.isArray(item?.bids) && Array.isArray(item?.asks));
    if (!snapshot) return null;
    const bids = snapshot.bids.slice(0, 8);
    const asks = snapshot.asks.slice(0, 8);
    const sizes = bids.concat(asks).map((item) => number(item?.size, 0));
    const maxSize = Math.max.apply(null, sizes.concat([1]));
    const section = proofSection(
      "DONDURULMUŞ EMİR TAHTASI",
      "Exact order-book snapshot · " + formatTime(snapshot.event_at_ms)
    );
    const book = document.createElement("div");
    book.className = "exact-orderbook";
    for (const pair of [["BID", bids], ["ASK", asks]]) {
      const side = pair[0];
      const levels = pair[1];
      const column = document.createElement("div");
      column.className = "exact-orderbook-side is-" + side.toLowerCase();
      const title = document.createElement("strong");
      title.textContent = side;
      column.append(title);
      for (const level of levels) {
        const row = document.createElement("div");
        row.className = "exact-orderbook-level";
        const price = document.createElement("span");
        price.textContent = formatNumber(level?.price);
        const barShell = document.createElement("span");
        barShell.className = "exact-orderbook-bar-shell";
        const bar = document.createElement("i");
        bar.className = "exact-orderbook-bar";
        bar.style.width = String(Math.max(2, number(level?.size, 0) / maxSize * 100)) + "%";
        barShell.append(bar);
        const size = document.createElement("span");
        size.textContent = formatNumber(level?.size);
        row.append(price, barShell, size);
        column.append(row);
      }
      book.append(column);
    }
    section.append(book);
    return section;
  }

  function renderExactOrderFlow(objects, components) {
    const trades = objects.filter((item) =>
      ["buy", "sell"].includes(text(item?.aggressor_side, "").toLowerCase())
    ).slice(0, 12);
    if (!trades.length && !Object.keys(components).length) return null;
    let buyNotional = 0;
    let sellNotional = 0;
    for (const trade of trades) {
      const notional = number(trade?.price, 0) * number(trade?.size, 0);
      if (text(trade?.aggressor_side, "").toLowerCase() === "buy") buyNotional += notional;
      else sellNotional += notional;
    }
    const section = proofSection(
      "DONDURULMUŞ EMİR AKIŞI",
      "Exact bağlı public-trade örneklemi. Bu görünüm CVD veya absorption iddiası üretmez."
    );
    const metrics = document.createElement("div");
    metrics.className = "exact-proof-metrics";
    for (const pair of [
      ["Book pressure", text(components.book_pressure)],
      ["Taker flow", text(components.taker_flow)],
      ["Alış notional", formatNumber(buyNotional)],
      ["Satış notional", formatNumber(sellNotional)]
    ]) {
      const item = document.createElement("div");
      const label = document.createElement("span");
      label.textContent = pair[0];
      const value = document.createElement("strong");
      value.textContent = pair[1];
      item.append(label, value);
      metrics.append(item);
    }
    section.append(metrics);
    return section;
  }

  function renderExactDerivatives(objects, components) {
    const observations = objects.filter((item) =>
      Object.prototype.hasOwnProperty.call(item, "funding_rate") ||
      Object.prototype.hasOwnProperty.call(item, "open_interest")
    );
    if (!observations.length && !Object.keys(components).length) return null;
    const latest = observations[0] || {};
    const section = proofSection(
      "DONDURULMUŞ TÜREV GÖZLEMİ",
      observations.length ? "Exact observation · " + formatTime(latest.event_at_ms) :
        "Exact derivatives source payload çözülemedi."
    );
    const metrics = document.createElement("div");
    metrics.className = "exact-proof-metrics";
    for (const pair of [
      ["Open Interest", latest.open_interest == null ? "—" : formatNumber(latest.open_interest)],
      ["Funding", latest.funding_rate == null ? "—" : formatNumber(latest.funding_rate)],
      ["Mark", latest.mark_price == null ? "—" : formatNumber(latest.mark_price)],
      ["Index", latest.index_price == null ? "—" : formatNumber(latest.index_price)],
      ["OI state", text(components.open_interest_state)],
      ["Funding state", text(components.funding_state)],
      ["Basis state", text(components.basis_state)]
    ]) {
      const item = document.createElement("div");
      const label = document.createElement("span");
      label.textContent = pair[0];
      const value = document.createElement("strong");
      value.textContent = pair[1];
      item.append(label, value);
      metrics.append(item);
    }
    section.append(metrics);
    return section;
  }

  function renderExactGeometry(objects) {
    const freeze = objects.find((item) => item?.bundle && Array.isArray(item.bundle.candles));
    if (!freeze || !freeze.bundle.candles.length) return null;
    const geometry = freeze.bundle?.signal_decision?.geometry || {};
    const annotations = [];
    if (geometry.entry_zone) annotations.push({
      kind: "entry_zone", label: "Tetik bölgesi",
      low: geometry.entry_zone.low, high: geometry.entry_zone.high
    });
    if (geometry.invalidation_price) annotations.push({
      kind: "invalidation", label: "Geçersizleşme", price: geometry.invalidation_price
    });
    for (const target of Array.isArray(geometry.targets) ? geometry.targets : []) {
      annotations.push({kind: "target", label: text(target?.label, "Hedef"), price: target?.target_price});
    }
    const section = proofSection("DONDURULMUŞ GEOMETRİ", "Exact signal freeze · " + formatTime(freeze.as_of_ms));
    section.append(renderChart({candles: freeze.bundle.candles, annotations}));
    return section;
  }

  function renderFamilyExactEvidence(payload, { kind, contribution = null } = {}) {
    const config = FAMILY_PROOF_CONFIG[kind];
    if (!config) return renderFrozenVisualProof(payload);
    const familyContribution = familyContributionForProof(payload, config, contribution);
    const resolution = exactFamilyResolution(payload, config, familyContribution);
    const root = document.createElement("article");
    root.className = "frozen-visual-proof family-frozen-proof exact-family-proof";
    root.dataset.visualProofStatus = resolution === "READY_EXACT" ? "ready" : "unavailable";
    root.dataset.familyKind = kind;
    root.dataset.resolutionState = resolution;
    root.dataset.narrativeIdentity = text(payload?.narrative_identity, "");
    const head = document.createElement("header");
    head.className = "frozen-proof-head";
    const copy = document.createElement("div");
    const eyebrow = document.createElement("span");
    eyebrow.textContent = "AİLEYE ÖZGÜ EXACT KANIT · POINT-IN-TIME";
    const title = document.createElement("strong");
    title.textContent = config.label + " · Frozen source proof";
    copy.append(eyebrow, title);
    const badge = document.createElement("span");
    badge.className = "frozen-proof-badge";
    badge.textContent = resolution;
    head.append(copy, badge);
    root.append(head);
    const objects = exactFamilyObjects(payload, config);
    const components = exactFamilyComponents(payload, config);
    let visual = null;
    if (kind === "geometry") visual = renderExactGeometry(objects);
    else if (kind === "liquidity") visual = renderExactOrderBook(objects);
    else if (kind === "order_flow") visual = renderExactOrderFlow(objects, components);
    else if (kind === "derivatives") visual = renderExactDerivatives(objects, components);
    if (visual) root.append(visual);
    else root.append(proofSection(
      "KANIT DURUMU",
      resolution === "IDENTITY_ONLY_EXACT"
        ? "Exact kimlik var; persisted source payload çözülemedi. Current data ile yeniden çizilmedi."
        : "Bu aile için exact source payload yok; kanıt uydurulmadı."
    ));
    const technical = document.createElement("details");
    technical.className = "frozen-proof-provenance-disclosure";
    const summary = document.createElement("summary");
    summary.textContent = "Provenance / teknik kimlikler";
    const ids = document.createElement("div");
    ids.className = "frozen-proof-identities";
    const identities = new Set(
      Array.isArray(familyContribution?.source_evidence_identities)
        ? familyContribution.source_evidence_identities
        : []
    );
    for (const resolutionItem of exactFamilyResolutions(payload, config)) {
      for (const identity of Array.isArray(resolutionItem?.evidence_identities)
        ? resolutionItem.evidence_identities
        : []) {
        identities.add(identity);
      }
    }
    for (const identity of [...identities].slice(0, 16)) {
      const code = document.createElement("code");
      code.textContent = identity;
      ids.append(code);
    }
    technical.append(summary, ids);
    root.append(technical);
    return root;
  }
  function renderFamilyFrozenProof(
    payload,
    { kind, contribution = null } = {}
  ) {
    const config = FAMILY_PROOF_CONFIG[kind];
    if (!config) return renderFrozenVisualProof(payload);

    const familyContribution = familyContributionForProof(
      payload,
      config,
      contribution
    );
    const resolution = familyProofResolution(
      payload,
      config,
      familyContribution
    );
    const root = document.createElement("article");
    root.className = "frozen-visual-proof family-frozen-proof";
    root.dataset.visualProofStatus = text(payload?.status, "unavailable");
    root.dataset.familyKind = kind;
    root.dataset.resolutionState = resolution;
    root.dataset.narrativeIdentity = text(payload?.narrative_identity, "");

    const head = document.createElement("header");
    head.className = "frozen-proof-head";
    const copy = document.createElement("div");
    const eyebrow = document.createElement("span");
    eyebrow.textContent = "AİLEYE ÖZGÜ KANIT · POINT-IN-TIME";
    const title = document.createElement("strong");
    title.textContent = `${config.label} · Exact kanıt`;
    copy.append(eyebrow, title);
    const badge = document.createElement("span");
    badge.className = "frozen-proof-badge";
    badge.textContent = resolution;
    head.append(copy, badge);
    root.append(head);

    const stateCopy =
      resolution === "READY_EXACT"
        ? "Bu aile için exact frozen görsel/persisted kanıt çözüldü."
        : resolution === "IDENTITY_ONLY_EXACT"
          ? "Exact kanıt kimliği var; bu aile için bound görsel payload yok. Current data ile çizim yapılmadı."
          : "Bu aile için exact görsel/identity kanıtı mevcut değil. Current data ile ikame yapılmadı.";
    root.append(proofSection("KANIT DURUMU", stateCopy));

    if (config.visual && resolution === "READY_EXACT") {
      root.append(renderChart(payload), renderProvenance(payload));
    }
    root.append(
      familyProofIdentitySection(payload, config, familyContribution),
      renderDomainManifest(payload, config.domains)
    );
    return root;
  }

  function renderFrozenVisualProof(payload) {
    const root = document.createElement("article");
    root.className = "frozen-visual-proof";
    root.dataset.visualProofStatus = text(payload?.status, "unavailable");
    root.dataset.narrativeIdentity = text(payload?.narrative_identity, "");

    const head = document.createElement("header");
    head.className = "frozen-proof-head";
    const copy = document.createElement("div");
    const eyebrow = document.createElement("span");
    eyebrow.textContent = "DONDURULMUŞ KANIT · POINT-IN-TIME";
    const title = document.createElement("strong");
    title.textContent = `${text(payload?.symbol, "PİYASA")} · ${text(
      payload?.timeframe
    )} · Frozen Visual Proof`;
    copy.append(eyebrow, title);
    const badge = document.createElement("span");
    badge.className = "frozen-proof-badge";
    badge.textContent =
      text(
        payload?.resolution_state,
        payload?.status === "ready" ? "READY_EXACT" : "UNAVAILABLE_EXPLICIT"
      );
    head.append(copy, badge);
    root.append(head);

    if (payload?.status !== "ready") {
      const unavailable = document.createElement("div");
      unavailable.className = "frozen-proof-unavailable";
      unavailable.textContent = `Frozen visual proof hazır değil: ${text(
        payload?.reason,
        "exact persisted visual payload unavailable"
      )}. Current data ile yerine konmadı.`;
      root.append(unavailable);
      if (Array.isArray(payload?.domain_evidence)) {
        root.append(renderDomainManifest(payload));
      }
      return root;
    }

    root.append(
      renderChart(payload),
      renderProvenance(payload),
      renderScoreComponents(payload),
      renderDomainManifest(payload)
    );
    return root;
  }

  function fixtureVisualProof({
    narrativeIdentity,
    symbol,
    timeframe,
    forecastIdentity,
    proofIdentity,
  }) {
    const candles = [];
    let close = 62000;
    for (let index = 0; index < 28; index += 1) {
      const wave = ((index % 7) - 3) * 70;
      const open = close;
      close = open + (index % 3 === 0 ? 180 : index % 3 === 1 ? -90 : 125) + wave;
      const high = Math.max(open, close) + 180 + (index % 4) * 24;
      const low = Math.min(open, close) - 160 - (index % 5) * 18;
      const openTime = 1_790_000_000_000 + index * 14_400_000;
      candles.push({
        candle_identity: ["binance", "spot", symbol, timeframe, openTime],
        open_time_ms: openTime,
        close_time_ms: openTime + 14_399_999,
        open: String(open),
        high: String(high),
        low: String(low),
        close: String(close),
        volume: String(10 + index),
        source: "fixture",
        source_timestamp_ms: openTime + 14_399_900,
        ingested_at_ms: openTime + 14_399_950,
      });
    }
    const identity = (suffix) => String(suffix).padStart(64, "0");
    return {
      schema_version: "intelligence-stream-visual-proof-v1/1",
      status: "ready",
      resolution_state: "READY_EXACT",
      visual_kind: "frozen_ohlc",
      narrative_identity: narrativeIdentity,
      symbol,
      timeframe,
      lineage: {
        narrative_identity: narrativeIdentity,
        forecast_identity: forecastIdentity,
        proof_identity: proofIdentity,
        signal_freeze_identity: identity(910),
        decision_freeze_bundle_identity: identity(911),
      },
      provenance: {
        source_as_of_ms: candles[candles.length - 1].close_time_ms,
        issued_at_ms: candles[candles.length - 1].close_time_ms + 1,
        frozen_at_ms: candles[candles.length - 1].close_time_ms + 2,
        source_cutoff_open_time_ms: candles[candles.length - 1].open_time_ms,
        candle_source: "explicit_visual_test_fixture",
        current_data_substitution: false,
        exact_persisted: false,
      },
      candles,
      annotations: [
        {
          annotation_identity: identity(920),
          kind: "entry_zone",
          label: "Tetik bölgesi",
          low: "62000",
          high: "62500",
          source_evidence_identity: identity(930),
          source_methodology: "price_action",
        },
        {
          annotation_identity: identity(921),
          kind: "invalidation",
          label: "Geçersizleşme",
          price: "60750",
          source_evidence_identity: identity(930),
          source_methodology: "price_action",
        },
        {
          annotation_identity: identity(922),
          kind: "target",
          label: "target_1",
          price: "65000",
          source_evidence_identity: identity(930),
          source_methodology: "price_action",
        },
        {
          annotation_identity: identity(923),
          kind: "target",
          label: "target_2",
          price: "66000",
          source_evidence_identity: identity(930),
          source_methodology: "price_action",
        },
      ],
      score_components: {
        confluence_support_score_0_100: 74,
        confluence_opposition_score_0_100: 19,
        family_contributions: [
          ["geometry", 78, 8],
          ["liquidity", 71, 13],
          ["order_flow", 65, 18],
          ["derivatives", 44, 31],
          ["onchain", 36, 22],
        ].map(([family, support, opposition], index) => ({
          family,
          support_points: support,
          opposition_points: opposition,
          source_evidence_identities:
            family === "onchain" ? [] : [identity(970 + index)],
        })),
      },
      domain_evidence: [
        ["frozen_chart", "resolved_frozen_bundle", identity(940)],
        ["consumed_candles", "resolved_frozen_bundle", identity(941)],
        ["order_book", "identity_only", identity(942)],
        ["liquidity_map", "identity_only", identity(943)],
        ["order_flow_cvd", "identity_only", identity(944)],
        ["derivatives", "identity_only", identity(945)],
        ["liquidation_map", "identity_only", identity(946)],
        ["onchain", "unavailable", null],
      ].map(([domain, visual_state, evidenceIdentity], index) => ({
        slice_identity: identity(950 + index),
        domain,
        availability: visual_state === "unavailable" ? "insufficient" : "available",
        verdict: visual_state === "unavailable" ? "insufficient" : "neutral",
        evidence_identities: evidenceIdentity ? [evidenceIdentity] : [],
        visual_state,
        resolution_state:
          visual_state === "resolved_frozen_bundle"
            ? "READY_EXACT"
            : visual_state === "identity_only"
              ? "IDENTITY_ONLY_EXACT"
              : "UNAVAILABLE_EXPLICIT",
      })),
      read_only: true,
      production_authority: false,
      real_capital: 0,
      fixture: true,
    };
  }

  window.CryptoSignalVisualProof = Object.freeze({
    renderFrozenVisualProof,
    renderFamilyFrozenProof,
    renderFamilyExactEvidence,
    fixtureVisualProof,
  });
})();
