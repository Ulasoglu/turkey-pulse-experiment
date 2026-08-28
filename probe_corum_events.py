from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL = "https://www.corum.bel.tr/etkinlikler"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def clean(value):
    return " ".join(str(value or "").split())


def main():
    session = requests.Session()
    response = session.get(URL, headers=HEADERS, timeout=(6, 12), allow_redirects=True)
    print("HTTP", response.status_code)
    print("FINAL URL", response.url)
    print("SERVER", response.headers.get("server"))
    print("CONTENT-TYPE", response.headers.get("content-type"))
    print("BYTES", len(response.content))
    print("SET-COOKIE", bool(response.headers.get("set-cookie")))
    if response.status_code >= 400:
        print("BLOCK PAGE", clean(response.text)[:2500])
        print("CORUM BLOCKED - probe ends without failing main workflow")
        return

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
        detail_headers = dict(HEADERS)
        detail_headers["Referer"] = response.url
        detail_headers["Sec-Fetch-Site"] = "same-origin"
        detail = session.get(detail_url, headers=detail_headers, timeout=(6, 12), allow_redirects=True)
        print("DETAIL HTTP", detail.status_code, detail_url)
        if detail.status_code >= 400:
            print("DETAIL BLOCK PAGE", clean(detail.text)[:1500])
            return
        ds = BeautifulSoup(detail.text, "html.parser")
        detail_text = clean(ds.get_text(" ", strip=True))
        for label in ("Başlangıç Tarihi", "Bitiş Tarihi", "Etkinlik Yeri", "Etkinlik Türü", "Bilet Fiyatı", "Katılım Koşulu", "Düzenleyen"):
            match = re.search(re.escape(label) + r"\s+(.{0,220}?)(?=Başlangıç Tarihi|Bitiş Tarihi|Etkinlik Yeri|Etkinlik Türü|Bilet Fiyatı|Katılım Koşulu|Düzenleyen|İlgili Müdürlük|$)", detail_text, flags=re.I)
            print("FIELD", label, "=>", clean(match.group(1)) if match else None)
        print("DETAIL TEXT", detail_text[:3000])


if __name__ == "__main__":
    main()
