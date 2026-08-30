from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "sources.json"
OUT = ROOT / "data" / "raw_signals.jsonl"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/0.9 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}
TURKEY_TZ = timezone(timedelta(hours=3))


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


def extract_page_image(soup, page_url):
    candidates = []
    for attrs in (
        {"property": "og:image"},
        {"property": "og:image:url"},
        {"name": "twitter:image"},
        {"name": "twitter:image:src"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            candidates.append(tag.get("content"))
    if not candidates:
        image = soup.find("img")
        if image:
            candidates.append(image.get("src") or image.get("data-src"))
    for candidate in candidates:
        if not candidate:
            continue
        absolute = urljoin(page_url, str(candidate).strip())
        if absolute.startswith(("http://", "https://")):
            return absolute
    return None


def event_policy(source):
    policy = source.get("freshness_policy") or {}
    return int(policy.get("max_started_days", 7)), bool(policy.get("require_not_ended", True))


def event_is_eligible(source, start, end, now):
    max_started_days, require_not_ended = event_policy(source)
    if start >= now:
        return True
    if start < now - timedelta(days=max_started_days):
        return False
    if require_not_ended and (end or start) < now:
        return False
    return True


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
        dt = dt.replace(tzinfo=TURKEY_TZ)
    return dt.astimezone(timezone.utc)


def parse_ankara_date(value, time_value=None):
    if not value:
        return None
    try:
        day, month, year = [int(x) for x in str(value).strip().split(".")]
        hour = minute = 0
        if time_value:
            hour, minute = [int(x) for x in str(time_value).strip().split(":")]
        return datetime(year, month, day, hour, minute, tzinfo=TURKEY_TZ).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


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
        new_count = eligible = stale_skipped = 0
        for item in records:
            if not isinstance(item, dict):
                continue
            title = str(item.get("adi") or "").strip()
            start = parse_bursa_date(item.get("tarih_baslama"))
            end = parse_bursa_date(item.get("tarih_bitis"))
            if not title or not start:
                continue
            if not event_is_eligible(source, start, end, now):
                stale_skipped += 1
                continue
            eligible += 1
            identity = {"id": item.get("id"), "title": title, "start": item.get("tarih_baslama"), "end": item.get("tarih_bitis"), "venue": item.get("mekan") or item.get("diger_mekan")}
            content_hash = sha256_json(identity)
            if content_hash in known:
                continue
            row = base_row(source, collected_at, r.status_code, content_hash, title, start.isoformat(), item.get("link") or source["url"])
            row.update({"event_id": item.get("id"), "event_start_at": start.isoformat(), "event_end_at": end.isoformat() if end else None, "event_category": item.get("kategori"), "venue": item.get("mekan") or item.get("diger_mekan"), "image_url": item.get("foto_url"), "raw_summary": "bursa_open_data_event", "raw_event": item})
            append(row)
            known.add(content_hash)
            new_count += 1
            print("NEW BURSA EVENT", start.isoformat(), title)
        print(f"Bursa events returned: {len(records)} eligible={eligible} stale_skipped={stale_skipped} new={new_count}")
    except Exception as exc:
        error_row(source, exc)
        print("ERROR BURSA EVENTS", exc)


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
        eligible = stale_skipped = new_count = 0
        for item in records:
            if not isinstance(item, dict):
                continue
            title = str(item.get("Adi") or "").strip()
            start = parse_izmir_date(item.get("EtkinlikBaslamaTarihi"))
            end = parse_izmir_date(item.get("EtkinlikBitisTarihi")) or start
            if not title or not start:
                continue
            if not event_is_eligible(source, start, end, now):
                stale_skipped += 1
                continue
            eligible += 1
            identity = {"id": item.get("Id"), "title": title, "start": item.get("EtkinlikBaslamaTarihi"), "end": item.get("EtkinlikBitisTarihi"), "venue": item.get("EtkinlikMerkezi")}
            content_hash = sha256_json(identity)
            if content_hash in known:
                continue
            row = base_row(source, collected_at, r.status_code, content_hash, title, start.isoformat(), source["url"])
            row.update({"event_id": item.get("Id"), "event_start_at": start.isoformat(), "event_end_at": end.isoformat(), "event_category": item.get("Tur"), "venue": item.get("EtkinlikMerkezi"), "image_url": item.get("Resim") or item.get("KucukAfis"), "is_free": item.get("UcretsizMi"), "ticket_url": item.get("BiletSatisLinki"), "event_slug": item.get("EtkinlikUrl"), "raw_summary": "izmir_open_data_event", "raw_event": item})
            append(row)
            known.add(content_hash)
            new_count += 1
            print("NEW IZMIR EVENT", start.isoformat(), title)
        print(f"Izmir events returned: {len(records)} eligible={eligible} stale_skipped={stale_skipped} new={new_count}")
    except Exception as exc:
        error_row(source, exc)
        print("ERROR IZMIR EVENTS", exc)


def ankara_event_links(source):
    links = []
    seen = set()
    discovery_urls = source.get("discovery_urls") or [source["url"]]
    for discovery_url in discovery_urls:
        try:
            r = requests.get(discovery_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select('a[href*="/event/"]'):
                href = a.get("href")
                if not href:
                    continue
                absolute = urljoin(r.url, href)
                if urlparse(absolute).netloc != urlparse(source["url"]).netloc:
                    continue
                if absolute in seen:
                    continue
                seen.add(absolute)
                links.append(absolute)
        except Exception as exc:
            print("ANKARA discovery error", discovery_url, exc)
    return links


def nearby_text_elements(soup):
    return soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "div", "span", "time"])


def extract_ankara_event(detail_url):
    r = requests.get(detail_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()

    heading = soup.find("h1") or soup.find("h2")
    title = " ".join((heading.get_text(" ", strip=True) if heading else (soup.title.get_text(" ", strip=True) if soup.title else "")).split())
    title = re.sub(r"\s*\|\|.*$", "", title).strip()
    if not title:
        return None

    elements = nearby_text_elements(soup)
    heading_index = 0
    if heading is not None:
        for i, element in enumerate(elements):
            if element is heading:
                heading_index = i
                break

    date_candidates = []
    for i in range(heading_index, min(len(elements), heading_index + 140)):
        element = elements[i]
        value = " ".join(element.get_text(" ", strip=True).split())
        if not value or len(value) > 700:
            continue
        tokens = re.findall(r"\b\d{2}\.\d{2}\.20\d{2}\b", value)
        if not tokens:
            continue
        classes = " ".join(element.get("class") or []).casefold()
        ident = str(element.get("id") or "").casefold()
        signal_bonus = 0
        if any(x in classes or x in ident for x in ["date", "tarih", "event", "detail", "info", "time"]):
            signal_bonus = 50
        distance = i - heading_index
        for token in tokens:
            date_candidates.append((signal_bonus - distance, i, token, value))

    if not date_candidates:
        return None

    date_candidates.sort(key=lambda item: (-item[0], item[1]))
    _, chosen_index, chosen_date, chosen_text = date_candidates[0]

    nearby = []
    for i in range(max(heading_index, chosen_index - 8), min(len(elements), chosen_index + 14)):
        value = " ".join(elements[i].get_text(" ", strip=True).split())
        if value and len(value) <= 500:
            nearby.append(value)
    context = " | ".join(nearby)

    time_match = re.search(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", context)
    time_value = time_match.group(0) if time_match else None
    start = parse_ankara_date(chosen_date, time_value)
    if start is None:
        return None

    same_text_dates = re.findall(r"\b\d{2}\.\d{2}\.20\d{2}\b", chosen_text)
    end = None
    if len(same_text_dates) >= 2:
        end = parse_ankara_date(same_text_dates[1], time_value)

    venue = None
    venue_patterns = [
        r"(?:mekan|mekân|yer|lokasyon|adres)\s*[:\-]\s*([^|]{3,180})",
        r"(?:etkinlik merkezi)\s*[:\-]\s*([^|]{3,180})",
    ]
    for pattern in venue_patterns:
        match = re.search(pattern, context, flags=re.I)
        if match:
            venue = " ".join(match.group(1).split()).strip()
            break

    slug = detail_url.rstrip("/").split("/")[-1]
    image = extract_page_image(soup, detail_url)

    return {
        "title": title,
        "start": start,
        "end": end,
        "venue": venue,
        "event_id": slug,
        "image_url": image,
        "detail_url": detail_url,
        "parser_context": context[:1200],
        "http_status": r.status_code,
    }


def collect_ankara_events(source):
    collected_at = now_iso()
    known = seen_hashes(source["id"])
    now = datetime.now(timezone.utc)
    links = ankara_event_links(source)
    parsed = eligible = stale_skipped = ambiguous = new_count = 0
    for link in links:
        try:
            event = extract_ankara_event(link)
            if not event:
                ambiguous += 1
                print("ANKARA parser skipped", link)
                continue
            parsed += 1
            start = event["start"]
            end = event["end"]
            print("ANKARA parsed", start.isoformat(), event["title"], "venue=", event.get("venue"))
            if not event_is_eligible(source, start, end, now):
                stale_skipped += 1
                continue
            eligible += 1
            identity = {"id": event["event_id"], "title": event["title"], "start": start.isoformat(), "end": end.isoformat() if end else None, "venue": event.get("venue")}
            content_hash = sha256_json(identity)
            if content_hash in known:
                continue
            row = base_row(source, collected_at, event["http_status"], content_hash, event["title"], start.isoformat(), event["detail_url"])
            row.update({
                "event_id": event["event_id"],
                "event_start_at": start.isoformat(),
                "event_end_at": end.isoformat() if end else None,
                "event_category": "culture",
                "venue": event.get("venue"),
                "image_url": event.get("image_url"),
                "raw_summary": "ankara_official_event_html",
                "parser_context": event.get("parser_context"),
            })
            append(row)
            known.add(content_hash)
            new_count += 1
            print("NEW ANKARA EVENT", start.isoformat(), event["title"])
        except Exception as exc:
            print("ANKARA detail error", link, exc)
        time.sleep(0.2)
    print(f"Ankara event links={len(links)} parsed={parsed} eligible={eligible} stale_skipped={stale_skipped} ambiguous={ambiguous} new={new_count}")


def collect_afad_events(source):
    collected_at = now_iso()
    known = seen_hashes(source["id"])
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=24)
    params = {"start": start_time.strftime("%Y-%m-%dT%H:%M:%S"), "end": end_time.strftime("%Y-%m-%dT%H:%M:%S"), "orderby": "timedesc", "limit": 500, "format": "json"}
    try:
        r = requests.get(source["url"], params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        events = r.json()
        if not isinstance(events, list):
            raise ValueError("AFAD response is not a JSON list")
        print(f"AFAD returned {len(events)} events")
        new_count = 0
        for event in events:
            identity = {k: event.get(k) for k in ("eventID", "date", "latitude", "longitude", "magnitude", "location")}
            content_hash = sha256_json(identity)
            if content_hash in known:
                continue
            magnitude = event.get("magnitude")
            location = event.get("location")
            magnitude_type = event.get("type")
            title = " - ".join(x for x in [f"{magnitude_type or 'M'} {magnitude}" if magnitude is not None else None, location] if x) or "AFAD earthquake event"
            row = base_row(source, collected_at, r.status_code, content_hash, title, event.get("date"))
            row.update({"province": event.get("province") or "UNKNOWN", "latitude": event.get("latitude"), "longitude": event.get("longitude"), "magnitude": magnitude, "magnitude_type": magnitude_type, "depth_km": event.get("depth"), "event_id": event.get("eventID"), "raw_summary": "; ".join(x for x in [f"province={event.get('province')}" if event.get("province") else None, f"district={event.get('district')}" if event.get("district") else None, f"depth_km={event.get('depth')}" if event.get("depth") is not None else None] if x), "raw_event": event})
            append(row)
            known.add(content_hash)
            new_count += 1
        print(f"AFAD new events written: {new_count}")
    except Exception as exc:
        error_row(source, exc)
        print("ERROR AFAD", exc)


def parse_date_tr(value):
    text = " ".join(str(value or "").split())
    months = {"ocak":1,"şubat":2,"mart":3,"nisan":4,"mayıs":5,"haziran":6,"temmuz":7,"ağustos":8,"eylül":9,"ekim":10,"kasım":11,"aralık":12}
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc).isoformat()
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})\s+([a-zçğıöşü]+)\s+(\d{4})\b", text.casefold())
    if m and months.get(m.group(2)):
        try:
            return datetime(int(m.group(3)), months[m.group(2)], int(m.group(1)), tzinfo=timezone.utc).isoformat()
        except ValueError:
            return None
    return None


def collect_municipal_feed(source):
    collected_at = now_iso()
    known = seen_hashes(source["id"])
    try:
        r = requests.get(source["url"], headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        items = []
        if source["id"] == "akom_istanbul_news":
            urls = set()
            for a in soup.select('a[href*="/haberler/"]'):
                href = a.get("href")
                if not href:
                    continue
                article_url = urljoin(source["url"], href)
                if article_url in urls:
                    continue
                urls.add(article_url)
                try:
                    detail = requests.get(article_url, headers=HEADERS, timeout=25)
                    detail.raise_for_status()
                    ds = BeautifulSoup(detail.text, "html.parser")
                    heading = ds.find("h1") or ds.find("h2")
                    title = " ".join((heading.get_text(" ", strip=True) if heading else a.get_text(" ", strip=True)).split())
                    if title:
                        items.append((title, parse_date_tr(ds.get_text(" ", strip=True)[:4000]), article_url, extract_page_image(ds, article_url)))
                except Exception as exc:
                    print("AKOM detail error", article_url, exc)
                time.sleep(0.25)
        elif source["id"] == "izmir_bb_news":
            urls = set()
            for a in soup.select('a[href*="/tr/Haberler/"]'):
                href = a.get("href")
                if not href:
                    continue
                article_url = urljoin(source["url"], href)
                if article_url in urls:
                    continue
                container = a
                for _ in range(6):
                    if container.parent is None:
                        break
                    container = container.parent
                    if parse_date_tr(container.get_text(" ", strip=True)):
                        break
                heading = container.find(["h1", "h2", "h3", "h4"])
                title = " ".join((heading.get_text(" ", strip=True) if heading else a.get_text(" ", strip=True)).split())
                if not title or title.casefold() in {"detaya git", "detay"}:
                    continue
                urls.add(article_url)
                image_url = None
                try:
                    detail = requests.get(article_url, headers=HEADERS, timeout=25)
                    detail.raise_for_status()
                    ds = BeautifulSoup(detail.text, "html.parser")
                    image_url = extract_page_image(ds, article_url)
                except Exception as exc:
                    print("IZMIR detail image error", article_url, exc)
                items.append((title, parse_date_tr(container.get_text(" ", strip=True)), article_url, image_url))
        else:
            raise ValueError(f"Unsupported municipal source: {source['id']}")
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        new_count = 0
        for title, published_at, article_url, image_url in items:
            if published_at:
                try:
                    if datetime.fromisoformat(published_at) < cutoff:
                        continue
                except ValueError:
                    pass
            content_hash = sha256_json({"source": source["id"], "url": article_url, "title": title, "published_at": published_at})
            if content_hash in known:
                continue
            row = base_row(source, collected_at, r.status_code, content_hash, title, published_at, article_url)
            row["image_url"] = image_url
            row["image_rights_status"] = source.get("rights_status")
            row["raw_summary"] = "municipal_feed item"
            append(row)
            known.add(content_hash)
            new_count += 1
        print(f"{source['id']} parsed={len(items)} new={new_count}")
    except Exception as exc:
        error_row(source, exc)
        print("ERROR MUNICIPAL", source["id"], exc)


def main():
    enabled = [s for s in load_manifest()["sources"] if s.get("enabled")]
    print(f"Probing {len(enabled)} enabled sources")
    for source in enabled:
        mode = source.get("mode")
        if mode == "bursa_events":
            collect_bursa_events(source)
        elif mode == "izmir_events":
            collect_izmir_events(source)
        elif mode == "ankara_events":
            collect_ankara_events(source)
        elif mode == "afad_events":
            collect_afad_events(source)
        elif mode == "municipal_feed":
            collect_municipal_feed(source)
        else:
            print("SKIP unsupported mode", source["id"], mode)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
