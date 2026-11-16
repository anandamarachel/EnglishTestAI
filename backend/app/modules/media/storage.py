"""Private file storage for audio. Files are never served statically.

Storage keys are generated here (never from user input) and every path is checked to
stay inside the root. Writes go to a temporary file first and are renamed into place,
so readers never see a partial file.
"""

import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

KEY_PATTERN = re.compile(r"^[a-z_]+/[0-9a-f]{32}\.[a-z0-9]{1,8}$")
TEMP_PREFIX = ".tmp-"


class MediaStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @staticmethod
    def new_key(purpose: str, extension: str) -> str:
        return f"{purpose}/{uuid4().hex}.{extension}"

    def path(self, key: str) -> Path:
        if not KEY_PATTERN.fullmatch(key):
            raise ValueError("Invalid storage key")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Storage key escapes the media root")
        return path

    def write(self, key: str, data: bytes) -> None:
        """Atomic: the final file appears complete or not at all."""
        final = self.path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        temp = final.parent / f"{TEMP_PREFIX}{uuid4().hex}"
        try:
            with open(temp, "xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, final)
        finally:
            temp.unlink(missing_ok=True)

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def size(self, key: str) -> int | None:
        try:
            return self.path(key).stat().st_size
        except FileNotFoundError:
            return None

    def read(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def read_range(self, key: str, start: int, end: int, chunk: int = 64 * 1024) -> Iterator[bytes]:
        """Bytes start..end inclusive, in chunks."""
        with open(self.path(key), "rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = handle.read(min(chunk, remaining))
                if not data:
                    return
                remaining -= len(data)
                yield data

    def stale_files(self, older_than_seconds: float) -> list[tuple[str | None, Path]]:
        """(key or None for temp/unknown files, path) last modified before the cutoff."""
        if not self.root.exists():
            return []
        cutoff = time.time() - older_than_seconds
        found = []
        for path in self.root.rglob("*"):
            if not path.is_file() or path.stat().st_mtime > cutoff:
                continue
            key = path.relative_to(self.root).as_posix()
            found.append((key if KEY_PATTERN.fullmatch(key) else None, path))
        return found
