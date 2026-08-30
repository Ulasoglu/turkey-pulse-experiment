"""ECMWF weather collector for Turkey Pulse.

Downloads ECMWF IFS Open Data, derives conservative +24h weather signals for
all Turkish province capitals and writes both a review file and guarded rows
into the normal raw signal stream.

These are model-derived signals, NOT official MGM warnings.
Licence: ECMWF Open Data, CC BY 4.0. Attribution required.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math

from ecmwf.opendata import Client

from probe_ecmwf_open_data import (
    PROVINCES,
    OUT,
    build_province_indices,
    derive_signals,
    read_fields,
    value_at_index,
)

CANDIDATE_OUT = Path("data/ecmwf_weather_candidates.jsonl")
RAW_OUT = Path("data/raw_signals.jsonl")
SOURCE_ID = "ecmwf_open_data_weather"
SOURCE_NAME = "ECMWF Open Data (IFS)"
SOURCE_URL = "https://www.ecmwf.int/en/forecasts/datasets/open-data"
ATTRIBUTION = "ECMWF Open Data – CC BY 4.0"

TURKISH_LABELS = {
    "HEAVY_RAIN": "Kuvvetli yağış ihtimali",
    "STRONG_WIND": "Kuvvetli rüzgâr ihtimali",
    "HEAT": "Aşırı sıcak ihtimali",
    "COLD": "Aşırı soğuk ihtimali",
}


def content_hash(item):
    identity = "|".join([
        SOURCE_ID,
        item["province"],
        item["weather_kind"],
        str(item["forecast_step_hours"]),
        str(item.get("precipitation_mm_24h")),
        str(item.get("wind_kmh")),
        str(item.get("temperature_c")),
    ])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def build_candidates():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    client = Client(source="ecmwf", model="ifs", resol="0p25", preserve_request_order=True)
    client.retrieve(
        time=0,
        step=24,
        stream="oper",
        type="fc",
        param=["2t", "10u", "10v", "tp"],
        target=str(OUT),
    )

    fields = read_fields(OUT)
    needed = {"2t", "10u", "10v", "tp"}
    if not needed.issubset(fields):
        raise RuntimeError(f"Missing ECMWF fields: {sorted(needed - set(fields))}")

    indices = build_province_indices(fields["2t"])
    generated_at = datetime.now(timezone.utc).replace(microsecond=0)
    candidates = []

    for province, (lat, lon) in PROVINCES.items():
        idx = indices[province]
        temp_c = value_at_index(fields["2t"], idx) - 273.15
        u = value_at_index(fields["10u"], idx)
        v = value_at_index(fields["10v"], idx)
        wind_kmh = math.hypot(u, v) * 3.6
        precip_mm = value_at_index(fields["tp"], idx) * 1000.0
        row = (province, temp_c, wind_kmh, precip_mm)

        for severity, kind, signal_province, value in derive_signals(row):
            title = f"{signal_province}: {TURKISH_LABELS[kind]}"
            summary = (
                f"ECMWF IFS modelinin yaklaşık +24 saatlik tahmininde {signal_province} için "
                f"dikkat çeken bir hava sinyali görülüyor ({value}). Bu, resmi bir MGM uyarısı değil; "
                "ECMWF model verisinden türetilmiş bir sinyaldir."
            )
            candidates.append({
                "source_id": SOURCE_ID,
                "source_name": SOURCE_NAME,
                "source_url": SOURCE_URL,
                "province": signal_province,
                "category": "WEATHER",
                "weather_kind": kind,
                "severity": severity,
                "title": title,
                "summary": summary,
                "event_time": generated_at.isoformat(),
                "collected_at": generated_at.isoformat(),
                "latitude": lat,
                "longitude": lon,
                "temperature_c": round(temp_c, 1),
                "wind_kmh": round(wind_kmh, 1),
                "precipitation_mm_24h": round(precip_mm, 1),
                "model": "ECMWF IFS 0.25°",
                "forecast_step_hours": 24,
                "derived_signal": True,
                "official_warning": False,
                "attribution": ATTRIBUTION,
                "rights_status": "open_license_verified",
                "review_only": False,
            })

    return candidates


def to_raw_row(item):
    return {
        "collected_at": item["collected_at"],
        "source_id": SOURCE_ID,
        "province": item["province"],
        "source_type": "national_model_weather",
        "rights_status": "open_license_verified",
        "url": SOURCE_URL,
        "http_status": 200,
        "content_hash": content_hash(item),
        "title": item["title"],
        "published_at": item["collected_at"],
        "latitude": item["latitude"],
        "longitude": item["longitude"],
        "magnitude": None,
        "depth_km": None,
        "event_id": None,
        "raw_summary": item["summary"],
        "weather_kind": item["weather_kind"],
        "weather_severity": item["severity"],
        "temperature_c": item["temperature_c"],
        "wind_kmh": item["wind_kmh"],
        "precipitation_mm_24h": item["precipitation_mm_24h"],
        "model": item["model"],
        "forecast_step_hours": item["forecast_step_hours"],
        "derived_signal": True,
        "official_warning": False,
        "attribution": ATTRIBUTION,
    }


def merge_into_raw(candidates):
    existing = []
    if RAW_OUT.exists():
        with RAW_OUT.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("source_id") != SOURCE_ID:
                    existing.append(row)

    merged = existing + [to_raw_row(item) for item in candidates]
    RAW_OUT.parent.mkdir(parents=True, exist_ok=True)
    with RAW_OUT.open("w", encoding="utf-8") as fh:
        for row in merged:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(existing), len(merged)


def main():
    print("=== ECMWF WEATHER COLLECTOR ===")
    print("MODE: guarded production pipeline input")
    print("IMPORTANT: model-derived signals; NOT official MGM warnings")
    candidates = build_candidates()

    CANDIDATE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CANDIDATE_OUT.open("w", encoding="utf-8") as fh:
        for item in candidates:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    before, after = merge_into_raw(candidates)
    print(f"CANDIDATES: {len(candidates)}")
    for item in candidates:
        print(f"{item['severity']} | {item['weather_kind']} | {item['province']} | {item['title']}")
    print(f"RAW MERGE: kept {before} non-ECMWF rows, wrote {after} total rows")
    print(f"WROTE: {CANDIDATE_OUT} and {RAW_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
