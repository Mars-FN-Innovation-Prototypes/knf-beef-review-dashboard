# Kevin's Natural Foods — Portfolio Trends

Public-source release · September 9, 2026

[Open Portfolio Trends](https://mars-fn-innovation-prototypes.github.io/knf-beef-review-dashboard/portfolio.html)

## What was added

A separately managed third workspace alongside Beef HMR and Stir Fry. It shows quarterly average consumer ratings across the verified KNF assortment, with product, category, source, format and incentive filters. Existing analysis datasets were not changed.

- 105 current individual food products in 11 categories, plus one verified historical Buffalo Sauce listing. The mixed Game Day Grill Pack, cookware and administrative catalog entries are excluded.
- 5,646 unique dated rating records, July 1, 2024–September 9, 2026, covering 89 of the 106 registered products. This includes 5,644 written records and two rating-only records.
- 5,109 records from retrieved public histories and 537 partial-page or earlier-archive records. The default eight-completed-quarter view uses 4,015 records from Q3 2024 through Q2 2026. Q3 2026 is available separately as quarter-to-date.
- 322 overlapping observations removed using provider IDs and same-product/date/rating/text matching. Syndication without stable IDs or matching text/date may still be unrecognized.

These are collected records, not every rating posted on every retailer. No-review evidence and unconfirmed access are different conditions; gaps are not filled with zero.

## Where the records came from

Counts below are unique records attributed to their originating source after deduplication, across the entire collection window including quarter-to-date and samples. They are not the default chart denominator.

| Source | Unique dated records | How included |
|---|---:|---|
| Thrive Market | 3,604 | Public sitemap identified 53 candidates. The 52 verified single-product listings returned complete written-review feeds; a mixed bundle was excluded. Cumulative rating-only totals remain separate. |
| Kevin's owned site | 1,546 | The official catalog established identity. Legacy Judge.me feeds were paginated through the window or feed end for all 105 current product listings. The site's current Bazaarvoice layer remains an unreconciled coverage gap. |
| Target | 272 | Newly retrieved public recent-review cards combined with earlier exact-product evidence; partial samples, not complete September histories. One shared chicken-flavor pool is excluded from dated metrics. |
| Walmart | 148 | Four listing histories reached the requested window/feed end; additional pages were access-limited. Only completed listing histories enter the default trend. |
| Kroger | 53 | Earlier verified records retained with original capture dates; no new complete September history obtained. |
| Amazon | 20 | Earlier public-page sample retained; not expanded or represented as complete historical Amazon coverage. |
| Meijer | 3 | Earlier verified native comments retained as archived sample evidence. |

The separate coverage panel also retains exact-listing or snapshot evidence for Costco, Hannaford, Whole Foods, Albertsons, Safeway, Publix, Wegmans, ShopRite, Hy-Vee, FreshDirect and Instacart-hosted pages. Some representative requests were blocked, timed out, or returned no verifiable dated payload. Regional banners and unmatched product/source combinations remain explicit discovery gaps. This release does **not** certify an exhaustive product-by-retailer census.

## How to use it

1. Start with **Retrieved public histories** and eight completed quarters. Every unique dated rating receives one vote. The n beneath each point is its denominator.
2. Click a quarter to see star distribution, categories, originating sources, products and review text.
3. Compare **Kevin's site only**, **Retailers only**, and individual sources. Source and product mix can change between quarters.
4. Check **Equal-product average** and **Comparable product/source cells**. The latter keeps only cells with evidence in every selected quarter and gives each cell equal fixed weight. An empty result means no comparable base, not poor ratings.
5. Toggle **Exclude disclosed incentives** as a sensitivity check. 853 records have explicit incentive evidence across the full collection. “Not disclosed or unknown” does not prove a review was organic. Store-visitor and verified-purchase badges alone are not classified as incentives.
6. Use **All collected evidence + samples** only with its coverage caveat. Adding samples changes composition, not just sample size.
7. Export the current chart as PNG or SVG, the quarterly table as CSV, or the selected quarter's filtered records. Chart exports carry filter and method labels.

## Reading the initial trend

In the default retrieved-history view, the quarterly mean is 4.40 in Q3 2024, 3.72 in Q1 2026 and 4.01 in Q2 2026. Q2 2026 uses n=747 across 65 products and three originating sources; 17.9% of those records are 1–2 stars.

These are descriptive results from the collected evidence, not a market-representative rating or evidence of causation. The changing product/source/incentive mix must be examined before interpreting a decline or recovery as an underlying product-quality change. The comparable-coverage and source-specific controls exist for that reason.

## Quality and limitations

- Official product identities, UPCs, flavor, protein and format checks keep refrigerated entrées, stir-fry kits, frozen bowls and family meals distinct. Historical status means absent from the current visible assortment, not confirmed discontinued.
- Automated checks cover valid stars/dates, unique record IDs, exact UPC matches, quarter totals, weighting, missing-data behavior, incentive exclusions, CSV safety and public-field allowlists. No cross-product provider-ID conflicts were detected.
- A stratified 58-record sample spanning all 11 categories was matched back to cached raw provider records for date, stars and text. This is a validation sample, not a guarantee of every source's completeness.
- Desktop/mobile layouts, filters, empty states and exports were tested. Public datasets omit reviewer-name, email and location fields. Raw source payloads remain outside the public repository.
- Legacy brand histories are not equivalent to the current Bazaarvoice history. The tested public Conversations route did not authorize the widget key. No credentials or private feeds were used to work around this.
- Target deeper pagination was unauthorized; Walmart access limits and other channel restrictions were respected. These gaps can still contain additional reviews.
- Current cumulative retailer totals cannot reconstruct historical quarters. They are shown separately and may overlap across syndicated or shared pools; do not sum them as unique consumers.
- There is no recurring collection, sales weighting, sales denominator, or consumer-care complaint feed in this release.

## Reproducible snapshot

The public repository includes the canonical product registry, sanitized source evidence, normalized records, validation report and calculation tests. The snapshot can be rebuilt locally without retailer network access. A later collection requires a new documented cutoff and a fresh coverage audit; the September 9 snapshot should not silently be relabeled as current.
