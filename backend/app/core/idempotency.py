"""Idempotency-Key handling for protected POST operations.

The reservation is inserted in the same transaction as the work it protects:
- A concurrent request with the same key blocks on the unique index until the first
  transaction ends, then sees the committed record and replays it. No duplicates.
- If the work fails and rolls back, the reservation disappears and a retry runs again.
- Same key and same input returns the stored references with the original status.
- Same key and different input (or another endpoint) returns 409 IDEMPOTENCY_CONFLICT.
Records expire after idempotency_ttl_hours; an expired key behaves like a new key.
Only a hash of the request and public result IDs are stored, never request content.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import Header, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.jobs.models import APIIdempotencyKey


@dataclass(frozen=True)
class Reservation:
    record_id: UUID


@dataclass(frozen=True)
class Replay:
    status_code: int
    refs: dict[str, Any]


def request_hash(operation: str, payload: Any) -> str:
    canonical = json.dumps(
        {"operation": operation, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def reserve(
    db: AsyncSession,
    *,
    user_id: UUID,
    key: UUID,
    operation: str,
    payload: Any,
    ttl_hours: int,
) -> Reservation | Replay:
    digest = request_hash(operation, payload)
    await db.execute(
        delete(APIIdempotencyKey).where(
            APIIdempotencyKey.user_id == user_id,
            APIIdempotencyKey.idempotency_key == key,
            APIIdempotencyKey.expires_at <= func.now(),
        )
    )
    inserted = await db.execute(
        insert(APIIdempotencyKey)
        .values(
            user_id=user_id,
            idempotency_key=key,
            operation=operation[:160],
            request_hash=digest,
            expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
        )
        .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
        .returning(APIIdempotencyKey.idempotency_record_id)
    )
    record_id = inserted.scalar_one_or_none()
    if record_id is not None:
        return Reservation(record_id)
    existing = await db.scalar(
        select(APIIdempotencyKey).where(
            APIIdempotencyKey.user_id == user_id, APIIdempotencyKey.idempotency_key == key
        )
    )
    if existing is None or existing.status != "completed":
        # Only possible if the other request's transaction is still settling.
        raise ApiError(
            409, "STATE_CONFLICT", "The same request is still being processed.", retryable=True
        )
    if existing.request_hash != digest:
        raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Key was already used for different input.")
    return Replay(existing.response_status, dict(existing.result_refs))


async def complete(
    db: AsyncSession, reservation: Reservation, status_code: int, refs: dict[str, Any]
) -> None:
    await db.execute(
        update(APIIdempotencyKey)
        .where(APIIdempotencyKey.idempotency_record_id == reservation.record_id)
        .values(
            status="completed",
            response_status=status_code,
            result_refs={k: str(v) for k, v in refs.items()},
        )
    )


IdempotencyKey = Annotated[
    UUID,
    Header(
        alias="Idempotency-Key",
        description="New UUID per operation; reuse it with the same body when retrying.",
    ),
]


async def run(
    db: AsyncSession,
    request: Request,
    *,
    user_id: UUID,
    key: UUID,
    payload: Any,
    work: Callable[[], Awaitable[tuple[int, dict[str, Any]]]],
) -> tuple[int, dict[str, Any]]:
    """Reserve, do the work, record (status, result IDs) and commit, all in one transaction.

    Returns the stored (status, refs) on replay. Callers rebuild the response from the
    refs, so a replay shows the resource's current state with the original status code.
    """
    settings = request.app.state.settings
    outcome = await reserve(
        db,
        user_id=user_id,
        key=key,
        operation=f"{request.method} {request.url.path}",
        payload=payload,
        ttl_hours=settings.idempotency_ttl_hours,
    )
    if isinstance(outcome, Replay):
        await db.rollback()
        return outcome.status_code, outcome.refs
    status_code, refs = await work()
    await complete(db, outcome, status_code, refs)
    await db.commit()
    return status_code, {k: str(v) for k, v in refs.items()}
