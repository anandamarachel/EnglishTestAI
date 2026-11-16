from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select, tuple_

from app.core.errors import validation_error
from app.core.pagination import DEFAULT_LIMIT, Cursor, Limit, decode_cursor, encode_cursor
from app.modules.auth.dependencies import CurrentUserDep, Session
from app.modules.catalog.models import AIPersona, Topic
from app.modules.catalog.schemas import PersonaOut, PersonaPage, TopicOut, TopicPage

router = APIRouter(tags=["Catalog"])

ERRORS = {code: {"description": "Error envelope"} for code in (401, 422, 429, 503)}


async def _page(session, model, id_column, cursor, limit, scope):
    """Active rows ordered by (name, id); identical for every user, so no owner scope."""
    query = select(model).where(model.is_active.is_(True))
    after = decode_cursor(cursor, scope, 2)
    if after is not None:
        try:
            name, last_id = str(after[0]), UUID(str(after[1]))
        except ValueError:
            raise validation_error("cursor", "Cursor is invalid.") from None
        query = query.where(tuple_(model.name, id_column) > (name, last_id))
    rows = (await session.scalars(query.order_by(model.name, id_column).limit(limit + 1))).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = encode_cursor(scope, [rows[-1].name, getattr(rows[-1], id_column.key)])
    return rows, next_cursor


@router.get("/topics", response_model=TopicPage, responses=ERRORS, summary="List active topics")
async def list_topics(
    _: CurrentUserDep, session: Session, limit: Limit = DEFAULT_LIMIT, cursor: Cursor = None
) -> TopicPage:
    rows, next_cursor = await _page(session, Topic, Topic.topic_id, cursor, limit, "topics")
    items = [TopicOut(topic_id=t.topic_id, name=t.name, description=t.description) for t in rows]
    return TopicPage(items=items, next_cursor=next_cursor)


@router.get(
    "/personas", response_model=PersonaPage, responses=ERRORS, summary="List active AI personas"
)
async def list_personas(
    _: CurrentUserDep, session: Session, limit: Limit = DEFAULT_LIMIT, cursor: Cursor = None
) -> PersonaPage:
    rows, next_cursor = await _page(
        session, AIPersona, AIPersona.persona_id, cursor, limit, "personas"
    )
    items = [
        PersonaOut(persona_id=p.persona_id, name=p.name, role_description=p.role_description)
        for p in rows
    ]
    return PersonaPage(items=items, next_cursor=next_cursor)
