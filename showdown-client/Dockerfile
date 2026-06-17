FROM node:20-alpine AS builder

ARG CLIENT_REF=master

RUN apk add --no-cache git python3 make g++ \
    && git clone --depth=1 --branch=${CLIENT_REF} \
        https://github.com/smogon/pokemon-showdown-client.git /build \
    && cd /build \
    && npm ci --no-audit --no-fund \
    && node build

FROM node:20-alpine

RUN apk add --no-cache tini curl \
    && addgroup -S client -g 1000 \
    && adduser -S client -u 1000 -G client

WORKDIR /opt/client
COPY --from=builder --chown=client:client /build /opt/client

USER client
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD curl -fsS http://localhost:8000/ || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "build-tools/build-and-grunt", "release"]
