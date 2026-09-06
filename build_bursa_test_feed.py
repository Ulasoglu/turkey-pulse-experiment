"""Build a temporary Bursa product-validation feed from DHA, IHA and AA probes.

TEST_ONLY. Does not touch the normal Turkey Pulse pipeline. Agency image URLs remain
metadata references only; this script never downloads media.
"""
from __future__ import annotations
import json, re
from difflib import SequenceMatcher
from pathlib import Path

INPUTS = [Path("data/test_only_dha_bursa.jsonl"),Path("data/test_only_iha_bursa.jsonl"),Path("data/test_only_aa_bursa.jsonl")]
OUT = Path("web/data/bursa-test-feed.json")
STOP = {"bursa","bursada","ve","ile","bir","icin","için","da","de","bu","sonra","olan","ihlas","haber","ajansı","ajansi"}

def norm(s):
    s=(s or "").lower().replace("’","").replace("'","")
    s=re.sub(r"[^a-z0-9çğıöşü ]+"," ",s)
    return " ".join(x for x in s.split() if x not in STOP and len(x)>2)

def source_of(r):
    raw=(r.get("source") or r.get("source_name") or "").strip()
    upper=raw.upper()
    if "DHA" in upper or "DEMİROREN" in upper or "DEMIROREN" in upper: return "DHA"
    if "IHA" in upper or "İHA" in upper or "İHLAS" in upper or "IHLAS" in upper: return "IHA"
    if upper=="AA" or "ANADOLU" in upper: return "AA"
    sid=(r.get("source_id") or "").lower()
    if sid.startswith("dha"): return "DHA"
    if sid.startswith("iha"): return "IHA"
    if sid.startswith("aa"): return "AA"
    return raw or "UNKNOWN"

def similarity(a,b):
    na,nb=norm(a),norm(b); wa,wb=set(na.split()),set(nb.split())
    jac=len(wa&wb)/max(1,len(wa|wb)); seq=SequenceMatcher(None,na,nb).ratio()
    return max(jac,seq)

def read_rows():
    rows=[]
    for p in INPUTS:
        if not p.exists(): continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r=json.loads(line); r["_normalized_source"]=source_of(r); rows.append(r)
    return rows

def cluster(rows):
    groups=[]
    for row in rows:
        title=row.get("title") or ""; best=None; score=0
        for g in groups:
            s=max(similarity(title,x.get("title") or "") for x in g)
            if s>score: best,score=g,s
        if best is not None and score>=0.58: best.append(row)
        else: groups.append([row])
    return groups

def main():
    rows=read_rows(); groups=cluster(rows); events=[]
    for i,g in enumerate(groups,1):
        primary=sorted(g,key=lambda r:{"DHA":0,"IHA":1,"AA":2}.get(r["_normalized_source"],9))[0]
        sources=[]
        for r in g:
            src=r["_normalized_source"]
            if src not in sources: sources.append(src)
        events.append({"id":f"bursa-test-{i}","test_only":True,"province":"Bursa","title":primary.get("title"),"published_at":primary.get("published_at") or primary.get("timestamp"),"image_url":primary.get("image_url") or primary.get("image_url_metadata"),"source_url":primary.get("url") or primary.get("source_url"),"sources":sources,"source_count":len(sources),"cluster_size":len(g),"rights_status":"test_only_no_media_rehosting"})
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"test_only":True,"province":"Bursa","raw_items":len(rows),"event_count":len(events),"events":events},ensure_ascii=False,indent=2),encoding="utf-8")
    print("=== BURSA TEST FEED ==="); print("Raw items:",len(rows)); print("Clustered events:",len(events)); print("Multi-source events:",sum(e["source_count"]>1 for e in events))
    for e in events: print(e["source_count"],"source(s)","/".join(e["sources"]),"-",e["title"])
    print("Output:",OUT)

if __name__=="__main__": main()
