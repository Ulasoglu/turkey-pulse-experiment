from __future__ import annotations
import json, re, hashlib
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INFILE = ROOT / "data" / "map_signals.jsonl"
OUTFILE = ROOT / "data" / "clustered_events.jsonl"
CLUSTER_VERSION = "event-cluster-v2-images"
VISIBLE = {"SHOW", "REVIEW"}

WINDOWS = {
    "WEATHER": timedelta(hours=24),
    "TRAFFIC": timedelta(hours=12),
    "UTILITY": timedelta(hours=12),
    "EVENT": timedelta(days=3),
    "INFRASTRUCTURE": timedelta(days=7),
    "EARTHQUAKE": timedelta(minutes=20),
    "OTHER": timedelta(hours=12),
}

STOPWORDS = {
    "ve","ile","icin","için","bir","bu","da","de","mi","mı","mu","mü",
    "istanbul","izmir","bursa","ankara","ibb","bb","belediyesi",
    "buyuksehir","büyükşehir","haber","haberler"
}

ANCHORS = {
    "WEATHER": {"yagis","yağış","saganak","sağanak","firtina","fırtına","ruzgar","rüzgar","rüzgâr","sicak","sıcak","uyari","uyarı"},
    "TRAFFIC": {"trafik","ulasim","ulaşım","yol","cadde","sokak","kopru","köprü","tunel","tünel","metro","tramvay","otobus","otobüs","vapur","sefer"},
    "UTILITY": {"elektrik","su","dogalgaz","doğalgaz","kesinti","kesintisi","ariza","arıza"},
    "EVENT": {"etkinlik","festival","konser","bayram","kutlama","kutlanacak","sergi"},
    "INFRASTRUCTURE": {"altyapi","altyapı","yenileme","proje","insaat","inşaat"},
    "EARTHQUAKE": {"deprem"},
    "OTHER": set(),
}

def text(v): return str(v or "").strip()

def norm(v):
    v = text(v).translate(str.maketrans({"I":"i","İ":"i","ı":"i"})).casefold()
    v = re.sub(r"[^\w\s]", " ", v, flags=re.UNICODE)
    return " ".join(v.split())

def toks(v):
    return {x for x in norm(v).split() if len(x) >= 3 and x not in STOPWORDS}

def dt(v):
    s = text(v)
    if not s: return None
    try: x = datetime.fromisoformat(s.replace("Z","+00:00"))
    except ValueError: return None
    if x.tzinfo is None: x = x.replace(tzinfo=timezone.utc)
    return x.astimezone(timezone.utc)

def when(r): return dt(r.get("published_at")) or dt(r.get("collected_at"))
def cat(r): return text(r.get("signal_category")) or "OTHER"
def prov(r): return norm(r.get("province"))

def similarity(a,b):
    A,B = toks(a), toks(b)
    return len(A&B)/len(A|B) if A and B and (A|B) else 0.0

def anchor_hits(a,b,c):
    A,B = toks(a), toks(b)
    anchors = {norm(x) for x in ANCHORS.get(c,set())}
    return len((A&B)&anchors)

def same_cluster(a,b):
    if prov(a) != prov(b) or cat(a) != cat(b): return False
    c = cat(a)
    if c == "EARTHQUAKE":
        ea, eb = text(a.get("event_id")), text(b.get("event_id"))
        return bool(ea and eb and ea == eb)
    ta,tb = when(a),when(b)
    if ta is None or tb is None: return False
    if abs(ta-tb) > WINDOWS.get(c,timedelta(hours=12)): return False
    sim = similarity(a.get("title"), b.get("title"))
    ah = anchor_hits(a.get("title"), b.get("title"), c)
    if sim >= 0.42: return True
    if ah >= 2 and sim >= 0.20: return True
    if c == "WEATHER" and ah >= 2: return True
    return False

def rep_score(r):
    s = 50 if text(r.get("map_decision")) == "SHOW" else 0
    s += 25 if text(r.get("signal_relevance")) == "HIGH" else 10 if text(r.get("signal_relevance")) == "MEDIUM" else 0
    s += min(len(text(r.get("title"))),120)/10
    t = when(r)
    if t: s += t.timestamp()/1_000_000_000
    return s

def cluster_id(rows):
    first = min(rows, key=lambda r: when(r) or datetime.max.replace(tzinfo=timezone.utc))
    seed = "|".join([prov(first),cat(first),norm(first.get("title")),text(first.get("published_at"))])
    return "cluster_" + hashlib.sha1(seed.encode()).hexdigest()[:12]

def load():
    rows=[]; bad=0
    if not INFILE.exists(): raise SystemExit(f"Missing input file: {INFILE}")
    with INFILE.open(encoding="utf-8") as f:
        for i,line in enumerate(f,1):
            line=line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad+=1
                print(f"SKIP invalid JSON line {i}")
    return rows,bad

def make_event(group):
    rep=max(group,key=rep_score)
    times=[when(r) for r in group if when(r)]
    sources=sorted({text(r.get("source_id")) for r in group if text(r.get("source_id"))})
    return {
        "cluster_id": cluster_id(group),
        "cluster_version": CLUSTER_VERSION,
        "province": rep.get("province"),
        "category": rep.get("signal_category"),
        "headline": rep.get("title"),
        "map_decision": "SHOW" if any(text(r.get("map_decision"))=="SHOW" for r in group) else "REVIEW",
        "relevance": rep.get("signal_relevance"),
        "freshness": rep.get("signal_freshness"),
        "published_at": rep.get("published_at"),
        "first_signal_at": min(times).isoformat() if times else None,
        "last_signal_at": max(times).isoformat() if times else None,
        "signal_count": len(group),
        "source_count": len(sources),
        "sources": sources,
        "titles": [text(r.get("title")) for r in group if text(r.get("title"))],
        "representative_source_id": rep.get("source_id"),
        "representative_url": rep.get("url"),
        "rights_status": rep.get("rights_status"),
        "image_url": rep.get("image_url"),
        "venue": rep.get("venue"),
        "latitude": rep.get("latitude"),
        "longitude": rep.get("longitude"),
        "magnitude": rep.get("magnitude"),
        "depth_km": rep.get("depth_km"),
        "member_event_ids": [r.get("event_id") for r in group if r.get("event_id") is not None],
    }

def main():
    rows,bad=load()
    candidates=[r for r in rows if text(r.get("map_decision")) in VISIBLE]
    candidates.sort(key=lambda r: when(r) or datetime.min.replace(tzinfo=timezone.utc))
    groups=[]
    for row in candidates:
        for g in groups:
            if any(same_cluster(row,m) for m in g):
                g.append(row); break
        else:
            groups.append([row])

    events=[make_event(g) for g in groups]
    events.sort(key=lambda e: dt(e.get("last_signal_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    OUTFILE.parent.mkdir(parents=True,exist_ok=True)
    with OUTFILE.open("w",encoding="utf-8") as f:
        for e in events: f.write(json.dumps(e,ensure_ascii=False)+"\n")

    multi=[e for e in events if e["signal_count"]>1]
    decisions=Counter(e["map_decision"] for e in events)
    cats=Counter(e["category"] for e in events)

    print("\n=== TURKEY PULSE EVENT CLUSTER ===")
    print(f"VERSION: {CLUSTER_VERSION}")
    print(f"INPUT ROWS:       {len(rows)}")
    print(f"VISIBLE INPUT:    {len(candidates)}")
    print(f"EVENT CLUSTERS:   {len(events)}")
    print(f"MERGED SIGNALS:   {len(candidates)-len(events)}")
    print(f"MULTI-SIGNAL:     {len(multi)}")
    print(f"BAD JSON LINES:   {bad}\n")
    print(f"Map decisions:\n  SHOW:   {decisions['SHOW']}\n  REVIEW: {decisions['REVIEW']}\n")
    print("Categories:")
    for k,v in sorted(cats.items()): print(f"  {k}: {v}")
    if multi:
        print("\nMerged clusters:")
        for e in multi:
            print(f"  {e['province']} | {e['category']} | {e['signal_count']} signals | {e['headline']}")
    print(f"\nWrote: {OUTFILE}")

if __name__ == "__main__":
    main()
