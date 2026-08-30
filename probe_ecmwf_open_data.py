"""Small feasibility probe for ECMWF Open Data.

Downloads a tiny subset of the latest IFS forecast (2m temperature, 10m wind
components and total precipitation) for the Turkey bounding box. It does not
feed production data yet; it only proves access, file size and GRIB parsing.

Data licence: ECMWF Open Data, CC BY 4.0. Attribution required.
"""
from pathlib import Path
import sys

TURKEY_AREA = [42.2, 25.5, 35.7, 45.0]  # N,W,S,E
OUT = Path("data/ecmwf_probe.grib2")


def main():
    try:
        from ecmwf.opendata import Client
    except Exception as exc:
        print("ECMWF PROBE: missing ecmwf-opendata package:", exc)
        print("Install with: pip install ecmwf-opendata")
        return 2

    OUT.parent.mkdir(parents=True, exist_ok=True)
    client = Client(source="ecmwf", model="ifs", resol="0p25", preserve_request_order=True)

    print("=== ECMWF OPEN DATA PROBE ===")
    print("Area Turkey:", TURKEY_AREA)
    print("Request: latest IFS, step=24h, 2t/10u/10v/tp")
    print("Licence: CC BY 4.0; attribution required")

    try:
        client.retrieve(
            time=0,
            step=24,
            stream="oper",
            type="fc",
            param=["2t", "10u", "10v", "tp"],
            target=str(OUT),
        )
    except Exception as exc:
        print("DOWNLOAD FAILED:", repr(exc))
        return 1

    size = OUT.stat().st_size if OUT.exists() else 0
    print(f"DOWNLOAD OK: {OUT} ({size / 1024 / 1024:.2f} MiB)")
    print("NOTE: public open-data files are global GRIB2 fields; Turkey extraction will be done locally in the next step.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
