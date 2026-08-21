# TEST_RULES.md — FROZEN BEFORE COLLECTION

Experiment: Turkey Pulse Zero-Euro Reality Test
Planned duration: 7 consecutive days

## Non-negotiable rules
1. Paid agency feeds (AA, DHA, İHA) do not count.
2. A publicly reachable page is not automatically a green production source.
3. Sources with unclear reuse rights may be observed as `discovery_only`, but they do not count toward production-safe coverage.
4. Duplicate reports of the same real-world event count once.
5. National/noise content does not count merely because a province name appears.
6. PR, ceremonies, condolences, routine appointments, generic national prices and ordinary procurement notices do not count as Useful Events.
7. Events older than 24 hours at collection do not count as live events.
8. We do not change thresholds after seeing the results.

## A Useful Event must be
- genuinely local to the province, and
- current, and
- something a reasonable user might click on in a "what is happening where?" map.

Examples:
- fire / flood / earthquake / landslide
- major accident or transport disruption
- water / power / infrastructure outage
- meaningful road closure
- official local warning
- meaningful local public-service change
- notable public event happening now/today
- meaningful local economic event

## Primary KPI: UEPD
Useful Events Per Province Per Day.

### Pre-registered thresholds
Strong:
- median UEPD >= 5
- bottom quartile UEPD >= 2

Interesting / needs change:
- median 3–5
- bottom quartile 1–2

Weak:
- median 1–3
- repeated zero-event provinces

Kill signal for Turkey-wide live promise:
- large cities work, but small/medium provinces repeatedly produce ~0 useful events from zero-euro sources.

## Secondary metrics
- freshness (<1h, 1–3h, 3–6h, 6–12h, 12–24h)
- geo precision (province / district / mahalle / coordinates)
- source diversity
- event-category diversity
- discovery-only dependency
- source uptime / failures
