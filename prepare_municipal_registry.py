import json
from pathlib import Path

BASE = Path("municipal_sources.json")
PATCH_FILES = [
    Path("municipal_sources_overrides.json"),
    Path("municipal_sources_overrides_round4.json"),
]

base = json.loads(BASE.read_text(encoding="utf-8"))
patches = [json.loads(path.read_text(encoding="utf-8")) for path in PATCH_FILES if path.exists()]

sources = base.get("sources", [])
by_id = {item["source_id"]: item for item in sources}

# Apply additions from every patch first. This lets later override files safely
# reference sources that were originally introduced by an earlier patch.
for patch in patches:
    for addition in patch.get("additions", []):
        source_id = addition["source_id"]
        if source_id in by_id:
            by_id[source_id].update(addition)
        else:
            sources.append(addition)
            by_id[source_id] = addition

# Apply overrides in file order so later validation rounds can supersede older
# probe states without rewriting historical audit notes.
for patch in patches:
    for override in patch.get("overrides", []):
        source_id = override["source_id"]
        if source_id not in by_id:
            raise RuntimeError(f"Override references unknown source_id: {source_id}")
        by_id[source_id].update(override)

BASE.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

enabled = sum(1 for item in sources if item.get("enabled", base.get("defaults", {}).get("enabled", True)))
print(
    f"Prepared municipal registry: {len(sources)} configured, {enabled} enabled, "
    f"{len(sources) - enabled} paused, patches={len(patches)}"
)
