# pokecli

Command-line client for the poke-battles API.

```bash
# Install (from project root, after `uv sync`)
uv pip install -e pokecli

# Set the API URL
export POKECLI_API=https://poke-battles.example.com

# Use
pokecli health
pokecli teams list
pokecli teams add "My team" --paste @team.txt --owner alice
pokecli battles create random random
pokecli battles watch battle-12345
pokecli sims run round-robin --team 1 --models random,random --n 50
pokecli leaderboard
```

All commands accept `--api <url>` to override the base URL.

## Subcommand tree

```
pokecli
├── health                          # GET /health
├── teams
│   ├── list   [--owner X] [--json]
│   ├── add    NAME --paste [@file|str] [--owner X] [--format F] [--public]
│   ├── show   ID
│   └── delete ID
├── battles
│   ├── create MODEL1 MODEL2 [--format F] [--user1 U] [--user2 U] [--team1 N] [--team2 N] [--no-watch]
│   ├── show   BATTLE_ID [--wait] [--timeout S] [--json]
│   └── watch  BATTLE_ID                 # live WS event stream
├── sims
│   ├── run    MODE (round_robin|team_vs_team) [--models m1,m2] [--n N] [--team-a ID] [--team-b ID]
│   └── show   SIM_ID [--wait] [--timeout S]
├── leaderboard  [--format F] [--limit N] [--json]
├── replay   BATTLE_ID
└── api      PATH                       # raw GET, useful for debugging
```

## Examples

```bash
# Health
pokecli health

# Teams
pokecli teams add "Hyper Offense" --paste @team.txt --owner alice
pokecli teams list
pokecli teams show 1
pokecli teams delete 1

# Battles
pokecli battles create cerebras/llama3.1-8b cerebras/llama3.1-8b
pokecli battles watch battle-1781723743919   # streams live events

# Simulations (round-robin across models)
pokecli sims run round-robin --team 1 --models cerebras/llama3.1-8b,cerebras/gpt-oss-120b,groq/llama-3.1-8b-instant --n 20
pokecli sims show sim-abcdef

# Leaderboard
pokecli leaderboard --format gen9ou --limit 10

# Replay (after a battle finishes)
pokecli replay battle-1781723743919
```
