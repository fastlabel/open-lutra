# Development Guide

> Summarizes information needed for development, such as testing policies and tool configurations.
> [Coding Style](CODING_STYLE.md) / [Branching Rules](CONTRIBUTING.md)

## Table of Contents

- [Choosing a Development Environment](#choosing-a-development-environment)
- [Developing with Dev Container](#developing-with-dev-container)
- [Tech Stack](TECH_STACK.md)
- [Directory Structure](STRUCTURE.md)
- [Testing](#testing)
- [Lint and Type Checking](#lint-and-type-checking)
- [Frontend Development Notes](#frontend-development-notes)
- [Common Development Tasks](#common-development-tasks)

---

## Choosing a Development Environment

This project supports two development approaches.

| Approach | Backend Editing | Frontend Editing | rclpy Completion | Use Case |
|------|:---:|:---:|:---:|------|
| **Host + `make up`** | o (hot reload) | o (Vite HMR) | x | Full-stack development |
| **Dev Container** | o (directly inside the container) | x (requires separate startup) | o | Backend-focused development |

**Dev Container is recommended when editing rclpy-dependent code** (`backend/app/infra/ros2/topic_node.py`, `thread.py`): rclpy type completion and go-to-definition work there. Backend tests, lint, and type checks run on the host in either approach (see [Testing](#testing)).

---

## Developing with Dev Container

### Prerequisites

- VS Code + [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- Docker Desktop must be running

### Startup Procedure

1. Open this project in VS Code
2. Open the command palette (`Cmd+Shift+P`) → select **Dev Containers: Reopen in Container**
3. On first run, the image is built and dependencies are installed
4. Once finished, VS Code reopens inside the container with the terminal pointing to `/app`

### Differences From the Traditional Workflow

**Host development (`make up`):**

```
Host PC (macOS)
  └── VS Code (edits files on the host)
  └── Docker Compose
       ├── backend container (uvicorn hot reload)
       ├── frontend container (Vite HMR)
       └── simulator container
```

- The editor runs on the host. Files are reflected into the container via a mount
- rclpy is not present on the host, so completion does not work

**Dev Container:**

```
Host PC (macOS)
  └── VS Code (Remote) ───connect──→ VS Code Server inside the backend container
                                    ├── Python extension (rclpy completion available)
                                    ├── Pylance (type checking)
                                    ├── Claude Code (shared conversation history)
                                    └── /app (source code)
```

- The editor itself runs inside the container, so ROS2 packages such as rclpy can be referenced directly
- Saved files are reflected inside the container immediately (not via a mount)

### Starting the Backend

Inside the Dev Container, the backend does not start automatically (it waits with `sleep infinity`). Start it manually from a terminal:

```bash
source /opt/ros/humble/setup.bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/app
```

You can check the API docs in a browser at `http://localhost:8000/docs`.

### Running Tests

Run pytest directly inside the container:

```bash
source /opt/ros/humble/setup.bash
uv run pytest tests/ -v
```

Unlike `make test`, you do not have to wait for the container to be built.

### Frontend Development

Because the Dev Container runs inside the backend container, frontend development requires an extra step:

```bash
# In a separate terminal on the host
cd frontend
pnpm install
pnpm run dev
```

Alternatively, start the frontend container separately via docker compose:

```bash
# In a separate terminal on the host
docker compose --profile frontend-dev up frontend
```

### Configuration Files

```
.devcontainer/
├── devcontainer.json              # Dev Container settings (extensions, settings, mounts)
├── docker-compose.devcontainer.yml # docker-compose override (command, volumes)
├── docker-compose.claude.yml      # Auto-generated (gitignored, mounts Claude history)
└── init-claude.sh                 # Script that dynamically generates the Claude history mount
```

### Troubleshooting

**The container does not start:**

```bash
make down
docker volume ls | grep devcontainer-venv | awk '{print $2}' | xargs -r docker volume rm
# Then run "Dev Containers: Rebuild Container"
```

**You added or updated a Python package:**

```bash
source /opt/ros/humble/setup.bash
uv sync
```

If you changed `pyproject.toml`, running `uv sync` inside the container is enough. No rebuild is required.

---

## Tech Stack

→ See [TECH_STACK.md](TECH_STACK.md).

---

## Project Structure

→ See [STRUCTURE.md](STRUCTURE.md).

---

## Testing

### Running Tests

```bash
make test              # Everything (backend + frontend)
make test-backend      # Backend only (pytest)
make test-frontend     # Frontend only (vitest)
make test-cov          # Everything + coverage
make test-cov-backend  # Backend + coverage
make test-cov-frontend # Frontend + coverage
```

Backend tests run on the host with `uv` alone — neither Docker nor rclpy is required. `app.main` imports the rclpy-dependent modules inside the lifespan, so `create_app()` (and therefore every router) is importable without ROS 2. `tests/conftest.py` defaults the `RECORDING_CONFIG` / `OUTPUT_DIR` variables that `Settings` requires, so plain `uv run pytest` and IDE test runners work without a `.env`. The same suite also runs inside the Dev Container.

### Test Layout

→ See "Testing" in [STRUCTURE.md](STRUCTURE.md).

### Testing Policy

**Backend:**

Maintain 100% coverage. For code that cannot be tested, exclude it from coverage measurement instead of writing tests.

**Three levels of coverage exclusion:**

| Level | Mechanism | Targets |
|---|---|---|
| Per file | `[tool.coverage.run] omit` in `pyproject.toml` | rclpy runtime (`topic_node.py`, `thread.py`), Docker-only code (`memory_reader.py`), entry points (`main.py`) |
| Patterns | `[tool.coverage.report] exclude_also` | `if TYPE_CHECKING:`, `if __name__ == "__main__":`, `...` (Protocol abstract methods) |
| Per line | `# pragma: no cover` | router.py endpoint functions, unreachable defensive code |

**router.py testing policy:**

- Endpoint functions are HTTP glue code, so mark them with `# pragma: no cover` and do not write unit tests for them
- Extract pure logic from routers into separate modules and test those (e.g., `scanner.py`)
- Endpoint wiring (status codes, exception handlers) is covered by `TestClient` tests against `create_app()` with mocked services (`test_router.py`, `test_exception_handlers.py`)

**Rules for writing tests:**

- Mocks must not depend on filesystem permissions (`chmod(0o000)` does not work as root inside Docker, so use `unittest.mock.patch`)
- conftest.py hierarchy: feature-specific fixtures live in the feature's `conftest.py`; shared fixtures live in `backend/tests/conftest.py`
- Test class naming: create one class per function/method/property under test (e.g., `TestActualHz`, `TestStart`)

**Frontend:**

- **Unit tests**: Verify pure functions, hooks, and non-trivial logic with Vitest + jsdom
- **API mocks**: MSW v2 (uses handlers auto-generated by orval)
- **Zustand stores**: Reset automatically between tests (`__mocks__/zustand.ts`)
- **TanStack Query**: A fresh QueryClient per test (retry: false, gcTime: Infinity)

**Zustand store testing policy (important):**

Most store actions are pass-through `set({ x })` calls, so writing unit tests for them effectively tests Zustand itself, which has little value. Therefore:

- **As a rule, do not write tests** — pass-through setters (`setFoo`, `toggleFoo` that just add/remove from a Set, etc.) are covered by component integration tests
- **Exceptions where unit tests are warranted**: stores with complex logic that is hard to reproduce in integration tests, such as state machines for countdowns, buffer-management algorithms, or timestamp calculations. Current exceptions: `features/recording/store.ts` (countdown + mutation orchestration), `stores/quality-history-store.ts` (MAX_BUFFER management)
- **Exclude from coverage measurement** — do not add to `coverage.include` in `vitest.config.ts`. Forcing 100% coverage leads to a pile of trivial tests
- **When adding a new store** — first ask "is this logic covered by integration tests?" YES → no tests needed; NO → write unit tests and add to `coverage.include`

### Running Frontend Tests

```bash
make test-frontend     # Via the Makefile
make test-cov-frontend # Via the Makefile (with coverage)

# Running the package scripts directly
cd frontend
pnpm test              # Run tests
pnpm run test:watch    # Watch mode
pnpm run test:coverage # Run with coverage
```

### Coverage

Coverage is measured with the v8 provider. After running `pnpm run test:coverage`, the HTML report is generated under `frontend/coverage/`.

```bash
# Open the coverage report in a browser
open frontend/coverage/index.html
```

**Coverage targets:**

| Directory | Files Included | Threshold |
|---|---|---|
| `src/lib/**` | Pure functions (format.ts, topic-sort.ts, etc.) | statements/branches/functions: 100% |
| `src/features/**/mutations.ts` | Mutation orchestration (side effects + branching) | - |
| `src/features/**/quality-utils.tsx` | Pure quality-decision utilities | - |
| `src/features/recording/store.ts` | Countdown state machine (a store, included as an exception) | - |
| `src/stores/quality-history-store.ts` | Buffer-management algorithm (a store, included as an exception) | - |

**Not covered:**
- Generated code (`src/api/generated/`), UI utilities (`src/lib/utils.ts`), QueryClient instance (`src/lib/query-client.ts`), components (TSX)
- **Stores in general** (since most setters are pass-through; see the "Zustand store testing policy" above)

**Manage coverage include as MIN** — do not lower the apparent percentage by including trivial code. Explicitly add only the files worth measuring.

> `frontend/coverage/` is included in `.gitignore`, so it is not committed to the repository.

---

## Lint and Type Checking

### Commands

```bash
make lint              # Everything (backend + frontend)
make lint-backend      # Backend only (ruff + mypy)
make lint-frontend     # Frontend only (tsc + biome)
```

**Backend (`make lint-backend`):**

1. `cd backend && uv run ruff check app/ tests/` - Python lint
2. `cd backend && uv run mypy app/` - Python type checking

**Frontend (`make lint-frontend`):**

1. `cd frontend && pnpm exec tsc --noEmit` - TypeScript type checking
2. `cd frontend && pnpm exec biome check src/` - TypeScript lint + format check

### Formatting

```bash
make format            # Everything (backend + frontend)
make format-backend    # Backend only (ruff)
make format-frontend   # Frontend only (biome)
```

**Backend (`make format-backend`):**

1. `cd backend && uv run ruff format app/ tests/` - Python formatting
2. `cd backend && uv run ruff check --fix app/ tests/` - Python auto-fix

**Frontend (`make format-frontend`):**

1. `cd frontend && pnpm exec biome check --write src/` - TypeScript lint auto-fix + formatting

### ruff Configuration (pyproject.toml)

Enabled rules: `E`, `W`, `F`, `I`, `B`, `C4`, `UP`, `ARG`, `SIM`, `TCH`, `PTH`, `RUF`

### mypy Configuration

Strict mode. The rclpy and rosidl modules lack type stubs and are therefore ignored:

```toml
[[tool.mypy.overrides]]
module = ["rclpy.*", "rosidl_runtime_py.*"]
ignore_missing_imports = true
```

---

## Frontend Development Notes

### react-resizable-panels v4

- Component names: `Group`, `Panel`, `Separator` (not v3's `PanelGroup`/`PanelResizeHandle`)
- Props: `orientation` (not v3's `direction`); no `order` prop
- **Size specifications**: `defaultSize`, `minSize`, and `maxSize` must be specified as **strings with `%`**
  - `defaultSize="20%"` (correct)
  - `defaultSize={20}` (interpreted as pixels, incorrect)

### Tailwind v4

- Data attributes: `data-resize-handle-active:bg-ring` (not v3's `data-[resize-handle-active]:bg-ring`)
- `@import "tailwindcss"` (not v3's `@tailwind base`, etc.)

### Choosing State Management

| Kind | Tool | Examples |
|------|--------|-----|
| Server state | TanStack Query | Recording status, file list |
| Real-time data | SSE → TanStack Query | Topic statistics, logs |
| UI state | Zustand | Panel open/close, topic selection |

---

## Common Development Tasks

### Adding a New API Endpoint

1. Define request/response models in `backend/app/features/{domain}/schemas.py`
2. Add the endpoint in `backend/app/features/{domain}/router.py` (always set `operation_id`)
3. If needed, implement business logic in `backend/app/features/{domain}/service.py`
4. Add tests
5. Regenerate the frontend API types: `make generate` (run while the backend is up)
6. If you added SSE events, update `docs/domain/sse.md`

### Supporting a New Topic Type

1. Check the subscription logic in `backend/app/features/topics/service.py`
2. Image/joint-state detection is structure-based (`backend/app/infra/mcap/messages.py`):
   - Image: has `format` field + `data` (bytes) (`is_image_message`)
   - Joint state: has `decoded.position` or `decoded.joint_state.position` (`extract_joint_positions`)
   - No hardcoded type names. Nested structures (custom message types that wrap a `JointState`, including composite types with extra joint groups) are already supported. To register a custom message package itself, see [`examples/custom_ros2_messages/`](../examples/custom_ros2_messages/)
3. Add dummy data publishing in the simulator (`simulator/robot_simulator.py`)

### Adding a UI Component

**Adding to an existing feature:**

1. Create the component under `frontend/src/features/{feature-name}/`
2. If referenced externally, add it to the barrel (`index.ts`) export
3. Place feature-specific stores and utilities inside the same feature

**For shared components:**

1. Create the new component under `frontend/src/components/ui/`

**Shared rules:**

- Import icons from `lucide-react`
- font-size must be 13px or larger
- Use Tailwind utility classes
- If server data is needed, use the orval-generated hooks; if custom options are needed, add a wrapper in `use-api.ts`
- Do not reference other features' internal files directly (only via the barrel)

### Updating Docker Image Dependencies

Which edits are picked up by a restart and which need `make build` differs per component, and differs again between the development and the production stack. See the "What lands where" table in each component's README:

- [backend/README.md](../backend/README.md#what-lands-where) — Python dependencies, ROS 2 / apt packages, config YAML
- [frontend/README.md](../frontend/README.md#what-lands-where) — Node.js dependencies, the pnpm version, Vite config
