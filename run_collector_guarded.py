from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import collector

MAX_CONNECT_SECONDS = 4
MAX_READ_SECONDS = 8

_original_get = requests.get
_original_collect_municipal_feed = collector.collect_municipal_feed


def guarded_get(url, *args, **kwargs):
    requested_timeout = kwargs.get("timeout")
    kwargs["timeout"] = (MAX_CONNECT_SECONDS, MAX_READ_SECONDS)
    started = time.perf_counter()
    try:
        response = _original_get(url, *args, **kwargs)
        elapsed = time.perf_counter() - started
        print(f"HTTP {response.status_code} {elapsed:.2f}s {url} timeout_was={requested_timeout!r}", flush=True)
        return response
    except Exception as exc:
        elapsed = time.perf_counter() - started
        print(f"HTTP ERROR {elapsed:.2f}s {url} {type(exc).__name__}: {exc} timeout_was={requested_timeout!r}", flush=True)
        raise


def seen_urls(source_id):
    result = set()
    if not collector.OUT.exists():
        return result
    with collector.OUT.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("source_id") == source_id and row.get("url"):
                result.add(row["url"])
    return result


def collect_konya_events(source):
    collected_at = collector.now_iso()
    known = collector.seen_hashes(source["id"])
    now = datetime.now(timezone.utc)
    try:
        response = requests.get(source["url"], headers=collector.HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        events = []
        seen = set()
        for anchor in soup.select('a[href*="kultursanatkonya.com/etkinlikler/"]'):
            href = anchor.get("href")
            title = " ".join(anchor.get_text(" ", strip=True).split())
            if not href or not title:
                continue
            detail_url = urljoin(response.url, href)
            if detail_url in seen:
                continue
            container = anchor
            published_at = None
            category = None
            for _ in range(6):
                text = " ".join(container.get_text(" ", strip=True).split())
                published_at = collector.parse_date_tr(text)
                if published_at:
                    upper = text.upper()
                    for candidate in ("TİYATRO", "ETKİNLİK", "SERGİ", "KONSER", "SİNEMA", "SÖYLEŞİ"):
                        if candidate in upper:
                            category = candidate.casefold()
                            break
                    break
                if container.parent is None:
                    break
                container = container.parent
            if not published_at:
                continue
            start = datetime.fromisoformat(published_at)
            if not collector.event_is_eligible(source, start, None, now):
                continue
            seen.add(detail_url)
            events.append((title, start, category, detail_url))

        new_count = 0
        for title, start, category, detail_url in events:
            event_id = detail_url.rstrip("/").split("/")[-1]
            content_hash = collector.sha256_json({"id": event_id, "title": title, "start": start.isoformat(), "url": detail_url})
            if content_hash in known:
                continue
            row = collector.base_row(source, collected_at, response.status_code, content_hash, title, start.isoformat(), detail_url)
            row.update({"event_id": event_id, "event_start_at": start.isoformat(), "event_end_at": None, "event_category": category or "culture", "venue": None, "image_url": None, "raw_summary": "konya_official_event_html"})
            collector.append(row)
            known.add(content_hash)
            new_count += 1
            print("NEW KONYA EVENT", start.isoformat(), title, flush=True)
        print(f"Konya events parsed={len(events)} new={new_count}", flush=True)
    except Exception as exc:
        collector.error_row(source, exc)
        print("ERROR KONYA EVENTS", exc, flush=True)


def collect_municipal_feed_fast(source):
    if source.get("id") != "akom_istanbul_news":
        return _original_collect_municipal_feed(source)
    collected_at = collector.now_iso()
    known_hashes = collector.seen_hashes(source["id"])
    known_urls = seen_urls(source["id"])
    try:
        response = requests.get(source["url"], headers=collector.HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        discovered = []
        local_seen = set()
        for anchor in soup.select('a[href*="/haberler/"]'):
            href = anchor.get("href")
            if not href:
                continue
            article_url = urljoin(source["url"], href)
            if article_url in local_seen:
                continue
            local_seen.add(article_url)
            discovered.append((article_url, anchor))
        skipped_known = 0
        fetched = 0
        items = []
        for article_url, anchor in discovered:
            if article_url in known_urls:
                skipped_known += 1
                continue
            try:
                detail = requests.get(article_url, headers=collector.HEADERS, timeout=25)
                detail.raise_for_status()
                ds = BeautifulSoup(detail.text, "html.parser")
                heading = ds.find("h1") or ds.find("h2")
                title = " ".join((heading.get_text(" ", strip=True) if heading else anchor.get_text(" ", strip=True)).split())
                if title:
                    items.append((title, collector.parse_date_tr(ds.get_text(" ", strip=True)[:4000]), article_url))
                fetched += 1
            except Exception as exc:
                print("AKOM detail error", article_url, exc, flush=True)
            time.sleep(0.1)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        new_count = 0
        for title, published_at, article_url in items:
            if published_at:
                try:
                    if datetime.fromisoformat(published_at) < cutoff:
                        continue
                except ValueError:
                    pass
            content_hash = collector.sha256_json({"source": source["id"], "url": article_url, "title": title, "published_at": published_at})
            if content_hash in known_hashes:
                continue
            row = collector.base_row(source, collected_at, response.status_code, content_hash, title, published_at, article_url)
            row["raw_summary"] = "municipal_feed item"
            collector.append(row)
            known_hashes.add(content_hash)
            known_urls.add(article_url)
            new_count += 1
        print(f"AKOM discovered={len(discovered)} skipped_known={skipped_known} detail_fetched={fetched} new={new_count}", flush=True)
    except Exception as exc:
        collector.error_row(source, exc)
        print("ERROR MUNICIPAL", source["id"], exc, flush=True)


def run_source_with_label(source):
    province = source.get("province") or "NATIONAL"
    source_id = source.get("id") or "unknown"
    print(f"\n=== {province.upper()} | {source_id} ===", flush=True)
    mode = source.get("mode")
    if mode == "bursa_events":
        collector.collect_bursa_events(source)
    elif mode == "izmir_events":
        collector.collect_izmir_events(source)
    elif mode == "ankara_events":
        collector.collect_ankara_events(source)
    elif mode == "konya_events":
        collect_konya_events(source)
    elif mode == "afad_events":
        collector.collect_afad_events(source)
    elif mode == "municipal_feed":
        collector.collect_municipal_feed(source)
    else:
        print("SKIP unsupported mode", source_id, mode, flush=True)


def guarded_main():
    enabled = [source for source in collector.load_manifest()["sources"] if source.get("enabled")]
    print(f"Probing {len(enabled)} enabled sources", flush=True)
    for source in enabled:
        run_source_with_label(source)
        time.sleep(0.25)


def main():
    requests.get = guarded_get
    collector.collect_municipal_feed = collect_municipal_feed_fast
    collector.main = guarded_main
    started = time.perf_counter()
    try:
        collector.main()
    finally:
        print(f"\nCOLLECTOR TOTAL {time.perf_counter() - started:.2f}s", flush=True)


if __name__ == "__main__":
    main()
