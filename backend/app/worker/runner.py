"""Durable AI job worker.

Each job runs in three steps:
1. claim (short transaction): pick a due job, mark it running with a lease, bump the
   execution version when recovering an expired lease, and read the handler's input;
2. execute (no transaction): call the AI engine with a timeout while a heartbeat
   renews the lease;
3. publish (short transaction): re-lock and check the job is still running with the
   same execution version; only then write domain results and mark it succeeded.
   Cancelled or superseded executions are discarded, never published.
Failures requeue with exponential backoff until max_attempts, then fail the job and
its exercise/evaluation. Model calls never happen inside a database transaction.

A handler may also define:
- ready: checked at claim; when False the job is deferred without using an attempt
  (the Listening coordinator waits for its grading jobs this way);
- discard: cleans up a result that was not published (e.g. a stored audio file).
Files left behind by a crash are removed later by the orphan sweep.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.engine import AIEngine, AIError
from app.core.config import Settings
from app.db import models  # noqa: F401 -- register every table so foreign keys resolve
from app.db.session import Database
from app.modules.exercises.models import Exercise
from app.modules.jobs import service as jobs
from app.modules.jobs.models import AIJob
from app.modules.listening import service as listening
from app.modules.media import service as media
from app.modules.media.storage import MediaStore
from app.modules.quiz import service as quiz
from app.modules.reading import service as reading
from app.modules.speaking import service as speaking
from app.modules.writing import service as writing

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Handler:
    prepare: Callable[[AsyncSession, AIJob], Awaitable[Any]]
    execute: Callable[[AIEngine, Any], Awaitable[Any]]
    publish: Callable[[AsyncSession, AIEngine, Any, Any], Awaitable[dict]]
    ready: Callable[[AsyncSession, AIJob], Awaitable[bool]] | None = None
    discard: Callable[[Any], None] | None = None


async def _handler_for(
    db: AsyncSession, job: AIJob, settings: Settings, store: MediaStore
) -> Handler | None:
    skill = await db.scalar(
        select(Exercise.skill).where(Exercise.exercise_id == await jobs.exercise_id_for(db, job))
    )
    if skill == "writing" and job.job_type == "generate_exercise":
        return Handler(
            writing.prepare_generation, writing.execute_generation, writing.publish_generation
        )
    if skill == "writing" and job.job_type == "evaluate_attempt":
        return Handler(
            writing.prepare_evaluation, writing.execute_evaluation, writing.publish_evaluation
        )
    if skill == "reading" and job.job_type == "generate_exercise":
        return Handler(
            partial(reading.prepare_generation, settings=settings),
            reading.execute_generation,
            reading.publish_generation,
        )
    if skill == "listening" and job.job_type == "generate_exercise":
        return Handler(
            partial(listening.prepare_generation, settings=settings),
            partial(listening.execute_generation, store=store),
            listening.publish_generation,
            discard=partial(listening.discard_generation, store=store),
        )
    if skill == "listening" and job.job_type == "evaluate_attempt":
        return Handler(
            listening.prepare_coordination,
            listening.execute_coordination,
            listening.publish_coordination,
            ready=listening.coordinator_ready,
        )
    if skill == "speaking" and job.job_type == "generate_exercise":
        return Handler(
            speaking.prepare_generation, speaking.execute_generation, speaking.publish_generation
        )
    if skill == "speaking" and job.job_type in ("start_conversation", "process_voice_turn"):
        return Handler(
            partial(speaking.prepare_voice, settings=settings),
            partial(speaking.execute_voice, store=store),
            speaking.publish_voice,
            discard=partial(speaking.discard_voice, store=store),
        )
    if skill == "speaking" and job.job_type == "evaluate_attempt":
        return Handler(
            speaking.prepare_evaluation,
            partial(speaking.execute_evaluation, store=store),
            speaking.publish_evaluation,
        )
    if job.job_type == "grade_answer":
        return Handler(quiz.prepare_grade, quiz.execute_grade, quiz.publish_grade)
    return None


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    version: int
    handler: Handler
    data: Any


class Worker:
    def __init__(self, settings: Settings, database: Database, engine: AIEngine) -> None:
        self.settings = settings
        self.database = database
        self.engine = engine
        self.lease = timedelta(seconds=settings.job_lease_seconds)
        self.store = MediaStore(settings.media_storage_dir)
        self._last_sweep: float | None = None

    # --- Claiming ------------------------------------------------------------------

    async def _candidates(self, limit: int) -> list[UUID]:
        async with self.database.sessions() as db:
            now = func.now()
            due = or_(AIJob.next_retry_at.is_(None), AIJob.next_retry_at <= now)
            expired = AIJob.lease_expires_at < now
            rows = await db.scalars(
                select(AIJob.job_id)
                .where(
                    or_(
                        (AIJob.status == "queued") & due,
                        AIJob.status.in_(("running", "cancel_requested")) & expired,
                    )
                )
                .order_by(AIJob.created_at)
                .limit(limit)
            )
            return list(rows)

    async def _claim(self, job_id: UUID) -> Claim | None:
        async with self.database.sessions() as db:
            job = await jobs.lock_job(db, job_id)
            now = datetime.now(UTC)
            lease_expired = job.lease_expires_at is not None and job.lease_expires_at < now
            if job.status == "cancel_requested" and lease_expired:
                job.status = "cancelled"  # its worker died; nothing left to stop
                job.finished_at = func.now()
                job.lease_expires_at = None
                await db.commit()
                return None
            due = job.next_retry_at is None or job.next_retry_at <= now
            claimable = (job.status == "queued" and due) or (
                job.status == "running" and lease_expired
            )
            if not claimable:
                await db.rollback()  # another worker took it, or it changed meanwhile
                return None
            if job.attempt_count >= job.max_attempts:
                await jobs.fail(db, job, "LEASE_EXPIRED")
                await db.commit()
                return None
            handler = await _handler_for(db, job, self.settings, self.store)
            if handler is None:
                await jobs.fail(db, job, "UNSUPPORTED_JOB")
                await db.commit()
                return None
            if handler.ready is not None and not await handler.ready(db, job):
                if job.status == "running":  # recovered while waiting: drop that execution
                    job.execution_version = job.execution_version + 1
                job.status = "queued"
                job.lease_expires_at = None
                job.next_retry_at = now + timedelta(seconds=self.settings.coordinator_poll_seconds)
                await db.commit()
                return None
            if job.status == "running":  # recovering: invalidate the vanished execution
                job.execution_version = job.execution_version + 1
            job.status = "running"
            job.attempt_count = job.attempt_count + 1
            job.started_at = job.started_at or func.now()
            job.lease_expires_at = now + self.lease
            job.next_retry_at = None
            try:
                data = await handler.prepare(db, job)
            except AIError as error:
                await jobs.fail(db, job, error.code)
                await db.commit()
                return None
            version = job.execution_version
            await db.commit()
            return Claim(job_id, version, handler, data)

    # --- Running -------------------------------------------------------------------

    async def _heartbeat(self, claim: Claim) -> None:
        interval = max(1.0, self.lease.total_seconds() / 3)
        while True:
            await asyncio.sleep(interval)
            async with self.database.sessions() as db:
                job = await jobs.lock_job(db, claim.job_id)
                if job.status != "running" or job.execution_version != claim.version:
                    await db.rollback()
                    return
                job.lease_expires_at = datetime.now(UTC) + self.lease
                await db.commit()

    async def _execute(self, claim: Claim) -> Any:
        heartbeat = asyncio.create_task(self._heartbeat(claim))
        try:
            return await asyncio.wait_for(
                claim.handler.execute(self.engine, claim.data),
                timeout=self.settings.ai_request_timeout_seconds,
            )
        except TimeoutError:
            raise AIError("AI_TIMEOUT", retryable=True) from None
        finally:
            heartbeat.cancel()

    async def _publish(self, claim: Claim, result: Any) -> bool:
        async with self.database.sessions() as db:
            job = await jobs.lock_job(db, claim.job_id)
            if job.status == "cancel_requested":
                job.status = "cancelled"
                job.finished_at = func.now()
                job.lease_expires_at = None
                await db.commit()
                return False
            if job.status != "running" or job.execution_version != claim.version:
                await db.rollback()  # superseded: a newer execution owns this job
                return False
            refs = await claim.handler.publish(db, self.engine, claim.data, result)
            job.status = "succeeded"
            job.finished_at = func.now()
            job.lease_expires_at = None
            job.error_code = None
            job.result_refs = {k: str(v) for k, v in refs.items()}
            await db.commit()
            return True

    async def _record_failure(self, claim: Claim, error: AIError) -> None:
        async with self.database.sessions() as db:
            job = await jobs.lock_job(db, claim.job_id)
            if job.status == "cancel_requested":
                job.status = "cancelled"
                job.finished_at = func.now()
                job.lease_expires_at = None
            elif job.status != "running" or job.execution_version != claim.version:
                await db.rollback()
                return
            elif error.retryable and job.attempt_count < job.max_attempts:
                delay = min(
                    self.settings.job_retry_max_seconds,
                    self.settings.job_retry_base_seconds * 2 ** (job.attempt_count - 1),
                )
                job.status = "queued"
                job.error_code = error.code
                job.lease_expires_at = None
                job.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
            else:
                await jobs.fail(db, job, error.code)
            await db.commit()

    async def process(self, claim: Claim) -> None:
        try:
            result = await self._execute(claim)
        except AIError as error:
            logger.warning("Job %s failed: %s", claim.job_id, error.code)
            await self._record_failure(claim, error)
            return
        except Exception:
            logger.exception("Job %s crashed", claim.job_id)
            await self._record_failure(claim, AIError("AI_ERROR", retryable=True))
            return
        # Discard only when the result certainly was not committed. After an ambiguous
        # failure (e.g. connection lost during commit) the file is kept; the orphan sweep
        # removes it later if no row references it.
        discard = False
        try:
            discard = not await self._publish(claim, result)
        except IntegrityError:
            # The database rejected the output (e.g. spans); treat as invalid model output.
            logger.warning("Job %s output rejected by database checks", claim.job_id)
            discard = True
            await self._record_failure(claim, AIError("AI_OUTPUT_INVALID", retryable=True))
        except AIError as error:
            logger.warning("Job %s could not publish: %s", claim.job_id, error.code)
            discard = True
            await self._record_failure(claim, error)
        finally:
            if discard and claim.handler.discard is not None:
                await asyncio.to_thread(claim.handler.discard, result)

    async def sweep_media(self) -> int:
        """Remove stored files that no media row references (after a grace period)."""
        async with self.database.sessions() as db:
            removed = await media.sweep_orphans(
                db, self.store, self.settings.media_orphan_grace_seconds
            )
        if removed:
            logger.info("Removed %d orphaned media file(s)", removed)
        return removed

    async def _maybe_sweep(self) -> None:
        now = asyncio.get_running_loop().time()
        if (
            self._last_sweep is None
            or now - self._last_sweep >= self.settings.media_sweep_interval_seconds
        ):
            self._last_sweep = now
            try:
                await self.sweep_media()
            except Exception:
                logger.exception("Media sweep failed")

    async def run_once(self) -> int:
        """Claim and process up to worker_concurrency jobs. Returns how many ran."""
        claims = []
        for job_id in await self._candidates(self.settings.worker_concurrency * 4):
            claim = await self._claim(job_id)
            if claim is not None:
                claims.append(claim)
            if len(claims) >= self.settings.worker_concurrency:
                break
        await asyncio.gather(*(self.process(claim) for claim in claims))
        return len(claims)

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._maybe_sweep()
            try:
                processed = await self.run_once()
            except Exception:
                logger.exception("Worker loop error")
                processed = 0
            if processed == 0:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self.settings.worker_poll_seconds)
                except TimeoutError:
                    pass
