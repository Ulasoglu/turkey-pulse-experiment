from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL = "https://www.corum.bel.tr/etkinlikler"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/0.9 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def clean(value):
    return " ".join(str(value or "").split())


def main():
    response = requests.get(URL, headers=HEADERS, timeout=(6, 12))
    print("HTTP", response.status_code)
    print("CONTENT-TYPE", response.headers.get("content-type"))
    print("BYTES", len(response.content))
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = clean(soup.get_text(" ", strip=True))
    print("PAGE TEXT", text[:5000])

    links = []
    seen = set()
    for anchor in soup.select('a[href*="/etkinlikler/"]'):
        href = anchor.get("href")
        if not href:
            continue
        absolute = urljoin(response.url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append((clean(anchor.get_text(" ", strip=True)), absolute))

    print("EVENT LINKS", len(links))
    for title, url in links[:20]:
        print("LINK", title[:180], "=>", url)

    dates = re.findall(r"\b\d{1,2}\s+(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+20\d{2}\b", text, flags=re.I)
    print("DATES", dates[:30])

    if links:
        detail_url = links[0][1]
        detail = requests.get(detail_url, headers=HEADERS, timeout=(6, 12))
        print("DETAIL HTTP", detail.status_code, detail_url)
        detail.raise_for_status()
        ds = BeautifulSoup(detail.text, "html.parser")
        detail_text = clean(ds.get_text(" ", strip=True))
        for label in ("Başlangıç Tarihi", "Bitiş Tarihi", "Etkinlik Yeri", "Etkinlik Türü", "Bilet Fiyatı", "Katılım Koşulu", "Düzenleyen"):
            match = re.search(re.escape(label) + r"\s+(.{0,220}?)(?=Başlangıç Tarihi|Bitiş Tarihi|Etkinlik Yeri|Etkinlik Türü|Bilet Fiyatı|Katılım Koşulu|Düzenleyen|İlgili Müdürlük|$)", detail_text, flags=re.I)
            print("FIELD", label, "=>", clean(match.group(1)) if match else None)
        print("DETAIL TEXT", detail_text[:3000])


if __name__ == "__main__":
    main()
