from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw_signals.jsonl"
OUT = ROOT / "data" / "filtered_signals.jsonl"
CORE_MANIFEST = ROOT / "sources.json"
MUNICIPAL_MANIFEST = ROOT / "municipal_sources.json"
MUNICIPAL_OVERRIDES = ROOT / "municipal_sources_overrides.json"
FILTER_VERSION = "rules-v11-live-utility"
TURKEY_TZ = timezone(timedelta(hours=3))

GENERIC_DROP_TITLES = {"haberler", "haber", "duyurular", "duyuru", "gündem", "guncel", "güncel"}
MAX_FUTURE_NEWS_SKEW = timedelta(hours=6)

CRITICAL_TERMS = {
    "uyarı", "sağanak", "yağış", "fırtına", "kuvvetli rüzgâr", "kuvvetli rüzgar",
    "aşırı sıcak", "yangın", "sel", "taşkın", "heyelan",
    "trafik", "ulaşım", "metro", "tramvay", "izban", "otobüs", "vapur", "sefer",
    "yol kapalı", "yol kapatıldı", "yol kapatılacak", "trafiğe kapalı",
    "trafiğe kapatıldı", "trafiğe kapatılacak",
    "elektrik kesintisi", "su kesintisi", "doğalgaz", "arıza", "kesinti",
}

EVENT_TERMS = {
    "etkinlik", "festival", "konser", "sergi", "tiyatro", "sinema", "fuar",
    "şenlik", "turnuva", "yarış", "gösteri", "söyleşi", "atölye",
}
SERVICE_TERMS = {
    "başvuru", "kayıt", "destek", "yardım", "burs", "hibe", "dağıtım", "kurs",
    "ücretsiz", "indirimli", "hak sahipleri", "müracaat",
}

LOCAL_IMPACT_TERMS = {
    "altyapı", "yenileme", "bakım", "onarım", "asfalt", "kazı", "kanalizasyon",
    "içme suyu", "yağmur suyu", "yol", "cadde", "sokak", "köprü", "tünel",
    "otopark", "pazar yeri", "tesis", "inşaat", "çalışma", "çalışmalar", "genişletme",
}
ACTIVE_MARKERS = {
    "başladı", "başlıyor", "başlayacak", "sürüyor", "sürdürülüyor", "sürdürülen",
    "devam ediyor", "devam edecek", "kapatılacak", "açılacak", "hizmete girecek",
    "uygulanacak", "yenilenecek", "çağırdı", "duyuruldu",
}

PR_TERMS = {
    "baş tacımız", "ziyaret etti", "teşekkür", "mesajı", "ağırladı", "buluştu",
    "protokol", "heyet", "gurur", "ödül", "başarı", "eğitimini tamamladı",
    "personeline eğitim", "personele özel eğitim", "yapay zekâ desteği",
    "yapay zeka desteği", "tebrik etti",
}
RETROSPECTIVE_TERMS = {
    "gerçekleştirildi", "düzenlendi", "tamamlandı", "sona erdi", "gerçekleşti",
    "kutlandı", "taçlandı", "yoğun ilgi gördü", "katılım sağladı", "bir araya geldi",
    "incelemelerde bulundu", "ziyaret gerçekleştirdi", "ödüllendirildi",
    "buluşma noktası oldu", "yolculuk yaptı", "avrupa beşincisi", "çifte gurur",
}

MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
    "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7,
    "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
}
DAY_MONTH_PATTERN = re.compile(
    r"(?<!\d)([0-3]?\d)\s+(ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik)(?!\w)",
    re.IGNORECASE,
)
FIXED_EVENT_DATES = {
    "zafer bayramı": (8, 30),
    "cumhuriyet bayramı": (10, 29),
    "ulusal egemenlik ve çocuk bayramı": (4, 23),
    "atatürk'ü anma gençlik ve spor bayramı": (5, 19),
    "atatürk’ü anma gençlik ve spor bayramı": (5, 19),
    "demokrasi ve milli birlik günü": (7, 15),
}


def text(value):
    return str(value or "").strip()


def normalize(value):
    return " ".join(text(value).translate(str.maketrans({"I": "i", "İ": "i", "ı": "i"})).casefold().split())


def contains_term(haystack, term):
    pattern = r"(?<!\w)" + re.escape(normalize(term)).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, haystack, flags=re.UNICODE) is not None


def term_hits(title_n, terms):
    return sorted(term for term in terms if contains_term(title_n, term))


def parse_iso(value):
    raw = text(value)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def infer_event_date_from_title(title_n, published, now):
    base_local = (published or now).astimezone(TURKEY_TZ)
    year = base_local.year
    candidates = []

    for match in DAY_MONTH_PATTERN.finditer(title_n):
        try:
            day = int(match.group(1))
            month = MONTHS.get(normalize(match.group(2)))
            if month:
                candidates.append(datetime(year, month, day, tzinfo=TURKEY_TZ).date())
        except ValueError:
            continue

    for marker, (month, day) in FIXED_EVENT_DATES.items():
        if contains_term(title_n, marker):
            candidates.append(datetime(year, month, day, tzinfo=TURKEY_TZ).date())

    if not candidates:
        return None
    return max(candidates)


def load_municipal_rows():
    if not MUNICIPAL_MANIFEST.exists():
        return {}, {"max_age_days": 7, "enabled": True}

    payload = json.loads(MUNICIPAL_MANIFEST.read_text(encoding="utf-8"))
    defaults = payload.get("defaults") or {"max_age_days": 7, "enabled": True}
    by_id = {}
    for row in payload.get("sources", []):
        source_id = text(row.get("source_id"))
        if source_id:
            by_id[source_id] = dict(row)

    if MUNICIPAL_OVERRIDES.exists():
        patch = json.loads(MUNICIPAL_OVERRIDES.read_text(encoding="utf-8"))
        for addition in patch.get("additions", []):
            source_id = text(addition.get("source_id"))
            if not source_id:
                continue
            by_id.setdefault(source_id, {}).update(addition)
        for override in patch.get("overrides", []):
            source_id = text(override.get("source_id"))
            if source_id in by_id:
                by_id[source_id].update(override)

    return by_id, defaults


def load_source_context():
    manifest = json.loads(CORE_MANIFEST.read_text(encoding="utf-8"))
    policies = {s["id"]: s.get("freshness_policy", {}) for s in manifest.get("sources", []) if s.get("id")}

    municipal_rows, defaults = load_municipal_rows()
    municipal_ids = set(municipal_rows)
    paused_municipal_ids = set()
    for source_id, row in municipal_rows.items():
        max_age_days = int(row.get("max_age_days", defaults.get("max_age_days", 7)))
        policies[source_id] = {"kind": "news", "max_age_days": max_age_days}
        enabled = bool(row.get("enabled", defaults.get("enabled", True)))
        if not enabled:
            paused_municipal_ids.add(source_id)

    return policies, municipal_ids, paused_municipal_ids


def freshness_decision(row, policy, now):
    kind = policy.get("kind")
    if not kind:
        return None

    if kind == "event":
        start = parse_iso(row.get("event_start_at"))
        end = parse_iso(row.get("event_end_at"))
        if start is None:
            return "DROP", "freshness_event_missing_start"
        max_started_days = int(policy.get("max_started_days", 7))
        if start < now - timedelta(days=max_started_days):
            return "DROP", "freshness_event_stale_start"
        if policy.get("require_not_ended", True) and (end or start) < now:
            return "DROP", "freshness_event_ended"
        return "KEEP", "freshness_event_valid"

    if kind == "news":
        published = parse_iso(row.get("published_at"))
        if published is None:
            return None
        if published > now + MAX_FUTURE_NEWS_SKEW:
            return "DROP", "freshness_news_future_timestamp"
        max_age_days = int(policy.get("max_age_days", 7))
        if published < now - timedelta(days=max_age_days):
            return "DROP", "freshness_news_too_old"
        return None

    return None


def is_generic_municipal(row, source_id, municipal_ids):
    return source_id in municipal_ids or text(row.get("source_type")) == "municipal_news"


def classify(row, policies, municipal_ids, paused_municipal_ids, now=None):
    now = now or datetime.now(timezone.utc)
    source_id = text(row.get("source_id"))
    title = text(row.get("title"))
    title_n = normalize(title)
    summary = normalize(row.get("raw_summary"))

    if summary.startswith("error:"):
        return "DROP", "collector_error"
    if source_id == "bursa_acik_yesil_catalog":
        return "DROP", "legacy_page_watch_not_event"
    if source_id in paused_municipal_ids:
        return "DROP", "municipal_source_paused"

    if source_id == "ecmwf_open_data_weather":
        if row.get("derived_signal") is not True:
            return "DROP", "ecmwf_not_derived_signal"
        if row.get("official_warning") is not False:
            return "DROP", "ecmwf_official_warning_guard"
        if text(row.get("rights_status")) != "open_license_verified":
            return "DROP", "ecmwf_rights_guard"
        if text(row.get("weather_kind")) not in {"HEAVY_RAIN", "STRONG_WIND", "HEAT", "COLD"}:
            return "DROP", "ecmwf_unknown_weather_kind"
        return "KEEP", "ecmwf_threshold_signal"

    fresh = freshness_decision(row, policies.get(source_id, {}), now)
    if fresh is not None:
        return fresh

    if source_id == "afad_event_service" and row.get("event_id") is None:
        return "DROP", "afad_non_event_record"
    if source_id == "afad_event_service":
        try:
            magnitude = float(row.get("magnitude"))
        except (TypeError, ValueError):
            return "DROP", "afad_missing_magnitude"
        if magnitude >= 4.0:
            return "KEEP", "earthquake_m4_plus"
        if magnitude >= 3.0:
            return "KEEP", "earthquake_m3_plus"
        return "DROP", "earthquake_below_m3"

    if not title:
        return "DROP", "missing_title"
    if title_n in {normalize(x) for x in GENERIC_DROP_TITLES}:
        return "DROP", "generic_navigation_title"

    critical_hits = term_hits(title_n, CRITICAL_TERMS)
    retro_hits = term_hits(title_n, RETROSPECTIVE_TERMS)
    pr_hits = term_hits(title_n, PR_TERMS)
    event_hits = term_hits(title_n, EVENT_TERMS)
    service_hits = term_hits(title_n, SERVICE_TERMS)
    local_hits = term_hits(title_n, LOCAL_IMPACT_TERMS)
    active_hits = term_hits(title_n, ACTIVE_MARKERS)
    generic_municipal = is_generic_municipal(row, source_id, municipal_ids)

    if critical_hits:
        return "KEEP", "critical_local_signal:" + ",".join(critical_hits[:3])
    if retro_hits:
        return "DROP", "retrospective:" + ",".join(retro_hits[:3])
    if pr_hits:
        return "DROP", "likely_pr:" + ",".join(pr_hits[:3])
    if local_hits and active_hits:
        return "KEEP", "active_local_impact:" + ",".join((local_hits + active_hits)[:4])
    if event_hits:
        if generic_municipal:
            published = parse_iso(row.get("published_at"))
            event_date = infer_event_date_from_title(title_n, published, now)
            if event_date is not None and event_date < now.astimezone(TURKEY_TZ).date():
                return "DROP", "past_event_announcement"
            if service_hits and not active_hits:
                return "MAYBE", "ambiguous_event_service:" + ",".join((event_hits + service_hits)[:4])
        return "KEEP", "public_event:" + ",".join(event_hits[:3])
    if service_hits:
        return "KEEP", "municipal_service:" + ",".join(service_hits[:3])
    if local_hits:
        return "MAYBE", "municipal_local_impact:" + ",".join(local_hits[:3])

    if source_id == "akom_istanbul_news":
        return "MAYBE", "akom_needs_review"
    if generic_municipal:
        return "DROP", "municipal_low_impact"
    return "MAYBE", "unclassified_source"


def load_rows():
    if not RAW.exists():
        raise SystemExit(f"Missing input file: {RAW}")
    rows = []
    bad = 0
    with RAW.open("r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
                print(f"SKIP invalid JSON line {n}")
    return rows, bad


def duplicate_key(row):
    title_n = normalize(row.get("title"))
    return (text(row.get("source_id")), title_n, text(row.get("published_at"))) if title_n else None


def main():
    rows, bad = load_rows()
    policies, municipal_ids, paused_municipal_ids = load_source_context()
    results = []
    counts = Counter()
    source_counts = Counter()
    municipal_counts = Counter()
    reason_counts = Counter()
    seen = set()
    now = datetime.now(timezone.utc)

    for row in rows:
        decision, reason = classify(row, policies, municipal_ids, paused_municipal_ids, now)
        if decision in {"KEEP", "MAYBE"}:
            key = duplicate_key(row)
            if key is not None:
                if key in seen:
                    decision, reason = "DROP", "duplicate_title_same_source_date"
                else:
                    seen.add(key)

        out = dict(row)
        out.update(filter_decision=decision, filter_reason=reason, filter_version=FILTER_VERSION)
        results.append(out)
        counts[decision] += 1
        reason_counts[reason.split(":", 1)[0]] += 1
        source_id = text(row.get("source_id"))
        source_counts[(source_id, decision)] += 1
        if is_generic_municipal(row, source_id, municipal_ids):
            municipal_counts[decision] += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("\n=== TURKEY PULSE FILTER REPORT ===")
    print(f"VERSION: {FILTER_VERSION}")
    print(f"RAW:   {len(rows)}")
    print(f"KEEP:  {counts['KEEP']}")
    print(f"MAYBE: {counts['MAYBE']}")
    print(f"DROP:  {counts['DROP']}")
    print(f"BAD JSON LINES: {bad}")
    print(f"MUNICIPAL REGISTRY: {len(municipal_ids)} known, {len(paused_municipal_ids)} paused")
    print(
        "MUNICIPAL ROWS: "
        f"KEEP={municipal_counts['KEEP']} MAYBE={municipal_counts['MAYBE']} DROP={municipal_counts['DROP']}"
    )
    print(
        "QUALITY GATE: "
        f"low_impact_drop={reason_counts['municipal_low_impact']} "
        f"retrospective_drop={reason_counts['retrospective']} "
        f"pr_drop={reason_counts['likely_pr']} "
        f"future_news_drop={reason_counts['freshness_news_future_timestamp']} "
        f"past_event_drop={reason_counts['past_event_announcement']} "
        f"ambiguous_event_service={reason_counts['ambiguous_event_service']} "
        f"service_keep={reason_counts['municipal_service']}"
    )
    print("\nBy source:")
    for sid in sorted({text(r.get("source_id")) for r in rows}):
        print(
            f"  {sid}: KEEP={source_counts[(sid, 'KEEP')]} "
            f"MAYBE={source_counts[(sid, 'MAYBE')]} DROP={source_counts[(sid, 'DROP')]}"
        )
    print(f"\nWrote: {OUT}")


if __name__ == "__main__":
    main()
