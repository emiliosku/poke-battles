# pokecore

Pure-Python core for the **poke-battles** project. Zero I/O dependencies. Safe to
import anywhere in the workspace.

## What's inside

- **`types`** — enums and dataclasses: `Type`, `Stat`, `Nature`, `Status`,
  `Category`, `Generation`, `Boosts`, `NatureModifier`, `TypePair`
- **`type_chart`** — 18×18 effectiveness matrix; helpers for damage calc and
  coverage analysis
- **`teams`** — Showdown paste parser and serializer (`parse_team`,
  `format_team`); pluggable `TypeResolver` for species→types
- **`formats`** — battle formats (`gen9randombattle`, `gen9ou`, …)
- **`elo`** — Glicko-2 rating system with rating-deviation and volatility

## Usage

```python
from pokecore import parse_team, Type, TypePair, defensive_multiplier

# Parse a Showdown paste
team = parse_team(paste, type_resolver=lambda sid: pokedex[sid])

# Calculate a hit
garchomp = team.pokemon[0]
multiplier = defensive_multiplier(garchomp.types, Type.ICE)
```

## Development

```bash
make typecheck   # mypy --strict
make lint        # ruff
make test-cov    # pytest with coverage (>=80% required)
```
