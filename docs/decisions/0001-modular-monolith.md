# 0001: Modular monolith

Date: 2026-10-26. Status: accepted.

## Context

Sabaq is built and run by one developer. It must ship paid plans by 14 Nov 2026 and still serve far more runners later (Gulf expansion) without a rewrite. It holds sensitive health data and payments, so every boundary we add is also something we have to secure, deploy and monitor.

## Decision

- One Django project, one database, one deployable image. No microservices.
- The code is split into apps under `apps/`: `accounts`, `races`, `athletes`, `plans`, `payments`, `notifications` and `core`. Each app owns its models and tables.
- Apps talk to each other only through the other app's `services.py` (writes and use cases) and `selectors.py` (reads). No app imports another app's models.
- Views parse input and render. Business rules live in `services.py`, and training rules live in `engine/`, which is pure Python and knows nothing about Django.
- The web tier is stateless: sessions and cache in Redis, nothing on local disk. Slow work runs as idempotent Celery jobs with time limits and retries.
- Configuration comes from environment variables. The same image runs in dev, staging and production; prod settings fail fast when a secret is missing.

## Consequences

- One repo, one deploy (`docker compose up`), one place to debug, and transactions across apps when they are needed.
- The boundaries are a convention, so code review and tests must hold them. A later CI check can forbid cross-app model imports.
- Scaling follows the path in `docs/architecture.md`: more web containers, managed Postgres/Redis, then read replicas and partitioning. Splitting one app into a service stays possible because each app already has a narrow interface. We do it only when a number shows we need it.
