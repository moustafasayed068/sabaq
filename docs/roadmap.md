# Roadmap

Target: free beta runners for the November races, paid plans on sale for the Pyramids Half Marathon (12 Dec 2026) by **14 Nov 2026** at the latest (4 weeks before the race). Dates are targets; quality and safety come first.

Claude Code: work top to bottom, one task per branch/PR, tick `[x]` when merged.

## Owner actions (start now, they take time)

- [ ] Open a Paymob merchant account (test keys first, live keys before 14 Nov).
- [ ] Buy the domain (e.g. sabaq.run or getsabaq.com) and the Instagram/TikTok handles.
- [ ] Rent a small VPS (or choose a managed host) for staging and production.
- [ ] Find a running coach or physiotherapist to review `docs/engine-rules.md` once (paid or revenue share).
- [ ] Ask a lawyer to review the privacy policy and health-data consent text.
- [ ] Start Meta Business verification for the WhatsApp Business API.

## M0: Foundation (27 Oct – 1 Nov)

- [x] Repo, `.gitignore`, `.env.example`, README with run instructions.
- [x] Django project with `settings/{base,dev,test,prod}.py`, PostgreSQL, Redis, custom User model in the first migration.
- [x] Docker Compose: web (gunicorn), worker, postgres, redis, reverse proxy with HTTPS for staging.
- [x] Tooling: uv or pip-tools with pinned hashes, ruff, mypy, pytest, pytest-django, coverage, bandit, pip-audit, pre-commit (incl. gitleaks).
- [ ] GitHub Actions CI running every gate in `docs/security.md`; branch protection on `main`. (CI done; branch protection is an owner action in GitHub settings.)
- [x] `apps/core`: base model (UUID, timestamps), audit log, feature flags, structured logging with request id, `/healthz`.
- [x] ADR 0001 modular monolith, ADR 0002 engine as pure Python ported from the JS reference.
- [x] **Port the engine** to `engine/` (pure Python, typed). All JS tests ported; golden tests pass against `reference/engine-js/golden/`.

## M1: Plan without payment (2 – 8 Nov)

- [x] `races`: Race and distances, seeded with the races in `reference/engine-js/sabaq-engine.js`; admin to add more.
- [x] Brand base: tokens as CSS variables (light/dark), fonts self-hosted from `brand/fonts/`, base layout RTL, components (button, chip, card, field, time input with 3 boxes, notice).
- [x] Landing page with "اختار سباقك".
- [x] Questionnaire as short steps (no JS required, HTMX enhanced), server-side validation.
- [x] Consent screen + health screen; health fields encrypted at the field level; staff access audited.
- [x] Phone login with one-time codes (dev: code printed to logs; production channel decided by the owner), rate limited.
- [x] Generate and store the plan (rows + engine input + engine_version); result page (ok / risky / blocked + alternatives).
- [x] "My plan" page and day page; week 1 open, later weeks locked.
- [x] Ownership tests for every endpoint (athlete A cannot see athlete B).
- [ ] Deploy to staging; invite 10 free beta runners (Gouna, Sharm, HYROX Cairo).

## M2: Pay and adapt (9 – 15 Nov)

- [ ] `payments`: Order, Payment; Paymob checkout; HMAC-verified idempotent webhook; unlock only from the webhook; refund flow (admin).
- [ ] Weekly check-in form; regenerate remaining weeks via the engine; pause flow for sharp pain with "doctor cleared me".
- [ ] Mark day done / missed / "I feel something".
- [ ] Admin: athletes list with flags first (pain, sick, paused), payments, races.
- [ ] Production deploy with backups, error tracking, `check --deploy` clean. **Paid plans on sale.**

## M3: Harden (16 – 30 Nov)

- [ ] Staff 2FA, admin path + IP limit, roles (support, coach reviewer, finance, owner).
- [ ] Data export and account deletion for athletes.
- [ ] Load test the plan and check-in pages (target: p95 < 300 ms at 50 req/s on one VPS).
- [ ] Restore test from backup; incident runbook.
- [ ] Privacy policy and terms pages (after the lawyer's review).

## M4: Season two (Dec – Jan)

- [ ] Ramadan rules in the engine (owner + coach decide them first) before selling Cairo Marathon plans.
- [ ] WhatsApp reminders and check-in prompts (after API approval).
- [ ] Race week and race day pages, after-race result + share card + "your next race".
- [ ] Strava import (read-only) to fill check-ins automatically.
- [ ] Gulf readiness: currency per country, Paymob UAE/KSA, translations.
