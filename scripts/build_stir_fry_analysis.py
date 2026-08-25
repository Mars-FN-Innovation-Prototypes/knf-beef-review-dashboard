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
REGISTRY_PATH = DATA / "stir_fry_product_registry.json"
REVIEWS_OUT = DATA / "stir_fry_reviews_normalized.json"
ANALYSIS_OUT = DATA / "stir_fry_analysis.json"

AS_OF = date(2026, 8, 25)
GROCERY_LAUNCH = date(2025, 2, 27)
RECENT_START = AS_OF - timedelta(days=182)
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


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def review_signature(row: dict) -> str:
    parts = [
        row["product_id"], row["date"], str(row["rating"]),
        normalized(row.get("text")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def topic_flags(row: dict) -> list[str]:
    text = normalized(f"{row.get('title', '')} {row.get('text', '')}")
    return [topic for topic, patterns in TOPICS.items() if any(re.search(pattern, text) for pattern in patterns)]


def metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {
            "n": 0, "average_rating": None, "low_star_share": None, "high_star_share": None,
            "topic_counts": {topic: 0 for topic in TOPICS},
            "topic_shares": {topic: None for topic in TOPICS},
        }
    topic_counts = {topic: sum(topic in row["topics"] for row in rows) for topic in TOPICS}
    return {
        "n": n,
        "average_rating": round(sum(row["rating"] for row in rows) / n, 2),
        "low_star_share": round(sum(row["rating"] <= 2 for row in rows) / n, 4),
        "high_star_share": round(sum(row["rating"] >= 4 for row in rows) / n, 4),
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
    registry = load(REGISTRY_PATH)
    products = {row["product_id"]: row for row in registry["products"]}

    raw_rows = []
    for priority, source_rows in enumerate([brand["reviews"], retail["reviews"]]):
        for source_row in source_rows:
            row = dict(source_row)
            row["portfolio"] = "stir_fry"
            row["cohort"] = products[row["product_id"]]["cohort"]
            row["_priority"] = priority
            raw_rows.append(row)

    deduplicated = []
    by_signature = {}
    duplicate_rows = 0
    for row in sorted(raw_rows, key=lambda item: (item["_priority"], item["date"], item["product_id"])):
        signature = review_signature(row)
        if signature in by_signature:
            duplicate_rows += 1
            retained = by_signature[signature]
            alternatives = retained.setdefault("also_observed_on", [])
            if row["source"] != retained["source"] and row["source"] not in alternatives:
                alternatives.append(row["source"])
            continue
        row.pop("_priority", None)
        row["topics"] = topic_flags(row)
        row["sentiment_band"] = "low" if row["rating"] <= 2 else "high" if row["rating"] >= 4 else "middle"
        row["incentive_disclosed"] = "review_earned_for_future_purchase" in (row.get("transparency_badges") or [])
        disclosure_text = f"{row.get('title', '')} {row.get('text', '')}"
        row["sponsorship_disclosed"] = bool(re.search(r"(?:#|\b)sponsored\b|\bpaid partnership\b", disclosure_text, re.I))
        by_signature[signature] = row
        deduplicated.append(row)

    deduplicated.sort(key=lambda row: (row["date"], row["product_id"]), reverse=True)
    metric_rows = [row for row in deduplicated if row.get("metric_eligible") is not False]

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
    all_snapshots = [*brand["snapshots"], *retail["snapshots"]]
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

    low_rows = [row for row in metric_rows if row["rating"] <= 2]
    complaint_topics = Counter(topic for row in low_rows for topic in row["topics"])
    total_metrics = metrics(metric_rows)
    grocery_all = cohort_metrics["grocery"]["all_written"]
    costco_all = cohort_metrics["costco_only"]["all_written"]
    grocery_launch = cohort_metrics["grocery"]["launch_6m"]
    grocery_recent = cohort_metrics["grocery"]["recent_6m"]
    incentive_rows = [row for row in comparable_rows if row["incentive_disclosed"]]
    non_incentive_rows = [row for row in comparable_rows if not row["incentive_disclosed"]]
    sponsored_rows = [row for row in metric_rows if row["sponsorship_disclosed"]]

    provocations = [
        {
            "id": "portion_architecture",
            "title": "Is the 2.5-serving promise creating an expectation gap?",
            "evidence": (
                f"{grocery_all['topic_counts']['portion_value']} of {grocery_all['n']} grocery-kit written reviews mention portion or value; "
                f"{grocery_all['topic_counts']['protein_quantity']} specifically flag protein quantity."
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
            "title": "The early Costco baseline is not a clean launch benchmark.",
            "evidence": (
                f"All {len(incentive_rows)} reviews carrying the disclosed future-purchase incentive badge were 5-star and concentrated in the early Costco period."
            ),
            "implication": "Use the Costco time series for issue discovery, but do not interpret the launch-to-now rating gap as a like-for-like decline.",
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
            "retailers": ["Costco", "Target", "Kroger", "Publix", "Albertsons", "Food Lion"],
        },
        "data_quality": {
            "raw_written_rows": len(raw_rows),
            "deduplicated_written_rows": len(metric_rows),
            "cross_source_duplicates_removed": duplicate_rows,
            "first_party_feed_rows": len(brand["reviews"]),
            "target_recent_rows": len(retail["reviews"]),
            "target_written_window_note": "Target exposes complete current rating distributions but only a recent written-review window in the public page payload.",
            "kroger_note": "Kroger aggregate ratings are retained as point-in-time context; reproducible written-review text was unavailable.",
            "listing_note": "A listing without a public review surface is shown as listing coverage, not as zero reviews.",
        },
        "overall": total_metrics,
        "comparable_history": metrics(comparable_rows),
        "incentive_disclosure": {
            "disclosed_incentive": metrics(incentive_rows),
            "no_disclosed_incentive": metrics(non_incentive_rows),
            "self_disclosed_sponsored": metrics(sponsored_rows),
            "note": "Future-purchase incentive badges and explicit sponsorship disclosures are tracked separately. No sponsorship inference is made where the review does not disclose it.",
        },
        "cohorts": cohort_metrics,
        "sources": source_metrics,
        "products": product_metrics,
        "monthly": monthly,
        "rating_snapshots": all_snapshots,
        "snapshot_summary": snapshot_summary,
        "coverage": retail["coverage"],
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
