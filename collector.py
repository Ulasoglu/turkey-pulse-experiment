from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "sources.json"
OUT = ROOT / "data" / "raw_signals.jsonl"
HEADERS = {"User-Agent": "TurkeyPulseFeasibilityExperiment/0.6 (+non-commercial feasibility probe)"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sha256_json(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def seen_hashes(source_id):
    result = set()
    if not OUT.exists():
        return result
    with OUT.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("source_id") == source_id and row.get("content_hash"):
                result.add(row["content_hash"])
    return result


def append(row):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def base_row(source, collected_at, status, content_hash, title, published_at, url=None):
    return {
        "collected_at": collected_at,
        "source_id": source["id"],
        "province": source["province"],
        "source_type": source["source_type"],
        "rights_status": source["rights_status"],
        "url": url or source["url"],
        "http_status": status,
        "content_hash": content_hash,
        "title": title,
        "published_at": published_at,
        "latitude": None,
        "longitude": None,
        "magnitude": None,
        "depth_km": None,
        "event_id": None,
    }


def error_row(source, exc):
    row = base_row(source, now_iso(), None, None, None, None)
    row["raw_summary"] = f"ERROR: {type(exc).__name__}: {exc}"
    append(row)


def parse_bursa_date(value):
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def parse_izmir_date(value):
    if not value:
        return None
    raw = str(value).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=3)))
    return dt.astimezone(timezone.utc)


def collect_bursa_events(source):
    collected_at = now_iso()
    known = seen_hashes(source["id"])
    try:
        r = requests.get(source["url"], headers=HEADERS, timeout=30)
        r.raise_for_status()
        records = r.json()
        if not isinstance(records, list):
            raise ValueError("Bursa events response is not a JSON list")
        now = datetime.now(timezone.utc)
        active_lookback = now - timedelta(days=7)
        new_count = eligible = stale_skipped = 0
        for item in records:
            if not isinstance(item, dict):
                continue
            title = str(item.get("adi") or "").strip()
            start = parse_bursa_date(item.get("tarih_baslama"))
            end = parse_bursa_date(item.get("tarih_bitis"))
            relevant_end = end or start
            if not title or not start or not relevant_end:
                continue
            is_future = start >= now
            is_recently_active = active_lookback <= start < now and relevant_end >= now
            if not (is_future or is_recently_active):
                stale_skipped += 1
                continue
            eligible += 1
            identity = {"id": item.get("id"), "title": title, "start": item.get("tarih_baslama"), "end": item.get("tarih_bitis"), "venue": item.get("mekan") or item.get("diger_mekan")}
            content_hash = sha256_json(identity)
            if content_hash in known:
                continue
            row = base_row(source, collected_at, r.status_code, content_hash, title, start.isoformat(), item.get("link") or source["url"])
            row.update({"event_id": item.get("id"), "event_start_at": start.isoformat(), "event_end_at": end.isoformat() if end else None, "event_category": item.get("kategori"), "venue": item.get("mekan") or item.get("diger_mekan"), "image_url": item.get("foto_url"), "raw_summary": "bursa_open_data_event", "raw_event": item})
            append(row); known.add(content_hash); new_count += 1
            print("NEW BURSA EVENT", start.isoformat(), title)
        print(f"Bursa events returned: {len(records)} eligible={eligible} stale_skipped={stale_skipped} new={new_count}")
    except Exception as exc:
        error_row(source, exc); print("ERROR BURSA EVENTS", exc)


def collect_izmir_events(source):
    collected_at = now_iso()
    known = seen_hashes(source["id"])
    try:
        r = requests.get(source["url"], headers=HEADERS, timeout=30)
        r.raise_for_status()
        records = r.json()
        if not isinstance(records, list):
            raise ValueError("Izmir events response is not a JSON list")
        now = datetime.now(timezone.utc)
        active_lookback = now - timedelta(days=7)
        eligible = stale_skipped = new_count = 0
        for item in records:
            if not isinstance(item, dict):
                continue
            title = str(item.get("Adi") or "").strip()
            start = parse_izmir_date(item.get("EtkinlikBaslamaTarihi"))
            end = parse_izmir_date(item.get("EtkinlikBitisTarihi")) or start
            if not title or not start or not end:
                continue
            is_future = start >= now
            is_recently_active = active_lookback <= start < now and end >= now
            if not (is_future or is_recently_active):
                stale_skipped += 1
                continue
            eligible += 1
            identity = {"id": item.get("Id"), "title": title, "start": item.get("EtkinlikBaslamaTarihi"), "end": item.get("EtkinlikBitisTarihi"), "venue": item.get("EtkinlikMerkezi")}
            content_hash = sha256_json(identity)
            if content_hash in known:
                continue
            row = base_row(source, collected_at, r.status_code, content_hash, title, start.isoformat(), source["url"])
            row.update({"event_id": item.get("Id"), "event_start_at": start.isoformat(), "event_end_at": end.isoformat(), "event_category": item.get("Tur"), "venue": item.get("EtkinlikMerkezi"), "image_url": item.get("Resim") or item.get("KucukAfis"), "is_free": item.get("UcretsizMi"), "ticket_url": item.get("BiletSatisLinki"), "event_slug": item.get("EtkinlikUrl"), "raw_summary": "izmir_open_data_event", "raw_event": item})
            append(row); known.add(content_hash); new_count += 1
            print("NEW IZMIR EVENT", start.isoformat(), title)
        print(f"Izmir events returned: {len(records)} eligible={eligible} stale_skipped={stale_skipped} new={new_count}")
    except Exception as exc:
        error_row(source, exc); print("ERROR IZMIR EVENTS", exc)


def collect_afad_events(source):
    collected_at = now_iso(); known = seen_hashes(source["id"])
    end_time = datetime.now(timezone.utc); start_time = end_time - timedelta(hours=24)
    params = {"start": start_time.strftime("%Y-%m-%dT%H:%M:%S"), "end": end_time.strftime("%Y-%m-%dT%H:%M:%S"), "orderby": "timedesc", "limit": 500, "format": "json"}
    try:
        r = requests.get(source["url"], params=params, headers=HEADERS, timeout=30); r.raise_for_status(); events = r.json()
        if not isinstance(events, list): raise ValueError("AFAD response is not a JSON list")
        print(f"AFAD returned {len(events)} events"); new_count = 0
        for event in events:
            identity = {k: event.get(k) for k in ("eventID", "date", "latitude", "longitude", "magnitude", "location")}; content_hash = sha256_json(identity)
            if content_hash in known: continue
            magnitude = event.get("magnitude"); location = event.get("location"); magnitude_type = event.get("type")
            title = " - ".join(x for x in [f"{magnitude_type or 'M'} {magnitude}" if magnitude is not None else None, location] if x) or "AFAD earthquake event"
            row = base_row(source, collected_at, r.status_code, content_hash, title, event.get("date"))
            row.update({"province": event.get("province") or "UNKNOWN", "latitude": event.get("latitude"), "longitude": event.get("longitude"), "magnitude": magnitude, "magnitude_type": magnitude_type, "depth_km": event.get("depth"), "event_id": event.get("eventID"), "raw_summary": "; ".join(x for x in [f"province={event.get('province')}" if event.get("province") else None, f"district={event.get('district')}" if event.get("district") else None, f"depth_km={event.get('depth')}" if event.get("depth") is not None else None] if x), "raw_event": event})
            append(row); known.add(content_hash); new_count += 1
        print(f"AFAD new events written: {new_count}")
    except Exception as exc:
        error_row(source, exc); print("ERROR AFAD", exc)


def parse_date_tr(value):
    text = " ".join(str(value or "").split()); months = {"ocak":1,"şubat":2,"mart":3,"nisan":4,"mayıs":5,"haziran":6,"temmuz":7,"ağustos":8,"eylül":9,"ekim":10,"kasım":11,"aralık":12}
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text)
    if m:
        try: return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc).isoformat()
        except ValueError: return None
    m = re.search(r"\b(\d{1,2})\s+([a-zçğıöşü]+)\s+(\d{4})\b", text.casefold())
    if m and months.get(m.group(2)):
        try: return datetime(int(m.group(3)), months[m.group(2)], int(m.group(1)), tzinfo=timezone.utc).isoformat()
        except ValueError: return None
    return None


def collect_municipal_feed(source):
    collected_at = now_iso(); known = seen_hashes(source["id"])
    try:
        r = requests.get(source["url"], headers=HEADERS, timeout=30); r.raise_for_status(); soup = BeautifulSoup(r.text, "html.parser"); items = []
        if source["id"] == "akom_istanbul_news":
            urls = set()
            for a in soup.select('a[href*="/haberler/"]'):
                href = a.get("href")
                if not href: continue
                article_url = urljoin(source["url"], href)
                if article_url in urls: continue
                urls.add(article_url)
                try:
                    detail = requests.get(article_url, headers=HEADERS, timeout=25); detail.raise_for_status(); ds = BeautifulSoup(detail.text, "html.parser"); heading = ds.find("h1") or ds.find("h2")
                    title = " ".join((heading.get_text(" ", strip=True) if heading else a.get_text(" ", strip=True)).split())
                    if title: items.append((title, parse_date_tr(ds.get_text(" ", strip=True)[:4000]), article_url))
                except Exception as exc: print("AKOM detail error", article_url, exc)
                time.sleep(0.25)
        elif source["id"] == "izmir_bb_news":
            urls = set()
            for a in soup.select('a[href*="/tr/Haberler/"]'):
                href = a.get("href")
                if not href: continue
                article_url = urljoin(source["url"], href)
                if article_url in urls: continue
                container = a
                for _ in range(6):
                    if container.parent is None: break
                    container = container.parent
                    if parse_date_tr(container.get_text(" ", strip=True)): break
                heading = container.find(["h1", "h2", "h3", "h4"]); title = " ".join((heading.get_text(" ", strip=True) if heading else a.get_text(" ", strip=True)).split())
                if not title or title.casefold() in {"detaya git", "detay"}: continue
                urls.add(article_url); items.append((title, parse_date_tr(container.get_text(" ", strip=True)), article_url))
        else: raise ValueError(f"Unsupported municipal source: {source['id']}")
        cutoff = datetime.now(timezone.utc) - timedelta(days=7); new_count = 0
        for title, published_at, article_url in items:
            if published_at:
                try:
                    if datetime.fromisoformat(published_at) < cutoff: continue
                except ValueError: pass
            content_hash = sha256_json({"source": source["id"], "url": article_url, "title": title, "published_at": published_at})
            if content_hash in known: continue
            row = base_row(source, collected_at, r.status_code, content_hash, title, published_at, article_url); row["raw_summary"] = "municipal_feed item"
            append(row); known.add(content_hash); new_count += 1
        print(f"{source['id']} parsed={len(items)} new={new_count}")
    except Exception as exc:
        error_row(source, exc); print("ERROR MUNICIPAL", source["id"], exc)


def main():
    enabled = [s for s in load_manifest()["sources"] if s.get("enabled")]
    print(f"Probing {len(enabled)} enabled sources")
    for source in enabled:
        mode = source.get("mode")
        if mode == "bursa_events": collect_bursa_events(source)
        elif mode == "izmir_events": collect_izmir_events(source)
        elif mode == "afad_events": collect_afad_events(source)
        elif mode == "municipal_feed": collect_municipal_feed(source)
        else: print("SKIP unsupported mode", source["id"], mode)
        time.sleep(1)


if __name__ == "__main__":
    main()
