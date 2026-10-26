"""Create the staff role groups with exactly their permissions (also runs after migrate)."""

from typing import Any

from django.core.management.base import BaseCommand

from apps.core.staff import sync_roles


class Command(BaseCommand):
    help = "Create or update the staff role groups (support, coach_reviewer, finance, ...)."

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        for name, count in sync_roles().items():
            self.stdout.write(f"{name}: {count} permissions")
