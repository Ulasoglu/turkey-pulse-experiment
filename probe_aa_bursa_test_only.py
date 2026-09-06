"""TEST_ONLY probe for Anadolu Ajansi Bursa.

Purpose: product feasibility only. This does not merge into Turkey Pulse production data.
AA article/image metadata remain source-owned; no media is downloaded or copied.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# AA's search page is JS-dependent. The server-rendered Gündem page exposes current
# article links, so the probe discovers there and keeps only articles whose title/
# description/body identify Bursa.
DISCOVERY_URL = "https://www.aa.com.tr/tr/gundem"
OUT = Path("data/test_only_aa_bursa.jsonl")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TurkeyPulseFeasibilityTest/1.0)"}
MAX_CANDIDATES = 60
MAX_ARTICLES = 12


def get(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r


def meta(soup: BeautifulSoup, *keys: tuple[str, str]) -> str | None:
    for attr, value in keys:
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def candidate_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin("https://www.aa.com.tr", a["href"]).split("#", 1)[0].rstrip("/")
        if not re.match(r"https://www\.aa\.com\.tr/tr/[^/]+/.+/\d+$", href):
            continue
        if href not in links:
            links.append(href)
    return links[:MAX_CANDIDATES]


def parse_article(url: str) -> dict | None:
    soup = BeautifulSoup(get(url).text, "html.parser")
    title = meta(soup, ("property", "og:title"), ("name", "twitter:title"))
    if not title and soup.h1:
        title = soup.h1.get_text(" ", strip=True)
    description = meta(soup, ("property", "og:description"), ("name", "description")) or ""
    image = meta(soup, ("property", "og:image"), ("name", "twitter:image"))
    published = meta(soup, ("property", "article:published_time"), ("name", "date"))

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            obj = json.loads(script.string or "")
        except Exception:
            continue
        objs = obj if isinstance(obj, list) else [obj]
        for item in objs:
            if not isinstance(item, dict):
                continue
            title = title or item.get("headline")
            published = published or item.get("datePublished")
            raw_image = item.get("image")
            if not image and isinstance(raw_image, str):
                image = raw_image
            elif not image and isinstance(raw_image, list) and raw_image:
                image = raw_image[0] if isinstance(raw_image[0], str) else None
            elif not image and isinstance(raw_image, dict):
                image = raw_image.get("url")

    text = soup.get_text(" ", strip=True)
    haystack = f"{title or ''} {description} {text[:5000]}".lower()
    if "bursa" not in haystack:
        return None

    if not published:
        # AA visibly renders dates like '06 Eylül 2026'. Keep the source string for
        # this feasibility probe; normalization can happen in the shared adapter.
        m = re.search(
            r"\b\d{1,2}\s+(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+\d{4}\b",
            text,
            re.IGNORECASE,
        )
        published = m.group(0) if m else None

    return {
        "test_only": True,
        "source": "AA",
        "province": "Bursa",
        "title": title,
        "published_at": published,
        "url": url,
        "image_url": image,
        "rights_status": "subscription_or_permission_required",
    }


def main() -> None:
    print("=== AA BURSA TEST_ONLY PROBE ===")
    print("Discovery:", DISCOVERY_URL)
    links = candidate_links(get(DISCOVERY_URL).text)
    print("Candidate links found:", len(links))
    rows = []
    for url in links:
        if len(rows) >= MAX_ARTICLES:
            break
        try:
            row = parse_article(url)
            if not row:
                continue
            rows.append(row)
            print("OK", row.get("published_at"), row.get("title"), "IMAGE=", bool(row.get("image_url")))
        except Exception as exc:
            print("ERROR", url, type(exc).__name__, str(exc)[:180])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("Rows written:", len(rows))
    print("With timestamps:", sum(bool(r.get("published_at")) for r in rows))
    print("With image metadata:", sum(bool(r.get("image_url")) for r in rows))
    print("Output:", OUT)
    print("TEST_ONLY: not merged into raw_signals.jsonl")


if __name__ == "__main__":
    main()
