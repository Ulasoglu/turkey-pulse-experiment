import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

PACKAGE_ID = "57c561d6-46d6-4ae0-ab3f-a79e295e374a"
RESOURCE_ID = "3ad62685-09c6-494d-8756-e7f6c615abc4"
CKAN_URL = (
    "https://acikyesil.bursa.bel.tr/api/3/action/"
    f"package_show?id={PACKAGE_ID}"
)
EXPECTED_RESOURCE_URL = (
    "https://bapi.bursa.bel.tr/apigateway/acikveri/etkinlik"
)

def fetch(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TurkeyPulseProbe/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return (
            response.status,
            response.headers.get("Content-Type", ""),
            response.read(),
        )

def parse_date(value):
    if not value:
        return None
    value = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(value, fmt).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass
    return None

print("=== BURSA EVENTS PROBE ===")
print("Package ID:", PACKAGE_ID)
print("Resource ID:", RESOURCE_ID)

try:
    status, content_type, body = fetch(CKAN_URL)
    print("CKAN HTTP:", status)
    payload = json.loads(body.decode("utf-8"))
except Exception as exc:
    raise SystemExit(
        "CKAN package lookup failed: "
        f"{type(exc).__name__}: {exc}"
    )

if not payload.get("success"):
    raise SystemExit(
        "CKAN returned success=false: "
        f"{payload.get('error')}"
    )

package = payload.get("result") or {}
print("Package title:", package.get("title"))
print("Package name:", package.get("name"))

resources = package.get("resources") or []
print("Resources in package:", len(resources))

resource = None
for item in resources:
    if item.get("id") == RESOURCE_ID:
        resource = item
        break

if resource is None:
    print("Resource found: NO")
    print("Available resources:")
    for item in resources:
        print(
            " -",
            item.get("id"),
            "|",
            item.get("name"),
            "|",
            item.get("format"),
            "|",
            item.get("url"),
        )
    raise SystemExit(1)

print("Resource found: YES")
print("Resource name:", resource.get("name"))
print("Format:", resource.get("format"))
print("Datastore active:", resource.get("datastore_active"))

resource_url = resource.get("url") or EXPECTED_RESOURCE_URL
print("Resource URL:", resource_url)

try:
    status, content_type, body = fetch(resource_url)
    print("")
    print("=== RESOURCE FETCH ===")
    print("HTTP:", status)
    print("Content-Type:", content_type)
    print("Bytes:", len(body))
except urllib.error.HTTPError as exc:
    raise SystemExit(
        f"Resource HTTP error: {exc.code} {exc.reason}"
    )
except Exception as exc:
    raise SystemExit(
        "Resource fetch failed: "
        f"{type(exc).__name__}: {exc}"
    )

try:
    data = json.loads(body.decode("utf-8-sig"))
    print("JSON: YES")
except Exception as exc:
    print("JSON: NO")
    print("Parse error:", type(exc).__name__, str(exc))
    print("")
    print("Preview:")
    print(
        body[:1500].decode(
            "utf-8",
            errors="replace",
        )
    )
    raise SystemExit(1)

if not isinstance(data, list):
    print("Top-level type:", type(data).__name__)
    raise SystemExit(
        "Expected the Bursa events endpoint to return a JSON list."
    )

records = data
print("Records:", len(records))

now = datetime.now(timezone.utc)
dated_records = []
future_or_active = []

for item in records:
    if not isinstance(item, dict):
        continue
    start = parse_date(item.get("tarih_baslama"))
    end = parse_date(item.get("tarih_bitis"))
    if start:
        dated_records.append((start, item))
    relevant_end = end or start
    if relevant_end and relevant_end >= now:
        future_or_active.append(item)

if dated_records:
    dated_records.sort(key=lambda pair: pair[0])
    oldest = dated_records[0]
    newest = dated_records[-1]
    print("Oldest start:", oldest[0].isoformat())
    print("Oldest title:", oldest[1].get("adi"))
    print("Newest start:", newest[0].isoformat())
    print("Newest title:", newest[1].get("adi"))
else:
    print("Oldest start: UNKNOWN")
    print("Newest start: UNKNOWN")

print("Now UTC:", now.isoformat())
print("Future/active records:", len(future_or_active))

print("")
print("=== FIRST 3 RECORDS ===")
for index, item in enumerate(records[:3], start=1):
    if not isinstance(item, dict):
        print(index, repr(item))
        continue
    summary = {
        "id": item.get("id"),
        "adi": item.get("adi"),
        "tarih_baslama": item.get("tarih_baslama"),
        "tarih_bitis": item.get("tarih_bitis"),
        "kategori": item.get("kategori"),
        "mekan": item.get("mekan"),
        "diger_mekan": item.get("diger_mekan"),
        "link": item.get("link"),
        "foto_url": item.get("foto_url"),
    }
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

print("")
print("=== NEWEST 3 BY START DATE ===")
for start, item in sorted(
    dated_records,
    key=lambda pair: pair[0],
    reverse=True,
)[:3]:
    summary = {
        "id": item.get("id"),
        "adi": item.get("adi"),
        "tarih_baslama": item.get("tarih_baslama"),
        "tarih_bitis": item.get("tarih_bitis"),
        "kategori": item.get("kategori"),
        "mekan": item.get("mekan"),
        "link": item.get("link"),
    }
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

print("")
print("=== BURSA EVENTS PROBE DONE ===")
