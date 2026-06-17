"""Local Showdown server lifecycle: clone, install, start, stop.

Used by the demo CLI and by Phase 4's container orchestrator. In production,
the orchestrator spawns the same image as a Docker container; for local dev
this module runs Showdown directly with ``node``.

Re-exported from :mod:`pokeengine`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import signal
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SHOWDOWN_REPO = "https://github.com/smogon/pokemon-showdown.git"
DEFAULT_PORT = 8000
STARTUP_TIMEOUT_S = 30.0
HEALTHCHECK_INTERVAL_S = 0.25


@dataclass(frozen=True)
class ShowdownHandle:
    process: subprocess.Popen[bytes]
    port: int
    server_dir: Path
    pid: int

    def stop(self, timeout: float = 5.0) -> None:
        if self.process.poll() is not None:
            return
        logger.info("Stopping Showdown server (pid=%d)", self.pid)
        with contextlib.suppress(ProcessLookupError):
            self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("Showdown did not exit cleanly, sending SIGKILL")
            self.process.kill()
            self.process.wait(timeout=timeout)


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def ensure_showdown(server_dir: Path | str = "server", *, force_clone: bool = False) -> Path:
    """Clone + install Showdown if ``server_dir`` is missing or ``force_clone``."""
    server_path = Path(server_dir)
    if server_path.exists() and not force_clone and (server_path / "node_modules").is_dir():
        return server_path
    if server_path.exists() and force_clone:
        shutil.rmtree(server_path)
    server_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Cloning Showdown into %s", server_path)
    subprocess.run(
        ["git", "clone", "--depth=1", SHOWDOWN_REPO, str(server_path)],
        check=True,
    )
    logger.info("Installing server dependencies")
    subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=server_path, check=True)
    config_src = server_path / "config" / "config-example.js"
    config_dst = server_path / "config" / "config.js"
    if config_src.exists() and not config_dst.exists():
        shutil.copy(config_src, config_dst)
    return server_path


def start_showdown(
    server_dir: Path | str = "server",
    *,
    port: int | None = None,
    no_security: bool = True,
) -> ShowdownHandle:
    """Start the local Showdown server and return a handle for lifecycle control."""
    server_path = Path(server_dir)
    if not server_path.exists():
        server_path = ensure_showdown(server_dir)
    chosen_port = port or _find_free_port()
    env = os.environ.copy()
    env["PORT"] = str(chosen_port)
    args = ["node", "pokemon-showdown", "start"]
    if no_security:
        args.append("--no-security")
    logger.info("Starting Showdown on port %d (cwd=%s)", chosen_port, server_path)
    proc = subprocess.Popen(args, cwd=server_path, env=env)
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Showdown process exited prematurely (code {proc.returncode})")
        if _port_is_open("127.0.0.1", chosen_port):
            time.sleep(0.5)
            return ShowdownHandle(
                process=proc, port=chosen_port, server_dir=server_path, pid=proc.pid
            )
        time.sleep(HEALTHCHECK_INTERVAL_S)
    proc.kill()
    proc.wait(timeout=2.0)
    raise TimeoutError(f"Showdown did not start within {STARTUP_TIMEOUT_S}s")


@contextlib.contextmanager
def showdown_server(
    server_dir: Path | str = "server", port: int | None = None
) -> Iterator[ShowdownHandle]:
    """Context manager that starts Showdown and tears it down on exit."""
    handle = start_showdown(server_dir, port=port)
    try:
        yield handle
    finally:
        handle.stop()


async def wait_for_battle(player: Any, battle_tag: str, timeout: float = 120.0) -> None:
    """Block until ``player`` reports the given battle as finished."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    winners: dict[str, str | None] = getattr(player, "_battle_winners", {})
    while loop.time() < deadline:
        if battle_tag in winners:
            return
        await asyncio.sleep(0.5)
        winners = getattr(player, "_battle_winners", {})
    raise TimeoutError(f"Battle {battle_tag} did not finish within {timeout}s")


__all__ = [
    "DEFAULT_PORT",
    "SHOWDOWN_REPO",
    "ShowdownHandle",
    "ensure_showdown",
    "showdown_server",
    "start_showdown",
    "wait_for_battle",
]
