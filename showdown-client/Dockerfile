FROM --platform=$BUILDPLATFORM node:20-alpine AS builder

ARG CLIENT_REF=master

RUN apk add --no-cache git python3 make g++ \
    && git clone --depth=1 --branch=${CLIENT_REF} \
        https://github.com/smogon/pokemon-showdown-client.git /build \
    && cd /build \
    && npm ci --no-audit --no-fund \
    && node build

FROM node:20-alpine

WORKDIR /opt/client
COPY --from=builder --chown=node:node /build /opt/client
COPY --chown=node:node showdown-client/static-server.mjs /opt/static-server.mjs

USER node
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD node -e "fetch('http://localhost:8000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "/opt/static-server.mjs"]
