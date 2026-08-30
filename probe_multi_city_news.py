from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.0 (+municipal multi-city probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
}

DATE_PATTERNS = [
    re.compile(r"\b([0-3]?\d)[./-]([01]?\d)[./-](20\d{2})\b"),
    re.compile(
        r"\b([0-3]?\d)\s+(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|Aralık|Aralik)(?:\s+\w+)?\s+(20\d{2})\b",
        re.IGNORECASE,
    ),
]

MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5,
    "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
}

NOISE = {
    "haberler", "haber detayı", "haber detayi", "detaylı bilgi", "detayli bilgi", "detaya git",
    "devamını oku", "devamini oku", "sonraki", "önceki", "onceki", "anasayfa", "tüm haberler",
    "tum haberler", "daha fazla", "detay",
}


@dataclass(frozen=True)
class Source:
    province: str
    url: str
    path_hints: tuple[str, ...]


SOURCES = [
    Source("Adana", "https://www.adana.bel.tr/tr/haberler", ("/tr/haberler",)),
    Source("Eskişehir", "https://www.eskisehir.bel.tr/haberler", ("/haberler",)),
    Source("Gaziantep", "https://www.gaziantep.bel.tr/tr/haberler", ("/tr/haberler",)),
    Source("Kayseri", "https://www.kayseri.bel.tr/haberler", ("/haberler", "/haber/")),
]


def clean(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip()


def norm(value: str | None) -> str:
    return clean(value).translate(str.maketrans({"I": "i", "İ": "i", "ı": "i"})).casefold()


def parse_date(text: str):
    value = clean(text)
    m = DATE_PATTERNS[0].search(value)
    if m:
        day, month, year = map(int, m.groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    m = DATE_PATTERNS[1].search(value)
    if m:
        day, month_name, year = m.groups()
        month = MONTHS.get(norm(month_name))
        if month:
            try:
                return datetime(int(year), month, int(day)).date().isoformat()
            except ValueError:
                return None
    return None


def is_internal_detail(source: Source, absolute_url: str) -> bool:
    base = urlparse(source.url)
    target = urlparse(absolute_url)
    if target.netloc != base.netloc:
        return False
    path = target.path.rstrip("/")
    root = base.path.rstrip("/")
    if path == root:
        return False
    if target.query and any(key in target.query.casefold() for key in ("page=", "sayfa=")):
        return False
    if path.startswith(root + "/") and path[len(root) + 1 :].isdigit():
        # Typical listing pagination, not a news detail.
        return False
    return any(hint in path for hint in source.path_hints)


def nearest_card(anchor):
    node = anchor
    best = anchor.parent
    for _ in range(6):
        if node is None:
            break
        text = clean(node.get_text(" ", strip=True))
        if 30 <= len(text) <= 2500:
            best = node
            if parse_date(text):
                return node
        node = node.parent
    return best


def title_from(anchor, card) -> str | None:
    anchor_text = clean(anchor.get_text(" ", strip=True))
    if len(anchor_text) >= 18 and norm(anchor_text) not in NOISE:
        return anchor_text[:260]
    for selector in ("h1", "h2", "h3", "h4", "h5", "h6", ".title", ".haber-baslik", ".news-title", "strong"):
        element = card.select_one(selector) if card else None
        candidate = clean(element.get_text(" ", strip=True)) if element else ""
        if len(candidate) >= 18 and norm(candidate) not in NOISE:
            return candidate[:260]
    if card:
        for element in card.find_all("a", href=True):
            candidate = clean(element.get_text(" ", strip=True))
            if len(candidate) >= 18 and norm(candidate) not in NOISE:
                return candidate[:260]
    return None


def extract(source: Source, html: str):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        href = clean(anchor.get("href"))
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(source.url, href)
        if not is_internal_detail(source, absolute):
            continue
        card = nearest_card(anchor)
        title = title_from(anchor, card)
        if not title:
            continue
        key = (norm(title), absolute.split("#", 1)[0])
        if key in seen:
            continue
        seen.add(key)
        card_text = clean(card.get_text(" ", strip=True)) if card else title
        rows.append({
            "title": title,
            "date": parse_date(card_text),
            "url": absolute.split("#", 1)[0],
            "context_chars": len(card_text),
        })

    # If a site uses title links whose paths are not predictable, fall back to
    # heading-linked items inside the main news page. We keep this deliberately
    # conservative and probe-only.
    if len(rows) < 3:
        for heading in soup.find_all(["h2", "h3", "h4", "h5", "h6"]):
            title = clean(heading.get_text(" ", strip=True))
            if len(title) < 18 or norm(title) in NOISE:
                continue
            anchor = heading.find("a", href=True) or heading.find_parent("a", href=True)
            if not anchor:
                continue
            absolute = urljoin(source.url, clean(anchor.get("href")))
            target = urlparse(absolute)
            if target.netloc != urlparse(source.url).netloc:
                continue
            key = (norm(title), absolute.split("#", 1)[0])
            if key in seen:
                continue
            seen.add(key)
            card = nearest_card(anchor)
            card_text = clean(card.get_text(" ", strip=True)) if card else title
            rows.append({"title": title[:260], "date": parse_date(card_text), "url": absolute.split("#", 1)[0], "context_chars": len(card_text)})

    return rows


def probe(source: Source):
    started = time.perf_counter()
    response = requests.get(source.url, headers=HEADERS, timeout=(5, 20), allow_redirects=True)
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    rows = extract(source, response.text)
    dated = sum(1 for row in rows if row["date"])
    unique_paths = len({urlparse(row["url"]).path for row in rows})
    return {
        "status": response.status_code,
        "elapsed": elapsed,
        "bytes": len(response.content),
        "rows": rows,
        "dated": dated,
        "unique_paths": unique_paths,
        "final_url": response.url,
    }


def main():
    print("=== MULTI-CITY MUNICIPAL NEWS PROBE ===")
    print("MODE: read-only feasibility probe; production data is NOT modified")
    successes = 0
    total_rows = 0

    for source in SOURCES:
        print(f"\n--- {source.province} ---")
        print(f"URL: {source.url}")
        try:
            result = probe(source)
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")
            continue

        rows = result["rows"]
        total_rows += len(rows)
        if rows:
            successes += 1
        print(f"HTTP: {result['status']} | {result['elapsed']:.2f}s | {result['bytes']} bytes")
        print(f"FINAL URL: {result['final_url']}")
        print(f"PARSED: {len(rows)} candidates | dated={result['dated']} | unique_paths={result['unique_paths']}")
        for index, row in enumerate(rows[:6], 1):
            print(f"  {index}. {row['date'] or 'NO_DATE'} | {row['title']}")
            print(f"     {row['url']}")

    print("\n=== PROBE SUMMARY ===")
    print(f"SOURCES WITH CANDIDATES: {successes}/{len(SOURCES)}")
    print(f"TOTAL CANDIDATES: {total_rows}")
    if successes == 0:
        raise SystemExit("Probe failed: no source produced any candidate rows")
    print("RESULT: probe completed; inspect per-city shape before building production adapters")


if __name__ == "__main__":
    main()
