# KNF Review Intelligence

Interactive, static dashboard with separately managed Beef HMR, Stir-Fry and Portfolio Trends analysis modules.

## Portfolio Trends — September 9, 2026

Open `portfolio.html` or choose **Portfolio** in the use-case switch. The original modules and their governed datasets are unchanged.

- 105 current individual food products plus one verified historical listing; 11 categories.
- 5,646 deduplicated dated ratings, July 1, 2024–September 9, 2026, across 89 products. 5,109 are from retrieved public histories; 537 are partial or earlier-archive evidence.
- Default: 4,015 ratings across Q3 2024–Q2 2026. Six completed quarters and current-quarter-to-date are optional.
- Review-weighted, equal-product and fixed comparable-product/source views; source/category overlays; product/format/current-assortment/incentive filters; quarter drill-down and review explorer.
- PNG/SVG chart export and CSV exports of quarterly metrics, selected reviews and listing coverage.
- Cumulative rating snapshots remain separate. Legacy/current brand provider reconciliation, incomplete retailer pagination and unconfirmed listings remain explicitly disclosed gaps; this is not complete market coverage.

See [collection summary](downloads/KNF_Portfolio_Trends_Collection_Summary.md) and [validation report](data/portfolio_validation.json).

### Rebuild and validate the frozen portfolio snapshot

```text
python scripts/build_portfolio.py
node portfolio-tests.mjs
node tests.mjs
python scripts/qa_portfolio.py
python -m http.server 8765
```

The default build uses committed `data/portfolio_source_evidence.json` and `data/portfolio_product_registry.json`; no network or credentials are required. The QA script performs additional raw-record checks when the local raw cache exists. The static application fetches only the summary and normalized records, not the larger evidence archive. Collection helpers are standard-library Python; browser calculations use native JavaScript modules.

`scripts/portfolio_sources.py` implements paced public-page/feed collection. Its raw cache is outside this repository under the workspace's `analysis/portfolio_collection_2026-09-09` directory. Raw pages, reviewer metadata and widget keys must not be published. `python scripts/build_portfolio.py --from-cache` explicitly freezes a new sanitized collection. Cutoff dates are fixed in this version; future refreshes must update and validate the period contract before release. Access/rate-limit responses are recorded as gaps, not bypassed. No scheduled refresh or new cloud service is configured.

## Included data

### Beef HMR

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

### Stir Fry

- Exact 13-product official catalog: six grocery kits and seven Costco-only larger-format items
- 166 deduplicated dated written reviews: the complete 81-review first-party history plus 56 incremental Target and 29 incremental Kroger comments
- Grocery-kit launch comparison anchored to February 27, 2025; Costco uses earliest observed review timing because the formal launch date was not confirmed
- 278 channel rating observations across Kevin's, Target, and Kroger, shown separately because syndication can overlap
- Exact-listing audit across Costco, Target, Kroger, Publix, Albertsons, Food Lion, and Amazon; searched-but-unconfirmed pages remain coverage gaps rather than zero-review records
- Separate tracking for 16 future-purchase incentive badges and one review that explicitly self-identifies as sponsored
- Branded one-page executive brief available from the Stir-Fry module in both PDF and Word formats

## Dashboard capabilities

- Use-case switch between the original Beef HMR workspace and the separately governed Stir-Fry launch workspace
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

### Stir-fry portfolio

- Official Kevin's product handles and storefront catalog endpoints establish product identity, cohort, pack architecture, and barcodes where available.
- Public first-party review feeds provide the complete observed history. The three exact Target pages and four exact Kroger pages contribute all written-review cards visible in their public interfaces as of the snapshot date; exact-text syndicated records are deduplicated.
- Written comments are deduplicated by product, rating, and exact normalized text so syndicated copies with channel-specific dates are not double-counted. Reviewer names are omitted.
- Monthly trends and fixed launch-versus-current windows use only the consistent first-party feed. Retailer aggregate ratings never enter dated trend or text-topic calculations.
- Transparent keyword rules tag taste, portion/value, protein quantity, vegetables, texture, convenience, dietary fit, and packaging. These signals are investigation prompts, not causal findings.
- `scripts/collect_stir_fry_catalog.py`, `scripts/collect_stir_fry_reviews.py`, `scripts/collect_stir_fry_retailer_reviews.py`, and `scripts/build_stir_fry_analysis.py` reproduce the module's governed data layers.

### Competitor benchmark

- The supplied product names were normalized into canonical products using brand, product name, pack size, UPC/item identifiers, and exact public product pages. Duplicate Hormel Beef Tips descriptions and the Jack Daniel's pack-title variants were merged to avoid double counting.
- The public Hormel PowerReviews feeds provide the complete first-party histories displayed within the 2023-2026 scope. Walmart product pages provide a bounded public server-rendered text sample plus complete point-in-time rating distributions for the listed pages.
- Walmart shares the Soules 6 oz and 14 oz review family. Records without a review-level size are excluded from product metrics rather than assigned by page title. Kroger contributes exact-SKU rating totals only because its written review payload was not reproducibly public.
- Target, Amazon, Kroger, Walmart, Costco, and brand sites were audited across all 13 products. Listings without defensible dated text remain coverage context and are not manufactured into review metrics.
- Competitor volume is sample-dependent and is not a market-share measure. Rating snapshots never enter the dated review trend, topic coding, or text-review KPIs.
- `scripts/collect_competitor_reviews.py` refreshes public benchmark evidence and safely falls back to the last verified Walmart sample when the retailer blocks automated access. `scripts/build_competitor_verified_evidence.mjs` applies the deterministic quality rules; reviewer names are not retained.

The site has no runtime dependencies and can be hosted directly with GitHub Pages.
