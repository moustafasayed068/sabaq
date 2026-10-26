# Load test

Target (docs/roadmap.md M3): p95 under 300 ms at 50 requests/s on one VPS, for the plan and
check-in pages.

## How to run it

```sh
python manage.py loadtest_seed --athletes 50 --out sessions.txt   # add --staging on staging
python scripts/loadtest.py --base https://staging.example --sessions sessions.txt --rate 50 --seconds 60
python manage.py loadtest_seed --cleanup                          # removes the test athletes
```

The seed command makes real athletes (questions, consent, health screen, plan) with numbers
from the `+2010999` block and writes one session key and workout date per line. The script
starts requests on a fixed schedule and mixes the plan page, a workout day and the check-in
page. Never run the seed command on production.

## Result (26 Oct 2026)

Production settings (`DEBUG=False`), gunicorn with 3 workers (as in the Docker image),
PostgreSQL 16 and Redis on the same machine, 4 vCPU / 16 GB, no TLS proxy, load generator on
the same machine.

| rate | page | p50 ms | p95 ms | p99 ms | errors |
| --- | --- | ---: | ---: | ---: | ---: |
| 50/s for 60 s | plan | 18 | 26 | 75 | 0 |
| | day | 14 | 22 | 35 | 0 |
| | check-in | 13 | 19 | 28 | 0 |
| | **all** | **15** | **24** | **43** | **0** |
| 150/s for 30 s | **all** | **16** | **34** | **84** | **0** |

The target is met with a wide margin. Each page also has a query-count test
(`apps/plans/tests/test_query_counts.py`) so a later change cannot quietly add N+1 queries.

**Repeat on the real VPS** once it exists (behind Caddy with TLS): a small VPS has fewer and
slower cores, so expect higher numbers. If p95 gets near 300 ms, first raise gunicorn workers
to 2 × cores + 1.
