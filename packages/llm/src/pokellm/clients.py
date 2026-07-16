"""LLM client: thin wrapper around LiteLLM with retry, observability, fallback.

The client does not depend on poke-env types — it just takes a state dict (as
produced by :func:`pokecore...`) and returns a decision.

Two call modes:

- :meth:`LLMClient.decide` — single-turn. Sends the prompt, parses the first
  tool call, returns a :class:`LLMDecision`. Backward-compatible with the
  pre-Phase-4 agent.
- :meth:`LLMClient.decide_loop` — multi-turn tool-calling loop. The LLM may
  call ``evaluate_candidate`` / ``propose_alternative`` /
  ``lookup_type_chart`` etc. between 0 and ``max_iterations`` times before
  terminating with ``choose_move`` or ``choose_switch``. The caller injects
  the heuristic's shortlist as the ``tool_context`` argument so the new
  ``evaluate_candidate`` / ``propose_alternative`` tools can answer.

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
from pokellm.tools import (
    TOOLS,
    estimate_damage_tool,
    evaluate_candidate_tool,
    evaluate_switch_tool,
    lookup_type_chart_tool,
    propose_alternative_tool,
)

logger = logging.getLogger(__name__)

try:
    import langfuse as _langfuse

    _HAS_LANGFUSE = True
except ImportError:
    _HAS_LANGFUSE = False

_langfuse_client: Any = None


def _get_langfuse() -> Any:
    global _langfuse_client
    if _langfuse_client is None and _HAS_LANGFUSE:
        pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
        sk = os.environ.get("LANGFUSE_SECRET_KEY")
        host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
        if pk and sk:
            try:
                _langfuse_client = _langfuse.Langfuse(public_key=pk, secret_key=sk, host=host)
                logger.info("Langfuse client initialized")
            except Exception as exc:
                logger.warning("Failed to init Langfuse: %s", exc)
    return _langfuse_client


def _default_on_response(cfg: AgentConfig) -> Callable[[dict[str, Any]], None]:
    def _cb(info: dict[str, Any]) -> None:
        lf = _get_langfuse()
        if lf is None:
            return
        try:
            trace = lf.trace(
                name="llm_decision",
                input=info,
                metadata={"model": cfg.model_id, "provider": cfg.provider},
            )
            trace.end(output=info)
        except Exception:
            pass

    return _cb


def _default_on_tool_call() -> Callable[[Any], None]:
    def _cb(record: Any) -> None:
        lf = _get_langfuse()
        if lf is None:
            return
        try:
            span = lf.span(name="tool_call")
            span.update(
                input={
                    "name": getattr(record, "name", ""),
                    "args": getattr(record, "arguments", {}),
                }
            )
            span.end(output=getattr(record, "result", None))
        except Exception:
            pass

    return _cb


@dataclass(frozen=True, slots=True)
class LLMDecision:
    """A parsed LLM decision."""

    action: str
    move_id: str | None = None
    pokemon_name: str | None = None
    terastallize: bool = False
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
        self._on_tool_call = on_tool_call or _default_on_tool_call()
        self._on_response = on_response or _default_on_response(config)
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
                terastallize=args.get("terastallize") is True,
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

    async def decide_loop(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tool_context: dict[str, Any] | None = None,
        max_iterations: int = 4,
    ) -> LLMDecision:
        """Multi-turn tool-calling loop.

        Each iteration:

        1. Call the LLM with the current message history.
        2. If the response contains a tool call:
           - If it's a terminal action (``choose_move`` / ``choose_switch``),
             return the parsed :class:`LLMDecision`.
           - Otherwise, dispatch to the local implementation in
             :mod:`pokellm.tools`, append a synthetic tool result to the
             message history, and continue the loop.
        3. If no tool call (e.g. plain text), parse as a fallback and return.
        4. Stop after ``max_iterations`` to bound cost.

        ``tool_context`` is a per-turn dict passed to every local tool
        implementation. The agent injects the heuristic's shortlist here so
        ``evaluate_candidate`` and ``propose_alternative`` can answer.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        tools = self._to_litellm_tools()
        tool_context = dict(tool_context or {})

        for iteration in range(max_iterations):
            response = await self._acompletion(messages, tools)
            message = self._safe_get_message(response)
            if message is None:
                return LLMDecision(action="__error__", commentary="malformed LLM response")
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if not tool_calls:
                content = getattr(message, "content", None)
                if content:
                    fallback = self._parse_text_fallback(content)
                    if fallback is not None:
                        return fallback
                return LLMDecision(
                    action="__no_tool_call__",
                    commentary=str(content)[:200] if content else "",
                )

            first_call = tool_calls[0]
            func_name, raw_args = self._extract_call(first_call)
            args = self._safe_json_loads(raw_args)

            # Terminal actions: return immediately.
            if func_name in {"choose_move", "choose_switch"}:
                # Record the call (no result, the loop ends).
                self._tool_history.append(
                    ToolCallRecord(name=func_name, arguments=args, result=None)
                )
                return self._build_decision(func_name, args, response, tool_calls)

            # Non-terminal: dispatch locally, append result, continue.
            result = _dispatch_tool(func_name, args, tool_context)
            self._tool_history.append(ToolCallRecord(name=func_name, arguments=args, result=result))
            if self._on_tool_call is not None:
                try:
                    self._on_tool_call(self._tool_history[-1])
                except Exception:
                    pass
            messages.append(_tool_call_message(first_call))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": getattr(first_call, "id", ""),
                    "content": json.dumps(result),
                }
            )
            logger.debug("decide_loop iteration %d: %s -> %s", iteration, func_name, result)

        return LLMDecision(
            action="__iter_limit__",
            commentary=f"LLM did not call choose_move/choose_switch in {max_iterations} iterations",
        )

    def _safe_get_message(self, response: Any) -> Any:
        try:
            return response.choices[0].message
        except (AttributeError, IndexError, KeyError) as exc:
            logger.error("Malformed LLM response: %s", exc)
            return None

    def _extract_call(self, call: Any) -> tuple[str, str]:
        try:
            return call.function.name, call.function.arguments
        except AttributeError:
            payload = call.get("function", {}) if isinstance(call, dict) else {}
            return payload.get("name", ""), payload.get("arguments", "{}")


def _dispatch_tool(
    func_name: str, args: dict[str, Any], tool_context: dict[str, Any]
) -> dict[str, Any]:
    """Run a reasoning tool locally and return its result as a dict."""
    try:
        if func_name == "lookup_type_chart":
            return {
                "multiplier": lookup_type_chart_tool(
                    str(args.get("move_type", "")),
                    str(args.get("defender_primary", "")),
                    args.get("defender_secondary") or None,
                )
            }
        if func_name == "estimate_damage":
            raw = estimate_damage_tool(
                int(args.get("move_base_power", 0)),
                str(args.get("move_type", "")),
                list(args.get("attacker_types", []) or []),
                str(args.get("defender_primary", "")),
                args.get("defender_secondary") or None,
            )
            return dict(raw)
        if func_name == "evaluate_switch":
            raw = evaluate_switch_tool(
                list(args.get("candidate_types", []) or []),
                list(args.get("opponent_types", []) or []),
                float(args.get("candidate_hp_fraction", 1.0)),
            )
            return dict(raw)
        if func_name == "evaluate_candidate":
            return dict(
                evaluate_candidate_tool(
                    str(args.get("kind", "")),
                    str(args.get("target_id", "")),
                    tool_context.get("shortlist_view"),
                )
            )
        if func_name == "propose_alternative":
            return dict(
                propose_alternative_tool(
                    str(args.get("kind", "")),
                    str(args.get("target_id", "")),
                    str(args.get("reasoning", "")),
                    tool_context.get("shortlist_view"),
                    tool_context.get("damage_estimate"),
                )
            )
    except Exception as exc:  # never let a tool crash the loop
        logger.warning("tool %s raised: %s", func_name, exc)
        return {"error": f"tool {func_name} failed: {exc}"}
    return {"error": f"unknown tool: {func_name}"}


def _tool_call_message(call: Any) -> dict[str, Any]:
    """Render an assistant tool_call message for the next iteration."""
    func_name, raw_args = ("unknown", "{}")
    try:
        func_name = call.function.name
        raw_args = call.function.arguments
    except AttributeError:
        if isinstance(call, dict):
            payload = call.get("function", {}) or {}
            func_name = payload.get("name", "unknown")
            raw_args = payload.get("arguments", "{}")
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": getattr(call, "id", "0"),
                "type": "function",
                "function": {"name": func_name, "arguments": raw_args},
            }
        ],
    }


__all__ = ["LLMClient", "LLMDecision", "ToolCallRecord"]
_ = (Awaitable, os)
