"""Showdown paste parser.

Parses Pokémon Showdown team-paste format into structured :class:`Team` objects.
Reverse serialization is also supported for storage round-trips.

Type resolution is pluggable: pass a ``type_resolver`` callable that maps
``species_id`` (lowercased, no spaces) to a :class:`TypePair`. When no resolver
is supplied, all Pokémon default to :class:`Type.NORMAL` — type information is
filled in by a later pipeline that consumes Smogon's ``pokedex.json``.

Re-exported from :mod:`pokecore`.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeVar

from pokecore.types import Nature, NatureModifier, Stat, Type, TypePair

T = TypeVar("T")

STAT_ALIASES: MappingProxyType[str, Stat] = MappingProxyType(
    {
        "hp": Stat.HP,
        "atk": Stat.ATTACK,
        "atks": Stat.ATTACK,
        "attack": Stat.ATTACK,
        "def": Stat.DEFENSE,
        "defense": Stat.DEFENSE,
        "spa": Stat.SPECIAL_ATTACK,
        "spatk": Stat.SPECIAL_ATTACK,
        "spattack": Stat.SPECIAL_ATTACK,
        "specialattack": Stat.SPECIAL_ATTACK,
        "spc": Stat.SPECIAL_ATTACK,
        "spd": Stat.SPECIAL_DEFENSE,
        "spdef": Stat.SPECIAL_DEFENSE,
        "spdefense": Stat.SPECIAL_DEFENSE,
        "specialdefense": Stat.SPECIAL_DEFENSE,
        "spe": Stat.SPEED,
        "speed": Stat.SPEED,
    }
)

NATURE_ALIASES: MappingProxyType[str, Nature] = MappingProxyType({n.value: n for n in Nature})

TYPE_ALIASES: MappingProxyType[str, Type] = MappingProxyType({t.value: t for t in Type})

ALL_STATS: tuple[Stat, ...] = (
    Stat.HP,
    Stat.ATTACK,
    Stat.DEFENSE,
    Stat.SPECIAL_ATTACK,
    Stat.SPECIAL_DEFENSE,
    Stat.SPEED,
)

TypeResolver = Callable[[str], TypePair]


@dataclass(frozen=True, slots=True)
class EVSpread:
    """Effort values, 0..252 per stat, total <= 510."""

    values: MappingProxyType[Stat, int]
    total: int

    @classmethod
    def zero(cls) -> EVSpread:
        return cls(MappingProxyType(dict.fromkeys(ALL_STATS, 0)), 0)

    @classmethod
    def parse(cls, raw: str) -> EVSpread:
        cleaned = raw.strip()
        if not cleaned:
            return cls.zero()
        pairs = _split_pairs(cleaned)
        values: dict[Stat, int] = dict.fromkeys(ALL_STATS, 0)
        for stat_token, value_token in pairs:
            stat = _lookup(STAT_ALIASES, stat_token)
            if stat is None:
                raise ValueError(f"Unknown stat in EV spread: {stat_token!r}")
            value = int(value_token)
            if not 0 <= value <= 252:
                raise ValueError(f"EV value {value} out of range [0, 252]")
            if value != 1 and value % 4 != 0:
                raise ValueError(f"EV value {value} must be divisible by 4")
            values[stat] = value
        total = sum(values.values())
        if total > 510:
            raise ValueError(f"EV total {total} exceeds 510")
        return cls(MappingProxyType(values), total)


@dataclass(frozen=True, slots=True)
class IVSpread:
    """Individual values, 0..31 per stat (default 31)."""

    values: MappingProxyType[Stat, int]

    @classmethod
    def default(cls) -> IVSpread:
        return cls(MappingProxyType(dict.fromkeys(ALL_STATS, 31)))

    @classmethod
    def parse(cls, raw: str) -> IVSpread:
        cleaned = raw.strip()
        if not cleaned:
            return cls.default()
        pairs = _split_pairs(cleaned)
        values: dict[Stat, int] = dict.fromkeys(ALL_STATS, 31)
        for stat_token, value_token in pairs:
            stat = _lookup(STAT_ALIASES, stat_token)
            if stat is None:
                raise ValueError(f"Unknown stat in IV spread: {stat_token!r}")
            value = int(value_token)
            if not 0 <= value <= 31:
                raise ValueError(f"IV value {value} out of range [0, 31]")
            values[stat] = value
        return cls(MappingProxyType(values))


@dataclass(frozen=True, slots=True)
class MoveSlot:
    name: str
    pp: int | None = None


@dataclass(frozen=True, slots=True)
class PokemonSet:
    nickname: str | None
    species: str
    species_id: str
    types: TypePair
    item: str | None
    ability: str
    level: int
    shiny: bool
    happiness: int | None
    nature: Nature
    nature_modifier: NatureModifier
    tera_type: Type | None
    evs: EVSpread
    ivs: IVSpread
    moves: tuple[MoveSlot, ...]

    def __post_init__(self) -> None:
        if not 1 <= self.level <= 100:
            raise ValueError(f"Level {self.level} out of range [1, 100]")
        if not 0 <= len(self.moves) <= 4:
            raise ValueError(f"Move count {len(self.moves)} out of range [0, 4]")


@dataclass(frozen=True, slots=True)
class Team:
    name: str | None
    pokemon: tuple[PokemonSet, ...]
    format: str | None

    def __post_init__(self) -> None:
        if not 1 <= len(self.pokemon) <= 6:
            raise ValueError(f"Team size {len(self.pokemon)} out of range [1, 6]")
        duplicates = [
            sid for sid, count in Counter(p.species_id for p in self.pokemon).items() if count > 1
        ]
        if duplicates:
            raise ValueError(f"Duplicate species in team: {duplicates}")

    def species_ids(self) -> Iterable[str]:
        return (p.species_id for p in self.pokemon)


_TRAILING_PAIR = re.compile(r"(\d+)\s+([A-Za-z][A-Za-z ]*?)\s*$")
_NATURE_TRAILING = re.compile(r"\b([A-Za-z]+)\s+Nature\s*$")
_NATURE_LEADING = re.compile(r"^([A-Za-z]+)\s+Nature\s*$")
_TERA_PATTERN = re.compile(r"^Tera Type:\s*(.+)$", re.IGNORECASE)


def _lookup(mapping: MappingProxyType[str, T], key: str) -> T | None:
    normalized = key.strip().lower()
    return mapping.get(normalized) or mapping.get(normalized.replace(" ", ""))


def _split_pairs(raw: str) -> list[tuple[str, str]]:
    text = raw.strip()
    pairs: list[tuple[str, str]] = []
    for chunk in text.split("/"):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = _TRAILING_PAIR.search(chunk)
        if not m:
            raise ValueError(f"Could not parse stat pair: {chunk!r}")
        value = m.group(1)
        stat = m.group(2).strip()
        pairs.append((stat, value))
    return pairs


def _normalize_species_id(species: str) -> str:
    return re.sub(r"[^a-z0-9]", "", species.lower())


# Most forms follow the ``{base}-{form}`` slug convention, but a handful
# of species' Showdown CDN slugs diverge from the standard transform:
#
# * Some form names are concatenated, not dash-separated, by the CDN
#   (``Basculin-Blue-Striped`` → ``basculin-bluestriped``, not
#   ``basculin-blue-striped``; ``Toxtricity-Low-Key`` → ``toxtricity-lowkey``).
# * A few forms don't get their own sprite and reuse the base form's art
#   (``Darmanitan-Galar-Zen`` reuses ``darmanitan-galar``;
#   ``Dudunsparce-Three-Segment`` reuses ``dudunsparce``).
# * A few forms were renamed to a different species entirely in the
#   games: Galarian Farfetch'd is the evolution Sirfetch'd, so its
#   slug is just ``sirfetchd``; Galarian Mr. Mime shares ``mrmime``'s
#   art.
# * Oricorio's Pom-Pom form uses the Hawaiian bird name
#   ``oricorio-pau``, not ``oricorio-pompom``.
# * Ogerpon's Tera-typed masks drop the ``-tera`` suffix on the CDN.
# * Tauros's three Paldean breeds share a single ``tauros-paldea`` sprite.
#
# The keys are the *standard* slug (what the NFKD + dash transform
# would produce); the values are the actual CDN slug.
_CDN_SLUG_OVERRIDES: dict[str, str] = {
    "basculin-blue-striped": "basculin-bluestriped",
    "basculin-white-striped": "basculin-whitestriped",
    "darmanitan-galar-zen": "darmanitan-galar",
    "dudunsparce-three-segment": "dudunsparce",
    "farfetchd-galar": "sirfetchd",
    "mr-mime-galar": "mrmime",
    "necrozma-dawn-wings": "necrozma-dawnwings",
    "necrozma-dusk-mane": "necrozma-duskmane",
    "ogerpon-cornerstone-tera": "ogerpon-cornerstone",
    "ogerpon-hearthflame-tera": "ogerpon-hearthflame",
    "ogerpon-teal-tera": "ogerpon-teal",
    "ogerpon-wellspring-tera": "ogerpon-wellspring",
    "oricorio-pom-pom": "oricorio-pau",
    "pichu-spiky-eared": "pichu-spikyeared",
    "pikachu-rock-star": "pikachu-rockstar",
    "toxtricity-low-key": "toxtricity-lowkey",
    "toxtricity-low-key-gmax": "toxtricity-lowkey",
    "urshifu-rapid-strike": "urshifu-rapidstrike",
    "urshifu-rapid-strike-gmax": "urshifu-rapidstrike",
    "tauros-paldea-aqua": "tauros-paldea",
    "tauros-paldea-blaze": "tauros-paldea",
    "tauros-paldea-combat": "tauros-paldea",
}


def sprite_id(species: str) -> str:
    """Return the slug the Pokémon Showdown CDN uses for sprite URLs.

    Showdown's CDN serves sprites at
    ``https://play.pokemonshowdown.com/sprites/{folder}/{sprite_id}.{ext}``,
    where ``sprite_id`` lowercases the species name, keeps the dashes that
    distinguish forms (``Charizard-Mega-X`` → ``charizard-megax``,
    ``Slowking-Galar`` → ``slowking-galar``), strips any non-alphanumeric
    noise such as dots and apostrophes (``Mr. Mime`` → ``mr-mime``,
    ``Farfetch'd`` → ``farfetchd``), and folds accented characters to their
    ASCII base (``Flabébé`` → ``flabebe``).

    Mega X / Mega Y (and only those) are special-cased: the trailing single
    letter is merged with the ``mega`` token so the slug matches what the
    CDN actually serves (``charizard-mega-x`` → ``charizard-megax``). Every
    other multi-letter form keeps the dash (``kyurem-black`` →
    ``kyurem-black``).

    A small set of species diverge from the standard transform
    (concatenated form names, base-form sprite reuse, Showdown renames).
    Those are handled by :data:`_CDN_SLUG_OVERRIDES`, checked after the
    standard transform.

    This is deliberately different from :func:`_normalize_species_id`,
    which the rest of the engine uses as a flat lookup key (no dashes).
    """
    import unicodedata

    # Fold accented characters down to ASCII base first so that
    # ``Flabébé`` → ``flabebe`` rather than dropping the trailing ``e``.
    folded = unicodedata.normalize("NFKD", species).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9-]", "", folded.lower().replace(" ", "-"))
    # The CDN serves Mega X / Mega Y as charizard-megax, not
    # charizard-mega-x. Don't merge other single-letter forms.
    slug = re.sub(r"-mega-([xy])$", r"-mega\1", slug)
    # Apply per-species overrides for the few forms whose CDN slug
    # diverges from the standard transform.
    return _CDN_SLUG_OVERRIDES.get(slug, slug)


def _parse_header(line: str) -> tuple[str | None, str, str | None]:
    text = line.strip()
    item: str | None = None
    if "@" in text:
        text, item_part = text.rsplit("@", 1)
        item = item_part.strip()
        text = text.strip()
    nickname: str | None = None
    species = text
    paren = re.search(r"\(([^)]+)\)\s*$", text)
    if paren:
        inner = paren.group(1).strip()
        head = text[: paren.start()].strip()
        if _normalize_species_id(inner) != _normalize_species_id(head):
            nickname = head
            species = inner
    return nickname, species, item


_GENDER_SUFFIX_RE = re.compile(r"\s*\((M|F)\)\s*$")
_TRAILING_PARENS_RE = re.compile(r"\(([^)]+)\)\s*$")


def _normalize_header_for_showdown(line: str) -> str:
    """Wrap a Pokémon header so poke-env's ``from_showdown`` parser
    correctly populates both ``mon.nickname`` and ``mon.species``.

    poke-env 0.15.0's :class:`TeambuilderPokemon.from_showdown` only sets
    ``mon.species`` when the header has the ``Nickname (Species) @ Item``
    form. For a plain ``Species @ Item`` header, the species field on the
    parsed object is left as ``None``. The packed team sent over the wire
    then has an empty species field (``Species||item|...``), and the
    client-side :class:`Pokemon` falls back to the base species for its
    display name — ``Typhlosion-Hisui`` renders as ``Typhlosion``,
    ``Slowking-Galar`` as ``Slowking``, ``Oricorio-Pom-Pom`` as
    ``Oricorio``, and so on. The bug also breaks sprite URLs and the
    LLM's switch-matcher equality check (which compares the id-form
    species against the LLM's display name).

    Showdown's own ``Teams.unpack`` happens to recover the species from
    the nickname via ``set.species = unpackName("") || set.name``, so the
    server-side battle runs with the correct form — only the client-side
    observers are degraded.

    This helper rewrites the header into ``Nickname (Species) @ Item``
    form (using the species as its own nickname) when no such parens
    are present, leaving nicknames, gender markers, and items untouched
    in every other case. The transform is idempotent.
    """
    text = line.rstrip()
    item: str | None = None
    if " @ " in text:
        text, item_part = text.rsplit(" @ ", 1)
        item = item_part.strip()
        text = text.rstrip()
    gender: str | None = None
    gender_match = _GENDER_SUFFIX_RE.search(text)
    if gender_match:
        gender = gender_match.group(1)
        text = text[: gender_match.start()].rstrip()
    if not _TRAILING_PARENS_RE.search(text):
        text = f"{text} ({text})"
    parts = [text]
    if gender:
        parts.append(f"({gender})")
    result = " ".join(parts)
    if item:
        result = f"{result} @ {item}"
    return result


def normalize_team_paste_for_showdown(paste: str | None) -> str | None:
    """Normalize a Showdown team paste for poke-env's teambuilder parser.

    Wraps each Pokémon header's species in ``(Species)`` form so that
    poke-env's :class:`TeambuilderPokemon.from_showdown` correctly sets
    the ``mon.species`` field for variant forms (regional forms like
    ``-Hisui``/``-Galar``/``-Alola``/``-Paldea``, special forms like
    ``-Mega``/``-Mega-X``/``-Mega-Y``/``-Pom-Pom``/``-Rapid-Strike``,
    etc.). See :func:`_normalize_header_for_showdown` for the full
    rationale.

    Blank lines, ``=== team name ===`` headers, and ``// comment`` lines
    are preserved as-is. The transform is idempotent.

    Returns ``None`` unchanged. Returns the input string unchanged when
    it contains no Pokémon headers (e.g. empty string or only blanks).
    The output uses ``\\n`` as the line separator.
    """
    if paste is None or not paste.strip():
        return paste
    out_lines: list[str] = []
    expecting_header = True
    for raw in paste.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            out_lines.append(line)
            expecting_header = True
            continue
        if stripped.startswith("===") and stripped.endswith("==="):
            out_lines.append(line)
            expecting_header = True
            continue
        if stripped.startswith("//"):
            out_lines.append(line)
            expecting_header = True
            continue
        if expecting_header:
            out_lines.append(_normalize_header_for_showdown(line))
            expecting_header = False
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def _parse_pokemon_block(
    block: Sequence[str],
    type_resolver: TypeResolver | None = None,
) -> PokemonSet:
    if not block:
        raise ValueError("Empty Pokémon block")
    nickname, species, item = _parse_header(block[0])
    species_id = _normalize_species_id(species)
    ability: str | None = None
    level = 100
    shiny = False
    happiness: int | None = None
    nature: Nature | None = None
    tera_type: Type | None = None
    evs = EVSpread.zero()
    ivs = IVSpread.default()
    moves: list[MoveSlot] = []

    for raw in block[1:]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Ability:"):
            ability = line[len("Ability:") :].strip()
            continue
        if line.startswith("Level:"):
            level = int(line[len("Level:") :].strip())
            continue
        if line.startswith("Shiny:"):
            shiny = line[len("Shiny:") :].strip().lower() in {"yes", "true", "y"}
            continue
        if line.startswith("Happiness:"):
            happiness = int(line[len("Happiness:") :].strip())
            continue
        if line.startswith("EVs:"):
            evs = EVSpread.parse(line[len("EVs:") :].strip())
            continue
        if line.startswith("IVs:"):
            ivs = IVSpread.parse(line[len("IVs:") :].strip())
            continue
        tera_match = _TERA_PATTERN.match(line)
        if tera_match:
            tera_name = tera_match.group(1).strip()
            tera_type = _lookup(TYPE_ALIASES, tera_name)
            if tera_type is None:
                raise ValueError(f"Unknown tera type: {tera_name!r}")
            continue
        if line.startswith("-"):
            move_text = line.lstrip("-").strip()
            pp: int | None = None
            if "/" in move_text:
                name_part, pp_part = move_text.split("/", 1)
                try:
                    pp = int(pp_part.strip())
                    move_text = name_part.strip()
                except ValueError:
                    pass
            moves.append(MoveSlot(name=move_text, pp=pp))
            continue
        nat_match = _NATURE_TRAILING.search(line)
        if nat_match:
            nature = _parse_nature_token(nat_match.group(1))
            continue
        nat_lead = _NATURE_LEADING.match(line)
        if nat_lead:
            nature = _parse_nature_token(nat_lead.group(1))
            continue

    if ability is None:
        raise ValueError(f"Pokémon {species!r} is missing Ability")
    if nature is None:
        raise ValueError(f"Pokémon {species!r} is missing Nature")
    types = type_resolver(species_id) if type_resolver is not None else TypePair(Type.NORMAL)
    return PokemonSet(
        nickname=nickname,
        species=species,
        species_id=species_id,
        types=types,
        item=item,
        ability=ability,
        level=level,
        shiny=shiny,
        happiness=happiness,
        nature=nature,
        nature_modifier=NatureModifier.from_nature(nature),
        tera_type=tera_type,
        evs=evs,
        ivs=ivs,
        moves=tuple(moves),
    )


def _parse_nature_token(token: str) -> Nature:
    nature = _lookup(NATURE_ALIASES, token)
    if nature is None:
        raise ValueError(f"Unknown nature: {token!r}")
    return nature


def parse_team(
    paste: str,
    *,
    type_resolver: TypeResolver | None = None,
    name: str | None = None,
    format: str | None = None,
) -> Team:
    """Parse a full Showdown team paste."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in paste.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append(current)
                current = []
            continue
        if stripped.startswith("===") and stripped.endswith("==="):
            continue
        if stripped.startswith("//"):
            continue
        current.append(line)
    if current:
        blocks.append(current)
    if not blocks:
        raise ValueError("Empty team paste")
    parsed = [_parse_pokemon_block(b, type_resolver) for b in blocks]
    return Team(name=name, pokemon=tuple(parsed), format=format)


def format_team(team: Team) -> str:
    """Serialize a team back to Showdown paste format."""
    out: list[str] = []
    if team.name:
        out.append(f"=== {team.name} ===")
    for pkmn in team.pokemon:
        header = pkmn.species
        if pkmn.nickname and pkmn.nickname != pkmn.species:
            header = f"{pkmn.nickname} ({pkmn.species})"
        if pkmn.item:
            header += f" @ {pkmn.item}"
        out.append(header)
        if pkmn.ability:
            out.append(f"Ability: {pkmn.ability}")
        if pkmn.level != 100:
            out.append(f"Level: {pkmn.level}")
        if pkmn.shiny:
            out.append("Shiny: Yes")
        if pkmn.happiness is not None:
            out.append(f"Happiness: {pkmn.happiness}")
        if pkmn.tera_type is not None:
            out.append(f"Tera Type: {pkmn.tera_type.value}")
        ev_parts = [
            f"{pkmn.evs.values[s]} {s.value.upper()}" for s in ALL_STATS if pkmn.evs.values[s] > 0
        ]
        if ev_parts:
            out.append("EVs: " + " / ".join(ev_parts))
        iv_parts = [
            f"{pkmn.ivs.values[s]} {s.value.upper()}" for s in ALL_STATS if pkmn.ivs.values[s] != 31
        ]
        if iv_parts:
            out.append("IVs: " + " / ".join(iv_parts))
        out.append(f"{pkmn.nature.value.capitalize()} Nature")
        for move in pkmn.moves:
            suffix = f" /{move.pp}" if move.pp is not None else ""
            out.append(f"- {move.name}{suffix}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"
