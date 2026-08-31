import json
from pathlib import Path

BASE = Path("municipal_sources.json")
PATCH = Path("municipal_sources_overrides.json")

base = json.loads(BASE.read_text(encoding="utf-8"))
patch = json.loads(PATCH.read_text(encoding="utf-8"))

sources = base.get("sources", [])
by_id = {item["source_id"]: item for item in sources}

for override in patch.get("overrides", []):
    source_id = override["source_id"]
    if source_id not in by_id:
        raise RuntimeError(f"Override references unknown source_id: {source_id}")
    by_id[source_id].update(override)

for addition in patch.get("additions", []):
    source_id = addition["source_id"]
    if source_id in by_id:
        by_id[source_id].update(addition)
    else:
        sources.append(addition)
        by_id[source_id] = addition

BASE.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

enabled = sum(1 for item in sources if item.get("enabled", base.get("defaults", {}).get("enabled", True)))
print(f"Prepared municipal registry: {len(sources)} configured, {enabled} enabled, {len(sources) - enabled} paused")
