import json
import urllib.request
import urllib.error

PACKAGE_ID = "2aa942cf-43ad-4a36-ab5d-e417ea77789f"
RESOURCE_ID = "dec71f1d-5b26-41a3-831a-c14788fabdb8"

API_URL = f"https://acikyesil.bursa.bel.tr/api/3/action/package_show?id={PACKAGE_ID}"


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TurkeyPulseProbe/1.1"},
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return (
            response.status,
            response.headers.get("Content-Type", ""),
            response.read(),
        )


print("=== BUSKI PROBE V2 ===")
print("Package ID:", PACKAGE_ID)
print("Resource ID:", RESOURCE_ID)

try:
    status, content_type, body = fetch(API_URL)
    print("CKAN HTTP:", status)

    payload = json.loads(body.decode("utf-8"))

except Exception as exc:
    raise SystemExit(
        f"CKAN package lookup failed: "
        f"{type(exc).__name__}: {exc}"
    )

if not payload.get("success"):
    raise SystemExit(
        f"CKAN returned success=false: "
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

if not resource:
    print("Resource found: NO")
    print("")
    print("Available resource IDs:")

    for item in resources:
        print(
            f"  {item.get('id')} | "
            f"{item.get('name')} | "
            f"{item.get('format')} | "
            f"{item.get('url')}"
        )

    raise SystemExit(1)

print("Resource found: YES")
print("Resource name:", resource.get("name"))
print("Format:", resource.get("format"))
print("Mimetype:", resource.get("mimetype"))
print("Datastore active:", resource.get("datastore_active"))
print("Last modified:", resource.get("last_modified"))
print("Created:", resource.get("created"))

resource_url = resource.get("url")

print("Resource URL:", resource_url)

if not resource_url:
    raise SystemExit("Resource has no URL")

try:
    status, content_type, body = fetch(resource_url)

    print("")
    print("=== RESOURCE FETCH ===")
    print("HTTP:", status)
    print("Content-Type:", content_type)
    print("Bytes:", len(body))

except urllib.error.HTTPError as exc:
    raise SystemExit(
        f"Resource HTTP error: "
        f"{exc.code} {exc.reason}"
    )

except Exception as exc:
    raise SystemExit(
        f"Resource fetch failed: "
        f"{type(exc).__name__}: {exc}"
    )

try:
    data = json.loads(
        body.decode("utf-8-sig")
    )

    print("JSON: YES")

except Exception as exc:
    print("JSON: NO")
    print(
        "Parse error:",
        type(exc).__name__,
        str(exc),
    )

    print("")
    print("Preview:")

    print(
        body[:1000].decode(
            "utf-8",
            errors="replace",
        )
    )

    raise SystemExit(0)

records = None

if isinstance(data, list):
    records = data

elif isinstance(data, dict):
    print(
        "Top-level keys:",
        list(data.keys())[:30],
    )

    for key in (
        "records",
        "result",
        "data",
        "items",
        "value",
    ):
        value = data.get(key)

        if isinstance(value, list):
            records = value
            print("Detected record key:", key)
            break

        if isinstance(value, dict):
            for nested_key in (
                "records",
                "data",
                "items",
                "results",
            ):
                nested_value = value.get(
                    nested_key
                )

                if isinstance(
                    nested_value,
                    list,
                ):
                    records = nested_value
                    print(
                        "Detected record key:",
                        f"{key}.{nested_key}",
                    )
                    break

            if records is not None:
                break

if records is None:
    records = []

print("Records:", len(records))

if records:
    print("")
    print("=== SAMPLE RECORD ===")
    print(
        json.dumps(
            records[0],
            ensure_ascii=False,
            indent=2,
        )[:5000]
    )

    print("")
    print("=== FIRST 5 RECORD DATES/FIELDS ===")

    for index, item in enumerate(
        records[:5],
        start=1,
    ):
        if isinstance(item, dict):
            print(
                f"{index}. keys="
                f"{list(item.keys())[:20]}"
            )
        else:
            print(
                f"{index}. "
                f"{str(item)[:500]}"
            )

else:
    print("")
    print(
        "No list-like records detected."
    )

print("")
print("=== BUSKI PROBE V2 DONE ===")
