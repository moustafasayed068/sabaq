"""Restore an encrypted backup. Replaces the data in the target database."""

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core import backups


class Command(BaseCommand):
    help = "Decrypt a backup and restore it with pg_restore. Needs --yes."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("path", type=Path)
        parser.add_argument(
            "--database",
            help="Restore into this database instead (for the monthly restore test).",
        )
        parser.add_argument("--yes", action="store_true", help="Confirm replacing the data.")

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        if not options["yes"]:
            raise CommandError("This replaces the data in the database. Add --yes to go on.")
        path: Path = options["path"]
        if not path.is_file():
            raise CommandError(f"No such file: {path}")
        try:
            backups.restore_backup(path, database=options["database"])
        except backups.BackupError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"restored {path.name}")
