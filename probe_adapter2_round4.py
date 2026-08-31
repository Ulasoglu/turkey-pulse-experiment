from __future__ import annotations

from probe_adapter2_news import Source, probe

SOURCES = [
    Source("Isparta", "isparta_bel_news", "https://www.isparta.bel.tr/haberler"),
    Source("Bolu", "bolu_bel_news", "https://www.bolu.bel.tr/haberler/"),
    Source("Kırşehir", "kirsehir_bel_news", "https://www.kirsehir.bel.tr/haberler"),
    Source("Kütahya", "kutahya_bel_news", "https://www.kutahya.bel.tr/"),
    Source("Elazığ", "elazig_bel_news", "https://www.elazig.bel.tr/"),
    Source("Nevşehir", "nevsehir_bel_news", "https://www.nevsehir.bel.tr/index.php?option=comcontent"),
    Source("Erzurum", "erzurum_bb_news", "https://www.erzurum.bel.tr/haberler"),
    Source("Şırnak", "sirnak_bel_news", "https://www.sirnak.bel.tr/"),
]


def main():
    print("=== ADAPTER 2 MUNICIPAL NEWS PROBE ===")
    print("ROUND: 4 / remaining reachable Adapter-1 mismatches")
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
    print("RESULT: inspect winners, then promote only validated shapes into production.")


if __name__ == "__main__":
    main()
