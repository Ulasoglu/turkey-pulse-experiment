from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw_signals.jsonl"
OUT = ROOT / "data" / "filtered_signals.jsonl"
FILTER_VERSION = "rules-v3-bursa"

GENERIC_DROP_TITLES = {"haberler", "haber", "duyurular"}
HIGH_SIGNAL_TERMS = {"uyarı","sağanak","yağış","fırtına","kuvvetli rüzgâr","kuvvetli rüzgar","aşırı sıcak","sıcaklık","yangın","kapatıldı","kapalı","ulaşım","trafik","yol","cadde","sokak","köprü","tünel","istasyon","metro","tramvay","izban","otobüs","vapur","sefer","altyapı","yenileme","elektrik kesintisi","su kesintisi","doğalgaz","arıza","ücretsiz","indirimli"}
EVENT_TERMS = {"etkinlik","festival","konser","kutlanacak","coşkusu","bayram","sergi","kayıt"}
PR_TERMS = {"baş tacımız","ziyaret etti","teşekkür","mesajı","ağırladı","buluştu","protokol","heyet","gurur","ödül","başarı","eğitimini tamamladı","personeline eğitim","personele özel eğitim","yapay zekâ desteği","yapay zeka desteği"}
RETROSPECTIVE_TERMS = {"buluşma noktası oldu","yolculuk yaptı","avrupa beşincisi","çifte gurur"}


def text(value): return str(value or "").strip()

def normalize(value):
    return " ".join(text(value).translate(str.maketrans({"I":"i","İ":"i","ı":"i"})).casefold().split())

def contains_term(haystack, term):
    pattern = r"(?<!\w)" + re.escape(normalize(term)).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, haystack, flags=re.UNICODE) is not None

def term_hits(title_n, terms): return sorted(term for term in terms if contains_term(title_n, term))


def classify(row):
    source_id = text(row.get("source_id")); title = text(row.get("title")); title_n = normalize(title); summary = normalize(row.get("raw_summary"))
    if summary.startswith("error:"): return "DROP", "collector_error"
    if source_id == "bursa_acik_yesil_catalog": return "DROP", "legacy_page_watch_not_event"
    if source_id == "bursa_open_data_events":
        if not title or not row.get("event_start_at"): return "DROP", "bursa_event_missing_core_fields"
        return "KEEP", "structured_bursa_public_event"
    if source_id == "afad_event_service" and row.get("event_id") is None: return "DROP", "afad_non_event_record"
    if source_id == "afad_event_service":
        try: magnitude = float(row.get("magnitude"))
        except (TypeError, ValueError): return "DROP", "afad_missing_magnitude"
        if magnitude >= 4.0: return "KEEP", "earthquake_m4_plus"
        if magnitude >= 3.0: return "KEEP", "earthquake_m3_plus"
        return "DROP", "earthquake_below_m3"
    if not title: return "DROP", "missing_title"
    if title_n in {normalize(x) for x in GENERIC_DROP_TITLES}: return "DROP", "generic_navigation_title"
    high_hits = term_hits(title_n, HIGH_SIGNAL_TERMS); event_hits = term_hits(title_n, EVENT_TERMS); pr_hits = term_hits(title_n, PR_TERMS); retro = term_hits(title_n, RETROSPECTIVE_TERMS)
    if high_hits: return "KEEP", "high_signal:" + ",".join(high_hits[:3])
    if retro: return "DROP", "retrospective:" + ",".join(retro[:3])
    if pr_hits: return "DROP", "likely_pr:" + ",".join(pr_hits[:3])
    if event_hits: return "KEEP", "public_event:" + ",".join(event_hits[:3])
    if source_id == "akom_istanbul_news": return "MAYBE", "akom_needs_review"
    if source_id == "izmir_bb_news": return "MAYBE", "municipal_news_needs_review"
    return "MAYBE", "unclassified_source"


def load_rows():
    if not RAW.exists(): raise SystemExit(f"Missing input file: {RAW}")
    rows=[]; bad=0
    with RAW.open("r", encoding="utf-8") as f:
        for n,line in enumerate(f,1):
            if not line.strip(): continue
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: bad += 1; print(f"SKIP invalid JSON line {n}")
    return rows,bad


def duplicate_key(row):
    title_n=normalize(row.get("title"))
    return (text(row.get("source_id")), title_n, text(row.get("published_at"))) if title_n else None


def main():
    rows,bad=load_rows(); results=[]; counts=Counter(); source_counts=Counter(); seen=set()
    for row in rows:
        decision,reason=classify(row)
        if decision in {"KEEP","MAYBE"}:
            key=duplicate_key(row)
            if key is not None:
                if key in seen: decision,reason="DROP","duplicate_title_same_source_date"
                else: seen.add(key)
        out=dict(row); out.update(filter_decision=decision, filter_reason=reason, filter_version=FILTER_VERSION); results.append(out)
        counts[decision]+=1; source_counts[(row.get("source_id"),decision)]+=1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for row in results: f.write(json.dumps(row, ensure_ascii=False)+"\n")
    print("\n=== TURKEY PULSE FILTER REPORT ==="); print(f"VERSION: {FILTER_VERSION}"); print(f"RAW:   {len(rows)}"); print(f"KEEP:  {counts['KEEP']}"); print(f"MAYBE: {counts['MAYBE']}"); print(f"DROP:  {counts['DROP']}"); print(f"BAD JSON LINES: {bad}\n"); print("By source:")
    for sid in sorted({text(r.get('source_id')) for r in rows}): print(f"  {sid}: KEEP={source_counts[(sid,'KEEP')]} MAYBE={source_counts[(sid,'MAYBE')]} DROP={source_counts[(sid,'DROP')]}")
    print(f"\nWrote: {OUT}")

if __name__ == "__main__": main()
