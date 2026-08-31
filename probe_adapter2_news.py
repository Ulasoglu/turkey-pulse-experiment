from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/2.0 (+adapter2 read-only probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
}

MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5,
    "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
}
DATE_NUMERIC = re.compile(r"\b([0-3]?\d)[./-]([01]?\d)[./-](20\d{2})\b")
DATE_TURKISH = re.compile(
    r"\b([0-3]?\d)\s+(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|Aralık|Aralik)(?:\s+\w+)?\s+(20\d{2})\b",
    re.IGNORECASE,
)
NOISE = {
    "haberler", "haber", "duyurular", "anasayfa", "ana sayfa", "devamını oku", "devamini oku",
    "detay", "detaylı bilgi", "detayli bilgi", "tüm haberler", "tum haberler", "daha fazla",
}
BAD_PATH_BITS = ("/iletisim", "/kurumsal", "/baskan", "/meclis", "/galeri", "/video", "/arama")


@dataclass(frozen=True)
class Source:
    province: str
    source_id: str
    url: str


# Round 3 focuses on reachable sources where Adapter 1 parsed zero candidates.
# These are deliberately tested as a small group before any production promotion.
SOURCES = [
    Source("Trabzon", "trabzon_bb_news", "https://trabzon.bel.tr/"),
    Source("Denizli", "denizli_bb_news", "https://yeni.denizli.bel.tr/Default.aspx?k=haberlist"),
    Source("Kastamonu", "kastamonu_bel_news", "https://www.kastamonu.bel.tr/haberler/"),
    Source("Mardin", "mardin_bb_news", "https://www.mardin.bel.tr/haberler"),
    Source("Siirt", "siirt_bel_news", "https://www.siirt.bel.tr/haberler"),
    Source("Afyonkarahisar", "afyon_bel_news", "https://www.afyon.bel.tr/ana-sayfa"),
    Source("Antalya", "antalya_bb_news", "https://www.antalya.bel.tr/haberler"),
]


def clean(value) -> str:
    return " ".join(str(value or "").split()).strip()


def norm(value) -> str:
    return clean(value).translate(str.maketrans({"I": "i", "İ": "i", "ı": "i"})).casefold()


def host(value: str) -> str:
    return urlparse(value).netloc.casefold().removeprefix("www.")


def parse_date(value):
    text = clean(value)
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except ValueError:
        pass
    match = DATE_NUMERIC.search(text)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    match = DATE_TURKISH.search(text)
    if match:
        day, month_name, year = match.groups()
        month = MONTHS.get(norm(month_name))
        if month:
            try:
                return datetime(int(year), month, int(day)).date().isoformat()
            except ValueError:
                return None
    return None


def request(url, timeout=25):
    started = time.perf_counter()
    response = requests.get(url, headers=HEADERS, timeout=(8, timeout), allow_redirects=True)
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    return response, elapsed


def plausible_link(source: Source, absolute: str) -> bool:
    parsed = urlparse(absolute)
    if host(absolute) != host(source.url):
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    low = absolute.casefold()
    if any(bit in low for bit in BAD_PATH_BITS):
        return False
    if re.search(r"\.(?:jpg|jpeg|png|gif|webp|pdf|zip)(?:$|\?)", low):
        return False
    return True


def add_candidate(rows, seen, source, title, url, date, strategy):
    title = clean(unescape(title))
    if len(title) < 18 or len(title) > 260 or norm(title) in NOISE:
        return
    absolute = urljoin(source.url, clean(url)).split("#", 1)[0]
    if not plausible_link(source, absolute):
        return
    key = absolute.rstrip("/").casefold()
    if key in seen:
        existing = next((row for row in rows if row["key"] == key), None)
        if existing and not existing["date"] and date:
            existing["date"] = date
            existing["strategy"] += "+dated"
        return
    seen.add(key)
    rows.append({"key": key, "title": title, "url": absolute, "date": date, "strategy": strategy})


def walk_jsonld(node, source, rows, seen):
    if isinstance(node, list):
        for item in node:
            walk_jsonld(item, source, rows, seen)
        return
    if not isinstance(node, dict):
        return
    title = node.get("headline") or node.get("name")
    url = node.get("url") or node.get("@id")
    kind = str(node.get("@type") or "")
    date = parse_date(node.get("datePublished") or node.get("dateCreated"))
    if title and url and any(token in kind.casefold() for token in ("article", "news", "listitem")):
        add_candidate(rows, seen, source, title, url, date, "jsonld")
    for value in node.values():
        if isinstance(value, (dict, list)):
            walk_jsonld(value, source, rows, seen)


def extract_html(source: Source, html: str):
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()

    for script in soup.find_all("script", type=lambda x: x and "ld+json" in x):
        try:
            payload = json.loads(script.string or script.get_text())
        except Exception:
            continue
        walk_jsonld(payload, source, rows, seen)

    for container in soup.find_all(["article", "li", "div"]):
        classes = " ".join(container.get("class") or []).casefold()
        if not any(token in classes for token in ("haber", "news", "post", "article", "card", "duyuru")):
            continue
        anchor = None
        heading = container.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading:
            anchor = heading.find("a", href=True) or heading.find_parent("a", href=True)
        anchor = anchor or container.find("a", href=True)
        if not anchor:
            continue
        title = clean(heading.get_text(" ", strip=True)) if heading else clean(anchor.get_text(" ", strip=True))
        time_node = container.find("time")
        date = parse_date(time_node.get("datetime") if time_node else None)
        if not date:
            date = parse_date(container.get_text(" ", strip=True))
        add_candidate(rows, seen, source, title, anchor.get("href"), date, "semantic-card")

    for heading in soup.find_all(["h2", "h3", "h4", "h5", "h6"]):
        anchor = heading.find("a", href=True) or heading.find_parent("a", href=True)
        if not anchor:
            continue
        title = clean(heading.get_text(" ", strip=True))
        parent_text = clean((heading.parent or heading).get_text(" ", strip=True))
        add_candidate(rows, seen, source, title, anchor.get("href"), parse_date(parent_text), "heading-link")

    return rows, soup


def wordpress_api_candidates(source: Source, soup, rows, seen):
    api_link = soup.find("link", rel=lambda value: value and "https://api.w.org/" in str(value))
    api_root = clean(api_link.get("href")) if api_link else ""
    if not api_root and "/category/" in source.url:
        parsed = urlparse(source.url)
        api_root = f"{parsed.scheme}://{parsed.netloc}/wp-json/"
    if not api_root:
        return None
    url = urljoin(api_root, "wp/v2/posts?per_page=10&_fields=link,date,title")
    try:
        response, elapsed = request(url, timeout=20)
        payload = response.json()
    except Exception as exc:
        return f"WP_API_ERROR {type(exc).__name__}: {exc}"
    if isinstance(payload, list):
        for item in payload:
            title = ((item.get("title") or {}).get("rendered") or "") if isinstance(item, dict) else ""
            link = item.get("link") if isinstance(item, dict) else None
            date = parse_date(item.get("date")) if isinstance(item, dict) else None
            if title and link:
                add_candidate(rows, seen, source, BeautifulSoup(title, "html.parser").get_text(" ", strip=True), link, date, "wordpress-api")
    return f"WP_API_OK {len(payload) if isinstance(payload, list) else 0} rows {elapsed:.2f}s"


def detail_date(url: str):
    try:
        response, _ = request(url, timeout=18)
    except Exception:
        return None, None
    soup = BeautifulSoup(response.text, "html.parser")
    for selector, attr in (
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ('meta[name="publish-date"]', "content"),
        ("time[datetime]", "datetime"),
    ):
        node = soup.select_one(selector)
        if node:
            date = parse_date(node.get(attr))
            if date:
                return date, "detail-semantic"
    for script in soup.find_all("script", type=lambda x: x and "ld+json" in x):
        try:
            payload = json.loads(script.string or script.get_text())
        except Exception:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                date = parse_date(node.get("datePublished") or node.get("dateCreated"))
                if date:
                    return date, "detail-jsonld"
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    text = clean(soup.get_text(" ", strip=True))[:6000]
    parsed = parse_date(text)
    return parsed, "detail-text" if parsed else None


def probe(source: Source):
    response, elapsed = request(source.url)
    rows, soup = extract_html(source, response.text)
    seen = {row["key"] for row in rows}
    wp_status = wordpress_api_candidates(source, soup, rows, seen)

    detail_fetches = 0
    for row in rows[:12]:
        if row["date"]:
            continue
        date, strategy = detail_date(row["url"])
        detail_fetches += 1
        if date:
            row["date"] = date
            row["strategy"] += "+" + strategy

    return {
        "status": response.status_code,
        "elapsed": elapsed,
        "bytes": len(response.content),
        "final_url": response.url,
        "rows": rows,
        "wp_status": wp_status,
        "detail_fetches": detail_fetches,
    }


def main():
    print("=== ADAPTER 2 MUNICIPAL NEWS PROBE ===")
    print("ROUND: 3 / reachable Adapter-1 mismatches")
    print("MODE: read-only; production data and registry are NOT modified")
    print("TLS verification stays enabled; access-control failures are not bypassed.")
    winners = 0

    for source in SOURCES:
        print(f"\n--- {source.province} / {source.source_id} ---")
        print(f"URL: {source.url}")
        try:
            result = probe(source)
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")
            continue

        rows = result["rows"]
        dated = sum(1 for row in rows if row["date"])
        if rows:
            winners += 1
        print(f"HTTP: {result['status']} | {result['elapsed']:.2f}s | {result['bytes']} bytes")
        print(f"FINAL URL: {result['final_url']}")
        print(f"PARSED: {len(rows)} candidates | dated={dated} | detail_fetches={result['detail_fetches']}")
        if result["wp_status"]:
            print(result["wp_status"])
        strategies = {}
        for row in rows:
            strategies[row["strategy"]] = strategies.get(row["strategy"], 0) + 1
        print("STRATEGIES:", strategies)
        for index, row in enumerate(rows[:8], 1):
            print(f"  {index}. {row['date'] or 'NO_DATE'} | {row['title']}")
            print(f"     {row['strategy']} | {row['url']}")

    print("\n=== ADAPTER 2 SUMMARY ===")
    print(f"SOURCES WITH CANDIDATES: {winners}/{len(SOURCES)}")
    print("RESULT: inspect winners, then promote only validated shapes into production.")


if __name__ == "__main__":
    main()
