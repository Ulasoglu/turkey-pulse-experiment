from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "raw_signals.jsonl"
TURKEY_TZ = timezone(timedelta(hours=3))
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.1 (+municipal news collector)",
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
    source_id: str
    province: str
    name: str
    url: str
    path_hints: tuple[str, ...]
    max_age_days: int = 7
    rights_status: str = "reuse_needs_final_check"


# One shared adapter; new compatible municipalities are added here after probe + rights review.
SOURCES = [
    Source(
        source_id="kayseri_bb_news",
        province="Kayseri",
        name="Kayseri Büyükşehir Belediyesi",
        url="https://www.kayseri.bel.tr/haberler",
        path_hints=("/haberler/", "/haber/"),
        max_age_days=7,
        rights_status="reuse_needs_final_check",
    ),
    Source(
        source_id="adana_bb_news",
        province="Adana",
        name="Adana Büyükşehir Belediyesi",
        url="https://www.adana.bel.tr/tr/haberler",
        path_hints=("/tr/haber/",),
        max_age_days=7,
        rights_status="reuse_needs_final_check",
    ),
]


def clean(value):
    return " ".join(str(value or "").split()).strip()


def norm(value):
    return clean(value).translate(str.maketrans({"I": "i", "İ": "i", "ı": "i"})).casefold()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_json(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def existing_hashes(source_id):
    values = set()
    if not OUT.exists():
        return values
    with OUT.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("source_id") == source_id and row.get("content_hash"):
                values.add(row["content_hash"])
    return values


def append_row(row):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_date(text):
    value = clean(text)
    match = DATE_PATTERNS[0].search(value)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return datetime(year, month, day, tzinfo=TURKEY_TZ).astimezone(timezone.utc)
        except ValueError:
            return None
    match = DATE_PATTERNS[1].search(value)
    if match:
        day, month_name, year = match.groups()
        month = MONTHS.get(norm(month_name))
        if month:
            try:
                return datetime(int(year), month, int(day), tzinfo=TURKEY_TZ).astimezone(timezone.utc)
            except ValueError:
                return None
    return None


def is_internal_detail(source, absolute_url):
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
    if path.startswith(root + "/") and path[len(root) + 1:].isdigit():
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


def title_from(anchor, card):
    anchor_text = clean(anchor.get_text(" ", strip=True))
    if len(anchor_text) >= 18 and norm(anchor_text) not in NOISE:
        return anchor_text[:260]
    for selector in ("h1", "h2", "h3", "h4", "h5", "h6", ".title", ".haber-baslik", ".news-title", "strong"):
        element = card.select_one(selector) if card else None
        candidate = clean(element.get_text(" ", strip=True)) if element else ""
        if len(candidate) >= 18 and norm(candidate) not in NOISE:
            return candidate[:260]
    return None


def extract_rows(source, html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = clean(anchor.get("href"))
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(source.url, href).split("#", 1)[0]
        if not is_internal_detail(source, absolute):
            continue
        card = nearest_card(anchor)
        title = title_from(anchor, card)
        if not title:
            continue
        published = parse_date(clean(card.get_text(" ", strip=True)) if card else title)
        key = (norm(title), absolute)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"title": title, "published": published, "url": absolute})
    return rows


def collect(source):
    print(f"\n--- {source.province} / {source.source_id} ---")
    response = requests.get(source.url, headers=HEADERS, timeout=(5, 25), allow_redirects=True)
    response.raise_for_status()
    candidates = extract_rows(source, response.text)
    cutoff = datetime.now(timezone.utc) - timedelta(days=source.max_age_days)
    known = existing_hashes(source.source_id)
    fresh = stale = undated = new_count = 0

    for item in candidates:
        published = item["published"]
        if published is None:
            undated += 1
            continue
        if published < cutoff:
            stale += 1
            continue
        fresh += 1
        content_hash = hash_json({"source": source.source_id, "url": item["url"], "title": item["title"], "published_at": published.isoformat()})
        if content_hash in known:
            continue
        row = {
            "collected_at": now_iso(),
            "source_id": source.source_id,
            "source_name": source.name,
            "province": source.province,
            "source_type": "municipal_news",
            "rights_status": source.rights_status,
            "image_rights_status": "reuse_needs_final_check",
            "url": item["url"],
            "http_status": response.status_code,
            "content_hash": content_hash,
            "title": item["title"],
            "published_at": published.isoformat(),
            "latitude": None,
            "longitude": None,
            "magnitude": None,
            "depth_km": None,
            "event_id": None,
            "image_url": None,
            "raw_summary": "municipal_news_generic item",
        }
        append_row(row)
        known.add(content_hash)
        new_count += 1
        print("NEW", published.date().isoformat(), item["title"])

    print(f"parsed={len(candidates)} fresh={fresh} stale={stale} undated={undated} new={new_count}")


def main():
    print("=== GENERIC MUNICIPAL NEWS COLLECTOR ===")
    print("Images disabled unless separately rights-cleared.")
    failures = 0
    for source in SOURCES:
        try:
            collect(source)
        except Exception as exc:
            failures += 1
            print(f"ERROR {source.source_id}: {type(exc).__name__}: {exc}")
        time.sleep(0.25)
    if failures == len(SOURCES):
        raise SystemExit("All municipal news sources failed")


if __name__ == "__main__":
    main()
