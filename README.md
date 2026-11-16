# English Day · SMAN 10 Gowa

Monorepo for **English Day**, an AI-assisted English practice mobile app (Writing,
Reading, Listening, Speaking).

```
.
├── backend/    # FastAPI server, PostgreSQL, AI worker (Docker)
├── frontend/   # Flutter mobile app
└── docs/       # Backend design, database schema, API contract, UI designs (docs/design/)
```

## Frontend (Flutter)

Use **Flutter 3.41.x (stable)** so `pubspec.lock` stays the same for everyone
(check with `flutter --version`).

```sh
cd frontend
flutter pub get
flutter run            # or: flutter run -d chrome / -d windows
```

UI details and screen mapping: [frontend/README.md](frontend/README.md).

---

## Backend (FastAPI)

Backend for **English Day**, an AI-assisted English practice app (Writing, Reading,
Listening, Speaking). The Flutter app talks to this FastAPI server.

## Quick start: run the backend

You only need **Docker Desktop** (running) and `make`. No Python setup is required.

```sh
cd backend
make start
```

The first run downloads and builds everything (a few minutes); later starts take
seconds. When it finishes it prints:

```text
Backend is running.
  API base URL      http://localhost:8000/api/v1
  Android emulator  http://10.0.2.2:8000/api/v1
  Swagger UI        http://localhost:8000/docs
```

That's it: the database, the API and the AI worker are all running, with the starter
topics and personas loaded. Your data is kept between runs.

| Command | What it does |
|---|---|
| `make start` | Start everything (also run it after `git pull` to pick up new code). |
| `make stop` | Stop everything. Data is kept. |
| `make restart` | Stop, rebuild with the latest code, start again. |
| `make logs` | Watch the server logs (Ctrl+C stops watching, not the server). |
| `make status` | Show what is running. |
| `make reset-mail` | Show the latest password-reset email (there is no real email in development). |
| `make reset` | **Delete all local data** and start fresh (asks for confirmation). |
| `make` | List all commands. |

### Connecting the Flutter app

- **Android emulator:** use `http://10.0.2.2:8000/api/v1` (the emulator's name for your
  computer).
- **iOS simulator / desktop / web:** use `http://localhost:8000/api/v1`.
- **Real phone on the same Wi-Fi:** in `backend/.env` set `API_BIND=0.0.0.0` and add your
  computer's LAN IP to `ALLOWED_HOSTS` (for example
  `["localhost","127.0.0.1","10.0.2.2","192.168.1.20","testserver"]`), then `make restart`
  and use `http://192.168.1.20:8000/api/v1`. Android blocks plain `http://` by default,
  so allow cleartext traffic in your debug build.

### Things to know while building the app

- **Try every endpoint** in Swagger UI (`/docs`): register, log in, press *Authorize* and
  paste the `access_token`. The full contract is in [docs/api/](docs/api/README.md)
  (OpenAPI file and a Postman collection).
- **AI is a stand-in by default** (see *Using real AI* below). Generated exercises, transcripts, replies and scores are
  predictable placeholders so you can build every screen; they are not real assessment.
  Listening and Speaking audio is a short beep per line followed by silence.
- **AI work is asynchronous.** Creating an exercise or submitting returns a `job`; poll
  `GET /jobs/{job_id}` until it is `succeeded`, then fetch the result.
- **Send an `Idempotency-Key` header** (a new UUID per action) on protected POST requests,
  and reuse the same key when retrying the same action.
- **Speaking recordings must be WAV (PCM)**, up to 10 MB and 2 minutes. Upload them as
  multipart (`audio` file plus a `client_message_key` UUID).
- **Audio** is downloaded from `GET /media/{media_id}/download` with the bearer token
  (byte ranges are supported for seeking).
- **Forgot password:** after requesting a reset, run `make reset-mail` to see the token.
- **Errors** always look like `{code, message, request_id, retryable, details}`.

### Using real AI (9router)

By default the backend uses the development stand-in engine. To use real models through
9router (any OpenAI-compatible gateway works), add to
`backend/.env` and run `make restart`:

```dotenv
AI_PROVIDER=router
ROUTER_BASE_URL=https://9router.lecimangga.my.id/v1   # or http://<LAN-IP>:20128/v1
ROUTER_API_KEY=sk-...
ROUTER_MODEL_GENERATE=gemini/gemini-3.8-flash         # exercises (or a 9router combo name)
ROUTER_MODEL_GRADE=gemini/gemini-3.1-pro-preview      # writing/speaking/short-answer grading
ROUTER_MODEL_CHAT=gemini/gemini-3.5-flash-lite        # Speaking partner replies
ROUTER_MODEL_STT=gemini/gemini-3.5-flash-lite         # transcription (model must accept audio)
AI_REQUEST_TIMEOUT_SECONDS=600
```

- Text, transcription and grading go through 9router; Listening and Speaking voices use
  Microsoft Edge TTS (free, needs internet) and `ffmpeg` (installed in the Docker image).
- Model names are exactly as `GET {ROUTER_BASE_URL}/models` lists them.
- Fluency and Pronunciation stay *not assessed* unless `ROUTER_ASSESS_AUDIO=true`, which sends
  the recordings to the grade model. Keep it off until a human has checked its judgments.
- Results are still validated by each module; when the model returns something unusable the
  engine asks it again, and a job that still fails is reported with a retryable error code
  (`AI_OUTPUT_INVALID`, `AI_TIMEOUT`, `AI_UNAVAILABLE`, `AI_RATE_LIMITED`, `TTS_UNAVAILABLE`, ...).
- The engine lives in `backend/app/ai/router.py`; tests with a mocked gateway are in
  `backend/tests/test_router_engine.py`.

### If something goes wrong

- `Cannot connect to the Docker daemon`: start Docker Desktop and try again.
- `port is already allocated`: another program uses port 8000 or 5432. Change
  `API_PORT` or `POSTGRES_PORT` in `backend/.env`, then `make start`.
- The emulator gets `400 Bad Request`: your `backend/.env` was created before
  `10.0.2.2` was allowed. Add `"10.0.2.2"` to `ALLOWED_HOSTS` and `make restart`.
- Something else: `make logs` shows what the server is doing; `make status` shows
  which part stopped.

---

The rest of this document is for backend development.

## Backend overview

FastAPI backend for the four English practice modules: PostgreSQL, 25 SQLAlchemy domain
models, Alembic migrations, environment-based configuration, health checks, tests and
Docker. Accounts (register, login, token refresh, logout, password change/reset,
profile), topics, personas, capabilities, the dashboard, attempt history, all four
practice flows, private audio storage/download, and the AI job queue with its worker are
implemented. A real AI/STT/TTS provider is **not connected yet**: development uses a
deterministic stand-in.

The database blueprint and API field contract are in
[docs/backend-design.md](docs/backend-design.md). The companion
[database.dbml](docs/database.dbml) describes the 25 domain tables implemented in
migration `0002`. All 42 contract operations are implemented.

The [API contract guide](docs/api/README.md) includes the complete
[OpenAPI specification](docs/api/openapi.json), the generated
[Postman collection](docs/api/english-practice.postman_collection.json), and a local
environment template.

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

## Requirements for backend development

(Only needed to change backend code; running the server needs just Docker, see above.)

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
make seed
make dev
```

`make setup` installs the locked dependencies and creates your local `.env`.
`make db-up` starts PostgreSQL and waits until it is ready. `make migrate`
creates or updates the tables. `make seed` adds the starter topics and AI personas
(safe to re-run). `make dev` starts the API with automatic reload
and keeps that terminal occupied until you stop it with Ctrl+C.

AI work (generating exercises, evaluating answers) runs in a separate worker process.
Start it in a second terminal with `make worker`. Without it, jobs stay `queued`.

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

### Authentication

Login returns a 15-minute bearer access token and a refresh token. Every protected
request checks that the token's session is still active, so logout takes effect
immediately. Refresh rotates the refresh token; an already-used token is rejected.
Passwords are hashed with Argon2id and must be 8–256 characters, with no composition
rules. Errors use `{code, message, request_id, retryable, details}`, and each response
carries an `X-Request-ID` header for matching it to server logs.

`make setup` generates a random `JWT_SECRET` (it also adds one to an existing `.env`
that lacks it). The API refuses to start without a secret of at least 32 characters.
Token lifetimes, password length and Argon2 cost are configurable; see `.env.example`.

Password reset: no email provider is configured yet. In development, reset messages are
written to `backend/var/outbox/` (git-ignored, owner-only files); open the newest file to
get the token. In production, forgot-password returns 503 until a provider is added.

Every request body is capped at `MAX_REQUEST_BYTES` (default 12 MiB) and larger requests
get 413 `CAPACITY_EXCEEDED`.

Auth rate limits are kept in memory per API process. With several Uvicorn workers each
counts separately, so move them to a shared store before scaling out. Behind a reverse
proxy, run Uvicorn with `--proxy-headers` and a trusted `--forwarded-allow-ips` so limits
apply to the real client address rather than the proxy's.

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
| `make seed` | Add/refresh starter topics and personas (repeatable). |
| `make dev` | Start the local API on port 8000 with automatic reload. |
| `make worker` | Run the AI job worker (second terminal). |
| `make check` | Run lint, formatting checks, and tests that do not require a database. |
| `make test-db` | Run the database integration tests (see below). |
| `make contract-check` | Validate the OpenAPI/Postman contract. |
| `make contract-export` | Regenerate Postman after editing OpenAPI. |

Don't run `make dev` while `make start` is running: both use port 8000. Use `make stop`
first (it also stops the database; `make db-up` starts only the database again).

## Run the entire stack in Docker

`make start` (see Quick start) wraps these steps: it creates `.env` if missing, runs
`docker compose --profile full up -d --build --wait`, then seeds the catalog.

The `full` profile builds the API image, waits for PostgreSQL, applies migrations
in a separate one-shot container, and starts the API and the AI worker only if migration
succeeds.
Compose overrides the database host to `db` and its internal port to `5432`.
The Python image runs as a non-root user and does not contain `.env` or dev tools.

`make stop` stops the containers and keeps the database and audio volumes.
`make reset` runs `docker compose --profile full down --volumes`, which **deletes them**.
Changing `POSTGRES_PASSWORD` in `.env` does not change the password of a database
already initialized in that volume; update the database role as well.

### AI provider and jobs

No AI model has been chosen yet. All model calls go through a provider-neutral interface
(`app/ai/`), so a local model on the AI PC or an external API can be added later without
changing the domain code. `AI_PROVIDER` selects the engine:

- `fake` (default outside production): a deterministic stand-in with a few fixed
  correction rules and predictable scores. It lets the Flutter app exercise complete
  flows now. Every result carries a limitation note saying it is illustrative.
- `none` (production default): the worker refuses to start and jobs stay `queued`.
  Production refuses `fake`.

Jobs live in PostgreSQL (`ai_jobs`). The worker claims them with a lease, calls the
engine outside any database transaction, and saves results only if the job is still
running the same execution. Failures retry with backoff up to `JOB_MAX_ATTEMPTS`
(default 3); cancelled or superseded results are discarded. The app keeps serving
existing data while no worker or model is available.

Writing uses an IELTS-style rubric (`writing-ielts-practice-v1`): Task Response,
Coherence and Cohesion, Lexical Resource, and Grammatical Range and Accuracy, each 0–9
in half bands. The overall band uses IELTS rounding. Scores are practice estimates, not
official IELTS results. Edit [rubric.py](backend/app/modules/writing/rubric.py) with a new
version to change it; past results keep the rubric they were scored with.

Reading generates a passage, questions and vocabulary in one job. The model quotes its
evidence and vocabulary as exact text, and the backend computes the offsets, so highlights
never depend on the model counting characters. Multiple-choice answers are graded
instantly; short answers are graded by a job (0, 0.5 or 1 point). The final result is a
percentage, plus a correct count when every question is multiple choice.

Listening generates a dialogue script and questions, renders the audio with TTS, checks
the audio bytes (PCM WAV for now) and stores them privately in `var/media`; the exercise
is ready only together with its audio. The transcript is hidden until the whole quiz is
submitted. Submitting locks every answer at once: multiple choice is graded on the spot,
and short answers get grading jobs plus one coordinator job that combines the grades.
Audio is downloaded through the API only (owner check, single byte ranges for seeking)
and replay never reruns TTS. In development the stand-in TTS produces a short beep per
line followed by silence, so playback and seeking can be tested. The API and worker must
share the media directory (Docker uses the `media_data` volume); the worker removes
unreferenced files after a one-hour grace period.

Speaking is a recorded conversation with a persona. Starting an attempt queues the
persona's greeting; each turn uploads a recording (PCM WAV for now, checked from its
bytes) and one job runs speech-to-text, the persona's reply and its audio. Only one
reply is prepared at a time, failed turns stay in history but are never used as model
context, and an exact retry never creates a second turn. Finishing queues IELTS-style
feedback (`speaking-ielts-practice-v1`). Fluency and Pronunciation need an audio
assessor, so until one is connected they are reported as not assessed and no overall
band is given; they are never guessed from the transcript.

Protected POST requests need an `Idempotency-Key` header (a new UUID per action, reused
when retrying the same action). Keep model inference and GPU dependencies out of this
image; they belong to the separate AI service.

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
make test-db
```

Create that test database once; `createdb` reports an error if it already exists.
Integration tests apply migrations, check schema drift, test real readiness,
and exercise downgrade/upgrade. They also test all four skills, long Writing
drafts, submission locks, cross-user/cross-exercise references, text spans,
audio ownership, job cancellation, and concurrent voice-job acceptance.
They refuse database names without `_test`.
They are skipped by default and must never point at production data.

## Configuration and deployment boundaries

- Local Compose binds PostgreSQL and the API to `127.0.0.1` only (the API can be opened
  to the LAN with `API_BIND=0.0.0.0` for phone testing).
- `ALLOWED_HOSTS` and `CORS_ORIGINS` are JSON arrays. Add the actual API hostname
  when deploying. Native Android does not need CORS enabled.
- `APP_ENV=production` disables interactive docs and the OpenAPI endpoint.
- Health endpoints intentionally expose only status; readiness checks connectivity,
  not migration state or AI availability. Verify migrations during deployment.
- This is a development Compose configuration. Its bootstrap database user is a
  PostgreSQL superuser. Before VPS deployment, use separate migration and restricted
  application roles, private database networking, HTTPS at a reverse proxy,
  server-managed secrets, tested backups, and resource limits.
- Authentication, owner-only access to every resource, upload validation and
  per-process auth rate limits are implemented. Shared rate limiting (including
  generation/uploads) and AI service authentication still need implementation before
  exposing the API publicly.
- Password recovery email delivery is not configured yet (production returns 503).
- No cloud deployment or AI model download is configured.

Implementation references: [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/),
[Alembic cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html), and
[official PostgreSQL image](https://hub.docker.com/_/postgres).
