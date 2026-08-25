const RELEASE_VERSION = "2026-08-25-retailer-completion";
const DATA_FILES = {
  reviews: "data/stir_fry_reviews_normalized.json",
  analysis: "data/stir_fry_analysis.json",
  registry: "data/stir_fry_product_registry.json",
};

const TOPICS = {
  taste: "Taste / flavor",
  portion_value: "Portion / value",
  protein_quantity: "Protein quantity",
  vegetables: "Vegetables",
  texture: "Texture",
  convenience: "Convenience",
  dietary_fit: "Dietary fit",
  packaging: "Packaging",
};

const SOURCE_COLORS = {
  "Kevin's Natural Foods": "#0000A0",
  Target: "#EB6916",
  Kroger: "#19738D",
};

const state = {
  data: null,
  cohort: "all",
  products: new Set(),
  sources: new Set(),
  ratings: new Set([1, 2, 3, 4, 5]),
  topic: "all",
  excludeIncentive: false,
  excludeSponsored: false,
  search: "",
  sort: "newest",
  trendMetric: "rating",
  visible: 10,
  trendPoints: [],
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const pct = (value, digits = 0) => value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
const score = value => value == null ? "—" : Number(value).toFixed(2);
const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
const prettyDate = value => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${value}T12:00:00`));
const cohortLabel = value => value === "grocery" ? "Grocery kit" : "Costco-only";

function metrics(rows) {
  const n = rows.length;
  const topicCounts = Object.fromEntries(Object.keys(TOPICS).map(topic => [topic, rows.filter(row => row.topics.includes(topic)).length]));
  return {
    n,
    average: n ? rows.reduce((sum, row) => sum + row.rating, 0) / n : null,
    low: n ? rows.filter(row => row.rating <= 2).length / n : null,
    high: n ? rows.filter(row => row.rating >= 4).length / n : null,
    topicCounts,
    topicShares: Object.fromEntries(Object.entries(topicCounts).map(([topic, count]) => [topic, n ? count / n : null])),
  };
}

function productInCohort(productId) {
  if (state.cohort === "all") return true;
  return state.data.products.get(productId)?.cohort === state.cohort;
}

function filteredReviews({ ignoreProduct = false, forceFirstParty = false } = {}) {
  const query = state.search.trim().toLowerCase();
  return state.data.reviews.filter(row => {
    if (!productInCohort(row.product_id)) return false;
    if (!ignoreProduct && !state.products.has(row.product_id)) return false;
    if (forceFirstParty && row.source !== "Kevin's Natural Foods") return false;
    if (!forceFirstParty && !state.sources.has(row.source)) return false;
    if (!state.ratings.has(row.rating)) return false;
    if (state.topic !== "all" && !row.topics.includes(state.topic)) return false;
    if (state.excludeIncentive && row.incentive_disclosed) return false;
    if (state.excludeSponsored && row.sponsorship_disclosed) return false;
    if (query && !`${row.title} ${row.text} ${row.product} ${row.source}`.toLowerCase().includes(query)) return false;
    return true;
  });
}

async function loadData() {
  try {
    const [reviews, analysis, registry] = await Promise.all(Object.values(DATA_FILES).map(path => fetch(`${path}?v=${RELEASE_VERSION}`).then(response => {
      if (!response.ok) throw new Error(`Could not load ${path}`);
      return response.json();
    })));
    const products = new Map(registry.products.map(product => [product.product_id, product]));
    state.data = { reviews, analysis, registry, products };
    state.products = new Set(products.keys());
    state.sources = new Set(reviews.map(row => row.source));
    buildFilters();
    bindEvents();
    render();
    $("#loading").classList.add("hidden");
    setTimeout(() => $("#loading").remove(), 300);
  } catch (error) {
    $("#loading").innerHTML = `<p><strong>Dashboard data could not be loaded.</strong><br>${escapeHtml(error.message)}</p>`;
  }
}

function buildFilters() {
  const reviewCounts = new Map();
  state.data.reviews.forEach(row => reviewCounts.set(row.product_id, (reviewCounts.get(row.product_id) || 0) + 1));
  $("#productFilters").innerHTML = [...state.data.products.values()].map(product => `
    <label data-cohort="${product.cohort}">
      <input type="checkbox" name="product" value="${product.product_id}" checked>
      <span>${escapeHtml(product.product)}</span><small>${reviewCounts.get(product.product_id) || 0}</small>
    </label>`).join("");
  const sourceCounts = new Map();
  state.data.reviews.forEach(row => sourceCounts.set(row.source, (sourceCounts.get(row.source) || 0) + 1));
  $("#sourceFilters").innerHTML = [...sourceCounts.entries()].map(([source, count]) => `
    <label><input type="checkbox" name="source" value="${escapeHtml(source)}" checked><span>${escapeHtml(source === "Kevin's Natural Foods" ? "Owned site" : source)}</span><small>${count}</small></label>`).join("");
}

function bindEvents() {
  $("#cohortFilter").addEventListener("change", event => {
    state.cohort = event.target.value;
    syncProductVisibility();
    state.visible = 10;
    render();
  });
  $("#productFilters").addEventListener("change", event => {
    if (event.target.name !== "product") return;
    event.target.checked ? state.products.add(event.target.value) : state.products.delete(event.target.value);
    state.visible = 10;
    render();
  });
  $("#sourceFilters").addEventListener("change", event => {
    if (event.target.name !== "source") return;
    event.target.checked ? state.sources.add(event.target.value) : state.sources.delete(event.target.value);
    state.visible = 10;
    render();
  });
  $$("input[name='rating']").forEach(input => input.addEventListener("change", event => {
    const rating = Number(event.target.value);
    event.target.checked ? state.ratings.add(rating) : state.ratings.delete(rating);
    state.visible = 10;
    render();
  }));
  $("#topicFilter").addEventListener("change", event => { state.topic = event.target.value; state.visible = 10; render(); });
  $("#excludeIncentive").addEventListener("change", event => { state.excludeIncentive = event.target.checked; state.visible = 10; render(); });
  $("#excludeSponsored").addEventListener("change", event => { state.excludeSponsored = event.target.checked; state.visible = 10; render(); });
  $("#searchReviews").addEventListener("input", event => { state.search = event.target.value; state.visible = 10; render(); });
  $("#reviewSort").addEventListener("change", event => { state.sort = event.target.value; renderReviews(filteredReviews()); });
  $("#trendMetric").addEventListener("change", event => { state.trendMetric = event.target.value; renderTrend(); });
  $("#loadMore").addEventListener("click", () => { state.visible += 10; renderReviews(filteredReviews()); });
  $("#resetFilters").addEventListener("click", resetFilters);
  $("#exportCsv").addEventListener("click", exportCsv);
  $$("[data-select='products'], [data-select='sources']").forEach(button => button.addEventListener("click", () => {
    const key = button.dataset.select;
    if (key === "products") {
      state.products = new Set([...state.data.products.values()].filter(product => state.cohort === "all" || product.cohort === state.cohort).map(product => product.product_id));
      $$("#productFilters input").forEach(input => input.checked = state.products.has(input.value));
    } else {
      state.sources = new Set(state.data.reviews.map(row => row.source));
      $$("#sourceFilters input").forEach(input => input.checked = true);
    }
    render();
  }));
  $("#trendChart").addEventListener("mousemove", trendHover);
  $("#trendChart").addEventListener("mouseleave", () => $("#chartTooltip").hidden = true);
  let resizeFrame;
  window.addEventListener("resize", () => { cancelAnimationFrame(resizeFrame); resizeFrame = requestAnimationFrame(renderTrend); });
}

function syncProductVisibility() {
  $$("#productFilters label").forEach(label => {
    const visible = state.cohort === "all" || label.dataset.cohort === state.cohort;
    label.hidden = !visible;
    const input = $("input", label);
    if (visible) { input.checked = true; state.products.add(input.value); }
  });
}

function resetFilters() {
  state.cohort = "all";
  state.products = new Set(state.data.products.keys());
  state.sources = new Set(state.data.reviews.map(row => row.source));
  state.ratings = new Set([1, 2, 3, 4, 5]);
  state.topic = "all";
  state.excludeIncentive = false;
  state.excludeSponsored = false;
  state.search = "";
  state.visible = 10;
  $("#cohortFilter").value = "all";
  $("#topicFilter").value = "all";
  $("#excludeIncentive").checked = false;
  $("#excludeSponsored").checked = false;
  $("#searchReviews").value = "";
  $$("#productFilters label").forEach(label => { label.hidden = false; $("input", label).checked = true; });
  $$("#sourceFilters input, input[name='rating']").forEach(input => input.checked = true);
  render();
  toast("Filters reset");
}

function render() {
  const reviews = filteredReviews();
  const current = metrics(reviews);
  $("#viewCount").textContent = `${current.n.toLocaleString()} review${current.n === 1 ? "" : "s"}`;
  $("#kpiReviews").textContent = current.n.toLocaleString();
  $("#kpiRating").textContent = score(current.average);
  $("#kpiLow").textContent = pct(current.low, 1);
  $("#kpiLowNote").textContent = `${reviews.filter(row => row.rating <= 2).length} low-star written reviews`;
  $("#kpiPortion").textContent = pct(current.topicShares.portion_value, 1);
  $("#kpiConvenience").textContent = pct(current.topicShares.convenience, 1);
  renderDistribution(reviews);
  renderSourceMix(reviews);
  renderThemes(reviews);
  renderTrend();
  renderCohortComparison();
  renderProvocations();
  renderProducts(reviews);
  renderChannelSnapshots();
  renderCoverage();
  renderReviews(reviews);
}

function renderDistribution(reviews) {
  const counts = Object.fromEntries([1, 2, 3, 4, 5].map(star => [star, reviews.filter(row => row.rating === star).length]));
  const max = Math.max(1, ...Object.values(counts));
  $("#ratingDistribution").innerHTML = [5, 4, 3, 2, 1].map(star => `
    <div class="bar-row"><span>${star} star</span><div class="bar-track"><i style="width:${counts[star] / max * 100}%"></i></div><strong>${counts[star]}</strong></div>`).join("");
}

function renderSourceMix(reviews) {
  const counts = [...new Set(state.data.reviews.map(row => row.source))].map(source => ({ source, n: reviews.filter(row => row.source === source).length }));
  const total = Math.max(1, reviews.length);
  $("#sourceMix").innerHTML = `
    <div class="source-stack">${counts.map(item => `<i style="width:${item.n / total * 100}%;background:${SOURCE_COLORS[item.source] || "#19738D"}"></i>`).join("")}</div>
    <div class="source-legend">${counts.map(item => `<div><i style="background:${SOURCE_COLORS[item.source] || "#19738D"}"></i><span>${escapeHtml(item.source === "Kevin's Natural Foods" ? "Owned site" : item.source)}</span><strong>${item.n}</strong></div>`).join("")}</div>
    <p class="snapshot-distribution-note">${state.data.analysis.data_quality.cross_source_duplicates_removed} exact cross-posts were deduplicated in the full portfolio archive.</p>`;
}

function renderThemes(reviews) {
  const n = reviews.length;
  $("#themeBars").innerHTML = Object.entries(TOPICS).map(([topic, label]) => {
    const count = reviews.filter(row => row.topics.includes(topic)).length;
    const share = n ? count / n : 0;
    return `<article class="theme-card"><header><span>${label}</span><strong>${pct(share)}</strong></header><div class="theme-meter"><i style="width:${share * 100}%"></i></div><small>${count} review${count === 1 ? "" : "s"}</small></article>`;
  }).join("");
}

function monthRange(rows) {
  if (!rows.length) return [];
  const first = new Date(`${rows.reduce((min, row) => row.date < min ? row.date : min, rows[0].date).slice(0, 7)}-01T12:00:00`);
  const last = new Date("2026-08-01T12:00:00");
  const months = [];
  for (const cursor = new Date(first); cursor <= last; cursor.setMonth(cursor.getMonth() + 1)) months.push(cursor.toISOString().slice(0, 7));
  return months;
}

function renderTrend() {
  if (!state.data) return;
  const rows = filteredReviews({ forceFirstParty: true });
  const months = monthRange(rows);
  const grouped = months.map(month => {
    const current = rows.filter(row => row.date.startsWith(month));
    const stat = metrics(current);
    const value = state.trendMetric === "rating" ? stat.average
      : state.trendMetric === "low" ? stat.low
      : state.trendMetric === "portion_value" ? stat.topicShares.portion_value
      : stat.n;
    return { month, rows: current, n: current.length, value };
  });
  const labels = { rating: "Average rating", low: "1–2 star share", volume: "Review volume", portion_value: "Portion / value mention share" };
  $("#trendLegend").textContent = labels[state.trendMetric];
  $("#trendTable").textContent = grouped.filter(item => item.n).map(item => `${item.month}: n=${item.n}, ${labels[state.trendMetric]} ${item.value == null ? "not available" : item.value}`).join("; ");
  drawTrend(grouped);
}

function drawTrend(grouped) {
  const canvas = $("#trendChart");
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  const width = rect.width;
  const height = rect.height;
  const margin = { left: 42, right: 18, top: 18, bottom: 32 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const values = grouped.filter(item => item.value != null).map(item => item.value);
  const maxVolume = Math.max(1, ...values);
  const domain = state.trendMetric === "rating" ? [1, 5] : state.trendMetric === "volume" ? [0, maxVolume] : [0, 1];
  const y = value => margin.top + plotH - ((value - domain[0]) / Math.max(.0001, domain[1] - domain[0])) * plotH;
  const x = index => margin.left + (grouped.length <= 1 ? plotW / 2 : index / (grouped.length - 1) * plotW);
  ctx.clearRect(0, 0, width, height);
  ctx.font = "10px Arial";
  ctx.fillStyle = "#748189";
  ctx.strokeStyle = "#e3e7e9";
  ctx.lineWidth = 1;
  const ticks = state.trendMetric === "rating" ? [1, 2, 3, 4, 5] : state.trendMetric === "volume" ? [0, Math.ceil(maxVolume / 2), maxVolume] : [0, .25, .5, .75, 1];
  ticks.forEach(tick => {
    const py = y(tick);
    ctx.beginPath(); ctx.moveTo(margin.left, py); ctx.lineTo(width - margin.right, py); ctx.stroke();
    const label = state.trendMetric === "rating" || state.trendMetric === "volume" ? String(tick) : `${Math.round(tick * 100)}%`;
    ctx.fillText(label, 4, py + 3);
  });
  const launchIndex = grouped.findIndex(item => item.month === "2025-02");
  if (launchIndex >= 0) {
    ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = "#EB6916"; ctx.beginPath(); ctx.moveTo(x(launchIndex), margin.top); ctx.lineTo(x(launchIndex), margin.top + plotH); ctx.stroke(); ctx.restore();
  }
  ctx.strokeStyle = "#0000A0";
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  let started = false;
  const points = [];
  grouped.forEach((item, index) => {
    if (item.value == null) { started = false; return; }
    const point = { ...item, x: x(index), y: y(item.value) };
    points.push(point);
    if (!started) { ctx.moveTo(point.x, point.y); started = true; } else ctx.lineTo(point.x, point.y);
  });
  ctx.stroke();
  points.forEach(point => { ctx.beginPath(); ctx.arc(point.x, point.y, 3.2, 0, Math.PI * 2); ctx.fillStyle = point.n < 3 ? "#FFD131" : "#62BB46"; ctx.fill(); ctx.strokeStyle = "#0000A0"; ctx.lineWidth = 1.2; ctx.stroke(); });
  const every = Math.max(1, Math.ceil(grouped.length / 8));
  grouped.forEach((item, index) => {
    if (index % every && index !== grouped.length - 1) return;
    ctx.fillStyle = "#748189";
    ctx.textAlign = "center";
    ctx.fillText(new Intl.DateTimeFormat("en-US", { month: "short", year: "2-digit" }).format(new Date(`${item.month}-01T12:00:00`)), x(index), height - 8);
  });
  state.trendPoints = points;
}

function trendHover(event) {
  if (!state.trendPoints.length) return;
  const canvas = event.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const nearest = state.trendPoints.reduce((best, point) => Math.abs(point.x - mouseX) < Math.abs(best.x - mouseX) ? point : best);
  if (Math.abs(nearest.x - mouseX) > 22) { $("#chartTooltip").hidden = true; return; }
  const label = state.trendMetric === "rating" ? score(nearest.value)
    : state.trendMetric === "volume" ? nearest.value
    : pct(nearest.value, 1);
  const tooltip = $("#chartTooltip");
  tooltip.innerHTML = `<strong>${nearest.month}</strong>${label}<br><span>n=${nearest.n}</span>`;
  tooltip.style.left = `${nearest.x}px`;
  tooltip.style.top = `${nearest.y}px`;
  tooltip.hidden = false;
}

function periodMetrics(rows, start, end) {
  return metrics(rows.filter(row => row.date >= start && row.date <= end));
}

function comparisonCard(cohort, label, start, end) {
  const base = filteredReviews({ forceFirstParty: true }).filter(row => row.cohort === cohort);
  const launch = periodMetrics(base, start, end);
  const recent = periodMetrics(base, "2026-02-24", "2026-08-25");
  const delta = launch.average != null && recent.average != null ? recent.average - launch.average : null;
  const incentiveN = base.filter(row => row.date >= start && row.date <= end && row.incentive_disclosed).length;
  const caution = cohort === "costco_only"
    ? `${incentiveN} of ${launch.n} early-window reviews carry a future-purchase incentive disclosure; this is not a like-for-like baseline.`
    : "Directional only: both windows have small written-review bases. Validate against consumer care and operational data.";
  return `<article class="cohort-card">
    <header><div><span>${label}</span><strong>${cohort === "grocery" ? "National launch" : "Observed start"} vs latest six months</strong></div><span class="status-pill ${launch.n < 10 || recent.n < 10 ? "variant" : ""}">Directional</span></header>
    <div class="period-pair">
      <div><small>${prettyDate(start)} – ${prettyDate(end)}</small><strong>${score(launch.average)}</strong><span>n=${launch.n} · ${pct(launch.low)} low-star</span></div>
      <b aria-hidden="true">→</b>
      <div><small>Feb 24 – Aug 25, 2026</small><strong>${score(recent.average)}</strong><span>n=${recent.n} · ${pct(recent.low)} low-star</span></div>
    </div>
    <p class="period-delta ${delta != null && delta < 0 ? "delta-negative" : "delta-positive"}">${delta == null ? "Change not available" : `${delta >= 0 ? "+" : ""}${delta.toFixed(2)} rating-point change`}</p>
    <p class="cohort-caution">${caution}</p>
  </article>`;
}

function renderCohortComparison() {
  const cards = [];
  if (state.cohort === "all" || state.cohort === "grocery") cards.push(comparisonCard("grocery", "6 grocery kits", "2025-02-27", "2025-08-28"));
  if (state.cohort === "all" || state.cohort === "costco_only") cards.push(comparisonCard("costco_only", "7 Costco-only items", "2023-04-27", "2023-10-26"));
  $("#cohortComparison").innerHTML = cards.join("");
}

function renderProvocations() {
  $("#provocationGrid").innerHTML = state.data.analysis.provocations.map((item, index) => `<article><span>0${index + 1}</span><div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.evidence)}</p><small>${escapeHtml(item.implication)}</small></div></article>`).join("");
}

function renderProducts(reviews) {
  const rows = [...state.data.products.values()].filter(product => productInCohort(product.product_id) && state.products.has(product.product_id));
  $("#stirProductTable tbody").innerHTML = rows.map(product => {
    const productRows = reviews.filter(row => row.product_id === product.product_id);
    const stat = metrics(productRows);
    const recent = metrics(productRows.filter(row => row.date >= "2026-02-24"));
    const primary = Object.entries(stat.topicCounts).sort((a, b) => b[1] - a[1])[0];
    const evidence = stat.n === 0 ? ["No written evidence", "gap"] : stat.n < 5 ? ["Thin base", "variant"] : ["Captured", ""];
    return `<tr tabindex="0" data-product="${product.product_id}">
      <td class="product-name"><a href="${escapeHtml(product.official_url)}" target="_blank" rel="noopener">${escapeHtml(product.product)}</a></td>
      <td>${cohortLabel(product.cohort)}</td><td>${stat.n}</td><td>${score(stat.average)}</td><td>${pct(stat.low)}</td><td>${recent.n}</td><td>${score(recent.average)}</td>
      <td>${primary && primary[1] ? `${escapeHtml(TOPICS[primary[0]])} (${primary[1]})` : "—"}</td><td><span class="status-pill ${evidence[1]}">${evidence[0]}</span></td></tr>`;
  }).join("");
  $$("#stirProductTable tbody tr").forEach(row => {
    const focus = () => { state.products = new Set([row.dataset.product]); $$("#productFilters input").forEach(input => input.checked = input.value === row.dataset.product); render(); window.scrollTo({ top: 0, behavior: "smooth" }); };
    row.addEventListener("click", event => { if (event.target.tagName !== "A") focus(); });
    row.addEventListener("keydown", event => { if (event.key === "Enter") focus(); });
  });
}

function renderChannelSnapshots() {
  const selected = state.data.analysis.rating_snapshots.filter(snapshot => state.products.has(snapshot.product_id) && productInCohort(snapshot.product_id));
  const selectedCoverage = state.data.analysis.coverage.filter(row => state.products.has(row.product_id) && productInCohort(row.product_id));
  const sources = ["Kevin's Natural Foods", "Target", "Kroger", "Amazon"];
  $("#channelSnapshots").innerHTML = sources.map(source => {
    const rows = selected.filter(snapshot => snapshot.source === source);
    if (source === "Amazon") {
      const coverage = selectedCoverage.filter(row => row.source === source);
      const searched = coverage.filter(row => row.status === "searched_no_exact_page").length;
      const notApplicable = coverage.filter(row => row.status === "not_applicable").length;
      const message = searched
        ? `${searched} applicable product${searched === 1 ? "" : "s"} searched; adjacent sauces and Heat & Eat items were excluded.`
        : `${notApplicable} Costco-only product${notApplicable === 1 ? "" : "s"} outside Amazon scope.`;
      return `<article class="snapshot-card stir-snapshot"><header><span>Amazon</span><strong>Exact-SKU assessment</strong></header><div class="snapshot-score"><strong>No exact scoped SKU</strong><span>Not recorded as zero reviews</span></div><p>${message}</p></article>`;
    }
    const count = rows.reduce((sum, row) => sum + Number(row.rating_count || 0), 0);
    const weighted = count ? rows.reduce((sum, row) => sum + Number(row.average_rating || 0) * Number(row.rating_count || 0), 0) / count : null;
    const distribution = Object.fromEntries([1, 2, 3, 4, 5].map(star => [star, rows.reduce((sum, row) => sum + Number(row.distribution?.[star] || 0), 0)]));
    const distTotal = Object.values(distribution).reduce((sum, n) => sum + n, 0);
    const low = distTotal ? (distribution[1] + distribution[2]) / distTotal : null;
    return `<article class="snapshot-card stir-snapshot"><header><span>${source === "Kevin's Natural Foods" ? "Owned site" : source}</span><strong>${rows.length} exact product page${rows.length === 1 ? "" : "s"}</strong></header><div class="snapshot-score"><strong>${score(weighted)}</strong><span>${count.toLocaleString()} rating observation${count === 1 ? "" : "s"}</span></div><p>${low == null ? "Star distribution not exposed for this channel." : `${pct(low, 1)} are 1–2 star observations.`}<br>May include syndicated or overlapping ratings.</p></article>`;
  }).join("");
}

function coverageCell(row) {
  if (!row) return `<span class="coverage-pill gap">Not assessed</span>`;
  const status = row.status;
  const href = row.page_url ? ` href="${escapeHtml(row.page_url)}" target="_blank" rel="noopener"` : "";
  if (status === "review_history_complete") return `<a class="coverage-pill"${href}>Complete written history</a>`;
  if (status === "rating_evidence") return `<a class="coverage-pill"${href}>Ratings observed</a>`;
  if (status === "listing_no_public_reviews") return `<a class="coverage-pill variant"${href}>Exact listing · no review surface</a>`;
  if (status === "official_costco_sku_page_not_indexed") return `<a class="coverage-pill variant"${href}>Costco-only · retailer page not indexed</a>`;
  if (status === "not_applicable") return `<span class="coverage-pill gap">Not applicable</span>`;
  if (status === "searched_no_exact_page") return `<span class="coverage-pill gap">Searched · no exact SKU</span>`;
  return `<span class="coverage-pill gap">Not assessed</span>`;
}

function renderCoverage() {
  const sources = ["Costco", "Target", "Kroger", "Publix", "Albertsons", "Food Lion", "Amazon"];
  const coverage = state.data.analysis.coverage;
  const products = [...state.data.products.values()].filter(product => productInCohort(product.product_id) && state.products.has(product.product_id));
  $("#stirCoverageTable tbody").innerHTML = products.map(product => {
    const cells = sources.map(source => `<td>${coverageCell(coverage.find(row => row.product_id === product.product_id && row.source === source))}</td>`).join("");
    return `<tr><th scope="row">${escapeHtml(product.product)}<small>${cohortLabel(product.cohort)}</small></th><td><a class="coverage-pill" href="${escapeHtml(product.official_url)}" target="_blank" rel="noopener">Official verified</a></td>${cells}</tr>`;
  }).join("");
}

function sortedReviews(rows) {
  return [...rows].sort((a, b) => {
    if (state.sort === "oldest") return a.date.localeCompare(b.date);
    if (state.sort === "lowest") return a.rating - b.rating || b.date.localeCompare(a.date);
    if (state.sort === "highest") return b.rating - a.rating || b.date.localeCompare(a.date);
    return b.date.localeCompare(a.date);
  });
}

function renderReviews(rows) {
  const sorted = sortedReviews(rows);
  $("#reviewResultLabel").textContent = `${sorted.length.toLocaleString()} matching dated written review${sorted.length === 1 ? "" : "s"}`;
  const visible = sorted.slice(0, state.visible);
  $("#reviewList").innerHTML = visible.length ? visible.map(row => {
    const stars = "★".repeat(row.rating) + "☆".repeat(5 - row.rating);
    const tags = row.topics.map(topic => `<span class="topic-tag">${escapeHtml(TOPICS[topic])}</span>`).join("");
    const disclosure = [
      row.incentive_disclosed ? `<span class="disclosure-tag">Future-purchase incentive disclosed</span>` : "",
      row.sponsorship_disclosed ? `<span class="disclosure-tag">Sponsored disclosed in review</span>` : "",
    ].join("");
    return `<article class="review-card"><div class="review-rating">${stars}<small>${prettyDate(row.date)}</small></div><div class="review-copy"><h3>${escapeHtml(row.title || "Untitled review")}</h3><p>${escapeHtml(row.text)}</p>${disclosure}</div><div class="review-meta"><strong>${escapeHtml(row.product)}</strong><span>${escapeHtml(row.source === "Kevin's Natural Foods" ? "Owned site" : row.source)}</span><span>${escapeHtml(cohortLabel(row.cohort))}</span><div class="topic-tags">${tags}</div></div></article>`;
  }).join("") : `<div class="empty-results"><strong>No written reviews match this view.</strong><p>Try broadening the product, rating, topic, or source filters.</p></div>`;
  $("#loadMore").hidden = state.visible >= sorted.length;
}

function exportCsv() {
  const rows = filteredReviews();
  if (!rows.length) { toast("No filtered rows to export"); return; }
  const columns = ["product", "cohort", "source", "date", "rating", "title", "text", "topics", "incentive_disclosed", "sponsorship_disclosed", "verified_buyer", "source_url"];
  const csv = [columns.join(","), ...rows.map(row => columns.map(column => {
    const value = column === "topics" ? row.topics.join("|") : row[column] ?? "";
    return `"${String(value).replaceAll('"', '""')}"`;
  }).join(","))].join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `knf-stir-fry-reviews-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
  toast(`Exported ${rows.length} reviews`);
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 2200);
}

loadData();
