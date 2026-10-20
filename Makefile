# OpenLUTRA - Makefile
# Simple launcher for use at robot sites

.PHONY: help up dev-up down restart logs ps build stream \
	minio-up minio-down \
	lint lint-backend lint-frontend \
	test test-backend test-frontend \
	test-cov test-cov-backend test-cov-frontend \
	format format-backend format-frontend \
	generate setup clean \
	prod-up prod-down prod-restart prod-logs prod-pull

help:
	@echo "OpenLUTRA"
	@echo ""
	@echo "Docker (development):"
	@echo "  make up         - Start the development environment (with simulator)"
	@echo "  make dev-up     - Start in dev mode (VITE_DEV_MODE=true / show command copy and StatusBar)"
	@echo "  make down       - Stop"
	@echo "  make restart    - Restart (down + up)"
	@echo "  make logs       - Show logs"
	@echo "  make ps         - Show container status"
	@echo "  make build      - Build Docker images"
	@echo "  make stream     - Show the SSE stream (topic monitoring)"
	@echo ""
	@echo "Local S3 (MinIO, for testing the upload feature):"
	@echo "  make minio-up   - Start MinIO + auto-create the bucket"
	@echo "  make minio-down - Stop MinIO"
	@echo ""
	@echo "Dev tools:"
	@echo "  make lint              - Lint (all: backend + frontend)"
	@echo "  make lint-backend      - Lint (ruff + mypy)"
	@echo "  make lint-frontend     - Lint (tsc + biome)"
	@echo "  make test              - Test (all: backend + frontend)"
	@echo "  make test-backend      - Test (pytest)"
	@echo "  make test-frontend     - Test (vitest)"
	@echo "  make test-cov          - Test + coverage (all)"
	@echo "  make test-cov-backend  - Test + coverage (pytest)"
	@echo "  make test-cov-frontend - Test + coverage (vitest)"
	@echo "  make format            - Format (all: backend + frontend)"
	@echo "  make format-backend    - Format (ruff)"
	@echo "  make format-frontend   - Format (biome)"
	@echo "  make generate          - Regenerate API types (exports OpenAPI + runs orval)"
	@echo "  make setup             - Initial setup (install dependencies)"
	@echo "  make clean             - Clear caches"
	@echo ""
	@echo "Production (Linux):"
	@echo "  make prod-pull - Pull code + rebuild + restart"
	@echo "  make prod-up     - Start production (host network)"
	@echo "  make prod-down   - Stop production"
	@echo "  make prod-logs   - Show production logs"

# ===== Docker (development) =====

up:
	@echo "=== Starting development environment ==="
	docker compose --profile sim up -d
	@echo "=== Started ==="
	@echo "  Frontend:  http://localhost:5173"
	@echo "  Backend:   http://localhost:8000"
	@echo "  Simulator: publishing robot dummy data"

dev-up:
	@echo "=== Starting development environment in dev mode (VITE_DEV_MODE=true) ==="
	VITE_DEV_MODE=true docker compose --profile sim up -d
	@echo "=== Started ==="
	@echo "  Frontend:  http://localhost:5173 (dev mode)"
	@echo "  Backend:   http://localhost:8000"
	@echo "  Simulator: publishing robot dummy data"

down:
	docker compose --profile sim down

restart:
	docker compose --profile sim down
	docker compose --profile sim up -d
	@echo "=== Restarted ==="
	@echo "  Frontend:  http://localhost:5173"
	@echo "  Backend:   http://localhost:8000"

# e.g. when SIM_MODE changes
restart-sim:
	docker compose up -d --build simulator
	@echo "=== Simulator restarted (SIM_MODE=$${SIM_MODE:-normal}) ==="

logs:
	docker compose --profile sim logs -f

ps:
	docker compose --profile sim ps

build:
	@echo "=== Building Docker images ==="
	docker compose build

stream:
	@curl -s -N http://localhost:8000/api/topics/stream

# ===== Local S3 (MinIO) =====

minio-up:
	@echo "=== Starting MinIO ==="
	docker compose --profile s3 up -d minio minio-init
	@echo "=== MinIO started ==="
	@echo "  S3 API:  http://localhost:9000"
	@echo "  Console: http://localhost:9001  (user: minioadmin / pass: minioadmin)"
	@echo "  Bucket:  $${S3_BUCKET:-lutra-recordings}"

minio-down:
	docker compose --profile s3 down

# ===== Dev tools =====

# ----- lint -----

lint: lint-backend lint-frontend

lint-backend:
	@echo "=== Lint (ruff) ==="
	cd backend && uv run ruff check app/ tests/
	@echo "=== Type check (mypy) ==="
	cd backend && uv run mypy app/

lint-frontend:
	@echo "=== Type check (tsc) ==="
	cd frontend && pnpm exec tsc --noEmit
	@echo "=== Lint (biome) ==="
	cd frontend && pnpm exec biome check src/

# ----- test -----

test: test-backend test-frontend

# Runs on the host; rclpy is not required.
test-backend:
	@echo "=== Tests: Backend (pytest) ==="
	cd backend && uv run pytest tests/ -v

test-frontend:
	@echo "=== Tests: Frontend (vitest) ==="
	cd frontend && pnpm exec vitest run

# ----- test-cov -----

test-cov: test-cov-backend test-cov-frontend

# Runs on the host; rclpy is not required.
test-cov-backend:
	@echo "=== Tests + Coverage: Backend (pytest) ==="
	cd backend && uv run pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=100

test-cov-frontend:
	@echo "=== Tests + Coverage: Frontend (vitest) ==="
	cd frontend && pnpm exec vitest run --coverage

# ----- format -----

format: format-backend format-frontend

format-backend:
	@echo "=== Format (Python) ==="
	cd backend && uv run ruff format app/ tests/
	cd backend && uv run ruff check --fix app/ tests/

format-frontend:
	@echo "=== Format (Frontend) ==="
	cd frontend && pnpm exec biome check --write src/

# Runs on the host; neither Docker nor a running backend is required.
generate:
	@echo "=== Exporting OpenAPI schema ==="
	cd backend && uv run python -m app.openapi > ../frontend/openapi.json
	@echo "=== Regenerating API types (orval) ==="
	rm -rf frontend/src/api/generated
	cd frontend && pnpm exec orval
	@echo "=== Regeneration complete ==="

setup:
	@echo "=== Installing dependencies ==="
	cd backend && uv sync --extra dev
	cd frontend && pnpm install
	cp -n .env.example .env 2>/dev/null || true
	@echo "=== Setup complete ==="

clean:
	@echo "=== Clearing caches ==="
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/node_modules/.cache 2>/dev/null || true
	@echo "=== Done ==="

# ===== Production (Linux) =====

# Talks to real ROS2 via the host network.
prod-up:
	@echo "=== Starting production environment (host network) ==="
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "=== Started ==="
	@echo "  Backend: http://localhost:8000"

prod-pull:
	@echo "=== git pull + rebuild ==="
	git pull
	docker compose -f docker-compose.yml -f docker-compose.prod.yml build
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "=== Done ==="

prod-restart:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "=== Restarted ==="
	@echo "  Backend: http://localhost:8000"

prod-down:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

prod-logs:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
