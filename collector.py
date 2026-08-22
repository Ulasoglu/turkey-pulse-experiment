from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "sources.json"
OUT = ROOT / "data" / "raw_signals.jsonl"

HEADERS = {
    "User-Agent": (
        "TurkeyPulseFeasibilityExperiment/0.2 "
        "(+non-commercial feasibility probe)"
    )
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8", errors="ignore")
    ).hexdigest()


def sha256_json(value) -> str:
    normalized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True
    )
    return sha256_text(normalized)


def load_manifest():
    return json.loads(
        MANIFEST.read_text(encoding="utf-8")
    )


def already_seen(source_id: str, content_hash: str) -> bool:
    if not OUT.exists():
        return False

    with OUT.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue

            if (
                row.get("source_id") == source_id
                and row.get("content_hash") == content_hash
            ):
                return True

    return False


def append(row):
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                row,
                ensure_ascii=False
            )
            + "\n"
        )


def probe_page(source):
    collected_at = now_iso()

    try:
        r = requests.get(
            source["url"],
            headers=HEADERS,
            timeout=25
        )

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
            "latitude": None,
            "longitude": None,
            "magnitude": None,
            "depth_km": None,
            "event_id": None,
            "raw_summary": (
                f"page_watch bytes={len(r.content)}"
            )
        }

        if not already_seen(
            source["id"],
            content_hash
        ):
            append(row)

            print(
                "NEW",
                source["id"],
                r.status_code,
                len(r.content)
            )
        else:
            print(
                "UNCHANGED",
                source["id"],
                r.status_code
            )

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
            "latitude": None,
            "longitude": None,
            "magnitude": None,
            "depth_km": None,
            "event_id": None,
            "raw_summary": (
                f"ERROR: {type(e).__name__}: {e}"
            )
        })

        print(
            "ERROR",
            source["id"],
            e
        )


def collect_afad_events(source):
    collected_at = now_iso()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=24)

    params = {
        "start": start_time.strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        "end": end_time.strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        "orderby": "timedesc",
        "limit": 500,
        "format": "json"
    }

    try:
        r = requests.get(
            source["url"],
            params=params,
            headers=HEADERS,
            timeout=30
        )

        r.raise_for_status()

        events = r.json()

        if not isinstance(events, list):
            raise ValueError(
                "AFAD response is not a JSON list"
            )

        print(
            f"AFAD returned {len(events)} events"
        )

        new_count = 0

        for event in events:
            event_id = event.get("eventID")
            event_date = event.get("date")
            location = event.get("location")
            province = event.get("province")
            district = event.get("district")
            magnitude = event.get("magnitude")
            magnitude_type = event.get("type")
            latitude = event.get("latitude")
            longitude = event.get("longitude")
            depth = event.get("depth")

            event_identity = {
                "event_id": event_id,
                "date": event_date,
                "latitude": latitude,
                "longitude": longitude,
                "magnitude": magnitude,
                "location": location
            }

            content_hash = sha256_json(
                event_identity
            )

            if already_seen(
                source["id"],
                content_hash
            ):
                continue

            title_parts = []

            if magnitude is not None:
                if magnitude_type:
                    title_parts.append(
                        f"{magnitude_type} {magnitude}"
                    )
                else:
                    title_parts.append(
                        f"M {magnitude}"
                    )

            if location:
                title_parts.append(location)

            title = " - ".join(
                title_parts
            ) or "AFAD earthquake event"

            summary_parts = []

            if province:
                summary_parts.append(
                    f"province={province}"
                )

            if district:
                summary_parts.append(
                    f"district={district}"
                )

            if depth is not None:
                summary_parts.append(
                    f"depth_km={depth}"
                )

            row = {
                "collected_at": collected_at,
                "source_id": source["id"],
                "province": province or "UNKNOWN",
                "source_type": source["source_type"],
                "rights_status": source["rights_status"],
                "url": source["url"],
                "http_status": r.status_code,
                "content_hash": content_hash,
                "title": title,
                "published_at": event_date,
                "latitude": latitude,
                "longitude": longitude,
                "magnitude": magnitude,
                "magnitude_type": magnitude_type,
                "depth_km": depth,
                "event_id": event_id,
                "raw_summary": "; ".join(
                    summary_parts
                ),
                "raw_event": event
            }

            append(row)
            new_count += 1

            print(
                "NEW AFAD",
                event_id,
                event_date,
                location,
                magnitude
            )

        print(
            f"AFAD new events written: {new_count}"
        )

    except Exception as e:
        append({
            "collected_at": collected_at,
            "source_id": source["id"],
            "province": "ALL",
            "source_type": source["source_type"],
            "rights_status": source["rights_status"],
            "url": source["url"],
            "http_status": (
                r.status_code
                if "r" in locals()
                else None
            ),
            "content_hash": None,
            "title": None,
            "published_at": None,
            "latitude": None,
            "longitude": None,
            "magnitude": None,
            "depth_km": None,
            "event_id": None,
            "raw_summary": (
                f"ERROR: {type(e).__name__}: {e}"
            )
        })

        print(
            "ERROR AFAD",
            e
        )


def main():
    manifest = load_manifest()

    enabled = [
        source
        for source in manifest["sources"]
        if source.get("enabled")
    ]

    print(
        f"Probing {len(enabled)} enabled sources"
    )

    for source in enabled:
        mode = source.get("mode")

        if mode == "page_watch":
            probe_page(source)

        elif mode == "afad_events":
            collect_afad_events(source)

        else:
            print(
                "SKIP unsupported mode",
                source["id"],
                mode
            )

        time.sleep(1)


if __name__ == "__main__":
    main()
