"""Test settings: fast, isolated, no network."""

import os

os.environ.setdefault(
    "FIELD_ENCRYPTION_KEYS", "dGVzdC1vbmx5LWluc2VjdXJlLWZpZWxkLWtleS0zMmI="
)  # test only
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-insecure-key")

from sabaq.settings.base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"

# Serve static files straight from the app folders; no collectstatic needed.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
