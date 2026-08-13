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

So the running server reads the working tree, not the code baked into the image. `uv.lock` and `.venv` are **not** mounted — they stay at their build-time state, which is why dependency changes need a rebuild.

### The container ignores `command:`

The image declares `ENTRYPOINT ["/entrypoint.sh"]`, and the script ends with its own `exec uv run --offline uvicorn app.main:app ...` without passing `"$@"` through. The `command:` in `docker-compose.yml` is therefore handed to the entrypoint as arguments and dropped — including its `--reload --reload-dir` flags:

```console
$ docker exec open-lutra-backend ps -eo args | grep uvicorn
uv run --offline uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Editing `backend/app/` updates the files inside the container immediately, but uvicorn runs without autoreload in both stacks, so the server keeps serving the code it imported at start-up until it is restarted.

`uv run --offline` is what keeps start-up working with no network access; the entrypoint also resolves `ROS_DOMAIN_ID` from `RECORDING_CONFIG` before launching.

## What lands where

| You change | Development (`make up`) | Production (`make prod-up`) |
|---|---|---|
| `backend/app/**` | Restart the container (`docker compose restart backend`) — the mount is live, but uvicorn has no autoreload | `make prod-restart` |
| `backend/tests/**` | Nothing to do — `make test-backend` runs pytest inside the running container against the mount | Not applicable |
| `config/*.yaml` | Restart the container — the YAML is read once and cached (`app/settings.py`), and `ROS_DOMAIN_ID` is resolved at start-up | `make prod-restart` |
| `.env` and other environment variables | Recreate the container (`make restart`); a plain `docker compose restart` reuses the environment the container was created with | `make prod-restart` |
| Dependencies in `pyproject.toml` | `make build`, then `make restart` — `uv.lock` and `.venv` live in the image, and `uv run --offline` cannot fetch new packages | `make build`, then `make prod-restart` |
| apt / ROS 2 packages in `Dockerfile` | `make build`, then `make restart` | `make build`, then `make prod-restart` |

Carrying an updated image to a site without network access:

```bash
docker save open-lutra-backend:latest | gzip > backend.tar.gz   # online
docker load < backend.tar.gz                                    # on site
```
