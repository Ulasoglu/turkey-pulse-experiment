from __future__ import annotations

import ast
import re

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://www.antalya.bel.tr/tr/etkinlikler"
SITE_JS = "https://library.antalya.bel.tr/js/site.js?v=20260828"
PANEL_JS = "https://library.antalya.bel.tr/js/PanelJs.js?v=20260828"
COLLECTION_ID = "6c75f6c0-fc5d-4d4f-9ae8-e96447fe893b"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.3 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=(10, 20))
    print("FETCH", url, "->", r.status_code, r.headers.get("content-type"), len(r.content), "bytes")
    r.raise_for_status()
    return r


def compact(text, limit=1600):
    return " ".join(text.split())[:limit]


def quoted_strings(js):
    # Pull string literals out of obfuscated JS without executing it.
    out = []
    for match in re.finditer(r"(['\"])(.*?)(?<!\\)\1", js, re.S):
        raw = match.group(0)
        try:
            value = ast.literal_eval(raw)
        except Exception:
            value = match.group(2)
        if isinstance(value, str):
            out.append(value)
    return out


def show_interesting_strings(label, js):
    tokens = [
        "collection", "data-collection", "dbfind", "include", "projection",
        "getvue", "getdata", "getlist", "content", "dynamicform",
        "/tr/", "/api", "api/", "ajax", "vue", "page", "rowcount",
    ]
    seen = set()
    count = 0
    for value in quoted_strings(js):
        low = value.casefold()
        if any(token in low for token in tokens):
            value = compact(value, 800)
            if value and value not in seen:
                seen.add(value)
                print(label, value)
                count += 1
                if count >= 180:
                    break
    print(label, "COUNT", count)


def show_collection_node(html):
    soup = BeautifulSoup(html, "html.parser")
    node = soup.find(attrs={"data-collection": COLLECTION_ID})
    if not node:
        print("COLLECTION NODE NOT FOUND")
        return
    print("COLLECTION NODE FOUND")
    for key, value in node.attrs.items():
        print("ATTR", key, compact(str(value), 2400))


def main():
    print("=== ANTALYA TARGETED LOADER PROBE ===")
    page = get(PAGE_URL)
    show_collection_node(page.text)

    for url, label in [(SITE_JS, "SITE_STRING"), (PANEL_JS, "PANEL_STRING")]:
        try:
            r = get(url)
        except Exception as exc:
            print("SCRIPT ERROR", url, exc)
            continue
        print("---", label, "---")
        show_interesting_strings(label, r.text)

        # Also print small source windows around loader-related terms that survived obfuscation.
        low = r.text.casefold()
        for token in ["data-collection", "getvuecomboboxdata", "dynamicform", "dbfind", "collection"]:
            start = 0
            hits = 0
            while True:
                pos = low.find(token, start)
                if pos < 0 or hits >= 12:
                    break
                a = max(0, pos - 350)
                b = min(len(r.text), pos + 650)
                print("WINDOW", token, compact(r.text[a:b], 1200))
                hits += 1
                start = pos + len(token)
            print("WINDOW", token, "COUNT", hits)


if __name__ == "__main__":
    main()
