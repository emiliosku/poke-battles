"""LLM client: thin wrapper around LiteLLM with retry, observability, fallback.

The client does not depend on poke-env types — it just takes a state dict (as
produced by :func:`pokecore...`) and returns a decision.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import litellm
from json_repair import repair_json
from tenacity import retry, stop_after_attempt, wait_exponential

from pokellm.config import AgentConfig
from pokellm.tools import TOOLS

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LLMDecision:
    """A parsed LLM decision."""

    action: str
    move_id: str | None = None
    pokemon_name: str | None = None
    commentary: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        if self.action == "choose_move":
            return f"choose_move({self.move_id})"
        if self.action == "choose_switch":
            return f"choose_switch({self.pokemon_name})"
        return f"unknown({self.action})"


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: Any


class LLMClient:
    """Async LLM client. State in, decision out."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        on_tool_call: Callable[[ToolCallRecord], None] | None = None,
        on_response: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.config = config
        self._on_tool_call = on_tool_call
        self._on_response = on_response
        self._tool_history: list[ToolCallRecord] = []

    @property
    def tool_history(self) -> list[ToolCallRecord]:
        return list(self._tool_history)

    @staticmethod
    def _to_litellm_tools() -> list[dict[str, Any]]:
        return [{"type": "function", "function": t} for t in TOOLS]

    def _truncate(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3] + "..."

    async def decide(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        extra_tools: list[dict[str, Any]] | None = None,
    ) -> LLMDecision:
        """Send a single-turn request to the LLM and parse the tool call."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        tools = self._to_litellm_tools()
        if extra_tools:
            tools.extend({"type": "function", "function": t} for t in extra_tools)
        response = await self._acompletion(messages, tools)
        return self._parse_response(response)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _acompletion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        cfg = self.config
        params: dict[str, Any] = {
            "model": cfg.model_id,
            "messages": messages,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "timeout": cfg.timeout_s,
        }
        if cfg.supports_tools and tools:
            params["tools"] = tools
            params["tool_choice"] = "required"
        return await litellm.acompletion(**params)

    def _parse_response(self, response: Any) -> LLMDecision:
        try:
            message = response.choices[0].message
        except (AttributeError, IndexError, KeyError) as exc:
            logger.error("Malformed LLM response: %s", exc)
            return LLMDecision(
                action="__error__", commentary=str(exc), raw_response={"error": str(exc)}
            )
        if self._on_response is not None:
            try:
                self._on_response({"message": str(getattr(message, "content", ""))[:200]})
            except Exception:
                pass
        tool_calls = list(getattr(message, "tool_calls", None) or [])
        if not tool_calls:
            content = getattr(message, "content", None)
            if content:
                fallback = self._parse_text_fallback(content)
                if fallback is not None:
                    return fallback
            return LLMDecision(
                action="__no_tool_call__", commentary=str(content)[:200] if content else ""
            )
        call = tool_calls[0]
        try:
            func_name = call.function.name
            raw_args = call.function.arguments
        except AttributeError:
            func_name = call.get("function", {}).get("name", "")
            raw_args = call.get("function", {}).get("arguments", "{}")
        args = self._safe_json_loads(raw_args)
        self._tool_history.append(ToolCallRecord(name=func_name, arguments=args, result=None))
        if self._on_tool_call is not None:
            try:
                self._on_tool_call(self._tool_history[-1])
            except Exception:
                pass
        return self._build_decision(func_name, args, response, tool_calls)

    def _parse_text_fallback(self, content: str) -> LLMDecision | None:
        repaired = repair_json(content, return_objects=True)
        if isinstance(repaired, dict):
            return self._build_decision(
                str(repaired.get("action", "__unknown__")),
                repaired,
                None,
                [],
            )
        return None

    def _build_decision(
        self,
        func_name: str,
        args: dict[str, Any],
        response: Any,
        tool_calls: list[Any],
    ) -> LLMDecision:
        commentary = str(args.get("commentary", "")).strip()
        if func_name == "choose_move":
            return LLMDecision(
                action="choose_move",
                move_id=str(args.get("move_name", "")).strip(),
                commentary=commentary,
                raw_response={"response": str(response)[:500]} if response is not None else {},
                tool_calls=[self._normalize_call(c) for c in tool_calls],
            )
        if func_name == "choose_switch":
            return LLMDecision(
                action="choose_switch",
                pokemon_name=str(args.get("pokemon_name", "")).strip(),
                commentary=commentary,
                raw_response={"response": str(response)[:500]} if response is not None else {},
                tool_calls=[self._normalize_call(c) for c in tool_calls],
            )
        return LLMDecision(
            action=f"__tool:{func_name}__",
            commentary=commentary,
            raw_response={"args": args, "response": str(response)[:500]}
            if response is not None
            else {"args": args},
            tool_calls=[self._normalize_call(c) for c in tool_calls],
        )

    @staticmethod
    def _normalize_call(call: Any) -> dict[str, Any]:
        if isinstance(call, dict):
            return call
        try:
            return {
                "id": getattr(call, "id", None),
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
        except AttributeError:
            return {"raw": str(call)[:200]}

    @staticmethod
    def _safe_json_loads(s: str | None) -> dict[str, Any]:
        if not s:
            return {}
        try:
            return dict(json.loads(s))
        except (json.JSONDecodeError, TypeError):
            repaired = repair_json(s, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
            return {}


__all__ = ["LLMClient", "LLMDecision", "ToolCallRecord"]
_ = (Awaitable, os)
