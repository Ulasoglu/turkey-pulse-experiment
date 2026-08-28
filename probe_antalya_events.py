from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

URL = "https://www.antalya.bel.tr/tr/etkinlikler"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.1 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    print("FETCH", url, "->", r.status_code, r.headers.get("content-type"), len(r.content), "bytes")
    r.raise_for_status()
    return r


def endpoint_hints(body, base):
    hints = set()
    patterns = [
        r"https?://[^\"'\s<>]+",
        r"/[A-Za-z0-9_./?=&%{}:-]*(?:api|event|etkinlik|content|service|ajax|list|search|get|page)[A-Za-z0-9_./?=&%{}:-]*",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, body, re.I):
            hints.add(urljoin(base, match))
    return sorted(hints)


def print_interesting_lines(label, body):
    tokens = [
        "{{item.", "custominclude", "startdate", "enddate", "refetkinliktipi",
        "axios", "fetch(", "$.ajax", "$http", "xmlhttprequest", "api/", "/api",
        "etkinlik", "event", "getcontent", "getlist", "contentlist", "search"
    ]
    seen = set()
    count = 0
    for raw in body.splitlines():
        compact = " ".join(raw.split())
        low = compact.casefold()
        if any(token.casefold() in low for token in tokens):
            if compact and compact not in seen:
                seen.add(compact)
                print(label, compact[:900])
                count += 1
                if count >= 80:
                    break
    print(label, "COUNT", count)


def inspect_script(url):
    try:
        r = get(url)
    except Exception as exc:
        print("SCRIPT ERROR", url, exc)
        return
    compact = " ".join(r.text.split())
    print("SCRIPT", url)
    for token in ["etkinlik", "StartDate", "custominclude", "baslik", "refetkinliktipi", "$http", "axios", "fetch(", "$.ajax", "api/"]:
        if token.casefold() in compact.casefold():
            print("  HAS", token)
    hints = endpoint_hints(r.text, r.url)
    print("  ENDPOINT HINTS", len(hints))
    for hint in hints[:100]:
        print("  HINT", hint)
    print_interesting_lines("  SCRIPT_LINE", r.text)


def main():
    print("=== ANTALYA EVENTS DEEP PROBE ===")
    r = get(URL)
    soup = BeautifulSoup(r.text, "html.parser")

    print("TITLE", soup.title.get_text(" ", strip=True) if soup.title else "")
    print("PAGE HAS TEMPLATE TOKENS", "{{item." in r.text)
    print_interesting_lines("PAGE_LINE", r.text)

    inline = [s.get_text("\n", strip=False) for s in soup.find_all("script") if not s.get("src")]
    print("INLINE SCRIPTS", len(inline))
    for idx, body in enumerate(inline):
        low = body.casefold()
        if any(token in low for token in ["etkinlik", "custominclude", "startdate", "axios", "fetch(", "$.ajax", "$http", "api/"]):
            print("INLINE_SCRIPT", idx, "bytes", len(body.encode("utf-8")))
            print_interesting_lines("  INLINE_LINE", body)
            hints = endpoint_hints(body, r.url)
            for hint in hints[:100]:
                print("  INLINE_HINT", hint)

    scripts = []
    seen = set()
    for script in soup.find_all("script", src=True):
        absolute = urljoin(r.url, script["src"])
        if absolute not in seen:
            seen.add(absolute)
            scripts.append(absolute)
    print("EXTERNAL SCRIPTS", len(scripts))
    for script in scripts:
        print("SCRIPT_URL", script)

    # Inspect first-party Antalya scripts even when they are hosted on library/mcmsmedia subdomains.
    candidates = []
    for s in scripts:
        host = urlparse(s).netloc.casefold()
        low = s.casefold()
        if host.endswith("antalya.bel.tr") and any(x in low for x in ["site", "panel", "app", "main", "bundle", "script", "js"]):
            candidates.append(s)

    print("FIRST_PARTY SCRIPT CANDIDATES", len(candidates))
    for script in candidates[-20:]:
        inspect_script(script)


if __name__ == "__main__":
    main()
