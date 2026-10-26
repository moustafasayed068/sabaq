"""Delete health data past its retention period. The daily ops service runs it."""

from typing import Any

from django.core.management.base import BaseCommand

from apps.plans.retention import apply_retention


class Command(BaseCommand):
    help = "Delete health data 12 months after an athlete's last plan, and stale anonymous answers."

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        result = apply_retention()
        self.stdout.write(", ".join(f"{k}={v}" for k, v in result.__dict__.items()))
