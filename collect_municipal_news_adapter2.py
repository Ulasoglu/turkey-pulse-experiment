from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from collect_municipal_news import (
    MAX_FUTURE_PUBLICATION_SKEW,
    REGISTRY,
    TURKEY_TZ,
    canonical_url,
    clean,
    compact_title,
    hash_json,
    nearest_card,
    now_iso,
    parse_publication_date,
    replace_source_snapshot,
    request_with_retry,
)

BAD_PATH_BITS = (
    "/iletisim", "/kurumsal", "/baskan", "/meclis", "/galeri", "/video", "/arama",
    "privacy-policy", "sayfa=kirikkale",
)
DETAIL_DATE_MARKER = re.compile(
    r"(?:Eklenme|Yayınlanma|Yayimlanma|Yayımlanma|Yayimlanma|Haber|Oluşturulma|Olusturulma)\s+Tarihi\s*[:\-]?\s*([^|]{0,80})",
    re.IGNORECASE,
)


def load_sources():
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    defaults = payload.get("defaults") or {}
    rows = []
    for row in payload.get("sources", []):
        strategy = clean(row.get("adapter2_strategy"))
        if not strategy:
            continue
        rows.append({
            "source_id": clean(row.get("source_id")),
            "province": clean(row.get("province")),
            "name": clean(row.get("name")),
            "url": clean(row.get("url")),
            "strategy": strategy,
            "url_hints": tuple(clean(x) for x in (row.get("adapter2_url_hints") or [])),
            "max_age_days": int(row.get("max_age_days", defaults.get("max_age_days", 7))),
            "detail_fetch_limit": int(row.get("adapter2_detail_fetch_limit", 12)),
            "rights_status": clean(row.get("rights_status") or defaults.get("rights_status") or "reuse_needs_final_check"),
        })
    return rows


def same_host(a, b):
    return urlparse(a).netloc.casefold().removeprefix("www.") == urlparse(b).netloc.casefold().removeprefix("www.")


def plausible_detail(source, absolute):
    if not same_host(source["url"], absolute):
        return False
    low = absolute.casefold()
    if canonical_url(absolute) == canonical_url(source["url"]):
        return False
    if any(bit in low for bit in BAD_PATH_BITS):
        return False
    hints = source["url_hints"]
    if hints and not any(hint.casefold() in low for hint in hints):
        return False
    return True


def parse_wordpress_date(value):
    raw = clean(value)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TURKEY_TZ)
    return dt.astimezone(timezone.utc)


def add_candidate(by_url, source, title, absolute, published, date_source, *, allow_undated=False):
    title = compact_title(title)
    if len(title) < 18 or not plausible_detail(source, absolute):
        return
    if published is None and not allow_undated:
        return
    key = canonical_url(absolute)
    current = by_url.get(key)
    candidate = {
        "title": title,
        "url": absolute,
        "published": published,
        "date_source": date_source,
    }
    if current is None:
        by_url[key] = candidate
        return
    if current.get("published") is None and published is not None:
        by_url[key] = candidate
        return
    if (current.get("published") is None) == (published is None) and len(title) < len(current["title"]):
        by_url[key] = candidate


def extract_heading_links(source, html):
    soup = BeautifulSoup(html, "html.parser")
    by_url = {}
    reference = datetime.now(timezone.utc)
    for heading in soup.find_all(["h2", "h3", "h4", "h5", "h6"]):
        anchor = heading.find("a", href=True) or heading.find_parent("a", href=True)
        if not anchor:
            continue
        absolute = urljoin(source["url"], clean(anchor.get("href"))).split("#", 1)[0]
        if not plausible_detail(source, absolute):
            continue
        card = nearest_card(anchor)
        card_text = clean(card.get_text(" ", strip=True)) if card else clean(heading.get_text(" ", strip=True))
        published, kind = parse_publication_date(card_text, allow_relative=True, reference=reference)
        add_candidate(
            by_url,
            source,
            heading.get_text(" ", strip=True),
            absolute,
            published,
            f"adapter2_heading_{kind}" if kind else "adapter2_heading",
        )
    return list(by_url.values())


def extract_semantic_cards(source, html, *, allow_undated=False):
    soup = BeautifulSoup(html, "html.parser")
    by_url = {}
    reference = datetime.now(timezone.utc)
    for container in soup.find_all(["article", "li", "div"]):
        classes = " ".join(container.get("class") or []).casefold()
        if not any(token in classes for token in ("haber", "news", "post", "article", "card", "duyuru")):
            continue
        heading = container.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        anchor = None
        if heading:
            anchor = heading.find("a", href=True) or heading.find_parent("a", href=True)
        anchor = anchor or container.find("a", href=True)
        if not anchor:
            continue
        absolute = urljoin(source["url"], clean(anchor.get("href"))).split("#", 1)[0]
        if not plausible_detail(source, absolute):
            continue
        title = heading.get_text(" ", strip=True) if heading else anchor.get_text(" ", strip=True)
        published, kind = parse_publication_date(
            container.get_text(" ", strip=True), allow_relative=True, reference=reference
        )
        add_candidate(
            by_url,
            source,
            title,
            absolute,
            published,
            f"adapter2_semantic_{kind}" if kind else "adapter2_semantic",
            allow_undated=allow_undated,
        )
    return list(by_url.values())


def walk_jsonld_for_date(node):
    if isinstance(node, list):
        for item in node:
            found = walk_jsonld_for_date(item)
            if found:
                return found
        return None
    if not isinstance(node, dict):
        return None
    for key in ("datePublished", "dateCreated"):
        if node.get(key):
            parsed = parse_wordpress_date(node.get(key))
            if parsed:
                return parsed
    for value in node.values():
        if isinstance(value, (dict, list)):
            found = walk_jsonld_for_date(value)
            if found:
                return found
    return None


def fetch_guarded_detail_date(url):
    response = request_with_retry(url, attempts=2, read_timeout=20)
    soup = BeautifulSoup(response.text, "html.parser")

    for selector, attr in (
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ('meta[name="publish-date"]', "content"),
        ("time[datetime]", "datetime"),
    ):
        node = soup.select_one(selector)
        if node:
            parsed = parse_wordpress_date(node.get(attr))
            if parsed:
                return parsed, "adapter2_detail_semantic"

    for script in soup.find_all("script", type=lambda value: value and "ld+json" in str(value)):
        try:
            payload = json.loads(script.string or script.get_text())
        except Exception:
            continue
        parsed = walk_jsonld_for_date(payload)
        if parsed:
            return parsed, "adapter2_detail_jsonld"

    text = clean(soup.get_text(" ", strip=True))
    marker = DETAIL_DATE_MARKER.search(text[:7000])
    if marker:
        parsed, kind = parse_publication_date(marker.group(1), allow_relative=False)
        if parsed:
            return parsed, f"adapter2_detail_marker_{kind}"

    return None, None


def enrich_detail_dates(source, candidates):
    fetched = dated = errors = 0
    for item in candidates:
        if item.get("published") is not None:
            continue
        if fetched >= source["detail_fetch_limit"]:
            break
        fetched += 1
        try:
            published, date_source = fetch_guarded_detail_date(item["url"])
            if published:
                item["published"] = published
                item["date_source"] = date_source
                dated += 1
        except Exception as exc:
            errors += 1
            print(f"DETAIL ERROR {item['url']}: {type(exc).__name__}: {exc}")
    return fetched, dated, errors


def extract_wordpress_api(source):
    parsed = urlparse(source["url"])
    api_url = f"{parsed.scheme}://{parsed.netloc}/wp-json/wp/v2/posts?per_page=20&_fields=link,date,title"
    response = request_with_retry(api_url, attempts=3, read_timeout=20)
    payload = response.json()
    by_url = {}
    if not isinstance(payload, list):
        return []
    for item in payload:
        if not isinstance(item, dict):
            continue
        rendered = (item.get("title") or {}).get("rendered") or ""
        title = BeautifulSoup(rendered, "html.parser").get_text(" ", strip=True)
        absolute = clean(item.get("link"))
        published = parse_wordpress_date(item.get("date"))
        if absolute:
            add_candidate(by_url, source, title, absolute, published, "adapter2_wordpress_api")
    return list(by_url.values())


def collect(source):
    print(f"\n--- {source['province']} / {source['source_id']} / {source['strategy']} ---")
    strategy = source["strategy"]
    http_status = 200
    detail_fetched = detail_dated = detail_errors = 0
    if strategy == "wordpress_api":
        candidates = extract_wordpress_api(source)
    else:
        response = request_with_retry(source["url"], attempts=3, read_timeout=20)
        http_status = response.status_code
        if strategy == "heading_link":
            candidates = extract_heading_links(source, response.text)
        elif strategy == "semantic_card":
            candidates = extract_semantic_cards(source, response.text)
        elif strategy == "semantic_card_detail":
            candidates = extract_semantic_cards(source, response.text, allow_undated=True)
            detail_fetched, detail_dated, detail_errors = enrich_detail_dates(source, candidates)
            candidates = [item for item in candidates if item.get("published") is not None]
        else:
            raise ValueError(f"Unknown adapter2_strategy={strategy} for {source['source_id']}")

    reference = datetime.now(timezone.utc)
    cutoff = reference - timedelta(days=source["max_age_days"])
    fresh = stale = future_rejected = 0
    snapshot_rows = []
    for item in candidates:
        published = item["published"]
        if published > reference + MAX_FUTURE_PUBLICATION_SKEW:
            future_rejected += 1
            continue
        if published < cutoff:
            stale += 1
            continue
        fresh += 1
        row = {
            "collected_at": now_iso(),
            "source_id": source["source_id"],
            "source_name": source["name"],
            "province": source["province"],
            "source_type": "municipal_news",
            "rights_status": source["rights_status"],
            "image_rights_status": "reuse_needs_final_check",
            "url": item["url"],
            "http_status": http_status,
            "content_hash": hash_json({
                "source": source["source_id"],
                "url": canonical_url(item["url"]),
                "title": item["title"],
                "published_at": published.isoformat(),
            }),
            "title": item["title"],
            "published_at": published.isoformat(),
            "published_at_source": item["date_source"],
            "latitude": None,
            "longitude": None,
            "magnitude": None,
            "depth_km": None,
            "event_id": None,
            "image_url": None,
            "raw_summary": "municipal_news_adapter2 item",
        }
        snapshot_rows.append(row)

    changed, old_count, final_count = replace_source_snapshot(source["source_id"], snapshot_rows)
    print(
        f"parsed={len(candidates)} fresh={fresh} stale={stale} future_rejected={future_rejected} "
        f"snapshot={final_count} replaced_old={old_count} changed={int(changed)} "
        f"detail_fetched={detail_fetched} detail_dated={detail_dated} detail_errors={detail_errors}"
    )


def main():
    print("=== MUNICIPAL NEWS ADAPTER 2 COLLECTOR ===")
    print("Only validated per-source strategies are enabled. Images remain disabled.")
    print("TLS verification stays enabled; no access-control bypasses are used.")
    print("Detail-date fallback accepts only semantic metadata, JSON-LD, or explicit publication-date markers.")
    sources = load_sources()
    print(f"Adapter 2 sources: {len(sources)}")
    failures = 0
    for source in sources:
        try:
            collect(source)
        except Exception as exc:
            failures += 1
            print(f"ERROR {source['source_id']}: {type(exc).__name__}: {exc}")
    if sources and failures == len(sources):
        raise SystemExit("All Adapter 2 municipal sources failed")


if __name__ == "__main__":
    main()
