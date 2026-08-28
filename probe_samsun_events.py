from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URLS = [
    "https://samsun.bel.tr/guncel/etkinlikler",
    "https://samsun.bel.tr/kultur-sanat",
]
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.0 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def compact(value, limit=500):
    return " ".join(str(value or "").split())[:limit]


def main():
    print("=== SAMSUN EVENTS SOURCE PROBE ===", flush=True)
    for url in URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=(6, 12))
            print("FETCH", url, "->", r.status_code, r.headers.get("content-type"), len(r.content), "bytes", flush=True)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(" ", strip=True)
            print("DATE TOKENS", re.findall(r"\b\d{1,2}\s+(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+20\d{2}\b", text, re.I)[:20])
            print("TIME TOKENS", re.findall(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", text)[:20])

            candidates = []
            for tag in soup.find_all(["a", "article", "div", "li"]):
                value = compact(tag.get_text(" ", strip=True), 700)
                if not value or len(value) < 12:
                    continue
                if not (re.search(r"\b20\d{2}\b", value) or re.search(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", value)):
                    continue
                href = tag.get("href") if tag.name == "a" else None
                if href:
                    href = urljoin(url, href)
                item = (value, href)
                if item not in candidates:
                    candidates.append(item)
            print("CANDIDATES", len(candidates))
            for value, href in candidates[:30]:
                print("ITEM", value, "URL=", href)

            links = []
            for a in soup.find_all("a", href=True):
                href = urljoin(url, a.get("href"))
                label = compact(a.get_text(" ", strip=True), 250)
                low = href.casefold()
                if "etkinlik" in low and href not in links:
                    links.append(href)
                    print("EVENT LINK", label, href)
            print("EVENT LINKS", len(links))

            for script in soup.find_all("script", src=True):
                src = urljoin(url, script.get("src"))
                if "samsun.bel.tr" in src:
                    print("SCRIPT", src)
        except Exception as exc:
            print("ERROR", url, type(exc).__name__, exc, flush=True)


if __name__ == "__main__":
    main()
