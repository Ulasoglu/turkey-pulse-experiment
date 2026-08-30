"""Staged ECMWF weather collector.

Creates candidate weather signals for all Turkish provinces from ECMWF Open
Data, but deliberately writes them to a separate review file instead of the
production raw signal stream. This lets us validate wording, thresholds and
pipeline shape before public map integration.

These are model-derived signals, NOT official MGM warnings.
Licence: ECMWF Open Data, CC BY 4.0. Attribution required.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import math

from ecmwf.opendata import Client

from probe_ecmwf_open_data import (
    PROVINCES,
    OUT,
    derive_signals,
    nearest_value,
    read_fields,
)

CANDIDATE_OUT = Path("data/ecmwf_weather_candidates.jsonl")
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

    generated_at = datetime.now(timezone.utc)
    valid_at = generated_at.replace(microsecond=0)
    candidates = []

    for province, (lat, lon) in PROVINCES.items():
        temp_c = nearest_value(fields["2t"], lat, lon) - 273.15
        u = nearest_value(fields["10u"], lat, lon)
        v = nearest_value(fields["10v"], lat, lon)
        wind_kmh = math.hypot(u, v) * 3.6
        precip_mm = nearest_value(fields["tp"], lat, lon) * 1000.0
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
                "event_time": valid_at.isoformat(),
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
                "review_only": True,
            })

    return candidates


def main():
    print("=== ECMWF STAGED WEATHER COLLECTOR ===")
    print("MODE: review-only; production raw signals are NOT modified")
    print("IMPORTANT: model-derived signals; NOT official MGM warnings")
    candidates = build_candidates()
    CANDIDATE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CANDIDATE_OUT.open("w", encoding="utf-8") as fh:
        for item in candidates:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"CANDIDATES: {len(candidates)}")
    for item in candidates:
        print(f"{item['severity']} | {item['weather_kind']} | {item['province']} | {item['title']}")
    print(f"WROTE: {CANDIDATE_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
