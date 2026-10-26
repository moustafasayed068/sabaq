import importlib
import subprocess
import sys

import pytest
from django.conf import settings

PROD_ENV = {
    "DJANGO_SECRET_KEY": "x" * 60,
    "DJANGO_ALLOWED_HOSTS": "sabaq.example",
    "POSTGRES_HOST": "db",
    "POSTGRES_PASSWORD": "pw",
    "REDIS_URL": "redis://redis:6379/0",
}


def test_security_baseline():
    assert settings.X_FRAME_OPTIONS == "DENY"
    assert settings.SECURE_CONTENT_TYPE_NOSNIFF
    assert settings.SECURE_REFERRER_POLICY == "same-origin"
    assert settings.SESSION_COOKIE_HTTPONLY
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert settings.LANGUAGE_CODE == "ar"
    assert settings.ADMIN_URL != "admin/"


@pytest.fixture
def prod(monkeypatch):
    for key, value in PROD_ENV.items():
        monkeypatch.setenv(key, value)
    base = importlib.import_module("sabaq.settings.base")
    importlib.reload(base)
    yield importlib.reload(importlib.import_module("sabaq.settings.prod"))
    monkeypatch.undo()
    importlib.reload(base)


def test_prod_settings_are_strict(prod):
    assert prod.DEBUG is False
    assert prod.ALLOWED_HOSTS == ["sabaq.example"]
    assert prod.SECURE_SSL_REDIRECT
    assert prod.SESSION_COOKIE_SECURE
    assert prod.CSRF_COOKIE_SECURE
    assert prod.SECURE_HSTS_SECONDS >= 31536000
    assert prod.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert prod.CACHES["default"]["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    assert prod.SESSION_ENGINE == "django.contrib.sessions.backends.cache"


@pytest.mark.parametrize("missing", ["DJANGO_SECRET_KEY", "POSTGRES_HOST", "REDIS_URL"])
def test_prod_settings_refuse_to_start_without_secrets(missing):
    """prod.py must fail fast when a required environment variable is missing."""
    env = {"PATH": "/usr/bin:/bin", **PROD_ENV}
    del env[missing]
    result = subprocess.run(
        [sys.executable, "-c", "import sabaq.settings.prod"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert missing in result.stderr
