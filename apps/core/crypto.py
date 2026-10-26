"""Field-level encryption for sensitive data (docs/security.md, ADR 0003).

Keys come from FIELD_ENCRYPTION_KEYS (comma-separated Fernet keys, newest first).
Old keys stay in the list until every row is re-encrypted with `manage.py rotate_field_keys`.
"""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.models.expressions import Expression


@cache
def _fernet() -> MultiFernet:
    keys = list(getattr(settings, "FIELD_ENCRYPTION_KEYS", []))
    if not keys:
        raise ImproperlyConfigured("Set FIELD_ENCRYPTION_KEYS.")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except ValueError as exc:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS must be Fernet keys.") from exc


def reset_keys_cache() -> None:
    _fernet.cache_clear()


def encrypt(data: bytes) -> str:
    return _fernet().encrypt(data).decode()


def decrypt(token: str) -> bytes:
    try:
        return _fernet().decrypt(token.encode())
    except InvalidToken as exc:
        raise ImproperlyConfigured("Cannot decrypt a field: wrong or missing key.") from exc


def rotate(token: str) -> str:
    """Re-encrypt with the newest key."""
    return _fernet().rotate(token.encode()).decode()


class EncryptedJSONField(models.TextField):  # type: ignore[type-arg]
    """JSON value stored encrypted. It can never be filtered or ordered on."""

    description = "Encrypted JSON"

    def from_db_value(
        self, value: str | None, expression: Expression, connection: BaseDatabaseWrapper
    ) -> Any:  # noqa: ANN401
        if value is None:
            return None
        return json.loads(decrypt(value))

    def to_python(self, value: Any) -> Any:  # noqa: ANN401
        return value

    def get_prep_value(self, value: Any) -> str | None:  # noqa: ANN401
        if value is None:
            return None
        return encrypt(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())

    def get_lookup(self, lookup_name: str) -> Any:  # noqa: ANN401
        if lookup_name == "isnull":
            return super().get_lookup(lookup_name)
        raise NotImplementedError("Encrypted fields cannot be queried.")
