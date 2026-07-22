import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const read = file => JSON.parse(fs.readFileSync(path.join(root, file), "utf8"));
const fail = message => { throw new Error(message); };

const reviews = read("data/reviews_normalized.json").filter(row => row.metric_eligible !== false);
const allCompetitors = read("data/competitor_reviews_normalized.json");
const competitors = allCompetitors.filter(row => row.metric_eligible !== false);
const registry = read("data/competitor_sku_registry.json");
const snapshots = read("data/competitor_rating_snapshots.json").snapshots;
const coverage = read("data/competitor_coverage_audit.json").rows;
const kevinRegistry = read("data/sku_registry.json");
const kevinCoverage = read("data/kevin_retailer_match_audit.json").rows;

if (reviews.length !== 638) fail(`Kevin's baseline changed: expected 638, found ${reviews.length}`);
if (competitors.length !== 202) fail(`Expected 202 quality-eligible competitor text reviews, found ${competitors.length}`);
if (allCompetitors.filter(row => row.metric_eligible === false && row.quality_status === "excluded_shared_variant_without_review_level_size").length !== 10) fail("Expected 10 auditable shared-variant exclusions");
if (registry.products.length !== 13) fail(`Expected 13 normalized competitor products, found ${registry.products.length}`);
if (registry.benchmark_rules.archive_end !== "2026-07-22") fail("Competitor archive end is stale");
if (registry.products.filter(product => product.benchmark_tier === "core").length !== 8) fail("Expected 8 core products");
if (snapshots.length !== 21) fail(`Expected 21 competitor rating snapshots, found ${snapshots.length}`);
if (coverage.length !== 78) fail(`Expected 78 product/source audit rows, found ${coverage.length}`);
if (kevinRegistry.products.length !== 8) fail(`Expected 8 Kevin's products, found ${kevinRegistry.products.length}`);
if (kevinCoverage.length !== 48) fail(`Expected 48 Kevin's product/source audit rows, found ${kevinCoverage.length}`);
if (kevinRegistry.products.some(product => !product.shopify_product_id || !product.find_a_store_url || !product.upcs.length)) fail("Kevin's owned-site product identity is incomplete");

const ids = new Set(registry.products.map(product => product.id));
const providerKeys = new Set();
for (const row of competitors) {
  if (!ids.has(row.product_id)) fail(`Unknown competitor product_id ${row.product_id}`);
  if (row.date < "2023-01-01" || row.date > "2026-07-22") fail(`Out-of-scope date ${row.date}`);
  if (![1, 2, 3, 4, 5].includes(Number(row.rating))) fail(`Invalid rating ${row.rating}`);
  if (!String(row.text || "").trim()) fail("Blank competitor review text");
  const key = `${row.source}|${row.provider_review_id}`;
  if (providerKeys.has(key)) fail(`Duplicate source review ${key}`);
  providerKeys.add(key);
}
if (snapshots.filter(row => row.source === "Kroger" && row.capture_status === "rating_total_only_public_text_payload_unavailable").length !== 6) fail("Expected six exact-SKU Kroger rating totals");
if (snapshots.filter(row => row.source === "Amazon").length !== 5) fail("Expected five audited Amazon aggregate-rating snapshots");
if (snapshots.filter(row => row.source === "Amazon" && row.metric_eligible !== false).length !== 3) fail("Expected three exact-SKU Amazon aggregates eligible for total-rating context");
if (snapshots.some(row => Object.keys(row.distribution || {}).length && Object.values(row.distribution).reduce((sum, value) => sum + Number(value), 0) !== Number(row.rating_count))) fail("Competitor rating distribution total mismatch");

console.log(JSON.stringify({
  kevin_metric_reviews: reviews.length,
  competitor_text_reviews: competitors.length,
  competitor_excluded_shared_variant_reviews: allCompetitors.length - competitors.length,
  competitor_products: registry.products.length,
  core_products: 8,
  competitor_snapshots: snapshots.length,
  coverage_rows: coverage.length,
  kevin_product_source_rows: kevinCoverage.length,
  competitor_date_range: [competitors.map(row => row.date).sort()[0], competitors.map(row => row.date).sort().at(-1)],
}, null, 2));
