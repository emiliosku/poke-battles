# Build the Vite bundle on the CI runner's native amd64 — the JS
# transpilation in ``npm run build`` SIGILLs about 1 in 2 runs under
# QEMU's arm64 emulation, the same flaky failure that originally hit
# the showdown and API Dockerfiles. Both of those were fixed by
# forcing the builder to amd64 and producing the runtime image for
# arm64; we do the same here so the final nginx image stays
# arm64-native for the OCI host.
FROM --platform=linux/amd64 node:20-alpine AS build

WORKDIR /app
COPY web/ /app/
ENV VITE_BASE_PATH=/poke-battles/
# Bake the /debug/sprites page into the production bundle. The
# `import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEBUG === "true"`
# guard in App.tsx reads this at build time. We set it here to "true"
# unconditionally so the deployed image always exposes the debug
# route (the size cost is ~7kB). The route hits the live pokeapi's
# /api/sprites/status endpoint and the Showdown CDN — no auth, no
# mutating endpoints, so the surface is safe to leave open.
ENV VITE_ENABLE_DEBUG=true
RUN npm ci --no-audit --no-fund && \
    npm run build

FROM --platform=linux/arm64 nginx:1.27-alpine

COPY --from=build /app/dist/ /usr/share/nginx/html/poke-battles/
COPY web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost/poke-battles/ >/dev/null || exit 1
