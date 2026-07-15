# Beef HMR Review Intelligence

Interactive, static dashboard for exploring written consumer reviews across eight Kevin's Natural Foods beef HMR products.

## Included data

- 588 metric-eligible full-text reviews spanning January 1, 2023 through July 15, 2026
- 422 first-party product-page reviews across all eight scoped products, plus retailer evidence from Target, Amazon, and Kroger
- A defined trend window from November 1, 2024 through July 15, 2026
- Separate first-party and retailer rating snapshots that are not blended into written-review trends
- Kroger, Walmart, and Costco assortment coverage, with Costco 32 oz club packs separated from exact 16 oz SKUs
- Exact scope limited to the eight products specified for the analysis
- Five indexed-summary, analyst-summary, or rating-only records retained as context but excluded from written-review KPIs

## Dashboard capabilities

- Coordinated filters for date coverage, product, source, star rating, topic, and review text
- Responsive monthly trend chart with selectable metrics
- Rating, source, topic, and product-level comparisons
- First-party and retailer rating-distribution snapshots
- Product-by-retailer coverage matrix with exact-SKU and club-pack labeling
- Searchable review explorer and filtered CSV export
- Transparent methodology, exclusions, and limitations

## Collection methodology

- Product matching uses the eight-product registry, exact first-party product handles, UPCs where available, and pack-size checks.
- First-party review pages were retrieved through their public storefront review feed and filtered to January 1, 2023 through July 15, 2026.
- Review HTML was converted to plain text; provider review IDs, verification status, source URLs, and provenance labels were retained. Reviewer names were intentionally omitted.
- Exact source-level duplicates and same-day cross-source duplicates were removed before analysis.
- Indexed summaries, analyst summaries, and rating-only entries remain in the archive for traceability but do not contribute to written-review metrics.

The site has no runtime dependencies and can be hosted directly with GitHub Pages.
