# EnglishTestCompro

AI-assisted English practice application. Current development focuses on the backend.

FastAPI backend for the four English practice modules. The foundation includes
PostgreSQL, 25 SQLAlchemy domain models, Alembic migrations, environment-based
configuration, health checks, tests, and Docker. Authentication endpoints, skill
endpoints, media storage, job workers, and the separate GPU AI service are
**not implemented yet**.

The revised database blueprint and API field contract are in
[docs/backend-design.md](docs/backend-design.md). The companion
[database.dbml](docs/database.dbml) describes the 25 domain tables implemented in
migration `0002`. The API field contract remains a design document; currently only
health endpoints are available.

The [API contract guide](docs/api/README.md) includes the complete
[OpenAPI specification](docs/api/openapi.json), generated
[Postman collection](docs/api/english-practice.postman_collection.json), and a local
environment template. All business endpoints are explicitly marked as planned.

## Repository structure

```text
EnglishTestCompro/
├── .gitignore
├── README.md
├── docs/                 Database blueprint and API field contract
└── backend/
    ├── app/
    │   ├── main.py          Application factory and entry point
    │   ├── api/             Versioned routes and health checks
    │   ├── core/            Configuration
    │   ├── db/              Models and database sessions
    │   └── modules/         Business modules
    ├── alembic/             Database migrations
    ├── tests/
    ├── scripts/init_env.py  Local environment setup
    ├── .env.example
    ├── Dockerfile
    ├── compose.yaml
    ├── Makefile
    ├── alembic.ini
    ├── pyproject.toml
    └── uv.lock
```

## Requirements

- Git to clone and update the repository, plus `make`.
- Python 3.14 and [uv](https://docs.astral.sh/uv/).
- Docker Engine/Desktop running, with Docker Compose.
- Available local ports 5432 and 8000, or override them in `.env` for Docker.

The commands below assume macOS, Linux, or a Windows WSL terminal with Docker
available. `make` runs the commands defined in `backend/Makefile`; the other
tools must be installed first.

## Local development: database in Docker, API on your machine

Clone the shared repository, then run this first-time setup from its root:

```sh
cd backend
make setup
make db-up
make migrate
make dev
```

`make setup` installs the locked dependencies and creates your local `.env`.
`make db-up` starts PostgreSQL and waits until it is ready. `make migrate`
creates or updates the tables. `make dev` starts the API with automatic reload
and keeps that terminal occupied until you stop it with Ctrl+C.

On later runs, use these commands from `backend/`:

```sh
make db-up
make dev
```

After pulling team changes, stop the API and run:

```sh
git pull
make setup
make db-up
make migrate
make dev
```

The setup script creates a private `.env` with a random password and preserves
an existing file. The settings reference is `.env.example`. Environment variables
override `.env`. Do not commit `.env` or use its credentials for production.
Each teammate generates their own `.env`; sharing another developer's file is
unnecessary. Each machine also has its own local PostgreSQL database.

- Swagger UI: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/api/v1/health/live
- Database readiness: http://127.0.0.1:8000/api/v1/health/ready

Readiness returns `{"status":"ok"}` when the API can connect to PostgreSQL.
Swagger UI currently shows health endpoints only. The planned practice and
account endpoints can be reviewed in the [API contract guide](docs/api/README.md).

`app/main.py` is the single application entry point. Use `app.main:app` in IDE
run configurations, local commands, and Docker. Set your IDE working directory
to `backend/` and select `backend/.venv/bin/python` as its interpreter.
`API_PORT` controls Docker's published port; pass `--port` explicitly for local Uvicorn.
Stop the API with Ctrl+C and stop PostgreSQL with `make db-down`.

Useful commands, all run from `backend/`:

| Command | Purpose |
|---|---|
| `make setup` | Install/update dependencies and create `.env` if missing. |
| `make db-up` / `make db-down` | Start/stop local PostgreSQL; stopping retains data. |
| `make migrate` | Apply pending database migrations. |
| `make dev` | Start the local API on port 8000 with automatic reload. |
| `make check` | Run lint, formatting checks, and tests that do not require a database. |
| `make contract-check` | Validate the OpenAPI/Postman contract. |
| `make contract-export` | Regenerate Postman after editing OpenAPI. |
| `make up` / `make down` | Start/stop the complete Docker stack. |

## Run the entire stack in Docker

After creating `.env`, run:

```sh
docker compose --profile full up -d --build --wait
docker compose --profile full ps -a
docker compose logs -f api
```

The `full` profile builds the API image, waits for PostgreSQL, applies migrations
in a separate one-shot container, and starts the API only if migration succeeds.
Compose overrides the database host to `db` and its internal port to `5432`.
The Python image runs as a non-root user and does not contain `.env` or dev tools.

```sh
docker compose --profile full down
```

This keeps the database volume. **Adding `--volumes` deletes the database.**
Changing `POSTGRES_PASSWORD` in `.env` does not change the password of a database
already initialized in that volume; update the database role as well.

Keep model inference and GPU dependencies in the separate AI service. The VPS
API will eventually call that service through authenticated requests. It should
remain able to serve existing data while the AI PC is offline.

## Migrations

The `0001` revision establishes the infrastructure baseline. Revision `0002` adds
the 25 domain tables, indexes, foreign keys, checks, and PostgreSQL integrity
triggers. `alembic upgrade head` applies both revisions to an empty database or
upgrades an existing baseline database.

Models live in `app/modules/<feature>/models.py`; `app/db/models.py` imports them
for Alembic. The SQL in `alembic/sql/0002_integrity.sql` belongs to revision `0002`:
keep that file with the migration and use a new revision for future changes.
Cross-table checks run at transaction commit, allowing an exercise/attempt and
its required detail rows to be created together. Services should use PostgreSQL's
default `READ COMMITTED` isolation and handle integrity errors at commit as well
as flush. Exercise-level locks serialize related writes; this favors correctness
for the initial workload and needs load testing before scaling.

For future schema changes:

1. Define models using `app.db.base.Base`.
2. Import the models in `app/db/models.py` so Alembic sees them.
3. Generate, inspect, and apply the revision:

```sh
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

Review generated migrations: Alembic does not infer every constraint or data
transformation. Give check constraints explicit names. Use `uv run alembic
downgrade -1` only after reviewing its data-loss implications. Never use startup
`create_all()` as a substitute for migrations. Services commit successful writes
explicitly; uncommitted work is rolled back when the request session closes.

## Checks and tests

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -m "not integration"
```

For integration tests, first create a separate disposable database:

```sh
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" english_practice_test'
POSTGRES_DB=english_practice_test RUN_DB_TESTS=1 uv run pytest -m integration
```

Create that test database once; `createdb` reports an error if it already exists.
Integration tests apply migrations, check schema drift, test real readiness,
and exercise downgrade/upgrade. They also test all four skills, long Writing
drafts, submission locks, cross-user/cross-exercise references, text spans,
audio ownership, job cancellation, and concurrent voice-job acceptance.
They refuse database names without `_test`.
They are skipped by default and must never point at production data.

Shortcuts: `make setup`, `make db-up`, `make migrate`, `make dev`, `make check`,
`make contract-export`, `make contract-check`, `make up`, and `make down`.

## Configuration and deployment boundaries

- Local Compose binds PostgreSQL and the API to `127.0.0.1` only.
- `ALLOWED_HOSTS` and `CORS_ORIGINS` are JSON arrays. Add the actual API hostname
  when deploying. Native Android does not need CORS enabled.
- `APP_ENV=production` disables interactive docs and the OpenAPI endpoint.
- Health endpoints intentionally expose only status; readiness checks connectivity,
  not migration state or AI availability. Verify migrations during deployment.
- This is a development Compose configuration. Its bootstrap database user is a
  PostgreSQL superuser. Before VPS deployment, use separate migration and restricted
  application roles, private database networking, HTTPS at a reverse proxy,
  server-managed secrets, tested backups, and resource limits.
- Authentication, authorization, rate limits, upload controls, and AI service
  authentication still need implementation before exposing business endpoints.
- No cloud deployment or AI model download is configured.

Implementation references: [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/),
[Alembic cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html), and
[official PostgreSQL image](https://hub.docker.com/_/postgres).
