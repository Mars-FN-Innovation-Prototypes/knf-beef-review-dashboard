"""Collect the public competitor benchmark evidence used by the dashboard.

The collector intentionally uses only public product pages and the public review
feeds configured by those pages. It does not authenticate, bypass access controls,
or retain reviewer names.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REGISTRY_PATH = DATA / "competitor_sku_registry.json"
OUT_REVIEWS = DATA / "competitor_reviews_normalized.json"
OUT_SNAPSHOTS = DATA / "competitor_rating_snapshots.json"
OUT_AUDIT = DATA / "competitor_coverage_audit.json"

START = date(2023, 1, 1)
END = date(2026, 7, 15)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)

POWERREVIEWS = {
    "hormel_roast_au_jus_15": {
        "page_id": "CF0006787-002",
        "variant": "037600473712",
        "page_url": "https://www.hormel.com/brands/hormel-square-table-entrees/product/beef-roast-au-jus/",
    },
    "hormel_beef_tips_gravy_15": {
        "page_id": "CF0002357-007",
        "variant": "037600154918",
        "page_url": "https://www.hormel.com/brands/hormel-square-table-entrees/product/beef-tips-and-gravy/",
    },
}
POWERREVIEWS_MERCHANT = "109444"
POWERREVIEWS_KEY = "8170e0b8-2a60-460e-9559-3c34e2205cb9"

WALMART = {
    "hormel_roast_au_jus_15": "10291008",
    "hormel_beef_tips_gravy_15": "10290929",
    "soules_beef_fajitas_14": "38227608",
    "soules_fajita_steak_6": "39496073",
    "soules_angus_fajitas_24": "10312195",
    "jack_daniels_brisket": "46575488",
    "brookwood_brisket_16": "1020754218",
    "del_real_barbacoa_15": "169151306",
    "del_real_birria_15": "3859154746",
}


class NextDataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self.capture = True

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.capture:
            self.capture = False


def fetch(url, attempts=3):
    last = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html,*/*"})
            with urlopen(request, timeout=50) as response:
                return response.read(), response.geturl()
        except Exception as exc:
            last = exc
            time.sleep(2 + attempt * 3)
    raise last


def clean_text(value):
    value = unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_epoch(value):
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).date()


def parse_us_date(value):
    return datetime.strptime(value, "%m/%d/%Y").date()


def in_scope(day):
    return START <= day <= END


def get_next_data(raw):
    parser = NextDataParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    if not parser.parts:
        raise ValueError("No __NEXT_DATA__ payload found")
    return json.loads("".join(parser.parts))


def collect_powerreviews(product, config):
    reviews = []
    snapshot = None
    offset = 0
    while True:
        params = {
            "apikey": POWERREVIEWS_KEY,
            "paging.from": offset,
            "paging.size": 25,
            "sort": "Newest",
            "page_locale": "en_US",
        }
        url = (
            f"https://display.powerreviews.com/m/{POWERREVIEWS_MERCHANT}/l/en_US/"
            f"product/{config['page_id']}/reviews?{urlencode(params)}"
        )
        raw, _ = fetch(url)
        payload = json.loads(raw.decode("utf-8"))
        result = payload["results"][0]
        if snapshot is None:
            rollup = result["rollup"]
            histogram = rollup.get("rating_histogram") or [0, 0, 0, 0, 0]
            snapshot = {
                "product_id": product["id"],
                "product": product["name"],
                "brand": product["brand"],
                "source": "Hormel",
                "provider": "PowerReviews",
                "page_url": config["page_url"],
                "average_rating": rollup.get("average_rating"),
                "rating_count": rollup.get("rating_count"),
                "written_review_count": rollup.get("review_count"),
                "distribution": {str(star): histogram[star - 1] for star in range(1, 6)},
                "capture_status": "complete_public_first_party_feed",
                "as_of": "2026-07-21",
            }
        batch = result.get("reviews", [])
        for item in batch:
            details = item.get("details") or {}
            metrics = item.get("metrics") or {}
            day = parse_epoch(details.get("created_date"))
            text = clean_text(details.get("comments"))
            if not text or not in_scope(day):
                continue
            reviews.append({
                "product_id": product["id"],
                "product": product["name"],
                "brand": product["brand"],
                "portfolio": "competitor",
                "benchmark_tier": product["benchmark_tier"],
                "family": product["family"],
                "pack_oz": product["pack_oz"],
                "source": "Hormel",
                "date": day.isoformat(),
                "rating": int(metrics.get("rating")),
                "title": clean_text(details.get("headline")),
                "text": text,
                "capture": "first-party public review",
                "provider": "PowerReviews",
                "provider_review_id": str(item.get("review_id") or item.get("ugc_id")),
                "verified_buyer": bool((item.get("badges") or {}).get("is_verified_buyer")),
                "source_url": config["page_url"],
                "metric_eligible": True,
            })
        offset += len(batch)
        if not batch or offset >= payload["paging"]["total_results"]:
            break
        time.sleep(0.6)
    return reviews, snapshot


def collect_walmart(product, item_id):
    page_url = f"https://www.walmart.com/reviews/product/{item_id}"
    raw, final_url = fetch(page_url)
    payload = get_next_data(raw)
    review_data = payload["props"]["pageProps"]["initialData"]["data"]["reviews"]
    reviews = []
    for item in review_data.get("customerReviews", []):
        try:
            day = parse_us_date(item.get("reviewSubmissionTime"))
        except Exception:
            continue
        text = clean_text(item.get("reviewText"))
        if not text or not in_scope(day):
            continue
        badges = item.get("badges") or []
        verified = any((badge.get("id") == "VerifiedPurchaser") for badge in badges)
        reviews.append({
            "product_id": product["id"],
            "product": product["name"],
            "brand": product["brand"],
            "portfolio": "competitor",
            "benchmark_tier": product["benchmark_tier"],
            "family": product["family"],
            "pack_oz": product["pack_oz"],
            "source": "Walmart",
            "date": day.isoformat(),
            "rating": int(item.get("rating")),
            "title": clean_text(item.get("reviewTitle")),
            "text": text,
            "capture": "public review page sample",
            "provider": "Walmart",
            "provider_review_id": str(item.get("reviewId") or item.get("reviewReferenceId")),
            "verified_buyer": verified,
            "source_url": final_url,
            "metric_eligible": True,
        })
    distribution = {
        "1": int(review_data.get("ratingValueOneCount") or 0),
        "2": int(review_data.get("ratingValueTwoCount") or 0),
        "3": int(review_data.get("ratingValueThreeCount") or 0),
        "4": int(review_data.get("ratingValueFourCount") or 0),
        "5": int(review_data.get("ratingValueFiveCount") or 0),
    }
    snapshot = {
        "product_id": product["id"],
        "product": product["name"],
        "brand": product["brand"],
        "source": "Walmart",
        "provider": "Walmart",
        "page_url": f"https://www.walmart.com/ip/{item_id}",
        "average_rating": review_data.get("roundedAverageOverallRating") or review_data.get("averageOverallRating"),
        "rating_count": review_data.get("totalReviewCount"),
        "written_review_count": review_data.get("reviewsWithTextCount"),
        "distribution": distribution,
        "captured_written_reviews": len(reviews),
        "capture_status": "public_ssr_sample_plus_complete_rating_distribution",
        "as_of": "2026-07-21",
    }
    return reviews, snapshot


def signature(review):
    normalized = "|".join([
        review["product_id"], review["date"], str(review["rating"]),
        clean_text(review.get("title")).lower(), clean_text(review.get("text")).lower(),
    ])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def deduplicate(reviews):
    source_ids = set()
    signatures = set()
    output = []
    for review in sorted(reviews, key=lambda row: (row["date"], row["product_id"], row["source"]), reverse=True):
        source_key = (review["source"], review["provider_review_id"])
        sig = signature(review)
        if source_key in source_ids or sig in signatures:
            continue
        source_ids.add(source_key)
        signatures.add(sig)
        output.append(review)
    return output


def build_coverage(products, snapshots, errors):
    snapshot_keys = {(row["product_id"], row["source"]) for row in snapshots}
    rows = []
    source_keys = {
        "Brand": "brand", "Target": "target", "Amazon": "amazon",
        "Kroger": "kroger", "Walmart": "walmart", "Costco": "costco",
    }
    for product in products:
        pages = product.get("retailer_pages") or {}
        for source, key in source_keys.items():
            page_url = pages.get(key)
            search_url = pages.get(f"{key}_search")
            has_snapshot = (product["id"], product["brand"] if source == "Brand" else source) in snapshot_keys
            if page_url:
                if source == "Costco" and product["pack_oz"] <= 20:
                    match_type = "club_pack_variant"
                else:
                    match_type = "exact_listed_sku"
                status = "review_evidence" if has_snapshot else "listing_only"
            elif search_url:
                match_type = "search_only"
                status = "exact_page_not_confirmed"
                page_url = search_url
            else:
                match_type = "not_located"
                status = "not_located"
            rows.append({
                "product_id": product["id"],
                "brand": product["brand"],
                "product": product["name"],
                "benchmark_tier": product["benchmark_tier"],
                "source": source,
                "status": status,
                "match_type": match_type,
                "pack_oz": product["pack_oz"],
                "page_url": page_url,
                "note": errors.get((product["id"], source)),
            })
    return rows


def main():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    products = {item["id"]: item for item in registry["products"]}
    all_reviews = []
    snapshots = []
    errors = {}

    for product_id, config in POWERREVIEWS.items():
        try:
            rows, snapshot = collect_powerreviews(products[product_id], config)
            all_reviews.extend(rows)
            snapshots.append(snapshot)
            print(product_id, "Hormel", len(rows), "reviews")
        except Exception as exc:
            errors[(product_id, "Brand")] = f"Collection error: {type(exc).__name__}"
            print(product_id, "Hormel ERROR", exc)

    for product_id, item_id in WALMART.items():
        try:
            rows, snapshot = collect_walmart(products[product_id], item_id)
            all_reviews.extend(rows)
            snapshots.append(snapshot)
            print(product_id, "Walmart", len(rows), "reviews")
        except Exception as exc:
            errors[(product_id, "Walmart")] = f"Collection error: {type(exc).__name__}"
            print(product_id, "Walmart ERROR", exc)
        time.sleep(1)

    deduped = deduplicate(all_reviews)
    coverage = build_coverage(list(products.values()), snapshots, errors)

    OUT_REVIEWS.write_text(json.dumps(deduped, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_SNAPSHOTS.write_text(json.dumps({
        "as_of": "2026-07-21",
        "method_note": "Rating distributions are point-in-time context. Walmart dated text is the public server-rendered sample, not the full written-review archive; Hormel PowerReviews histories are complete public first-party feeds.",
        "snapshots": snapshots,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_AUDIT.write_text(json.dumps({
        "as_of": "2026-07-21",
        "sources_audited": ["Brand", "Target", "Amazon", "Kroger", "Walmart", "Costco"],
        "rows": coverage,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("raw", len(all_reviews), "deduplicated", len(deduped), "snapshots", len(snapshots))
    print("date range", min((r["date"] for r in deduped), default=None), max((r["date"] for r in deduped), default=None))


if __name__ == "__main__":
    main()
