from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from app.modules.auth.dependencies import CurrentUserDep, Session
from app.modules.media import service
from app.modules.media.schemas import MediaOut

router = APIRouter(tags=["Media"])

ERRORS = {code: {"description": "Error envelope"} for code in (401, 404, 409, 410, 416, 503)}


@router.get(
    "/media/{media_id}",
    response_model=MediaOut,
    responses=ERRORS,
    summary="Get private media metadata",
)
async def get_media(media_id: UUID, current: CurrentUserDep, session: Session) -> MediaOut:
    return service.to_out(await service.get_owned(session, current.user.user_id, media_id))


@router.get(
    "/media/{media_id}/download",
    responses={
        **ERRORS,
        200: {"content": {"audio/*": {}}, "description": "Audio stream"},
        206: {"content": {"audio/*": {}}, "description": "Partial audio content"},
    },
    response_class=StreamingResponse,
    summary="Download or replay private audio",
)
async def download_media(
    media_id: UUID,
    request: Request,
    current: CurrentUserDep,
    session: Session,
    range_header: str | None = Header(default=None, alias="Range"),
) -> StreamingResponse:
    """Streams the stored file; replay never reruns TTS."""
    store = request.app.state.media_store
    media = await service.get_owned(session, current.user.user_id, media_id)
    size = service.check_downloadable(media, store)
    requested = service.parse_range(range_header, size)
    start, end = requested or (0, size - 1)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Cache-Control": "private, no-store",
    }
    if requested is not None:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    key, mime_type = media.storage_key, media.mime_type
    await session.close()  # release the connection before a possibly long stream
    return StreamingResponse(
        iterate_in_threadpool(store.read_range(key, start, end)),
        status_code=206 if requested is not None else 200,
        media_type=mime_type,
        headers=headers,
    )
