# Security and privacy

Sabaq stores health answers, injuries, phone numbers and payments. Treat all of it as sensitive. Target: OWASP ASVS level 2 and the OWASP Top 10 covered by tests and settings, not by hope.

Legal note (not legal advice): Egypt's Personal Data Protection Law (No. 151 of 2020) treats health data as sensitive personal data, which needs explicit consent and extra protection. The UAE and Saudi Arabia have their own data protection laws for the Gulf phase. Have a lawyer review the privacy policy, consent text and data retention before launch.

## Data we keep, and how

| Data | Why | Protection | Kept for |
| --- | --- | --- | --- |
| Phone number | login, reminders | unique, verified, never in logs or URLs | while the account exists |
| Health answers, injuries, pain, sickness check-ins | safety rules | encrypted at the field level (key from env / KMS), visible only to the athlete and staff with the `health_viewer` role, every view audited | plan end + 12 months, then deleted or anonymised |
| Age, sex, weight | plan and race-day advice | normal DB, weight optional | while the account exists |
| Payments | billing | we never see or store card numbers; only Paymob ids, amount, status | as tax law requires |

- Collect the minimum. No height, no ID numbers, no location.
- Explicit consent screen before the health questions, stored with timestamp and text version.
- Athletes can download their data and delete their account from settings. Deletion removes or anonymises personal and health data and is audited.

## Application settings (production)

- `DEBUG=False`, strict `ALLOWED_HOSTS`, `SECRET_KEY` from env, `SECURE_SSL_REDIRECT`, HSTS (with preload once stable), `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SameSite=Lax`, `X_FRAME_OPTIONS=DENY`, `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY=same-origin`.
- Content Security Policy (django-csp): self only, plus the fonts and Paymob domains that are needed. No inline scripts; HTMX loaded from our own static files.
- `python manage.py check --deploy` passes in CI with no warnings.

## Authentication and accounts

- Custom user model from the first migration. Phone-first login with one-time codes; codes are short-lived, single use, hashed at rest, and rate limited per phone and per IP.
- Passwords (staff) hashed with Argon2. Staff must use 2FA (django-otp or similar).
- Admin lives at a non-default path, needs 2FA, and can be limited by IP. Staff permissions by role (support, coach reviewer, finance, owner) with least privilege.
- Login, code, check-in and payment endpoints rate limited (django-ratelimit or at the proxy). Lockout after repeated failed codes.
- Session rotation on login, logout everywhere option, idle timeout for staff.

## Authorisation

- Every query that returns athlete data is scoped to `request.user` in a selector; views never filter by an id from the URL alone. Tests prove athlete A cannot read or change athlete B's plan, check-ins or payments (IDOR tests for every endpoint).
- UUIDs in URLs; still check ownership.

## Payments (Paymob)

- Prices are decided on the server from the Order, never taken from the browser.
- Webhooks: verify the HMAC on every callback, reject on mismatch, process idempotently by Paymob transaction id, and confirm the amount and currency match the Order before unlocking the plan. Log every webhook (without card data).
- Unlock happens only from a verified webhook, never from the redirect page.

## Input and output

- Django forms/validators for every input, with server-side limits (ages, distances, times, text length).
- Templates auto-escape; no `|safe` on user content. No raw SQL with string formatting.
- File uploads are off in the MVP. If added later: size and type checks, stored outside the web root, served with signed URLs.

## Secrets and infrastructure

- Secrets only in env / a secrets manager; `.env` in `.gitignore`; `.env.example` with fake values. Secret scanning on the repo (GitHub secret scanning + gitleaks in pre-commit).
- Database not exposed to the internet; app connects with a least-privilege user. Backups encrypted, tested by a restore at least monthly.
- Containers run as non-root, minimal base images, pinned versions.
- Firewall: only 80/443 open (and SSH by key from known IPs).

## Supply chain and checks in CI

- Dependencies pinned with hashes (pip-tools or uv lock). Dependabot or Renovate for updates.
- CI runs on every PR: `ruff` (lint + format), `mypy`, `pytest` with coverage, `bandit`, `pip-audit`, `manage.py check --deploy`, `makemigrations --check`. A PR cannot merge if any fails.
- `main` is protected: PRs only, CI green.

## Audit log

Append-only `AuditEvent` for: login, failed code attempts, health data viewed by staff, plan paused/resumed, payment status changes, data export, account deletion, staff permission changes.

## Incidents

Keep a one-page runbook: how to rotate secrets, revoke sessions, take the site to maintenance mode, and who to notify. Security contact email on the site.
