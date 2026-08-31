from __future__ import annotations

import json
import time

import collect_municipal_news as generic


def load_adapter2_ids():
    payload = json.loads(generic.REGISTRY.read_text(encoding="utf-8"))
    return {
        str(row.get("source_id") or "").strip()
        for row in (payload.get("sources") or [])
        if str(row.get("adapter2_strategy") or "").strip()
    }


def main():
    print("=== GENERIC MUNICIPAL NEWS ROUTER ===")
    print("Adapter 2 sources are delegated and are not allowed to overwrite their snapshots here.")

    sources = generic.load_sources()
    adapter2_ids = load_adapter2_ids()
    delegated = [source for source in sources if source.source_id in adapter2_ids]
    enabled_sources = [
        source for source in sources
        if source.enabled and source.source_id not in adapter2_ids
    ]
    disabled_sources = [
        source for source in sources
        if not source.enabled and source.source_id not in adapter2_ids
    ]

    print(
        f"Registry: {len(sources)} configured, {len(enabled_sources)} generic, "
        f"{len(delegated)} adapter2-delegated, {len(disabled_sources)} paused"
    )
    for source in delegated:
        print(f"DELEGATE {source.source_id}: handled_by_adapter2")
    for source in disabled_sources:
        print(f"SKIP {source.source_id}: status={source.status}")

    failures = 0
    for source in enabled_sources:
        try:
            generic.collect(source)
        except Exception as exc:
            failures += 1
            print(f"ERROR {source.source_id}: {type(exc).__name__}: {exc}")
        time.sleep(0.25)

    if enabled_sources and failures == len(enabled_sources):
        raise SystemExit("All enabled generic municipal news sources failed")


if __name__ == "__main__":
    main()
