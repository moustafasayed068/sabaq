# 0003: Field-level encryption for health data

Date: 2026-10-26. Status: accepted.

## Context

Health answers, injury history, current pain and sickness check-ins are sensitive personal data under Egypt's PDPL 151/2020. `docs/security.md` asks for them to be encrypted at the field level, with keys from the environment or a KMS. It also asks that only the athlete and the `health_viewer` staff role see them, and that every staff view is audited. Database-level or disk encryption alone does not protect against a leaked backup or a broad SQL read.

## Decision

- Add `cryptography` (pinned) and use Fernet (AES-128-CBC + HMAC-SHA256, authenticated) through `MultiFernet`.
- Keys come from `FIELD_ENCRYPTION_KEYS`: comma-separated, newest first. Production refuses to start without them. Dev and test use fixed, clearly named insecure keys.
- `apps.core.crypto.EncryptedJSONField` stores a JSON value as a Fernet token. Any lookup other than `isnull` raises, so encrypted data is never filtered or indexed by accident.
- Health answers live in `athletes.HealthScreen.data`, one row per questionnaire. Consent is stored first (`athletes.Consent`, with text version and SHA-256).
- Admin: decrypted answers are visible only with `athletes.view_health_answers` (put it in a `health_viewer` group). Every change-view open writes `AuditEvent(health_data_viewed)`.
- **Rotation:**
  1. Put a new key first in `FIELD_ENCRYPTION_KEYS`.
  2. Run `manage.py rotate_field_keys`.
  3. Remove the old key.

## Consequences

- Losing every key loses the health data. Keys must be backed up separately from database backups and never stored next to them.
- Health answers cannot be searched or reported on in SQL. Aggregates must decrypt in Python, which is fine at our scale.
- One more dependency, which has a strong security track record and is widely audited.
