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


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "stir_fry_brand_reviews_2026-08-25.json"
AS_OF = date(2026, 8, 25)
BACKFILL_START = date(2023, 1, 1)
SHOP_DOMAIN = "kevins-natural-foods.myshopify.com"
PLATFORM = "shopify"
BASE_URL = "https://www.kevinsnaturalfoods.com/products/"
FEED_URL = "https://cdn.judge.me/reviews/reviews_for_widget"

# The official Kevin's catalog listed these 13 products under Stir-Fry Entrees
# on 2026-08-25.  Grocery kits launched in February 2025.  The seven 32 oz / four-
# serving items are kept as a separate Costco-only cohort.
PRODUCTS = {
    "beef_fajitas": {"name": "Beef Fajitas", "handle": "beef-fajitas", "channel": "costco_only", "servings": 4},
    "teriyaki_chicken_kit": {"name": "Teriyaki-Style Chicken Stir-Fry Kit", "handle": "teriyaki-style-chicken-stir-fry-kit", "channel": "grocery", "servings": 2.5},
    "beef_broccoli_kit": {"name": "Beef & Broccoli Stir-Fry Kit", "handle": "beef-broccoli-stir-fry-kit", "channel": "grocery", "servings": 2.5},
    "chicken_fajitas_kit": {"name": "Chicken Fajitas Skillet Meal Kit", "handle": "chicken-fajitas-skillet-meal-kit", "channel": "grocery", "servings": 2.5},
    "general_tso_chicken_kit": {"name": "General Tso's Chicken Stir-Fry Kit", "handle": "general-tso-s-chicken-with-green-beans", "channel": "grocery", "servings": 2.5},
    "sichuan_chicken_kit": {"name": "Sichuan Chicken Stir-Fry Kit", "handle": "sichuan-chicken-stir-fry-kit", "channel": "grocery", "servings": 2.5},
    "honey_garlic_chicken_kit": {"name": "Honey Garlic Chicken Stir-Fry Kit", "handle": "honey-garlic-chicken-stir-fry-kit", "channel": "grocery", "servings": 2.5},
    "orange_chicken_costco": {"name": "Orange Chicken Stir-Fry", "handle": "orange-chicken-stir-fry", "channel": "costco_only", "servings": 4},
    "honey_garlic_chicken_costco": {"name": "Honey Garlic Chicken Stir-Fry", "handle": "honey-garlic-chicken-green-bean-stir-fry", "channel": "costco_only", "servings": 4},
    "beef_broccoli_costco": {"name": "Beef & Broccoli Stir-Fry", "handle": "beef-broccoli-stir-fry", "channel": "costco_only", "servings": 4},
    "sichuan_chicken_costco": {"name": "Sichuan Chicken Green Bean Stir-Fry", "handle": "sichuan-chicken-green-bean-stir-fry", "channel": "costco_only", "servings": 4},
    "hot_honey_garlic_chicken_costco": {"name": "Hot Honey Garlic Chicken Stir-Fry", "handle": "hot-honey-garlic-chicken-stir-fry", "channel": "costco_only", "servings": 4},
    "teriyaki_chicken_costco": {"name": "Teriyaki-Style Chicken Stir-Fry", "handle": "teriyaki-style-chicken-stir-fry", "channel": "costco_only", "servings": 4},
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"br", "p", "li"}:
            self.parts.append(" ")

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def strip_html(value: str | None) -> str:
    parser = TextExtractor()
    parser.feed(html.unescape(value or ""))
    return parser.text()


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/json",
            "User-Agent": "Mozilla/5.0 (compatible; KNFReviewResearch/1.0)",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def embedded_payload(page_html: str) -> tuple[str, dict]:
    product_match = re.search(r'data-product-id="(\d+)"', page_html)
    if not product_match:
        raise RuntimeError("Product ID was not found in the storefront page")
    product_id = product_match.group(1)
    marker = f"jdgm.data.reviewWidget[{product_id}] = "
    start = page_html.find(marker)
    if start < 0:
        raise RuntimeError(f"Review payload was not found for product {product_id}")
    start += len(marker)
    end = page_html.find("</script>", start)
    payload_text = page_html[start:end].strip().removesuffix(";")
    return product_id, json.loads(payload_text)


def feed_page(product_id: str, page: int, timestamp: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "product_id": product_id,
            "page": page,
            "sort_by": "created_at",
            "sort_dir": "desc",
            "ts": timestamp,
            "shop_domain": SHOP_DOMAIN,
            "platform": PLATFORM,
        }
    )
    return json.loads(fetch_text(f"{FEED_URL}?{query}"))


def normalize_review(product_id: str, product: dict, product_page: str, row: dict) -> dict:
    review_date = date.fromisoformat(row["created_at"][:10])
    return {
        "product_id": product_id,
        "product": product["name"],
        "cohort": product["channel"],
        "source": "Kevin's Natural Foods",
        "date": review_date.isoformat(),
        "rating": int(row["rating"]),
        "title": html.unescape(strip_html(row.get("title"))),
        "text": strip_html(row.get("body_html") or row.get("body")),
        "capture": "complete first-party public review feed",
        "provider": "Judge.me",
        "provider_review_id": row.get("uuid"),
        "verified_buyer": bool(row.get("verified_buyer")),
        "transparency_badges": row.get("transparency_badges") or [],
        "source_url": product_page,
        "metric_eligible": True,
    }


def collect_product(product_id: str, product: dict) -> tuple[list[dict], dict]:
    product_page = BASE_URL + product["handle"]
    shopify_product_id, first = embedded_payload(fetch_text(product_page))
    product_external_id = str(first["product_external_id"])
    timestamp = first.get("metafield_updated_at") or AS_OF.isoformat()
    total_pages = int(first["pagination"]["total_pages"])

    raw_reviews: list[dict] = []
    seen_ids: set[str] = set()
    for page in range(1, total_pages + 1):
        payload = first if page == 1 else feed_page(product_external_id, page, timestamp)
        for review in payload.get("reviews", []):
            review_id = review.get("uuid")
            if review_id and review_id in seen_ids:
                continue
            if review_id:
                seen_ids.add(review_id)
            raw_reviews.append(review)
        if page < total_pages:
            time.sleep(0.12)

    normalized = [normalize_review(product_id, product, product_page, row) for row in raw_reviews]
    in_scope = [
        row for row in normalized
        if BACKFILL_START <= date.fromisoformat(row["date"]) <= AS_OF
        and (row["title"] or row["text"])
    ]
    histogram = {str(item["rating"]): int(item["frequency"]) for item in first.get("histogram", [])}
    snapshot = {
        "product_id": product_id,
        "product": product["name"],
        "cohort": product["channel"],
        "source": "Kevin's Natural Foods",
        "page_url": product_page,
        "shopify_product_id": shopify_product_id,
        "product_external_id": product_external_id,
        "rating_count": int(first["number_of_reviews"]),
        "average_rating": float(first["average_rating"]),
        "distribution": histogram,
        "feed_records_retrieved": len(raw_reviews),
        "written_reviews_since_2023": len(in_scope),
        "earliest_included_date": min((row["date"] for row in in_scope), default=None),
        "latest_included_date": max((row["date"] for row in in_scope), default=None),
        "captured_at": AS_OF.isoformat(),
    }
    if len(raw_reviews) != int(first["number_of_reviews"]):
        snapshot["count_note"] = "Provider aggregate includes records not returned by the public written-review feed."
    return in_scope, snapshot


def main() -> None:
    reviews: list[dict] = []
    snapshots: list[dict] = []
    for product_id, product in PRODUCTS.items():
        product_reviews, snapshot = collect_product(product_id, product)
        reviews.extend(product_reviews)
        snapshots.append(snapshot)
        print(f"{product_id}: {len(product_reviews)} included of {snapshot['rating_count']} aggregate ratings")

    payload = {
        "as_of": AS_OF.isoformat(),
        "backfill_start": BACKFILL_START.isoformat(),
        "scope_note": "13 products listed in the official Stir-Fry Entrees catalog section on 2026-08-25.",
        "cohort_note": "Six 2.5-serving grocery kits launched in February 2025; seven four-serving items are treated as Costco-only based on stakeholder guidance and official product metadata.",
        "collection_method": "Complete public first-party product-page review feed; reviewer names omitted.",
        "source": "Kevin's Natural Foods",
        "provider": "Judge.me",
        "snapshots": snapshots,
        "reviews": sorted(reviews, key=lambda row: (row["date"], row["product_id"]), reverse=True),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(reviews)} reviews to {OUTPUT}")


if __name__ == "__main__":
    main()
