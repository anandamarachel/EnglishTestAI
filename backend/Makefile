.DEFAULT_GOAL := help
.PHONY: help start stop restart logs status reset-mail reset env \
	setup db-up db-down migrate seed dev worker check test test-db \
	contract-export contract-check up down

COMPOSE := docker compose --profile full
API_URL := http://localhost:$(or $(shell grep -E '^API_PORT=' .env 2>/dev/null | cut -d= -f2),8000)

# ---------------------------------------------------------------------------------------
# Run the backend (frontend developers): needs only Docker and make.
# ---------------------------------------------------------------------------------------

help: ## Show these commands
	@echo "Run the backend (needs only Docker):"
	@grep -hE '^(start|stop|restart|logs|status|reset-mail|reset):.*## ' $(MAKEFILE_LIST) \
		| awk -F':.*## ' '{printf "  make %-12s %s\n", $$1, $$2}'
	@echo ""
	@echo "Backend development (needs Python 3.14 + uv):"
	@grep -hE '^(setup|db-up|db-down|migrate|seed|dev|worker|check|test-db|contract-export):.*## ' $(MAKEFILE_LIST) \
		| awk -F':.*## ' '{printf "  make %-16s %s\n", $$1, $$2}'

env:
	@if [ ! -f .env ]; then \
		if command -v python3 >/dev/null 2>&1; then python3 scripts/init_env.py; \
		else docker run --rm --user "$$(id -u):$$(id -g)" -v "$(CURDIR)":/work -w /work \
			python:3.14-slim python scripts/init_env.py; fi; \
	fi

start: env ## Build and start everything (database, API, AI worker), then add starter data
	@echo "Starting the backend (the first run downloads and builds images; a few minutes)..."
	@$(COMPOSE) up -d --build --wait
	@$(COMPOSE) run --rm --no-deps migrate python -m app.modules.catalog.seed
	@echo ""
	@echo "Backend is running."
	@echo "  API base URL      $(API_URL)/api/v1"
	@echo "  Android emulator  http://10.0.2.2:$(subst http://localhost:,,$(API_URL))/api/v1"
	@echo "  Swagger UI        $(API_URL)/docs"
	@echo "Stop it with: make stop"

stop: ## Stop everything (your data is kept)
	@$(COMPOSE) stop

restart: stop start ## Stop, rebuild with the latest code, and start again

logs: ## Follow the API and worker logs (Ctrl+C to stop following)
	@$(COMPOSE) logs -f --tail=100 api worker

status: ## Show which containers are running
	@$(COMPOSE) ps -a

reset-mail: ## Print the newest password-reset email (development has no real email)
	@$(COMPOSE) exec -T api sh -c 'f=$$(ls -t /app/var/outbox 2>/dev/null | head -1); \
		if [ -n "$$f" ]; then cat "/app/var/outbox/$$f"; else echo "No reset emails yet."; fi'

reset: ## DELETE all local data (accounts, exercises, audio) and start fresh
	@printf "This deletes every local account, exercise and recording. Type 'yes' to continue: "; \
		read answer; [ "$$answer" = "yes" ] || { echo "Cancelled."; exit 1; }
	@$(COMPOSE) down --volumes
	@$(MAKE) --no-print-directory start

# ---------------------------------------------------------------------------------------
# Backend development: API on your machine with reload, database in Docker.
# ---------------------------------------------------------------------------------------

setup: ## Install dependencies and create .env
	uv sync --locked
	uv run python scripts/init_env.py

db-up: ## Start only PostgreSQL
	docker compose up -d --wait db

db-down: ## Stop PostgreSQL (data kept)
	docker compose stop db

migrate: ## Apply database migrations
	uv run alembic upgrade head

seed: ## Add/refresh starter topics and personas
	uv run python -m app.modules.catalog.seed

dev: ## Run the API locally with auto-reload
	uv run uvicorn app.main:app --reload --host 127.0.0.1

worker: ## Run the AI job worker locally (second terminal)
	uv run python -m app.worker

check: ## Lint, format check and unit tests
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -m "not integration"

test:
	uv run pytest -m "not integration"

test-db: ## Database integration tests (needs the _test database)
	POSTGRES_DB=english_practice_test RUN_DB_TESTS=1 uv run pytest -m integration

contract-export: ## Regenerate Postman from OpenAPI
	uv run python scripts/export_postman.py

contract-check:
	uv run pytest tests/test_api_contract.py

up:
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down
