import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dataDir = path.join(root, "data");
const cachePath = path.join(dataDir, "competitor_walmart_public_sample_2026-07-21.json");
const reviewPath = path.join(dataDir, "competitor_reviews_normalized.json");
const snapshotPath = path.join(dataDir, "competitor_rating_snapshots.json");
const coveragePath = path.join(dataDir, "competitor_coverage_audit.json");
const registry = JSON.parse(fs.readFileSync(path.join(dataDir, "competitor_sku_registry.json"), "utf8"));
const products = new Map(registry.products.map(product => [product.id, product]));

function readHeadJson(relativePath) {
  return JSON.parse(execFileSync("git", ["show", `HEAD:${relativePath}`], { cwd: root, encoding: "utf8", maxBuffer: 50 * 1024 * 1024 }));
}

if (process.argv.includes("--seed-from-head")) {
  const reviews = readHeadJson("data/competitor_reviews_normalized.json").filter(row => row.source === "Walmart");
  const snapshots = readHeadJson("data/competitor_rating_snapshots.json").snapshots.filter(row => row.source === "Walmart");
  fs.writeFileSync(cachePath, `${JSON.stringify({
    captured_at: "2026-07-21",
    acquisition: "Public server-rendered Walmart review pages; one visible page per item.",
    limitation: "This is a bounded public-page text sample. It is not the full Walmart written-review archive.",
    reviews,
    snapshots,
  }, null, 2)}\n`);
}

if (!fs.existsSync(cachePath)) throw new Error("Verified Walmart cache missing; seed it from the last accepted dataset first.");

const priorReviews = readHeadJson("data/competitor_reviews_normalized.json");
const priorSnapshots = readHeadJson("data/competitor_rating_snapshots.json").snapshots;
const cache = JSON.parse(fs.readFileSync(cachePath, "utf8"));

const firstPartyReviews = priorReviews.filter(row => row.source === "Hormel");
const firstPartySnapshots = priorSnapshots.filter(row => row.source === "Hormel");

const sharedSoulesIds = new Set(["soules_beef_fajitas_14", "soules_fajita_steak_6"]);
const walmartReviews = cache.reviews.map(row => {
  if (!sharedSoulesIds.has(row.product_id)) return {
    ...row,
    capture: "bounded public review-page sample",
    quality_status: "accepted_exact_listed_sku_sample",
  };
  return {
    ...row,
    metric_eligible: false,
    capture: "bounded public review-page sample; excluded from product metrics",
    quality_status: "excluded_shared_variant_without_review_level_size",
    exclusion_reason: "Walmart syndicates this review family across 6 oz and 14 oz pages; the retained record lacks a review-level size field.",
  };
});

const walmartSnapshots = cache.snapshots
  .filter(row => row.product_id !== "soules_fajita_steak_6")
  .map(row => {
    if (row.product_id === "soules_beef_fajitas_14") return {
      ...row,
      captured_written_reviews: 0,
      capture_status: "complete_rating_distribution_shared_variant_text_excluded",
      snapshot_scope: "shared_variant_family",
      related_product_ids: ["soules_beef_fajitas_14", "soules_fajita_steak_6"],
      quality_note: "The rating distribution is shared across the Walmart Soules Fajita Steak variant family. Unresolved written text is excluded from product-level metrics.",
    };
    return {
      ...row,
      capture_status: "bounded_public_text_sample_plus_complete_rating_distribution",
      snapshot_scope: "listed_sku_page",
      quality_note: "Written reviews are a bounded public-page sample; the point-in-time rating distribution is complete for the listed page.",
    };
  });

const krogerRatings = {
  hormel_roast_au_jus_15: [3.66, 35],
  hormel_beef_tips_gravy_15: [2.95, 22],
  soules_beef_fajitas_14: [4.50, 1199],
  brookwood_brisket_16: [3.00, 6],
  del_real_barbacoa_15: [4.26, 138],
  del_real_birria_15: [4.13, 54],
};

const krogerSnapshots = Object.entries(krogerRatings).map(([productId, [averageRating, ratingCount]]) => {
  const product = products.get(productId);
  return {
    product_id: productId,
    product: product.name,
    brand: product.brand,
    source: "Kroger",
    provider: "Kroger",
    page_url: product.retailer_pages.kroger,
    average_rating: averageRating,
    rating_count: ratingCount,
    written_review_count: null,
    distribution: {},
    captured_written_reviews: 0,
    capture_status: "rating_total_only_public_text_payload_unavailable",
    snapshot_scope: "exact_listed_sku",
    quality_note: "Exact-SKU public rating total; review text was not exposed in a reproducible public payload and is excluded from text metrics.",
    as_of: "2026-07-22",
  };
});

const reviews = [...firstPartyReviews, ...walmartReviews].sort((a, b) => b.date.localeCompare(a.date) || a.product_id.localeCompare(b.product_id));
const snapshots = [...firstPartySnapshots, ...walmartSnapshots, ...krogerSnapshots];

const relatedVariants = new Map([
  ["soules_beef_fajitas_14|Target", {
    url: "https://www.target.com/p/john-soules-foods-fully-cooked-beef-fajitas-frozen-12oz/-/A-14871276",
    note: "Related 12 oz frozen pack (791 ratings), excluded from the supplied 14 oz refrigerated benchmark.",
  }],
  ["del_real_barbacoa_15|Target", {
    url: "https://www.target.com/p/-/A-84724173",
    note: "Related 12 oz pack (434 ratings), excluded from the supplied 15 oz benchmark.",
  }],
]);

const sourceKeys = { Brand: "brand", Target: "target", Amazon: "amazon", Kroger: "kroger", Walmart: "walmart", Costco: "costco" };
const snapshotKeys = new Set(snapshots.map(row => `${row.product_id}|${row.source}`));
const reviewKeys = new Set(reviews.filter(row => row.metric_eligible !== false).map(row => `${row.product_id}|${row.source}`));
const coverageRows = [];

for (const product of registry.products) {
  for (const [source, key] of Object.entries(sourceKeys)) {
    const evidenceSource = source === "Brand" ? product.brand : source;
    const evidenceKey = `${product.id}|${evidenceSource}`;
    const pageUrl = product.retailer_pages?.[key];
    const searchUrl = product.retailer_pages?.[`${key}_search`];
    const related = relatedVariants.get(`${product.id}|${source}`);
    let status = "not_located";
    let matchType = "not_located";
    let resolvedUrl = null;
    let note = null;

    if (pageUrl) {
      resolvedUrl = pageUrl;
      matchType = source === "Costco" && product.pack_oz <= 20 ? "club_pack_variant" : "exact_listed_sku";
      if (reviewKeys.has(evidenceKey)) status = "review_evidence";
      else if (snapshotKeys.has(evidenceKey)) status = "rating_evidence";
      else status = "listing_only";
      if (product.id === "soules_fajita_steak_6" && source === "Walmart") {
        status = "shared_variant_rating_context";
        matchType = "exact_variant_page_shared_review_family";
        note = "The page shares reviews and aggregate ratings with the 14 oz variant; unresolved written text is excluded from product metrics.";
      }
    } else if (searchUrl) {
      resolvedUrl = searchUrl;
      matchType = "search_only";
      status = "exact_page_not_confirmed";
    } else if (related) {
      resolvedUrl = related.url;
      matchType = "different_pack_size";
      status = "related_variant_excluded";
      note = related.note;
    }

    coverageRows.push({
      product_id: product.id,
      brand: product.brand,
      product: product.name,
      benchmark_tier: product.benchmark_tier,
      source,
      status,
      match_type: matchType,
      pack_oz: product.pack_oz,
      page_url: resolvedUrl,
      note,
    });
  }
}

fs.writeFileSync(reviewPath, `${JSON.stringify(reviews, null, 2)}\n`);
fs.writeFileSync(snapshotPath, `${JSON.stringify({
  as_of: "2026-07-22",
  method_note: "Hormel review text is a complete public first-party feed within the 2023-present scope. Walmart text is a bounded server-rendered public-page sample; shared Soules 6 oz/14 oz records without review-level size are excluded from product metrics. Kroger contributes exact-SKU point-in-time rating totals only because a reproducible public review-text payload was unavailable. Rating totals never enter dated text metrics.",
  snapshots,
}, null, 2)}\n`);
fs.writeFileSync(coveragePath, `${JSON.stringify({
  as_of: "2026-07-22",
  sources_audited: ["Brand", "Target", "Amazon", "Kroger", "Walmart", "Costco"],
  quality_rules: [
    "Exact supplied SKU or explicitly labeled pack/form-factor variant only.",
    "Rating totals are separated from dated written-review metrics.",
    "Shared retailer review families are excluded unless a review-level variant identifier resolves the record.",
    "Search results and related pack sizes are coverage context, not review evidence.",
  ],
  rows: coverageRows,
}, null, 2)}\n`);

const eligible = reviews.filter(row => row.metric_eligible !== false);
console.log(JSON.stringify({
  eligible_written_reviews: eligible.length,
  excluded_shared_variant_reviews: reviews.length - eligible.length,
  snapshots: snapshots.length,
  coverage_rows: coverageRows.length,
  sources: Object.fromEntries([...new Set(eligible.map(row => row.source))].map(source => [source, eligible.filter(row => row.source === source).length])),
}, null, 2));
