"""Local development. Never used in production."""

import base64
import os

# A fixed, clearly fake key derived at import time (dev only; never a real secret).
os.environ.setdefault(
    "FIELD_ENCRYPTION_KEYS",
    base64.urlsafe_b64encode(b"dev-only-insecure-field-key-0123456789"[:32]).decode(),
)
os.environ.setdefault("DJANGO_SECRET_KEY", "dev-only-insecure-key-do-not-use-in-production")

from sabaq.settings.base import *  # noqa: F403
from sabaq.settings.base import INSTALLED_APPS, MIDDLEWARE

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
INTERNAL_IPS = ["127.0.0.1"]

try:
    import debug_toolbar  # noqa: F401
except ImportError:  # pragma: no cover - the dev group is not installed
    pass
else:
    INSTALLED_APPS = [*INSTALLED_APPS, "debug_toolbar"]
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware", *MIDDLEWARE]

# Serve static files straight from the app folders; no collectstatic needed.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
