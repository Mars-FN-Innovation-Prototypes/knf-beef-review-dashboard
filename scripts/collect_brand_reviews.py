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
OUTPUT = ROOT / "analysis" / "brand_reviews_2026-07-15.json"
AS_OF = date(2026, 7, 15)
BACKFILL_START = date(2023, 1, 1)
SHOP_DOMAIN = "kevins-natural-foods.myshopify.com"
PLATFORM = "shopify"
BASE_URL = "https://www.kevinsnaturalfoods.com/products/"
FEED_URL = "https://cdn.judge.me/reviews/reviews_for_widget"

PRODUCTS = {
    "korean_bbq_beef": "korean-bbq-style-steak-tips",
    "honey_garlic_beef": "honey-garlic-beef",
    "sirloin_gravy": "sirloin-steak-tips-with-gravy",
    "teriyaki_beef": "teriyaki-style-beef",
    "mongolian_beef": "mongolian-style-beef",
    "peppercorn_steak_tips": "peppercorn-steak-tips",
    "chimichurri_beef": "chimichurri-beef",
    "sirloin_mushroom": "top-sirloin-beef-with-creamy-mushroom-sauce",
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


def embedded_payload(page_html: str) -> dict:
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
    return json.loads(payload_text)


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


def normalize_review(product_id: str, product_page: str, row: dict) -> dict:
    review_date = date.fromisoformat(row["created_at"][:10])
    return {
        "product_id": product_id,
        "source": "Kevin's Natural Foods",
        "date": review_date.isoformat(),
        "rating": int(row["rating"]),
        "title": html.unescape(strip_html(row.get("title"))),
        "text": strip_html(row.get("body_html") or row.get("body")),
        "capture": "first-party public review",
        "provider": "Judge.me",
        "provider_review_id": row.get("uuid"),
        "verified_buyer": bool(row.get("verified_buyer")),
        "transparency_badges": row.get("transparency_badges") or [],
        "source_url": product_page,
    }


def collect_product(product_id: str, handle: str) -> tuple[list[dict], dict]:
    product_page = BASE_URL + handle
    first = embedded_payload(fetch_text(product_page))
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

    normalized = [normalize_review(product_id, product_page, row) for row in raw_reviews]
    in_scope = [
        row
        for row in normalized
        if BACKFILL_START <= date.fromisoformat(row["date"]) <= AS_OF
        and (row["title"] or row["text"])
    ]
    histogram = {str(item["rating"]): int(item["frequency"]) for item in first.get("histogram", [])}
    snapshot = {
        "product_id": product_id,
        "source": "Kevin's Natural Foods",
        "page_url": product_page,
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
    for product_id, handle in PRODUCTS.items():
        product_reviews, snapshot = collect_product(product_id, handle)
        reviews.extend(product_reviews)
        snapshots.append(snapshot)
        print(
            f"{product_id}: {snapshot['written_reviews_since_2023']} included "
            f"of {snapshot['rating_count']} aggregate ratings"
        )

    payload = {
        "as_of": AS_OF.isoformat(),
        "backfill_start": BACKFILL_START.isoformat(),
        "collection_method": (
            "Public first-party product pages and their storefront review feed; "
            "full text retained, HTML removed, reviewer names omitted."
        ),
        "source": "Kevin's Natural Foods",
        "provider": "Judge.me",
        "snapshots": snapshots,
        "reviews": sorted(reviews, key=lambda row: (row["date"], row["product_id"]), reverse=True),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(reviews)} reviews to {OUTPUT}")


if __name__ == "__main__":
    main()
