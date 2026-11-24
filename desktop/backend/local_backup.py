"""Versioned backups of the embedded SQLite database."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import re
import sqlite3
from threading import Lock
from time import monotonic


logger = logging.getLogger("marketai.local")

BACKUP_INTERVAL = timedelta(hours=24)
RETENTION = 14
BACKUP_NAME = re.compile(r"marketai-\d{8}T\d{12}Z\.sqlite3")


class LocalBackup:
    def __init__(self, database: Path):
        self.database = database.resolve()
        self.directory = database.parent / "backups"
        self.pending = self.directory / "restore-pending"
        self.lock = Lock()
        self.error = None
        self.restore_result = None

    def _paths(self):
        return sorted(
            (path for path in self.directory.glob("marketai-*.sqlite3")
             if BACKUP_NAME.fullmatch(path.name) and path.is_file() and not path.is_symlink()),
            reverse=True,
        )

    def _pending_name(self):
        return self.pending.read_text(encoding="ascii") if self.pending.exists() else None

    def _copy(self, source, destination, *, validate_source=False):
        deadline = monotonic() + 120

        def check_progress(status, remaining, total):
            if status != sqlite3.SQLITE_DONE and monotonic() >= deadline:
                raise sqlite3.OperationalError("Database copy timed out")

        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            if validate_source:
                self._validate(original)
            with closing(sqlite3.connect(destination)) as target:
                original.backup(target, pages=256, progress=check_progress, sleep=0.1)

    @staticmethod
    def _validate(connection):
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not {"users", "catalog_products", "product_watches"}.issubset(tables):
            raise sqlite3.DatabaseError("Unexpected backup schema")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise sqlite3.DatabaseError("Backup failed integrity check")

    def _snapshot(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.directory / f"marketai-{timestamp}.sqlite3"
        temporary = target.with_suffix(".tmp")
        temporary.touch(mode=0o600, exist_ok=False)
        try:
            self._copy(self.database, temporary)
            with closing(sqlite3.connect(temporary)) as connection:
                self._validate(connection)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def create(self, *, automatic=False):
        with self.lock:
            try:
                existing = self._paths()
                if automatic and existing and (
                    datetime.now(timezone.utc) - self._created_at(existing[0]) < BACKUP_INTERVAL
                ):
                    return
                self._snapshot()
                self._prune(self._pending_name())
                self.error = None
            except (OSError, sqlite3.Error):
                self.error = "backup_failed"
                raise

    def _prune(self, preserve=None):
        paths = self._paths()
        protected = [path for path in paths if path.name == preserve]
        other = [path for path in paths if path.name != preserve]
        for old in other[RETENTION - len(protected):]:
            old.unlink()

    @staticmethod
    def _created_at(path):
        return datetime.strptime(path.stem.removeprefix("marketai-"), "%Y%m%dT%H%M%S%fZ").replace(
            tzinfo=timezone.utc
        )

    def _find(self, name):
        for path in self._paths():
            if path.name == name:
                return path
        raise FileNotFoundError("Backup unavailable")

    def schedule_restore(self, name):
        with self.lock:
            source = self._find(name)
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as connection:
                self._validate(connection)
            temporary = self.pending.with_suffix(".tmp")
            temporary.write_text(name, encoding="ascii")
            temporary.replace(self.pending)
            self.restore_result = None

    def cancel_restore(self):
        with self.lock:
            self.pending.unlink(missing_ok=True)
            self.restore_result = None

    def apply_pending_restore(self):
        """Run before SQLAlchemy opens the local database or starts workers."""
        with self.lock:
            try:
                pending = self._pending_name()
                if pending is None:
                    return
                source = self._find(pending)
                with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as connection:
                    self._validate(connection)
                if self.database.exists():
                    self._snapshot()
                self._copy(source, self.database, validate_source=True)
                self.pending.unlink()
                self.restore_result = "restored"
            except (OSError, sqlite3.Error, UnicodeError):
                self.restore_result = "restore_failed"
                # Leave the request visible, so the user can retry or choose another copy.
                logger.exception("Database restore failed")
                return
            try:
                self._prune(preserve=pending)
            except OSError:
                self.error = "backup_failed"
                logger.exception("Could not rotate backups after restore")

    def status(self):
        with self.lock:
            return {
                "versions": [
                    {"id": path.name, "created_at": self._created_at(path).isoformat(),
                     "bytes": path.stat().st_size}
                    for path in self._paths()
                ],
                "pending": self._pending_name(),
                "restore_result": self.restore_result,
                "error": self.error,
                "retention": RETENTION,
            }
