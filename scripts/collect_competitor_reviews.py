"""Collect the public competitor benchmark evidence used by the dashboard.

The collector intentionally uses only public product pages and the public review
feeds configured by those pages. It does not authenticate, bypass access controls,
or retain reviewer names.
"""

from __future__ import annotations

import hashlib
import json
import math
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
WALMART_CACHE = DATA / "competitor_walmart_public_sample_2026-07-21.json"

START = date(2023, 1, 1)
END = date(2026, 7, 22)
USER_AGENT = "Mozilla/5.0 (compatible; PublicReviewResearch/2.0)"

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
    # The 38227608 review feed is shared across the 14 oz and 6 oz variants.
    # Review-level Size features and item IDs determine the final product.
    "soules_angus_fajitas_24": "10312195",
    "jack_daniels_brisket": "46575488",
    "brookwood_brisket_16": "1020754218",
    "del_real_barbacoa_15": "169151306",
    "del_real_birria_15": "3859154746",
}

SOULES_SIZE_PRODUCTS = {
    6: "soules_fajita_steak_6",
    14: "soules_beef_fajitas_14",
    24: "soules_angus_fajitas_24",
}
SOULES_ITEM_PRODUCTS = {
    "38227608": "soules_beef_fajitas_14",
    "39496073": "soules_fajita_steak_6",
    "10312195": "soules_angus_fajitas_24",
}

# Exact public Kroger rating totals. The page text is not exposed through a
# reproducible public review payload, so these remain rating-only context.
KROGER_RATING_CONTEXT = {
    "hormel_roast_au_jus_15": (3.66, 35),
    "hormel_beef_tips_gravy_15": (2.95, 22),
    "soules_beef_fajitas_14": (4.50, 1199),
    "brookwood_brisket_16": (3.00, 6),
    "del_real_barbacoa_15": (4.26, 138),
    "del_real_birria_15": (4.13, 54),
}

RELATED_VARIANTS = {
    ("soules_beef_fajitas_14", "Target"): {
        "url": "https://www.target.com/p/john-soules-foods-fully-cooked-beef-fajitas-frozen-12oz/-/A-14871276",
        "note": "Related 12 oz frozen pack (791 ratings), excluded from the supplied 14 oz benchmark.",
    },
    ("del_real_barbacoa_15", "Target"): {
        "url": "https://www.target.com/p/-/A-84724173",
        "note": "Related 12 oz pack (434 ratings), excluded from the supplied 15 oz benchmark.",
    },
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
            request = Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/html,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            })
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
                "as_of": END.isoformat(),
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


def walmart_page(item_id, page):
    page_url = f"https://www.walmart.com/reviews/product/{item_id}?{urlencode({'page': page, 'sort': 'submission-desc'})}"
    raw, final_url = fetch(page_url)
    payload = get_next_data(raw)
    review_data = payload["props"]["pageProps"]["initialData"]["data"]["reviews"]
    return page, review_data.get("customerReviews", []), review_data, final_url


def feature_size_oz(item):
    for feature in item.get("features") or []:
        if str(feature.get("name") or "").strip().lower() != "size":
            continue
        match = re.search(r"(\d+(?:\.\d+)?)\s*oz", str(feature.get("value") or ""), re.I)
        if match:
            return int(round(float(match.group(1))))
    return None


def assigned_walmart_product(source_product_id, item):
    if not source_product_id.startswith("soules_"):
        return source_product_id, None, "canonical_exact_page"
    size_oz = feature_size_oz(item)
    if size_oz in SOULES_SIZE_PRODUCTS:
        return SOULES_SIZE_PRODUCTS[size_oz], size_oz, "review_level_size_feature"
    item_product = SOULES_ITEM_PRODUCTS.get(str(item.get("itemId") or ""))
    if item_product:
        return item_product, size_oz, "review_level_item_id"
    return None, size_oz, "unresolved_shared_variant"


def collect_walmart(product, item_id, products):
    first_page, first_rows, first_data, first_url = walmart_page(item_id, 1)
    expected_written = int(first_data.get("reviewsWithTextCount") or 0)
    max_pages = max(1, math.ceil(expected_written / 10) + 2)
    seen = {}
    pages_scanned = 0
    past_floor_pages = 0
    reached_archive_floor = False
    exhausted_lifetime = False
    final_url = first_url

    for page in range(1, max_pages + 1):
        if page == 1:
            _, rows, review_data, final_url = first_page, first_rows, first_data, first_url
        else:
            _, rows, review_data, final_url = walmart_page(item_id, page)
        pages_scanned = page
        if not rows:
            exhausted_lifetime = True
            break
        page_dates = []
        for item in rows:
            key = str(item.get("reviewId") or item.get("reviewReferenceId") or "")
            if key and key not in seen:
                retained = dict(item)
                retained["_source_url"] = final_url
                seen[key] = retained
            try:
                page_dates.append(parse_us_date(item.get("reviewSubmissionTime")))
            except Exception:
                pass
        if page_dates and max(page_dates) < START:
            past_floor_pages += 1
        else:
            past_floor_pages = 0
        if past_floor_pages >= 2:
            reached_archive_floor = True
            break
        if len(seen) >= expected_written:
            exhausted_lifetime = True
            break
        time.sleep(0.55)

    reviews = []
    unresolved_variants = 0
    out_of_scope_variants = 0
    for item in seen.values():
        try:
            day = parse_us_date(item.get("reviewSubmissionTime"))
        except Exception:
            continue
        text = clean_text(item.get("reviewText"))
        if not text or not in_scope(day):
            continue
        assigned_id, variant_size, assignment = assigned_walmart_product(product["id"], item)
        if assigned_id is None:
            unresolved_variants += 1
            continue
        if assigned_id not in products:
            out_of_scope_variants += 1
            continue
        assigned = products[assigned_id]
        badges = item.get("badges") or []
        verified = any((badge.get("id") == "VerifiedPurchaser") for badge in badges)
        reviews.append({
            "product_id": assigned["id"],
            "product": assigned["name"],
            "brand": assigned["brand"],
            "portfolio": "competitor",
            "benchmark_tier": assigned["benchmark_tier"],
            "family": assigned["family"],
            "pack_oz": assigned["pack_oz"],
            "source": "Walmart",
            "date": day.isoformat(),
            "rating": int(item.get("rating")),
            "title": clean_text(item.get("reviewTitle")),
            "text": text,
            "capture": "complete public in-scope review-page archive",
            "provider": "Walmart",
            "provider_review_id": str(item.get("reviewId") or item.get("reviewReferenceId")),
            "verified_buyer": verified,
            "source_url": item.get("_source_url") or final_url,
            "review_variant_size_oz": variant_size,
            "variant_assignment": assignment,
            "syndication_source": clean_text(item.get("syndicationSource")),
            "metric_eligible": True,
        })
    distribution = {
        "1": int(first_data.get("ratingValueOneCount") or 0),
        "2": int(first_data.get("ratingValueTwoCount") or 0),
        "3": int(first_data.get("ratingValueThreeCount") or 0),
        "4": int(first_data.get("ratingValueFourCount") or 0),
        "5": int(first_data.get("ratingValueFiveCount") or 0),
    }
    complete_in_scope = reached_archive_floor or exhausted_lifetime
    shared_variant = item_id == "38227608"
    snapshot = {
        "product_id": product["id"],
        "product": product["name"],
        "brand": product["brand"],
        "source": "Walmart",
        "provider": "Walmart",
        "page_url": f"https://www.walmart.com/ip/{item_id}",
        "average_rating": first_data.get("roundedAverageOverallRating") or first_data.get("averageOverallRating"),
        "rating_count": first_data.get("totalReviewCount"),
        "written_review_count": expected_written,
        "distribution": distribution,
        "captured_written_reviews": len(reviews),
        "pages_scanned": pages_scanned,
        "capture_status": "complete_public_in_scope_written_set" if complete_in_scope else "partial_public_in_scope_written_set",
        "snapshot_scope": "shared_variant_family" if shared_variant else "listed_sku_page",
        "related_product_ids": ["soules_beef_fajitas_14", "soules_fajita_steak_6"] if item_id == "38227608" else [],
        "unresolved_in_scope_variants": unresolved_variants,
        "excluded_out_of_scope_variants": out_of_scope_variants,
        "as_of": END.isoformat(),
    }
    return reviews, snapshot


def cached_walmart_fallback(product, item_id, products):
    """Retain the last verified public sample when Walmart blocks a refresh.

    Shared Soules text is kept for auditability but excluded from product metrics
    unless a review-level size field resolves the exact variant.
    """
    cache = json.loads(WALMART_CACHE.read_text(encoding="utf-8"))
    shared_ids = {"soules_beef_fajitas_14", "soules_fajita_steak_6"}
    if item_id == "38227608":
        source_rows = [row for row in cache["reviews"] if row["product_id"] in shared_ids]
    else:
        source_rows = [row for row in cache["reviews"] if row["product_id"] == product["id"]]

    rows = []
    for row in source_rows:
        retained = dict(row)
        retained["capture"] = "bounded public review-page sample"
        retained["quality_status"] = "accepted_exact_listed_sku_sample"
        if item_id == "38227608":
            retained["metric_eligible"] = False
            retained["capture"] = "bounded public review-page sample; excluded from product metrics"
            retained["quality_status"] = "excluded_shared_variant_without_review_level_size"
            retained["exclusion_reason"] = (
                "Walmart syndicates this review family across 6 oz and 14 oz pages; "
                "the retained record lacks a review-level size field."
            )
        rows.append(retained)

    snapshot = next(
        row for row in cache["snapshots"]
        if row["product_id"] == product["id"]
    )
    snapshot = dict(snapshot)
    if item_id == "38227608":
        snapshot.update({
            "captured_written_reviews": 0,
            "capture_status": "complete_rating_distribution_shared_variant_text_excluded",
            "snapshot_scope": "shared_variant_family",
            "related_product_ids": ["soules_beef_fajitas_14", "soules_fajita_steak_6"],
            "quality_note": "Unresolved 6 oz/14 oz written text is excluded from product-level metrics.",
        })
    else:
        snapshot.update({
            "capture_status": "bounded_public_text_sample_plus_complete_rating_distribution",
            "snapshot_scope": "listed_sku_page",
            "quality_note": "Live refresh was blocked; the last verified public-page sample is retained.",
        })
    return rows, snapshot


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


def build_coverage(products, snapshots, errors, reviews):
    snapshot_keys = {(row["product_id"], row["source"]) for row in snapshots}
    review_keys = {(row["product_id"], row["source"]) for row in reviews}
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
            evidence_source = product["brand"] if source == "Brand" else source
            has_snapshot = (product["id"], evidence_source) in snapshot_keys
            has_reviews = (product["id"], evidence_source) in review_keys
            if page_url:
                if source == "Costco" and product["pack_oz"] <= 20:
                    match_type = "club_pack_variant"
                else:
                    match_type = "exact_listed_sku"
                status = "review_evidence" if (has_snapshot or has_reviews) else "listing_only"
            elif search_url:
                match_type = "search_only"
                status = "exact_page_not_confirmed"
                page_url = search_url
            elif (product["id"], source) in RELATED_VARIANTS:
                related = RELATED_VARIANTS[(product["id"], source)]
                match_type = "different_pack_size"
                status = "related_variant_excluded"
                page_url = related["url"]
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
                "note": errors.get((product["id"], source)) or (RELATED_VARIANTS.get((product["id"], source)) or {}).get("note"),
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
            rows, snapshot = collect_walmart(products[product_id], item_id, products)
            all_reviews.extend(rows)
            snapshots.append(snapshot)
            print(product_id, "Walmart", len(rows), "reviews")
        except Exception as exc:
            try:
                rows, snapshot = cached_walmart_fallback(products[product_id], item_id, products)
                all_reviews.extend(rows)
                snapshots.append(snapshot)
                errors[(product_id, "Walmart")] = "Live refresh blocked; last verified bounded public sample retained."
                print(product_id, "Walmart FALLBACK", len(rows), "reviews", type(exc).__name__)
            except Exception as fallback_exc:
                errors[(product_id, "Walmart")] = f"Collection error: {type(exc).__name__}"
                print(product_id, "Walmart ERROR", exc, "FALLBACK ERROR", fallback_exc)
        time.sleep(1)

    for product_id, (average_rating, rating_count) in KROGER_RATING_CONTEXT.items():
        product = products[product_id]
        snapshots.append({
            "product_id": product_id,
            "product": product["name"],
            "brand": product["brand"],
            "source": "Kroger",
            "provider": "Kroger",
            "page_url": product["retailer_pages"]["kroger"],
            "average_rating": average_rating,
            "rating_count": rating_count,
            "written_review_count": None,
            "distribution": {},
            "captured_written_reviews": 0,
            "capture_status": "rating_total_only_public_text_payload_unavailable",
            "as_of": END.isoformat(),
        })

    deduped = deduplicate(all_reviews)
    coverage = build_coverage(list(products.values()), snapshots, errors, deduped)

    OUT_REVIEWS.write_text(json.dumps(deduped, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_SNAPSHOTS.write_text(json.dumps({
        "as_of": END.isoformat(),
        "method_note": "Hormel histories are complete public first-party feeds. Walmart is paginated only when the public interface permits; otherwise the last verified bounded page sample is retained. Shared Soules text without review-level size is excluded. Kroger totals remain rating-only context because reproducible public review text was unavailable.",
        "snapshots": snapshots,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_AUDIT.write_text(json.dumps({
        "as_of": END.isoformat(),
        "sources_audited": ["Brand", "Target", "Amazon", "Kroger", "Walmart", "Costco"],
        "rows": coverage,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("raw", len(all_reviews), "deduplicated", len(deduped), "snapshots", len(snapshots))
    print("date range", min((r["date"] for r in deduped), default=None), max((r["date"] for r in deduped), default=None))


if __name__ == "__main__":
    main()
