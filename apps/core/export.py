"""Turn model rows into plain JSON for the athlete's data export."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db.models import Model

ALWAYS_SKIP = {"id", "session_key"}


def json_value(value: object) -> Any:  # noqa: ANN401 - JSON
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [json_value(v) for v in value]
    return value


def row(obj: Model, *, skip: tuple[str, ...] = ()) -> dict[str, Any]:
    """Every stored field of `obj` (foreign keys as ids), minus internal ones."""
    out: dict[str, Any] = {}
    for field in obj._meta.concrete_fields:
        if field.name in ALWAYS_SKIP or field.name in skip:
            continue
        out[field.name] = json_value(getattr(obj, field.attname))
    return out
