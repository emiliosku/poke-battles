FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 poke && mkdir /app && chown poke:poke /app
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages ./packages

RUN pip install uv && \
    uv pip install --system \
        -e ./packages/core \
        -e ./packages/engine \
        -e ./packages/llm \
        -e ./packages/api \
        "psycopg2-binary>=2.9.0"

RUN chown -R poke:poke /app

USER poke

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "pokeapi.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
