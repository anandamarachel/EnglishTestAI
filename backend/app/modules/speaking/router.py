import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.core import idempotency
from app.core.errors import ApiError
from app.core.pagination import DEFAULT_LIMIT, Cursor, Limit
from app.modules.auth.dependencies import CurrentUserDep, Session
from app.modules.exercises.models import Exercise
from app.modules.exercises.schemas import CreateExerciseResult
from app.modules.jobs import service as jobs
from app.modules.practice import attempts
from app.modules.practice.schemas import AttemptQueuedResult
from app.modules.speaking import service
from app.modules.speaking.models import ConversationMessage
from app.modules.speaking.schemas import (
    ConversationOut,
    CreateSpeakingExerciseRequest,
    MessagePage,
    VoiceTurnResult,
)

router = APIRouter(tags=["Speaking"])

ERRORS = {
    code: {"description": "Error envelope"} for code in (401, 404, 409, 413, 415, 422, 429, 503)
}


@router.post(
    "/speaking/exercises",
    status_code=202,
    response_model=CreateExerciseResult,
    responses=ERRORS,
    summary="Create Speaking exercise",
)
async def create_speaking_exercise(
    data: CreateSpeakingExerciseRequest,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    settings = request.app.state.settings
    user_id = current.user.user_id

    async def work():
        exercise, job = await service.create_exercise(session, settings, user_id, data)
        return 202, {"exercise_id": exercise.exercise_id, "job_id": job.job_id}

    status, refs = await idempotency.run(
        session, request, user_id=user_id, key=key, payload=data.model_dump(mode="json"), work=work
    )
    job = await jobs.get_owned(session, user_id, UUID(refs["job_id"]))
    result = CreateExerciseResult(
        exercise_id=UUID(refs["exercise_id"]), job=await jobs.to_out(session, job)
    )
    return JSONResponse(status_code=status, content=result.model_dump(mode="json"))


async def _owned_speaking(session, user_id: UUID, attempt_id: UUID):
    attempt = await attempts.get_owned(session, user_id, attempt_id)
    exercise = await session.get(Exercise, attempt.exercise_id)
    if exercise.skill != "speaking":
        raise ApiError(409, "STATE_CONFLICT", "Only Speaking attempts have a conversation.")
    return attempt


@router.get(
    "/speaking/attempts/{attempt_id}/conversation",
    response_model=ConversationOut,
    responses=ERRORS,
    summary="Get conversation state",
)
async def get_conversation(
    attempt_id: UUID, current: CurrentUserDep, session: Session
) -> ConversationOut:
    await _owned_speaking(session, current.user.user_id, attempt_id)
    return await service.conversation_out(session, attempt_id)


@router.get(
    "/speaking/attempts/{attempt_id}/messages",
    response_model=MessagePage,
    responses=ERRORS,
    summary="List conversation messages",
)
async def list_messages(
    attempt_id: UUID,
    current: CurrentUserDep,
    session: Session,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> MessagePage:
    """Oldest first. Failed and cancelled turns stay listed with their states."""
    user_id = current.user.user_id
    await _owned_speaking(session, user_id, attempt_id)
    items, next_cursor = await service.list_messages(session, user_id, attempt_id, limit, cursor)
    return MessagePage(items=items, next_cursor=next_cursor)


@router.post(
    "/speaking/attempts/{attempt_id}/turns",
    status_code=202,
    response_model=VoiceTurnResult,
    responses=ERRORS,
    summary="Send a recorded voice turn",
)
async def create_voice_turn(
    attempt_id: UUID,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
    audio: Annotated[UploadFile, File(description="Recorded audio (PCM WAV).")],
    client_message_key: Annotated[UUID, Form()],
) -> JSONResponse:
    """Queues speech-to-text, the persona's reply and its audio (one job)."""
    settings = request.app.state.settings
    store = request.app.state.media_store
    user_id = current.user.user_id
    data = await audio.read(settings.max_audio_bytes + 1)
    if len(data) > settings.max_audio_bytes:
        raise ApiError(413, "CAPACITY_EXCEEDED", "The recording is too large.")
    # The reservation stores a digest of the recording, never the audio itself.
    payload = {
        "client_message_key": str(client_message_key),
        "audio_sha256": hashlib.sha256(data).hexdigest(),
    }

    async def work():
        attempt, exercise = await attempts.lock_attempt(session, user_id, attempt_id)
        message, job = await service.accept_turn(
            session, settings, store, user_id, attempt, exercise, client_message_key, data
        )
        return 202, {"message_id": message.message_id, "job_id": job.job_id}

    status, refs = await idempotency.run(
        session, request, user_id=user_id, key=key, payload=payload, work=work
    )
    message = await session.get(ConversationMessage, UUID(refs["message_id"]))
    await session.refresh(message)
    job = await jobs.get_owned(session, user_id, UUID(refs["job_id"]))
    result = VoiceTurnResult(
        message=await service.message_out(session, message), job=await jobs.to_out(session, job)
    )
    return JSONResponse(status_code=status, content=result.model_dump(mode="json"))


async def _session_change(request, key, current, session, attempt_id, change) -> JSONResponse:
    user_id = current.user.user_id

    async def work():
        attempt, exercise = await attempts.lock_attempt(session, user_id, attempt_id)
        await change(session, attempt, exercise)
        return 200, {"attempt_id": attempt_id}

    status, _ = await idempotency.run(
        session, request, user_id=user_id, key=key, payload={}, work=work
    )
    result = await service.conversation_out(session, attempt_id)
    return JSONResponse(status_code=status, content=result.model_dump(mode="json"))


@router.post(
    "/speaking/attempts/{attempt_id}/pause",
    response_model=ConversationOut,
    responses=ERRORS,
    summary="Pause conversation",
)
async def pause_conversation(
    attempt_id: UUID,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    """New turns are refused; a reply already in progress may still finish."""
    return await _session_change(request, key, current, session, attempt_id, service.pause)


@router.post(
    "/speaking/attempts/{attempt_id}/resume",
    response_model=ConversationOut,
    responses=ERRORS,
    summary="Resume conversation",
)
async def resume_conversation(
    attempt_id: UUID,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    return await _session_change(request, key, current, session, attempt_id, service.resume)


@router.post(
    "/speaking/attempts/{attempt_id}/finish",
    status_code=202,
    response_model=AttemptQueuedResult,
    responses=ERRORS,
    summary="Finish conversation and queue feedback",
)
async def finish_conversation(
    attempt_id: UUID,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    settings = request.app.state.settings
    user_id = current.user.user_id

    async def work():
        attempt, exercise = await attempts.lock_attempt(session, user_id, attempt_id)
        job = await service.finish(session, settings, user_id, attempt, exercise)
        return 202, {"attempt_id": attempt_id, "job_id": job.job_id}

    status, refs = await idempotency.run(
        session, request, user_id=user_id, key=key, payload={}, work=work
    )
    job = await jobs.get_owned(session, user_id, UUID(refs["job_id"]))
    result = AttemptQueuedResult(
        attempt=await attempts.summary(session, attempt_id), job=await jobs.to_out(session, job)
    )
    return JSONResponse(status_code=status, content=result.model_dump(mode="json"))
