from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "raw_signals.jsonl"
REGISTRY = ROOT / "municipal_sources.json"
TURKEY_TZ = timezone(timedelta(hours=3))
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.4 (+municipal news collector)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
}

DATE_PATTERNS = [
    re.compile(r"\b([0-3]?\d)[./-]([01]?\d)[./-](20\d{2})\b"),
    re.compile(
        r"\b([0-3]?\d)\s+(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|Aralık|Aralik)(?:\s+\w+)?\s+(20\d{2})\b",
        re.IGNORECASE,
    ),
]
RELATIVE_DATE_PATTERN = re.compile(r"\b(\d{1,2})\s+gün\s+önce\b", re.IGNORECASE)
CLOCK_PATTERN = re.compile(r"\b[0-2]?\d:[0-5]\d\b")
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
    detail_date_fallback: bool = False
    detail_fetch_limit: int = 20
    enabled: bool = True
    status: str = "active"


def load_sources():
    if not REGISTRY.exists():
        raise RuntimeError(f"Missing municipal source registry: {REGISTRY}")
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    defaults = payload.get("defaults") or {}
    rows = payload.get("sources") or []
    sources = []
    seen = set()
    for row in rows:
        source_id = str(row.get("source_id") or "").strip()
        province = str(row.get("province") or "").strip()
        name = str(row.get("name") or "").strip()
        url = str(row.get("url") or "").strip()
        path_hints = tuple(str(value) for value in (row.get("path_hints") or []))
        if not source_id or not province or not name or not url or not path_hints:
            raise ValueError(f"Invalid municipal source registry row: {row}")
        if source_id in seen:
            raise ValueError(f"Duplicate municipal source_id: {source_id}")
        seen.add(source_id)
        sources.append(
            Source(
                source_id=source_id,
                province=province,
                name=name,
                url=url,
                path_hints=path_hints,
                max_age_days=int(row.get("max_age_days", defaults.get("max_age_days", 7))),
                rights_status=str(row.get("rights_status", defaults.get("rights_status", "reuse_needs_final_check"))),
                detail_date_fallback=bool(row.get("detail_date_fallback", defaults.get("detail_date_fallback", False))),
                detail_fetch_limit=int(row.get("detail_fetch_limit", defaults.get("detail_fetch_limit", 20))),
                enabled=bool(row.get("enabled", defaults.get("enabled", True))),
                status=str(row.get("status", "active")),
            )
        )
    return sources


def clean(value):
    return " ".join(str(value or "").split()).strip()


def norm(value):
    return clean(value).translate(str.maketrans({"I": "i", "İ": "i", "ı": "i"})).casefold()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_json(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def canonical_url(value):
    parsed = urlparse(value)
    query = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
    ]
    return urlunparse((
        parsed.scheme.casefold(),
        parsed.netloc.casefold(),
        parsed.path.rstrip("/") or "/",
        "",
        urlencode(query),
        "",
    ))


def parse_date(text, allow_relative=False, reference=None):
    value = clean(text)
    match = DATE_PATTERNS[0].search(value)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return datetime(year, month, day, tzinfo=TURKEY_TZ).astimezone(timezone.utc), "absolute"
        except ValueError:
            return None, None
    match = DATE_PATTERNS[1].search(value)
    if match:
        day, month_name, year = match.groups()
        month = MONTHS.get(norm(month_name))
        if month:
            try:
                return datetime(int(year), month, int(day), tzinfo=TURKEY_TZ).astimezone(timezone.utc), "absolute"
            except ValueError:
                return None, None
    if allow_relative:
        now_local = (reference or datetime.now(timezone.utc)).astimezone(TURKEY_TZ)
        normalized = norm(value)
        if re.search(r"\bbugün\b", normalized):
            local_date = now_local.date()
            return datetime(local_date.year, local_date.month, local_date.day, tzinfo=TURKEY_TZ).astimezone(timezone.utc), "relative"
        if re.search(r"\bdün\b", normalized):
            local_date = (now_local - timedelta(days=1)).date()
            return datetime(local_date.year, local_date.month, local_date.day, tzinfo=TURKEY_TZ).astimezone(timezone.utc), "relative"
        relative = RELATIVE_DATE_PATTERN.search(value)
        if relative:
            local_date = (now_local - timedelta(days=int(relative.group(1)))).date()
            return datetime(local_date.year, local_date.month, local_date.day, tzinfo=TURKEY_TZ).astimezone(timezone.utc), "relative"
    return None, None


def strip_date_suffix(value):
    text = clean(value)
    text = DATE_PATTERNS[0].sub(" ", text)
    text = DATE_PATTERNS[1].sub(" ", text)
    text = RELATIVE_DATE_PATTERN.sub(" ", text)
    text = re.sub(r"\bbugün\b|\bdün\b", " ", text, flags=re.IGNORECASE)
    text = CLOCK_PATTERN.sub(" ", text)
    return clean(text).strip(" -–—|·")


def request_with_retry(url, *, attempts=3, read_timeout=20):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=(8, read_timeout + (attempt - 1) * 10),
                allow_redirects=True,
            )
            response.raise_for_status()
            if attempt > 1:
                print(f"RETRY OK attempt={attempt} {url}")
            return response
        except requests.exceptions.SSLError:
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            wait = 0.75 * attempt
            print(f"RETRY attempt={attempt + 1}/{attempts} after {type(exc).__name__}: {url}")
            time.sleep(wait)
    raise last_error


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
    # Prefer the tightest parent that looks like one item. Do not climb into a
    # large list container just because a sibling happens to contain a date.
    node = anchor
    best = anchor.parent
    for _ in range(5):
        if node is None:
            break
        text = clean(node.get_text(" ", strip=True))
        links = len(node.find_all("a", href=True)) if hasattr(node, "find_all") else 0
        if 25 <= len(text) <= 1600 and links <= 6:
            best = node
            _, kind = parse_date(text, allow_relative=True)
            if kind:
                return node
        node = node.parent
    return best


def title_from(anchor, card):
    anchor_text = strip_date_suffix(anchor.get_text(" ", strip=True))
    if len(anchor_text) >= 18 and norm(anchor_text) not in NOISE:
        return anchor_text[:260]
    for selector in ("h1", "h2", "h3", "h4", "h5", "h6", ".title", ".haber-baslik", ".news-title", "strong"):
        element = card.select_one(selector) if card else None
        candidate = strip_date_suffix(element.get_text(" ", strip=True)) if element else ""
        if len(candidate) >= 18 and norm(candidate) not in NOISE:
            return candidate[:260]
    return None


def extract_rows(source, html):
    soup = BeautifulSoup(html, "html.parser")
    by_url = {}
    reference = datetime.now(timezone.utc)
    for anchor in soup.find_all("a", href=True):
        href = clean(anchor.get("href"))
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(source.url, href).split("#", 1)[0]
        if not is_internal_detail(source, absolute):
            continue
        url_key = canonical_url(absolute)
        card = nearest_card(anchor)
        title = title_from(anchor, card)
        if not title:
            continue

        # Date nearest to the link wins. Relative dates are accepted only in
        # the anchor/card itself, never from a broad ancestor/list container.
        anchor_text = clean(anchor.get_text(" ", strip=True))
        published, date_kind = parse_date(anchor_text, allow_relative=True, reference=reference)
        if not published:
            card_text = clean(card.get_text(" ", strip=True)) if card else ""
            published, date_kind = parse_date(card_text, allow_relative=True, reference=reference)

        candidate = {
            "title": title,
            "published": published,
            "url": absolute,
            "date_source": f"listing_{date_kind}" if published else None,
        }
        existing = by_url.get(url_key)
        if existing is None:
            by_url[url_key] = candidate
            continue

        # A detail URL represents one story. Prefer an absolute date over a
        # relative one and a cleaner/shorter headline over duplicated metadata.
        existing_absolute = existing.get("date_source") == "listing_absolute"
        candidate_absolute = candidate.get("date_source") == "listing_absolute"
        if candidate_absolute and not existing_absolute:
            by_url[url_key] = candidate
        elif candidate_absolute == existing_absolute and len(candidate["title"]) < len(existing["title"]):
            by_url[url_key] = candidate

    return list(by_url.values())


def fetch_detail_date(item):
    response = request_with_retry(item["url"], attempts=2, read_timeout=20)
    soup = BeautifulSoup(response.text, "html.parser")
    text = clean(soup.get_text(" ", strip=True))
    published, _ = parse_date(text[:5000], allow_relative=False)
    return published


def load_raw_rows():
    if not OUT.exists():
        return []
    rows = []
    with OUT.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def same_story(existing, current):
    return (
        clean(existing.get("title")) == clean(current.get("title"))
        and existing.get("published_at") == current.get("published_at")
        and canonical_url(existing.get("url") or "") == canonical_url(current.get("url") or "")
    )


def replace_source_snapshot(source_id, current_rows):
    all_rows = load_raw_rows()
    old_source_rows = [row for row in all_rows if row.get("source_id") == source_id]
    other_rows = [row for row in all_rows if row.get("source_id") != source_id]

    old_by_url = {}
    for row in old_source_rows:
        key = canonical_url(row.get("url") or "")
        old_by_url.setdefault(key, []).append(row)

    final_source_rows = []
    changed = False
    for current in current_rows:
        key = canonical_url(current.get("url") or "")
        matching = next((row for row in old_by_url.get(key, []) if same_story(row, current)), None)
        if matching:
            final_source_rows.append(matching)
        else:
            final_source_rows.append(current)
            changed = True

    if len(old_source_rows) != len(final_source_rows):
        changed = True
    elif len({canonical_url(row.get("url") or "") for row in old_source_rows}) != len(old_source_rows):
        changed = True

    if changed:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8") as handle:
            for row in other_rows + final_source_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return changed, len(old_source_rows), len(final_source_rows)


def collect(source):
    print(f"\n--- {source.province} / {source.source_id} ---")
    response = request_with_retry(source.url, attempts=3, read_timeout=20)
    candidates = extract_rows(source, response.text)

    detail_fetched = detail_dated = detail_errors = 0
    if source.detail_date_fallback:
        for item in candidates:
            if item["published"] is not None:
                continue
            if detail_fetched >= source.detail_fetch_limit:
                break
            detail_fetched += 1
            try:
                published = fetch_detail_date(item)
                if published:
                    item["published"] = published
                    item["date_source"] = "detail_absolute"
                    detail_dated += 1
                else:
                    print("DETAIL NO DATE", item["url"])
            except Exception as exc:
                detail_errors += 1
                print(f"DETAIL ERROR {item['url']}: {type(exc).__name__}: {exc}")
            time.sleep(0.15)

    cutoff = datetime.now(timezone.utc) - timedelta(days=source.max_age_days)
    fresh = stale = undated = 0
    snapshot_rows = []

    for item in candidates:
        published = item["published"]
        if published is None:
            undated += 1
            continue
        if published < cutoff:
            stale += 1
            continue
        fresh += 1
        content_hash = hash_json({
            "source": source.source_id,
            "url": canonical_url(item["url"]),
            "title": item["title"],
            "published_at": published.isoformat(),
        })
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
            "published_at_source": item.get("date_source"),
            "latitude": None,
            "longitude": None,
            "magnitude": None,
            "depth_km": None,
            "event_id": None,
            "image_url": None,
            "raw_summary": "municipal_news_generic item",
        }
        snapshot_rows.append(row)

    changed, old_count, final_count = replace_source_snapshot(source.source_id, snapshot_rows)
    print(
        f"parsed={len(candidates)} fresh={fresh} stale={stale} undated={undated} "
        f"snapshot={final_count} replaced_old={old_count} changed={int(changed)} "
        f"detail_fetched={detail_fetched} detail_dated={detail_dated} detail_errors={detail_errors}"
    )


def main():
    print("=== GENERIC MUNICIPAL NEWS COLLECTOR ===")
    print("Images disabled unless separately rights-cleared.")
    print("Hardening: canonical-URL dedupe, relative-date parsing, source snapshots, retries enabled.")
    sources = load_sources()
    enabled_sources = [source for source in sources if source.enabled]
    disabled_sources = [source for source in sources if not source.enabled]
    print(f"Registry: {len(sources)} configured, {len(enabled_sources)} enabled, {len(disabled_sources)} paused")
    for source in disabled_sources:
        print(f"SKIP {source.source_id}: status={source.status}")

    failures = 0
    for source in enabled_sources:
        try:
            collect(source)
        except Exception as exc:
            failures += 1
            print(f"ERROR {source.source_id}: {type(exc).__name__}: {exc}")
        time.sleep(0.25)
    if enabled_sources and failures == len(enabled_sources):
        raise SystemExit("All enabled municipal news sources failed")


if __name__ == "__main__":
    main()
