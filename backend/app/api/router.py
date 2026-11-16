from fastapi import APIRouter

from app.api.capabilities import router as capabilities_router
from app.api.health import router as health_router
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.exercises.router import router as exercises_router
from app.modules.jobs.router import router as jobs_router
from app.modules.listening.router import router as listening_router
from app.modules.media.router import router as media_router
from app.modules.practice.router import router as practice_router
from app.modules.reading.router import router as reading_router
from app.modules.speaking.router import router as speaking_router
from app.modules.users.router import router as users_router
from app.modules.writing.router import router as writing_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(practice_router)
router.include_router(capabilities_router)
router.include_router(catalog_router)
router.include_router(writing_router)
router.include_router(exercises_router)
router.include_router(jobs_router)
router.include_router(reading_router)
router.include_router(listening_router)
router.include_router(media_router)
router.include_router(speaking_router)
