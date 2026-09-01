import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

REGISTRY = Path("municipal_sources.json")

TURKEY_PROVINCES = {
    "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Aksaray", "Amasya", "Ankara",
    "Antalya", "Ardahan", "Artvin", "Aydın", "Balıkesir", "Bartın", "Batman", "Bayburt",
    "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı",
    "Çorum", "Denizli", "Diyarbakır", "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum",
    "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari", "Hatay", "Iğdır", "Isparta",
    "İstanbul", "İzmir", "Kahramanmaraş", "Karabük", "Karaman", "Kars", "Kastamonu",
    "Kayseri", "Kilis", "Kırıkkale", "Kırklareli", "Kırşehir", "Kocaeli", "Konya", "Kütahya",
    "Malatya", "Manisa", "Mardin", "Mersin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu",
    "Osmaniye", "Rize", "Sakarya", "Samsun", "Siirt", "Sinop", "Sivas", "Şanlıurfa",
    "Şırnak", "Tekirdağ", "Tokat", "Trabzon", "Tunceli", "Uşak", "Van", "Yalova",
    "Yozgat", "Zonguldak",
}

PROVISIONAL_STATUSES = {
    "active_test",
    "active_adapter2_candidate",
    "active_adapter2_candidate_stale",
}


def is_enabled(source, defaults):
    return bool(source.get("enabled", defaults.get("enabled", True)))


def coverage_class(status: str) -> str:
    if status == "covered_by_existing_collector":
        return "validated"
    if status in {"active", "active_validated", "active_validated_stale"}:
        return "validated"
    if status.startswith("active_adapter2_") and "candidate" not in status:
        return "validated"
    if status in PROVISIONAL_STATUSES:
        return "provisional"
    if status.startswith("paused_"):
        return "blocked"
    return "provisional"


def main():
    parser = argparse.ArgumentParser(description="Audit 81-province municipal source coverage.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when provinces are missing, duplicated, or unknown.",
    )
    args = parser.parse_args()

    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    defaults = payload.get("defaults", {})
    sources = payload.get("sources", [])

    province_to_sources = defaultdict(list)
    status_counts = Counter()
    class_counts = Counter()
    enabled_count = 0

    for source in sources:
        province = str(source.get("province", "")).strip()
        source_id = str(source.get("source_id", "")).strip()
        status = str(source.get("status", "<missing>")).strip() or "<missing>"
        province_to_sources[province].append(source_id)
        status_counts[status] += 1
        class_counts[coverage_class(status)] += 1
        if is_enabled(source, defaults):
            enabled_count += 1

    configured_provinces = set(province_to_sources) - {""}
    missing = sorted(TURKEY_PROVINCES - configured_provinces)
    unknown = sorted(configured_provinces - TURKEY_PROVINCES)
    duplicates = {
        province: ids
        for province, ids in sorted(province_to_sources.items())
        if province and len(ids) > 1
    }

    review = []
    recovery = []
    missing_status = []
    for source in sources:
        status = str(source.get("status", "")).strip()
        row = (source.get("province", "?"), source.get("source_id", "?"), status or "<missing>")
        classification = coverage_class(status)
        if classification == "provisional":
            review.append(row)
        elif classification == "blocked":
            recovery.append(row)
        if not status:
            missing_status.append(row)

    print("=== MUNICIPAL COVERAGE AUDIT ===")
    print(f"Configured sources : {len(sources)}")
    print(f"Unique provinces   : {len(configured_provinces)}/81")
    print(f"Enabled sources    : {enabled_count}")
    print(f"Disabled sources   : {len(sources) - enabled_count}")
    print(f"Validated coverage : {class_counts['validated']}/81")
    print(f"Provisional        : {class_counts['provisional']}/81")
    print(f"Blocked/recovery   : {class_counts['blocked']}/81")
    print(f"Missing provinces  : {', '.join(missing) if missing else 'NONE'}")
    print(f"Unknown provinces  : {', '.join(unknown) if unknown else 'NONE'}")

    if duplicates:
        print("Duplicate provinces:")
        for province, ids in duplicates.items():
            print(f"  - {province}: {', '.join(ids)}")
    else:
        print("Duplicate provinces: NONE")

    print("Status counts:")
    for status, count in sorted(status_counts.items()):
        print(f"  - {status}: {count}")

    print(f"Validation queue   : {len(review)}")
    for province, source_id, status in sorted(review):
        print(f"  - {province}: {source_id} [{status}]")

    print(f"Recovery queue     : {len(recovery)}")
    for province, source_id, status in sorted(recovery):
        print(f"  - {province}: {source_id} [{status}]")

    if missing_status:
        print("Sources without status:")
        for province, source_id, status in sorted(missing_status):
            print(f"  - {province}: {source_id} [{status}]")

    structural_ok = not missing and not unknown and not duplicates and len(configured_provinces) == 81
    print(f"Structural coverage: {'PASS' if structural_ok else 'FAIL'}")

    if args.strict and not structural_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
