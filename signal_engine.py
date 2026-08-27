from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INFILE = ROOT / "data" / "filtered_signals.jsonl"
OUTFILE = ROOT / "data" / "map_signals.jsonl"
ENGINE_VERSION = "signal-engine-v1"

CATEGORY_RULES = [
    ("WEATHER", {"uyarı","sağanak","yağış","fırtına","rüzgâr","rüzgar","sıcak","sıcaklık"}),
    ("TRAFFIC", {"trafik","ulaşım","yol","cadde","sokak","köprü","tünel","istasyon","metro","tramvay","izban","otobüs","vapur","sefer"}),
    ("UTILITY", {"elektrik kesintisi","su kesintisi","doğalgaz","arıza"}),
    ("EVENT", {"etkinlik","festival","konser","kutlanacak","coşkusu","bayram","sergi","ücretsiz","indirimli"}),
    ("INFRASTRUCTURE", {"altyapı","yenileme","proje","inşaat"}),
]

NOW_TERMS = {"uyarı","kapatıldı","kapalı","kesintisi","arıza","sağanak","fırtına","yağış","deprem"}
SOON_TERMS = {"yarın","bugün","bu akşam","hafta sonu","etkinlik","festival","konser","kutlanacak","bayram","ücretsiz","indirimli"}
LONG_TERM_TERMS = {"proje","yatırım","yenileme","altyapı","inşaat","dönemi başlıyor"}
HIGH_RELEVANCE_TERMS = {"uyarı","kapatıldı","kesintisi","arıza","trafik","ulaşım","deprem","yangın","sağanak","fırtına","yağış"}
MEDIUM_RELEVANCE_TERMS = {"etkinlik","festival","konser","bayram","ücretsiz","indirimli","yenileme","altyapı","proje"}

def text(value):
    return str(value or "").strip()

def normalize(value):
    value = text(value).translate(str.maketrans({"I":"i","İ":"i","ı":"i"})).casefold()
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
        dt = datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

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
    return "MEDIUM" if row.get("filter_decision") == "KEEP" else "LOW"

def detect_urgency(row, category):
    title_n = normalize(row.get("title"))
    if category == "EARTHQUAKE":
        return "NOW"
    if has_any(title_n, NOW_TERMS):
        return "NOW"
    if has_any(title_n, SOON_TERMS):
        return "SOON"
    if has_any(title_n, LONG_TERM_TERMS):
        return "LONG_TERM"
    published_at = parse_iso(row.get("published_at"))
    if published_at:
        age = datetime.now(timezone.utc) - published_at
        if age <= timedelta(days=3):
            return "RECENT"
    return "UNKNOWN"

def decide_map_visibility(row, category, relevance, urgency):
    if text(row.get("filter_decision")) == "DROP":
        return "HIDE"
    if category == "EARTHQUAKE" and relevance in {"HIGH","MEDIUM"}:
        return "SHOW"
    if relevance == "HIGH" and urgency in {"NOW","SOON","RECENT"}:
        return "SHOW"
    if category == "EVENT" and relevance in {"HIGH","MEDIUM"} and urgency in {"SOON","RECENT"}:
        return "SHOW"
    if relevance == "MEDIUM":
        return "REVIEW"
    return "HIDE"

def load_rows():
    if not INFILE.exists():
        raise SystemExit(f"Missing input file: {INFILE}")
    rows, bad_lines = [], 0
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
    results = []
    visibility_counts = Counter()
    category_counts = Counter()
    relevance_counts = Counter()
    urgency_counts = Counter()

    for row in rows:
        category = detect_category(row)
        relevance = detect_relevance(row, category)
        urgency = detect_urgency(row, category)
        map_decision = decide_map_visibility(row, category, relevance, urgency)

        enriched = dict(row)
        enriched["signal_category"] = category
        enriched["signal_relevance"] = relevance
        enriched["signal_urgency"] = urgency
        enriched["map_decision"] = map_decision
        enriched["signal_engine_version"] = ENGINE_VERSION
        results.append(enriched)

        visibility_counts[map_decision] += 1
        category_counts[category] += 1
        relevance_counts[relevance] += 1
        urgency_counts[urgency] += 1

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTFILE.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("")
    print("=== TURKEY PULSE SIGNAL ENGINE ===")
    print(f"VERSION: {ENGINE_VERSION}")
    print(f"INPUT:  {len(rows)}")
    print(f"SHOW:   {visibility_counts['SHOW']}")
    print(f"REVIEW: {visibility_counts['REVIEW']}")
    print(f"HIDE:   {visibility_counts['HIDE']}")
    print(f"BAD JSON LINES: {bad_lines}")
    print("")
    print("Categories:")
    for key, value in sorted(category_counts.items()):
        print(f"  {key}: {value}")
    print("")
    print("Relevance:")
    for key, value in sorted(relevance_counts.items()):
        print(f"  {key}: {value}")
    print("")
    print("Urgency:")
    for key, value in sorted(urgency_counts.items()):
        print(f"  {key}: {value}")
    print("")
    print(f"Wrote: {OUTFILE}")

if __name__ == "__main__":
    main()
