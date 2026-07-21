"""Resolve exact public Walmart item pages for the proposed competitor set."""

from __future__ import annotations

import json
import re
import sys
import time
from html.parser import HTMLParser
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


QUERIES = [
    "Hormel Slow Simmered Beef Roast Au Jus 15 oz",
    "Hormel Beef Tips and Gravy 15 oz",
    "Soules Kitchen Beef Fajitas 14 oz",
    "Soules Kitchen Fajita Steak 6 oz",
    "Sadler's Beef Brisket 32 oz",
    "Soules Angus Beef Fajitas 24 oz",
    "Jack Daniel's Thinly Sliced Beef Brisket 20 oz",
    "Brookwood Farms Sliced Beef Brisket 16 oz",
    "Del Real Barbacoa 15 oz",
    "Del Real Birria 16 oz",
    "Mama Mancini's Italian Style Jumbo Beef Meatballs 48 oz",
    "Ruprecht Braised Beef Pot Roast 32 oz",
    "Jack Daniel's Beef Brisket 15 oz",
    "Harris Ranch Homestyle Beef Pot Roast 16 oz",
]


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


def tokens(text):
    stop = {"and", "style", "beef", "oz", "the", "with"}
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in stop}


def fetch_next(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=45) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parser = NextDataParser()
    parser.feed(raw)
    return json.loads("".join(parser.parts))


def flatten_items(data):
    stacks = data["props"]["pageProps"]["initialData"]["searchResult"]["itemStacks"]
    seen = set()
    for stack in stacks:
        for item in stack.get("items", []):
            item_id = str(item.get("usItemId", ""))
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            yield item


def candidate(item, query):
    name = item.get("name") or item.get("title") or ""
    score = len(tokens(name) & tokens(query))
    query_size = re.search(r"(\d+)\s*oz", query.lower())
    if query_size and re.search(rf"\b{query_size.group(1)}\s*(?:fl\s*)?oz\b", name.lower()):
        score += 4
    return score


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else None
    if output_path:
        from pathlib import Path
        path = Path(output_path)
        results = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    else:
        path = None
        results = {}
    for query in QUERIES:
        if query in results:
            continue
        url = "https://www.walmart.com/search?q=" + quote_plus(query)
        data = None
        for attempt in range(3):
            try:
                data = fetch_next(url)
                break
            except Exception as exc:
                print(query, "attempt", attempt + 1, "failed:", exc, file=sys.stderr)
                time.sleep(4 + attempt * 3)
        if data is None:
            results[query] = []
            if path:
                path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            continue
        items = sorted(flatten_items(data), key=lambda item: candidate(item, query), reverse=True)[:5]
        results[query] = [
            {
                "score": candidate(item, query),
                "name": item.get("name") or item.get("title"),
                "us_item_id": str(item.get("usItemId")),
                "canonical_url": item.get("canonicalUrl") or item.get("productPageUrl"),
                "average_rating": item.get("averageRating") or (item.get("rating") or {}).get("averageRating"),
                "rating_count": (item.get("rating") or {}).get("numberOfReviews"),
                "upc": item.get("upc"),
            }
            for item in items
        ]
        print(query, results[query][0] if results[query] else "NO MATCH", file=sys.stderr)
        if path:
            path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        time.sleep(2)
    output = json.dumps(results, indent=2, ensure_ascii=False)
    if path:
        path.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
