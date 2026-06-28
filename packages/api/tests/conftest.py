"""API test configuration.

Integration tests are skipped unless ``POKE_BATTLES_RUN_INTEGRATION=1`` is
set in the environment. The flag is opt-in so a default ``uv run pytest``
run is hermetic — it never tries to spawn a real Showdown server, a
browser, or hit a live CDN.
"""

from __future__ import annotations

import os

import pytest

INTEGRATION_ENV_VAR = "POKE_BATTLES_RUN_INTEGRATION"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(INTEGRATION_ENV_VAR) == "1":
        return
    skip_integration = pytest.mark.skip(
        reason=f"set {INTEGRATION_ENV_VAR}=1 to run integration tests"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
