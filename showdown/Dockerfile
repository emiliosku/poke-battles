# The transpilation step (``node build``) SIGILLs about 1 in 2 runs
# under QEMU's arm64 emulation, so we force the builder stage to
# run natively on the CI runner (amd64). The final image is built
# for arm64 and runs natively on the OCI ARM host — avoiding both
# the build-time SIGILL and the runtime ``exec format error`` that
# hits when the host has no QEMU binfmt_misc registered (the
# previous ``linux/amd64`` build assumed QEMU user-mode emulation
# was available, which it isn't on the OCI ARM box).
FROM --platform=linux/amd64 node:20-alpine AS builder

ARG SHOWDOWN_REF=master

RUN apk add --no-cache git python3 make g++ \
    && git clone --depth=1 --branch=${SHOWDOWN_REF} \
        https://github.com/smogon/pokemon-showdown.git /build \
    && cd /build \
    && npm ci --no-audit --no-fund \
    && node build

FROM --platform=linux/arm64 node:20-alpine

RUN apk add --no-cache curl \
    && addgroup -S showdown \
    && adduser -S showdown -G showdown

WORKDIR /opt/showdown
COPY --from=builder --chown=showdown:showdown /build /opt/showdown

# Drop tini: the previous amd64 tini binary segfaulted on the ARM
# host under QEMU, and now that the image is arm64-native there's
# no QEMU to translate it anyway. node as PID 1 handles SIGTERM
# and SIGINT cleanly, and the server doesn't fork subprocesses
# that need reaping.
USER showdown
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD curl -fsS http://localhost:8000/ || exit 1

CMD ["node", "pokemon-showdown", "start", "--no-security"]
