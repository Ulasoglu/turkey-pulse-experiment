from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INFILE = ROOT / "data" / "filtered_signals.jsonl"
OUTFILE = ROOT / "data" / "map_signals.jsonl"
CORE_MANIFEST = ROOT / "sources.json"
MUNICIPAL_MANIFEST = ROOT / "municipal_sources.json"
MUNICIPAL_OVERRIDES = ROOT / "municipal_sources_overrides.json"
ENGINE_VERSION = "signal-engine-v10-service-inflections"

CATEGORY_RULES = [
    ("WEATHER", {"uyarı", "sağanak", "yağış", "fırtına", "rüzgâr", "rüzgar", "sıcak", "sıcaklık", "sel", "taşkın", "heyelan"}),
    ("TRAFFIC", {"trafik", "ulaşım", "yol", "cadde", "sokak", "köprü", "tünel", "istasyon", "metro", "tramvay", "izban", "otobüs", "vapur", "sefer"}),
    ("UTILITY", {"elektrik kesintisi", "su kesintisi", "doğalgaz", "arıza", "kesinti"}),
    ("INFRASTRUCTURE", {"altyapı", "yenileme", "bakım", "onarım", "asfalt", "kanalizasyon", "inşaat", "proje", "genişletme"}),
    ("EVENT", {"etkinlik", "festival", "konser", "sergi", "tiyatro", "sinema", "fuar", "şenlik", "turnuva", "yarış", "gösteri", "söyleşi", "atölye"}),
]
EVENT_CATEGORY_TERMS = {"etkinlik", "festival", "konser", "sergi", "tiyatro", "sinema", "fuar", "şenlik", "turnuva", "yarış", "gösteri", "söyleşi", "atölye"}
SERVICE_CATEGORY_TERMS = {"başvuru", "kayıt", "destek", "yardım", "burs", "hibe", "müracaat", "kurs"}
SERVICE_STEM_PATTERN = re.compile(
    r"(?<!\w)(?:başvuru|kayıt|destek|yardım|burs|hibe|müracaat|kurs)\w*",
    flags=re.UNICODE,
)
HIGH_RELEVANCE_TERMS = {"uyarı", "kapatıldı", "kapatılacak", "kesintisi", "kesinti", "arıza", "trafik", "ulaşım", "deprem", "yangın", "sağanak", "fırtına", "yağış", "sel", "taşkın", "heyelan"}
MEDIUM_RELEVANCE_TERMS = {"etkinlik", "festival", "konser", "sergi", "tiyatro", "sinema", "fuar", "şenlik", "turnuva", "yarış", "yenileme", "altyapı", "bakım", "onarım", "asfalt", "kanalizasyon", "proje", "başvuru", "kayıt", "destek", "yardım", "burs", "hibe"}
LIFETIMES = {
    "EARTHQUAKE": timedelta(hours=24),
    "WEATHER": timedelta(hours=24),
    "TRAFFIC": timedelta(hours=24),
    "UTILITY": timedelta(hours=24),
    "EVENT": timedelta(days=7),
    "INFRASTRUCTURE": timedelta(days=7),
    "OTHER": timedelta(days=3),
}
NOW_WINDOWS = {
    "EARTHQUAKE": timedelta(hours=3),
    "WEATHER": timedelta(hours=6),
    "TRAFFIC": timedelta(hours=6),
    "UTILITY": timedelta(hours=6),
    "EVENT": timedelta(hours=24),
    "INFRASTRUCTURE": timedelta(hours=24),
    "OTHER": timedelta(hours=24),
}


def text(v):
    return str(v or "").strip()


def normalize(v):
    return " ".join(text(v).translate(str.maketrans({"I": "i", "İ": "i", "ı": "i"})).casefold().split())


def contains_term(h, t):
    return re.search(r"(?<!\w)" + re.escape(normalize(t)).replace(r"\ ", r"\s+") + r"(?!\w)", h, flags=re.UNICODE) is not None


def has_any(h, terms):
    return any(contains_term(h, t) for t in terms)


def parse_iso(v):
    raw = text(v)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_municipal_rows():
    if not MUNICIPAL_MANIFEST.exists():
        return {}, {"max_age_days": 7}

    payload = json.loads(MUNICIPAL_MANIFEST.read_text(encoding="utf-8"))
    defaults = payload.get("defaults") or {"max_age_days": 7}
    by_id = {}
    for row in payload.get("sources", []):
        source_id = text(row.get("source_id"))
        if source_id:
            by_id[source_id] = dict(row)

    if MUNICIPAL_OVERRIDES.exists():
        patch = json.loads(MUNICIPAL_OVERRIDES.read_text(encoding="utf-8"))
        for addition in patch.get("additions", []):
            source_id = text(addition.get("source_id"))
            if source_id:
                by_id.setdefault(source_id, {}).update(addition)
        for override in patch.get("overrides", []):
            source_id = text(override.get("source_id"))
            if source_id in by_id:
                by_id[source_id].update(override)

    return by_id, defaults


def load_policies():
    manifest = json.loads(CORE_MANIFEST.read_text(encoding="utf-8"))
    policies = {s["id"]: s.get("freshness_policy", {}) for s in manifest.get("sources", []) if s.get("id")}

    municipal_rows, defaults = load_municipal_rows()
    for source_id, row in municipal_rows.items():
        policies[source_id] = {
            "kind": "news",
            "max_age_days": int(row.get("max_age_days", defaults.get("max_age_days", 7))),
        }
    return policies


def source_is_event(row, policies):
    return policies.get(text(row.get("source_id")), {}).get("kind") == "event" or bool(row.get("event_start_at"))


def service_opportunity(row):
    title = normalize(row.get("title"))
    has_service = bool(SERVICE_STEM_PATTERN.search(title)) or has_any(title, SERVICE_CATEGORY_TERMS)
    return has_service and not has_any(title, EVENT_CATEGORY_TERMS)


def detect_category(row, policies):
    sid = text(row.get("source_id"))
    title = normalize(row.get("title"))
    filter_reason = text(row.get("filter_reason"))

    if sid == "afad_event_service":
        return "EARTHQUAKE"
    if sid == "ecmwf_open_data_weather" and row.get("derived_signal") is True:
        return "WEATHER"

    if filter_reason.startswith(("active_local_impact:", "municipal_local_impact:")):
        return "INFRASTRUCTURE"
    if filter_reason.startswith("public_event:"):
        return "EVENT"
    if filter_reason.startswith(("municipal_service:", "ambiguous_event_service:")):
        return "OTHER"

    if source_is_event(row, policies):
        return "OTHER" if service_opportunity(row) else "EVENT"

    for category, terms in CATEGORY_RULES:
        if has_any(title, terms):
            return category
    return "OTHER"


def detect_relevance(row, category, policies):
    sid = text(row.get("source_id"))
    filter_decision = text(row.get("filter_decision"))
    filter_reason = text(row.get("filter_reason"))

    if sid == "ecmwf_open_data_weather" and category == "WEATHER":
        return "HIGH" if filter_decision == "KEEP" else "LOW"
    if source_is_event(row, policies):
        return "MEDIUM"
    if filter_reason.startswith("critical_local_signal:"):
        return "HIGH"
    if filter_reason.startswith("public_event:"):
        return "MEDIUM"
    if filter_reason.startswith(("active_local_impact:", "municipal_local_impact:", "municipal_service:", "ambiguous_event_service:")):
        return "MEDIUM"

    title = normalize(row.get("title"))
    if category == "EARTHQUAKE":
        try:
            magnitude = float(row.get("magnitude"))
        except (TypeError, ValueError):
            return "MEDIUM"
        return "HIGH" if magnitude >= 4 else "MEDIUM"
    if has_any(title, HIGH_RELEVANCE_TERMS):
        return "HIGH"
    if has_any(title, MEDIUM_RELEVANCE_TERMS):
        return "MEDIUM"
    return "MEDIUM" if filter_decision == "KEEP" else "LOW"


def event_freshness(row, now, policy):
    start = parse_iso(row.get("event_start_at"))
    end = parse_iso(row.get("event_end_at"))
    if start is None:
        return "UNKNOWN", None, None
    require_not_ended = bool(policy.get("require_not_ended", True))
    max_started_days = int(policy.get("max_started_days", 7))
    if end is not None and require_not_ended and now > end:
        return "OLD", max(now - end, timedelta(0)), end
    if now < start:
        until = start - now
        status = "NOW" if until <= timedelta(hours=24) else "RECENT"
        expires = end or (start + timedelta(days=max_started_days))
        return status, timedelta(0), expires
    age = max(now - start, timedelta(0))
    if age > timedelta(days=max_started_days):
        return "OLD", age, end or (start + timedelta(days=max_started_days))
    expires = end if end is not None else start + timedelta(days=max_started_days)
    return "NOW", age, expires


def freshness(row, category, now, policies):
    sid = text(row.get("source_id"))
    policy = policies.get(sid, {})
    if category == "EVENT" and row.get("event_start_at"):
        return event_freshness(row, now, policy)
    occurred = parse_iso(row.get("published_at")) or parse_iso(row.get("collected_at"))
    if occurred is None:
        return "UNKNOWN", None, None
    if occurred > now + timedelta(hours=6):
        return "UNKNOWN", None, None
    age = max(now - occurred, timedelta(0))
    expires = occurred + LIFETIMES[category]
    if now >= expires:
        return "OLD", age, expires
    return ("NOW" if age <= NOW_WINDOWS[category] else "RECENT"), age, expires


def decide(row, category, relevance, fresh):
    filter_decision = text(row.get("filter_decision"))
    filter_reason = text(row.get("filter_reason"))
    if filter_decision == "DROP" or fresh == "OLD":
        return "HIDE"
    if fresh == "UNKNOWN":
        return "REVIEW" if relevance in {"HIGH", "MEDIUM"} else "HIDE"
    if category == "EARTHQUAKE" and relevance in {"HIGH", "MEDIUM"}:
        return "SHOW"
    if category == "EVENT" and relevance in {"HIGH", "MEDIUM"}:
        return "SHOW"
    if filter_reason.startswith("municipal_service:") and filter_decision == "KEEP":
        return "SHOW"
    if category == "OTHER" and service_opportunity(row) and filter_decision == "KEEP":
        return "SHOW"
    if relevance == "HIGH" and fresh in {"NOW", "RECENT"}:
        return "SHOW"
    if relevance == "MEDIUM":
        return "REVIEW"
    return "HIDE"


def load_rows():
    if not INFILE.exists():
        raise SystemExit(f"Missing input file: {INFILE}")
    rows = []
    bad = 0
    with INFILE.open("r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
                print(f"SKIP invalid JSON line {n}")
    return rows, bad


def main():
    rows, bad = load_rows()
    policies = load_policies()
    now = datetime.now(timezone.utc)
    results = []
    vis = Counter()
    cats = Counter()
    rels = Counter()
    freshs = Counter()

    for row in rows:
        cat = detect_category(row, policies)
        rel = detect_relevance(row, cat, policies)
        fresh, age, expires = freshness(row, cat, now, policies)
        decision = decide(row, cat, rel, fresh)
        out = dict(row)
        out.update(
            signal_category=cat,
            signal_relevance=rel,
            signal_freshness=fresh,
            signal_age_minutes=round(age.total_seconds() / 60, 1) if age is not None else None,
            expires_at=expires.isoformat() if expires else None,
            map_decision=decision,
            signal_engine_version=ENGINE_VERSION,
        )
        results.append(out)
        vis[decision] += 1
        cats[cat] += 1
        rels[rel] += 1
        freshs[fresh] += 1

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTFILE.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("\n=== TURKEY PULSE SIGNAL ENGINE ===")
    print(f"VERSION: {ENGINE_VERSION}")
    print(f"AS OF:   {now.isoformat()}")
    print(f"INPUT:   {len(rows)}")
    print(f"SHOW:    {vis['SHOW']}")
    print(f"REVIEW:  {vis['REVIEW']}")
    print(f"HIDE:    {vis['HIDE']}")
    print(f"BAD JSON LINES: {bad}")
    print("\nFreshness:")
    for k in ("NOW", "RECENT", "OLD", "UNKNOWN"):
        print(f"  {k}: {freshs[k]}")
    print("\nCategories:")
    for k, v in sorted(cats.items()):
        print(f"  {k}: {v}")
    print("\nRelevance:")
    for k, v in sorted(rels.items()):
        print(f"  {k}: {v}")
    print(f"\nWrote: {OUTFILE}")


if __name__ == "__main__":
    main()
