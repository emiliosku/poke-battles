# Engine

End-to-end poke-env + Showdown protocol + event normalization.

## Quickstart

```bash
# Install
uv pip install -e packages/core -e "packages/engine[dev]"

# Clone the Showdown server (one-time, ~50 MB)
uv run python -c "from pokeengine.runner import ensure_showdown; ensure_showdown('server')"

# Run a battle end-to-end
uv run python -m pokeengine.demo --port 8000
```

The demo:

1. Spawns a local Pokémon Showdown server on `ws://localhost:8000`
2. Creates two `AgentPlayer`s using the random move chooser
3. Runs one `gen9randombattle`
4. Reports the winner, turn count, and captured event counts
5. Tears down the server

## Container deployment (OCI ARM)

A baked image is available in `../showdown/Dockerfile`. The Phase 4 orchestrator
will pull it from OCI Container Registry and spawn one container per battle
(or per match in a simulation/tournament).

## Module layout

- `pokeengine.events` — `Event` / `EventKind` / `BattleResult` (normalized event types)
- `pokeengine.parser` — `parse_line` / `parse_stream` (Showdown protocol → events)
- `pokeengine.player` — `AgentPlayer(Player)` wraps poke-env and captures events
- `pokeengine.format_validator` — `validate_team(team, fmt, known_species?)`
- `pokeengine.runner` — `start_showdown` / `showdown_server` / `ensure_showdown`
- `pokeengine.demo` — CLI demo
- `pokeengine.smoke` — Smoke test (RandomPlayer vs AgentPlayer)

## Smoke test

```bash
uv run python -m pokeengine.smoke
```

If a battle completes in <30s and reports `player won: True/False`, your local
Showdown is reachable and the agent is correctly choosing moves.
