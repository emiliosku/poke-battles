"""Unit tests for :mod:`pokellm.clients` (offline)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from pokellm.clients import LLMClient, ToolCallRecord
from pokellm.config import AgentConfig, Tier
from pokellm.tools import evaluate_candidate_tool, propose_alternative_tool


def _cfg() -> AgentConfig:
    return AgentConfig(
        name="test",
        provider="mock",
        model_id="mock/test",
        tier=Tier.MOCK,
        supports_tools=True,
    )


class _ScriptedResponse:
    def __init__(self, content: str, tool_calls: list[Any] | None = None) -> None:
        self.choices = [_ScriptedChoice(content, tool_calls or [])]


class _ScriptedChoice:
    def __init__(self, content: str, tool_calls: list[Any]) -> None:
        self.message = _ScriptedMessage(content, tool_calls)


class _ScriptedMessage:
    def __init__(self, content: str, tool_calls: list[Any]) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _ScriptedToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.function = _ScriptedFunction(name, arguments)


class _ScriptedFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


def _scripted_client(
    script: list[tuple[str, list[tuple[str, str, dict[str, object]]]]],
) -> LLMClient:
    """Build a client that returns the given script of (content, tool_calls) entries.

    Each tool_call is a tuple of (id, name, args-dict).
    """

    class _Stub(LLMClient):
        def __init__(self) -> None:
            super().__init__(config=_cfg())
            self._iter = 0
            self._script = script

        async def _acompletion(self, messages, tools):  # type: ignore[no-untyped-def]
            if self._iter >= len(self._script):
                content: str = ""
                calls: list[tuple[str, str, dict[str, object]]] = []
            else:
                content, calls = self._script[self._iter]
                self._iter += 1
            tool_calls = [
                _ScriptedToolCall(call_id, name, json.dumps(args)) for call_id, name, args in calls
            ]
            return _ScriptedResponse(content, tool_calls)

    return _Stub()


@pytest.mark.asyncio
async def test_decide_loop_terminates_on_choose_move() -> None:
    client = _scripted_client(
        [
            (
                "",
                [
                    (
                        "c1",
                        "choose_move",
                        {"move_name": "earthquake", "terastallize": True, "commentary": "final"},
                    )
                ],
            )
        ]
    )
    decision = await client.decide_loop(system_prompt="sys", user_prompt="user", max_iterations=4)
    assert decision.action == "choose_move"
    assert decision.move_id == "earthquake"
    assert decision.terastallize is True


@pytest.mark.asyncio
async def test_decide_loop_handles_reasoning_then_terminal() -> None:
    client = _scripted_client(
        [
            ("", [("c1", "evaluate_candidate", {"kind": "move", "target_id": "earthquake"})]),
            ("", [("c2", "choose_switch", {"pokemon_name": "Heatran", "commentary": "pivot"})]),
        ]
    )
    decision = await client.decide_loop(
        system_prompt="sys",
        user_prompt="user",
        tool_context={
            "shortlist_view": [
                {"kind": "move", "target_id": "earthquake", "score": 100.0, "justification": "ok"}
            ]
        },
        max_iterations=4,
    )
    assert decision.action == "choose_switch"
    assert decision.pokemon_name == "Heatran"
    history = client.tool_history
    assert [h.name for h in history] == ["evaluate_candidate", "choose_switch"]


@pytest.mark.asyncio
async def test_decide_loop_uses_tool_context_for_shortlist() -> None:
    """The LLM should see a tool result containing the shortlist score."""
    shortlist_view = [
        {
            "kind": "move",
            "target_id": "earthquake",
            "score": 100.0,
            "justification": "4x super effective",
            "expected_pct": 120.0,
            "ko_chance": {"ohko": 0.5},
        }
    ]

    class _VerifyCtx(LLMClient):
        def __init__(self) -> None:
            super().__init__(config=_cfg())
            self._iter = 0
            self._script = [
                ("", [("c1", "evaluate_candidate", {"kind": "move", "target_id": "earthquake"})]),
                ("", [("c2", "choose_move", {"move_name": "earthquake", "commentary": "ok"})]),
            ]
            self.tool_result_seen: str | None = None

        async def _acompletion(  # type: ignore[no-untyped-def]
            self, messages, tools
        ):
            content, calls = self._script[self._iter]
            self._iter += 1
            tool_results = [m for m in messages if m.get("role") == "tool"]
            if tool_results:
                self.tool_result_seen = tool_results[-1]["content"]
            tool_calls = [
                _ScriptedToolCall(call_id, name, json.dumps(args)) for call_id, name, args in calls
            ]
            return _ScriptedResponse(content, tool_calls)

    client = _VerifyCtx()
    decision = await client.decide_loop(
        system_prompt="sys",
        user_prompt="user",
        tool_context={"shortlist_view": shortlist_view},
        max_iterations=3,
    )
    assert decision.action == "choose_move"
    assert client.tool_result_seen is not None
    assert "100" in client.tool_result_seen


@pytest.mark.asyncio
async def test_decide_loop_stops_at_max_iterations() -> None:
    # Always returns a non-terminal tool call; loop should give up after 2.
    client = _scripted_client(
        [
            ("", [("c1", "lookup_type_chart", {"move_type": "fire", "defender_primary": "water"})]),
            ("", [("c2", "lookup_type_chart", {"move_type": "fire", "defender_primary": "water"})]),
            ("", [("c3", "lookup_type_chart", {"move_type": "fire", "defender_primary": "water"})]),
        ]
    )
    decision = await client.decide_loop(system_prompt="sys", user_prompt="user", max_iterations=2)
    assert decision.action == "__iter_limit__"


def test_evaluate_candidate_tool_finds_shortlist_entry() -> None:
    shortlist = [
        {"kind": "move", "target_id": "earthquake", "score": 100.0, "justification": "ok"},
    ]
    result = evaluate_candidate_tool("move", "earthquake", shortlist)
    assert result["found"] is True
    assert result["score"] == 100.0


def test_evaluate_candidate_tool_returns_miss() -> None:
    result = evaluate_candidate_tool("move", "absorb", [{"kind": "move", "target_id": "x"}])
    assert result["found"] is False


def test_propose_alternative_tool_compares_to_shortlist() -> None:
    shortlist = [{"kind": "move", "target_id": "x", "score": 50.0}]
    worse = propose_alternative_tool("move", "y", "no reason", shortlist, damage_estimate=20.0)
    assert worse["beats_shortlist"] is False
    better = propose_alternative_tool("move", "y", "good", shortlist, damage_estimate=80.0)
    assert better["beats_shortlist"] is True
    assert better["proposal_score"] == 80.0


__all__ = ["ToolCallRecord"]
