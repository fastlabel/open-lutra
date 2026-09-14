# Backend

FastAPI + ROS 2 service for OpenLUTRA.

- Directory layout: [docs/STRUCTURE.md](../docs/STRUCTURE.md)
- Feature boundaries and data flow: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- Test layout, lint and coverage commands: [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md)

This file covers only how the container is put together, and which edits are picked up by a restart versus a rebuild.

## Container layout

The repository-root `Dockerfile` builds `open-lutra-backend:latest`, shared by the development and the production stack. Unlike the frontend image, it does contain the application code, the config directory, and a resolved virtualenv:

```console
$ docker run --rm --entrypoint sh open-lutra-backend:latest -c "ls -a /app"
.env  .venv  app  config  pyproject.toml  uv.lock
```

Compose then mounts the working tree over most of that, in development and production alike:

| Host | Container | Mode |
|---|---|---|
| `backend/app/` | `/app/app` | rw |
| `backend/tests/` | `/app/tests` | rw |
| `config/` | `/app/config` | ro |
| `backend/pyproject.toml` | `/app/pyproject.toml` | ro |
| `backend/uv.lock` | `/app/uv.lock` | ro |

So the running server reads the working tree, not the code baked into the image. `pyproject.toml` and `uv.lock` are mounted as a pair because uv compares the two: the working tree's `pyproject.toml` next to the image's older `uv.lock` reads as an outdated lockfile. `.venv` is **not** mounted — it stays at its build-time state, which is why dependency changes need a rebuild.

### What the entrypoint runs

The image declares `ENTRYPOINT ["/entrypoint.sh"]`. The script sources ROS 2 — plus `/ros2_ws` when a custom-message workspace is built into the image — and resolves `ROS_DOMAIN_ID` from `RECORDING_CONFIG`. It then hands over to `command:` when compose supplies one, and otherwise runs the server itself:

```console
$ docker exec open-lutra-backend ps -eo args | grep uvicorn     # development
uv run --locked --offline uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/app
```

That is how development adds `--reload --reload-dir /app/app`, so edits under `backend/app/` restart the server on their own. Production clears the command (`command: []` in `docker-compose.prod.yml`) and gets the entrypoint's own invocation, without the reloader.

`--offline` is what keeps start-up working with no network access, and `--locked` makes a `pyproject.toml` / `uv.lock` mismatch report itself as one instead of starting a resolution that offline mode could never finish.

## What lands where

| You change | Development (`make up`) | Production (`make prod-up`) |
|---|---|---|
| `backend/app/**` | Applied immediately — uvicorn reloads on its own (`--reload`) | `make prod-restart` — production runs without the reloader |
| `backend/tests/**` | Nothing to do — `make test-backend` runs pytest on the host; the mount only matters when running pytest inside the container | Not applicable |
| `config/*.yaml` | Restart the container — the YAML is read once and cached (`app/settings.py`), and `ROS_DOMAIN_ID` is resolved at start-up | `make prod-restart` |
| `.env` and other environment variables | Recreate the container (`make restart`); a plain `docker compose restart` reuses the environment the container was created with | `make prod-restart` |
| Dependencies in `pyproject.toml` (with `uv.lock` relocked) | `make build`, then `make restart` — `.venv` lives in the image, and `--offline` cannot fetch new packages | `make build`, then `make prod-restart` |
| Version or `[tool.*]` settings in `pyproject.toml` | Nothing to do — both mounted files move together, so uv still sees a matching lockfile | Nothing to do |
| apt / ROS 2 packages in `Dockerfile` | `make build`, then `make restart` | `make build`, then `make prod-restart` |

Carrying an updated image to a site without network access:

```bash
docker save open-lutra-backend:latest | gzip > backend.tar.gz   # online
docker load < backend.tar.gz                                    # on site
```
