"""Production and staging. Strict: every secret comes from the environment."""

from django.core.exceptions import ImproperlyConfigured

from sabaq.env import env_bool, env_int, env_list, env_str
from sabaq.settings.base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Production always uses PostgreSQL and Redis; fail fast when they are not configured.
env_str("POSTGRES_HOST")
env_str("REDIS_URL")
if LOGIN_CODE_SENDER == "console":  # noqa: F405
    raise ImproperlyConfigured("LOGIN_CODE_SENDER=console writes codes to the log: dev only.")
if not FIELD_ENCRYPTION_KEYS:  # noqa: F405 - health data must never be stored unencrypted
    raise ImproperlyConfigured("Set the FIELD_ENCRYPTION_KEYS environment variable.")

# TLS ends at Caddy, which sets X-Forwarded-Proto.
TRUST_X_FORWARDED_FOR = env_bool("DJANGO_TRUST_X_FORWARDED_FOR", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# The header allows preloading; submitting the domain to hstspreload.org is a separate,
# manual step done only once HTTPS is stable on every subdomain.
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

_paymob = [PAYMOB_SECRET_KEY, PAYMOB_PUBLIC_KEY, PAYMOB_HMAC_SECRET, PAYMOB_INTEGRATION_IDS]  # noqa: F405
if any(_paymob) and not all(_paymob):
    raise ImproperlyConfigured(
        "Set all of PAYMOB_SECRET_KEY, PAYMOB_PUBLIC_KEY, PAYMOB_HMAC_SECRET and "
        "PAYMOB_INTEGRATION_IDS, or none of them (payments closed)."
    )
if not PAYMOB_BASE_URL.startswith("https://"):  # noqa: F405
    raise ImproperlyConfigured("PAYMOB_BASE_URL must use https.")
