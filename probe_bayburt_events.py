from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL = "https://www.bayburt.bel.tr/etkinlikler"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
}


def clean(value):
    return " ".join(str(value or "").split())


def main():
    response = requests.get(URL, headers=HEADERS, timeout=(6, 12), allow_redirects=True)
    print("HTTP", response.status_code)
    print("FINAL URL", response.url)
    print("SERVER", response.headers.get("server"))
    print("CONTENT-TYPE", response.headers.get("content-type"))
    print("BYTES", len(response.content))
    if response.status_code >= 400:
        print("BLOCK PAGE", clean(response.text)[:2000])
        print("BAYBURT BLOCKED - probe ends without failing main workflow")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    text = clean(soup.get_text(" ", strip=True))
    print("PAGE TEXT", text[:6000])

    links = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        label = clean(anchor.get_text(" ", strip=True))
        absolute = urljoin(response.url, href)
        if absolute in seen:
            continue
        if "etkinlik" not in href.casefold() and "etkinlik" not in label.casefold():
            continue
        seen.add(absolute)
        links.append((label, absolute))

    print("EVENT-LIKE LINKS", len(links))
    for label, url in links[:30]:
        print("LINK", label[:200], "=>", url)

    dates = re.findall(r"\b\d{1,2}\s+(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+20\d{2}\b", text, flags=re.I)
    print("FULL DATES", dates[:40])

    scripts = []
    for script in soup.find_all("script", src=True):
        scripts.append(urljoin(response.url, script.get("src")))
    print("SCRIPTS", len(scripts))
    for src in scripts[:30]:
        print("SCRIPT", src)


if __name__ == "__main__":
    main()
