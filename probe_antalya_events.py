from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

URL = "https://www.antalya.bel.tr/tr/etkinlikler"
COLLECTION_ID = "6c75f6c0-fc5d-4d4f-9ae8-e96447fe893b"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.2 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    print("FETCH", url, "->", r.status_code, r.headers.get("content-type"), len(r.content), "bytes")
    r.raise_for_status()
    return r


def compact(value, limit=1400):
    return " ".join(value.split())[:limit]


def endpoint_hints(body, base):
    hints = set()
    patterns = [
        r"https?://[^\"'\s<>]+",
        r"/[A-Za-z0-9_./?=&%{}:-]*(?:api|collection|content|event|etkinlik|service|ajax|list|search|get|page)[A-Za-z0-9_./?=&%{}:-]*",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, body, re.I):
            hints.add(urljoin(base, match))
    return sorted(hints)


def print_matches(label, body, tokens, max_count=120):
    seen = set()
    count = 0
    for raw in body.splitlines():
        line = compact(raw)
        low = line.casefold()
        if line and any(token.casefold() in low for token in tokens) and line not in seen:
            seen.add(line)
            print(label, line)
            count += 1
            if count >= max_count:
                break
    print(label, "COUNT", count)


def inspect_script(url):
    try:
        r = get(url)
    except Exception as exc:
        print("SCRIPT ERROR", url, exc)
        return

    body = r.text
    low = body.casefold()
    interesting = [
        COLLECTION_ID.casefold(), "data-collection", "collectionid", "collection-id",
        "custominclude", "startdate", "finisbroadcastertime", "pagesize", "page-size",
        "axios", "fetch(", "$.ajax", "$http", "xmlhttprequest", "/api", "api/",
    ]
    if not any(token in low for token in interesting):
        return

    print("=== INTERESTING SCRIPT", url, "===")
    for token in interesting:
        if token in low:
            print("HAS", token)
    print_matches("SCRIPT_LINE", body, interesting)
    for hint in endpoint_hints(body, r.url)[:150]:
        print("SCRIPT_HINT", hint)


def main():
    print("=== ANTALYA COLLECTION LOADER PROBE ===")
    print("TARGET COLLECTION", COLLECTION_ID)
    r = get(URL)
    soup = BeautifulSoup(r.text, "html.parser")

    tokens = [
        COLLECTION_ID, "data-collection", "collectionid", "collection-id", "custominclude",
        "StartDate", "finisBroadcasterTime", "pagesize", "page-size", "sort", "filter",
    ]
    print_matches("PAGE_COLLECTION", r.text, tokens)

    # Print the actual DOM nodes around collection-related attributes/classes.
    dom_count = 0
    for tag in soup.find_all(True):
        attrs = " ".join(f"{k}={v}" for k, v in tag.attrs.items())
        text = tag.get_text(" ", strip=True)
        hay = f"{tag.name} {attrs} {text}".casefold()
        if COLLECTION_ID.casefold() in hay or "data-collection" in hay or "custominclude" in hay:
            print("COLLECTION_DOM", compact(str(tag), 2200))
            dom_count += 1
            if dom_count >= 30:
                break
    print("COLLECTION_DOM COUNT", dom_count)

    # Inline scripts may initialize the generic loader with the collection metadata.
    for idx, script in enumerate(soup.find_all("script")):
        if script.get("src"):
            continue
        body = script.get_text("\n", strip=False)
        low = body.casefold()
        if any(t.casefold() in low for t in tokens + ["axios", "fetch(", "$.ajax", "$http"]):
            print("=== INLINE", idx, "===")
            print_matches("INLINE_LINE", body, tokens + ["axios", "fetch(", "$.ajax", "$http", "/api", "api/"])
            for hint in endpoint_hints(body, r.url)[:100]:
                print("INLINE_HINT", hint)

    scripts = []
    seen = set()
    for script in soup.find_all("script", src=True):
        absolute = urljoin(r.url, script["src"])
        if absolute not in seen:
            seen.add(absolute)
            scripts.append(absolute)

    print("EXTERNAL SCRIPTS", len(scripts))
    for script in scripts:
        host = urlparse(script).netloc.casefold()
        if host.endswith("antalya.bel.tr"):
            inspect_script(script)


if __name__ == "__main__":
    main()
