"""Celery app. Every task must be idempotent and have a time limit (docs/architecture.md)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sabaq.settings.prod")

app = Celery("sabaq")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
