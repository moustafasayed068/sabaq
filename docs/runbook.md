# Runbook

Short steps for running Sabaq on one VPS with `docker compose`. Keep this page current.
Setting up a new Oracle Cloud server first: `docs/deploy-oracle.md`.

## First deploy

1. Copy `.env.example` to `.env` and fill every value. Generate fresh keys; never reuse the
   examples. Store `FIELD_ENCRYPTION_KEYS` and `BACKUP_ENCRYPTION_KEYS` in a password manager
   **off the server**: without them, health fields and backups cannot be read.
2. `docker compose up -d --build`. The `migrate` service runs first, then `web`, `worker`,
   `backup` and `caddy`.
3. `docker compose exec web python manage.py check --deploy` must print no issues.
4. Create the first staff account and its 2FA (the admin needs a password **and** a code):
   `docker compose exec web python manage.py createsuperuser`, then
   `docker compose exec web python manage.py staff_otp_setup <phone>`. Scan the QR code with an
   authenticator app and keep the 10 backup codes in the password manager.
5. Paymob (when the keys arrive): set the five `PAYMOB_*` values, set the transaction callback
   URL in the Paymob dashboard to `https://<domain>/payments/paymob/callback/`, restart `web`,
   and run one sandbox payment end to end (plan unlocks, admin shows the order as paid).
6. Error tracking (optional): set `SENTRY_DSN`, restart `web` and `worker`.

## Staff accounts

- Roles are groups, synced after every migrate (`python manage.py sync_roles` by hand):
  `support`, `coach_reviewer`, `finance`, `health_viewer`, `race_editor`. The owner is a
  superuser. Give each person the smallest role that fits; every change is audited.
- Each staff member runs `staff_otp_setup` once. Lost phone: run it again (old codes stop).
- Optional: limit the admin to known networks with `DJANGO_ADMIN_ALLOWED_NETWORKS`
  (others get 404). Staff are signed out after `STAFF_IDLE_TIMEOUT_S` (30 minutes).
- Leaving staff: untick "staff status" and "active" on their account.

## Backups

- The `backup` service makes one encrypted dump a day into the `backups` volume and keeps
  `BACKUP_KEEP_DAYS` days (never deleting the newest). Right after, it runs `apply_retention`:
  health data 12 months after an athlete's last plan, and answers from people who never
  signed up after 30 days, are deleted (docs/security.md).
- Run one now: `docker compose run --rm backup python manage.py backup_db`.
- List them: `docker compose run --rm backup ls -l /backups`.
- **Off the server**: a backup on the same disk does not survive losing the VPS. Copy the
  volume to storage you control at least daily, for example with your host's object storage
  and `rclone`, or `scp` from another machine. Files are already encrypted.
- A failed backup prints `backup failed` in `docker compose logs backup` and, with Sentry on,
  sends an error event.

## Restore

Restore into a scratch database first, check it, then into the real one.

```sh
# 1. scratch database
docker compose exec postgres createdb -U "$POSTGRES_USER" sabaq_restore_test
docker compose run --rm backup python manage.py restore_db /backups/<file>.dump.enc \
  --database sabaq_restore_test --yes
# 2. check: counts look right
docker compose exec postgres psql -U "$POSTGRES_USER" -d sabaq_restore_test \
  -c "select count(*) from accounts_user" -c "select count(*) from plans_plan"
docker compose exec postgres dropdb -U "$POSTGRES_USER" sabaq_restore_test
```

To replace production data (outage only): stop `web` and `worker`, run the same
`restore_db` command without `--database`, start them again.

**Monthly restore test** (docs/security.md): run steps 1 and 2 with the newest backup and
write the date and the counts in the ops log.

## Incidents

| Situation | Do this |
| --- | --- |
| Site down | `docker compose ps`, `docker compose logs --tail 200 web`. `/healthz` must answer `ok`. |
| Bad deploy | `git checkout <previous tag>` then `docker compose up -d --build web worker`. |
| Maintenance | `docker compose stop web`; Caddy answers 502 until it is back. |
| Secret leaked (Django key, Paymob, DB password) | Rotate it in `.env` and at the provider, restart. A new `DJANGO_SECRET_KEY` signs everyone out. |
| Field key leaked | Add a new key first in `FIELD_ENCRYPTION_KEYS`, restart, run `python manage.py rotate_field_keys`, then remove the old key. |
| Backup key leaked | Add a new key first in `BACKUP_ENCRYPTION_KEYS`; old backups stay readable with the old key until they age out, then remove it. |
| Sign everyone out | `docker compose exec redis redis-cli FLUSHDB` (sessions and cache live in Redis). |
| Payment callback failures | Admin > Orders shows `mismatch` or stuck `created`; logs show `payments.callback_*`. Never mark an order paid by hand. |
| Data breach | Stop the leak, keep logs, tell the owner the same day. Egypt's PDPL (Law 151 of 2020) needs notifying the regulator; ask the lawyer for the deadline. |

Security contact: the owner. Put the contact email on the site before launch.

## Going live with the privacy and terms pages

`/privacy/` and `/terms/` are drafts: staff can read them, everyone else gets 404, and the
footer has no links. After the lawyer approves (and the texts are updated), add a feature flag
named `legal_pages` in the admin and turn it on.
