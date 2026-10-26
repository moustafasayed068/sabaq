# syntax=docker/dockerfile:1
# One image for web and worker. Pinned by digest; Dependabot keeps them current.

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS build
RUN pip install --no-cache-dir uv==0.11.32
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN DJANGO_SETTINGS_MODULE=sabaq.settings.base DJANGO_SECRET_KEY=collectstatic-only \
    /opt/venv/bin/python manage.py collectstatic --noinput

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS app-base
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=sabaq.settings.prod
RUN groupadd --system --gid 10001 sabaq && useradd --system --uid 10001 --gid sabaq --no-create-home sabaq
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build --chown=root:root /app /app
USER sabaq
EXPOSE 8000
CMD ["gunicorn", "sabaq.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", \
     "--timeout", "30", "--access-logfile", "-", "--forwarded-allow-ips", "*"]

# Backup service: the app plus pg_dump/pg_restore of the same major version as the database
# (PostgreSQL 18, from the PostgreSQL apt repository; its signing key is checked by fingerprint).
FROM app-base AS backup
USER root
ARG PGDG_KEY_FINGERPRINT=B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /tmp/pgdg.asc \
 && gpg --show-keys --with-colons /tmp/pgdg.asc | grep -q "^fpr:::::::::${PGDG_KEY_FINGERPRINT}:" \
 && install -d /usr/share/postgresql-common/pgdg \
 && mv /tmp/pgdg.asc /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-18 \
 && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
 && install -d -o sabaq -g sabaq -m 700 /backups
USER sabaq
CMD ["sh", "-c", "while true; do python manage.py backup_db || echo 'backup failed'; sleep 86400; done"]

# The default image (web and worker).
FROM app-base AS app
