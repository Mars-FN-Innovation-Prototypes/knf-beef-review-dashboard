# Beef HMR Review Intelligence

Interactive, static dashboard for exploring written consumer reviews across eight Kevin's Natural Foods beef HMR products.

## Included data

- 638 metric-eligible full-text reviews spanning January 1, 2023 through July 22, 2026
- 422 first-party product-page reviews across all eight scoped products, plus retailer evidence from Target, Amazon, Kroger, and Walmart
- A defined trend window from November 1, 2024 through July 22, 2026
- Separate first-party and retailer rating snapshots that are not blended into written-review trends
- Owned-site identity verification for all eight scoped products and barcode-led matching across Brand, Target, Amazon, Kroger, Walmart, and Costco, with Costco 32 oz club packs separated from exact 16 oz SKUs
- Exact scope limited to the eight products specified for the analysis
- Two rating-only records retained as context but excluded from written-review KPIs
- An optional 13-product competitor registry derived from the supplied benchmark list: eight core 14-20 oz products and five adjacent pack/form-factor comparators
- 202 quality-eligible dated competitor written reviews: 132 complete Hormel first-party records and 70 bounded Walmart public-page records
- Ten unresolved Walmart Soules 6 oz/14 oz shared-variant records retained for auditability but excluded from product metrics
- Ten complete point-in-time rating distributions plus six exact-SKU Kroger rating totals, all kept separate from the written-review trend layer

## Dashboard capabilities

- Coordinated filters for date coverage, product, source, star rating, topic, and review text
- Responsive monthly trend chart with selectable metrics
- Rating, source, topic, and product-level comparisons
- First-party and retailer rating-distribution snapshots
- Product-by-retailer coverage matrix with exact-SKU and club-pack labeling
- Searchable review explorer and filtered CSV export
- Transparent methodology, exclusions, and limitations
- Opt-in competitor overlays on KPIs, monthly trends, rating distribution, and topic prevalence; the default remains Kevin's-only
- Executive competitor comparison with Trend Written, Full Written, and Total Ratings views; paired average-rating and 1-2-star-share visuals retain sample and source-page context
- Core versus expanded competitor selection, equal-product and review-weighted benchmark views, product evidence status, and retailer snapshot context
- Amazon aggregate-rating context for three exact core competitor SKUs, with a birria taco kit and Mama Mancini's multipack retained as clearly excluded variant evidence

## Collection methodology

- Product matching uses the eight-product registry, exact first-party product handles, UPCs where available, and pack-size checks.
- First-party review pages were retrieved through their public storefront review feed and filtered to January 1, 2023 through July 22, 2026.
- Walmart's complete public set of 48 written Honey Garlic reviews was paginated and retained with stable provider review IDs. Current Target totals and two incremental reviews were reconciled against the existing archive.
- Amazon remains a clearly labeled 20-review public first-page sample across two Mongolian ASINs because deeper review pages require sign-in.
- Review HTML was converted to plain text; provider review IDs, verification status, source URLs, and provenance labels were retained. Reviewer names were intentionally omitted.
- Exact source-level duplicates and same-day cross-source duplicates were removed before analysis.
- Indexed summaries, analyst summaries, and rating-only entries remain in the archive for traceability but do not contribute to written-review metrics.

### Competitor benchmark

- The supplied product names were normalized into canonical products using brand, product name, pack size, UPC/item identifiers, and exact public product pages. Duplicate Hormel Beef Tips descriptions and the Jack Daniel's pack-title variants were merged to avoid double counting.
- The public Hormel PowerReviews feeds provide the complete first-party histories displayed within the 2023-2026 scope. Walmart product pages provide a bounded public server-rendered text sample plus complete point-in-time rating distributions for the listed pages.
- Walmart shares the Soules 6 oz and 14 oz review family. Records without a review-level size are excluded from product metrics rather than assigned by page title. Kroger contributes exact-SKU rating totals only because its written review payload was not reproducibly public.
- Target, Amazon, Kroger, Walmart, Costco, and brand sites were audited across all 13 products. Listings without defensible dated text remain coverage context and are not manufactured into review metrics.
- Competitor volume is sample-dependent and is not a market-share measure. Rating snapshots never enter the dated review trend, topic coding, or text-review KPIs.
- `scripts/collect_competitor_reviews.py` refreshes public benchmark evidence and safely falls back to the last verified Walmart sample when the retailer blocks automated access. `scripts/build_competitor_verified_evidence.mjs` applies the deterministic quality rules; reviewer names are not retained.

The site has no runtime dependencies and can be hosted directly with GitHub Pages.
