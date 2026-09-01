from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

INPUT = Path("data/map_signals.jsonl")
OUTPUT = Path("web/data/feed.json")

HARD_DROP_PREFIXES = (
    "collector_error",
    "municipal_source_paused",
    "freshness_news_too_old",
    "freshness_news_future_timestamp",
    "freshness_event_missing_start",
    "freshness_event_stale_start",
    "freshness_event_ended",
    "legacy_page_watch_not_event",
    "afad_non_event_record",
    "afad_missing_magnitude",
    "earthquake_below_m3",
    "missing_title",
    "generic_navigation_title",
    "likely_pr:",
    "retrospective:",
    "past_event_announcement",
    "duplicate_title_same_source_date",
)


def text(value):
    return str(value or "").strip()


def normalize_title(value):
    raw = text(value).translate(str.maketrans({"I": "i", "İ": "i", "ı": "i"})).casefold()
    raw = re.sub(r"[^\w\s]", " ", raw, flags=re.UNICODE)
    return " ".join(raw.split())


def valid_http_url(value):
    raw = text(value)
    return raw if raw.startswith(("http://", "https://")) else None


def stable_id(row):
    for key in ("event_id", "content_hash"):
        value = text(row.get(key))
        if value:
            return f"feed_{value}"
    raw = "|".join(
        [
            text(row.get("source_id")),
            text(row.get("url")),
            text(row.get("title")),
            text(row.get("published_at")),
        ]
    )
    return "feed_" + hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def human_source_url(row):
    source_id = text(row.get("source_id"))
    raw_url = valid_http_url(row.get("url"))
    event_id = text(row.get("event_id"))

    if source_id == "afad_event_service":
        return f"https://deprem.afad.gov.tr/event-detail/{event_id}" if event_id else "https://deprem.afad.gov.tr/"
    if source_id == "bursa_open_data_events":
        return raw_url if raw_url and "/etkinlik/" in raw_url else "https://www.bursa.bel.tr/etkinlik"
    if source_id == "izmir_open_data_events":
        if raw_url and "openapi.izmir.bel.tr" not in raw_url:
            return raw_url
        return "https://kultursanat.izmir.bel.tr/"
    return raw_url


def is_news_like(row):
    source_type = text(row.get("source_type"))
    source_id = text(row.get("source_id"))
    return (
        source_type == "municipal_news"
        or source_id.endswith(("_news", "_duyurular"))
        or source_id in {"akom_istanbul_news", "izmir_bb_news", "istanbul_ibb_news"}
    )


def include_row(row):
    title = text(row.get("title"))
    if not title:
        return False

    freshness = text(row.get("signal_freshness"))
    if freshness not in {"NOW", "RECENT"}:
        return False

    reason = text(row.get("filter_reason"))
    if any(reason.startswith(prefix) for prefix in HARD_DROP_PREFIXES):
        return False

    decision = text(row.get("filter_decision"))
    source_id = text(row.get("source_id"))

    # Keep strict thresholds for earthquakes/weather. The broader feed should
    # not become a stream of tiny AFAD events or model noise.
    if source_id in {"afad_event_service", "ecmwf_open_data_weather"}:
        return text(row.get("map_decision")) == "SHOW"

    if decision in {"KEEP", "MAYBE"}:
        return True

    # Real/current municipal news that is simply too small for a map marker is
    # still useful inside the province feed.
    if is_news_like(row) and reason == "municipal_low_impact":
        return True

    return False


def normalized_category(row):
    category = text(row.get("signal_category")) or "OTHER"
    if category == "UTILITY":
        return "INFRASTRUCTURE"
    return category


def to_item(row):
    return {
        "id": stable_id(row),
        "province": row.get("province"),
        "category": normalized_category(row),
        "title": text(row.get("title")) or "Gelişme",
        "relevance": text(row.get("signal_relevance")) or "MEDIUM",
        "freshness": text(row.get("signal_freshness")) or "RECENT",
        "published_at": row.get("published_at"),
        "source_id": row.get("source_id"),
        "source_name": row.get("source_name"),
        "source_url": human_source_url(row),
        "rights_status": row.get("rights_status"),
        "image_rights_status": row.get("image_rights_status", "reuse_needs_final_check"),
        "image_url": None,
        "venue": row.get("venue"),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "signal_count": 1,
        "source_count": 1,
        "magnitude": row.get("magnitude"),
        "depth_km": row.get("depth_km"),
        "feed_tier": "local" if text(row.get("filter_reason")) == "municipal_low_impact" else "curated",
        "filter_reason": row.get("filter_reason"),
    }


def story_key(item):
    # Same source + province + normalized headline is one feed story even when
    # a collector snapshot contains several dated occurrences of the same event.
    # Example: Konya event 1253 (ÜÇ HAREM) appeared once per day with the same
    # event identity. Showing all of them is duplicate UI, not extra information.
    return (
        text(item.get("source_id")),
        text(item.get("province")),
        normalize_title(item.get("title")),
    )


def item_rank(item):
    # Prefer curated metadata when the same story exists in more than one form,
    # then prefer the newest timestamp.
    tier = 1 if item.get("feed_tier") == "curated" else 0
    return (tier, text(item.get("published_at")))


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    bad = 0

    if INPUT.exists():
        with INPUT.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                if include_row(row):
                    rows.append(to_item(row))

    unique = {}
    duplicate_rows = 0
    for item in rows:
        key = story_key(item)
        existing = unique.get(key)
        if existing is None:
            unique[key] = item
            continue
        duplicate_rows += 1
        if item_rank(item) > item_rank(existing):
            unique[key] = item

    items = list(unique.values())
    items.sort(key=lambda item: text(item.get("published_at")), reverse=True)
    OUTPUT.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    province_count = len({text(item.get("province")) for item in items if text(item.get("province"))})
    curated = sum(1 for item in items if item.get("feed_tier") == "curated")
    local = sum(1 for item in items if item.get("feed_tier") == "local")
    print("\n=== TURKEY PULSE PROVINCE FEED EXPORT ===")
    print(f"INPUT:      {INPUT}")
    print(f"OUTPUT:     {len(items)}")
    print(f"PROVINCES:  {province_count}")
    print(f"CURATED:    {curated}")
    print(f"LOCAL NEWS: {local}")
    print(f"DEDUPED:    {duplicate_rows}")
    print(f"BAD JSON:   {bad}")
    print(f"Wrote: {OUTPUT}")


if __name__ == "__main__":
    main()
