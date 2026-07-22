import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const read = file => JSON.parse(fs.readFileSync(path.join(root, file), "utf8"));
const fail = message => { throw new Error(message); };

const reviews = read("data/reviews_normalized.json").filter(row => row.metric_eligible !== false);
const competitors = read("data/competitor_reviews_normalized.json").filter(row => row.metric_eligible !== false);
const registry = read("data/competitor_sku_registry.json");
const snapshots = read("data/competitor_rating_snapshots.json").snapshots;
const coverage = read("data/competitor_coverage_audit.json").rows;
const kevinRegistry = read("data/sku_registry.json");
const kevinCoverage = read("data/kevin_retailer_match_audit.json").rows;

if (reviews.length !== 638) fail(`Kevin's baseline changed: expected 638, found ${reviews.length}`);
if (competitors.length !== 212) fail(`Expected 212 competitor text reviews, found ${competitors.length}`);
if (registry.products.length !== 13) fail(`Expected 13 normalized competitor products, found ${registry.products.length}`);
if (registry.products.filter(product => product.benchmark_tier === "core").length !== 8) fail("Expected 8 core products");
if (snapshots.length !== 11) fail(`Expected 11 competitor rating snapshots, found ${snapshots.length}`);
if (coverage.length !== 78) fail(`Expected 78 product/source audit rows, found ${coverage.length}`);
if (kevinRegistry.products.length !== 8) fail(`Expected 8 Kevin's products, found ${kevinRegistry.products.length}`);
if (kevinCoverage.length !== 48) fail(`Expected 48 Kevin's product/source audit rows, found ${kevinCoverage.length}`);
if (kevinRegistry.products.some(product => !product.shopify_product_id || !product.find_a_store_url || !product.upcs.length)) fail("Kevin's owned-site product identity is incomplete");

const ids = new Set(registry.products.map(product => product.id));
const providerKeys = new Set();
for (const row of competitors) {
  if (!ids.has(row.product_id)) fail(`Unknown competitor product_id ${row.product_id}`);
  if (row.date < "2023-01-01" || row.date > "2026-07-15") fail(`Out-of-scope date ${row.date}`);
  if (![1, 2, 3, 4, 5].includes(Number(row.rating))) fail(`Invalid rating ${row.rating}`);
  if (!String(row.text || "").trim()) fail("Blank competitor review text");
  const key = `${row.source}|${row.provider_review_id}`;
  if (providerKeys.has(key)) fail(`Duplicate source review ${key}`);
  providerKeys.add(key);
}

console.log(JSON.stringify({
  kevin_metric_reviews: reviews.length,
  competitor_text_reviews: competitors.length,
  competitor_products: registry.products.length,
  core_products: 8,
  competitor_snapshots: snapshots.length,
  coverage_rows: coverage.length,
  kevin_product_source_rows: kevinCoverage.length,
  competitor_date_range: [competitors.map(row => row.date).sort()[0], competitors.map(row => row.date).sort().at(-1)],
}, null, 2));
