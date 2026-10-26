from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.crypto import EncryptedJSONField


class Command(BaseCommand):
    help = (
        "Re-encrypt every encrypted field with the newest key in FIELD_ENCRYPTION_KEYS. "
        "Run after adding a new key first in the list; then the old key can be removed."
    )

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        total = 0
        for model in apps.get_models():
            names = [f.name for f in model._meta.fields if isinstance(f, EncryptedJSONField)]
            if not names:
                continue
            with transaction.atomic():
                # Loading decrypts with any listed key; saving encrypts with the newest one.
                for obj in model._default_manager.select_for_update().iterator():
                    obj.save(update_fields=names)
                    total += 1
        self.stdout.write(f"re-encrypted {total} rows")
