"""Collect review evidence and coverage for the approved stir-fry retailers.

Only public product pages are used.  Listing confirmation and review evidence
are deliberately separate so an exact page without a review surface is not
reported as zero consumer sentiment.
"""

from __future__ import annotations

import base64
import gzip
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
KROGER_ARCHIVE = DATA / "stir_fry_kroger_reviews_2026-08-25.json"
TARGET_ARCHIVE = DATA / "stir_fry_target_reviews_2026-08-25.json.gz.b64"
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

# Correct a harmless slug typo before requests are made; Kroger keys identity
# from the trailing product identifier, while keeping a readable canonical URL.
EXACT_LISTINGS = {
    ("teriyaki_chicken_kit", "Publix"): "https://www.publix.com/pd/kevins-natural-foods-teriyaki-style-chicken-stir-fry-kit/RIO-PCI-634263",
    ("teriyaki_chicken_kit", "Food Lion"): "https://foodlion.com/groceries/meat/prepared-meat/prepared-chicken/kevins-natural-foods-teriyaki-style-chicken-stir-fry-kit-16-oz-pkg.html",
    ("beef_broccoli_costco", "Costco"): "https://sameday.costco.com/store/costco/products/32881613-kevin-s-natural-foods-beef-broccoli-stir-fry-32-oz",
    ("sichuan_chicken_costco", "Costco"): "https://sameday.costco.com/store/costco/products/28547551-kevin-s-natural-foods-sichuan-style-chicken-with-green-beans-32-oz",
}

RETAILERS = ["Costco", "Target", "Kroger", "Publix", "Albertsons", "Food Lion", "Amazon"]

SEARCH_SCOPE_NOTE = (
    "Exact scoped names, known UPCs, pack sizes, official product assignments, retailer search, "
    "and public web indexing were checked as of 2026-08-25."
)

AMAZON_EXCLUDED_CANDIDATES = [
    {
        "candidate": "Kevin's Natural Foods Chicken Orange Sous Vide, 16 Ounce",
        "reason": "Different Heat & Eat product architecture; not the Costco-only Orange Chicken Stir-Fry item.",
    },
    {
        "candidate": "Kevin's Natural Foods simmer sauces and sauce bundles",
        "reason": "Sauce-only products; none is one of the 13 scoped complete stir-fry items.",
    },
    {
        "candidate": "Taylor Farms and other third-party stir-fry kits",
        "reason": "Different brand and therefore outside the exact-SKU scope.",
    },
]


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

    statistics = node["statistics"]
    rating = statistics["rating"]
    written_total = int(statistics["review_count"])
    archive = json.loads(gzip.decompress(base64.b64decode(TARGET_ARCHIVE.read_text(encoding="ascii"))).decode("utf-8"))
    reviews = [row for row in archive["reviews"] if row["product_id"] == product_id]
    if len(reviews) != written_total:
        raise RuntimeError(
            f"Target archive has {len(reviews)} written reviews but the current page reports {written_total}; refresh required"
        )

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
        "written_review_count": written_total,
        "distribution": distribution,
        "captured_written_reviews": len(reviews),
        "capture_status": "complete_public_written_review_history",
        "as_of": AS_OF.isoformat(),
    }
    return reviews, snapshot


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
                if snapshot.get("written_review_count"):
                    status = "review_history_complete"
                elif snapshot.get("rating_count"):
                    status = "rating_evidence"
                else:
                    status = "listing_no_public_reviews"
                page_url = snapshot["page_url"]
                match_type = "exact_sku"
            elif exact_url:
                status = "listing_no_public_reviews"
                page_url = exact_url
                match_type = "exact_sku"
            elif intended_channel and retailer == "Costco":
                status = "official_costco_sku_page_not_indexed"
                page_url = "https://www.kevinsnaturalfoods.com/products/" + product["handle"]
                match_type = "official_sku_channel_assignment"
            elif intended_channel or retailer == "Costco":
                status = "not_applicable"
                page_url = None
                match_type = "not_applicable"
            else:
                status = "searched_no_exact_page"
                page_url = None
                match_type = "searched_not_located"
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
                    "search_scope": SEARCH_SCOPE_NOTE if status == "searched_no_exact_page" else None,
                    "confidence": "exact" if match_type == "exact_sku" else "governed_scope",
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
            print(product_id, "Target", len(rows), "written /", snapshot["rating_count"], "ratings")
        except Exception as exc:
            errors.append({"product_id": product_id, "source": "Target", "error": f"{type(exc).__name__}: {exc}"})
            print(product_id, "Target ERROR", exc)

    kroger = json.loads(KROGER_ARCHIVE.read_text(encoding="utf-8"))
    if {row["product_id"] for row in kroger["snapshots"]} != set(KROGER_PRODUCTS):
        raise RuntimeError("Kroger archive product set does not match the governed exact-page registry")
    if any(row["page_url"] != KROGER_PRODUCTS[row["product_id"]] for row in kroger["snapshots"]):
        raise RuntimeError("Kroger archive URL does not match the governed exact-page registry")
    reviews.extend(kroger["reviews"])
    snapshots.extend(kroger["snapshots"])
    print("Kroger", len(kroger["reviews"]), "public review cards /", len(kroger["snapshots"]), "exact pages")

    payload = {
        "as_of": AS_OF.isoformat(),
        "analysis_start": START.isoformat(),
        "method_note": (
            "Public retailer evidence only. Target and Kroger exact pages provide complete visible written-review histories and "
            "current rating distributions. Costco, Publix, and Food Lion exact pages are retained as listing evidence when no "
            "public review surface is present. Albertsons and Amazon were searched for the exact scoped grocery SKUs; no exact "
            "page was confirmed. Costco-only items are not treated as applicable to the other six retailers."
        ),
        "deduplication_note": "Cross-posted written records are deduplicated during analysis using exact normalized product, rating, and body text.",
        "amazon_assessment": {
            "status": "searched_no_exact_scoped_sku",
            "scope": "Six grocery stir-fry kits; seven stakeholder-designated Costco-only products are not applicable.",
            "search_note": SEARCH_SCOPE_NOTE,
            "excluded_candidates": AMAZON_EXCLUDED_CANDIDATES,
            "reference": "https://www.amazon.com/s?k=Kevin%27s+Natural+Foods+stir+fry+kit",
        },
        "snapshots": snapshots,
        "reviews": sorted(reviews, key=lambda row: (row.get("date") or "", row["product_id"]), reverse=True),
        "coverage": coverage_rows(snapshots, errors),
        "errors": errors,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote", OUTPUT, "reviews", len(reviews), "snapshots", len(snapshots), "errors", len(errors))


if __name__ == "__main__":
    main()
