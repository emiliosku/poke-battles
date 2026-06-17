# pokellm

LLM agent for Pokémon Showdown. Wraps LiteLLM (so it works with **any**
provider — OpenRouter, Cerebras, Groq, Mistral, OpenAI, Anthropic, Gemini,
HuggingFace, local Ollama) and adds:

- **Versioned prompts** (`prompts/system_v1.j2`, …) with Jinja2 templating
- **Tool-calling**: the model picks a move or switch by emitting a tool call
- **Reasoning tools**: `lookup_type_chart`, `estimate_damage`,
  `evaluate_switch` — small models can offload type math to deterministic code
- **Tiered memory**: per-battle short-term (last 20 actions) and cross-battle
  long-term (per-opponent model)
- **Tunable model config** (`models.yaml`): per-model `{provider, model_id,
  temperature, max_tokens, timeout_s, supports_tools, tier, rate_limit}`
- **Langfuse tracing** for observability (lazy no-op if no keys)

## Architecture

```
                ┌────────────────────────┐
battle_state ─→ │ StateFormatter (pure) │ ──→ prompt
                └────────────────────────┘
                                                  │
                ┌────────────────────────┐       │
  memory  ────→ │ LLMClient (litellm)    │ ←─────┘
                │ + retry + langfuse     │
                └───────────┬────────────┘
                            │ tool call
                ┌───────────▼────────────┐
                │ DecisionParser (pure) │ ──→ BattleOrder
                └────────────────────────┘
```

## Quickstart

```python
from pokellm import LLMAgent, AgentConfig

config = AgentConfig.from_yaml("models.yaml")["cerebras/llama3.1-8b"]
agent = LLMAgent(config=config)
# In your AgentPlayer:
await agent.choose_move(battle)
```

See `prompts/system_v1.j2` for the default system prompt and
`tests/unit/test_prompts.py` for the rendering tests.

## Free-tier providers (no credit card)

`models.example.yaml` ships with mappings for the providers that have free
quotas as of Q1 2026 (OpenRouter, Cerebras, Groq, Mistral, Google AI Studio,
HuggingFace). Just put the API key in `.env` and the matching provider is
picked automatically.
