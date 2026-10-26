"""Encrypted database backups.

A backup file is a header line, then the `pg_dump --format=custom` output cut into 1 MiB chunks,
each one encrypted and authenticated with Fernet and written on its own line. Keys come from
BACKUP_ENCRYPTION_KEYS (newest first), separate from the field keys, so a leaked backup key
does not open health fields and the other way round. Chunking keeps memory flat for big dumps.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404 - runs pg_dump / pg_restore with fixed arguments, never a shell
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO, Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

HEADER = b"SABAQ-BACKUP-1\n"
CHUNK = 1024 * 1024
NAME = re.compile(r"^sabaq-(\d{8}-\d{6})\.dump\.enc$")


class BackupError(Exception):
    pass


def _fernet() -> MultiFernet:
    keys = [k for k in getattr(settings, "BACKUP_ENCRYPTION_KEYS", []) if k]
    if not keys:
        raise ImproperlyConfigured("Set BACKUP_ENCRYPTION_KEYS to make or read backups.")
    return MultiFernet([Fernet(k) for k in keys])


def encrypt_stream(src: IO[bytes], dst: IO[bytes], fernet: MultiFernet | None = None) -> int:
    """Encrypt `src` into `dst`. Returns the number of plain bytes."""
    f = fernet or _fernet()
    dst.write(HEADER)
    total = 0
    while chunk := src.read(CHUNK):
        dst.write(f.encrypt(chunk) + b"\n")
        total += len(chunk)
    dst.write(f.encrypt(b"") + b"\n")  # end marker: a cut-off file is detected
    return total


def decrypt_chunks(src: IO[bytes], fernet: MultiFernet | None = None) -> Iterator[bytes]:
    f = fernet or _fernet()
    if src.readline() != HEADER:
        raise BackupError("not a Sabaq backup file")
    ended = False
    for line in src:
        if ended:
            raise BackupError("data after the end marker")
        try:
            chunk = f.decrypt(line.strip())
        except InvalidToken as exc:
            raise BackupError("wrong key or damaged backup") from exc
        if chunk == b"":
            ended = True
            continue
        yield chunk
    if not ended:
        raise BackupError("backup is cut off (no end marker)")


@dataclass(frozen=True)
class Database:
    name: str
    user: str
    password: str
    host: str
    port: str

    @classmethod
    def from_settings(cls, alias: str = "default") -> Database:
        db: dict[str, Any] = settings.DATABASES[alias]
        if "postgresql" not in db["ENGINE"]:
            raise BackupError("backups need PostgreSQL")
        return cls(
            name=str(db["NAME"]),
            user=str(db["USER"]),
            password=str(db.get("PASSWORD") or ""),
            host=str(db.get("HOST") or "localhost"),
            port=str(db.get("PORT") or 5432),
        )

    def args(self, database: str | None = None) -> list[str]:
        return ["-h", self.host, "-p", self.port, "-U", self.user, "-d", database or self.name]

    def env(self) -> dict[str, str]:
        # The password goes in the environment, never on the command line (ps shows arguments).
        return {**os.environ, "PGPASSWORD": self.password}


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise BackupError(f"{name} is not installed (use the backup image)")
    return path


def backup_dir() -> Path:
    return Path(getattr(settings, "BACKUP_DIR", "/backups"))


def make_backup(now: datetime | None = None, directory: Path | None = None) -> Path:
    """Dump the database, encrypt it, and write it atomically. Returns the file path."""
    db = Database.from_settings()
    fernet = _fernet()
    directory = directory or backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = (now or timezone.now()).strftime("%Y%m%d-%H%M%S")
    final = directory / f"sabaq-{stamp}.dump.enc"
    partial = final.with_suffix(".partial")
    cmd = [_tool("pg_dump"), "--format=custom", "--no-owner", "--no-privileges", *db.args()]
    with (
        subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=db.env()) as proc,  # noqa: S603  # nosec B603 - fixed arguments
        partial.open("wb") as out,
    ):
        if proc.stdout is None:  # pragma: no cover - Popen with PIPE always has it
            raise BackupError("pg_dump has no output")
        size = encrypt_stream(proc.stdout, out, fernet)
        _, err = proc.communicate()
    if proc.returncode != 0 or size == 0:
        partial.unlink(missing_ok=True)
        raise BackupError(f"pg_dump failed: {err.decode(errors='replace').strip()[:300]}")
    partial.chmod(0o600)
    partial.rename(final)
    return final


def restore_backup(path: Path, *, database: str | None = None) -> None:
    """Decrypt a backup and restore it with pg_restore (replacing objects that exist)."""
    db = Database.from_settings()
    fernet = _fernet()
    cmd = [
        _tool("pg_restore"),
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--exit-on-error",
        *db.args(database),
    ]
    with (
        path.open("rb") as src,
        subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, env=db.env()) as proc,  # noqa: S603  # nosec B603 - fixed arguments
    ):
        if proc.stdin is None:  # pragma: no cover - Popen with PIPE always has it
            raise BackupError("pg_restore has no input")
        try:
            for chunk in decrypt_chunks(src, fernet):
                proc.stdin.write(chunk)
        except BackupError:
            proc.kill()
            raise
        finally:
            proc.stdin.close()
        err = proc.stderr.read() if proc.stderr else b""
        proc.wait()
    if proc.returncode != 0:
        raise BackupError(f"pg_restore failed: {err.decode(errors='replace').strip()[:300]}")


def prune(keep_days: int, now: datetime | None = None, directory: Path | None = None) -> list[Path]:
    """Delete backups older than `keep_days`, never the newest one."""
    directory = directory or backup_dir()
    now = now or timezone.now()
    found: list[tuple[datetime, Path]] = []
    for p in directory.glob("sabaq-*.dump.enc"):
        m = NAME.match(p.name)
        if m:
            when = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=now.tzinfo)
            found.append((when, p))
    found.sort()
    removed = []
    for when, p in found[:-1]:
        if now - when > timedelta(days=keep_days):
            p.unlink()
            removed.append(p)
    return removed
