from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

URL = "https://www.antalya.bel.tr/tr/etkinlikler"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.0 (+non-commercial feasibility probe)",
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
        r"/[A-Za-z0-9_./?=&%{}:-]*(?:api|event|etkinlik|content|service|ajax|list|search)[A-Za-z0-9_./?=&%{}:-]*",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, body, re.I):
            hints.add(urljoin(base, match))
    return sorted(hints)


def inspect_script(url):
    try:
        r = get(url)
    except Exception as exc:
        print("SCRIPT ERROR", url, exc)
        return
    compact = " ".join(r.text.split())
    print("SCRIPT", url)
    for token in ["etkinlik", "StartDate", "baslik", "refetkinliktipi", "$http", "axios", "fetch(", "api/"]:
        if token.casefold() in compact.casefold():
            print("  HAS", token)
    hints = endpoint_hints(r.text, r.url)
    print("  ENDPOINT HINTS", len(hints))
    for hint in hints[:80]:
        print("  HINT", hint)


def main():
    print("=== ANTALYA EVENTS PROBE ===")
    r = get(URL)
    soup = BeautifulSoup(r.text, "html.parser")

    print("TITLE", soup.title.get_text(" ", strip=True) if soup.title else "")
    print("PAGE HAS TEMPLATE TOKENS", "{{item." in r.text)

    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        absolute = urljoin(r.url, a["href"])
        if urlparse(absolute).netloc == urlparse(r.url).netloc and any(x in absolute.casefold() for x in ["etkinlik", "event"]):
            if absolute not in seen:
                seen.add(absolute); links.append(absolute)
    print("EVENT-LIKE LINKS", len(links))
    for link in links[:50]: print("EVENT_LINK", link)

    hints = endpoint_hints(r.text, r.url)
    print("PAGE ENDPOINT HINTS", len(hints))
    for hint in hints[:100]: print("HINT", hint)

    scripts=[]
    for script in soup.find_all("script", src=True):
        absolute=urljoin(r.url,script["src"])
        if urlparse(absolute).netloc == urlparse(r.url).netloc:
            scripts.append(absolute)
    print("LOCAL SCRIPTS", len(scripts))
    for script in scripts: print("SCRIPT_URL", script)

    # Inspect the most likely application scripts first. The page renders Angular-like
    # {{item.*}} placeholders server-side, so a backing endpoint may be referenced here.
    candidates=[s for s in scripts if any(x in s.casefold() for x in ["app", "main", "site", "custom", "bundle", "script"])]
    for script in (candidates or scripts)[-12:]:
        inspect_script(script)


if __name__ == "__main__":
    main()
