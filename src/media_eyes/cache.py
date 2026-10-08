"""Cross-process cache transactions, atomic records and bounded retention."""

import json
import re
import shutil
import time
import uuid
from functools import wraps
from pathlib import Path

from filelock import FileLock, Timeout

MEDIA_ID = re.compile(r"^[a-f0-9]{64}$")


def write_json(path: Path, value):
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False))
    temporary.replace(path)


def cached_operation(fn):
    @wraps(fn)
    def wrapped(self, *args, **kwargs):
        try:
            with self.cache_lock.acquire(timeout=30):
                outer = self._cache_depth == 0
                self._cache_depth += 1
                try:
                    if outer:
                        candidate = args[0] if args else kwargs.get("media_id")
                        self._active_media_id = (
                            candidate
                            if isinstance(candidate, str) and MEDIA_ID.fullmatch(candidate)
                            else None
                        )
                        self.cleanup_cache(protected=self._active_media_id)
                    result = fn(self, *args, **kwargs)
                    if outer:
                        self.cleanup_cache(protected=self._active_media_id)
                    return result
                finally:
                    self._cache_depth -= 1
        except Timeout as exc:
            raise ValueError(
                "Media cache is busy; retry after the active operation finishes"
            ) from exc

    return wrapped


def make_lock(cache: Path):
    return FileLock(cache / ".media-eyes.lock")


def prune(cache: Path, ttl_days: float, max_bytes: int, protected: str | None = None):
    entries = []
    for directory in cache.iterdir():
        if (
            not MEDIA_ID.fullmatch(directory.name)
            or directory.is_symlink()
            or not directory.is_dir()
        ):
            continue
        marker = directory / ".access"
        access = marker.stat().st_mtime if marker.exists() else directory.stat().st_mtime
        size = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
        entries.append((access, size, directory))
    total = sum(size for _, size, _ in entries)
    removed = 0
    for access, size, directory in sorted(entries):
        if directory.name == protected:
            continue
        if access < time.time() - ttl_days * 86400 or total > max_bytes:
            shutil.rmtree(directory)
            total -= size
            removed += 1
    if total > max_bytes:
        raise ValueError(
            "Active media exceeds the cache budget; use a shorter source or larger cache"
        )
    return {"removed": removed, "bytes": total}
