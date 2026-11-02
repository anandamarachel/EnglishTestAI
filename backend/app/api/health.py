import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/live")
async def liveness() -> dict[str, str]:
    """Process health, deliberately independent of PostgreSQL and the AI PC."""
    return {"status": "ok"}


@router.get("/ready", responses={503: {"description": "Database unavailable"}})
async def readiness(session: Annotated[AsyncSession, Depends(get_session)]) -> JSONResponse:
    """Database connectivity only; migrations are verified separately during deployment."""
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Driver exception strings can contain connection details; do not expose them.
        logger.warning("Database readiness check failed")
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return JSONResponse(content={"status": "ok"})
