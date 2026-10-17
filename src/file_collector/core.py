"""Read-only discovery and deterministic destination previews."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import fnmatch
import os
from pathlib import Path
import re
import stat
import threading


@dataclass(frozen=True)
class Filters:
    extensions: str = ""
    name: str = ""
    min_size: int = 0
    max_size: int | None = None
    after: str = ""
    before: str = ""
    max_depth: int | None = None
    excluded: str = ""
    hidden: bool = False

    def __post_init__(self):
        if self.min_size < 0 or (self.max_size is not None and self.max_size < self.min_size):
            raise ValueError("Invalid size range")
        if self.max_depth is not None and self.max_depth < 0:
            raise ValueError("Invalid depth")
        for value in (self.after, self.before):
            if value:
                date.fromisoformat(value)
        if self.after and self.before and self.after > self.before:
            raise ValueError("Invalid date range")


@dataclass(frozen=True)
class File:
    path: Path
    size: int
    mtime_ns: int
    device: int
    inode: int

    @classmethod
    def read(cls, path):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Not a regular file")
        return cls(path, info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino)


@dataclass
class SearchResult:
    files: list[File] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


def _parts(value):
    return [part for part in re.split(r"[,;\s]+", value.casefold()) if part]


def scan(roots, filters, destination=None, cancel=None):
    """Scan without following links; a depth of zero scans root files only."""
    cancel = cancel or threading.Event()
    result = SearchResult()
    visited = {}
    destination = Path(destination).resolve() if destination else None
    extensions = {ext.lstrip("*.") for ext in _parts(filters.extensions)}
    excluded = _parts(filters.excluded)
    after = datetime.combine(date.fromisoformat(filters.after), time()).timestamp() if filters.after else None
    before = datetime.combine(date.fromisoformat(filters.before) + timedelta(days=1), time()).timestamp() if filters.before else None
    stack = []
    for root in roots:
        path = Path(root).expanduser().resolve()
        if path.is_dir():
            stack.append((path, 0))
        else:
            result.errors.append(str(path) + ": not a directory")
    while stack and not cancel.is_set():
        directory, depth = stack.pop()
        if directory == destination or (destination and destination in directory.parents):
            continue
        if directory in visited and visited[directory] <= depth:
            continue
        visited[directory] = depth
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if cancel.is_set():
                        break
                    if not filters.hidden and entry.name.startswith("."):
                        continue
                    path = Path(entry.path)
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if not any(fnmatch.fnmatchcase(entry.name.casefold(), pat) for pat in excluded):
                                if filters.max_depth is None or depth < filters.max_depth:
                                    stack.append((path, depth + 1))
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        if extensions and path.suffix.lstrip(".").casefold() not in extensions:
                            continue
                        if filters.name.casefold() not in entry.name.casefold():
                            continue
                        file = File.read(path)
                        if file.size < filters.min_size or (filters.max_size is not None and file.size > filters.max_size):
                            continue
                        modified = file.mtime_ns / 1_000_000_000
                        if (after is not None and modified < after) or (before is not None and modified >= before):
                            continue
                        result.files.append(file)
                    except (OSError, ValueError) as error:
                        result.errors.append(f"{path}: {error}")
        except OSError as error:
            result.errors.append(f"{directory}: {error}")
    result.files = sorted({file.path: file for file in result.files}.values(),
                          key=lambda file: (file.path.name.casefold(), str(file.path)))
    result.cancelled = cancel.is_set()
    return result


@dataclass(frozen=True)
class PlanItem:
    file: File
    target: Path
    skip: bool = False
    renamed: bool = False


def make_plan(files, destination, conflicts="rename"):
    if conflicts not in ("rename", "skip"):
        raise ValueError("Unknown conflict policy")
    destination = Path(destination).expanduser().resolve()
    if not destination.is_dir():
        raise ValueError("Choose an existing destination folder")
    occupied = {entry.name.casefold() for entry in destination.iterdir()}
    plan = []
    for file in files:
        target = destination / file.path.name
        if destination in file.path.parents:
            plan.append(PlanItem(file, target, skip=True))
            continue
        conflict = target.name.casefold() in occupied
        if conflict and conflicts == "skip":
            plan.append(PlanItem(file, target, skip=True))
            continue
        number = 1
        while target.name.casefold() in occupied:
            target = destination / f"{file.path.stem}_{number:03}{file.path.suffix}"
            number += 1
        occupied.add(target.name.casefold())
        plan.append(PlanItem(file, target, renamed=conflict))
    return plan
