import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import router
from app.core.body_limit import BodyLimitMiddleware
from app.core.config import Settings
from app.core.errors import install_error_handlers
from app.core.rate_limit import RateLimiter
from app.core.request_id import RequestIdMiddleware
from app.core.security import PasswordService, TokenService
from app.db import models  # noqa: F401 -- register every table so foreign keys resolve
from app.db.session import Database
from app.modules.auth.delivery import DisabledDelivery, MemoryDelivery, OutboxDelivery
from app.modules.media.storage import MediaStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        database = Database(settings)
        application.state.database = database
        try:
            yield
        finally:
            await database.close()

    expose_docs = settings.app_env != "production"
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_docs else None,
    )
    application.state.settings = settings
    application.state.passwords = PasswordService(settings)
    application.state.tokens = TokenService(settings)
    application.state.rate_limiter = RateLimiter()
    application.state.media_store = MediaStore(settings.media_storage_dir)
    application.state.reset_delivery = {
        "disabled": DisabledDelivery,
        "memory": MemoryDelivery,
        "outbox": lambda: OutboxDelivery(settings.password_reset_outbox_dir),
    }[settings.password_reset_delivery]()
    install_error_handlers(application)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )
    application.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_bytes)
    # Added last so it is outermost: every response, including rejections, gets an ID.
    application.add_middleware(RequestIdMiddleware)
    application.include_router(router)
    return application


app = create_app()
