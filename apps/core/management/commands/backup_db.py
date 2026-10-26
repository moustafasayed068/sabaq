"""Make one encrypted database backup and prune old ones. The backup service runs it daily."""

import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core import backups

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Dump PostgreSQL, encrypt it with BACKUP_ENCRYPTION_KEYS and prune old backups."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--keep-days", type=int, default=settings.BACKUP_KEEP_DAYS)

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        try:
            path = backups.make_backup()
        except backups.BackupError as exc:
            log.error("backup.failed")  # reaches error tracking; the reason stays in this log
            raise CommandError(str(exc)) from exc
        removed = backups.prune(options["keep_days"])
        self.stdout.write(f"backup written: {path.name} ({path.stat().st_size} bytes)")
        if removed:
            self.stdout.write(f"pruned {len(removed)} old backup(s)")
