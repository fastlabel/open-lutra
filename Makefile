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

# Default: show help
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
	@echo "  make generate          - Regenerate API types (requires: backend running)"
	@echo "  make setup             - Initial setup (install dependencies)"
	@echo "  make clean             - Clear caches"
	@echo ""
	@echo "Production (Linux):"
	@echo "  make prod-pull - Pull code + rebuild + restart"
	@echo "  make prod-up     - Start production (host network)"
	@echo "  make prod-down   - Stop production"
	@echo "  make prod-logs   - Show production logs"

# ===== Docker (development) =====

# Start the development environment (with simulator)
up:
	@echo "=== Starting development environment ==="
	docker compose --profile sim up -d
	@echo "=== Started ==="
	@echo "  Frontend:  http://localhost:5173"
	@echo "  Backend:   http://localhost:8000"
	@echo "  Simulator: publishing robot dummy data"

# Start in dev mode (VITE_DEV_MODE=true: shows developer UI like command copy and StatusBar)
dev-up:
	@echo "=== Starting development environment in dev mode (VITE_DEV_MODE=true) ==="
	VITE_DEV_MODE=true docker compose --profile sim up -d
	@echo "=== Started ==="
	@echo "  Frontend:  http://localhost:5173 (dev mode)"
	@echo "  Backend:   http://localhost:8000"
	@echo "  Simulator: publishing robot dummy data"

# Stop
down:
	docker compose --profile sim down

# Restart
restart:
	docker compose --profile sim down
	docker compose --profile sim up -d
	@echo "=== Restarted ==="
	@echo "  Frontend:  http://localhost:5173"
	@echo "  Backend:   http://localhost:8000"

# Restart only the simulator (e.g. when SIM_MODE changes)
restart-sim:
	docker compose up -d --build simulator
	@echo "=== Simulator restarted (SIM_MODE=$${SIM_MODE:-normal}) ==="

# Show logs
logs:
	docker compose --profile sim logs -f

# Show container status
ps:
	docker compose --profile sim ps

# Build Docker images
build:
	@echo "=== Building Docker images ==="
	docker compose build

# Show the SSE stream (topic monitoring)
stream:
	@curl -s -N http://localhost:8000/api/topics/stream

# ===== Local S3 (MinIO) =====

# Start MinIO and auto-create the bucket
minio-up:
	@echo "=== Starting MinIO ==="
	docker compose --profile s3 up -d minio minio-init
	@echo "=== MinIO started ==="
	@echo "  S3 API:  http://localhost:9000"
	@echo "  Console: http://localhost:9001  (user: minioadmin / pass: minioadmin)"
	@echo "  Bucket:  $${S3_BUCKET:-lutra-recordings}"

# Stop MinIO
minio-down:
	docker compose --profile s3 down

# ===== Dev tools =====

# ----- lint -----

# Lint (all)
lint: lint-backend lint-frontend

# Lint (backend: ruff + mypy)
lint-backend:
	@echo "=== Lint (ruff) ==="
	cd backend && uv run ruff check app/ tests/
	@echo "=== Type check (mypy) ==="
	cd backend && uv run mypy app/

# Lint (frontend: tsc + biome)
lint-frontend:
	@echo "=== Type check (tsc) ==="
	cd frontend && pnpm exec tsc --noEmit
	@echo "=== Lint (biome) ==="
	cd frontend && pnpm exec biome check src/

# ----- test -----

# Test (all)
test: test-backend test-frontend

# Test (backend: runs on the host; rclpy is not required)
test-backend:
	@echo "=== Tests: Backend (pytest) ==="
	cd backend && uv run pytest tests/ -v

# Test (frontend)
test-frontend:
	@echo "=== Tests: Frontend (vitest) ==="
	cd frontend && pnpm exec vitest run

# ----- test-cov -----

# Test + coverage (all)
test-cov: test-cov-backend test-cov-frontend

# Test + coverage (backend: runs on the host; rclpy is not required)
test-cov-backend:
	@echo "=== Tests + Coverage: Backend (pytest) ==="
	cd backend && uv run pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=100

# Test + coverage (frontend)
test-cov-frontend:
	@echo "=== Tests + Coverage: Frontend (vitest) ==="
	cd frontend && pnpm exec vitest run --coverage

# ----- format -----

# Format (all)
format: format-backend format-frontend

# Format (backend: ruff)
format-backend:
	@echo "=== Format (Python) ==="
	cd backend && uv run ruff format app/ tests/
	cd backend && uv run ruff check --fix app/ tests/

# Format (frontend: biome)
format-frontend:
	@echo "=== Format (Frontend) ==="
	cd frontend && pnpm exec biome check --write src/

# Regenerate API types (run while the backend is up)
generate:
	@echo "=== Regenerating API types (orval) ==="
	rm -rf frontend/src/api/generated
	cd frontend && pnpm exec orval
	@echo "=== Regeneration complete ==="

# Initial setup
setup:
	@echo "=== Installing dependencies ==="
	cd backend && uv sync --extra dev
	cd frontend && pnpm install
	cp -n .env.example .env 2>/dev/null || true
	@echo "=== Setup complete ==="

# Clear caches
clean:
	@echo "=== Clearing caches ==="
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/node_modules/.cache 2>/dev/null || true
	@echo "=== Done ==="

# ===== Production (Linux) =====

# Start production (talks to real ROS2 via host network)
prod-up:
	@echo "=== Starting production environment (host network) ==="
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "=== Started ==="
	@echo "  Backend: http://localhost:8000"

# Pull code + rebuild + restart
prod-pull:
	@echo "=== git pull + rebuild ==="
	git pull
	docker compose -f docker-compose.yml -f docker-compose.prod.yml build
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "=== Done ==="

# Restart production
prod-restart:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "=== Restarted ==="
	@echo "  Backend: http://localhost:8000"

# Stop production
prod-down:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# Show production logs
prod-logs:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
