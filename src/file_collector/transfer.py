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
import stat
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


def _open_regular(path):
    """Open without blocking on FIFOs or following links; refuse anything but regular files."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Not a regular file")
        return open(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _db_path(path):
    # Names may hold bytes that are not UTF-8; keep them exactly.
    return os.fsencode(str(path))


def _from_db(value):
    return Path(os.fsdecode(value))


def _digest(file, cancel):
    digest = hashlib.sha256()
    with _open_regular(file.path) as stream:
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
    try:
        _rename_noreplace(source, target)
    except OSError as error:
        if error.errno not in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
            raise
        # FAT/exFAT and some network filesystems cannot refuse an overwrite atomically;
        # the operation lock serializes this tool, so check first and rename plainly.
        if os.path.lexists(target):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(target))
        os.rename(source, target)


def _publish(staging, target):
    try:
        _rename_noreplace(staging, target)
    except OSError as error:
        if error.errno not in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
            raise
        try:
            os.link(staging, target, follow_symlinks=False)
        except OSError as link_error:
            if link_error.errno in (errno.EEXIST,):
                raise
            if os.path.lexists(target):
                raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(target)) from None
            os.rename(staging, target)
        else:
            staging.unlink()


def _copy_metadata(source, staging):
    """Keep times and permission bits, but never setuid/setgid; tolerate filesystems without them."""
    info = os.lstat(source)
    try:
        shutil.copystat(source, staging, follow_symlinks=False)
    except OSError:
        try:
            os.utime(staging, ns=(info.st_atime_ns, info.st_mtime_ns))
        except OSError:
            pass
    try:
        if os.geteuid() == 0:
            os.chown(staging, info.st_uid, info.st_gid)
        os.chmod(staging, stat.S_IMODE(info.st_mode) & 0o777)
    except OSError:
        pass


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
            with _open_regular(file.path) as source:
                while chunk := source.read(1024 * 1024):
                    if cancel.is_set():
                        raise InterruptedError("Cancelled")
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if _digest(File.read(staging), cancel) != digest or not _same(file):
            raise ValueError("Copy verification failed; original preserved")
        _copy_metadata(file.path, staging)
        if cancel.is_set():
            raise InterruptedError("Cancelled")
        _publish(staging, target)
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


STAGING_PREFIX = ".file-collector-"


def _remove_stale_staging(plan):
    """Drop partial copies left by an earlier killed run; the operation lock excludes live ones."""
    for directory in {item.target.parent for item in plan}:
        try:
            for entry in os.scandir(directory):
                if entry.name.startswith(STAGING_PREFIX) and entry.is_file(follow_symlinks=False):
                    try:
                        os.unlink(entry.path)
                    except OSError:
                        pass
        except OSError:
            pass


def _untouched(source, target):
    return os.path.lexists(source) and not os.path.lexists(target)


def collect(plan, journal=None, cancel=None, progress=None):
    journal = journal or default_journal()
    cancel = cancel or threading.Event()
    result = Outcome(run_id=uuid.uuid4().hex)
    with operation_lock(journal), database(journal) as connection:
        _remove_stale_staging(plan)
        for index, item in enumerate(plan):
            if cancel.is_set():
                result.cancelled = True
                break
            if item.skip:
                result.skipped += 1
            else:
                ident = None
                try:
                    digest = _digest(item.file, cancel)
                    cursor = connection.execute(
                        "INSERT INTO operations(run,source,target,digest,status) VALUES(?,?,?,?,?)",
                        (result.run_id, _db_path(item.file.path), _db_path(item.target), digest, "pending"))
                    ident = cursor.lastrowid
                    connection.commit()
                    _move(item.file, item.target, digest, cancel)
                    connection.execute("UPDATE operations SET status='done' WHERE id=?", (ident,))
                    connection.commit()
                    result.moved += 1
                except InterruptedError:
                    _mark_failed(connection, ident, item)
                    result.cancelled = True
                    break
                except (OSError, ValueError) as error:
                    _mark_failed(connection, ident, item)
                    result.errors.append(f"{item.file.path}: {error}")
            if progress:
                progress(index + 1, len(plan), item.file.path.name)
    return result


def _mark_failed(connection, ident, item):
    """A move that changed nothing is not a collection; keep 'pending' only for ambiguous states."""
    if ident is not None and _untouched(item.file.path, item.target):
        connection.execute("UPDATE operations SET status='failed' WHERE id=?", (ident,))
        connection.commit()


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
            original, current = _from_db(source), _from_db(target)
            try:
                if status == "pending" and os.path.lexists(original) and not os.path.lexists(current):
                    connection.execute("UPDATE operations SET status='unchanged' WHERE id=?", (ident,))
                    connection.commit()
                    result.skipped += 1
                    if progress:
                        progress(index + 1, len(rows), current.name)
                    continue
                if status == "pending" and os.path.lexists(original) and os.path.lexists(current):
                    # A crash left both: if both still match the recorded content, drop the extra copy.
                    if _digest(File.read(original), cancel) == digest and _digest(File.read(current), cancel) == digest:
                        current.unlink()
                        _sync_directory(current.parent)
                        connection.execute("UPDATE operations SET status='restored' WHERE id=?", (ident,))
                        connection.commit()
                        result.moved += 1
                        if progress:
                            progress(index + 1, len(rows), current.name)
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
