FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 poke && mkdir /app && chown poke:poke /app
WORKDIR /app
USER poke

COPY --chown=poke:poke pyproject.toml uv.lock ./
COPY --chown=poke:poke packages ./packages

RUN pip install --user uv && \
    ~/.local/bin/uv sync --frozen --no-dev && \
    ~/.local/bin/uv pip install --system "asyncpg>=0.29.0"

ENV PATH="/home/poke/.local/bin:${PATH}"
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "pokeapi.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
