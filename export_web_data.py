import json
from pathlib import Path

INPUT = Path("data/clustered_events.jsonl")
OUTPUT = Path("web/data/signals.json")
SOURCES = Path("sources.json")


def load_source_policy():
    if not SOURCES.exists(): return {}
    try: manifest = json.loads(SOURCES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return {}
    return {source.get("id"): source for source in manifest.get("sources", []) if source.get("id")}


def safe_image_url(row, source_policy):
    image_url=row.get("image_url"); source_id=row.get("representative_source_id"); policy=source_policy.get(source_id,{}); image_rights=policy.get("image_rights_status","reuse_needs_final_check")
    if not image_url or image_rights!="open_license_verified" or not str(image_url).startswith(("http://","https://")): return None
    return image_url


def first_event_id(row):
    for value in row.get("member_event_ids") or []:
        if value is not None and str(value).strip(): return str(value).strip()
    return None


def human_source_url(row):
    source_id=row.get("representative_source_id"); raw_url=str(row.get("representative_url") or "").strip(); event_id=first_event_id(row)
    if source_id=="afad_event_service": return f"https://deprem.afad.gov.tr/event-detail/{event_id}" if event_id else "https://deprem.afad.gov.tr/"
    if source_id=="bursa_open_data_events": return raw_url if raw_url.startswith("https://www.bursa.bel.tr/etkinlik/") else "https://www.bursa.bel.tr/etkinlik"
    if source_id=="izmir_open_data_events": return raw_url if raw_url and "openapi.izmir.bel.tr" not in raw_url and raw_url.startswith(("http://","https://")) else "https://kultursanat.izmir.bel.tr/"
    if source_id=="ecmwf_open_data_weather": return "https://www.ecmwf.int/en/forecasts/datasets/open-data"
    return raw_url if raw_url.startswith(("http://","https://")) else None


def main():
    OUTPUT.parent.mkdir(parents=True,exist_ok=True); source_policy=load_source_policy(); items=[]
    if INPUT.exists():
        with INPUT.open("r",encoding="utf-8") as handle:
            for line in handle:
                line=line.strip()
                if not line: continue
                try: row=json.loads(line)
                except json.JSONDecodeError: continue
                if row.get("map_decision")!="SHOW": continue
                source_id=row.get("representative_source_id"); policy=source_policy.get(source_id,{})
                items.append({
                    "id":row.get("cluster_id"),"province":row.get("province"),"category":row.get("category","OTHER"),"title":row.get("headline") or "Gelişme","relevance":row.get("relevance","MEDIUM"),"freshness":row.get("freshness","RECENT"),"published_at":row.get("published_at"),
                    "source_id":source_id,"source_url":human_source_url(row),"rights_status":policy.get("data_rights_status",row.get("rights_status")),"image_rights_status":policy.get("image_rights_status","reuse_needs_final_check"),"image_url":safe_image_url(row,source_policy),
                    "venue":row.get("venue"),"latitude":row.get("latitude"),"longitude":row.get("longitude"),"signal_count":row.get("signal_count",1),"source_count":row.get("source_count",1),"magnitude":row.get("magnitude"),"depth_km":row.get("depth_km"),
                    "derived_signal":bool(row.get("derived_signal",False)),"official_warning":bool(row.get("official_warning",False)),"model":row.get("model"),"forecast_step_hours":row.get("forecast_step_hours"),"attribution":row.get("attribution"),"weather_kind":row.get("weather_kind"),
                    "temperature_c":row.get("temperature_c"),"wind_kmh":row.get("wind_kmh"),"precipitation_mm_24h":row.get("precipitation_mm_24h"),
                })
    items.sort(key=lambda item:item.get("published_at") or "",reverse=True); OUTPUT.write_text(json.dumps(items,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    image_count=sum(1 for item in items if item.get("image_url")); blocked_image_count=sum(1 for item in items if item.get("image_rights_status")!="open_license_verified"); link_count=sum(1 for item in items if item.get("source_url")); model_count=sum(1 for item in items if item.get("derived_signal"))
    print(f"Web export: {len(items)} visible signals -> {OUTPUT} ({image_count} with verified reusable images, {blocked_image_count} image-rights-blocked, {link_count} with human links, {model_count} model-derived)")

if __name__=="__main__": main()
