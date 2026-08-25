"""Capture official catalog identity for the 13 Kevin's stir-fry products."""

from __future__ import annotations

import json
import urllib.request
from datetime import date
from pathlib import Path

from collect_stir_fry_reviews import PRODUCTS


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "stir_fry_product_registry.json"
AS_OF = date(2026, 8, 25)
BASE_URL = "https://www.kevinsnaturalfoods.com/products/"


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; KNFReviewResearch/1.0)",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    rows = []
    for product_id, config in PRODUCTS.items():
        product_url = BASE_URL + config["handle"]
        payload = fetch_json(product_url + ".js")
        variants = []
        for variant in payload.get("variants", []):
            variants.append(
                {
                    "variant_id": str(variant.get("id")),
                    "title": variant.get("title"),
                    "sku": variant.get("sku"),
                    "barcode": variant.get("barcode"),
                    "available": bool(variant.get("available")),
                    "weight_grams": variant.get("grams"),
                }
            )
        row = {
            "product_id": product_id,
            "product": config["name"],
            "cohort": config["channel"],
            "servings": config["servings"],
            "handle": config["handle"],
            "official_url": product_url,
            "shopify_product_id": str(payload.get("id")),
            "vendor": payload.get("vendor"),
            "product_type": payload.get("type"),
            "tags": payload.get("tags") or [],
            "variants": variants,
        }
        rows.append(row)
        print(product_id, [variant.get("barcode") for variant in variants])

    OUTPUT.write_text(
        json.dumps(
            {
                "as_of": AS_OF.isoformat(),
                "source": "Kevin's Natural Foods official Shopify product catalog",
                "scope_note": "Exact official identities for the 13 products listed in the Stir-Fry Entrées collection section.",
                "products": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Wrote", OUTPUT)


if __name__ == "__main__":
    main()
