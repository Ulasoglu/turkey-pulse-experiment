from __future__ import annotations

from probe_adapter2_news import Source, probe

SOURCES = [
    Source("Bilecik", "bilecik_bel_news", "https://www.bilecik.bel.tr/HaberArsivi"),
    Source("İstanbul", "istanbul_ibb_news", "https://istanbulseninhaber.ibb.istanbul/haber-kategori/guncel-haberler"),
    Source("Konya", "konya_bb_news", "https://www.konya.bel.tr/haber"),
    Source("Kilis", "kilis_bel_news", "https://www.kilis.bel.tr/index.php/category/haber/"),
    Source("Osmaniye", "osmaniye_bel_news", "https://osmaniye-bld.gov.tr/kategori/haberler"),
    Source("Yozgat", "yozgat_bel_news", "https://www.yozgat.bel.tr/"),
]


def main():
    print("=== ADAPTER 2 MUNICIPAL NEWS PROBE ===")
    print("ROUND: 5 / remaining reachable provisional or zero-output sources")
    print("MODE: read-only; production data and registry are NOT modified")
    print("TLS verification stays enabled; access-control failures are not bypassed.")
    winners = 0

    for source in SOURCES:
        print(f"\n--- {source.province} / {source.source_id} ---")
        print(f"URL: {source.url}")
        try:
            result = probe(source)
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")
            continue

        rows = result["rows"]
        dated = sum(1 for row in rows if row["date"])
        if rows:
            winners += 1
        print(f"HTTP: {result['status']} | {result['elapsed']:.2f}s | {result['bytes']} bytes")
        print(f"FINAL URL: {result['final_url']}")
        print(f"PARSED: {len(rows)} candidates | dated={dated} | detail_fetches={result['detail_fetches']}")
        if result["wp_status"]:
            print(result["wp_status"])
        strategies = {}
        for row in rows:
            strategies[row["strategy"]] = strategies.get(row["strategy"], 0) + 1
        print("STRATEGIES:", strategies)
        for index, row in enumerate(rows[:8], 1):
            print(f"  {index}. {row['date'] or 'NO_DATE'} | {row['title']}")
            print(f"     {row['strategy']} | {row['url']}")

    print("\n=== ADAPTER 2 SUMMARY ===")
    print(f"SOURCES WITH CANDIDATES: {winners}/{len(SOURCES)}")
    print("RESULT: inspect winners, then promote only validated news-only shapes into production.")


if __name__ == "__main__":
    main()
