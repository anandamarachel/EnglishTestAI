# Feature modules

Add `auth`, `users`, `writing`, `reading`, `listening`, `speaking`, `history`,
`media`, and `ai_jobs` here as their features are implemented. Each module can
own its `router.py`, `schemas.py`, `service.py`, and `models.py` as needed.

Register routers in `app/api/router.py` and model imports in `app/db/models.py`.
Use the shared `Base`, request-scoped session dependency, and configuration.
Services own transactions; migrations own schema changes. Do not call
`Base.metadata.create_all()` on application startup.

The local AI model service is a separate deployment. Its models and GPU
dependencies do not belong in this VPS application image.
