# Sabaq (سبق)

Sabaq gives runners in Egypt (then the Gulf) an Arabic training plan for the race they signed up for: running races (5K to marathon) and HYROX. The runner picks a race, answers a few questions, gets week 1 free, pays to unlock the rest, logs each week, and the plan adapts until race day.

Tagline: **خطتك لحد خط النهاية**.

Read these before any non-trivial change:

- `docs/product.md`: pages, user flow, edge cases (sick, injured, missed days), MVP scope.
- `docs/engine-rules.md`: every training and safety rule the plan engine follows.
- `docs/brand.md`: colours, type, logo, voice and copy rules.
- `docs/architecture.md`: modular monolith, app boundaries, data rules, background jobs, scaling path. **Binding.**
- `docs/security.md`: privacy, auth, payments, settings, CI checks. **Binding.** Health data is sensitive.
- `docs/roadmap.md`: milestones and the current task list. Tick tasks as you finish them.
- `reference/engine-js/`: the working JavaScript engine, its tests, and golden outputs. This is the spec for the Python engine.
- `reference/plan-lab.html`: the clickable prototype of the questions, the plan and the weekly check-in. Open it in a browser.

## Stack (decided)

- Python 3.12, Django 5, PostgreSQL (SQLite is fine locally).
- Server-rendered Django templates + HTMX. No SPA. Mobile-first web app, no native app yet.
- Payments: Paymob (cards, Meeza, Fawry; Egypt now, UAE/KSA later). Week 1 is free; a plan for one race is a one-time payment.
- Reminders: WhatsApp Business API later; until it is approved, reminders are off and the admin can message manually.
- Hosting: a small VPS. Keep it deployable with one `docker compose up`.
- Tests: pytest + pytest-django.

- Background jobs: Celery (or RQ) + Redis. Cache and sessions in Redis.
- Quality gates: ruff, mypy, pytest + coverage, bandit, pip-audit, `check --deploy`, `makemigrations --check`, in GitHub Actions on every PR.

## Project layout (target)

See `docs/architecture.md` for the full layout. In short: `sabaq/settings/{base,dev,test,prod}.py`, apps under `apps/` (accounts, races, athletes, plans, payments, notifications, core), each with `services.py` as its public API; `engine/` is pure Python; decisions in `docs/decisions/`.

## Non-negotiables

1. Security and privacy rules in `docs/security.md` are requirements, not suggestions. Every endpoint that returns athlete data has an ownership test (athlete A cannot see athlete B).
2. Health answers and check-in health fields are encrypted at the field level and every staff view of them is audited.
3. Payments unlock a plan only from a verified, idempotent Paymob webhook whose amount matches the order.
4. No business logic in views or templates. Apps talk to each other through `services.py` only.
5. Every bug fix starts with a failing test. Every new feature ships with tests.
6. Type hints on all new Python code; mypy passes.
7. Big decisions get a short ADR in `docs/decisions/` (context, decision, consequences).
8. No new dependency without a reason; pin everything.

## The engine: hard rules

- `engine/` is pure Python: plain functions and dataclasses in, plain data out. No Django, no database, no network. Django calls it and stores the result.
- The Python engine must reproduce `reference/engine-js/golden/*.json` exactly (dates, roles, titles, km, steps text). When they differ, the JS reference wins unless the owner approves a change.
- Rounding: JS `Math.round` rounds .5 up; Python `round` rounds .5 to even. Port with a helper `js_round(x) = math.floor(x + 0.5)` and use it everywhere the JS uses `Math.round`.
- Never change a safety rule (health screen, pain stop, weekly increase caps, long-run caps, taper, sickness rules, feasibility thresholds) without the owner saying so. If a rule looks wrong, say so and propose the change; do not apply it silently.
- No AI/LLM decides training. The engine is rules only. An LLM may only reword messages later.
- Training paces use the published Daniels & Gilbert VDOT formulas (see the JS file).

## UI conventions

- Every page is `dir="rtl" lang="ar"`. Times, paces and distances sit inside an LTR-isolated span (`class="num"`), Western digits.
- Copy is Egyptian Arabic, second person (انت), short, no emoji. Follow `docs/brand.md` exactly, including the "write / don't write" table.
- Use the tokens in `brand/tokens.json` as CSS custom properties; no hard-coded colours. Light and dark themes both.
- Time inputs are three numeric boxes (hours, minutes, seconds), never one text box: the iPhone number keypad has no colon.
- Forms work without JavaScript; HTMX only improves them.

## Working rules

- Work in small steps: one roadmap task per branch and per pull request, with tests.
- Run `pytest` before every commit. Do not commit failing tests.
- Do not add packages without a reason in the PR description.
- Secrets live in `.env` (never committed). Keep `.env.example` current.
- When a task needs the owner (Paymob keys, WhatsApp approval, a coach's review, a copy decision), stop and ask in one short message. Do not invent keys or fake integrations.
- Write commit messages in English; UI text in Egyptian Arabic.

## Commands

- `python manage.py runserver`: run locally.
- `pytest`: all tests. `pytest engine`: engine only.
- `node reference/engine-js/test.js`: re-run the JS reference tests.
- `node reference/engine-js/make-golden.js`: regenerate golden outputs (only if the owner approved a JS rule change).
