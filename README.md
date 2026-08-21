# Turkey Pulse Experiment

A zero-euro feasibility collector for the "Türkiye şimdi" concept.

## Goal
Measure whether a useful, fresh, local event map can be fed with free sources before building any product UI.

## Test provinces (15)
İstanbul, Ankara, İzmir, Bursa, Antalya, Konya, Samsun, Çorum, Malatya, Bilecik, Artvin, Bayburt, Ağrı, Hakkâri, Şırnak.

## What this repository does
- keeps a frozen source manifest
- probes configured sources on a schedule
- stores raw observations as append-only JSONL
- never uses paid AA/DHA/İHA feeds
- separates production-safe/open sources from discovery-only sources
- does not use AI yet

## Important
The initial manifest is intentionally conservative. Sources are disabled until their exact endpoint and reuse status are verified.
That prevents us from creating a "successful" test with data we could not legally/technically use later.

## Run locally
```bash
python -m pip install -r requirements.txt
python collector.py
```

## Output
`data/raw_signals.jsonl`

Each line has:
- collected_at
- source_id
- province
- source_type
- rights_status
- url
- http_status
- content_hash
- title
- published_at
- raw_summary

## GitHub Actions
`.github/workflows/collect.yml` runs every hour and commits only the experiment dataset.
