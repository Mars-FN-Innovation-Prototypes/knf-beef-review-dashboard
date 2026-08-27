"""Build the separately governed stir-fry dashboard dataset."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BRAND_PATH = DATA / "stir_fry_brand_reviews_2026-08-25.json"
RETAIL_PATH = DATA / "stir_fry_retailer_evidence_2026-08-25.json"
EXPANDED_PATH = DATA / "stir_fry_expanded_reviews_2026-08-27.json"
REGISTRY_PATH = DATA / "stir_fry_product_registry.json"
REVIEWS_OUT = DATA / "stir_fry_reviews_normalized.json"
ANALYSIS_OUT = DATA / "stir_fry_analysis.json"

AS_OF = date(2026, 8, 27)
GROCERY_LAUNCH = date(2025, 2, 27)
RECENT_START = AS_OF - timedelta(days=182)
RECENT_12M_START = AS_OF - timedelta(days=365)
GROCERY_LAUNCH_WINDOW_END = GROCERY_LAUNCH + timedelta(days=182)

TOPICS = {
    "taste": [
        r"\btast(?:e|es|ed|ing)\b", r"\bflavo[u]?r", r"\bdelicious\b", r"\byummy\b",
        r"\bbland\b", r"\bsalty\b", r"\bsweet\b", r"\bspic(?:e|y)\b", r"\bsauce\b",
    ],
    "portion_value": [
        r"\bportion", r"\bserv(?:e|es|ing)", r"\bnot enough\b", r"\btoo (?:little|small)\b",
        r"\bbarely\b", r"\bprice\b", r"\bcost\b", r"\bexpensive\b", r"\boverpriced\b",
        r"\bworth\b", r"\bvalue\b", r"\brip[ -]?off\b", r"\bfeed(?:s|ing)?\b",
    ],
    "protein_quantity": [
        r"\b(?:little|tiny|small amount of|not much|hardly any|barely any|no) chicken\b",
        r"\b(?:little|tiny|small amount of|not much|hardly any|barely any|no) (?:meat|beef)\b",
        r"\bmore chicken\b", r"\bmore (?:meat|beef)\b", r"\bprotein\b",
    ],
    "vegetables": [
        r"\bgreen bean", r"\bbroccoli\b", r"\bvegetable", r"\bvegg", r"\bpepper", r"\bonion",
        r"\bcarrot", r"\bsoggy\b", r"\bfresh\b",
    ],
    "texture": [
        r"\btexture\b", r"\btough\b", r"\bchew", r"\brubber", r"\bgristle", r"\bgrisly\b",
        r"\bdry\b", r"\btender\b", r"\bmushy\b", r"\bsoggy\b",
    ],
    "convenience": [
        r"\beasy\b", r"\bquick\b", r"\bconvenien", r"\bminute", r"\bprep", r"\bweeknight\b",
        r"\bbusy\b", r"\bsimple\b", r"\bready\b",
    ],
    "dietary_fit": [
        r"\bgluten", r"\bsoy[- ]?free\b", r"\bpaleo\b", r"\bhealthy\b", r"\ballerg",
        r"\bingredient", r"\bcarb", r"\bweight watchers\b",
    ],
    "packaging": [r"\bpackage\b", r"\bpackaging\b", r"\bpouch\b", r"\bbag\b", r"\bleak"],
}

# Precise, complaint-oriented rules kept separate from the broader topic tags.
# A review can carry more than one value-for-money category.
VALUE_CATEGORIES = {
    "protein_quantity": [
        r"\b(?:not enough|too little|very little|hardly any|barely any|no|smallest amount of|small amount of|tiny amount of|little bit of|barely a serving of) (?:chicken|beef|meat|steak|protein)\b",
        r"\b(?:tiny|small|very small) (?:piece of |packet of |portion of )?(?:chicken|beef|meat|steak|protein)\b",
        r"\b(?:chicken|beef|meat|steak|protein) (?:portion|packet|amount) (?:is |was |seems? )?(?:very |too )?(?:small|tiny|skimpy|insufficient|poor|a joke|not enough)\b",
        r"\bmore (?:chicken|beef|meat|steak|protein)\b",
        r"\bonly half (?:the )?(?:amount of )?(?:chicken|beef|meat|steak|protein)\b",
        r"\bhalf (?:the )?(?:amount of )?(?:chicken|beef|meat|steak|protein)\b",
        r"\b(?:more|way more|mostly|lots? of|tons? of) (?:broccoli|green beans?|vegetables?|veggies).{0,30}\b(?:than (?:there (?:is|are) )?|with (?:only )?)(?:a |very )?(?:little|small amount of|not enough)? ?(?:chicken|beef|meat|steak)\b",
    ],
    "vegetable_quantity": [
        r"\b(?:not enough|too few|very few|hardly any|barely any|no|small amount of|tiny amount of) (?:vegetables?|veggies|broccoli|green beans?|peppers?|onions?)\b",
        r"\b(?:vegetables?|veggies|broccoli|green beans?|peppers?|onions?) (?:were |are |was |seem(?:ed)? )?(?:sparse|lacking|skimpy|insufficient)\b",
        r"\b(?:vegetable|veggie|broccoli|green bean|pepper|onion) (?:portion|amount) (?:is |was )?(?:small|tiny|skimpy|insufficient)\b",
        r"\b(?:had to add|added|need(?:ed|s)?|wish(?:ed)? (?:there (?:was|were) )?) more (?:vegetables?|veggies|broccoli|green beans?|peppers?|onions?)\b",
    ],
    "serving_size": [
        r"\b(?:portion|serving|servings|size|amount) (?:is |was |were |are |seems? )?(?:way |very |too |really |ridiculously |super )?(?:small|tiny|skimpy|poor|a joke|not enough)\b",
        r"\b(?:too small|small|tiny|skimpy|minimal) (?:portion|serving|servings|size|amount)\b",
        r"\b(?:small|tiny) on servings\b",
        r"\b(?:barely|only|less than) (?:a |one |two |1 |2 )?servings?\b",
        r"\b(?:not enough|only enough) for (?:one|two|three|1|2|3|our|a family|my family)\b",
        r"\b(?:feeds?|fed) (?:only )?(?:one|1|two|2)\b",
        r"\b(?:about |only )?(?:1\.5|one and a half) servings?\b",
        r"\b(?:supposed|claims?|stretch).{0,35}\b2 5 servings?\b",
        r"\b(?:not|isn t|wasn t) (?:a )?full meal\b",
        r"\b(?:had to add|needs?|needed|require[ds]?) (?:a side of |some )?(?:rice|noodles|protein|chicken|beef).{0,30}\b(?:full|complete|enough|filling) meal\b",
        r"\bwish (?:there|it|this|they).{0,20}\bmore (?:in|food|product)\b",
    ],
    "explicit_price_value": [
        r"\bnot (?:a )?(?:good )?value\b",
        r"\bnot worth\b",
        r"\bisn t worth\b",
        r"\bwasn t worth\b",
        r"\bnot cost effective\b",
        r"\btoo expensive\b",
        r"\brelatively expensive\b",
        r"\boverpriced\b",
        r"\bpoor value\b",
        r"\bbad value\b",
        r"\bwaste of (?:money|cash)\b",
        r"\brip[ -]?off\b",
        r"\b(?:price|cost).{0,55}\b(?:small|little|half|not enough|only|disappoint)\b",
        r"\b(?:small|little|half|not enough|only).{0,55}\b(?:same |the )?(?:price|cost)\b",
    ],
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def review_signature(row: dict) -> str:
    parts = [
        row["product_id"], str(row["rating"]),
        normalized(row.get("text")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def topic_flags(row: dict) -> list[str]:
    text = normalized(f"{row.get('title', '')} {row.get('text', '')}")
    return [topic for topic, patterns in TOPICS.items() if any(re.search(pattern, text) for pattern in patterns)]


def value_category_flags(row: dict) -> list[str]:
    text = normalized(f"{row.get('title', '')} {row.get('text', '')}")
    return [
        category
        for category, patterns in VALUE_CATEGORIES.items()
        if any(re.search(pattern, text) for pattern in patterns)
    ]


def metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {
            "n": 0, "rated_n": 0, "average_rating": None, "low_star_share": None, "high_star_share": None,
            "low_value_count": 0, "low_value_share": None,
            "topic_counts": {topic: 0 for topic in TOPICS},
            "topic_shares": {topic: None for topic in TOPICS},
        }
    rated_rows = [row for row in rows if 1 <= int(row.get("rating") or 0) <= 5]
    rated_n = len(rated_rows)
    topic_counts = {topic: sum(topic in row["topics"] for row in rows) for topic in TOPICS}
    return {
        "n": n,
        "rated_n": rated_n,
        "average_rating": round(sum(row["rating"] for row in rated_rows) / rated_n, 2) if rated_n else None,
        "low_star_share": round(sum(row["rating"] <= 2 for row in rated_rows) / rated_n, 4) if rated_n else None,
        "high_star_share": round(sum(row["rating"] >= 4 for row in rated_rows) / rated_n, 4) if rated_n else None,
        "low_value_count": sum(row.get("low_value_for_money", False) for row in rows),
        "low_value_share": round(sum(row.get("low_value_for_money", False) for row in rows) / n, 4),
        "topic_counts": topic_counts,
        "topic_shares": {topic: round(count / n, 4) for topic, count in topic_counts.items()},
    }


def aggregate_distribution(snapshots: list[dict]) -> dict:
    distribution = {str(star): 0 for star in range(1, 6)}
    usable = False
    for snapshot in snapshots:
        current = snapshot.get("distribution") or {}
        if current:
            usable = True
        for star in range(1, 6):
            distribution[str(star)] += int(current.get(str(star)) or 0)
    return distribution if usable else {}


def main() -> None:
    brand = load(BRAND_PATH)
    retail = load(RETAIL_PATH)
    expanded = load(EXPANDED_PATH)
    registry = load(REGISTRY_PATH)
    products = {row["product_id"]: row for row in registry["products"]}

    raw_rows = []
    brand_date_index = {
        (row["product_id"], int(row["rating"]), normalized(row.get("text"))): row["date"]
        for row in brand["reviews"]
    }
    undated_retail_rows = 0
    retailer_dates_resolved = 0
    for priority, source_rows in enumerate([brand["reviews"], retail["reviews"], expanded["reviews"]]):
        for source_row in source_rows:
            row = dict(source_row)
            if not row.get("date"):
                undated_retail_rows += 1
                matched_date = brand_date_index.get(
                    (row["product_id"], int(row["rating"]), normalized(row.get("text")))
                )
                if matched_date:
                    row["date"] = matched_date
                    row["date_resolution"] = "matched_first_party_text"
                    row["metric_eligible"] = True
                    retailer_dates_resolved += 1
            row["portfolio"] = "stir_fry"
            row["cohort"] = products[row["product_id"]]["cohort"]
            row["_priority"] = priority
            raw_rows.append(row)

    deduplicated = []
    by_signature = {}
    duplicate_rows = 0
    cross_source_duplicate_rows = 0
    within_source_duplicate_rows = 0
    for row in sorted(raw_rows, key=lambda item: (item["_priority"], item.get("date") or "", item["product_id"])):
        signature = review_signature(row)
        if signature in by_signature:
            duplicate_rows += 1
            retained = by_signature[signature]
            alternatives = retained.setdefault("also_observed_on", [])
            if row["source"] != retained["source"]:
                cross_source_duplicate_rows += 1
                if row["source"] not in alternatives:
                    alternatives.append(row["source"])
            else:
                within_source_duplicate_rows += 1
            continue
        row.pop("_priority", None)
        row["topics"] = topic_flags(row)
        row["value_categories"] = value_category_flags(row)
        row["low_value_for_money"] = bool(row["value_categories"])
        row["sentiment_band"] = (
            "unrated" if not 1 <= int(row.get("rating") or 0) <= 5
            else "low" if row["rating"] <= 2
            else "high" if row["rating"] >= 4
            else "middle"
        )
        badges = row.get("transparency_badges") or []
        row["incentive_disclosed"] = bool(
            {"review_earned_for_future_purchase", "thrive_cash_earned"}.intersection(badges)
        )
        row["incentive_type"] = (
            "thrive_cash" if "thrive_cash_earned" in badges
            else "future_purchase" if "review_earned_for_future_purchase" in badges
            else None
        )
        disclosure_text = f"{row.get('title', '')} {row.get('text', '')}"
        row["sponsorship_disclosed"] = bool(re.search(r"(?:#|\b)sponsored\b|\bpaid partnership\b", disclosure_text, re.I))
        by_signature[signature] = row
        deduplicated.append(row)

    deduplicated.sort(key=lambda row: (row.get("date") or "", row["product_id"]), reverse=True)
    metric_rows = [row for row in deduplicated if row.get("metric_eligible") is not False and row.get("date")]

    product_metrics = []
    for product_id, product in products.items():
        rows = [row for row in metric_rows if row["product_id"] == product_id]
        recent = [row for row in rows if row["date"] >= RECENT_START.isoformat()]
        entry = {
            "product_id": product_id,
            "product": product["product"],
            "cohort": product["cohort"],
            "official_url": product["official_url"],
            "all": metrics(rows),
            "recent_6m": metrics(recent),
            "earliest_review": min((row["date"] for row in rows), default=None),
            "latest_review": max((row["date"] for row in rows), default=None),
        }
        product_metrics.append(entry)

    monthly_groups = defaultdict(list)
    for row in metric_rows:
        monthly_groups[row["date"][:7]].append(row)
    monthly = [{"month": month, **metrics(rows)} for month, rows in sorted(monthly_groups.items())]

    comparable_rows = [row for row in metric_rows if row["source"] == "Kevin's Natural Foods"]
    cohort_metrics = {}
    for cohort in ["grocery", "costco_only"]:
        cohort_rows = [row for row in metric_rows if row["cohort"] == cohort]
        history_rows = [row for row in comparable_rows if row["cohort"] == cohort]
        if cohort == "grocery":
            launch_rows = [
                row for row in history_rows
                if GROCERY_LAUNCH.isoformat() <= row["date"] <= GROCERY_LAUNCH_WINDOW_END.isoformat()
            ]
        else:
            observed_start = min((date.fromisoformat(row["date"]) for row in history_rows), default=AS_OF)
            observed_end = observed_start + timedelta(days=182)
            launch_rows = [row for row in history_rows if observed_start <= date.fromisoformat(row["date"]) <= observed_end]
        recent_rows = [row for row in history_rows if row["date"] >= RECENT_START.isoformat()]
        cohort_metrics[cohort] = {
            "all_written": metrics(cohort_rows),
            "comparable_history": metrics(history_rows),
            "launch_6m": metrics(launch_rows),
            "recent_6m": metrics(recent_rows),
            "launch_window_start": GROCERY_LAUNCH.isoformat() if cohort == "grocery" else min((row["date"] for row in history_rows), default=None),
            "launch_window_end": GROCERY_LAUNCH_WINDOW_END.isoformat() if cohort == "grocery" else (observed_start + timedelta(days=182)).isoformat(),
        }

    source_groups = defaultdict(list)
    for row in metric_rows:
        source_groups[row["source"]].append(row)
    source_metrics = {source: metrics(rows) for source, rows in sorted(source_groups.items())}

    snapshot_groups = defaultdict(list)
    all_snapshots = [*brand["snapshots"], *retail["snapshots"], *expanded["snapshots"]]
    for snapshot in all_snapshots:
        snapshot_groups[snapshot["source"]].append(snapshot)
    snapshot_summary = []
    for source, snapshots in sorted(snapshot_groups.items()):
        rating_count = sum(int(row.get("rating_count") or 0) for row in snapshots)
        weighted = sum(float(row.get("average_rating") or 0) * int(row.get("rating_count") or 0) for row in snapshots)
        snapshot_summary.append({
            "source": source,
            "products_with_exact_page": len(snapshots),
            "products_with_ratings": sum(bool(row.get("rating_count")) for row in snapshots),
            "rating_observations": rating_count,
            "weighted_average_rating": round(weighted / rating_count, 2) if rating_count else None,
            "distribution": aggregate_distribution(snapshots),
            "note": (
                "Channel total; may include syndicated or overlapping ratings and is not a unique-consumer count."
            ),
        })

    assessment_summary = []
    all_coverage = [*retail["coverage"], *expanded["coverage"]]
    for source_name in ["Costco", "Target", "Kroger", "Publix", "Albertsons", "Food Lion", "Amazon", "Thrive Market", "Meijer"]:
        rows = [row for row in all_coverage if row["source"] == source_name]
        assessment_summary.append({
            "source": source_name,
            "exact_pages": sum(row["match_type"] == "exact_sku" for row in rows),
            "review_histories_complete": sum(row["status"] == "review_history_complete" for row in rows),
            "listing_no_public_reviews": sum(row["status"] == "listing_no_public_reviews" for row in rows),
            "official_assignment_page_unindexed": sum(row["status"] == "official_costco_sku_page_not_indexed" for row in rows),
            "searched_no_exact_page": sum(row["status"] == "searched_no_exact_page" for row in rows),
            "not_applicable": sum(row["status"] == "not_applicable" for row in rows),
        })

    low_rows = [row for row in metric_rows if row["rating"] <= 2]
    complaint_topics = Counter(topic for row in low_rows for topic in row["topics"])
    total_metrics = metrics(metric_rows)
    grocery_all = cohort_metrics["grocery"]["all_written"]
    costco_all = cohort_metrics["costco_only"]["all_written"]
    grocery_launch = cohort_metrics["grocery"]["launch_6m"]
    grocery_recent = cohort_metrics["grocery"]["recent_6m"]
    incentive_rows = [row for row in metric_rows if row["incentive_disclosed"]]
    non_incentive_rows = [row for row in metric_rows if not row["incentive_disclosed"]]
    sponsored_rows = [row for row in metric_rows if row["sponsorship_disclosed"]]
    low_value_rows = [row for row in metric_rows if row["low_value_for_money"]]
    low_value_recent_12m = [row for row in low_value_rows if row["date"] >= RECENT_12M_START.isoformat()]

    value_by_category = []
    for category in VALUE_CATEGORIES:
        category_rows = [row for row in metric_rows if category in row["value_categories"]]
        value_by_category.append({
            "category": category,
            "n": len(category_rows),
            "share_of_all_reviews": round(len(category_rows) / len(metric_rows), 4) if metric_rows else None,
            "share_of_low_value_reviews": round(len(category_rows) / len(low_value_rows), 4) if low_value_rows else None,
            "average_rating": round(sum(row["rating"] for row in category_rows) / len(category_rows), 2) if category_rows else None,
        })

    value_by_source = []
    for source, rows in sorted(source_groups.items()):
        flagged = [row for row in rows if row["low_value_for_money"]]
        value_by_source.append({
            "source": source,
            "n": len(rows),
            "low_value_n": len(flagged),
            "low_value_share": round(len(flagged) / len(rows), 4) if rows else None,
            "disclosed_incentive_n": sum(row["incentive_disclosed"] for row in rows),
        })

    value_by_product = []
    for product_id, product in products.items():
        rows = [row for row in metric_rows if row["product_id"] == product_id]
        flagged = [row for row in rows if row["low_value_for_money"]]
        value_by_product.append({
            "product_id": product_id,
            "product": product["product"],
            "cohort": product["cohort"],
            "n": len(rows),
            "low_value_n": len(flagged),
            "low_value_share": round(len(flagged) / len(rows), 4) if rows else None,
            "categories": {category: sum(category in row["value_categories"] for row in rows) for category in VALUE_CATEGORIES},
        })

    owned_value_rows = [row for row in comparable_rows if row["low_value_for_money"]]
    non_incentive_value_base = [row for row in metric_rows if not row["incentive_disclosed"]]
    non_incentive_value_rows = [row for row in non_incentive_value_base if row["low_value_for_money"]]

    provocations = [
        {
            "id": "portion_architecture",
            "title": "Is the 2.5-serving promise creating an expectation gap?",
            "evidence": (
                f"{sum(row['low_value_for_money'] for row in metric_rows if row['cohort'] == 'grocery')} of {grocery_all['n']} grocery-kit written reviews contain a precise low-value signal; "
                f"{sum('protein_quantity' in row['value_categories'] for row in metric_rows if row['cohort'] == 'grocery')} specifically flag protein quantity."
            ),
            "implication": "Test pack communication and protein-to-vegetable balance before treating the issue as flavor reformulation.",
            "confidence": "strongest_directional_signal" if grocery_all["n"] >= 30 else "directional_small_sample",
        },
        {
            "id": "launch_to_now",
            "title": "Did the grocery-kit experience weaken as distribution scaled?",
            "evidence": (
                f"On the complete first-party history, grocery kits moved from {grocery_launch['average_rating']:.2f} (n={grocery_launch['n']}) "
                f"in the first six months after launch to {grocery_recent['average_rating']:.2f} (n={grocery_recent['n']}) in the latest six months."
            ),
            "implication": "Validate the signal against consumer care, lots, promotions, and channel mix; the written-review bases remain small.",
            "confidence": "directional_small_sample",
        },
        {
            "id": "early_incentive_bias",
            "title": "Incentive-bearing cohorts must remain visible, not blended away.",
            "evidence": (
                f"{len(incentive_rows)} written reviews carry a disclosed future-purchase or Thrive Cash incentive; source-specific views preserve that context."
            ),
            "implication": "Use owned-site trends for launch-to-now comparison and retailer cohorts for issue discovery; do not treat the combined rating as a like-for-like trend.",
            "confidence": "strong_methodological_finding",
        },
        {
            "id": "convenience_equity",
            "title": "Convenience appears to be an equity worth protecting.",
            "evidence": (
                f"Convenience language appears in {total_metrics['topic_counts']['convenience']} of {total_metrics['n']} deduplicated written reviews."
            ),
            "implication": "Any product or pack change should preserve the under-10-minute, low-mess preparation benefit.",
            "confidence": "directional",
        },
        {
            "id": "distribution_learning",
            "title": "Use retailer variance as a learning agenda, not a scorecard.",
            "evidence": "Target and Kroger aggregates are larger than the owned-site feed for several grocery SKUs, but their populations and syndication rules differ.",
            "implication": "Validate channel, price, promotion, and review-origin metadata before comparing retailer averages as if they were controlled cohorts.",
            "confidence": "methodological_guardrail",
        },
    ]

    output = {
        "as_of": AS_OF.isoformat(),
        "scope": {
            "product_count": len(products),
            "grocery_product_count": sum(row["cohort"] == "grocery" for row in products.values()),
            "costco_only_product_count": sum(row["cohort"] == "costco_only" for row in products.values()),
            "grocery_launch_date": GROCERY_LAUNCH.isoformat(),
            "costco_launch_note": "Formal launch date not confirmed; earliest captured written review is used as the observed-start marker.",
            "retailers": ["Costco", "Target", "Kroger", "Publix", "Albertsons", "Food Lion", "Amazon", "Thrive Market", "Meijer"],
        },
        "data_quality": {
            "raw_written_rows": len(raw_rows),
            "deduplicated_written_rows": len(metric_rows),
            "duplicate_rows_removed": duplicate_rows,
            "cross_source_duplicates_removed": cross_source_duplicate_rows,
            "within_source_duplicates_removed": within_source_duplicate_rows,
            "first_party_feed_rows": len(brand["reviews"]),
            "target_complete_written_rows": sum(row["source"] == "Target" for row in retail["reviews"]),
            "kroger_complete_visible_cards": sum(row["source"] == "Kroger" for row in retail["reviews"]),
            "thrive_complete_written_rows": sum(row["source"] == "Thrive Market" for row in expanded["reviews"]),
            "meijer_incremental_written_rows": sum(row["source"] == "Meijer" for row in expanded["reviews"]),
            "undated_retail_cards": undated_retail_rows,
            "undated_dates_resolved_from_first_party": retailer_dates_resolved,
            "target_written_window_note": "All written reviews exposed by the three exact Target product pages were loaded and captured.",
            "kroger_note": "All visible public cards were captured from four exact Kroger pages; undated cards are excluded unless they exactly match a dated first-party record.",
            "amazon_note": "Amazon was assessed for all six grocery kits; no exact scoped product page was confirmed. Adjacent sauces and Heat & Eat items were excluded.",
            "thrive_note": "All written reviews returned by the public review endpoint for three exact-UPC grocery kits were captured. Thrive Cash disclosure is preserved row by row.",
            "meijer_note": "Three native Meijer-origin reviews were captured from the exact Instacart-hosted listing; syndicated Kevin's rows were deduplicated rather than counted again.",
            "listing_note": "An exact listing without a public review surface is shown as listing coverage, not as zero reviews. A searched-no-exact-page result is also not a zero-review claim.",
        },
        "overall": total_metrics,
        "comparable_history": metrics(comparable_rows),
        "incentive_disclosure": {
            "disclosed_incentive": metrics(incentive_rows),
            "no_disclosed_incentive": metrics(non_incentive_rows),
            "self_disclosed_sponsored": metrics(sponsored_rows),
            "note": "Future-purchase and Thrive Cash badges are treated as disclosed incentives; explicit sponsorship remains a separate field. No sponsorship inference is made where the review does not disclose it.",
        },
        "value_for_money": {
            "definition": "All-time written reviews that explicitly indicate insufficient protein, insufficient vegetables, inadequate serving size, or negative price/value tension. Reviews may carry more than one category.",
            "overall": {
                "n": len(metric_rows),
                "low_value_n": len(low_value_rows),
                "low_value_share": round(len(low_value_rows) / len(metric_rows), 4) if metric_rows else None,
                "average_rating": round(
                    sum(row["rating"] for row in low_value_rows if 1 <= row["rating"] <= 5)
                    / sum(1 <= row["rating"] <= 5 for row in low_value_rows), 2
                ) if any(1 <= row["rating"] <= 5 for row in low_value_rows) else None,
            },
            "recent_12m": {
                "start": RECENT_12M_START.isoformat(),
                "n": sum(row["date"] >= RECENT_12M_START.isoformat() for row in metric_rows),
                "low_value_n": len(low_value_recent_12m),
            },
            "owned_site": {
                "n": len(comparable_rows),
                "low_value_n": len(owned_value_rows),
                "low_value_share": round(len(owned_value_rows) / len(comparable_rows), 4) if comparable_rows else None,
            },
            "excluding_disclosed_incentives": {
                "n": len(non_incentive_value_base),
                "low_value_n": len(non_incentive_value_rows),
                "low_value_share": round(len(non_incentive_value_rows) / len(non_incentive_value_base), 4) if non_incentive_value_base else None,
            },
            "by_category": value_by_category,
            "by_source": value_by_source,
            "by_product": sorted(value_by_product, key=lambda row: (row["low_value_n"], row["n"]), reverse=True),
        },
        "cohorts": cohort_metrics,
        "sources": source_metrics,
        "products": product_metrics,
        "monthly": monthly,
        "rating_snapshots": all_snapshots,
        "snapshot_summary": snapshot_summary,
        "assessment_summary": assessment_summary,
        "coverage": all_coverage,
        "complaint_topics": dict(complaint_topics.most_common()),
        "provocations": provocations,
    }

    REVIEWS_OUT.write_text(json.dumps(metric_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ANALYSIS_OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("raw", len(raw_rows), "deduplicated", len(metric_rows), "duplicates", duplicate_rows)
    print("overall", total_metrics)
    print("grocery", grocery_all)
    print("costco", costco_all)
    print("complaint topics", complaint_topics)
    print("Wrote", REVIEWS_OUT, "and", ANALYSIS_OUT)


if __name__ == "__main__":
    main()
