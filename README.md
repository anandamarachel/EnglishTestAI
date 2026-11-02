# EnglishTestCompro

AI-assisted English practice application. Current development focuses on the backend.

FastAPI application API for the four English practice modules. This initial setup
provides infrastructure only: PostgreSQL, SQLAlchemy, Alembic, environment-based
configuration, health checks, tests, and Docker. Authentication, the 22-table
domain schema, skill endpoints, media storage, background jobs, and the separate
GPU AI service are **not implemented yet**.

## Repository structure

```text
EnglishTestCompro/
├── .gitignore
├── README.md
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

- Python 3.14 and [uv](https://docs.astral.sh/uv/).
- Docker Engine/Desktop running, with Docker Compose.
- Available local ports 5432 and 8000, or override them in `.env` for Docker.

## Local development: database in Docker, API on your machine

From the repository root, enter the backend directory first:

```sh
cd backend
```

Run all commands below from `backend/`:

```sh
uv sync --locked
uv run python scripts/init_env.py
docker compose up -d --wait db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The setup script creates a private `.env` with a random password and preserves
an existing file. The settings reference is `.env.example`. Environment variables
override `.env`. Do not commit `.env` or use its credentials for production.

- Swagger UI: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/api/v1/health/live
- Database readiness: http://127.0.0.1:8000/api/v1/health/ready

`app/main.py` is the single application entry point. Use `app.main:app` in IDE
run configurations, local commands, and Docker. Set your IDE working directory
to `backend/` and select `backend/.venv/bin/python` as its interpreter.
`API_PORT` controls Docker's published port; pass `--port` explicitly for local Uvicorn.
Stop the API with Ctrl+C and stop PostgreSQL with `docker compose stop db`.

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

The `0001` revision intentionally establishes history without business tables.
`alembic upgrade head` creates Alembic's version table. Add the actual domain
schema in reviewed migrations as features are implemented.

1. Define models using `app.db.base.Base`.
2. Import the models in `app/db/models.py` so Alembic sees them.
3. Generate, inspect, and apply the revision:

```sh
uv run alembic revision --autogenerate -m "add users"
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
and exercise downgrade/upgrade. They refuse database names without `_test`.
They are skipped by default and must never point at production data.

Shortcuts: `make setup`, `make db-up`, `make migrate`, `make dev`, `make check`,
`make up`, and `make down`.

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
- No repository remote, cloud deployment, or AI model download is configured.

Implementation references: [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/),
[Alembic cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html), and
[official PostgreSQL image](https://hub.docker.com/_/postgres).
