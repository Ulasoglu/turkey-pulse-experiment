from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL = "https://www.konya.bel.tr/etkinlik"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.0 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def clean(value: str) -> str:
    return " ".join(value.split())


def main():
    print("=== KONYA EVENTS SOURCE PROBE ===", flush=True)
    r = requests.get(URL, headers=HEADERS, timeout=(6, 12))
    print("HTTP", r.status_code, r.headers.get("content-type"), len(r.content), "bytes", flush=True)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    text = clean(soup.get_text(" ", strip=True))
    print("PAGE TEXT", text[:2500], flush=True)

    candidates = []
    seen = set()
    for a in soup.find_all("a", href=True):
        label = clean(a.get_text(" ", strip=True))
        href = urljoin(URL, a["href"])
        haystack = (label + " " + href).casefold()
        if any(token in haystack for token in ["etkinlik", "tiyatro", "konser", "sergi", "sinema"]):
            key = (label, href)
            if key not in seen:
                seen.add(key)
                candidates.append(key)

    print("CANDIDATE LINKS", len(candidates), flush=True)
    for label, href in candidates[:40]:
        print("LINK", repr(label[:160]), href, flush=True)

    # Look for structured data or obvious API/AJAX hints without guessing endpoints.
    for script in soup.find_all("script"):
        body = script.string or script.get_text(" ", strip=False) or ""
        low = body.casefold()
        if any(token in low for token in ["etkinlik", "fetch(", "ajax", "api/", "application/ld+json"]):
            snippet = clean(body)
            if snippet:
                print("SCRIPT HINT", snippet[:2500], flush=True)

    dates = re.findall(r"\b\d{1,2}\s+(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+\d{4}\b", text, re.I)
    print("DATES", dates[:30], flush=True)


if __name__ == "__main__":
    main()
