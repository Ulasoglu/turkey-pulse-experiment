from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL = "https://kultursanat.ankara.bel.tr/"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/0.7 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def main():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    print("=== ANKARA EVENTS PROBE ===")
    print("HTTP:", r.status_code)
    print("FINAL URL:", r.url)
    print("CONTENT TYPE:", r.headers.get("content-type"))
    print("BYTES:", len(r.content))
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    event_links = []
    seen = set()
    for a in soup.select('a[href*="/event/"]'):
        href = a.get("href")
        if not href:
            continue
        absolute = urljoin(r.url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        title = " ".join(a.get_text(" ", strip=True).split())
        event_links.append((title, absolute))

    print("EVENT LINKS:", len(event_links))
    for title, link in event_links[:20]:
        print("EVENT", repr(title[:120]), link)

    text = " ".join(soup.get_text(" ", strip=True).split())
    dates = sorted(set(re.findall(r"\b\d{2}\.\d{2}\.20\d{2}\b", text)))
    print("DATE TOKENS:", len(dates), dates[:40])

    endpoint_hints = set()
    for script in soup.find_all("script"):
        src = script.get("src")
        if src:
            endpoint_hints.add(urljoin(r.url, src))
        body = script.string or script.get_text(" ", strip=True)
        for match in re.findall(r"https?://[^\"'\s<>]+|/[A-Za-z0-9_./?=&%-]*(?:api|event|etkinlik)[A-Za-z0-9_./?=&%-]*", body, re.I):
            endpoint_hints.add(urljoin(r.url, match))

    print("SCRIPT / ENDPOINT HINTS:", len(endpoint_hints))
    for hint in sorted(endpoint_hints)[:60]:
        print("HINT", hint)


if __name__ == "__main__":
    main()
