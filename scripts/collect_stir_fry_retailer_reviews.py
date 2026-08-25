"""Collect review evidence and coverage for the approved stir-fry retailers.

Only public product pages are used.  Listing confirmation and review evidence
are deliberately separate so an exact page without a review surface is not
reported as zero consumer sentiment.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from collect_stir_fry_reviews import PRODUCTS


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = DATA / "stir_fry_retailer_evidence_2026-08-25.json"
AS_OF = date(2026, 8, 25)
START = date(2023, 1, 1)

TARGET_PRODUCTS = {
    "chicken_fajitas_kit": {
        "item_id": "94978150",
        "url": "https://www.target.com/p/-/A-94978150",
    },
    "general_tso_chicken_kit": {
        "item_id": "94736217",
        "url": "https://www.target.com/p/-/A-94736217",
    },
    "honey_garlic_chicken_kit": {
        "item_id": "94177635",
        "url": "https://www.target.com/p/-/A-94177635",
    },
}

KROGER_PRODUCTS = {
    "chicken_fajitas_kit": "https://www.kroger.com/p/kevin-s-natural-foods-chicken-fajitas-skillet-meal-kit/0081026402818",
    "general_tso_chicken_kit": "https://www.kroger.com/p/kevin-s-natural-foods-general-tso-s-chicken-stir-fry/0081026402812",
    "sichuan_chicken_kit": "https://www.kroger.com/p/kevin-s-natural-foods-sichuan-chicken-stir-fry/0081026402816",
    "honey_garlic_chicken_kit": "https://www.kroger.com/p/kevin-s-natural-foods-honey-garlic-chicken-stir-fry/0081026402815",
}

KROGER_PUBLIC_CONTEXT = {
    "chicken_fajitas_kit": {"average_rating": 2.60, "rating_count": 10},
    "general_tso_chicken_kit": {"average_rating": 2.15, "rating_count": 13},
    "sichuan_chicken_kit": {"average_rating": None, "rating_count": 0},
    "honey_garlic_chicken_kit": {"average_rating": 3.90, "rating_count": 10},
}

# Correct a harmless slug typo before requests are made; Kroger keys identity
# from the trailing product identifier, while keeping a readable canonical URL.
EXACT_LISTINGS = {
    ("teriyaki_chicken_kit", "Publix"): "https://www.publix.com/pd/kevins-natural-foods-teriyaki-style-chicken-stir-fry-kit/RIO-PCI-634263",
    ("teriyaki_chicken_kit", "Food Lion"): "https://foodlion.com/groceries/meat/prepared-meat/prepared-chicken/kevins-natural-foods-teriyaki-style-chicken-stir-fry-kit-16-oz-pkg.html",
    ("beef_broccoli_costco", "Costco"): "https://sameday.costco.com/store/costco/products/32881613-kevin-s-natural-foods-beef-broccoli-stir-fry-32-oz",
    ("sichuan_chicken_costco", "Costco"): "https://sameday.costco.com/store/costco/products/28547551-kevin-s-natural-foods-sichuan-style-chicken-with-green-beans-32-oz",
}

RETAILERS = ["Costco", "Target", "Kroger", "Publix", "Albertsons", "Food Lion"]


class ScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[tuple[dict, str]] = []
        self._attrs: dict | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "script":
            self._attrs = dict(attrs)
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._attrs is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._attrs is not None:
            self.scripts.append((self._attrs, "".join(self._parts)))
            self._attrs = None
            self._parts = []


def fetch(url: str, attempts: int = 3) -> tuple[str, str]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "text/html,application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                    "User-Agent": "Mozilla/5.0 (compatible; KNFReviewResearch/1.0)",
                },
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read().decode("utf-8", errors="replace"), response.geturl()
        except Exception as exc:  # pragma: no cover - network retry path
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise last_error or RuntimeError("Request failed")


def clean_text(value) -> str:
    return " ".join(html.unescape(urllib.parse.unquote(str(value or ""))).split())


def next_data(raw: str) -> dict:
    parser = ScriptParser()
    parser.feed(raw)
    for attrs, text in parser.scripts:
        if attrs.get("id") == "__NEXT_DATA__":
            return json.loads(text)
    raise RuntimeError("__NEXT_DATA__ was not found")


def find_target_review_node(value):
    if isinstance(value, dict):
        if isinstance(value.get("most_recent"), list) and isinstance(value.get("statistics"), dict):
            rating = value["statistics"].get("rating") or {}
            if "review_count" in value["statistics"] and "count" in rating:
                return value
        for child in value.values():
            found = find_target_review_node(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_target_review_node(child)
            if found is not None:
                return found
    return None


def collect_target(product_id: str, config: dict) -> tuple[list[dict], dict]:
    raw, final_url = fetch(config["url"])
    node = find_target_review_node(next_data(raw))
    if node is None:
        raise RuntimeError("Target ratings-and-reviews payload was not found")

    reviews = []
    for item in node.get("most_recent", []):
        rating = item.get("rating") or {}
        submitted = rating.get("submitted_at")
        if not submitted:
            continue
        day = date.fromisoformat(submitted[:10])
        text = clean_text(item.get("text"))
        if not text or not (START <= day <= AS_OF):
            continue
        syndication = clean_text(
            item.get("syndication_source")
            or item.get("originally_posted_on")
            or item.get("source")
        )
        reviews.append(
            {
                "product_id": product_id,
                "product": PRODUCTS[product_id]["name"],
                "cohort": PRODUCTS[product_id]["channel"],
                "source": "Target",
                "date": day.isoformat(),
                "rating": int(rating.get("value")),
                "title": clean_text(item.get("title")),
                "text": text,
                "capture": "public retailer review",
                "provider": "Target",
                "provider_review_id": str(item.get("id")),
                "verified_buyer": bool(item.get("verified_purchase")),
                "syndication_source": syndication or None,
                "source_url": final_url,
                "metric_eligible": True,
            }
        )

    statistics = node["statistics"]
    rating = statistics["rating"]
    distribution = {
        str(star): int((rating.get("distribution") or {}).get(f"rating{star}") or 0)
        for star in range(1, 6)
    }
    snapshot = {
        "product_id": product_id,
        "product": PRODUCTS[product_id]["name"],
        "cohort": PRODUCTS[product_id]["channel"],
        "source": "Target",
        "provider": "Target",
        "page_url": final_url,
        "item_id": config["item_id"],
        "average_rating": float(rating["average"]),
        "rating_count": int(rating["count"]),
        "written_review_count": int(statistics["review_count"]),
        "distribution": distribution,
        "captured_recent_reviews": len(reviews),
        "capture_status": "complete_rating_distribution_plus_recent_public_reviews",
        "as_of": AS_OF.isoformat(),
    }
    return reviews, snapshot


def iter_json_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_objects(child)


def collect_kroger_snapshot(product_id: str, url: str) -> dict:
    raw, final_url = fetch(url)
    parser = ScriptParser()
    parser.feed(raw)
    candidates = []
    for attrs, text in parser.scripts:
        if attrs.get("type") != "application/ld+json" or not text.strip():
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        for node in iter_json_objects(payload):
            aggregate = node.get("aggregateRating")
            if isinstance(aggregate, dict) and aggregate.get("ratingValue") is not None:
                candidates.append(aggregate)

    aggregate = candidates[0] if candidates else {}
    average = aggregate.get("ratingValue")
    count = aggregate.get("reviewCount") or aggregate.get("ratingCount")
    return {
        "product_id": product_id,
        "product": PRODUCTS[product_id]["name"],
        "cohort": PRODUCTS[product_id]["channel"],
        "source": "Kroger",
        "provider": "Kroger",
        "page_url": final_url,
        "average_rating": float(average) if average is not None else None,
        "rating_count": int(count) if count is not None else 0,
        "written_review_count": None,
        "distribution": {},
        "captured_written_reviews": 0,
        "capture_status": (
            "public_aggregate_rating_only_text_payload_unavailable"
            if count
            else "exact_listing_no_public_rating_observed"
        ),
        "as_of": AS_OF.isoformat(),
    }


def coverage_rows(snapshots: list[dict], errors: list[dict]) -> list[dict]:
    snapshot_map = {(row["product_id"], row["source"]): row for row in snapshots}
    error_map = {(row["product_id"], row["source"]): row["error"] for row in errors}
    rows = []
    for product_id, product in PRODUCTS.items():
        for retailer in RETAILERS:
            snapshot = snapshot_map.get((product_id, retailer))
            exact_url = EXACT_LISTINGS.get((product_id, retailer))
            intended_channel = product["channel"] == "costco_only"
            if snapshot:
                status = "review_evidence" if snapshot.get("rating_count") else "listing_only"
                page_url = snapshot["page_url"]
                match_type = "exact_sku"
            elif exact_url:
                status = "listing_only"
                page_url = exact_url
                match_type = "exact_sku"
            elif intended_channel and retailer == "Costco":
                status = "official_costco_only_sku_page_not_indexed"
                page_url = "https://www.kevinsnaturalfoods.com/products/" + product["handle"]
                match_type = "official_sku_channel_assignment"
            elif intended_channel:
                status = "not_applicable_costco_only"
                page_url = None
                match_type = "not_applicable"
            else:
                status = "exact_page_not_confirmed"
                page_url = None
                match_type = "not_located"
            rows.append(
                {
                    "product_id": product_id,
                    "product": product["name"],
                    "cohort": product["channel"],
                    "source": retailer,
                    "status": status,
                    "match_type": match_type,
                    "page_url": page_url,
                    "note": error_map.get((product_id, retailer)),
                }
            )
    return rows


def main() -> None:
    reviews = []
    snapshots = []
    errors = []

    for product_id, config in TARGET_PRODUCTS.items():
        try:
            rows, snapshot = collect_target(product_id, config)
            reviews.extend(rows)
            snapshots.append(snapshot)
            print(product_id, "Target", len(rows), "recent /", snapshot["rating_count"], "ratings")
        except Exception as exc:
            errors.append({"product_id": product_id, "source": "Target", "error": f"{type(exc).__name__}: {exc}"})
            print(product_id, "Target ERROR", exc)

    for product_id, url in KROGER_PRODUCTS.items():
        try:
            snapshot = collect_kroger_snapshot(product_id, url)
            snapshots.append(snapshot)
            print(product_id, "Kroger", snapshot["average_rating"], snapshot["rating_count"])
        except Exception as exc:
            context = KROGER_PUBLIC_CONTEXT[product_id]
            snapshots.append({
                "product_id": product_id,
                "product": PRODUCTS[product_id]["name"],
                "cohort": PRODUCTS[product_id]["channel"],
                "source": "Kroger",
                "provider": "Kroger",
                "page_url": url,
                "average_rating": context["average_rating"],
                "rating_count": context["rating_count"],
                "written_review_count": None,
                "distribution": {},
                "captured_written_reviews": 0,
                "capture_status": (
                    "public_index_aggregate_rating_only_text_payload_unavailable"
                    if context["rating_count"]
                    else "exact_listing_no_public_rating_observed"
                ),
                "as_of": AS_OF.isoformat(),
            })
            errors.append({
                "product_id": product_id,
                "source": "Kroger",
                "error": "Live page blocked automated refresh; verified public index aggregate retained.",
            })
            print(product_id, "Kroger FALLBACK", context["average_rating"], context["rating_count"], type(exc).__name__)

    payload = {
        "as_of": AS_OF.isoformat(),
        "analysis_start": START.isoformat(),
        "method_note": (
            "Public retailer pages only. Target provides complete current rating distributions and a recent written-review window. "
            "Kroger provides public aggregate rating context but no reproducible written-review payload. Publix, Albertsons, "
            "Food Lion, and Costco are retained as listing coverage unless a public review surface is confirmed."
        ),
        "deduplication_note": "Cross-posted written records are deduplicated during analysis using product, date, rating, title, and body text.",
        "snapshots": snapshots,
        "reviews": sorted(reviews, key=lambda row: (row["date"], row["product_id"]), reverse=True),
        "coverage": coverage_rows(snapshots, errors),
        "errors": errors,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote", OUTPUT, "reviews", len(reviews), "snapshots", len(snapshots), "errors", len(errors))


if __name__ == "__main__":
    main()
