import json
import urllib.request
import urllib.error

RESOURCE_ID = "dec71f1d-5b26-41a3-831a-c14788fabdb8"
API_URL = f"https://acikyesil.bursa.bel.tr/api/3/action/package_search?q={RESOURCE_ID}"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TurkeyPulseProbe/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()

print("=== BUSKI PROBE ===")
print("Resource ID:", RESOURCE_ID)

try:
    status, ctype, body = fetch(API_URL)
    print("CKAN HTTP:", status)
    payload = json.loads(body.decode("utf-8"))
except Exception as e:
    raise SystemExit(f"CKAN lookup failed: {type(e).__name__}: {e}")

resource = None
for package in payload.get("result", {}).get("results", []):
    for r in package.get("resources", []):
        if r.get("id") == RESOURCE_ID:
            resource = r
            break
    if resource:
        break

if not resource:
    raise SystemExit("Resource found: NO")

url = resource.get("url")
print("Resource found: YES")
print("Name:", resource.get("name"))
print("Format:", resource.get("format"))
print("Resource URL:", url)

if not url:
    raise SystemExit("Resource has no URL")

try:
    status, ctype, body = fetch(url)
    print("HTTP:", status)
    print("Content-Type:", ctype)
    print("Bytes:", len(body))
except urllib.error.HTTPError as e:
    raise SystemExit(f"Resource HTTP error: {e.code} {e.reason}")
except Exception as e:
    raise SystemExit(f"Resource fetch failed: {type(e).__name__}: {e}")

try:
    data = json.loads(body.decode("utf-8-sig"))
    print("JSON: YES")
except Exception as e:
    print("JSON: NO")
    print("Parse error:", type(e).__name__, str(e))
    print("Preview:", body[:500].decode("utf-8", errors="replace"))
    raise SystemExit(0)

if isinstance(data, list):
    records = data
elif isinstance(data, dict):
    records = None
    for key in ("records", "result", "data", "items"):
        value = data.get(key)
        if isinstance(value, list):
            records = value
            break
    if records is None:
        records = []
        print("Top-level keys:", list(data.keys())[:30])
else:
    records = []

print("Records:", len(records))

if records:
    print("\nSample record:")
    print(json.dumps(records[0], ensure_ascii=False, indent=2)[:3000])
else:
    print("\nNo list-like records detected.")
