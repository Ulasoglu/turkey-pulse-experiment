from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB_DATA = ROOT / "web" / "data" / "signals.json"
TURKEY_TZ = timezone(timedelta(hours=3))
QUALITY_VERSION = "web-quality-v2-time-consistency"

# These HTML event sources often expose a start time but no reliable end time.
# For a "what is happening now?" product, yesterday's event should not stay
# visible for a week just because the source has no end timestamp.
STRICT_START_SOURCES = {
    "ankara_abb_culture_events",
    "konya_bb_events",
    "samsun_bb_events",
}

MONTHS = {
    "ocak": 1,
    "şubat": 2,
    "subat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5,
    "mayis": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8,
    "agustos": 8,
    "eylül": 9,
    "eylul": 9,
    "ekim": 10,
    "kasım": 11,
    "kasim": 11,
    "aralık": 12,
    "aralik": 12,
}
MONTH_PATTERN = re.compile(
    r"(?<!\d)([0-3]?\d)\s+"
    r"(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|Aralık|Aralik)\b",
    re.IGNORECASE,
)


def text(value):
    return str(value or "").strip()


def normalize(value):
    return " ".join(
        text(value)
        .translate(str.maketrans({"I": "i", "İ": "i", "ı": "i"}))
        .casefold()
        .split()
    )


def parse_iso(value):
    raw = text(value)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def title_calendar_date(title, reference):
    match = MONTH_PATTERN.search(text(title))
    if not match:
        return None
    day = int(match.group(1))
    month_name = normalize(match.group(2))
    month = MONTHS.get(month_name)
    if not month:
        return None

    # Infer the year nearest to the current product date. Around New Year this
    # prevents December/January announcements from being assigned a silly year.
    candidates = []
    for year in (reference.year - 1, reference.year, reference.year + 1):
        try:
            candidate = datetime(year, month, day, tzinfo=TURKEY_TZ)
        except ValueError:
            continue
        candidates.append(candidate)
    if not candidates:
        return None
    return min(candidates, key=lambda dt: abs((dt - reference).total_seconds()))


def reason_to_drop(row, now_local):
    source_id = text(row.get("source_id"))
    category = text(row.get("category"))
    title = text(row.get("title"))

    # Dedicated HTML event sources without reliable end times: keep today's and
    # future events, hide older starts.
    if category == "EVENT" and source_id in STRICT_START_SOURCES:
        occurred = parse_iso(row.get("published_at"))
        if occurred is not None:
            local_date = occurred.astimezone(TURKEY_TZ).date()
            if local_date < now_local.date():
                return "stale_html_event_start"

    # Municipal news can announce an event days before it happens. If the title
    # contains an explicit Turkish calendar date and that date has already
    # passed, do not keep showing the announcement as a live event.
    if category == "EVENT" and source_id.endswith(("_news", "_duyurular")):
        event_date = title_calendar_date(title, now_local)
        if event_date is not None and event_date.date() < now_local.date():
            return "expired_dated_news_event"

    # Do not infer service actionability from a short exported headline here.
    # The upstream filter and signal engine still have the richer source row and
    # already decide whether municipal support/application items deserve SHOW.
    # A final headline-only rule previously removed legitimate opportunities
    # such as Manisa's current youth environmental-project support call.

    return None


def main():
    if not WEB_DATA.exists():
        raise SystemExit(f"Missing web data: {WEB_DATA}")

    rows = json.loads(WEB_DATA.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("web/data/signals.json must contain a JSON array")

    now_local = datetime.now(timezone.utc).astimezone(TURKEY_TZ)
    kept = []
    dropped = Counter()

    for row in rows:
        reason = reason_to_drop(row, now_local)
        if reason:
            dropped[reason] += 1
            continue
        kept.append(row)

    WEB_DATA.write_text(
        json.dumps(kept, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("\n=== TURKEY PULSE WEB QUALITY GATE ===")
    print(f"VERSION: {QUALITY_VERSION}")
    print(f"INPUT:  {len(rows)}")
    print(f"OUTPUT: {len(kept)}")
    print(f"DROP:   {len(rows) - len(kept)}")
    for reason, count in sorted(dropped.items()):
        print(f"  {reason}: {count}")
    print(f"Wrote: {WEB_DATA}")


if __name__ == "__main__":
    main()
