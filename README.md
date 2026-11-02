# EnglishTestCompro

AI-assisted English practice application. Current development focuses on the backend.

```text
EnglishTestCompro/
├── .gitignore           Shared ignore rules
├── README.md
└── backend/
    ├── app/             FastAPI application; entry point: app/main.py
    ├── alembic/         Database migrations
    ├── tests/
    ├── scripts/
    ├── .env.example
    ├── Dockerfile
    ├── compose.yaml
    ├── Makefile
    ├── alembic.ini
    ├── pyproject.toml
    ├── uv.lock
    └── README.md        Backend setup and development instructions
```

Start from the backend directory:

```sh
cd backend
make setup
make db-up
make migrate
make dev
```

See [backend/README.md](backend/README.md) for prerequisites, Docker commands,
migrations, tests, and configuration. Local secrets live in `backend/.env` and
are excluded from Git. Set your IDE interpreter to `backend/.venv/bin/python`
and its working directory to `backend/`.
