"""CLI entry point: ``uv run python -m pokeengine``."""

from __future__ import annotations

import sys

from pokeengine.demo import main

if __name__ == "__main__":
    sys.exit(main())
