from __future__ import annotations
import hashlib, json, time
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "sources.json"
OUT = ROOT / "data" / "raw_signals.jsonl"

HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/0.1 (+non-commercial feasibility probe)"
}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))

def already_seen(source_id: str, content_hash: str) -> bool:
    if not OUT.exists():
        return False
    # Experiment-scale linear scan is intentional: simple and auditable.
    with OUT.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("source_id") == source_id and row.get("content_hash") == content_hash:
                return True
    return False

def append(row):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def probe_page(source):
    collected_at = now_iso()
    try:
        r = requests.get(source["url"], headers=HEADERS, timeout=25)
        text = r.text or ""
        content_hash = sha256_text(text)
        row = {
            "collected_at": collected_at,
            "source_id": source["id"],
            "province": source["province"],
            "source_type": source["source_type"],
            "rights_status": source["rights_status"],
            "url": source["url"],
            "http_status": r.status_code,
            "content_hash": content_hash,
            "title": None,
            "published_at": None,
            "raw_summary": f"page_watch bytes={len(r.content)}"
        }
        if not already_seen(source["id"], content_hash):
            append(row)
            print("NEW", source["id"], r.status_code, len(r.content))
        else:
            print("UNCHANGED", source["id"], r.status_code)
    except Exception as e:
        append({
            "collected_at": collected_at,
            "source_id": source["id"],
            "province": source["province"],
            "source_type": source["source_type"],
            "rights_status": source["rights_status"],
            "url": source["url"],
            "http_status": None,
            "content_hash": None,
            "title": None,
            "published_at": None,
            "raw_summary": f"ERROR: {type(e).__name__}: {e}"
        })
        print("ERROR", source["id"], e)

def main():
    manifest = load_manifest()
    enabled = [s for s in manifest["sources"] if s.get("enabled")]
    print(f"Probing {len(enabled)} enabled sources")
    for s in enabled:
        if s["mode"] == "page_watch":
            probe_page(s)
        else:
            print("SKIP unsupported mode", s["id"], s["mode"])
        time.sleep(1)

if __name__ == "__main__":
    main()
