# Feature modules

The domain models are grouped into `users`, `auth`, `catalog`, `media`,
`exercises`, `practice`, `writing`, `reading`, `listening`, `speaking`, `quiz`,
`assessment`, and `jobs`. These packages currently contain persistence models.
Add `router.py`, `schemas.py`, and `service.py` as each feature is implemented.
History will query existing attempts and results; it needs no separate history table.

Register routers in `app/api/router.py` and model imports in `app/db/models.py`.
Use the shared `Base`, request-scoped session dependency, and configuration.
Services own transactions; migrations own schema changes. Do not call
`Base.metadata.create_all()` on application startup.

Create each exercise/attempt and its matching detail in the same transaction.
Deferred database checks validate the complete state at commit. Models expose
foreign-key columns; query related records explicitly in services. Response
schemas must be defined separately so password/token hashes, answer keys, and
private transcripts are not accidentally returned to clients.

The local AI model service is a separate deployment. Its models and GPU
dependencies do not belong in this VPS application image.
