"""Collect public review evidence for the verified Kevin's retailer pages."""

from __future__ import annotations

import html
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = DATA / "core_retailer_collection_2026-07-22.json"
AS_OF = date(2026, 7, 22)
BACKFILL_START = date(2023, 1, 1)

TARGET_PRODUCTS = {
    "sirloin_gravy": {
        "name": "Sirloin Steak Tips with Gravy",
        "url": "https://www.target.com/p/kevin-39-s-natural-foods-gluten-free-sirloin-steak-tips-with-gravy-16oz/-/A-88883892",
        "item_id": "88883892",
    },
    "teriyaki_beef": {
        "name": "Teriyaki-Style Beef",
        "url": "https://www.target.com/p/kevin-39-s-gluten-free-teriyaki-style-beef-16oz/-/A-87790111",
        "item_id": "87790111",
    },
}

WALMART_PRODUCTS = {
    "honey_garlic_beef": {
        "name": "Honey Garlic Beef",
        "item_id": "2455684608",
        "url": "https://www.walmart.com/reviews/product/2455684608",
    }
}


class ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self._attrs = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._attrs = dict(attrs)
            self._parts = []

    def handle_data(self, data):
        if self._attrs is not None:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._attrs is not None:
            self.scripts.append((self._attrs, "".join(self._parts)))
            self._attrs = None
            self._parts = []


def fetch(url: str, attempts: int = 3) -> tuple[str, str]:
    last_error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "text/html,application/json",
                    "User-Agent": "Mozilla/5.0 (compatible; KNFReviewResearch/2.0)",
                },
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read().decode("utf-8", errors="replace"), response.geturl()
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def next_data(raw: str) -> dict:
    parser = ScriptParser()
    parser.feed(raw)
    for attrs, text in parser.scripts:
        if attrs.get("id") == "__NEXT_DATA__":
            return json.loads(text)
    raise RuntimeError("__NEXT_DATA__ was not found")


def clean_text(value) -> str:
    text = urllib.parse.unquote(str(value or ""))
    return " ".join(html.unescape(text).split())


def find_review_node(value):
    if isinstance(value, dict):
        if isinstance(value.get("most_recent"), list) and isinstance(value.get("statistics"), dict):
            statistics = value["statistics"]
            if isinstance(statistics.get("rating"), dict) and "review_count" in statistics:
                return value
        for child in value.values():
            found = find_review_node(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_review_node(child)
            if found is not None:
                return found
    return None


def collect_target(product_id: str, config: dict) -> tuple[list[dict], dict]:
    raw, final_url = fetch(config["url"])
    payload = next_data(raw)
    node = find_review_node(payload)
    if node is None:
        raise RuntimeError("Target ratings_and_reviews node was not found")
    reviews = []
    for item in node.get("most_recent", []):
        rating = item.get("rating") or {}
        submitted = rating.get("submitted_at")
        if not submitted:
            continue
        day = date.fromisoformat(submitted[:10])
        text = clean_text(item.get("text"))
        if not text or not (BACKFILL_START <= day <= AS_OF):
            continue
        reviews.append({
            "product_id": product_id,
            "product": config["name"],
            "source": "Target",
            "date": day.isoformat(),
            "rating": int(rating.get("value")),
            "title": clean_text(item.get("title")),
            "text": text,
            "capture": "public retailer review",
            "provider": "Target",
            "provider_review_id": str(item.get("id")),
            "verified_buyer": False,
            "source_url": final_url,
            "metric_eligible": True,
        })
    statistics = node["statistics"]
    rating = statistics["rating"]
    distribution = {str(star): int(rating.get("distribution", {}).get(f"rating{star}") or 0) for star in range(1, 6)}
    snapshot = {
        "product_id": product_id,
        "product": config["name"],
        "source": "Target",
        "provider": "Target",
        "page_url": final_url,
        "item_id": config["item_id"],
        "average_rating": float(rating.get("average")),
        "rating_count": int(rating.get("count")),
        "written_review_count": int(statistics.get("review_count")),
        "distribution": distribution,
        "captured_recent_reviews": len(reviews),
        "capture_status": "complete_rating_distribution_plus_recent_public_reviews",
        "as_of": AS_OF.isoformat(),
    }
    return reviews, snapshot


def walmart_page(url: str, page: int) -> tuple[list[dict], dict, str]:
    separator = "&" if "?" in url else "?"
    page_url = f"{url}{separator}{urllib.parse.urlencode({'page': page, 'sort': 'submission-desc'})}"
    raw, final_url = fetch(page_url)
    payload = next_data(raw)
    review_data = payload["props"]["pageProps"]["initialData"]["data"]["reviews"]
    return review_data.get("customerReviews", []), review_data, final_url


def collect_walmart(product_id: str, config: dict) -> tuple[list[dict], dict]:
    first_rows, first_data, _ = walmart_page(config["url"], 1)
    expected_written = int(first_data.get("reviewsWithTextCount") or 0)
    max_pages = max(1, math.ceil(expected_written / 10) + 3)
    seen = {}
    last_new_page = 0
    final_url = config["url"]
    for page in range(1, max_pages + 1):
        rows, review_data, final_url = (first_rows, first_data, config["url"]) if page == 1 else walmart_page(config["url"], page)
        before = len(seen)
        for item in rows:
            key = str(item.get("reviewId") or item.get("reviewReferenceId"))
            if key and key not in seen:
                seen[key] = item
        if len(seen) > before:
            last_new_page = page
        if len(seen) >= expected_written or page - last_new_page >= 2:
            break
        time.sleep(0.35)

    reviews = []
    for item in seen.values():
        submitted = item.get("reviewSubmissionTime")
        if not submitted:
            continue
        day = datetime.strptime(submitted, "%m/%d/%Y").date()
        text = clean_text(item.get("reviewText"))
        if not text or not (BACKFILL_START <= day <= AS_OF):
            continue
        badges = item.get("badges") or []
        reviews.append({
            "product_id": product_id,
            "product": config["name"],
            "source": "Walmart",
            "date": day.isoformat(),
            "rating": int(item.get("rating")),
            "title": clean_text(item.get("reviewTitle")),
            "text": text,
            "capture": "public retailer review",
            "provider": "Walmart",
            "provider_review_id": str(item.get("reviewId") or item.get("reviewReferenceId")),
            "verified_buyer": any(badge.get("id") == "VerifiedPurchaser" for badge in badges),
            "source_url": final_url,
            "metric_eligible": True,
        })
    distribution = {str(star): int(first_data.get(f"ratingValue{['Zero','One','Two','Three','Four','Five'][star]}Count") or 0) for star in range(1, 6)}
    snapshot = {
        "product_id": product_id,
        "product": config["name"],
        "source": "Walmart",
        "provider": "Walmart",
        "page_url": f"https://www.walmart.com/ip/{config['item_id']}",
        "item_id": config["item_id"],
        "average_rating": float(first_data.get("roundedAverageOverallRating") or first_data.get("averageOverallRating")),
        "rating_count": int(first_data.get("totalReviewCount")),
        "written_review_count": expected_written,
        "distribution": distribution,
        "captured_written_reviews": len(reviews),
        "capture_status": "complete_public_written_set" if len(reviews) == expected_written else "partial_public_written_set",
        "as_of": AS_OF.isoformat(),
    }
    return sorted(reviews, key=lambda row: row["date"], reverse=True), snapshot


def main():
    reviews = []
    snapshots = []
    errors = []
    for product_id, config in TARGET_PRODUCTS.items():
        try:
            rows, snapshot = collect_target(product_id, config)
            reviews.extend(rows)
            snapshots.append(snapshot)
            print(product_id, "Target", len(rows), "recent rows", snapshot["written_review_count"], "written total")
        except Exception as exc:
            errors.append({"product_id": product_id, "source": "Target", "error": f"{type(exc).__name__}: {exc}"})
            print(product_id, "Target ERROR", exc)
    for product_id, config in WALMART_PRODUCTS.items():
        try:
            rows, snapshot = collect_walmart(product_id, config)
            reviews.extend(rows)
            snapshots.append(snapshot)
            print(product_id, "Walmart", len(rows), "captured", snapshot["written_review_count"], "written total")
        except Exception as exc:
            errors.append({"product_id": product_id, "source": "Walmart", "error": f"{type(exc).__name__}: {exc}"})
            print(product_id, "Walmart ERROR", exc)

    payload = {
        "as_of": AS_OF.isoformat(),
        "backfill_start": BACKFILL_START.isoformat(),
        "method_note": "Public retailer pages only. Walmart pages were paginated until the public written-review count was reached. Target public pages expose complete rating distributions and the most recent written records; the existing Target archive is retained and incrementally updated.",
        "amazon_note": "Amazon review pages require sign-in beyond the public first page. The two verified Mongolian ASIN samples remain capped at 10 unique written reviews each; no access control was bypassed.",
        "snapshots": snapshots,
        "reviews": sorted(reviews, key=lambda row: (row["date"], row["source"], row["product_id"]), reverse=True),
        "errors": errors,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUTPUT, "reviews", len(reviews), "snapshots", len(snapshots), "errors", len(errors))


if __name__ == "__main__":
    main()
