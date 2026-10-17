"""Non-overwriting moves with a durable operation journal and assisted restore."""

from contextlib import contextmanager
import ctypes
from dataclasses import dataclass, field
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import uuid

from .core import File


@dataclass
class Outcome:
    run_id: str = ""
    moved: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


def default_journal():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "file-collector/history.sqlite3"


@contextmanager
def database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY, run TEXT NOT NULL,
                created TEXT DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL, target TEXT NOT NULL,
                digest TEXT NOT NULL, status TEXT NOT NULL
            );
        """)
        os.chmod(path, 0o600)
        yield connection
    finally:
        connection.close()


@contextmanager
def operation_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(str(path) + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def _same(file):
    return File.read(file.path) == file


def _digest(file, cancel):
    digest = hashlib.sha256()
    with open(os.open(file.path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
                file.device, file.inode, file.size, file.mtime_ns):
            raise ValueError("Source changed; search again")
        while chunk := stream.read(1024 * 1024):
            if cancel.is_set():
                raise InterruptedError("Cancelled")
            digest.update(chunk)
    if not _same(file):
        raise ValueError("Source changed; search again")
    return digest.hexdigest()


def _rename_noreplace(source, target):
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, "renameat2", None)
    if function is None:
        raise OSError(errno.ENOSYS, "Non-overwriting rename unavailable")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(-100, os.fsencode(source), -100, os.fsencode(target), 1):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))


def _rename(source, target):
    _rename_noreplace(source, target)


def _sync_directory(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            os.fsync(fd)
        except OSError as error:
            if error.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
    finally:
        os.close(fd)


def _copy_verified(file, target, digest, cancel):
    """Publish only a complete verified copy; keep source until publication is durable."""
    fd, name = tempfile.mkstemp(prefix=".file-collector-", dir=target.parent)
    staging = Path(name)
    try:
        with os.fdopen(fd, "wb") as output:
            with open(os.open(file.path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as source:
                while chunk := source.read(1024 * 1024):
                    if cancel.is_set():
                        raise InterruptedError("Cancelled")
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if _digest(File.read(staging), cancel) != digest or not _same(file):
            raise ValueError("Copy verification failed; original preserved")
        shutil.copystat(file.path, staging, follow_symlinks=False)
        if cancel.is_set():
            raise InterruptedError("Cancelled")
        try:
            _rename_noreplace(staging, target)
        except OSError as error:
            if error.errno not in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
                raise
            os.link(staging, target, follow_symlinks=False)
            staging.unlink()
        _sync_directory(target.parent)
        if not _same(file):
            raise ValueError("Source changed; both files preserved")
        file.path.unlink()
        _sync_directory(file.path.parent)
    finally:
        staging.unlink(missing_ok=True)


def _move(file, target, digest, cancel):
    if target.parent.resolve() != target.parent:
        raise ValueError("Destination changed; preview again")
    if not _same(file):
        raise ValueError("Source changed; search again")
    if cancel.is_set():
        raise InterruptedError("Cancelled")
    try:
        _rename(file.path, target)
    except OSError as error:
        if error.errno not in (errno.EXDEV, errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
            raise
        _copy_verified(file, target, digest, cancel)
    else:
        _sync_directory(target.parent)
        _sync_directory(file.path.parent)


def collect(plan, journal=None, cancel=None, progress=None):
    journal = journal or default_journal()
    cancel = cancel or threading.Event()
    result = Outcome(run_id=uuid.uuid4().hex)
    with operation_lock(journal), database(journal) as connection:
        for index, item in enumerate(plan):
            if cancel.is_set():
                result.cancelled = True
                break
            if item.skip:
                result.skipped += 1
            else:
                try:
                    digest = _digest(item.file, cancel)
                    cursor = connection.execute(
                        "INSERT INTO operations(run,source,target,digest,status) VALUES(?,?,?,?,?)",
                        (result.run_id, str(item.file.path), str(item.target), digest, "pending"))
                    connection.commit()
                    _move(item.file, item.target, digest, cancel)
                    connection.execute("UPDATE operations SET status='done' WHERE id=?", (cursor.lastrowid,))
                    connection.commit()
                    result.moved += 1
                except InterruptedError:
                    result.cancelled = True
                    break
                except (OSError, ValueError) as error:
                    result.errors.append(f"{item.file.path}: {error}")
            if progress:
                progress(index + 1, len(plan), item.file.path.name)
    return result


def history(journal=None):
    journal = journal or default_journal()
    if not Path(journal).exists():
        return []
    with database(journal) as connection:
        return connection.execute(
            "SELECT run, MIN(created), COUNT(*) FROM operations "
            "WHERE status IN ('done','pending') GROUP BY run ORDER BY MIN(id) DESC").fetchall()


def restore(run_id, journal=None, cancel=None, progress=None):
    journal = journal or default_journal()
    cancel = cancel or threading.Event()
    result = Outcome(run_id=run_id)
    with operation_lock(journal), database(journal) as connection:
        rows = connection.execute(
            "SELECT id,source,target,digest,status FROM operations "
            "WHERE run=? AND status IN ('done','pending') ORDER BY id DESC", (run_id,)).fetchall()
        for index, (ident, source, target, digest, status) in enumerate(rows):
            if cancel.is_set():
                result.cancelled = True
                break
            original, current = Path(source), Path(target)
            try:
                if status == "pending" and os.path.lexists(original) and not os.path.lexists(current):
                    connection.execute("UPDATE operations SET status='unchanged' WHERE id=?", (ident,))
                    connection.commit()
                    result.skipped += 1
                    continue
                if os.path.lexists(original):
                    raise ValueError("Original path is occupied; no files changed")
                file = File.read(current)
                if _digest(file, cancel) != digest:
                    raise ValueError("Collected file was modified; no files changed")
                _move(file, original, digest, cancel)
                connection.execute("UPDATE operations SET status='restored' WHERE id=?", (ident,))
                connection.commit()
                result.moved += 1
            except InterruptedError:
                result.cancelled = True
                break
            except (OSError, ValueError) as error:
                result.errors.append(f"{current}: {error}")
            if progress:
                progress(index + 1, len(rows), current.name)
    return result
