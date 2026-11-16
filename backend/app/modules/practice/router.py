from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core import idempotency
from app.core.errors import ApiError
from app.core.pagination import DEFAULT_LIMIT, Cursor, Limit
from app.modules.assessment import service as assessment
from app.modules.assessment.schemas import EvaluationOut
from app.modules.auth.dependencies import CurrentUserDep, Session
from app.modules.jobs import service as jobs
from app.modules.practice import attempts, service
from app.modules.practice.schemas import (
    AttemptDetail,
    AttemptGradedResult,
    AttemptQueuedResult,
    AttemptResult,
    AttemptStatus,
    AttemptSummaryPage,
    CreateAttemptRequest,
    CreateAttemptResult,
    Dashboard,
    SavedDraft,
    SaveDraftRequest,
    Skill,
    SubmitAttemptRequest,
)
from app.modules.quiz import service as quiz
from app.modules.quiz.models import Answer
from app.modules.quiz.schemas import (
    AnswerFeedbackOut,
    AnswerGradedResult,
    AnswerQueuedResult,
    SubmitAnswerRequest,
)
from app.modules.speaking import service as speaking
from app.modules.users.service import to_user_out

router = APIRouter(tags=["Practice"])

ERRORS = {code: {"description": "Error envelope"} for code in (401, 404, 422, 429, 503)}


@router.get("/dashboard", response_model=Dashboard, responses=ERRORS, summary="Get dashboard")
async def get_dashboard(current: CurrentUserDep, session: Session) -> Dashboard:
    user_id = current.user.user_id
    pending, has_more = await service.pending_attempts(session, user_id)
    return Dashboard(
        user=to_user_out(current.user),
        resume_attempt=await service.resume_attempt(session, user_id),
        pending_attempts=pending,
        has_more_pending=has_more,
    )


@router.get(
    "/attempts", response_model=AttemptSummaryPage, responses=ERRORS, summary="List attempts"
)
async def list_attempts(
    current: CurrentUserDep,
    session: Session,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    skill: Skill | None = None,
    status: AttemptStatus | None = None,
) -> AttemptSummaryPage:
    items, next_cursor = await service.list_attempts(
        session, current.user.user_id, skill=skill, status=status, limit=limit, cursor=cursor
    )
    return AttemptSummaryPage(items=items, next_cursor=next_cursor)


# --- Attempt lifecycle -------------------------------------------------------------

MUTATION_ERRORS = {
    code: {"description": "Error envelope"} for code in (401, 404, 409, 413, 422, 429, 503)
}


@router.post(
    "/exercises/{exercise_id}/attempts",
    status_code=201,
    response_model=CreateAttemptResult,
    responses=MUTATION_ERRORS,
    summary="Start attempt",
)
async def create_attempt(
    exercise_id: UUID,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
    data: CreateAttemptRequest | None = None,
) -> JSONResponse:
    data = data or CreateAttemptRequest()
    user_id = current.user.user_id

    settings = request.app.state.settings

    async def work():
        attempt, job = await attempts.create(
            session, settings, user_id, exercise_id, data.source_attempt_id
        )
        refs = {"attempt_id": attempt.attempt_id}
        return 201, {**refs, "job_id": job.job_id} if job else refs

    status, refs = await idempotency.run(
        session, request, user_id=user_id, key=key, payload=data.model_dump(mode="json"), work=work
    )
    attempt_id = UUID(refs["attempt_id"])
    job = await jobs.get_owned(session, user_id, UUID(refs["job_id"])) if "job_id" in refs else None
    result = CreateAttemptResult(
        attempt=await attempts.summary(session, attempt_id),
        conversation=await speaking.conversation_out(session, attempt_id),
        job=await jobs.to_out(session, job) if job else None,
    )
    return JSONResponse(status_code=status, content=result.model_dump(mode="json"))


@router.get(
    "/attempts/{attempt_id}", response_model=AttemptDetail, responses=ERRORS, summary="Get attempt"
)
async def get_attempt(attempt_id: UUID, current: CurrentUserDep, session: Session) -> AttemptDetail:
    return await attempts.detail(session, current.user.user_id, attempt_id)


@router.patch(
    "/attempts/{attempt_id}/draft",
    response_model=SavedDraft,
    responses=MUTATION_ERRORS,
    summary="Save draft",
)
async def save_draft(
    attempt_id: UUID, data: SaveDraftRequest, current: CurrentUserDep, session: Session
) -> SavedDraft:
    attempt = await attempts.save_draft(
        session, current.user.user_id, attempt_id, data.revision, data.draft
    )
    await session.commit()
    return SavedDraft(
        attempt_id=attempt.attempt_id,
        revision=attempt.revision,
        last_saved_at=attempt.last_saved_at,
        last_activity_at=attempt.last_activity_at,
    )


@router.post(
    "/attempts/{attempt_id}/submit",
    status_code=202,
    response_model=AttemptQueuedResult,
    responses={**MUTATION_ERRORS, 200: {"model": AttemptGradedResult}},
    summary="Submit attempt",
)
async def submit_attempt(
    attempt_id: UUID,
    data: SubmitAttemptRequest,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    """Writing: 202 with the evaluation job. Reading: 200 with the final quiz result."""
    settings = request.app.state.settings
    user_id = current.user.user_id

    async def work():
        attempt, job, evaluation = await attempts.submit(
            session, settings, user_id, attempt_id, data.revision
        )
        if job is not None:
            return 202, {"attempt_id": attempt.attempt_id, "job_id": job.job_id}
        return 200, {"attempt_id": attempt.attempt_id, "evaluation_id": evaluation.evaluation_id}

    status, refs = await idempotency.run(
        session, request, user_id=user_id, key=key, payload=data.model_dump(mode="json"), work=work
    )
    summary = await attempts.summary(session, attempt_id)
    if "job_id" in refs:
        job = await jobs.get_owned(session, user_id, UUID(refs["job_id"]))
        result = AttemptQueuedResult(attempt=summary, job=await jobs.to_out(session, job))
    else:
        evaluation = await assessment.get_for_attempt(session, attempt_id)
        result = AttemptGradedResult(
            attempt=summary, evaluation=await assessment.to_out(session, evaluation)
        )
    return JSONResponse(status_code=status, content=result.model_dump(mode="json"))


@router.post(
    "/attempts/{attempt_id}/answers/{question_id}/submit",
    status_code=200,
    response_model=AnswerGradedResult,
    responses={**MUTATION_ERRORS, 202: {"model": AnswerQueuedResult}},
    summary="Submit one Reading answer",
)
async def submit_answer(
    attempt_id: UUID,
    question_id: UUID,
    data: SubmitAnswerRequest,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    """Multiple choice: 200 with feedback now. Short answer: 202 with its grading job."""
    settings = request.app.state.settings
    user_id = current.user.user_id

    async def work():
        answer, job = await attempts.submit_answer(
            session, settings, user_id, attempt_id, question_id, data
        )
        attempt = await attempts.get_owned(session, user_id, attempt_id)
        refs = {"answer_id": answer.answer_id, "attempt_revision": attempt.revision}
        if job is not None:
            return 202, {**refs, "job_id": job.job_id}
        return 200, refs

    status, refs = await idempotency.run(
        session, request, user_id=user_id, key=key, payload=data.model_dump(mode="json"), work=work
    )
    answer = await session.get(Answer, UUID(refs["answer_id"]))
    await session.refresh(answer)
    revision = int(refs["attempt_revision"])
    if "job_id" in refs:
        job = await jobs.get_owned(session, user_id, UUID(refs["job_id"]))
        result = AnswerQueuedResult(
            answer=quiz.answer_out(answer, answer.grading_status == "graded"),
            job=await jobs.to_out(session, job),
            attempt_revision=revision,
        )
    else:
        result = AnswerGradedResult(
            answer=quiz.answer_out(answer, True),
            feedback=await quiz.feedback_out(session, answer),
            attempt_revision=revision,
        )
    return JSONResponse(status_code=status, content=result.model_dump(mode="json"))


@router.get(
    "/attempts/{attempt_id}/answers/{question_id}/feedback",
    response_model=AnswerFeedbackOut,
    responses={**ERRORS, 409: {"description": "FEEDBACK_LOCKED or GRADING_PENDING"}},
    summary="Get answer feedback",
)
async def get_answer_feedback(
    attempt_id: UUID, question_id: UUID, current: CurrentUserDep, session: Session
) -> AnswerFeedbackOut:
    return await attempts.answer_feedback(session, current.user.user_id, attempt_id, question_id)


@router.post(
    "/attempts/{attempt_id}/cancel",
    response_model=AttemptResult,
    responses=MUTATION_ERRORS,
    summary="Cancel attempt",
)
async def cancel_attempt(
    attempt_id: UUID,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    user_id = current.user.user_id

    async def work():
        attempt = await attempts.cancel(session, user_id, attempt_id)
        return 200, {"attempt_id": attempt.attempt_id}

    status, _ = await idempotency.run(
        session, request, user_id=user_id, key=key, payload={}, work=work
    )
    result = AttemptResult(attempt=await attempts.summary(session, attempt_id))
    return JSONResponse(status_code=status, content=result.model_dump(mode="json"))


@router.get(
    "/attempts/{attempt_id}/evaluation",
    response_model=EvaluationOut,
    responses=ERRORS,
    summary="Get evaluation",
)
async def get_evaluation(
    attempt_id: UUID, current: CurrentUserDep, session: Session
) -> EvaluationOut:
    await attempts.get_owned(session, current.user.user_id, attempt_id)
    evaluation = await assessment.get_for_attempt(session, attempt_id)
    if evaluation is None:
        raise ApiError(404, "NOT_FOUND", "No evaluation yet.")
    return await assessment.to_out(session, evaluation)
