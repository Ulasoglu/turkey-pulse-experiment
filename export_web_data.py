import json
from pathlib import Path

INPUT = Path("data/clustered_events.jsonl")
OUTPUT = Path("web/data/signals.json")
SOURCES = Path("sources.json")


def load_source_policy():
    if not SOURCES.exists():
        return {}
    try:
        manifest = json.loads(SOURCES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {source.get("id"): source for source in manifest.get("sources", []) if source.get("id")}


def safe_image_url(row, source_policy):
    image_url = row.get("image_url")
    source_id = row.get("representative_source_id")
    policy = source_policy.get(source_id, {})
    image_rights = policy.get("image_rights_status", "reuse_needs_final_check")
    if not image_url:
        return None
    if image_rights != "open_license_verified":
        return None
    if not str(image_url).startswith(("http://", "https://")):
        return None
    return image_url


def first_event_id(row):
    ids = row.get("member_event_ids") or []
    for value in ids:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def human_source_url(row):
    """Return a public, human-readable source page instead of raw API output."""
    source_id = row.get("representative_source_id")
    raw_url = str(row.get("representative_url") or "").strip()
    event_id = first_event_id(row)

    if source_id == "afad_event_service":
        if event_id:
            return f"https://deprem.afad.gov.tr/event-detail/{event_id}"
        return "https://deprem.afad.gov.tr/"

    if source_id == "bursa_open_data_events":
        if raw_url.startswith("https://www.bursa.bel.tr/etkinlik/"):
            return raw_url
        return "https://www.bursa.bel.tr/etkinlik"

    if source_id == "izmir_open_data_events":
        if raw_url and "openapi.izmir.bel.tr" not in raw_url and raw_url.startswith(("http://", "https://")):
            return raw_url
        return "https://kultursanat.izmir.bel.tr/"

    if raw_url.startswith(("http://", "https://")):
        return raw_url
    return None


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    source_policy = load_source_policy()
    items = []

    if INPUT.exists():
        with INPUT.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if row.get("map_decision") != "SHOW":
                    continue

                source_id = row.get("representative_source_id")
                policy = source_policy.get(source_id, {})
                items.append({
                    "id": row.get("cluster_id"),
                    "province": row.get("province"),
                    "category": row.get("category", "OTHER"),
                    "title": row.get("headline") or "Gelişme",
                    "relevance": row.get("relevance", "MEDIUM"),
                    "freshness": row.get("freshness", "RECENT"),
                    "published_at": row.get("published_at"),
                    "source_id": source_id,
                    "source_url": human_source_url(row),
                    "rights_status": policy.get("data_rights_status", row.get("rights_status")),
                    "image_rights_status": policy.get("image_rights_status", "reuse_needs_final_check"),
                    "image_url": safe_image_url(row, source_policy),
                    "venue": row.get("venue"),
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                    "signal_count": row.get("signal_count", 1),
                    "source_count": row.get("source_count", 1),
                    "magnitude": row.get("magnitude"),
                    "depth_km": row.get("depth_km"),
                })

    items.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    OUTPUT.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    image_count = sum(1 for item in items if item.get("image_url"))
    blocked_image_count = sum(1 for item in items if item.get("image_rights_status") != "open_license_verified")
    link_count = sum(1 for item in items if item.get("source_url"))
    print(
        f"Web export: {len(items)} visible signals -> {OUTPUT} "
        f"({image_count} with verified reusable images, {blocked_image_count} image-rights-blocked, {link_count} with human links)"
    )


if __name__ == "__main__":
    main()
