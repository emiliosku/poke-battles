FROM node:20-alpine AS builder

ARG SHOWDOWN_REF=master

RUN apk add --no-cache git python3 make g++ \
    && git clone --depth=1 --branch=${SHOWDOWN_REF} \
        https://github.com/smogon/pokemon-showdown.git /build \
    && cd /build \
    && npm ci --no-audit --no-fund \
    && node build

FROM node:20-alpine

RUN apk add --no-cache tini curl \
    && addgroup -S showdown \
    && adduser -S showdown -G showdown

WORKDIR /opt/showdown
COPY --from=builder --chown=showdown:showdown /build /opt/showdown

USER showdown
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD curl -fsS http://localhost:8000/ || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "pokemon-showdown", "start", "--no-security"]
