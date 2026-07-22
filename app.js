const DATA_FILES = {
  reviews: "data/reviews_normalized.json",
  analysis: "data/analysis_output.json",
  registry: "data/sku_registry.json",
  retailers: "data/retailer_evidence.json",
  retailerMatchAudit: "data/kevin_retailer_match_audit.json",
  competitorReviews: "data/competitor_reviews_normalized.json",
  competitorRegistry: "data/competitor_sku_registry.json",
  competitorSnapshots: "data/competitor_rating_snapshots.json",
  competitorCoverage: "data/competitor_coverage_audit.json",
};
const RELEASE_VERSION = "2026-07-22-amazon-aggregate-audit";

const ANALYSIS_START = "2024-11-01";
const ANALYSIS_END = "2026-07-22";
const COLORS = ["#0000A0", "#19738D", "#62BB46", "#EB6916", "#FFD131", "#3C3C3C"];
const TOPICS = {
  texture: { label: "Texture", rx: /\b(texture|tough|chew\w*|rubber\w*|grist\w*|grisly|fatty|mushy|slimy|spongy|soggy|mealy|stringy|tender|sinew\w*|powdery|blob|meat quality|fake meat|dry)\b/i },
  taste: { label: "Taste / flavor", rx: /\b(taste|flavor|bland|salty|sweet|sour|spic\w*|season\w*|delicious|gross|disgust\w*|smell\w*)\b/i },
  sauce: { label: "Sauce / gravy", rx: /\b(sauce|gravy|water\w*|liquid|soup\w*|runny)\b/i },
  value: { label: "Price / portion", rx: /\b(price|expensive|cost|worth|portion|serving|size|small|value)\b/i },
  packaging: { label: "Packaging", rx: /\b(package|packaging|bag|box|picture|photo|label)\b/i },
  changed: { label: "Product changed", rx: /\b(used to|recipe chang\w*|formula|not the same|anymore|different now|went downhill|quality has)\b/i },
};

const state = {
  dateMode: "analysis",
  products: new Set(),
  sources: new Set(),
  ratings: new Set([1, 2, 3, 4, 5]),
  topic: "all",
  search: "",
  trendMetric: "rating",
  reviewSort: "newest",
  reviewLimit: 12,
  productSort: { key: "n", direction: "desc" },
  benchmarkMode: "off",
  comparisonView: "trend",
};

let data = { reviews: [], analysis: null, registry: null, retailers: null, retailerMatchAudit: null, competitorReviews: [], competitorRegistry: null, competitorSnapshots: null, competitorCoverage: null };
let chartPoints = [];
let toastTimer;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const fmtPct = (value) => Number.isFinite(value) ? `${value.toFixed(1)}%` : "—";
const fmtRating = (value) => Number.isFinite(value) ? value.toFixed(2) : "—";
const mean = (values) => values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
const percent = (count, total) => total ? count / total * 100 : null;
const monthLabel = (month, short = false) => {
  const [year, m] = month.split("-").map(Number);
  return new Date(year, m - 1, 1).toLocaleDateString("en-US", short ? { month: "short" } : { month: "short", year: "numeric" });
};
const escapeHTML = (value = "") => String(value).replace(/[&<>'"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]);

function classifyTopics(review) {
  const text = `${review.title || ""} ${review.text || ""}`;
  return Object.fromEntries(Object.entries(TOPICS).map(([key, topic]) => [key, topic.rx.test(text)]));
}

async function loadData() {
  try {
    const [reviews, analysis, registry, retailers, retailerMatchAudit, competitorReviews, competitorRegistry, competitorSnapshots, competitorCoverage] = await Promise.all(Object.values(DATA_FILES).map(path => fetch(`${path}?v=${RELEASE_VERSION}`).then(response => {
      if (!response.ok) throw new Error(`Unable to load ${path}`);
      return response.json();
    })));
    const eligibleReviews = reviews.filter(review => review.metric_eligible !== false);
    data = {
      reviews: eligibleReviews.map((review, index) => ({ ...review, uid: index, topics: classifyTopics(review) })),
      analysis,
      registry,
      retailers,
      retailerMatchAudit,
      competitorReviews: competitorReviews.filter(review => review.metric_eligible !== false).map((review, index) => ({ ...review, uid: `competitor-${index}`, topics: classifyTopics(review) })),
      competitorRegistry,
      competitorSnapshots,
      competitorCoverage,
    };
    registry.products.forEach(product => state.products.add(product.id));
    [...new Set(eligibleReviews.map(review => review.source))].forEach(source => state.sources.add(source));
    buildFilters();
    bindEvents();
    render();
    setTimeout(() => $("#loading").classList.add("hidden"), 120);
  } catch (error) {
    $("#loading").innerHTML = `<p><strong>Dashboard data could not be loaded.</strong><br>${escapeHTML(error.message)}</p>`;
  }
}

function buildFilters() {
  const countsByProduct = Object.fromEntries(data.registry.products.map(product => [product.id, data.reviews.filter(review => review.product_id === product.id).length]));
  $("#productFilters").innerHTML = data.registry.products.map(product => `
    <label><input type="checkbox" name="product" value="${product.id}" checked><span>${escapeHTML(product.name)}</span><small>${countsByProduct[product.id]}</small></label>
  `).join("");
  const sourceCounts = Object.entries(data.reviews.reduce((acc, review) => ({ ...acc, [review.source]: (acc[review.source] || 0) + 1 }), {})).sort((a, b) => b[1] - a[1]);
  $("#sourceFilters").innerHTML = sourceCounts.map(([source, count]) => `
    <label><input type="checkbox" name="source" value="${escapeHTML(source)}" checked><span>${escapeHTML(source)}</span><small class="sr-only">${count} reviews</small></label>
  `).join("");
}

function bindEvents() {
  $("#benchmarkMode").addEventListener("change", event => { state.benchmarkMode = event.target.value; render(); });
  $("#vpComparisonViews").addEventListener("click", event => {
    const button = event.target.closest("button[data-comparison-view]");
    if (!button) return;
    state.comparisonView = button.dataset.comparisonView;
    renderExecutiveComparison();
  });
  $$('input[name="dateMode"]').forEach(input => input.addEventListener("change", () => { state.dateMode = input.value; state.reviewLimit = 12; render(); }));
  $("#productFilters").addEventListener("change", event => { if (event.target.matches('input[name="product"]')) { syncSet("product", state.products); state.reviewLimit = 12; render(); } });
  $("#sourceFilters").addEventListener("change", event => { if (event.target.matches('input[name="source"]')) { syncSet("source", state.sources); state.reviewLimit = 12; render(); } });
  $$('.rating-filter input[name="rating"]').forEach(input => input.addEventListener("change", () => { syncSet("rating", state.ratings, Number); state.reviewLimit = 12; render(); }));
  $("#topicFilter").addEventListener("change", event => { state.topic = event.target.value; state.reviewLimit = 12; render(); });
  $("#searchReviews").addEventListener("input", event => { state.search = event.target.value.trim().toLowerCase(); state.reviewLimit = 12; render(); });
  $("#trendMetric").addEventListener("change", event => { state.trendMetric = event.target.value; renderTrend(filteredReviews()); });
  $("#reviewSort").addEventListener("change", event => { state.reviewSort = event.target.value; state.reviewLimit = 12; renderReviews(filteredReviews()); });
  $("#resetFilters").addEventListener("click", resetFilters);
  $("#clearProductFocus").addEventListener("click", () => selectAll("products"));
  $$("[data-select]").forEach(button => button.addEventListener("click", () => selectAll(button.dataset.select)));
  $("#loadMore").addEventListener("click", () => { state.reviewLimit += 12; renderReviews(filteredReviews()); });
  $("#exportCsv").addEventListener("click", exportCSV);
  $("#productTable thead").addEventListener("click", event => {
    const th = event.target.closest("th[data-sort]");
    if (!th) return;
    const key = th.dataset.sort;
    state.productSort = state.productSort.key === key ? { key, direction: state.productSort.direction === "asc" ? "desc" : "asc" } : { key, direction: key === "product" ? "asc" : "desc" };
    renderProductTable();
  });
  $("#productTable tbody").addEventListener("click", focusProductFromRow);
  $("#productTable tbody").addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); focusProductFromRow(event); } });
  window.addEventListener("resize", debounce(() => renderTrend(filteredReviews()), 120));
  $("#trendChart").addEventListener("mousemove", showChartTooltip);
  $("#trendChart").addEventListener("mouseleave", () => $("#chartTooltip").hidden = true);
}

function debounce(fn, delay) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); }; }
function syncSet(name, set, transform = value => value) { set.clear(); $$(`input[name="${name}"]:checked`).forEach(input => set.add(transform(input.value))); }

function selectAll(group) {
  const name = group === "products" ? "product" : "source";
  $$(`input[name="${name}"]`).forEach(input => input.checked = true);
  syncSet(name, group === "products" ? state.products : state.sources);
  state.reviewLimit = 12;
  render();
}

function resetFilters() {
  state.dateMode = "analysis";
  state.benchmarkMode = "off";
  state.comparisonView = "trend";
  state.topic = "all";
  state.search = "";
  state.reviewLimit = 12;
  $$('input[name="dateMode"]').forEach(input => input.checked = input.value === "analysis");
  $$('input[name="product"], input[name="source"], input[name="rating"]').forEach(input => input.checked = true);
  syncSet("product", state.products);
  syncSet("source", state.sources);
  syncSet("rating", state.ratings, Number);
  $("#topicFilter").value = "all";
  $("#benchmarkMode").value = "off";
  $("#searchReviews").value = "";
  render();
}

function inDateMode(review) {
  return state.dateMode === "all" || (review.date >= ANALYSIS_START && review.date <= ANALYSIS_END);
}

function passesNonProductFilters(review) {
  if (!inDateMode(review)) return false;
  if (!state.sources.has(review.source) || !state.ratings.has(Number(review.rating))) return false;
  if (state.topic !== "all" && !review.topics[state.topic]) return false;
  if (state.search && !`${review.product} ${review.title || ""} ${review.text || ""}`.toLowerCase().includes(state.search)) return false;
  return true;
}

function filteredReviews() {
  return data.reviews.filter(review => state.products.has(review.product_id) && passesNonProductFilters(review));
}

function benchmarkProducts() {
  if (state.benchmarkMode === "off") return [];
  return data.competitorRegistry.products.filter(product => state.benchmarkMode === "all" || product.benchmark_tier === "core");
}

function benchmarkReviews() {
  const ids = new Set(benchmarkProducts().map(product => product.id));
  return data.competitorReviews.filter(review => {
    if (!ids.has(review.product_id) || !inDateMode(review) || !state.ratings.has(Number(review.rating))) return false;
    if (state.topic !== "all" && !review.topics[state.topic]) return false;
    if (state.search && !`${review.brand || ""} ${review.product} ${review.title || ""} ${review.text || ""}`.toLowerCase().includes(state.search)) return false;
    return true;
  });
}

function reviewMetrics(reviews) {
  return {
    n: reviews.length,
    rating: mean(reviews.map(review => Number(review.rating))),
    low: percent(reviews.filter(review => Number(review.rating) <= 2).length, reviews.length),
    texture: percent(reviews.filter(review => review.topics.texture).length, reviews.length),
    taste: percent(reviews.filter(review => review.topics.taste).length, reviews.length),
  };
}

function snapshotMetrics(snapshots) {
  const distribution = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
  snapshots.filter(snapshot => snapshot.metric_eligible !== false).forEach(snapshot => {
    Object.keys(distribution).forEach(star => { distribution[star] += Number(snapshot.distribution?.[star] || 0); });
  });
  const n = Object.values(distribution).reduce((sum, count) => sum + count, 0);
  return {
    n,
    pages: snapshots.length,
    products: new Set(snapshots.map(snapshot => snapshot.product_id)).size,
    rating: n ? Object.entries(distribution).reduce((sum, [star, count]) => sum + Number(star) * count, 0) / n : null,
    low: n ? percent(distribution[1] + distribution[2], n) : null,
  };
}

function executiveComparisonData() {
  const coreIds = new Set(data.competitorRegistry.products.filter(product => product.benchmark_tier === "core").map(product => product.id));
  if (state.comparisonView === "ratings") {
    const kevinSnapshots = data.analysis.rating_snapshots.filter(snapshot => Object.values(snapshot.distribution || {}).reduce((sum, count) => sum + Number(count), 0) > 0);
    const competitorSnapshots = data.competitorSnapshots.snapshots.filter(snapshot => snapshot.metric_eligible !== false && coreIds.has(snapshot.product_id) && Object.values(snapshot.distribution || {}).reduce((sum, count) => sum + Number(count), 0) > 0);
    const kevin = snapshotMetrics(kevinSnapshots);
    const competitor = snapshotMetrics(competitorSnapshots);
    return {
      kevin,
      competitor,
      headline: `Observed channel rating totals slightly favor competitors: ${fmtRating(competitor.rating)} versus ${fmtRating(kevin.rating)}, with ${fmtPct(competitor.low)} versus ${fmtPct(kevin.low)} in 1-2 stars. Treat this as source-page context, not a unique or time-aligned population.`,
      scope: `Point-in-time source-page totals · Kevin's ${kevin.n.toLocaleString()} ratings across ${kevin.pages} pages / ${kevin.products} products · Competitors ${competitor.n.toLocaleString()} ratings across ${competitor.pages} pages / ${competitor.products} core products · Totals may include syndicated or repeated populations.`,
      evidenceLabel: "Observed ratings",
    };
  }

  const start = state.comparisonView === "trend" ? ANALYSIS_START : "2023-01-01";
  const kevinRows = data.reviews.filter(review => review.date >= start && review.date <= ANALYSIS_END);
  const competitorRows = data.competitorReviews.filter(review => coreIds.has(review.product_id) && review.date >= start && review.date <= ANALYSIS_END);
  const kevin = { ...reviewMetrics(kevinRows), products: new Set(kevinRows.map(review => review.product_id)).size };
  const competitor = { ...reviewMetrics(competitorRows), products: new Set(competitorRows.map(review => review.product_id)).size };
  const recent = state.comparisonView === "trend";
  return {
    kevin,
    competitor,
    headline: recent
      ? `Competitors lead recent dated written feedback. Kevin's 1-2-star share is ${fmtPct(kevin.low)}, ${Math.abs(kevin.low - competitor.low).toFixed(1)} points above competitors, and its average rating trails by ${(competitor.rating - kevin.rating).toFixed(2)} stars.`
      : `The full archive reverses the recent result. Kevin's averages ${fmtRating(kevin.rating)} versus ${fmtRating(competitor.rating)}, with ${fmtPct(kevin.low)} in 1-2 stars versus ${fmtPct(competitor.low)} for competitors.`,
    scope: `Dated written reviews · ${recent ? "Nov 1, 2024-Jul 22, 2026" : "Jan 1, 2023-Jul 22, 2026"} · Kevin's n=${kevin.n.toLocaleString()} / ${kevin.products} products · Competitors n=${competitor.n.toLocaleString()} / ${competitor.products} core products.`,
    evidenceLabel: recent ? "Trend written" : "Full written",
  };
}

function comparisonBars(label, kevinValue, competitorValue, max, formatter, note) {
  const width = value => Math.max(0, Math.min(100, Number(value) / max * 100));
  return `<article class="vp-metric-card"><header><span>${escapeHTML(label)}</span><small>${escapeHTML(note)}</small></header><div class="vp-pair"><div><span>Kevin's</span><div class="vp-track"><i style="width:${width(kevinValue)}%"></i></div><strong>${escapeHTML(formatter(kevinValue))}</strong></div><div class="competitor"><span>Competitors</span><div class="vp-track"><i style="width:${width(competitorValue)}%"></i></div><strong>${escapeHTML(formatter(competitorValue))}</strong></div></div></article>`;
}

function renderExecutiveComparison() {
  const comparison = executiveComparisonData();
  $$("#vpComparisonViews button").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.comparisonView === state.comparisonView)));
  $("#vpComparisonHeadline").textContent = comparison.headline;
  $("#vpComparisonMetrics").innerHTML = [
    comparisonBars("Average rating", comparison.kevin.rating, comparison.competitor.rating, 5, fmtRating, "Higher is better"),
    comparisonBars("1-2 star share", comparison.kevin.low, comparison.competitor.low, 100, fmtPct, "Lower is better"),
  ].join("");
  $("#vpComparisonScope").textContent = comparison.scope;
}

function formatDelta(value, suffix = "") {
  if (!Number.isFinite(value)) return "No comparison";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}${suffix} vs benchmark`;
}

function render() {
  const reviews = filteredReviews();
  const competitor = benchmarkReviews();
  renderKPIs(reviews);
  renderTrend(reviews);
  renderRatingDistribution(reviews);
  renderSourceMix(reviews);
  renderThemes(reviews);
  renderProductTable();
  renderSnapshots();
  renderCoverage();
  renderReviews(reviews);
  renderBenchmark(reviews, competitor);
  const allProducts = state.products.size === data.registry.products.length;
  $("#clearProductFocus").hidden = allProducts;
  $("#viewCount").textContent = `${reviews.length.toLocaleString()} review${reviews.length === 1 ? "" : "s"}`;
}

function renderKPIs(reviews) {
  const rating = mean(reviews.map(review => Number(review.rating)));
  const lowCount = reviews.filter(review => Number(review.rating) <= 2).length;
  const textureCount = reviews.filter(review => review.topics.texture).length;
  const tasteCount = reviews.filter(review => review.topics.taste).length;
  $("#kpiReviews").textContent = reviews.length.toLocaleString();
  $("#kpiCoverage").textContent = state.dateMode === "analysis" ? "Nov 2024–Jul 2026" : "Jan 2023–Jul 2026 backfill";
  $("#kpiRating").textContent = fmtRating(rating);
  $("#kpiLow").textContent = fmtPct(percent(lowCount, reviews.length));
  $("#kpiLowNote").textContent = `${lowCount} low-rating review${lowCount === 1 ? "" : "s"}`;
  $("#kpiTexture").textContent = fmtPct(percent(textureCount, reviews.length));
  $("#kpiTaste").textContent = fmtPct(percent(tasteCount, reviews.length));
  const benchmark = reviewMetrics(benchmarkReviews());
  if (state.benchmarkMode === "off" || !benchmark.n) {
    $("#kpiRatingNote").textContent = "Computed from written reviews";
    $("#kpiTextureNote").textContent = "Keyword-coded";
    $("#kpiTasteNote").textContent = "Keyword-coded";
  } else {
    $("#kpiRatingNote").textContent = formatDelta(rating - benchmark.rating);
    $("#kpiLowNote").textContent = formatDelta(percent(lowCount, reviews.length) - benchmark.low, " pts");
    $("#kpiTextureNote").textContent = formatDelta(percent(textureCount, reviews.length) - benchmark.texture, " pts");
    $("#kpiTasteNote").textContent = formatDelta(percent(tasteCount, reviews.length) - benchmark.taste, " pts");
  }
}

function groupByMonth(reviews, months = null) {
  const groups = {};
  reviews.forEach(review => { const month = review.date.slice(0, 7); (groups[month] ||= []).push(review); });
  if (!months) {
    const startMonth = state.dateMode === "analysis" ? ANALYSIS_START.slice(0, 7) : "2023-01";
    const endMonth = ANALYSIS_END.slice(0, 7);
    months = [];
    const start = new Date(`${startMonth}-01T00:00:00`);
    const end = new Date(`${endMonth}-01T00:00:00`);
    for (const cursor = new Date(start); cursor <= end; cursor.setMonth(cursor.getMonth() + 1)) months.push(`${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}`);
  }
  return months.map(month => ({ month, reviews: groups[month] || [] }));
}

function metricForGroup(group) {
  const reviews = group.reviews;
  if (!reviews.length) return null;
  if (state.trendMetric === "rating") return mean(reviews.map(review => Number(review.rating)));
  if (state.trendMetric === "low") return percent(reviews.filter(review => Number(review.rating) <= 2).length, reviews.length);
  if (state.trendMetric === "texture") return percent(reviews.filter(review => review.topics.texture).length, reviews.length);
  return reviews.length;
}

function renderTrend(reviews) {
  const canvas = $("#trendChart");
  const wrap = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(300, wrap.clientWidth);
  const height = Math.max(220, wrap.clientHeight);
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);
  const groups = groupByMonth(reviews);
  const competitorGroups = groupByMonth(benchmarkReviews(), groups.map(group => group.month));
  const values = groups.map(metricForGroup);
  const competitorValues = competitorGroups.map(metricForGroup);
  const meta = {
    rating: { label: "Average rating", max: 5, suffix: "" },
    low: { label: "1–2 star share", max: 100, suffix: "%" },
    texture: { label: "Texture mention share", max: 100, suffix: "%" },
    volume: { label: "Review volume", max: Math.max(5, ...values.filter(Number.isFinite), ...competitorValues.filter(Number.isFinite)) * 1.15, suffix: "" },
  }[state.trendMetric];
  $("#trendLegend").textContent = `Kevin's ${meta.label.toLowerCase()}`;
  $("#benchmarkLegend").hidden = state.benchmarkMode === "off";
  const pad = { left: 43, right: 15, top: 14, bottom: 35 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  ctx.font = "10px Segoe UI, Arial";
  ctx.textBaseline = "middle";
  ctx.strokeStyle = "#e5ddd5";
  ctx.fillStyle = "#68625e";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + plotH * i / 4;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    const value = meta.max * (1 - i / 4);
    ctx.fillText(state.trendMetric === "rating" ? value.toFixed(1) : Math.round(value).toString(), 6, y);
  }
  if (!groups.length || (!values.some(Number.isFinite) && !competitorValues.some(Number.isFinite))) {
    ctx.fillStyle = "#68625e"; ctx.textAlign = "center"; ctx.font = '13px "Mars Centra", Arial';
    ctx.fillText("No reviews match the current filters", width / 2, height / 2);
    chartPoints = [];
    return;
  }
  const xAt = index => groups.length === 1 ? pad.left + plotW / 2 : pad.left + index / (groups.length - 1) * plotW;
  const yAt = value => pad.top + (1 - value / meta.max) * plotH;
  const cutoffIndex = groups.findIndex(group => group.month === "2025-11");
  if (cutoffIndex >= 0) {
    const x = xAt(cutoffIndex);
    ctx.strokeStyle = "#EB6916"; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + plotH); ctx.stroke(); ctx.setLineDash([]);
  }
  ctx.fillStyle = "#68625e"; ctx.textAlign = "center"; ctx.font = '9px "Mars Centra", Arial';
  groups.forEach((group, index) => { if (index % Math.max(1, Math.ceil(groups.length / 8)) === 0 || index === groups.length - 1) ctx.fillText(monthLabel(group.month, true), xAt(index), height - 13); });
  const drawSeries = (seriesValues, seriesGroups, color, dashed, seriesLabel) => {
    ctx.strokeStyle = color; ctx.lineWidth = 2.5; ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.setLineDash(dashed ? [7, 5] : []);
    let drawing = false; ctx.beginPath();
    seriesValues.forEach((value, index) => {
      if (!Number.isFinite(value)) { drawing = false; return; }
      const x = xAt(index), y = yAt(value);
      if (!drawing) { ctx.moveTo(x, y); drawing = true; } else ctx.lineTo(x, y);
    });
    ctx.stroke(); ctx.setLineDash([]);
    seriesValues.forEach((value, index) => {
      if (!Number.isFinite(value)) return;
      const x = xAt(index), y = yAt(value);
      ctx.fillStyle = "white"; ctx.strokeStyle = color; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x, y, dashed ? 3 : 3.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      chartPoints.push({ x, y, month: groups[index].month, value, n: seriesGroups[index].reviews.length, suffix: meta.suffix, label: `${seriesLabel} ${meta.label.toLowerCase()}` });
    });
  };
  chartPoints = [];
  drawSeries(values, groups, "#0000A0", false, "Kevin's");
  if (state.benchmarkMode !== "off") drawSeries(competitorValues, competitorGroups, "#EB6916", true, "Competitor");
  $("#trendTable").textContent = groups.map((group, index) => `${monthLabel(group.month)}: Kevin's ${Number.isFinite(values[index]) ? values[index].toFixed(state.trendMetric === "volume" ? 0 : 1) + meta.suffix : "no data"}; competitor ${Number.isFinite(competitorValues[index]) ? competitorValues[index].toFixed(state.trendMetric === "volume" ? 0 : 1) + meta.suffix : "no data"}`).join("; ");
}

function showChartTooltip(event) {
  if (!chartPoints.length) return;
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const nearest = chartPoints.reduce((best, point) => Math.abs(point.x - x) < Math.abs(best.x - x) ? point : best, chartPoints[0]);
  if (Math.abs(nearest.x - x) > 28) { $("#chartTooltip").hidden = true; return; }
  const tooltip = $("#chartTooltip");
  const monthPoints = chartPoints.filter(point => point.month === nearest.month);
  tooltip.innerHTML = `<strong>${monthLabel(nearest.month)}</strong>${monthPoints.map(point => `${escapeHTML(point.label)}: ${point.value.toFixed(state.trendMetric === "volume" ? 0 : 1)}${point.suffix}<br><small>${point.n} review${point.n === 1 ? "" : "s"}</small>`).join("<hr>")}`;
  tooltip.style.left = `${nearest.x}px`;
  tooltip.style.top = `${nearest.y}px`;
  tooltip.hidden = false;
}

function renderRatingDistribution(reviews) {
  const competitor = benchmarkReviews();
  const counts = [5, 4, 3, 2, 1].map(star => ({ star, count: reviews.filter(review => Number(review.rating) === star).length }));
  $("#ratingDistribution").innerHTML = counts.map(({ star, count }) => {
    const share = percent(count, reviews.length) || 0;
    const competitorShare = percent(competitor.filter(review => Number(review.rating) === star).length, competitor.length) || 0;
    return `<div class="bar-row"><span>${star} star</span><div class="bar-pair"><div class="bar-track" title="Kevin's ${share.toFixed(1)}%"><i style="width:${share}%"></i></div>${state.benchmarkMode !== "off" ? `<div class="bar-track benchmark" title="Competitor ${competitorShare.toFixed(1)}%"><i style="width:${competitorShare}%"></i></div>` : ""}</div><strong>${share.toFixed(0)}%${state.benchmarkMode !== "off" ? `<small>${competitorShare.toFixed(0)}%</small>` : ""}</strong></div>`;
  }).join("");
}

function renderSourceMix(reviews) {
  const counts = [...new Set(data.reviews.map(review => review.source))].map(source => ({ source, count: reviews.filter(review => review.source === source).length })).sort((a, b) => b.count - a.count);
  const stack = counts.map(({ source, count }, index) => `<i title="${escapeHTML(source)}: ${count}" style="width:${percent(count, reviews.length) || 0}%;background:${COLORS[index]}"></i>`).join("");
  const legend = counts.map(({ source, count }, index) => `<div><i style="background:${COLORS[index]}"></i><span>${escapeHTML(source)}</span><strong>${count}</strong></div>`).join("");
  $("#sourceMix").innerHTML = `<div class="source-stack">${stack}</div><div class="source-legend">${legend}</div>`;
}

function renderThemes(reviews) {
  const competitor = benchmarkReviews();
  $("#themeBars").innerHTML = Object.entries(TOPICS).map(([key, topic]) => {
    const count = reviews.filter(review => review.topics[key]).length;
    const share = percent(count, reviews.length) || 0;
    const competitorCount = competitor.filter(review => review.topics[key]).length;
    const competitorShare = percent(competitorCount, competitor.length) || 0;
    return `<article class="theme-card"><header><span>${topic.label}</span><strong>${share.toFixed(1)}%</strong></header><div class="theme-meter"><i style="width:${share}%"></i></div>${state.benchmarkMode !== "off" ? `<div class="theme-meter benchmark"><i style="width:${competitorShare}%"></i></div>` : ""}<small>${count} Kevin's match${count === 1 ? "" : "es"}${state.benchmarkMode !== "off" ? ` · competitor ${competitorShare.toFixed(1)}%` : ""}</small></article>`;
  }).join("");
}

function renderBenchmark(kevinReviews, competitorReviews) {
  const active = state.benchmarkMode !== "off";
  const section = $("#benchmark");
  const banner = $("#benchmarkBanner");
  section.hidden = !active;
  banner.hidden = !active;
  $("#benchmarkNav").hidden = !active;
  if (!active) return;

  renderExecutiveComparison();

  const products = benchmarkProducts();
  const metrics = reviewMetrics(competitorReviews);
  const kevin = reviewMetrics(kevinReviews);
  const productsWithText = products.filter(product => competitorReviews.some(review => review.product_id === product.id));
  const equalProductRatings = productsWithText.map(product => mean(competitorReviews.filter(review => review.product_id === product.id).map(review => Number(review.rating)))).filter(Number.isFinite);
  const equalProductAverage = mean(equalProductRatings);
  const modeLabel = state.benchmarkMode === "core" ? "Core 14-20 oz benchmark" : "All supplied competitors";
  banner.innerHTML = `<div><span class="benchmark-chip">Overlay active</span><strong>${escapeHTML(modeLabel)}</strong><p>${metrics.n.toLocaleString()} captured written reviews across ${productsWithText.length} products with text; ${products.length} normalized products remain visible for coverage.</p></div><div class="benchmark-key"><span><i></i>Kevin's</span><span><i></i>Competitor</span></div>`;

  $("#benchmarkSummary").innerHTML = [
    ["Captured text", metrics.n.toLocaleString(), `${productsWithText.length}/${products.length} products with written-review evidence`],
    ["Review-weighted rating", fmtRating(metrics.rating), Number.isFinite(kevin.rating) ? `${metrics.rating - kevin.rating > 0 ? "+" : ""}${(metrics.rating - kevin.rating).toFixed(1)} vs Kevin's` : "Current competitor view"],
    ["Equal-product rating", fmtRating(equalProductAverage), "Each evidenced product weighted equally"],
    ["Low-rating share", fmtPct(metrics.low), Number.isFinite(kevin.low) ? `${Math.abs(metrics.low - kevin.low).toFixed(1)} pts ${metrics.low > kevin.low ? "above" : "below"} Kevin's` : "1-2 star reviews"],
  ].map(([label, value, note]) => `<article><span>${label}</span><strong>${value}</strong><p>${note}</p></article>`).join("");

  $("#benchmarkTable tbody").innerHTML = products.map(product => {
    const rows = competitorReviews.filter(review => review.product_id === product.id);
    const row = reviewMetrics(rows);
    const sources = [...new Set(rows.map(review => review.source))];
    const evidence = !rows.length ? "Coverage / rating context" : sources.includes("Hormel") ? "Complete first-party + bounded retailer sample" : "Bounded retailer sample";
    return `<tr class="benchmark-row"><td class="product-name"><small>${escapeHTML(product.brand)}</small>${escapeHTML(product.name)}</td><td>${product.pack_oz} oz</td><td><span class="status-pill ${product.benchmark_tier === "adjacent" ? "variant" : ""}">${product.benchmark_tier}</span></td><td>${row.n}</td><td>${fmtRating(row.rating)}</td><td>${fmtPct(row.low)}</td><td>${fmtPct(row.texture)}</td><td>${fmtPct(row.taste)}</td><td><span class="status-pill ${rows.length ? "" : "gap"}">${evidence}</span></td></tr>`;
  }).join("");

  const productIds = new Set(products.map(product => product.id));
  const snapshots = (data.competitorSnapshots.snapshots || []).filter(snapshot => productIds.has(snapshot.product_id));
  $("#benchmarkSnapshots").innerHTML = snapshots.map(snapshot => {
    const total = Number(snapshot.rating_count) || Object.values(snapshot.distribution || {}).reduce((sum, value) => sum + Number(value), 0);
    const hasDistribution = Object.keys(snapshot.distribution || {}).length > 0;
    const roundedPercentages = snapshot.distribution_basis === "source_rounded_percentages_apportioned_to_rating_total";
    const bars = hasDistribution ? [5, 4, 3, 2, 1].map(star => {
      const count = Number(snapshot.distribution?.[String(star)] || 0);
      const share = roundedPercentages ? Number(snapshot.distribution_percent?.[String(star)] || 0) : percent(count, total) || 0;
      return `<div><span>${star}</span><i><b style="width:${share}%"></b></i><span>${roundedPercentages ? `${share}%` : count.toLocaleString()}</span></div>`;
    }).join("") : `<p class="snapshot-distribution-note">Star distribution not publicly available.</p>`;
    const status = {
      complete_public_first_party_feed: "Complete public first-party feed",
      bounded_public_text_sample_plus_complete_rating_distribution: `${snapshot.captured_written_reviews || 0} dated reviews in bounded public-page sample; complete point-in-time distribution`,
      complete_rating_distribution_shared_variant_text_excluded: "Shared variant-family rating distribution; unresolved written text excluded",
      rating_total_only_public_text_payload_unavailable: "Exact-SKU rating total only; reproducible public review text unavailable",
      amazon_aggregate_exact_sku_no_dated_text: "Exact-SKU Amazon aggregate; rounded star percentages; dated review text not captured",
      amazon_aggregate_related_variant_excluded: "Related Amazon variant aggregate; excluded from benchmark metrics",
    }[snapshot.capture_status] || "Public rating context; see methodology";
    return `<article class="snapshot-card competitor-snapshot"><header><span>${escapeHTML(snapshot.brand)} · ${escapeHTML(snapshot.source)}</span><strong>${escapeHTML(snapshot.product)}</strong></header><div class="snapshot-score"><strong>${fmtRating(Number(snapshot.average_rating))}</strong><span>${total.toLocaleString()} ratings</span></div><div class="snapshot-stars">${bars}</div><p>${escapeHTML(status)}<br><a href="${escapeHTML(snapshot.page_url)}" target="_blank" rel="noopener noreferrer">Open source page ↗</a></p></article>`;
  }).join("");

  const auditRows = data.competitorCoverage.rows || [];
  const auditSources = ["Brand", "Target", "Amazon", "Kroger", "Walmart", "Costco"];
  const statusLabel = { review_evidence: "Review evidence", rating_evidence: "Rating context", shared_variant_rating_context: "Shared rating context", related_variant_excluded: "Related size excluded", listing_only: "Exact listing", exact_page_not_confirmed: "Search only", not_located: "Not located" };
  $("#benchmarkCoverageTable tbody").innerHTML = products.map(product => {
    const cells = auditSources.map(source => {
      const audit = auditRows.find(row => row.product_id === product.id && row.source === source);
      if (!audit) return `<td><span class="coverage-pill gap">Not audited</span></td>`;
      const label = statusLabel[audit.status] || audit.status;
      const classes = audit.status === "not_located" ? "gap" : audit.match_type === "club_pack_variant" || audit.status === "exact_page_not_confirmed" || audit.status === "related_variant_excluded" || audit.status === "shared_variant_rating_context" ? "variant" : "";
      const pill = audit.page_url ? `<a class="coverage-pill ${classes}" href="${escapeHTML(audit.page_url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(label)} ↗</a>` : `<span class="coverage-pill ${classes}">${escapeHTML(label)}</span>`;
      return `<td>${pill}<small>${escapeHTML(audit.match_type.replaceAll("_", " "))}${audit.note ? `<br>${escapeHTML(audit.note)}` : ""}</small></td>`;
    }).join("");
    return `<tr><th scope="row">${escapeHTML(product.brand)}<br><small>${escapeHTML(product.name)}</small></th>${cells}</tr>`;
  }).join("");
}

function productMetrics() {
  const contentPool = data.reviews.filter(review => {
    if (!state.sources.has(review.source) || !state.ratings.has(Number(review.rating))) return false;
    if (state.topic !== "all" && !review.topics[state.topic]) return false;
    if (state.search && !`${review.product} ${review.title || ""} ${review.text || ""}`.toLowerCase().includes(state.search)) return false;
    return true;
  });
  return data.registry.products.map(product => {
    const productPool = contentPool.filter(review => review.product_id === product.id);
    const reviews = productPool.filter(inDateMode);
    const preReviews = productPool.filter(review => review.date >= ANALYSIS_START && review.date < "2025-11-01");
    const postReviews = productPool.filter(review => review.date >= "2025-11-01" && review.date <= ANALYSIS_END);
    const n = reviews.length;
    const pre = mean(preReviews.map(review => Number(review.rating)));
    const post = mean(postReviews.map(review => Number(review.rating)));
    return {
      id: product.id,
      product: product.name,
      n,
      archiveCount: productPool.length,
      rating: mean(reviews.map(review => Number(review.rating))),
      pre,
      post,
      delta: Number.isFinite(pre) && Number.isFinite(post) ? post - pre : null,
      low: percent(reviews.filter(review => Number(review.rating) <= 2).length, n),
      texture: percent(reviews.filter(review => review.topics.texture).length, n),
      taste: percent(reviews.filter(review => review.topics.taste).length, n),
    };
  });
}

function renderProductTable() {
  const { key, direction } = state.productSort;
  const rows = productMetrics().sort((a, b) => {
    const av = a[key] ?? -Infinity, bv = b[key] ?? -Infinity;
    const result = typeof av === "string" ? av.localeCompare(bv) : av - bv;
    return direction === "asc" ? result : -result;
  });
  $("#productTable tbody").innerHTML = rows.map(row => `
    <tr class="product-row" tabindex="0" data-product-id="${row.id}" aria-label="Filter dashboard to ${escapeHTML(row.product)}">
      <td class="product-name">${escapeHTML(row.product)}</td>
      <td>${row.n}</td>
      <td><div class="metric-cell"><span>${fmtRating(row.rating)}</span><span class="mini-track"><i style="width:${(row.rating || 0) * 20}%"></i></span></div></td>
      <td>${fmtRating(row.pre)}</td><td>${fmtRating(row.post)}</td><td class="${row.delta < 0 ? "delta-negative" : row.delta > 0 ? "delta-positive" : ""}">${Number.isFinite(row.delta) ? `${row.delta > 0 ? "+" : ""}${row.delta.toFixed(2)}` : "—"}</td>
      <td>${fmtPct(row.low)}</td><td>${fmtPct(row.texture)}</td><td>${fmtPct(row.taste)}</td>
      <td><span class="status-pill ${row.archiveCount ? "" : "gap"}">${row.n ? "Written reviews" : row.archiveCount ? "Archive only" : "Coverage gap"}</span></td>
    </tr>
  `).join("");
}

function focusProductFromRow(event) {
  const row = event.target.closest("tr[data-product-id]");
  if (!row) return;
  $$('input[name="product"]').forEach(input => input.checked = input.value === row.dataset.productId);
  syncSet("product", state.products);
  state.reviewLimit = 12;
  render();
  $("#overview").scrollIntoView({ behavior: "smooth", block: "start" });
  showToast(`Filtered to ${data.registry.products.find(product => product.id === row.dataset.productId).name}`);
}

function renderSnapshots() {
  const productNames = Object.fromEntries(data.registry.products.map(product => [product.id, product.name]));
  $("#retailerSnapshots").innerHTML = data.analysis.rating_snapshots.map(snapshot => {
    const average = snapshot.rating_count ? Object.entries(snapshot.distribution).reduce((sum, [star, count]) => sum + Number(star) * count, 0) / snapshot.rating_count : null;
    const bars = [5, 4, 3, 2, 1].map(star => {
      const count = snapshot.distribution[String(star)] || 0;
      return `<div><span>${star}</span><i><b style="width:${percent(count, snapshot.rating_count) || 0}%"></b></i><span>${count}</span></div>`;
    }).join("");
    const product = data.registry.products.find(item => item.id === snapshot.product_id);
    const page = snapshot.page_url || (snapshot.source === "Kevin's Natural Foods" ? product?.retailer_pages?.brand : product?.retailer_pages?.[snapshot.source.toLowerCase()]);
    return `<article class="snapshot-card"><header><span>${escapeHTML(snapshot.source)}</span><strong>${escapeHTML(productNames[snapshot.product_id])}</strong></header><div class="snapshot-score"><strong>${fmtRating(average)}</strong><span>${snapshot.rating_count} rating${snapshot.rating_count === 1 ? "" : "s"}</span></div><div class="snapshot-stars">${bars}</div><p>${escapeHTML(snapshot.page_status)}${page ? `<br><a href="${escapeHTML(page)}" target="_blank" rel="noopener noreferrer">Open retailer page ↗</a>` : ""}</p></article>`;
  }).join("");
}

function renderCoverage() {
  const retailers = ["Brand", "Target", "Amazon", "Kroger", "Walmart", "Costco"];
  const matches = data.retailerMatchAudit?.rows || [];
  const labels = { exact_owned_site: "Owned-site SKU", exact_16oz: "Exact 16 oz", club_pack_variant: "32 oz club pack" };

  $("#coverageSummary").innerHTML = retailers.map(source => {
    const found = matches.filter(item => item.source === source && item.match_type !== "not_located");
    const exact = found.filter(item => item.match_type === "exact_16oz" || item.match_type === "exact_owned_site").length;
    const club = found.filter(item => item.match_type === "club_pack_variant").length;
    const detail = source === "Brand" ? `${exact} official product identities` : source === "Costco" ? `${club} club-pack flavor variants` : `${exact} exact 16 oz listings`;
    return `<article><span>${escapeHTML(source)}</span><strong>${found.length}/8</strong><p>${detail}</p></article>`;
  }).join("");

  $("#coverageTable tbody").innerHTML = data.registry.products.map(product => {
    const cells = retailers.map(source => {
      const match = matches.find(item => item.product_id === product.id && item.source === source);
      if (!match || match.match_type === "not_located") return `<td><span class="coverage-pill gap">Not returned</span><small>Not returned for the reference market; not confirmed absent.</small></td>`;
      const statusLabels = {
        owned_site_verified: "Official Kevin's product page",
        official_locator_in_stock: "Official locator: in stock at audit",
        official_locator_out_of_stock: "Official locator: listed, out of stock at audit",
        official_locator_in_store: "Official locator: found in stores",
        direct_page_verified_prior: "Direct retailer page; local availability varies",
      };
      const item = match.item_id ? `Item ${match.item_id}` : "Verified product identity";
      const pack = match.pack_oz ? `${match.pack_oz} oz` : "Pack varies";
      const variantClass = match.match_type === "club_pack_variant" ? "variant" : "";
      return `<td><a class="coverage-pill ${variantClass}" href="${escapeHTML(match.page_url)}" target="_blank" rel="noopener noreferrer">${labels[match.match_type]} &#8599;</a><small>${escapeHTML(pack)} &middot; ${escapeHTML(item)}<br>${escapeHTML(statusLabels[match.status] || match.status)}</small></td>`;
    }).join("");
    return `<tr><th scope="row">${escapeHTML(product.name)}</th>${cells}</tr>`;
  }).join("");
}

function sortedReviews(reviews) {
  return [...reviews].sort((a, b) => {
    if (state.reviewSort === "oldest") return a.date.localeCompare(b.date);
    if (state.reviewSort === "lowest") return Number(a.rating) - Number(b.rating) || b.date.localeCompare(a.date);
    if (state.reviewSort === "highest") return Number(b.rating) - Number(a.rating) || b.date.localeCompare(a.date);
    return b.date.localeCompare(a.date);
  });
}

function renderReviews(reviews) {
  const sorted = sortedReviews(reviews);
  const visible = sorted.slice(0, state.reviewLimit);
  $("#reviewResultLabel").textContent = `${reviews.length.toLocaleString()} matching review${reviews.length === 1 ? "" : "s"}; showing ${Math.min(visible.length, reviews.length).toLocaleString()}.`;
  if (!visible.length) {
    $("#reviewList").innerHTML = `<div class="empty-results"><strong>No reviews match the current filters.</strong><br>Broaden the product, source, rating, topic, or text selection.</div>`;
  } else {
    $("#reviewList").innerHTML = visible.map(review => {
      const tags = Object.entries(review.topics).filter(([, match]) => match).map(([key]) => `<span class="topic-tag">${TOPICS[key].label}</span>`).join("");
      const stars = "★".repeat(Number(review.rating)) + "☆".repeat(5 - Number(review.rating));
      const verification = review.verified_buyer ? " · Verified buyer" : "";
      return `<article class="review-card"><div class="review-rating" aria-label="${review.rating} out of 5 stars">${stars}<small>${review.date}</small></div><div class="review-copy"><h3>${escapeHTML(review.title || "Untitled review")}</h3><p>${escapeHTML(review.text || "No written comment captured.")}</p></div><div class="review-meta"><strong>${escapeHTML(review.product)}</strong><span>${escapeHTML(review.source)} · ${escapeHTML(review.capture)}${verification}</span><div class="topic-tags">${tags}</div></div></article>`;
    }).join("");
  }
  $("#loadMore").hidden = state.reviewLimit >= reviews.length;
}

function exportCSV() {
  const reviews = sortedReviews(filteredReviews());
  if (!reviews.length) { showToast("No reviews to export"); return; }
  const columns = ["product", "source", "date", "rating", "title", "text", "capture", "provider", "provider_review_id", "verified_buyer", "source_url", ...Object.keys(TOPICS)];
  const quote = value => `"${String(value ?? "").replace(/"/g, '""')}"`;
  const rows = reviews.map(review => columns.map(column => quote(column in review.topics ? review.topics[column] : review[column])).join(","));
  const blob = new Blob([[columns.join(","), ...rows].join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = `beef-hmr-reviews-${new Date().toISOString().slice(0, 10)}.csv`; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  showToast(`Exported ${reviews.length} filtered reviews`);
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
}

loadData();
