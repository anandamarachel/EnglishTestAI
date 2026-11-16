from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.config import Settings
from app.modules.auth.dependencies import CurrentUserDep

router = APIRouter(tags=["Capabilities"])


class SpeakingCapabilities(BaseModel):
    live_transcription: bool
    pronunciation_assessment: bool


class Limits(BaseModel):
    max_audio_bytes: int
    max_audio_duration_ms: int
    max_request_bytes: int


class Capabilities(BaseModel):
    speaking: SpeakingCapabilities
    limits: Limits


@router.get(
    "/capabilities",
    response_model=Capabilities,
    responses={401: {"description": "Error envelope"}},
    summary="Get capabilities and configured limits",
)
async def get_capabilities(_: CurrentUserDep, request: Request) -> Capabilities:
    settings: Settings = request.app.state.settings
    return Capabilities(
        # Only true once implemented and verified; neither exists yet.
        speaking=SpeakingCapabilities(live_transcription=False, pronunciation_assessment=False),
        limits=Limits(
            max_audio_bytes=settings.max_audio_bytes,
            max_audio_duration_ms=settings.max_audio_duration_ms,
            max_request_bytes=settings.max_request_bytes,
        ),
    )
