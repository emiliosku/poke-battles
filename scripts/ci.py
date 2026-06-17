# CI helper: run the same checks as `make ci` from any environment.
# Useful when `make` is not installed (e.g., minimal containers).

import subprocess
import sys

COMMANDS = [
    ("ruff check", ["uv", "run", "ruff", "check", "."]),
    ("ruff format", ["uv", "run", "ruff", "format", "--check", "."]),
    (
        "mypy (packages)",
        [
            "uv",
            "run",
            "mypy",
            "packages/core/src",
            "packages/engine/src",
            "packages/llm/src",
            "packages/api/src",
        ],
    ),
    ("mypy (tests)", ["uv", "run", "mypy", "tests"]),
    (
        "pytest + coverage",
        [
            "uv",
            "run",
            "pytest",
            "--cov=pokecore",
            "--cov=pokeengine",
            "--cov=pokellm",
            "--cov=pokeapi",
            "--cov-report=term",
            "--cov-report=xml",
        ],
    ),
]


def main() -> int:
    failed: list[str] = []
    for label, cmd in COMMANDS:
        print(f"\n=== {label} ===")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            failed.append(label)
    print("\n=== Summary ===")
    if failed:
        print("FAILED:")
        for f in failed:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
