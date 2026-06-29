"""Public, auth-free debug endpoints.

These exist because the OCI host doesn't expose the API container's
stdout, and there is no SSH access from the agent environment. The
endpoints are read-only and reveal only server state (no secrets, no
user data) so they are safe to leave on the public route.

Exposed shape::

    GET /debug/orchestrator

    {
      "uptime_s": 1234.5,
      "showdown": {
        "started": true,
        "port": 8123,
        "pid": 42,
        "alive": true,
        "server_dir": "/opt/showdown",
        "websocket_url": "ws://localhost:8123/showdown/websocket"
      },
      "orchestrator": {
        "running": true,
        "max_concurrent": 4,
        "queue_size": 0,
        "worker_count": 4,
        "results_count": 12
      },
      "logs_tail": [
        {"ts": "...", "level": "INFO", "logger": "...",
         "message": "..."}
      ]
    }

    GET /debug/logs?tail=50

    Returns just the log tail (defaults to 50, capped at 200).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query, Request

from pokeapi.debug import MemoryLogHandler, format_records

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/orchestrator")
async def orchestrator_snapshot(request: Request) -> dict[str, Any]:
    return _snapshot(request, tail=20)


@router.get("/logs")
async def logs_tail(
    request: Request, tail: int = Query(default=50, ge=1, le=200)
) -> dict[str, Any]:
    return {"logs_tail": format_records(_logs(request, tail=tail))}


def _snapshot(request: Request, tail: int) -> dict[str, Any]:
    start = getattr(request.app.state, "start_time", time.monotonic())
    bservice = getattr(request.app.state, "bservice", None)
    orch = getattr(request.app.state, "orchestrator", None)

    showdown: dict[str, Any] = {"started": False}
    if bservice is not None:
        handle = bservice.handle
        if handle is None:
            showdown = {
                "started": False,
                "server_dir": bservice.showdown_dir,
                "default_port": bservice.showdown_port,
            }
        else:
            alive = handle.process.poll() is None
            showdown = {
                "started": True,
                "port": handle.port,
                "pid": handle.pid,
                "alive": alive,
                "returncode": handle.process.returncode,
                "server_dir": str(handle.server_dir),
                "websocket_url": bservice.websocket_url(),
            }

    orch_state: dict[str, Any] = {"running": False}
    if orch is not None:
        running_jobs: list[str] = []
        queue_size = orch.queue.qsize()
        for task in orch._workers:
            if not task.done():
                running_jobs.append(task.get_name())
        orch_state = {
            "running": orch._running,
            "max_concurrent": orch.max_concurrent,
            "queue_size": queue_size,
            "worker_count": len(orch._workers),
            "results_count": len(orch.results),
            "worker_names": running_jobs,
        }

    return {
        "uptime_s": time.monotonic() - start,
        "showdown": showdown,
        "orchestrator": orch_state,
        "logs_tail": format_records(_logs(request, tail=tail)),
    }


def _logs(request: Request, tail: int) -> list[Any]:
    handler: MemoryLogHandler | None = getattr(request.app.state, "log_handler", None)
    if handler is None:
        return []
    snapshot = handler.snapshot()
    if tail <= 0 or tail >= len(snapshot):
        return snapshot
    return snapshot[-tail:]


__all__ = ["router"]
