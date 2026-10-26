# syntax=docker/dockerfile:1
# One image for web and worker. Pinned by digest; Dependabot keeps them current.

FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d AS build
RUN pip install --no-cache-dir uv==0.11.32
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN DJANGO_SETTINGS_MODULE=sabaq.settings.base DJANGO_SECRET_KEY=collectstatic-only \
    /opt/venv/bin/python manage.py collectstatic --noinput

FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d
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
