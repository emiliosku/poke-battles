"""Read the canonical Showdown Pokédex shipped under
``packages/engine/server/dist/data/pokedex.js`` and expose a typed view
of it: every species's id, name, types, base stats, and abilities.

This is the same data the Showdown client uses for sprite layout, so the
``species_id`` we return is exactly the canonical lookup key — and a
good starting point for figuring out which sprite slug to hit on the
Showdown CDN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

# Resolve the pokedex.js file shipped with the engine package.
# This file lives in packages/core/src/pokecore/pokedex.py; the engine
# data is under packages/engine/server/dist/data/pokedex.js. Both
# packages sit under the same monorepo root (packages/), so go up to
# ``packages/`` and then across.
_DEFAULT_PATH = (
    Path(__file__).resolve().parents[3] / "engine" / "server" / "dist" / "data" / "pokedex.js"
)


@dataclass(frozen=True, slots=True)
class PokedexEntry:
    species_id: str
    name: str
    num: int
    types: tuple[str, ...]
    base_stats: dict[str, int]
    abilities: dict[str, str]


# Crude: the file is JS with `name:"Bulbasaur"` style key/value pairs.
# Avoid a real JS parser — just regex out the objects we need.
_FIELDS = ("name", "num", "types", "baseStats", "abilities")


def _parse_pokedex_js(content: str) -> dict[str, dict[str, Any]]:
    """Pull the top-level pokemon objects out of the pokedex.js bundle.

    The file uses ``__export``/``__toCommonJS`` boilerplate to wrap
    ``const Pokedex = { ... }``; we don't need the runtime, just the data.
    """
    body_match = re.search(r"const Pokedex = \{(.*?)\n\};", content, re.DOTALL)
    if body_match is None:
        return {}
    body = body_match.group(1)
    out: dict[str, dict[str, Any]] = {}
    pos = 0
    while pos < len(body):
        # Top-level keys are indented with 2 spaces and may be preceded
        # by a comma+newline (entries are separated by ``,\n  ``). Accept
        # both ``key: {`` and ``key:{`` styles.
        m = re.match(r"(?:,\s*)?\n  ([a-z0-9]+):\s*\{", body[pos:])
        if not m:
            # No more top-level entries.
            break
        key = m.group(1)
        # The match's end is the position right after the opening `{`.
        start = pos + m.end() - 1
        depth = 1
        i = start + 1
        while i < len(body) and depth > 0:
            if body[i] == "{":
                depth += 1
            elif body[i] == "}":
                depth -= 1
            i += 1
        block = body[start + 1 : i - 1]
        entry: dict[str, Any] = {}
        # ``name: "Bulbasaur"`` (string literal in JS).
        m = re.search(r'name:\s*"([^"]*)"', block)
        if m:
            entry["name"] = m.group(1)
        # ``num: 6`` (integer literal).
        m = re.search(r"\bnum:\s*(-?\d+)", block)
        if m:
            entry["num"] = int(m.group(1))
        # ``types: ["Fire", "Flying"]`` (array of strings).
        m = re.search(r"types:\s*\[([^\]]*)\]", block)
        if m:
            entry["types"] = tuple(re.findall(r'"([^"]+)"', m.group(1)))
        # ``baseStats: { hp: 45, atk: 49, ... }`` (object with unquoted keys).
        m = re.search(r"baseStats:\s*\{([^}]*)\}", block)
        if m:
            entry["base_stats"] = {
                k: int(v) for k, v in re.findall(r"(\w+):\s*(-?\d+)", m.group(1))
            }
        # ``abilities: { 0: "Overgrow", H: "Chlorophyll" }`` (mixed keys).
        m = re.search(r"abilities:\s*\{([^}]*)\}", block)
        if m:
            entry["abilities"] = dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", m.group(1)))
        out[key] = entry
        pos = i
    return out


@lru_cache(maxsize=1)
def load_pokedex(path: str | Path | None = None) -> tuple[PokedexEntry, ...]:
    """Return every Pokémon in the bundled Showdown Pokédex, in nat. dex order."""
    target = Path(path) if path else _DEFAULT_PATH
    if not target.exists():
        return ()
    content = target.read_text(encoding="utf-8")
    raw = _parse_pokedex_js(content)
    out: list[PokedexEntry] = []
    for sid, entry in raw.items():
        if not entry.get("name") or "num" not in entry:
            continue
        out.append(
            PokedexEntry(
                species_id=sid,
                name=entry["name"],
                num=entry["num"],
                types=entry.get("types", ()),
                base_stats=entry.get("base_stats", {}),
                abilities=entry.get("abilities", {}),
            )
        )
    out.sort(key=lambda e: e.num)
    return tuple(out)


def species_ids() -> tuple[str, ...]:
    """All canonical species ids in the bundled Showdown Pokédex."""
    return tuple(e.species_id for e in load_pokedex())


def get(species_id: str) -> PokedexEntry | None:
    """Look up an entry by its canonical species id."""
    for entry in load_pokedex():
        if entry.species_id == species_id:
            return entry
    return None


__all__ = [
    "PokedexEntry",
    "get",
    "load_pokedex",
    "species_ids",
]
