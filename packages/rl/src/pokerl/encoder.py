"""Battle state encoder: AbstractBattle → fixed-size numpy observation vector.

Encodes the full visible battle state into a flat float32 array suitable
for neural network input. No torch dependency — pure numpy.

Observation layout (360 floats total):
- Player side: 6 pokemon × 29 features = 174
- Opponent side: 6 pokemon × 29 features = 174
- Field state: 10 features
- Global state: 2 features

Per-pokemon features (29):
  [0]     hp_fraction (0.0–1.0)
  [1]     type1 index / NUM_TYPES (normalized 0–1)
  [2]     type2 index / NUM_TYPES (normalized 0–1, 0 if monotype)
  [3]     status index / NUM_STATUSES (normalized 0–1, 0 if healthy)
  [4]     is_active (0 or 1)
  [5]     is_fainted (0 or 1)
  [6:13]  boosts (atk, def, spa, spd, spe, accuracy, evasion) / 6
  [13:29] 4 moves × 4 features each:
           - base_power / 250
           - type index / NUM_TYPES
           - category index / NUM_CATEGORIES (0=phys, 1=spec, 2=status)
           - pp_fraction (pp / max_pp, or 0)
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

# ---------------------------------------------------------------------------
# Type / status / category lookup tables
# ---------------------------------------------------------------------------

TYPES: list[str] = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy", "typeless",
]
NUM_TYPES: int = len(TYPES)
_TYPE_INDEX: dict[str, int] = {t: i for i, t in enumerate(TYPES)}

STATUSES: list[str] = [
    "healthy", "brn", "frz", "par", "psn", "tox", "slp", "fnt",
]
NUM_STATUSES: int = len(STATUSES)
_STATUS_INDEX: dict[str, int] = {s: i for i, s in enumerate(STATUSES)}

CATEGORIES: list[str] = ["physical", "special", "status"]
NUM_CATEGORIES: int = len(CATEGORIES)
_CATEGORY_INDEX: dict[str, int] = {c: i for i, c in enumerate(CATEGORIES)}

WEATHERS: list[str] = ["none", "sunnyday", "raindance", "sandstorm", "snow", "hail"]
NUM_WEATHERS: int = len(WEATHERS)
_WEATHER_INDEX: dict[str, int] = {w: i for i, w in enumerate(WEATHERS)}

TERRAINS: list[str] = ["none", "electric", "grassy", "misty", "psychic"]
NUM_TERRAINS: int = len(TERRAINS)
_TERRAIN_INDEX: dict[str, int] = {t: i for i, t in enumerate(TERRAINS)}

# Sizes
_FEATURES_PER_MOVE: int = 4
_MOVES_PER_POKEMON: int = 4
_FEATURES_PER_POKEMON: int = 6 + 7 + _MOVES_PER_POKEMON * _FEATURES_PER_MOVE  # 29
_POKEMON_PER_SIDE: int = 6
_SIDE_SIZE: int = _POKEMON_PER_SIDE * _FEATURES_PER_POKEMON  # 174
_FIELD_SIZE: int = 10
_GLOBAL_SIZE: int = 2

OBSERVATION_SIZE: int = 2 * _SIDE_SIZE + _FIELD_SIZE + _GLOBAL_SIZE  # 360

# Boost stat names in canonical order
_BOOST_KEYS: list[str] = ["atk", "def", "spa", "spd", "spe", "accuracy", "evasion"]


def _type_idx(type_str: str | None) -> float:
    """Normalize a type string to [0, 1] index."""
    if type_str is None:
        return 0.0
    key = str(type_str).lower().replace(" ", "").split("(")[0].strip()
    # Handle poke-env enum repr like "Type.FIRE"
    if "." in key:
        key = key.split(".")[-1].lower()
    idx = _TYPE_INDEX.get(key, 0)
    return idx / max(NUM_TYPES - 1, 1)


def _status_idx(status: object | None) -> float:
    """Normalize a status to [0, 1] index."""
    if status is None:
        return 0.0
    key = str(status).lower().split(".")[-1].strip()
    idx = _STATUS_INDEX.get(key, 0)
    return idx / max(NUM_STATUSES - 1, 1)


def _category_idx(cat_str: str | None) -> float:
    """Normalize a category string to [0, 1] index."""
    if cat_str is None:
        return 2.0 / max(NUM_CATEGORIES - 1, 1)  # default to status
    key = str(cat_str).lower().split("(")[0].strip()
    if "." in key:
        key = key.split(".")[-1].lower()
    idx = _CATEGORY_INDEX.get(key, 2)
    return idx / max(NUM_CATEGORIES - 1, 1)


def _encode_pokemon_from_battle(mon: object | None, *, is_active: bool) -> npt.NDArray[np.float32]:
    """Encode a single poke-env Pokemon object into features."""
    features = np.zeros(_FEATURES_PER_POKEMON, dtype=np.float32)
    if mon is None:
        return features

    # HP fraction
    hp = getattr(mon, "current_hp_fraction", None)
    features[0] = float(hp) if hp is not None else 0.0

    # Types
    types_raw = getattr(mon, "types", None) or ()
    types_list = list(types_raw)
    features[1] = _type_idx(types_list[0] if len(types_list) > 0 else None)
    features[2] = _type_idx(types_list[1] if len(types_list) > 1 else None)

    # Status
    features[3] = _status_idx(getattr(mon, "status", None))

    # Flags
    features[4] = 1.0 if is_active else 0.0
    features[5] = 1.0 if getattr(mon, "fainted", False) else 0.0

    # Boosts (7 values, normalized to [-1, 1])
    boosts: dict[str, int] = getattr(mon, "boosts", {}) or {}
    for i, key in enumerate(_BOOST_KEYS):
        features[6 + i] = boosts.get(key, 0) / 6.0

    # Moves (up to 4)
    moves_dict: dict[str, object] = getattr(mon, "moves", {}) or {}
    moves_list = list(moves_dict.values())
    for m_idx in range(_MOVES_PER_POKEMON):
        base = 13 + m_idx * _FEATURES_PER_MOVE
        if m_idx < len(moves_list):
            mv = moves_list[m_idx]
            bp = int(getattr(mv, "base_power", 0) or 0)
            features[base] = bp / 250.0
            features[base + 1] = _type_idx(getattr(mv, "type", None))
            features[base + 2] = _category_idx(getattr(mv, "category", None))
            pp = int(getattr(mv, "current_pp", 0) or 0)
            max_pp = int(getattr(mv, "max_pp", 1) or 1)
            features[base + 3] = pp / max(max_pp, 1)

    return features


def _encode_side(
    team: dict[str, object] | None,
    active: object | None,
) -> npt.NDArray[np.float32]:
    """Encode one side (up to 6 pokemon) into a flat array."""
    side = np.zeros(_SIDE_SIZE, dtype=np.float32)
    if team is None:
        return side

    # Order: active first, then bench
    mons: list[object] = []
    seen: set[int] = set()
    if active is not None:
        mons.append(active)
        seen.add(id(active))
    for mon in team.values():
        if id(mon) not in seen:
            mons.append(mon)
            seen.add(id(mon))

    for i in range(min(len(mons), _POKEMON_PER_SIDE)):
        mon = mons[i]
        is_act = mon is active
        offset = i * _FEATURES_PER_POKEMON
        side[offset : offset + _FEATURES_PER_POKEMON] = _encode_pokemon_from_battle(
            mon, is_active=is_act
        )

    return side


def _encode_field(battle: object) -> npt.NDArray[np.float32]:
    """Encode field conditions into a fixed array."""
    field = np.zeros(_FIELD_SIZE, dtype=np.float32)

    # Weather (normalized index)
    weather_dict: dict[str, int] = getattr(battle, "weather", {}) or {}
    weather_key = next(iter(weather_dict), "none")
    weather_str = str(weather_key).lower().split(".")[-1].strip()
    field[0] = _WEATHER_INDEX.get(weather_str, 0) / max(NUM_WEATHERS - 1, 1)

    # Terrain
    fields_dict: dict[str, int] = getattr(battle, "fields", {}) or {}
    terrain_key = "none"
    for k in fields_dict:
        k_str = str(k).lower()
        if "terrain" in k_str:
            terrain_key = k_str.replace("_terrain", "").replace("terrain", "").strip()
            break
    field[1] = _TERRAIN_INDEX.get(terrain_key, 0) / max(NUM_TERRAINS - 1, 1)

    # Trick room
    field[2] = 1.0 if any("trick" in str(k).lower() for k in fields_dict) else 0.0

    # Player side conditions (hazards)
    player_sc: dict[str, int] = getattr(battle, "side_conditions", {}) or {}
    opp_sc: dict[str, int] = getattr(battle, "opponent_side_conditions", {}) or {}

    # Encode common hazards: spikes(0-3), stealth_rock(0-1), toxic_spikes(0-2), sticky_web(0-1)
    field[3] = _hazard_count(player_sc, "spikes") / 3.0
    field[4] = _hazard_count(player_sc, "stealth_rock") / 1.0
    field[5] = _hazard_count(player_sc, "toxic_spikes") / 2.0
    field[6] = _hazard_count(opp_sc, "spikes") / 3.0
    field[7] = _hazard_count(opp_sc, "stealth_rock") / 1.0
    field[8] = _hazard_count(opp_sc, "toxic_spikes") / 2.0
    # Sticky web (either side)
    field[9] = max(
        _hazard_count(player_sc, "sticky_web"),
        _hazard_count(opp_sc, "sticky_web"),
    )

    return field


def _hazard_count(conditions: dict[str, int], keyword: str) -> float:
    """Find a hazard count by keyword match in side conditions."""
    for k, v in conditions.items():
        if keyword in str(k).lower():
            return float(v)
    return 0.0


def encode_battle(battle: object) -> npt.NDArray[np.float32]:
    """Encode a poke-env AbstractBattle into a flat float32 observation vector.

    Parameters
    ----------
    battle:
        A poke-env ``AbstractBattle`` (or any object with the same attributes).

    Returns
    -------
    np.ndarray of shape (OBSERVATION_SIZE,) with dtype float32.
    All values are normalized to approximately [0, 1] or [-1, 1].
    """
    obs = np.zeros(OBSERVATION_SIZE, dtype=np.float32)

    # Player side
    player_team: dict[str, object] | None = getattr(battle, "team", None)
    player_active = getattr(battle, "active_pokemon", None)
    obs[0:_SIDE_SIZE] = _encode_side(player_team, player_active)

    # Opponent side
    opp_team: dict[str, object] | None = getattr(battle, "opponent_team", None)
    opp_active = getattr(battle, "opponent_active_pokemon", None)
    obs[_SIDE_SIZE : 2 * _SIDE_SIZE] = _encode_side(opp_team, opp_active)

    # Field
    field_offset = 2 * _SIDE_SIZE
    obs[field_offset : field_offset + _FIELD_SIZE] = _encode_field(battle)

    # Global
    global_offset = field_offset + _FIELD_SIZE
    turn = int(getattr(battle, "turn", 0) or 0)
    obs[global_offset] = min(turn / 100.0, 1.0)  # normalized turn count
    can_tera = getattr(battle, "can_tera", False)
    if callable(can_tera):
        can_tera = can_tera()
    obs[global_offset + 1] = 1.0 if can_tera else 0.0

    return obs
