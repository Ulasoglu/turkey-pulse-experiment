from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw_signals.jsonl"
OUT = ROOT / "data" / "filtered_signals.jsonl"


# V1: deliberately simple, transparent and zero-cost.
# Raw data is never changed or deleted.
GENERIC_DROP_TITLES = {
    "haberler",
    "haber",
    "duyurular",
}

HIGH_SIGNAL_TERMS = {
    # Weather / safety
    "uyarı", "sağanak", "yağış", "fırtına", "kuvvetli rüzgâr",
    "kuvvetli rüzgar", "aşırı sıcak", "sıcaklık", "yangın",
    "kapatıldı", "kapalı",

    # Mobility / infrastructure
    "ulaşım", "trafik", "yol", "cadde", "sokak", "köprü",
    "tünel", "istasyon", "metro", "tramvay", "izban",
    "otobüs", "vapur", "sefer", "altyapı", "yenileme",

    # Utility / disruption
    "elektrik kesint", "su kesint", "doğalgaz", "arıza",

    # Events with clear public usefulness
    "ücretsiz", "indirimli",
}

EVENT_TERMS = {
    "etkinlik", "festival", "konser", "kutlanacak",
    "coşkusu", "bayram", "sergi",
}

PR_TERMS = {
    "baş tacımız", "ziyaret etti", "teşekkür", "mesajı",
    "ağırladı", "buluştu", "protokol", "heyet",
    "gurur", "ödül", "başarı", "eğitimini tamamladı",
    "personeline eğitim", "personele özel eğitim",
}


def text(value) -> str:
    return str(value or "").strip()


def normalize(value) -> str:
    return " ".join(text(value).casefold().split())


def classify(row: dict) -> tuple[str, str]:
    source_id = text(row.get("source_id"))
    title = text(row.get("title"))
    title_n = normalize(title)
    raw_summary = normalize(row.get("raw_summary"))

    # Technical/errors/page-watch records are not public map signals.
    if raw_summary.startswith("error:"):
        return "DROP", "collector_error"

    if source_id == "bursa_acik_yesil_catalog":
        return "DROP", "page_watch_not_an_event"

    # Old AFAD page-watch record from the earliest experiment.
    if source_id == "afad_event_service" and row.get("event_id") is None:
        return "DROP", "afad_non_event_record"

    # Earthquakes: keep raw data, but public-map threshold starts at M3.0.
    if source_id == "afad_event_service":
        try:
            magnitude = float(row.get("magnitude"))
        except (TypeError, ValueError):
            return "DROP", "afad_missing_magnitude"

        if magnitude >= 4.0:
            return "KEEP", "earthquake_m4_plus"
        if magnitude >= 3.0:
            return "KEEP", "earthquake_m3_plus"
        return "DROP", "earthquake_below_m3"

    if not title:
        return "DROP", "missing_title"

    if title_n in GENERIC_DROP_TITLES:
        return "DROP", "generic_navigation_title"

    # Emergency municipal sources get a small trust boost, but still need
    # a meaningful title.
    high_hits = [term for term in HIGH_SIGNAL_TERMS if term in title_n]
    event_hits = [term for term in EVENT_TERMS if term in title_n]
    pr_hits = [term for term in PR_TERMS if term in title_n]

    if high_hits:
        return "KEEP", "high_signal:" + ",".join(sorted(high_hits)[:3])

    if pr_hits:
        return "DROP", "likely_pr:" + ",".join(sorted(pr_hits)[:3])

    if event_hits:
        return "KEEP", "public_event:" + ",".join(sorted(event_hits)[:3])

    if source_id == "akom_istanbul_news":
        # AKOM is emergency-focused. Unmatched articles are worth review
        # instead of being silently discarded.
        return "MAYBE", "akom_needs_review"

    if source_id == "izmir_bb_news":
        return "MAYBE", "municipal_news_needs_review"

    return "MAYBE", "unclassified_source"


def load_rows():
    if not RAW.exists():
        raise SystemExit(f"Missing input file: {RAW}")

    rows = []
    bad_lines = 0

    with RAW.open("r", encoding="utf-8") as f:
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
    counts = Counter()
    source_counts = Counter()

    for row in rows:
        decision, reason = classify(row)

        filtered = dict(row)
        filtered["filter_decision"] = decision
        filtered["filter_reason"] = reason
        filtered["filter_version"] = "rules-v1"

        results.append(filtered)
        counts[decision] += 1
        source_counts[(row.get("source_id"), decision)] += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("")
    print("=== TURKEY PULSE FILTER REPORT ===")
    print(f"RAW:   {len(rows)}")
    print(f"KEEP:  {counts['KEEP']}")
    print(f"MAYBE: {counts['MAYBE']}")
    print(f"DROP:  {counts['DROP']}")
    print(f"BAD JSON LINES: {bad_lines}")
    print("")
    print("By source:")

    sources = sorted({text(row.get("source_id")) for row in rows})
    for source_id in sources:
        print(
            f"  {source_id}: "
            f"KEEP={source_counts[(source_id, 'KEEP')]} "
            f"MAYBE={source_counts[(source_id, 'MAYBE')]} "
            f"DROP={source_counts[(source_id, 'DROP')]}"
        )

    print("")
    print(f"Wrote: {OUT}")


if __name__ == "__main__":
    main()
