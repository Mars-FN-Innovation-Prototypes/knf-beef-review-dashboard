"""Merge refreshed first-party and retailer evidence, then rebuild dashboard analysis."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
AS_OF = date(2026, 7, 22)
BACKFILL_START = date(2023, 1, 1)
WINDOW_START = date(2024, 11, 1)
CUTOFF = date(2025, 11, 1)

REGISTRY = json.loads((DATA / "sku_registry.json").read_text(encoding="utf-8"))
BASE_REVIEWS = json.loads((DATA / "reviews_normalized.json").read_text(encoding="utf-8"))
BASE_ANALYSIS = json.loads((DATA / "analysis_output.json").read_text(encoding="utf-8"))
BRAND = json.loads((DATA / "brand_reviews_2026-07-22.json").read_text(encoding="utf-8"))
RETAIL = json.loads((DATA / "core_retailer_collection_2026-07-22.json").read_text(encoding="utf-8"))

NAME_BY_ID = {product["id"]: product["name"] for product in REGISTRY["products"]}
PRIOR_TARGET_WRITTEN_COUNT = 120


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def source_key(row):
    return (
        row["product_id"], row["source"].lower(), row["date"], int(row["rating"]),
        norm(row.get("title")), norm(row.get("text")),
    )


def title_key(row):
    return (
        row["product_id"], row["source"].lower(), row["date"], int(row["rating"]),
        norm(row.get("title")),
    )


def cross_source_key(row):
    return (
        row["product_id"], row["date"], int(row["rating"]),
        norm(row.get("title")), norm(row.get("text")),
    )


def normalize_row(row):
    normalized = dict(row)
    normalized["product"] = NAME_BY_ID[row["product_id"]]
    normalized["rating"] = int(row["rating"])
    normalized["title"] = str(row.get("title") or "")
    normalized["text"] = str(row.get("text") or "")
    normalized["metric_eligible"] = bool(normalized["title"].strip() or normalized["text"].strip()) and row.get("metric_eligible", True) is not False
    return normalized


# Keep the existing non-brand archive, but replace lower-fidelity Walmart summaries.
rows = [
    normalize_row(row) for row in BASE_REVIEWS
    if row["source"] != "Kevin's Natural Foods" and not (row["source"] == "Walmart" and row.get("metric_eligible") is False)
]

# Replace the complete first-party set with the July 22 refresh.
for row in BRAND["reviews"]:
    row = dict(row)
    row["metric_eligible"] = True
    rows.append(normalize_row(row))

# Target recent records replace matching truncated rows; new dates append. Walmart adds the complete written set.
replacements = 0
appended_retailer = 0
for incoming in map(normalize_row, RETAIL["reviews"]):
    # Walmart supplies stable review IDs and this collection is a complete public
    # set, so retain every distinct provider record. Title/date/rating alone is
    # not unique enough (two shoppers can post the same short title on one day).
    if incoming["source"] == "Walmart":
        rows.append(incoming)
        appended_retailer += 1
        continue
    match_index = next((index for index, current in enumerate(rows) if title_key(current) == title_key(incoming)), None)
    if match_index is not None:
        current = rows[match_index]
        if len(incoming.get("text", "")) > len(current.get("text", "")) or not current.get("provider_review_id"):
            rows[match_index] = incoming
            replacements += 1
        continue
    rows.append(incoming)
    appended_retailer += 1

# Remove exact within-source duplicates, then cross-source syndicated duplicates without inflating metrics.
within = {}
for row in rows:
    within.setdefault(source_key(row), row)
within_rows = list(within.values())
cross = {}
for row in within_rows:
    cross.setdefault(cross_source_key(row), row)
reviews = sorted(cross.values(), key=lambda row: (row["date"], row["source"], row["product_id"]), reverse=True)
analysis_reviews = [row for row in reviews if row.get("metric_eligible") is not False]

texture_re = re.compile(r"\b(texture|tough|chew\w*|rubber\w*|grist\w*|grisly|fatty|mushy|slimy|spongy|soggy|mealy|stringy|tender|sinew\w*|powdery|blob|meat quality|fake meat|dry)\b", re.I)
taste_re = re.compile(r"\b(taste|flavor|bland|salty|sweet|sour|spic\w*|season\w*|delicious|gross|disgust\w*|smell\w*)\b", re.I)


def period(row):
    day = date.fromisoformat(row["date"])
    if day < WINDOW_START:
        return "archive"
    return "post" if day >= CUTOFF else "pre"


def metrics(group):
    if not group:
        return {"n": 0, "avg_rating": None, "negative_pct": None, "texture_pct": None, "taste_pct": None}
    return {
        "n": len(group),
        "avg_rating": round(mean(row["rating"] for row in group), 2),
        "negative_pct": round(100 * sum(row["rating"] <= 2 for row in group) / len(group), 1),
        "texture_pct": round(100 * sum(bool(texture_re.search(f"{row.get('title', '')} {row.get('text', '')}")) for row in group) / len(group), 1),
        "taste_pct": round(100 * sum(bool(taste_re.search(f"{row.get('title', '')} {row.get('text', '')}")) for row in group) / len(group), 1),
    }


overall = {name: metrics([row for row in analysis_reviews if period(row) == name]) for name in ("pre", "post")}
overall["delta_rating"] = round(overall["post"]["avg_rating"] - overall["pre"]["avg_rating"], 2)
overall["delta_texture_pp"] = round(overall["post"]["texture_pct"] - overall["pre"]["texture_pct"], 1)

products = []
for product in REGISTRY["products"]:
    product_rows = [row for row in analysis_reviews if row["product_id"] == product["id"] and period(row) != "archive"]
    pre = metrics([row for row in product_rows if period(row) == "pre"])
    post = metrics([row for row in product_rows if period(row) == "post"])
    products.append({
        "product_id": product["id"], "product": product["name"], "total_n": len(product_rows),
        "pre": pre, "post": post,
        "rating_delta": round(post["avg_rating"] - pre["avg_rating"], 2) if pre["n"] and post["n"] else None,
        "texture_delta_pp": round(post["texture_pct"] - pre["texture_pct"], 1) if pre["n"] and post["n"] else None,
    })

month_groups = defaultdict(list)
for row in analysis_reviews:
    if period(row) != "archive":
        month_groups[row["date"][:7]].append(row)
monthly = [{"month": month, **metrics(group)} for month, group in sorted(month_groups.items())]

# Keep Kroger point-in-time context, replace brand/Walmart snapshots, and add current Target snapshots.
kroger_snapshots = [snapshot for snapshot in BASE_ANALYSIS["rating_snapshots"] if snapshot["source"] == "Kroger"]
rating_snapshots = list(kroger_snapshots)
for snapshot in BRAND["snapshots"]:
    rating_snapshots.append({
        "product_id": snapshot["product_id"],
        "source": "Kevin's Natural Foods",
        "page_url": snapshot["page_url"],
        "rating_count": snapshot["rating_count"],
        "written_review_count": snapshot["written_reviews_since_2023"],
        "distribution": snapshot["distribution"],
        "captured_at": snapshot["captured_at"],
        "page_status": f"Complete public feed; {snapshot['written_reviews_since_2023']} full-text reviews dated from Jan 1, 2023.",
    })
for snapshot in RETAIL["snapshots"]:
    status = (
        f"Complete public written set captured: {snapshot['written_review_count']} reviews."
        if snapshot["source"] == "Walmart"
        else f"Complete rating distribution; {snapshot['written_review_count']} written reviews in the retained Target archive."
    )
    rating_snapshots.append({
        "product_id": snapshot["product_id"],
        "source": snapshot["source"],
        "page_url": snapshot["page_url"],
        "rating_count": snapshot["rating_count"],
        "written_review_count": snapshot["written_review_count"],
        "distribution": snapshot["distribution"],
        "captured_at": snapshot["as_of"],
        "page_status": status,
    })

for snapshot in rating_snapshots:
    if sum(snapshot["distribution"].values()) != snapshot["rating_count"]:
        raise RuntimeError(f"Rating distribution mismatch: {snapshot['source']} {snapshot['product_id']}")

source_counts = Counter(row["source"] for row in analysis_reviews)
target_increment = source_counts["Target"] - PRIOR_TARGET_WRITTEN_COUNT
walmart_increment = source_counts["Walmart"]
refresh_added = target_increment + walmart_increment
target_recent_matched = sum(row["source"] == "Target" for row in RETAIL["reviews"]) - target_increment
output = dict(BASE_ANALYSIS)
output.update({
    "as_of": AS_OF.isoformat(),
    "scope": [product["name"] for product in REGISTRY["products"]],
    "methodology": {
        **BASE_ANALYSIS.get("methodology", {}),
        "analysis_window": f"{WINDOW_START.isoformat()} through {AS_OF.isoformat()}",
        "archive_floor": BACKFILL_START.isoformat(),
        "post_definition": f"Reviews dated {CUTOFF.isoformat()} through {AS_OF.isoformat()}",
        "retailer_collection": "Complete public Walmart written set; current Target rating distributions and incremental recent reviews; Amazon remains a labeled first-page sample.",
    },
    "data_quality": {
        **BASE_ANALYSIS.get("data_quality", {}),
        "captured_records_after_dedup": len(reviews),
        "metric_eligible_written_reviews": len(analysis_reviews),
        "written_reviews_in_analysis_window": sum(period(row) != "archive" for row in analysis_reviews),
        "excluded_lower_fidelity_records": len(reviews) - len(analysis_reviews),
        "brand_reviews_since_2023": len(BRAND["reviews"]),
        "within_source_duplicates_removed": len(rows) - len(within_rows),
        "cross_source_duplicates_removed": len(within_rows) - len(reviews),
        "retailer_records_added_in_refresh": refresh_added,
        "target_records_added_in_refresh": target_increment,
        "target_recent_records_matched_to_archive": target_recent_matched,
        "walmart_complete_written_reviews": next(snapshot["written_review_count"] for snapshot in RETAIL["snapshots"] if snapshot["source"] == "Walmart"),
        "amazon_collection_status": "20 unique public first-page reviews across two Mongolian ASINs; deeper pages require sign-in",
        "source_counts": dict(sorted(source_counts.items())),
    },
    "overall": overall,
    "products": products,
    "monthly": monthly,
    "rating_snapshots": rating_snapshots,
    "brand_review_capture": {
        "as_of": BRAND["as_of"],
        "backfill_start": BRAND["backfill_start"],
        "collection_method": BRAND["collection_method"],
        "snapshots": BRAND["snapshots"],
    },
    "retailer_refresh": {
        "as_of": RETAIL["as_of"],
        "method_note": RETAIL["method_note"],
        "amazon_note": RETAIL["amazon_note"],
        "snapshots": RETAIL["snapshots"],
    },
})

if len(REGISTRY["products"]) != 8:
    raise RuntimeError("Expected eight Kevin's products")
if any(row["product_id"] not in NAME_BY_ID for row in reviews):
    raise RuntimeError("Unknown product_id in merged reviews")
if any(not (BACKFILL_START <= date.fromisoformat(row["date"]) <= AS_OF) for row in reviews):
    raise RuntimeError("Review outside the retained date scope")

(DATA / "reviews_normalized.json").write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
(DATA / "analysis_output.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "records": len(reviews),
    "metric_eligible": len(analysis_reviews),
    "analysis_window": sum(period(row) != "archive" for row in analysis_reviews),
    "sources": dict(sorted(source_counts.items())),
    "retailer_records_added_in_refresh": refresh_added,
    "target_recent_records_matched_to_archive": target_recent_matched,
    "cross_source_duplicates_removed": len(within_rows) - len(reviews),
    "overall": overall,
}, indent=2))
