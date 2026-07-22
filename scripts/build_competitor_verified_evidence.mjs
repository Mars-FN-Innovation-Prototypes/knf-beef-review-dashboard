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

function apportionedDistribution(ratingCount, percentages) {
  const entries = Object.entries(percentages).map(([star, share]) => {
    const exact = ratingCount * share / 100;
    return { star, count: Math.floor(exact), remainder: exact - Math.floor(exact) };
  });
  let remaining = ratingCount - entries.reduce((sum, row) => sum + row.count, 0);
  entries.sort((a, b) => b.remainder - a.remainder || Number(b.star) - Number(a.star));
  for (let index = 0; index < remaining; index += 1) entries[index].count += 1;
  return Object.fromEntries(entries.sort((a, b) => Number(a.star) - Number(b.star)).map(row => [row.star, row.count]));
}

const amazonRatings = [
  {
    productId: "hormel_roast_au_jus_15",
    asin: "B0012S1M6A",
    averageRating: 4.5,
    ratingCount: 3069,
    percentages: { 1: 2, 2: 1, 3: 9, 4: 15, 5: 73 },
    scope: "exact_listed_sku",
    metricEligible: true,
  },
  {
    productId: "hormel_beef_tips_gravy_15",
    asin: "B01ITAXT3M",
    averageRating: 4.4,
    ratingCount: 3361,
    percentages: { 1: 4, 2: 3, 3: 8, 4: 11, 5: 74 },
    scope: "exact_listed_sku",
    metricEligible: true,
  },
  {
    productId: "del_real_barbacoa_15",
    asin: "B00AFYPGCS",
    averageRating: 4.3,
    ratingCount: 1026,
    percentages: { 1: 7, 2: 4, 3: 10, 4: 12, 5: 67 },
    scope: "exact_listed_sku",
    metricEligible: true,
  },
  {
    productId: "del_real_birria_15",
    asin: "B0BFDG62H2",
    averageRating: 4.0,
    ratingCount: 564,
    percentages: { 1: 11, 2: 8, 3: 9, 4: 11, 5: 61 },
    scope: "related_birria_taco_kit",
    metricEligible: false,
    productLabel: "Beef Birria Taco Kit (related variant)",
    qualityNote: "This Amazon page is a prepared taco kit with beef, consomme, and tortillas, not the supplied 15 oz seasoned beef birria entree. Its aggregate is shown as related channel context and excluded from benchmark metrics.",
  },
  {
    productId: "mama_mancinis_meatballs_48",
    asin: "B0CVSJM9CF",
    averageRating: 4.6,
    ratingCount: 35,
    percentages: null,
    scope: "multipack_of_exact_48oz_unit",
    metricEligible: false,
    qualityNote: "The listing is a pack of three 48 oz units. The aggregate is retained as multipack context; Amazon did not expose a star-distribution table on the inspected page.",
  },
];

const amazonSnapshots = amazonRatings.map(row => {
  const product = products.get(row.productId);
  return {
    product_id: row.productId,
    product: row.productLabel || product.name,
    brand: product.brand,
    source: "Amazon",
    provider: "Amazon",
    page_url: `https://www.amazon.com/dp/${row.asin}`,
    item_id: row.asin,
    average_rating: row.averageRating,
    rating_count: row.ratingCount,
    written_review_count: null,
    distribution: row.percentages ? apportionedDistribution(row.ratingCount, row.percentages) : {},
    distribution_percent: row.percentages || {},
    distribution_basis: row.percentages ? "source_rounded_percentages_apportioned_to_rating_total" : "not_available",
    captured_written_reviews: 0,
    capture_status: row.metricEligible ? "amazon_aggregate_exact_sku_no_dated_text" : "amazon_aggregate_related_variant_excluded",
    snapshot_scope: row.scope,
    metric_eligible: row.metricEligible,
    quality_note: row.qualityNote || "Exact-SKU Amazon aggregate. Star counts are apportioned to the published rating total from Amazon's rounded percentage distribution; dated written-review text is not included.",
    as_of: "2026-07-22",
  };
});

const reviews = [...firstPartyReviews, ...walmartReviews].sort((a, b) => b.date.localeCompare(a.date) || a.product_id.localeCompare(b.product_id));
const snapshots = [...firstPartySnapshots, ...walmartSnapshots, ...krogerSnapshots, ...amazonSnapshots];

const relatedVariants = new Map([
  ["soules_beef_fajitas_14|Target", {
    url: "https://www.target.com/p/john-soules-foods-fully-cooked-beef-fajitas-frozen-12oz/-/A-14871276",
    note: "Related 12 oz frozen pack (791 ratings), excluded from the supplied 14 oz refrigerated benchmark.",
  }],
  ["del_real_barbacoa_15|Target", {
    url: "https://www.target.com/p/-/A-84724173",
    note: "Related 12 oz pack (434 ratings), excluded from the supplied 15 oz benchmark.",
  }],
  ["del_real_birria_15|Amazon", {
    url: "https://www.amazon.com/dp/B0BFDG62H2",
    matchType: "different_product_format",
    note: "Related beef birria taco kit (564 ratings), excluded from the supplied 15 oz seasoned beef birria benchmark.",
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
      if (product.id === "mama_mancinis_meatballs_48" && source === "Amazon") {
        matchType = "multipack_of_exact_48oz_unit";
        note = "Amazon lists a pack of three 48 oz units. Its 35-rating aggregate is retained as multipack context and excluded from like-for-like benchmark totals.";
      }
    } else if (searchUrl) {
      resolvedUrl = searchUrl;
      matchType = "search_only";
      status = "exact_page_not_confirmed";
    } else if (related) {
      resolvedUrl = related.url;
      matchType = related.matchType || "different_pack_size";
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
  method_note: "Hormel review text is a complete public first-party feed within the 2023-present scope. Walmart text is a bounded server-rendered public-page sample; shared Soules 6 oz/14 oz records without review-level size are excluded from product metrics. Kroger contributes exact-SKU point-in-time rating totals only. Amazon contributes exact-SKU aggregate ratings for three core products; rounded star percentages are apportioned to the published totals, while a related birria taco kit and a Mama Mancini's multipack remain excluded context. Rating totals never enter dated text metrics.",
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
