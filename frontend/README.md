# Frontend

React + Vite UI for OpenLUTRA.

- Directory layout: [docs/STRUCTURE.md](../docs/STRUCTURE.md)
- Feature pattern, lint/test commands, UI conventions: [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md)

This file covers only how the container is put together, and which edits are picked up by a restart versus a rebuild.

## Container layout

`frontend/Dockerfile` builds `open-lutra-frontend:latest`, shared by the development and the production stack. The image carries pnpm (installed through corepack) and a fully populated `/app/node_modules`; the source tree is deliberately not copied:

```console
$ docker run --rm --entrypoint sh open-lutra-frontend:latest -c "ls /app"
node_modules  package.json  pnpm-lock.yaml  pnpm-workspace.yaml
```

Compose supplies the source instead, as a bind mount of `./frontend` onto `/app`, with the named volume `frontend_node_modules` layered back on top of `/app/node_modules`. Both stacks mount it, so the running server always reads the working tree rather than anything baked into the image.

Both stacks also run the Vite dev server. Production keeps it because `VITE_API_BASE` depends on the site's hostname and is passed as runtime env; a static build would have to be rebuilt per site.

The start-up command is the one real difference:

| Stack | Command |
|---|---|
| Development (`make up`) | `pnpm install --frozen-lockfile && pnpm run dev` |
| Production (`make prod-up`) | `pnpm run dev` |

Development reinstalls on every start so dependency changes land without an image rebuild. Production skips the install because everything already ships inside the image — that is what lets `make prod-up` succeed on a site with no internet access.

## What lands where

| You change | Development (`make up`) | Production (`make prod-up`) |
|---|---|---|
| `src/**`, `index.html`, `public/**` | Applied immediately (Vite HMR) | Applied immediately (Vite HMR) |
| `vite.config.ts`, `tsconfig.json`, `orval.config.ts` | Restart the container (`make restart`) | `make prod-restart` |
| `VITE_DEV_MODE`, `VITE_API_BASE` and other environment variables | Recreate the container (`make restart` / `make dev-up`); a plain `docker compose restart` reuses the environment the container was created with | `make prod-restart` |
| Dependencies in `package.json` / `pnpm-lock.yaml` | Restart the container — the start-up install reconciles the volume with the lockfile (needs network) | `make build`, then drop the stale volume (below) |
| `packageManager` (pnpm version) in `package.json` | Restart the container — corepack fetches the new pnpm (needs network) | `make build`; otherwise corepack tries to fetch pnpm at start and fails without network |
| `frontend/Dockerfile` | `make build`, then `make restart` | `make build`, then `make prod-restart` |

## Refreshing node_modules in production

A named volume is initialized from the image only while it is still empty, so an existing `frontend_node_modules` keeps serving the previous dependencies even after the image is rebuilt. Drop it explicitly:

```bash
make prod-down
docker volume rm <compose project>_frontend_node_modules
make prod-up
```

Development needs none of this: its start-up `pnpm install --frozen-lockfile` reconciles the volume with the lockfile on every start.

Carrying an updated image to a site without network access:

```bash
docker save open-lutra-frontend:latest | gzip > frontend.tar.gz   # online
docker load < frontend.tar.gz                                     # on site
```
