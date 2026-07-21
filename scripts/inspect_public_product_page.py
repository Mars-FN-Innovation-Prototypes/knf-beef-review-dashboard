"""Small read-only helper for inspecting public product-page data contracts."""

from __future__ import annotations

import json
import re
import sys

from html.parser import HTMLParser
from urllib.request import Request, urlopen


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


def walk(obj, path=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            next_path = f"{path}.{key}" if path else key
            if re.search(r"review|rating|productid|usitemid|upc", key, re.I):
                preview = str(value)
                print(next_path, preview[:400].replace("\n", " "))
            walk(value, next_path)
    elif isinstance(obj, list):
        for index, value in enumerate(obj[:20]):
            walk(value, f"{path}[{index}]")


def main(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=45) as response:
        raw = response.read()
        final_url = response.geturl()
        status = response.status
    print("status", status, "bytes", len(raw), "url", final_url)
    parser = ScriptParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    print("scripts", [(a.get("id"), a.get("type"), len(t)) for a, t in parser.scripts])
    for attrs, text in parser.scripts:
        if not text.strip().startswith(("{", "[")):
            continue
        try:
            data = json.loads(text)
        except Exception:
            continue
        print("JSON", attrs.get("id"), attrs.get("type"), len(text))
        walk(data)


if __name__ == "__main__":
    main(sys.argv[1])
