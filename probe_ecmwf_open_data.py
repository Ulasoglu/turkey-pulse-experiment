"""ECMWF Open Data feasibility probe for Turkish province capitals.

Downloads the latest IFS 24h forecast, decodes temperature, wind and
precipitation at all 81 province-capital coordinates, then applies conservative
probe-only thresholds for derived weather signals.

IMPORTANT: these are model-derived signals, NOT official MGM warnings.
Data licence: ECMWF Open Data, CC BY 4.0. Attribution required.
"""
from pathlib import Path
import math
import sys

OUT = Path("data/ecmwf_probe.grib2")

RAIN_NOTICE_MM = 15.0
RAIN_HIGH_MM = 30.0
WIND_NOTICE_KMH = 40.0
WIND_HIGH_KMH = 60.0
HEAT_NOTICE_C = 35.0
HEAT_HIGH_C = 40.0
COLD_NOTICE_C = -10.0
COLD_HIGH_C = -20.0

PROVINCES = {
    "Adana": (37.00, 35.32), "Adıyaman": (37.76, 38.28), "Afyonkarahisar": (38.76, 30.54),
    "Ağrı": (39.72, 43.05), "Aksaray": (38.37, 34.03), "Amasya": (40.65, 35.83),
    "Ankara": (39.93, 32.86), "Antalya": (36.89, 30.70), "Ardahan": (41.11, 42.70),
    "Artvin": (41.18, 41.82), "Aydın": (37.85, 27.84), "Balıkesir": (39.65, 27.89),
    "Bartın": (41.63, 32.34), "Batman": (37.89, 41.13), "Bayburt": (40.26, 40.23),
    "Bilecik": (40.15, 29.98), "Bingöl": (38.89, 40.50), "Bitlis": (38.40, 42.11),
    "Bolu": (40.74, 31.61), "Burdur": (37.72, 30.29), "Bursa": (40.19, 29.06),
    "Çanakkale": (40.15, 26.41), "Çankırı": (40.60, 33.62), "Çorum": (40.55, 34.95),
    "Denizli": (37.78, 29.10), "Diyarbakır": (37.91, 40.24), "Düzce": (40.84, 31.16),
    "Edirne": (41.68, 26.56), "Elazığ": (38.68, 39.23), "Erzincan": (39.75, 39.49),
    "Erzurum": (39.90, 41.27), "Eskişehir": (39.77, 30.52), "Gaziantep": (37.07, 37.38),
    "Giresun": (40.91, 38.39), "Gümüşhane": (40.46, 39.48), "Hakkari": (37.58, 43.74),
    "Hatay": (36.20, 36.16), "Iğdır": (39.92, 44.05), "Isparta": (37.76, 30.55),
    "İstanbul": (41.01, 28.98), "İzmir": (38.42, 27.14), "Kahramanmaraş": (37.58, 36.93),
    "Karabük": (41.20, 32.63), "Karaman": (37.18, 33.22), "Kars": (40.60, 43.10),
    "Kastamonu": (41.39, 33.78), "Kayseri": (38.72, 35.49), "Kırıkkale": (39.84, 33.51),
    "Kırklareli": (41.74, 27.23), "Kırşehir": (39.15, 34.16), "Kilis": (36.72, 37.12),
    "Kocaeli": (40.77, 29.94), "Konya": (37.87, 32.49), "Kütahya": (39.42, 29.98),
    "Malatya": (38.35, 38.31), "Manisa": (38.62, 27.43), "Mardin": (37.31, 40.74),
    "Mersin": (36.80, 34.63), "Muğla": (37.22, 28.36), "Muş": (38.73, 41.49),
    "Nevşehir": (38.62, 34.71), "Niğde": (37.97, 34.68), "Ordu": (40.98, 37.88),
    "Osmaniye": (37.07, 36.25), "Rize": (41.02, 40.52), "Sakarya": (40.77, 30.40),
    "Samsun": (41.29, 36.33), "Siirt": (37.93, 41.94), "Sinop": (42.03, 35.15),
    "Sivas": (39.75, 37.02), "Şanlıurfa": (37.17, 38.79), "Şırnak": (37.52, 42.46),
    "Tekirdağ": (40.98, 27.51), "Tokat": (40.31, 36.55), "Trabzon": (41.00, 39.72),
    "Tunceli": (39.11, 39.55), "Uşak": (38.68, 29.41), "Van": (38.49, 43.38),
    "Yalova": (40.65, 29.27), "Yozgat": (39.82, 34.81), "Zonguldak": (41.45, 31.79),
}


def read_fields(path):
    from eccodes import codes_grib_new_from_file, codes_get, codes_get_array, codes_release
    fields = {}
    with path.open("rb") as fh:
        while True:
            gid = codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                short = codes_get(gid, "shortName")
                fields[short] = (
                    codes_get_array(gid, "latitudes"),
                    codes_get_array(gid, "longitudes"),
                    codes_get_array(gid, "values"),
                )
            finally:
                codes_release(gid)
    return fields


def build_province_indices(field):
    """Find each province's nearest grid point once and reuse it for all fields."""
    import numpy as np
    lats, lons, _ = field
    lats = np.asarray(lats)
    lons = np.asarray(lons)
    lons = np.where(lons > 180, lons - 360, lons)
    indices = {}
    for province, (lat, lon) in PROVINCES.items():
        distances = (lats - lat) ** 2 + (lons - lon) ** 2
        indices[province] = int(np.argmin(distances))
    return indices


def value_at_index(field, index):
    return float(field[2][index])


def nearest_value(field, lat, lon):
    """Compatibility helper for one-off lookups; production code should cache indices."""
    import numpy as np
    lats, lons, vals = field
    lats = np.asarray(lats)
    lons = np.asarray(lons)
    lons = np.where(lons > 180, lons - 360, lons)
    idx = int(np.argmin((lats - lat) ** 2 + (lons - lon) ** 2))
    return float(vals[idx])


def derive_signals(row):
    province, temp_c, wind_kmh, precip_mm = row
    signals = []
    if precip_mm >= RAIN_NOTICE_MM:
        severity = "HIGH" if precip_mm >= RAIN_HIGH_MM else "NOTICE"
        signals.append((severity, "HEAVY_RAIN", province, f"{precip_mm:.1f} mm/24h"))
    if wind_kmh >= WIND_NOTICE_KMH:
        severity = "HIGH" if wind_kmh >= WIND_HIGH_KMH else "NOTICE"
        signals.append((severity, "STRONG_WIND", province, f"{wind_kmh:.1f} km/h"))
    if temp_c >= HEAT_NOTICE_C:
        severity = "HIGH" if temp_c >= HEAT_HIGH_C else "NOTICE"
        signals.append((severity, "HEAT", province, f"{temp_c:.1f} C"))
    if temp_c <= COLD_NOTICE_C:
        severity = "HIGH" if temp_c <= COLD_HIGH_C else "NOTICE"
        signals.append((severity, "COLD", province, f"{temp_c:.1f} C"))
    return signals


def main():
    try:
        from ecmwf.opendata import Client
        import eccodes  # noqa: F401
    except Exception as exc:
        print("ECMWF PROBE dependency missing:", exc)
        return 2

    OUT.parent.mkdir(parents=True, exist_ok=True)
    client = Client(source="ecmwf", model="ifs", resol="0p25", preserve_request_order=True)
    print("=== ECMWF 81-PROVINCE WEATHER SIGNAL PROBE ===")
    print("Request: latest IFS, +24h, 2t/10u/10v/tp")
    print("Licence: CC BY 4.0; attribution required")
    print("IMPORTANT: derived model signals; NOT official MGM warnings")

    try:
        client.retrieve(time=0, step=24, stream="oper", type="fc",
                        param=["2t", "10u", "10v", "tp"], target=str(OUT))
    except Exception as exc:
        print("DOWNLOAD FAILED:", repr(exc))
        return 1

    print(f"DOWNLOAD OK: {OUT} ({OUT.stat().st_size / 1024 / 1024:.2f} MiB)")
    fields = read_fields(OUT)
    needed = {"2t", "10u", "10v", "tp"}
    print("Decoded fields:", sorted(fields))
    if not needed.issubset(fields):
        print("MISSING FIELDS:", sorted(needed - set(fields)))
        return 1

    indices = build_province_indices(fields["2t"])
    rows = []
    for province in PROVINCES:
        idx = indices[province]
        temp_c = value_at_index(fields["2t"], idx) - 273.15
        u = value_at_index(fields["10u"], idx)
        v = value_at_index(fields["10v"], idx)
        wind_kmh = math.hypot(u, v) * 3.6
        precip_mm = value_at_index(fields["tp"], idx) * 1000.0
        rows.append((province, temp_c, wind_kmh, precip_mm))

    print(f"PROVINCES DECODED: {len(rows)}/81")
    all_signals = [signal for row in rows for signal in derive_signals(row)]
    order = {"HIGH": 0, "NOTICE": 1}
    all_signals.sort(key=lambda s: (order[s[0]], s[1], s[2]))
    print("=== DERIVED WEATHER SIGNALS ===")
    if not all_signals:
        print("NONE: no province crosses the conservative thresholds")
    else:
        for severity, kind, province, value in all_signals:
            print(f"{severity} | {kind} | {province} | {value}")
    print(f"SIGNAL COUNT: {len(all_signals)} across {len(set(s[2] for s in all_signals))} provinces")
    print("PROBE ONLY: no production weather signals written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
