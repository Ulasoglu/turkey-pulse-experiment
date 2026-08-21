from pathlib import Path
import json, collections

p = Path("data/raw_signals.jsonl")
if not p.exists():
    print("No data yet.")
    raise SystemExit(0)

rows = []
for line in p.read_text(encoding="utf-8").splitlines():
    try:
        rows.append(json.loads(line))
    except Exception:
        pass

print("Observations:", len(rows))
print("By source:")
for k,v in collections.Counter(r.get("source_id") for r in rows).most_common():
    print(f"  {k}: {v}")
print("\nThis is only collection-health output. UEPD/LRS scoring happens after event classification.")
