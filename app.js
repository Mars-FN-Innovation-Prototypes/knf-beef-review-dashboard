const DATA_FILES = {
  reviews: "data/reviews_normalized.json",
  analysis: "data/analysis_output.json",
  registry: "data/sku_registry.json",
  retailers: "data/retailer_evidence.json",
};

const ANALYSIS_START = "2024-11-01";
const ANALYSIS_END = "2026-07-14";
const COLORS = ["#246fa8", "#52b9c5", "#e77a3e", "#6e8c74", "#8a6aa6", "#b8a056"];
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
};

let data = { reviews: [], analysis: null, registry: null, retailers: null };
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
    const [reviews, analysis, registry, retailers] = await Promise.all(Object.values(DATA_FILES).map(path => fetch(path).then(response => {
      if (!response.ok) throw new Error(`Unable to load ${path}`);
      return response.json();
    })));
    data = {
      reviews: reviews.map((review, index) => ({ ...review, uid: index, topics: classifyTopics(review) })),
      analysis,
      registry,
      retailers,
    };
    registry.products.forEach(product => state.products.add(product.id));
    [...new Set(reviews.map(review => review.source))].forEach(source => state.sources.add(source));
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
  state.topic = "all";
  state.search = "";
  state.reviewLimit = 12;
  $$('input[name="dateMode"]').forEach(input => input.checked = input.value === "analysis");
  $$('input[name="product"], input[name="source"], input[name="rating"]').forEach(input => input.checked = true);
  syncSet("product", state.products);
  syncSet("source", state.sources);
  syncSet("rating", state.ratings, Number);
  $("#topicFilter").value = "all";
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

function render() {
  const reviews = filteredReviews();
  renderKPIs(reviews);
  renderTrend(reviews);
  renderRatingDistribution(reviews);
  renderSourceMix(reviews);
  renderThemes(reviews);
  renderProductTable();
  renderSnapshots();
  renderReviews(reviews);
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
  $("#kpiCoverage").textContent = state.dateMode === "analysis" ? "Nov 2024–Jul 2026" : "Complete captured archive";
  $("#kpiRating").textContent = fmtRating(rating);
  $("#kpiLow").textContent = fmtPct(percent(lowCount, reviews.length));
  $("#kpiLowNote").textContent = `${lowCount} low-rating review${lowCount === 1 ? "" : "s"}`;
  $("#kpiTexture").textContent = fmtPct(percent(textureCount, reviews.length));
  $("#kpiTaste").textContent = fmtPct(percent(tasteCount, reviews.length));
}

function groupByMonth(reviews) {
  const groups = {};
  reviews.forEach(review => { const month = review.date.slice(0, 7); (groups[month] ||= []).push(review); });
  if (!reviews.length) return [];
  const dates = reviews.map(review => review.date).sort();
  const start = new Date(`${dates[0].slice(0, 7)}-01T00:00:00`);
  const end = new Date(`${dates.at(-1).slice(0, 7)}-01T00:00:00`);
  const months = [];
  for (const cursor = new Date(start); cursor <= end; cursor.setMonth(cursor.getMonth() + 1)) months.push(`${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}`);
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
  const values = groups.map(metricForGroup);
  const meta = {
    rating: { label: "Average rating", max: 5, suffix: "" },
    low: { label: "1–2 star share", max: 100, suffix: "%" },
    texture: { label: "Texture mention share", max: 100, suffix: "%" },
    volume: { label: "Review volume", max: Math.max(5, ...values.filter(Number.isFinite)) * 1.15, suffix: "" },
  }[state.trendMetric];
  $("#trendLegend").textContent = meta.label;
  const pad = { left: 43, right: 15, top: 14, bottom: 35 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  ctx.font = "10px Segoe UI, Arial";
  ctx.textBaseline = "middle";
  ctx.strokeStyle = "#dfe6e9";
  ctx.fillStyle = "#7b8991";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + plotH * i / 4;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    const value = meta.max * (1 - i / 4);
    ctx.fillText(state.trendMetric === "rating" ? value.toFixed(1) : Math.round(value).toString(), 6, y);
  }
  if (!groups.length) {
    ctx.fillStyle = "#73828b"; ctx.textAlign = "center"; ctx.font = "13px Segoe UI, Arial";
    ctx.fillText("No reviews match the current filters", width / 2, height / 2);
    chartPoints = [];
    return;
  }
  const xAt = index => groups.length === 1 ? pad.left + plotW / 2 : pad.left + index / (groups.length - 1) * plotW;
  const yAt = value => pad.top + (1 - value / meta.max) * plotH;
  const cutoffIndex = groups.findIndex(group => group.month === "2025-11");
  if (cutoffIndex >= 0) {
    const x = xAt(cutoffIndex);
    ctx.strokeStyle = "#e77a3e"; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + plotH); ctx.stroke(); ctx.setLineDash([]);
  }
  ctx.fillStyle = "#7b8991"; ctx.textAlign = "center"; ctx.font = "9px Segoe UI, Arial";
  groups.forEach((group, index) => { if (index % Math.max(1, Math.ceil(groups.length / 8)) === 0 || index === groups.length - 1) ctx.fillText(monthLabel(group.month, true), xAt(index), height - 13); });
  ctx.strokeStyle = "#246fa8"; ctx.lineWidth = 2.5; ctx.lineJoin = "round"; ctx.lineCap = "round";
  let drawing = false;
  ctx.beginPath();
  values.forEach((value, index) => {
    if (!Number.isFinite(value)) { drawing = false; return; }
    const x = xAt(index), y = yAt(value);
    if (!drawing) { ctx.moveTo(x, y); drawing = true; } else ctx.lineTo(x, y);
  });
  ctx.stroke();
  chartPoints = [];
  values.forEach((value, index) => {
    if (!Number.isFinite(value)) return;
    const x = xAt(index), y = yAt(value);
    ctx.fillStyle = "white"; ctx.strokeStyle = "#246fa8"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y, 3.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    chartPoints.push({ x, y, month: groups[index].month, value, n: groups[index].reviews.length, suffix: meta.suffix, label: meta.label });
  });
  $("#trendTable").textContent = groups.map((group, index) => `${monthLabel(group.month)}: ${Number.isFinite(values[index]) ? values[index].toFixed(state.trendMetric === "volume" ? 0 : 1) + meta.suffix : "no data"}, ${group.reviews.length} reviews`).join("; ");
}

function showChartTooltip(event) {
  if (!chartPoints.length) return;
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const nearest = chartPoints.reduce((best, point) => Math.abs(point.x - x) < Math.abs(best.x - x) ? point : best, chartPoints[0]);
  if (Math.abs(nearest.x - x) > 28) { $("#chartTooltip").hidden = true; return; }
  const tooltip = $("#chartTooltip");
  tooltip.innerHTML = `<strong>${monthLabel(nearest.month)}</strong>${escapeHTML(nearest.label)}: ${nearest.value.toFixed(state.trendMetric === "volume" ? 0 : 1)}${nearest.suffix}<br>${nearest.n} review${nearest.n === 1 ? "" : "s"}`;
  tooltip.style.left = `${nearest.x}px`;
  tooltip.style.top = `${nearest.y}px`;
  tooltip.hidden = false;
}

function renderRatingDistribution(reviews) {
  const counts = [5, 4, 3, 2, 1].map(star => ({ star, count: reviews.filter(review => Number(review.rating) === star).length }));
  $("#ratingDistribution").innerHTML = counts.map(({ star, count }) => {
    const share = percent(count, reviews.length) || 0;
    return `<div class="bar-row"><span>${star} star</span><div class="bar-track"><i style="width:${share}%"></i></div><strong>${share.toFixed(0)}%</strong></div>`;
  }).join("");
}

function renderSourceMix(reviews) {
  const counts = [...new Set(data.reviews.map(review => review.source))].map(source => ({ source, count: reviews.filter(review => review.source === source).length })).sort((a, b) => b.count - a.count);
  const stack = counts.map(({ source, count }, index) => `<i title="${escapeHTML(source)}: ${count}" style="width:${percent(count, reviews.length) || 0}%;background:${COLORS[index]}"></i>`).join("");
  const legend = counts.map(({ source, count }, index) => `<div><i style="background:${COLORS[index]}"></i><span>${escapeHTML(source)}</span><strong>${count}</strong></div>`).join("");
  $("#sourceMix").innerHTML = `<div class="source-stack">${stack}</div><div class="source-legend">${legend}</div>`;
}

function renderThemes(reviews) {
  $("#themeBars").innerHTML = Object.entries(TOPICS).map(([key, topic]) => {
    const count = reviews.filter(review => review.topics[key]).length;
    const share = percent(count, reviews.length) || 0;
    return `<article class="theme-card"><header><span>${topic.label}</span><strong>${share.toFixed(1)}%</strong></header><div class="theme-meter"><i style="width:${share}%"></i></div><small>${count} matching review${count === 1 ? "" : "s"}</small></article>`;
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
      <td><span class="status-pill ${row.n ? "" : "gap"}">${row.n ? "Written reviews" : "Coverage gap"}</span></td>
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
  $("#retailerSnapshots").innerHTML = data.retailers.rating_snapshots.map(snapshot => {
    const average = snapshot.rating_count ? Object.entries(snapshot.distribution).reduce((sum, [star, count]) => sum + Number(star) * count, 0) / snapshot.rating_count : null;
    const bars = [5, 4, 3, 2, 1].map(star => {
      const count = snapshot.distribution[String(star)] || 0;
      return `<div><span>${star}</span><i><b style="width:${percent(count, snapshot.rating_count) || 0}%"></b></i><span>${count}</span></div>`;
    }).join("");
    const product = data.registry.products.find(item => item.id === snapshot.product_id);
    const page = product?.retailer_pages?.[snapshot.source.toLowerCase()];
    return `<article class="snapshot-card"><header><span>${escapeHTML(snapshot.source)}</span><strong>${escapeHTML(productNames[snapshot.product_id])}</strong></header><div class="snapshot-score"><strong>${fmtRating(average)}</strong><span>${snapshot.rating_count} rating${snapshot.rating_count === 1 ? "" : "s"}</span></div><div class="snapshot-stars">${bars}</div><p>${escapeHTML(snapshot.page_status)}${page ? `<br><a href="${escapeHTML(page)}" target="_blank" rel="noopener noreferrer">Open retailer page ↗</a>` : ""}</p></article>`;
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
      return `<article class="review-card"><div class="review-rating" aria-label="${review.rating} out of 5 stars">${stars}<small>${review.date}</small></div><div class="review-copy"><h3>${escapeHTML(review.title || "Untitled review")}</h3><p>${escapeHTML(review.text || "No written comment captured.")}</p></div><div class="review-meta"><strong>${escapeHTML(review.product)}</strong><span>${escapeHTML(review.source)} · ${escapeHTML(review.capture)}</span><div class="topic-tags">${tags}</div></div></article>`;
    }).join("");
  }
  $("#loadMore").hidden = state.reviewLimit >= reviews.length;
}

function exportCSV() {
  const reviews = sortedReviews(filteredReviews());
  if (!reviews.length) { showToast("No reviews to export"); return; }
  const columns = ["product", "source", "date", "rating", "title", "text", "capture", ...Object.keys(TOPICS)];
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
