from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
INFILE=ROOT/"data"/"filtered_signals.jsonl"; OUTFILE=ROOT/"data"/"map_signals.jsonl"
ENGINE_VERSION="signal-engine-v3-bursa"
CATEGORY_RULES=[("WEATHER",{"uyarı","sağanak","yağış","fırtına","rüzgâr","rüzgar","sıcak","sıcaklık"}),("TRAFFIC",{"trafik","ulaşım","yol","cadde","sokak","köprü","tünel","istasyon","metro","tramvay","izban","otobüs","vapur","sefer"}),("UTILITY",{"elektrik kesintisi","su kesintisi","doğalgaz","arıza"}),("EVENT",{"etkinlik","festival","konser","kutlanacak","coşkusu","bayram","sergi","ücretsiz","indirimli"}),("INFRASTRUCTURE",{"altyapı","yenileme","proje","inşaat"})]
HIGH_RELEVANCE_TERMS={"uyarı","kapatıldı","kesintisi","arıza","trafik","ulaşım","deprem","yangın","sağanak","fırtına","yağış"}
MEDIUM_RELEVANCE_TERMS={"etkinlik","festival","konser","bayram","ücretsiz","indirimli","yenileme","altyapı","proje"}
LIFETIMES={"EARTHQUAKE":timedelta(hours=24),"WEATHER":timedelta(hours=24),"TRAFFIC":timedelta(hours=24),"UTILITY":timedelta(hours=24),"EVENT":timedelta(days=7),"INFRASTRUCTURE":timedelta(days=7),"OTHER":timedelta(hours=24)}
NOW_WINDOWS={"EARTHQUAKE":timedelta(hours=3),"WEATHER":timedelta(hours=6),"TRAFFIC":timedelta(hours=6),"UTILITY":timedelta(hours=6),"EVENT":timedelta(hours=24),"INFRASTRUCTURE":timedelta(hours=24),"OTHER":timedelta(hours=6)}

def text(v): return str(v or "").strip()
def normalize(v): return " ".join(text(v).translate(str.maketrans({"I":"i","İ":"i","ı":"i"})).casefold().split())
def contains_term(h,t): return re.search(r"(?<!\w)"+re.escape(normalize(t)).replace(r"\ ",r"\s+")+r"(?!\w)",h,flags=re.UNICODE) is not None
def has_any(h,terms): return any(contains_term(h,t) for t in terms)
def parse_iso(v):
    raw=text(v)
    if not raw:return None
    try:dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError:return None
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def detect_category(row):
    sid=text(row.get("source_id")); title=normalize(row.get("title"))
    if sid=="afad_event_service":return "EARTHQUAKE"
    if sid=="bursa_open_data_events":return "EVENT"
    for category,terms in CATEGORY_RULES:
        if has_any(title,terms):return category
    return "OTHER"

def detect_relevance(row,category):
    if text(row.get("source_id"))=="bursa_open_data_events":return "MEDIUM"
    title=normalize(row.get("title"))
    if category=="EARTHQUAKE":
        try:m=float(row.get("magnitude"))
        except (TypeError,ValueError):return "MEDIUM"
        return "HIGH" if m>=4 else "MEDIUM"
    if has_any(title,HIGH_RELEVANCE_TERMS):return "HIGH"
    if has_any(title,MEDIUM_RELEVANCE_TERMS):return "MEDIUM"
    return "MEDIUM" if text(row.get("filter_decision"))=="KEEP" else "LOW"

def freshness(row,category,now):
    if category=="EVENT" and row.get("event_start_at"):
        start=parse_iso(row.get("event_start_at")); end=parse_iso(row.get("event_end_at")) or start
        if start is None:return "UNKNOWN",None,None
        if end and now>end:return "OLD",max(now-end,timedelta(0)),end
        if now<start:
            until=start-now
            status="NOW" if until<=timedelta(hours=24) else "RECENT"
            return status,timedelta(0),end or (start+LIFETIMES[category])
        return "NOW",max(now-start,timedelta(0)),end or (start+LIFETIMES[category])
    occurred=parse_iso(row.get("published_at")) or parse_iso(row.get("collected_at"))
    if occurred is None:return "UNKNOWN",None,None
    age=max(now-occurred,timedelta(0)); expires=occurred+LIFETIMES[category]
    if now>=expires:return "OLD",age,expires
    return ("NOW" if age<=NOW_WINDOWS[category] else "RECENT"),age,expires

def decide(row,category,relevance,fresh):
    if text(row.get("filter_decision"))=="DROP" or fresh=="OLD":return "HIDE"
    if fresh=="UNKNOWN":return "REVIEW" if relevance in {"HIGH","MEDIUM"} else "HIDE"
    if category=="EARTHQUAKE" and relevance in {"HIGH","MEDIUM"}:return "SHOW"
    if category=="EVENT" and relevance in {"HIGH","MEDIUM"}:return "SHOW"
    if relevance=="HIGH" and fresh in {"NOW","RECENT"}:return "SHOW"
    if relevance=="MEDIUM":return "REVIEW"
    return "HIDE"

def load_rows():
    if not INFILE.exists():raise SystemExit(f"Missing input file: {INFILE}")
    rows=[];bad=0
    with INFILE.open("r",encoding="utf-8") as f:
        for n,line in enumerate(f,1):
            if not line.strip():continue
            try:rows.append(json.loads(line))
            except json.JSONDecodeError:bad+=1;print(f"SKIP invalid JSON line {n}")
    return rows,bad

def main():
    rows,bad=load_rows();now=datetime.now(timezone.utc);results=[];vis=Counter();cats=Counter();rels=Counter();freshs=Counter()
    for row in rows:
        cat=detect_category(row);rel=detect_relevance(row,cat);fresh,age,expires=freshness(row,cat,now);decision=decide(row,cat,rel,fresh)
        out=dict(row);out.update(signal_category=cat,signal_relevance=rel,signal_freshness=fresh,signal_age_minutes=round(age.total_seconds()/60,1) if age is not None else None,expires_at=expires.isoformat() if expires else None,map_decision=decision,signal_engine_version=ENGINE_VERSION);results.append(out)
        vis[decision]+=1;cats[cat]+=1;rels[rel]+=1;freshs[fresh]+=1
    OUTFILE.parent.mkdir(parents=True,exist_ok=True)
    with OUTFILE.open("w",encoding="utf-8") as f:
        for row in results:f.write(json.dumps(row,ensure_ascii=False)+"\n")
    print("\n=== TURKEY PULSE SIGNAL ENGINE ===");print(f"VERSION: {ENGINE_VERSION}");print(f"AS OF:   {now.isoformat()}");print(f"INPUT:   {len(rows)}");print(f"SHOW:    {vis['SHOW']}");print(f"REVIEW:  {vis['REVIEW']}");print(f"HIDE:    {vis['HIDE']}");print(f"BAD JSON LINES: {bad}");print("\nFreshness:")
    for k in ("NOW","RECENT","OLD","UNKNOWN"):print(f"  {k}: {freshs[k]}")
    print("\nCategories:")
    for k,v in sorted(cats.items()):print(f"  {k}: {v}")
    print("\nRelevance:")
    for k,v in sorted(rels.items()):print(f"  {k}: {v}")
    print(f"\nWrote: {OUTFILE}")

if __name__=="__main__":main()
