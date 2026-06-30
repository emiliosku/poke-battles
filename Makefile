.PHONY: help install sync lint format typecheck test test-cov ci demo bench train clean

MODELS ?= random heuristic
N ?= 10
FORMAT ?= gen9randombattle
UV_PROJECT_ENVIRONMENT ?= .uv-venv
export UV_PROJECT_ENVIRONMENT

help:
	@echo "Available targets:"
	@echo "  install     - Install all workspace packages"
	@echo "  sync        - Sync dependencies via uv"
	@echo "  lint        - Run ruff linter"
	@echo "  format      - Run ruff formatter"
	@echo "  typecheck   - Run mypy --strict"
	@echo "  test        - Run pytest"
	@echo "  test-cov    - Run pytest with coverage"
	@echo "  ci          - Run lint, typecheck, test-cov"
	@echo "  demo        - Run a local 1v1 random battle"
	@echo "  bench       - Run benchmark matchups (MODELS='random heuristic' N=10 FORMAT=gen9randombattle)"
	@echo "  train       - Run RL training (requires Showdown server + [train] extra)"
	@echo "  clean       - Remove build artifacts"

install:
	uv pip install \
		-e packages/core \
		-e "packages/engine[dev]" \
		-e packages/llm \
		-e packages/api \
		-e packages/eval \
		-e packages/rl \
		-e pokecli

sync:
	uv sync

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy \
		packages/core/src \
		packages/engine/src \
		packages/llm/src \
		packages/api/src \
		packages/eval/src \
		packages/rl/src \
		tests

test:
	uv run pytest

test-cov:
	uv run pytest \
		--cov=pokecore --cov=pokeengine \
		--cov=pokellm --cov=pokeapi --cov=pokebench --cov=pokerl \
		--cov-report=term-missing --cov-report=html

ci: lint typecheck test-cov

demo:
	uv run python -m pokeengine.demo

bench:
	uv run pokebench --models $(MODELS) --n-battles $(N) --format $(FORMAT)

train:
	uv run pokerl-train --timesteps 500000 --opponent random

clean:
	rm -rf .venv build dist .pytest_cache .ruff_cache .mypy_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
