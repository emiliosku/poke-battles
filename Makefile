.PHONY: help install sync lint format typecheck test test-cov ci demo clean

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
	@echo "  clean       - Remove build artifacts"

install:
	uv pip install \
		-e packages/core \
		-e "packages/engine[dev]" \
		-e packages/llm \
		-e packages/api \
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
		tests

test:
	uv run pytest

test-cov:
	uv run pytest \
		--cov=pokecore --cov=pokeengine \
		--cov=pokellm --cov=pokeapi \
		--cov-report=term-missing --cov-report=html

ci: lint typecheck test-cov

demo:
	uv run python -m pokeengine.demo

clean:
	rm -rf .venv build dist .pytest_cache .ruff_cache .mypy_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
