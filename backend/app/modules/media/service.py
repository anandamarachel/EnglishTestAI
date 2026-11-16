"""Private media: ownership checks, download ranges and orphan cleanup."""

import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.media.models import MediaAsset
from app.modules.media.schemas import MediaOut
from app.modules.media.storage import MediaStore

logger = logging.getLogger(__name__)
RANGE_PATTERN = re.compile(r"bytes=([0-9]*)-([0-9]*)")


def is_available(media: MediaAsset) -> bool:
    expired = media.expires_at is not None and media.expires_at <= datetime.now(UTC)
    return media.status == "ready" and not expired


def to_out(media: MediaAsset) -> MediaOut:
    return MediaOut(
        media_id=media.media_id,
        purpose=media.purpose,
        mime_type=media.mime_type,
        size_bytes=media.size_bytes,
        duration_ms=media.duration_ms,
        status=media.status,
        available=is_available(media),
    )


async def get_owned(db: AsyncSession, user_id: UUID, media_id: UUID) -> MediaAsset:
    media = await db.scalar(
        select(MediaAsset).where(
            MediaAsset.media_id == media_id, MediaAsset.owner_user_id == user_id
        )
    )
    if media is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return media


def _unavailable() -> ApiError:
    return ApiError(410, "MEDIA_UNAVAILABLE", "Audio has expired or was deleted.")


def check_downloadable(media: MediaAsset, store: MediaStore) -> int:
    """File size once the media can be streamed; otherwise the matching error."""
    if media.status in ("pending", "failed"):
        retryable = media.status == "pending"
        raise ApiError(409, "MEDIA_NOT_READY", "This audio is not ready.", retryable=retryable)
    if not is_available(media):
        raise _unavailable()
    size = store.size(media.storage_key)
    if size is None or size != media.size_bytes:
        # A ready row whose file is missing or changed is an operations fault; never
        # serve a different file. Logged without the storage key.
        logger.error("Media file missing or size mismatch for media %s", media.media_id)
        raise _unavailable()
    return size


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """One byte range (inclusive), None for the whole file. Anything else is 416."""
    if header is None:
        return None
    match = RANGE_PATTERN.fullmatch(header.strip())
    unsatisfiable = ApiError(
        416,
        "RANGE_NOT_SATISFIABLE",
        "Requested audio range is unavailable.",
        headers={"Content-Range": f"bytes */{size}"},
    )
    if match is None or match[1] == match[2] == "":
        raise unsatisfiable
    if match[1] == "":  # suffix: the last N bytes
        length = int(match[2])
        if length == 0:
            raise unsatisfiable
        return max(0, size - length), size - 1
    start = int(match[1])
    end = int(match[2]) if match[2] else size - 1
    if start >= size or end < start:
        raise unsatisfiable
    return start, min(end, size - 1)


async def sweep_orphans(db: AsyncSession, store: MediaStore, grace_seconds: float) -> int:
    """Delete old files that no media row references (failed or interrupted writes).

    Referenced files are never touched, whatever their status. The grace period must
    exceed the time between writing a file and committing its row.
    """
    candidates = store.stale_files(grace_seconds)
    keys = [key for key, _ in candidates if key is not None]
    referenced: set[str] = set()
    for index in range(0, len(keys), 500):
        batch = keys[index : index + 500]
        referenced.update(
            await db.scalars(
                select(MediaAsset.storage_key).where(MediaAsset.storage_key.in_(batch))
            )
        )
    removed = 0
    for key, path in candidates:
        if key is None or key not in referenced:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
