# Static build of the OpenLUTRA frontend, served by nginx.
# Build context: the repository root, filtered by frontend.Dockerfile.dockerignore.

FROM node:22-slim AS build

WORKDIR /app

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack enable && corepack install
RUN pnpm install --frozen-lockfile

COPY frontend/ ./

# VITE_* values are inlined at build time. MJPEG streams bypass nginx and hit the
# backend directly, so the default assumes the browser runs on the device itself.
ARG VITE_API_BASE=http://localhost:8000
ENV VITE_API_BASE=${VITE_API_BASE} \
    VITE_DEV_MODE=false

# `pnpm run build` runs `tsc -b` first, which needs routeTree.gen.ts that only
# `vite build` generates.
RUN pnpm exec vite build

FROM nginx:1.27-alpine

# The nginx image renders templates/*.template with envsubst at startup,
# substituting only variables that are defined in the environment.
ENV BACKEND_ORIGIN=http://127.0.0.1:8000
COPY examples/greengrass/docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 5173
