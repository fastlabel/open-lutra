# Frontend image for the production stack (Vite dev server).
#
# The point of this image is to make `make prod-up` work on a site with no
# internet access: pnpm itself and every dependency are baked in at build time,
# so starting a container never reaches out to the network.

FROM node:22-slim

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# `corepack install` resolves the version from package.json's `packageManager`
# field, so the pnpm version is not duplicated here. This caches the pnpm
# binary inside the image; without it corepack downloads pnpm from
# registry.npmjs.org on every container start.
RUN corepack enable && corepack install

RUN pnpm install --frozen-lockfile

# The source tree is bind-mounted at /app by compose, so it is deliberately not
# copied into the image. The named volume mounted at /app/node_modules is
# initialized from the image's contents while it is still empty, which is what
# removes the need for an install at container start.

CMD ["pnpm", "run", "dev"]
