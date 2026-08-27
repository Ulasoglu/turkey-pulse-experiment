from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INFILE = ROOT / "data" / "filtered_signals.jsonl"
OUTFILE = ROOT / "data" / "map_signals.jsonl"

ENGINE_VERSION = "signal-engine-v2"

CATEGORY_RULES = [
    ("WEATHER", {"uyarı", "sağanak", "yağış", "fırtına", "rüzgâr", "rüzgar", "sıcak", "sıcaklık"}),
    ("TRAFFIC", {"trafik", "ulaşım", "yol", "cadde", "sokak", "köprü", "tünel", "istasyon", "metro", "tramvay", "izban", "otobüs", "vapur", "sefer"}),
    ("UTILITY", {"elektrik kesintisi", "su kesintisi", "doğalgaz", "arıza"}),
    ("EVENT", {"etkinlik", "festival", "konser", "kutlanacak", "coşkusu", "bayram", "sergi", "ücretsiz", "indirimli"}),
    ("INFRASTRUCTURE", {"altyapı", "yenileme", "proje", "inşaat"}),
]

HIGH_RELEVANCE_TERMS = {
    "uyarı", "kapatıldı", "kesintisi", "arıza", "trafik", "ulaşım",
    "deprem", "yangın", "sağanak", "fırtına", "yağış",
}
MEDIUM_RELEVANCE_TERMS = {
    "etkinlik", "festival", "konser", "bayram", "ücretsiz", "indirimli",
    "yenileme", "altyapı", "proje",
}

# V2 freshness/lifetime rules.
# These are product-test defaults, not claims about official alert validity.
LIFETIMES = {
    "EARTHQUAKE": timedelta(hours=24),
    "WEATHER": timedelta(hours=24),
    "TRAFFIC": timedelta(hours=24),
    "UTILITY": timedelta(hours=24),
    "EVENT": timedelta(days=7),
    "INFRASTRUCTURE": timedelta(days=7),
    "OTHER": timedelta(hours=24),
}

NOW_WINDOWS = {
    "EARTHQUAKE": timedelta(hours=3),
    "WEATHER": timedelta(hours=6),
    "TRAFFIC": timedelta(hours=6),
    "UTILITY": timedelta(hours=6),
    "EVENT": timedelta(hours=24),
    "INFRASTRUCTURE": timedelta(hours=24),
    "OTHER": timedelta(hours=6),
}


def text(value):
    return str(value or "").strip()


def normalize(value):
    value = text(value).translate(str.maketrans({"I": "i", "İ": "i", "ı": "i"})).casefold()
    return " ".join(value.split())


def contains_term(haystack, term):
    pattern = r"(?<!\w)" + re.escape(normalize(term)).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, haystack, flags=re.UNICODE) is not None


def has_any(haystack, terms):
    return any(contains_term(haystack, term) for term in terms)


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


def signal_time(row):
    # published_at is the event time for AFAD and publication time for municipal feeds.
    return parse_iso(row.get("published_at")) or parse_iso(row.get("collected_at"))


def detect_category(row):
    source_id = text(row.get("source_id"))
    title_n = normalize(row.get("title"))

    if source_id == "afad_event_service":
        return "EARTHQUAKE"

    for category, terms in CATEGORY_RULES:
        if has_any(title_n, terms):
            return category

    return "OTHER"


def detect_relevance(row, category):
    title_n = normalize(row.get("title"))

    if category == "EARTHQUAKE":
        try:
            magnitude = float(row.get("magnitude"))
        except (TypeError, ValueError):
            return "MEDIUM"
        return "HIGH" if magnitude >= 4.0 else "MEDIUM"

    if has_any(title_n, HIGH_RELEVANCE_TERMS):
        return "HIGH"

    if has_any(title_n, MEDIUM_RELEVANCE_TERMS):
        return "MEDIUM"

    return "MEDIUM" if text(row.get("filter_decision")) == "KEEP" else "LOW"


def freshness(row, category, now):
    occurred = signal_time(row)

    if occurred is None:
        return "UNKNOWN", None, None

    # Protect against small clock/date anomalies.
    age = max(now - occurred, timedelta(0))
    expires_at = occurred + LIFETIMES[category]

    if now >= expires_at:
        return "OLD", age, expires_at

    if age <= NOW_WINDOWS[category]:
        return "NOW", age, expires_at

    return "RECENT", age, expires_at


def decide_map_visibility(row, category, relevance, freshness_status):
    if text(row.get("filter_decision")) == "DROP":
        return "HIDE"

    # No stale signal may remain visible on the live map.
    if freshness_status == "OLD":
        return "HIDE"

    # Unknown timestamps are never auto-published.
    if freshness_status == "UNKNOWN":
        return "REVIEW" if relevance in {"HIGH", "MEDIUM"} else "HIDE"

    if category == "EARTHQUAKE" and relevance in {"HIGH", "MEDIUM"}:
        return "SHOW"

    if relevance == "HIGH" and freshness_status in {"NOW", "RECENT"}:
        return "SHOW"

    if category == "EVENT" and relevance in {"HIGH", "MEDIUM"}:
        return "SHOW"

    if relevance == "MEDIUM":
        return "REVIEW"

    return "HIDE"


def load_rows():
    if not INFILE.exists():
        raise SystemExit(f"Missing input file: {INFILE}")

    rows = []
    bad_lines = 0

    with INFILE.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad_lines += 1
                print(f"SKIP invalid JSON line {line_no}")

    return rows, bad_lines


def main():
    rows, bad_lines = load_rows()
    now = datetime.now(timezone.utc)

    results = []
    visibility_counts = Counter()
    category_counts = Counter()
    relevance_counts = Counter()
    freshness_counts = Counter()

    for row in rows:
        category = detect_category(row)
        relevance = detect_relevance(row, category)
        freshness_status, age, expires_at = freshness(row, category, now)
        map_decision = decide_map_visibility(
            row, category, relevance, freshness_status
        )

        enriched = dict(row)
        enriched["signal_category"] = category
        enriched["signal_relevance"] = relevance
        enriched["signal_freshness"] = freshness_status
        enriched["signal_age_minutes"] = (
            round(age.total_seconds() / 60, 1) if age is not None else None
        )
        enriched["expires_at"] = (
            expires_at.isoformat() if expires_at is not None else None
        )
        enriched["map_decision"] = map_decision
        enriched["signal_engine_version"] = ENGINE_VERSION

        results.append(enriched)

        visibility_counts[map_decision] += 1
        category_counts[category] += 1
        relevance_counts[relevance] += 1
        freshness_counts[freshness_status] += 1

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTFILE.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("")
    print("=== TURKEY PULSE SIGNAL ENGINE ===")
    print(f"VERSION: {ENGINE_VERSION}")
    print(f"AS OF:   {now.isoformat()}")
    print(f"INPUT:   {len(rows)}")
    print(f"SHOW:    {visibility_counts['SHOW']}")
    print(f"REVIEW:  {visibility_counts['REVIEW']}")
    print(f"HIDE:    {visibility_counts['HIDE']}")
    print(f"BAD JSON LINES: {bad_lines}")

    print("")
    print("Freshness:")
    for key in ("NOW", "RECENT", "OLD", "UNKNOWN"):
        print(f"  {key}: {freshness_counts[key]}")

    print("")
    print("Categories:")
    for key, value in sorted(category_counts.items()):
        print(f"  {key}: {value}")

    print("")
    print("Relevance:")
    for key, value in sorted(relevance_counts.items()):
        print(f"  {key}: {value}")

    print("")
    print(f"Wrote: {OUTFILE}")


if __name__ == "__main__":
    main()
