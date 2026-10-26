import io
import os
import stat
from datetime import timedelta
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet, MultiFernet
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.core import backups

KEY = Fernet.generate_key().decode()


@pytest.fixture
def keys(settings, tmp_path):
    settings.BACKUP_ENCRYPTION_KEYS = [KEY]
    settings.BACKUP_DIR = str(tmp_path / "backups")
    return settings


@pytest.fixture
def fake_tools(tmp_path, monkeypatch):
    """pg_dump prints a known dump; pg_restore copies its input to a file."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    dump = tmp_path / "dump.bin"
    dump.write_bytes(os.urandom(3 * backups.CHUNK + 123))
    restored = tmp_path / "restored.bin"
    scripts = {
        "pg_dump": f'#!/bin/sh\ntest "$PGPASSWORD" = "pw" || exit 3\ncat "{dump}"\n',
        "pg_restore": f'#!/bin/sh\ncat > "{restored}"\necho "$@" > "{restored}.args"\n',
    }
    for name, body in scripts.items():
        path = bin_dir / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setattr(
        backups.Database,
        "from_settings",
        classmethod(lambda cls, alias="default": cls("sabaq", "sabaq", "pw", "db", "5432")),
    )
    return dump, restored


def test_round_trip_in_chunks():
    plain = os.urandom(backups.CHUNK * 2 + 5)
    f = MultiFernet([Fernet(KEY)])
    out = io.BytesIO()
    assert backups.encrypt_stream(io.BytesIO(plain), out, f) == len(plain)
    data = out.getvalue()
    assert data.startswith(backups.HEADER)
    assert plain[:64] not in data
    assert b"".join(backups.decrypt_chunks(io.BytesIO(data), f)) == plain


def _encrypted(plain: bytes = b"x" * 10) -> bytes:
    out = io.BytesIO()
    backups.encrypt_stream(io.BytesIO(plain), out, MultiFernet([Fernet(KEY)]))
    return out.getvalue()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"nope\n", "not a Sabaq backup"),
        (_encrypted()[:-120], "wrong key or damaged"),
        (b"\n".join(_encrypted().split(b"\n")[:-2]) + b"\n", "cut off"),
        (_encrypted() + _encrypted().split(b"\n")[1] + b"\n", "after the end marker"),
    ],
    ids=["header", "damaged", "cut", "trailing"],
)
def test_damaged_files_are_refused(data, message):
    with pytest.raises(backups.BackupError, match=message):
        list(backups.decrypt_chunks(io.BytesIO(data), MultiFernet([Fernet(KEY)])))


def test_wrong_key_is_refused():
    other = MultiFernet([Fernet(Fernet.generate_key())])
    with pytest.raises(backups.BackupError, match="wrong key"):
        list(backups.decrypt_chunks(io.BytesIO(_encrypted()), other))


def test_old_key_still_reads_after_rotation(settings):
    new = Fernet.generate_key().decode()
    settings.BACKUP_ENCRYPTION_KEYS = [new, KEY]
    assert b"".join(backups.decrypt_chunks(io.BytesIO(_encrypted()))) == b"x" * 10


def test_missing_keys_fail_loudly(settings):
    settings.BACKUP_ENCRYPTION_KEYS = []
    with pytest.raises(Exception, match="BACKUP_ENCRYPTION_KEYS"):
        backups.encrypt_stream(io.BytesIO(b""), io.BytesIO())


def test_backup_and_restore_commands(keys, fake_tools, tmp_path):
    dump, restored = fake_tools
    out = io.StringIO()
    call_command("backup_db", stdout=out)
    files = list((tmp_path / "backups").glob("*.dump.enc"))
    assert len(files) == 1
    assert "backup written" in out.getvalue()
    assert oct(files[0].stat().st_mode & 0o777) == "0o600"
    assert dump.read_bytes()[:64] not in files[0].read_bytes()
    with pytest.raises(CommandError, match="--yes"):
        call_command("restore_db", str(files[0]))
    call_command(
        "restore_db", str(files[0]), "--yes", "--database", "scratch", stdout=io.StringIO()
    )
    assert restored.read_bytes() == dump.read_bytes()
    assert "-d scratch" in (tmp_path / "restored.bin.args").read_text()


def test_failed_dump_leaves_no_file(keys, fake_tools, tmp_path, monkeypatch):
    monkeypatch.setattr(
        backups.Database,
        "from_settings",
        classmethod(lambda cls, alias="default": cls("sabaq", "sabaq", "bad", "db", "5432")),
    )
    with pytest.raises(CommandError, match="pg_dump failed"):
        call_command("backup_db")
    assert not list((tmp_path / "backups").iterdir())


def test_restore_refuses_missing_file(keys):
    with pytest.raises(CommandError, match="No such file"):
        call_command("restore_db", "/nope.enc", "--yes")


def test_backups_need_postgres(monkeypatch):
    sqlite = SimpleNamespace(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}})
    monkeypatch.setattr(backups, "settings", sqlite)
    with pytest.raises(backups.BackupError, match="PostgreSQL"):
        backups.Database.from_settings()


def test_database_settings_are_read_for_postgres(monkeypatch):
    pg = SimpleNamespace(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "n",
                "USER": "u",
                "PASSWORD": "p",
                "HOST": "h",
                "PORT": 6543,
            }
        }
    )
    monkeypatch.setattr(backups, "settings", pg)
    db = backups.Database.from_settings()
    assert db.args() == ["-h", "h", "-p", "6543", "-U", "u", "-d", "n"]
    assert db.args("other")[-1] == "other"
    assert db.env()["PGPASSWORD"] == "p"


def test_missing_tools_are_explained(keys, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(backups.BackupError, match="not installed"):
        backups._tool("pg_dump")


def test_prune_keeps_recent_and_the_newest(tmp_path):
    now = timezone.now()
    names = []
    for days in (30, 20, 3, 0):
        stamp = (now - timedelta(days=days)).strftime("%Y%m%d-%H%M%S")
        p = tmp_path / f"sabaq-{stamp}.dump.enc"
        p.write_bytes(b"x")
        names.append(p)
    (tmp_path / "other.txt").write_text("keep")
    removed = backups.prune(14, now=now, directory=tmp_path)
    assert sorted(removed) == sorted(names[:2])
    assert (tmp_path / "other.txt").exists()
    # Even when every backup is old, the newest stays.
    assert backups.prune(0, now=now + timedelta(days=100), directory=tmp_path) == [names[2]]
