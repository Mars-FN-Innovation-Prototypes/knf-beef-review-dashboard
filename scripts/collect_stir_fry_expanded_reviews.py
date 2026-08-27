"""Create the audited Thrive Market and Meijer stir-fry review archive.

Thrive exposes a public product-review endpoint used by its own product pages.
The endpoint is collected at a page size large enough to include the complete
written history and then validated against the response totals.  The three
Meijer-origin reviews are transcribed from the exact Instacart-hosted Meijer
listing; their dates, ratings, titles, and text were visually verified.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "stir_fry_expanded_reviews_2026-08-27.json"

THRIVE_PRODUCTS = [
    {
        "product_id": "beef_broccoli_kit",
        "product": "Beef & Broccoli Stir-Fry Kit",
        "cohort": "grocery",
        "thrive_product_id": 35385,
        "sku": "810264028111",
        "page_url": "https://thrivemarket.com/p/kevins-natural-foods-beef-and-broccoli-stir-fry-kit",
        "raw_file": ".tmp-thrive-reviews.json",
    },
    {
        "product_id": "teriyaki_chicken_kit",
        "product": "Teriyaki-Style Chicken Stir-Fry Kit",
        "cohort": "grocery",
        "thrive_product_id": 35379,
        "sku": "810264028135",
        "page_url": "https://thrivemarket.com/p/kevins-natural-foods-teriyaki-style-chicken-stir-fry-kit",
        "raw_file": ".tmp-thrive-teriyaki.json",
    },
    {
        "product_id": "chicken_fajitas_kit",
        "product": "Chicken Fajitas Skillet Meal Kit",
        "cohort": "grocery",
        "thrive_product_id": 35388,
        "sku": "810264028180",
        "page_url": "https://thrivemarket.com/p/kevins-natural-foods-chicken-fajitas-skillet-meal-kit",
        "raw_file": ".tmp-thrive-fajitas.json",
    },
]

MEIJER_URL = (
    "https://www.instacart.com/products/64414811-"
    "kevins-natural-foods-honey-garlic-chicken-stirfry?retailer_id=1840"
)

MEIJER_REVIEWS = [
    {
        "date": "2026-03-16",
        "rating": 5,
        "title": "Better than I can make myself",
        "text": (
            "While this Honey Garlic Chicken Stir Fry meal kit is relatively expensive, and I think it's a stretch "
            "that it is supposed to be 2.5 servings, I think the taste and ease of preparation make it worth "
            "purchasing. The packet of chicken seems on the small side, but you get lots of beans, and I think they "
            "taste fresh and good. The amount of sauce you get is ample, and I would describe the taste as slightly "
            "salty and spicy with some sweetness added in. For someone who lives alone and isn't the greatest cook, "
            "I appreciate that this meal stays fresh for a fairly long time in the fridge, and when I don't feel like "
            "fussing with a sauce and/or choosing a separate vegetable, I can always count on having something "
            "delicious for dinner with this kit."
        ),
        "provider_review_id": "meijer-2026-03-16-better-than-i-can-make-myself",
    },
    {
        "date": "2026-01-23",
        "rating": 3,
        "title": "Half the meat as others",
        "text": (
            "The taste is great, but because you get vegetables, there’s only half the amount of chicken for the "
            "same price as the other meals. Not cost effective."
        ),
        "provider_review_id": "meijer-2026-01-23-half-the-meat-as-others",
    },
    {
        "date": "2026-01-13",
        "rating": 2,
        "title": "Nana",
        "text": (
            "Disappointed with this product. Expected more honey garlic flavor. No hint of orange either. Not worth "
            "the 11.00 price either for the small amount of ingredients in package. I added white rice (not included). "
            "I gave an extra point for quick preparation. Next time I will just get a rotisserie chicken at the deli "
            "or the Meijer Fresh chicken strips located in deli too. A bag of frozen green beans and Korean BBQ or "
            "orange glaze would provide a more complete meal."
        ),
        "provider_review_id": "meijer-2026-01-13-nana",
    },
]


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def thrive_payload(product: dict, source_dir: Path) -> dict:
    raw_path = source_dir / product["raw_file"]
    if raw_path.exists():
        return json.loads(raw_path.read_text(encoding="utf-8"))
    endpoint = (
        f"https://thrivemarket.com/api/v1/product/{product['thrive_product_id']}/reviews/"
        "?cur_page=1&page_size=100&sort=1&ratings_filter=0"
    )
    return fetch_json(endpoint)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=ROOT)
    args = parser.parse_args()

    reviews = []
    snapshots = []
    coverage = []

    for product in THRIVE_PRODUCTS:
        payload = thrive_payload(product, args.source_dir)
        source_reviews = payload.get("reviews") or []
        expected = int(payload.get("review_count") or 0)
        if len(source_reviews) != expected:
            raise ValueError(
                f"Thrive {product['product']} returned {len(source_reviews)} rows; expected {expected}."
            )

        for row in source_reviews:
            reviews.append({
                "product_id": product["product_id"],
                "product": product["product"],
                "cohort": product["cohort"],
                "source": "Thrive Market",
                "date": datetime.fromisoformat(row["created_at"]).date().isoformat(),
                "rating": int(row["value"]),
                "title": row.get("title") or "",
                "text": row.get("detail") or "",
                "capture": "complete public written review history",
                "provider": "Thrive Market public product-review endpoint",
                "provider_review_id": str(row["id"]),
                "verified_buyer": bool(row.get("is_verified_buyer")),
                "transparency_badges": ["thrive_cash_earned"] if row.get("thrive_cash_earned") else [],
                "source_url": product["page_url"],
                "metric_eligible": True,
            })

        snapshots.append({
            "product_id": product["product_id"],
            "product": product["product"],
            "cohort": product["cohort"],
            "source": "Thrive Market",
            "page_url": product["page_url"],
            "sku": product["sku"],
            "average_rating": float(payload["average_rating"]),
            "rating_count": int(payload["rating_count"]),
            "written_review_count": expected,
            "captured_written_reviews": len(source_reviews),
            "distribution": {str(star): int(payload["rating_histogram"].get(str(star), 0)) for star in range(1, 6)},
            "distribution_scope": "written_reviews",
            "status": "review_history_complete",
            "captured_at": "2026-08-27",
        })
        coverage.append({
            "product_id": product["product_id"],
            "product": product["product"],
            "cohort": product["cohort"],
            "source": "Thrive Market",
            "match_type": "exact_sku",
            "status": "review_history_complete",
            "page_url": product["page_url"],
            "note": f"Exact UPC {product['sku']}; complete public written review history captured.",
        })

    for row in MEIJER_REVIEWS:
        reviews.append({
            "product_id": "honey_garlic_chicken_kit",
            "product": "Honey Garlic Chicken Stir-Fry Kit",
            "cohort": "grocery",
            "source": "Meijer",
            **row,
            "capture": "complete native Meijer-origin written reviews on exact listing",
            "provider": "Instacart retailer-attributed review surface",
            "verified_buyer": None,
            "transparency_badges": [],
            "source_url": MEIJER_URL,
            "metric_eligible": True,
        })

    snapshots.append({
        "product_id": "honey_garlic_chicken_kit",
        "product": "Honey Garlic Chicken Stir-Fry Kit",
        "cohort": "grocery",
        "source": "Meijer",
        "page_url": MEIJER_URL,
        "sku": "810264028159",
        "average_rating": 3.8,
        "rating_count": 11,
        "written_review_count": 11,
        "captured_written_reviews": 3,
        "native_source_written_count": 3,
        "distribution": {"1": 1, "2": 2, "3": 2, "4": 0, "5": 6},
        "distribution_scope": "listing_total_including_syndicated_reviews",
        "status": "review_history_complete",
        "captured_at": "2026-08-27",
        "note": "Listing total includes syndicated Kevin's reviews; three native Meijer-origin rows are incremental.",
    })
    coverage.append({
        "product_id": "honey_garlic_chicken_kit",
        "product": "Honey Garlic Chicken Stir-Fry Kit",
        "cohort": "grocery",
        "source": "Meijer",
        "match_type": "exact_sku",
        "status": "review_history_complete",
        "page_url": MEIJER_URL,
        "note": "Exact 16 oz product; all three retailer-native Meijer reviews captured separately from syndicated rows.",
    })

    output = {
        "as_of": "2026-08-27",
        "scope_note": "Incremental exact-SKU review sources discovered during the 13-product deep dive.",
        "collection_method": (
            "Complete public Thrive review endpoint histories plus visually verified native Meijer-origin reviews "
            "from the exact Instacart-hosted Meijer listing."
        ),
        "reviews": reviews,
        "snapshots": snapshots,
        "coverage": coverage,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(reviews)} rows and {len(snapshots)} snapshots to {OUTPUT}")


if __name__ == "__main__":
    main()
