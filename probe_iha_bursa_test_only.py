"""TEST_ONLY probe for IHA Bursa.

Purpose: product feasibility only. This does not merge into Turkey Pulse production data.
Article/image metadata remain source-owned; no media is downloaded or copied.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

LISTING_URL = "https://www.iha.com.tr/bursa-haberleri"
OUT = Path("data/test_only_iha_bursa.jsonl")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TurkeyPulseFeasibilityTest/1.0)"}
MAX_ARTICLES = 15
ISTANBUL = ZoneInfo("Europe/Istanbul")


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


def article_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(LISTING_URL, a["href"])
        if re.search(r"https://www\.iha\.com\.tr/bursa-haberleri/.+-\d+/?$", href):
            href = href.rstrip("/")
            if href not in links:
                links.append(href)
    return links[:MAX_ARTICLES]


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ISTANBUL)
        return dt.isoformat()
    except ValueError:
        pass
    for pattern in (
        r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s*(?:-|,)?\s*(\d{1,2}):(\d{2})",
        r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})",
    ):
        m = re.search(pattern, value)
        if m:
            parts = [int(x) for x in m.groups()]
            day, month, year = parts[:3]
            hour, minute = (parts[3], parts[4]) if len(parts) == 5 else (0, 0)
            return datetime(year, month, day, hour, minute, tzinfo=ISTANBUL).isoformat()
    return value


def find_visible_date(soup: BeautifulSoup) -> str | None:
    text = soup.get_text(" ", strip=True)
    patterns = (
        r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\s*(?:-|,)?\s*\d{1,2}:\d{2}\b",
        r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b",
    )
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(0)
    return None


def parse_article(url: str) -> dict:
    soup = BeautifulSoup(get(url).text, "html.parser")
    title = meta(soup, ("property", "og:title"), ("name", "twitter:title"))
    if not title and soup.h1:
        title = soup.h1.get_text(" ", strip=True)

    image = meta(soup, ("property", "og:image"), ("name", "twitter:image"))
    published = meta(
        soup,
        ("property", "article:published_time"),
        ("name", "date"),
        ("itemprop", "datePublished"),
    )

    # JSON-LD is often the cleanest fallback for date/image.
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
            published = published or item.get("datePublished") or item.get("dateCreated")
            raw_image = item.get("image")
            if not image and isinstance(raw_image, str):
                image = raw_image
            elif not image and isinstance(raw_image, list) and raw_image:
                image = raw_image[0] if isinstance(raw_image[0], str) else None
            elif not image and isinstance(raw_image, dict):
                image = raw_image.get("url")

    published = normalize_date(published or find_visible_date(soup))

    return {
        "test_only": True,
        "source": "IHA",
        "province": "Bursa",
        "title": title,
        "published_at": published,
        "url": url,
        "image_url": image,
        "rights_status": "no_reuse_without_permission",
    }


def main() -> None:
    print("=== IHA BURSA TEST_ONLY PROBE ===")
    print("Listing:", LISTING_URL)
    links = article_links(get(LISTING_URL).text)
    print("Article links found:", len(links))

    rows = []
    for url in links:
        try:
            row = parse_article(url)
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
