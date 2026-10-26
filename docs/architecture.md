# Architecture: built to grow, easy to change

Goal: one developer can understand, change and fix any part quickly, and the same code can serve 100 users this season and 100,000 later without a rewrite. We get there with a **modular monolith**, not microservices: one Django project, clear module boundaries, stateless web servers, and the heavy or slow work in background jobs.

## Principles

1. **Boring, proven tools.** Django, PostgreSQL, Redis. No framework of the month.
2. **Clear boundaries.** Each app owns its models. Other apps call its `services.py` functions, never its models or tables directly. The engine knows nothing about Django.
3. **Business logic out of views.** Views parse input and render. Rules live in `services.py` (use cases) and `engine/` (training logic). Models hold data and small invariants.
4. **Stateless web tier.** No local files, no in-memory sessions. Sessions and cache in Redis, uploads in object storage. Any number of web containers can run behind a load balancer.
5. **Everything slow is a job.** Sending WhatsApp/email, payment reconciliation, regenerating plans in bulk, exports: background workers, retried safely.
6. **Configuration in the environment** (12-factor). Same image for dev, staging, production; only env vars differ.
7. **Change is cheap.** Typed code, tests at the right level, one way to do each thing, decisions written down.

## Layout

```
sabaq/settings/        base.py, dev.py, test.py, prod.py (prod is strict; dev never used in prod)
apps/
  accounts/            custom User from day one (phone-first), auth, sessions
  races/               Race, RaceDistance
  athletes/            Profile, Questionnaire, HealthScreen (sensitive data)
  plans/               Plan, PlanWeek, PlanDay, CheckIn; services call engine/
  payments/            Order, Payment, Paymob client + webhook (idempotent)
  notifications/       message templates, channels (WhatsApp later), jobs
  core/                shared utilities: audit log, feature flags, base models, i18n helpers
engine/                pure Python plan engine + tests + golden tests
templates/, static/    RTL UI, components as template partials
docs/decisions/        ADRs: one short file per important decision (0001-modular-monolith.md, ...)
```

Each app: `models.py`, `services.py` (public API of the app), `selectors.py` (read queries), `views.py`, `forms.py`, `urls.py`, `admin.py`, `tests/`.

## Data

- PostgreSQL in every environment except quick local tests.
- UUID primary keys exposed in URLs (never sequential ids in URLs).
- Every model gets `created_at`, `updated_at`. Money in integer piastres/fils plus a currency code, never floats.
- Plans are **stored as generated** (weeks and days as rows) plus the exact engine input and `engine_version`. Old plans never change when the engine changes; a regenerate creates a new version.
- Migrations are reviewed: no destructive change in the same release that removes code using the column (expand → migrate → contract).
- Indexes for every foreign key and every filter used by a list page; check slow queries with `django-debug-toolbar` locally and `pg_stat_statements` in production.
- Avoid N+1: list pages use `select_related` / `prefetch_related`; a test asserts the query count of key pages.

## Background work

- Celery (or RQ) with Redis. Every task is idempotent (safe to run twice) and has a timeout, retries with backoff, and a dead-letter log.
- Scheduled jobs (morning reminders, weekly check-in prompt) run from the scheduler, not cron on one machine.

## Scaling path (do the next step only when a number says so)

1. One VPS: Docker Compose with web (gunicorn), worker, Postgres, Redis, Caddy/Nginx with HTTPS. Daily backups off the server.
2. Managed Postgres + Redis, 2+ web containers behind a load balancer, static files on a CDN.
3. Read replica for heavy reads, caching of race pages and plan views, partition big tables (check-ins, audit log) by month.
4. Region expansion (Gulf): same code, per-country settings for currency, payment method and data residency.

## Internationalisation

All UI text goes through Django `gettext` from day one (Arabic first). English and Gulf variants then only need translation files, not code changes. Dates and numbers are formatted in one helper.

## Observability

- Structured JSON logs with a request id. Never log phone numbers, health answers, tokens or card data.
- Error tracking (Sentry or similar) with PII scrubbing on.
- Health endpoint `/healthz` (no data) for the load balancer. Basic metrics: request time, error rate, job queue length, payment webhook failures.

## Making changes safely

- Feature flags (`core.flags`) for anything risky, so it can be turned off without a deploy.
- Every bug fix starts with a failing test that reproduces it.
- Engine changes bump `engine_version` and update the golden files only with the owner's approval.
