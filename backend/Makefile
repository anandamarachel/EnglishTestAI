.PHONY: setup db-up db-down migrate dev check test test-db contract-export contract-check up down

setup:
	uv sync --locked
	uv run python scripts/init_env.py

db-up:
	docker compose up -d --wait db

db-down:
	docker compose stop db

migrate:
	uv run alembic upgrade head

dev:
	uv run uvicorn app.main:app --reload --host 127.0.0.1

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -m "not integration"

test:
	uv run pytest -m "not integration"

test-db:
	RUN_DB_TESTS=1 uv run pytest -m integration

contract-export:
	uv run python scripts/export_postman.py

contract-check:
	uv run pytest tests/test_api_contract.py

up:
	docker compose --profile full up -d --build --wait

down:
	docker compose --profile full down
