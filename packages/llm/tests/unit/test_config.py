"""Unit tests for pokellm.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from pokellm.config import AgentConfig, Tier, example_yaml, load_models_yaml

SAMPLE_YAML = """\
cerebras/llama:
  provider: cerebras
  model_id: cerebras/llama3.1-8b
  tier: free
  temperature: 0.5
  max_tokens: 512
  rate_limit_rpm: 30
  notes: "small fast model"
openrouter/qwen:
  provider: openrouter
  model_id: openrouter/qwen-72b:free
mock/test:
  provider: mock
  model_id: mock/deterministic
  tier: mock
  supports_tools: false
"""


class TestAgentConfig:
    def test_required_fields(self) -> None:
        cfg = AgentConfig(name="x", provider="cerebras", model_id="cerebras/llama3.1-8b")
        assert cfg.name == "x"
        assert cfg.provider == "cerebras"
        assert cfg.tier == Tier.FREE
        assert cfg.temperature == 0.7
        assert cfg.supports_tools is True

    def test_invalid_temperature(self) -> None:
        with pytest.raises(ValueError, match="temperature"):
            AgentConfig(name="x", provider="p", model_id="m", temperature=2.5)

    def test_invalid_max_tokens(self) -> None:
        with pytest.raises(ValueError, match="max_tokens"):
            AgentConfig(name="x", provider="p", model_id="m", max_tokens=8)

    def test_invalid_timeout(self) -> None:
        with pytest.raises(ValueError, match="timeout_s"):
            AgentConfig(name="x", provider="p", model_id="m", timeout_s=0.1)

    def test_rate_limit_optional(self) -> None:
        cfg = AgentConfig(name="x", provider="p", model_id="m", rate_limit_rpm=60)
        assert cfg.rate_limit_rpm == 60


class TestLoadModelsYaml:
    def test_loads_minimal(self, tmp_path: Path) -> None:
        p = tmp_path / "models.yaml"
        p.write_text(SAMPLE_YAML)
        configs = load_models_yaml(p)
        assert "cerebras/llama" in configs
        assert "openrouter/qwen" in configs
        assert "mock/test" in configs
        assert configs["cerebras/llama"].provider == "cerebras"
        assert configs["cerebras/llama"].tier == Tier.FREE
        assert configs["cerebras/llama"].temperature == 0.5
        assert configs["cerebras/llama"].max_tokens == 512
        assert configs["cerebras/llama"].rate_limit_rpm == 30
        assert configs["mock/test"].supports_tools is False

    def test_missing_required_key(self, tmp_path: Path) -> None:
        p = tmp_path / "models.yaml"
        p.write_text("foo:\n  provider: x\n")
        with pytest.raises(ValueError, match="missing keys"):
            load_models_yaml(p)

    def test_invalid_yaml_root(self, tmp_path: Path) -> None:
        p = tmp_path / "models.yaml"
        p.write_text("- a\n- b\n")
        with pytest.raises(ValueError, match="top-level mapping"):
            load_models_yaml(p)

    def test_example_yaml(self) -> None:
        yaml = example_yaml()
        assert "cerebras" in yaml
        assert "openrouter" in yaml
        assert "groq" in yaml
