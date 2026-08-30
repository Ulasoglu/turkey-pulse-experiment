import json
from pathlib import Path

INPUT = Path("data/clustered_events.jsonl")
OUTPUT = Path("web/data/signals.json")


def safe_image_url(row):
    image_url = row.get("image_url")
    rights = row.get("rights_status")
    if not image_url:
        return None
    if rights != "open_license_verified":
        return None
    if not str(image_url).startswith(("http://", "https://")):
        return None
    return image_url


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
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

                items.append({
                    "id": row.get("cluster_id"),
                    "province": row.get("province"),
                    "category": row.get("category", "OTHER"),
                    "title": row.get("headline") or "Gelişme",
                    "relevance": row.get("relevance", "MEDIUM"),
                    "freshness": row.get("freshness", "RECENT"),
                    "published_at": row.get("published_at"),
                    "source_id": row.get("representative_source_id"),
                    "source_url": row.get("representative_url"),
                    "rights_status": row.get("rights_status"),
                    "image_url": safe_image_url(row),
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
    print(f"Web export: {len(items)} visible signals -> {OUTPUT} ({image_count} with reusable images)")


if __name__ == "__main__":
    main()
