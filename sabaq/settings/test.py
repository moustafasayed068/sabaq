"""Test settings: fast, isolated, no network."""

import base64
import os

# A fixed, clearly fake key derived at import time (test only; never a real secret).
os.environ.setdefault(
    "FIELD_ENCRYPTION_KEYS",
    base64.urlsafe_b64encode(b"test-only-insecure-field-key-0123456789"[:32]).decode(),
)
os.environ.setdefault("LOGIN_CODE_SENDER", "console")
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

# Most admin tests sign staff in with force_login; the 2FA tests turn this back on.
STAFF_REQUIRE_2FA = False
