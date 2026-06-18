"""Smogon data loader for format validation.

Extracts species, moves, and abilities from the Showdown server's TypeScript
data files. Falls back gracefully if the server directory is not available.

Re-exported from :mod:`pokeengine`.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SPECIES: set[str] = set()
_MOVES: set[str] = set()
_ABILITIES: set[str] = set()
_ITEMS: set[str] = set()
_LOADED = False


def _load_data(server_dir: str = "server") -> None:
    global _SPECIES, _MOVES, _ABILITIES, _ITEMS, _LOADED
    if _LOADED:
        return

    base = Path(server_dir) / "server" / "data"
    if not base.exists():
        logger.warning("Showdown data dir not found at %s; skipping Smogon data load", base)
        _LOADED = True
        return

    _SPECIES = _extract_keys(base / "pokedex.ts")
    _MOVES = _extract_keys(base / "moves.ts")
    _ABILITIES = _extract_keys(base / "abilities.ts")
    _ITEMS = _extract_keys(base / "items.ts")
    _LOADED = True
    logger.info(
        "Loaded Smogon data: %d species, %d moves, %d abilities, %d items",
        len(_SPECIES),
        len(_MOVES),
        len(_ABILITIES),
        len(_ITEMS),
    )


def _extract_keys(path: Path) -> set[str]:
    """Extract top-level exported keys from a Showdown TypeScript data file."""
    if not path.exists():
        logger.warning("Data file not found: %s", path)
        return set()
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^\s*exports\.(\w+)\s*[:=]\s*", re.MULTILINE)
    return {m.group(1).lower() for m in pattern.finditer(text)}


def valid_species(name: str) -> bool:
    if not _LOADED:
        _load_data()
    return name.lower() in _SPECIES if _SPECIES else True


def valid_move(name: str) -> bool:
    if not _LOADED:
        _load_data()
    return name.lower().replace(" ", "").replace("-", "") in _MOVES if _MOVES else True


def valid_ability(name: str) -> bool:
    if not _LOADED:
        _load_data()
    return name.lower().replace(" ", "").replace("-", "") in _ABILITIES if _ABILITIES else True


def valid_item(name: str) -> bool:
    if not _LOADED:
        _load_data()
    return name.lower().replace(" ", "").replace("-", "") in _ITEMS if _ITEMS else True


def get_species_data(server_dir: str = "server") -> dict[str, Any]:
    """Return a dict of species data for use by other modules."""
    if not _LOADED:
        _load_data(server_dir)
    return {
        "species": _SPECIES,
        "moves": _MOVES,
        "abilities": _ABILITIES,
        "items": _ITEMS,
        "loaded": _LOADED,
    }


__all__ = [
    "valid_species",
    "valid_move",
    "valid_ability",
    "valid_item",
    "get_species_data",
]
