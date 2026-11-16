from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core import idempotency
from app.modules.auth.dependencies import CurrentUserDep, Session
from app.modules.jobs import service
from app.modules.jobs.schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["Jobs"])

ERRORS = {code: {"description": "Error envelope"} for code in (401, 404, 409, 422, 429, 503)}


@router.get("/{job_id}", response_model=JobOut, responses=ERRORS, summary="Get job")
async def get_job(job_id: UUID, current: CurrentUserDep, session: Session) -> JobOut:
    """Public state only: no leases, counters, prompts or provider errors."""
    return await service.to_out(
        session, await service.get_owned(session, current.user.user_id, job_id)
    )


async def _transition(request, session, user_id, job_id, key, action) -> JSONResponse:
    async def work():
        job = await service.lock_job(session, job_id, user_id)
        status = await action(job)
        return status, {"job_id": job.job_id}

    status, _ = await idempotency.run(
        session, request, user_id=user_id, key=key, payload={"job_id": str(job_id)}, work=work
    )
    job = await service.get_owned(session, user_id, job_id)
    await session.refresh(job)
    out = await service.to_out(session, job)
    return JSONResponse(status_code=status, content=out.model_dump(mode="json"))


@router.post(
    "/{job_id}/cancel",
    response_model=JobOut,
    responses={**ERRORS, 202: {"model": JobOut}},
    summary="Cancel job",
)
async def cancel_job(
    job_id: UUID,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    async def action(job):
        return await service.cancel(session, job)

    return await _transition(request, session, current.user.user_id, job_id, key, action)


@router.post(
    "/{job_id}/retry", status_code=202, response_model=JobOut, responses=ERRORS, summary="Retry job"
)
async def retry_job(
    job_id: UUID,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    async def action(job):
        await service.retry(session, job)
        return 202

    return await _transition(request, session, current.user.user_id, job_id, key, action)
