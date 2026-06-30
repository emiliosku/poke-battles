"""Model configuration loader.

Reads ``models.yaml`` (or any YAML file) and returns a mapping from logical
name to :class:`AgentConfig`. The same config is consumed by :class:`LLMClient`
to dial per-model parameters and routing.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml


class Tier(StrEnum):
    FREE = "free"
    PAID = "paid"
    LOCAL = "local"
    MOCK = "mock"


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """One model entry from ``models.yaml``."""

    name: str
    provider: str
    model_id: str
    tier: Tier = Tier.FREE
    temperature: float = 0.7
    max_tokens: int = 1024
    timeout_s: float = 30.0
    supports_tools: bool = True
    rate_limit_rpm: int | None = None
    daily_token_cap: int | None = None
    mode: str = "hybrid"
    notes: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature out of [0, 2]: {self.temperature}")
        # Mode=heuristic is a deterministic baseline; allow zero tokens/timeout.
        if self.mode != "heuristic":
            if self.max_tokens < 32:
                raise ValueError(f"max_tokens too low: {self.max_tokens}")
            if self.timeout_s < 1.0:
                raise ValueError(f"timeout_s too low: {self.timeout_s}")
        if self.mode not in {"legacy", "hybrid", "heuristic"}:
            raise ValueError(f"mode must be legacy/hybrid/heuristic, got {self.mode!r}")


_REQUIRED_KEYS = {"provider", "model_id"}


def load_models_yaml(path: str | Path) -> dict[str, AgentConfig]:
    """Load model configs from a YAML file.

    Expected format::

        model-name:
          provider: cerebras
          model_id: cerebras/llama3.1-8b
          tier: free
          temperature: 0.6
          max_tokens: 1024
          timeout_s: 30
          supports_tools: true
          rate_limit_rpm: 30
          notes: "Fast 8B model, good for random battles"
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"models.yaml at {path} must be a top-level mapping")
    out: dict[str, AgentConfig] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            raise ValueError(f"models.yaml: entry {name!r} must be a mapping")
        missing = _REQUIRED_KEYS - set(entry)
        if missing:
            raise ValueError(f"models.yaml: {name!r} missing keys: {sorted(missing)}")
        tier_str = str(entry.get("tier", "free")).lower()
        out[str(name)] = AgentConfig(
            name=str(name),
            provider=str(entry["provider"]),
            model_id=str(entry["model_id"]),
            tier=Tier(tier_str),
            temperature=float(entry.get("temperature", 0.7)),
            max_tokens=int(entry.get("max_tokens", 1024)),
            timeout_s=float(entry.get("timeout_s", 30.0)),
            supports_tools=bool(entry.get("supports_tools", True)),
            rate_limit_rpm=int(entry["rate_limit_rpm"]) if "rate_limit_rpm" in entry else None,
            daily_token_cap=int(entry["daily_token_cap"]) if "daily_token_cap" in entry else None,
            mode=str(entry.get("mode", "hybrid")),
            notes=str(entry.get("notes", "")),
        )
    return out


def example_yaml() -> str:
    """Return an example ``models.yaml`` block (suitable for free-tier keys)."""
    return """\
# models.yaml — agent model registry
# Each entry is a logical name. The matching env var for the provider
# (e.g. CEREBRAS_API_KEY) is required at request time.

# Cerebras (free)
cerebras/llama3.1-8b:
  provider: cerebras
  model_id: cerebras/llama3.1-8b
  tier: free
  rate_limit_rpm: 30

# OpenRouter (free)
openrouter/qwen3-72b:
  provider: openrouter
  model_id: openrouter/qwen/qwen3-72b-instruct:free
  tier: free

# Groq (free)
groq/llama-3.1-8b-instant:
  provider: groq
  model_id: groq/llama-3.1-8b-instant
  tier: free

# Mock for tests / offline development
mock/deterministic:
  provider: mock
  model_id: mock/deterministic
  tier: mock
  supports_tools: false
"""


def find_models_yaml() -> Path:
    """Look for ``models.yaml`` in cwd, then ``./config``, else return cwd/models.yaml."""
    for candidate in [Path("models.yaml"), Path("config/models.yaml")]:
        if candidate.exists():
            return candidate
    return Path("models.yaml")


__all__ = ["AgentConfig", "Tier", "example_yaml", "find_models_yaml", "load_models_yaml"]
_ = os
