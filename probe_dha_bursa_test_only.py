#!/usr/bin/env python3
"""TEST_ONLY probe for DHA Bursa.

Product-validation only. This probe does NOT merge DHA content into the normal
Turkey Pulse dataset and does NOT download or store image files. It extracts
metadata needed to evaluate the desired news-card experience.

DHA states that its articles/news/photos may not be reused without permission.
Do not turn this probe into a production source without appropriate rights.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin
from urllib.request import Request, urlopen

LIST_URL = "https://www.dha.com.tr/bursa-haber/"
OUT = "data/test_only_dha_bursa.jsonl"
UA = "Mozilla/5.0 (compatible; TurkeyPulseProductProbe/1.0)"
MAX_ARTICLES = 12


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
    with urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def clean(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip() or None


def meta(html: str, key: str) -> str | None:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(key)}["\']',
        rf'<meta[^>]+name=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.I)
        if m:
            return clean(m.group(1))
    return None


def article_links(html: str) -> list[str]:
    links = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        url = urljoin(LIST_URL, unescape(href))
        if "dha.com.tr/yerel-haberler/bursa/" not in url:
            continue
        if url not in links:
            links.append(url)
    return links[:MAX_ARTICLES]


def parse_article(url: str) -> dict:
    html = fetch(url)
    title = meta(html, "og:title")
    image = meta(html, "og:image")
    description = meta(html, "og:description")

    if not title:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
        title = clean(m.group(1)) if m else None

    published = None
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})", html)
    if m:
        try:
            published = datetime.strptime(
                f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M"
            ).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass

    district = None
    m = re.search(r"/yerel-haberler/bursa/([^/]+)/", url, re.I)
    if m:
        district = m.group(1).replace("-", " ").title()

    return {
        "source_id": "dha_test_only",
        "source_name": "DHA",
        "test_only": True,
        "rights_status": "no_reuse_without_permission",
        "province": "Bursa",
        "district": district,
        "title": title,
        "summary_metadata": description,
        "published_at": published,
        "url": url,
        "image_url_metadata": image,
        "image_downloaded": False,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    listing = fetch(LIST_URL)
    links = article_links(listing)
    print("=== DHA BURSA TEST_ONLY PROBE ===")
    print("Listing:", LIST_URL)
    print("Article links found:", len(links))

    rows = []
    for url in links:
        try:
            row = parse_article(url)
            rows.append(row)
            print("OK", row.get("published_at"), row.get("title"), "IMAGE=", bool(row.get("image_url_metadata")))
        except Exception as exc:
            print("ERROR", url, repr(exc))

    with open(OUT, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("Rows written:", len(rows))
    print("With image metadata:", sum(bool(r.get("image_url_metadata")) for r in rows))
    print("Output:", OUT)
    print("TEST_ONLY: not merged into raw_signals.jsonl")


if __name__ == "__main__":
    main()
