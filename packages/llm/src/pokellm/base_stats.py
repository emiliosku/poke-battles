"""A small inline base-stats table for the heuristic agent.

The :mod:`pokecore.pokedex` data ships with the engine image but is not
bundled at the static-analysis layer (the engine's ``dist/data/pokedex.js``
is gitignored). To keep the heuristic usable without that file, we ship a
focused table of the ~120 most common Gen 9 random-battle / OU mons. For
species not in the table the heuristic falls back to ``base=100`` for every
stat, which is the same as not knowing the species at all.

Each entry maps ``species_id`` (the canonical Showdown id, lowercase, no
spaces) to a base-stats dict using the same keys Showdown uses:
``hp, atk, def, spa, spd, spe``. The list is hand-curated and intentionally
small — adding more is a PR away.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

# Each tuple has the shape: (base_atk, base_def, base_spa, base_spd, base_hp, base_spe)
_BASE_STATS: dict[str, tuple[int, int, int, int, int, int]] = {
    # Starters and pseudo-legendaries
    "garchomp": (130, 120, 80, 95, 108, 130),
    "dragonite": (134, 95, 100, 100, 121, 80),
    "salamence": (135, 80, 110, 110, 120, 100),
    "tyranitar": (134, 110, 95, 100, 120, 61),
    "metagross": (135, 130, 95, 90, 120, 70),
    "hydreigon": (105, 90, 125, 90, 92, 98),
    "volcarona": (60, 65, 135, 105, 85, 100),
    "ferrothorn": (94, 131, 54, 116, 89, 20),
    "blaziken": (120, 70, 110, 70, 80, 100),
    "swampert": (110, 90, 85, 90, 100, 50),
    "feraligatr": (105, 100, 79, 83, 85, 78),
    "golisopod": (125, 140, 60, 85, 125, 40),
    "tornadustherian": (100, 100, 100, 121, 79, 70),
    "landorustherian": (145, 107, 99, 71, 91, 91),
    "magnezone": (95, 130, 120, 70, 90, 60),
    "rotomwash": (65, 107, 105, 70, 86, 60),
    "rotomheat": (65, 107, 105, 70, 86, 60),
    # Common OU mons
    "heatran": (91, 106, 130, 106, 91, 50),
    "pikachu": (55, 40, 50, 50, 35, 90),
    "charizard": (84, 78, 109, 85, 78, 100),
    "blastoise": (83, 100, 85, 105, 79, 78),
    "venusaur": (82, 83, 100, 100, 80, 80),
    "kingambit": (135, 120, 60, 95, 100, 50),
    "ironvaliant": (119, 59, 131, 69, 59, 116),
    "ironmoth": (118, 70, 126, 80, 70, 108),
    "ironbundle": (124, 80, 132, 70, 56, 133),
    "ironhands": (140, 108, 50, 122, 100, 50),
    "ironthorns": (100, 120, 64, 116, 80, 72),
    "tinglu": (95, 145, 45, 100, 100, 30),
    "chiyu": (80, 60, 135, 80, 80, 116),
    "chienpao": (120, 80, 60, 90, 80, 135),
    "wochien": (85, 100, 80, 100, 100, 45),
    "ironjugulis": (118, 70, 80, 122, 70, 108),
    "roaringmoon": (139, 70, 105, 70, 50, 119),
    "ogerpon": (120, 84, 96, 60, 84, 110),
    "ogerponwellspring": (120, 84, 96, 60, 84, 110),
    "ogerponhearthflame": (120, 84, 96, 60, 84, 110),
    "ogerponcornerstone": (120, 84, 96, 60, 84, 110),
    "rillaboom": (125, 90, 70, 100, 70, 85),
    "cinderace": (116, 75, 90, 67, 70, 119),
    "inteleon": (125, 65, 80, 70, 70, 120),
    "dragapult": (120, 75, 75, 100, 80, 142),
    "urshifu": (130, 100, 63, 60, 100, 97),
    "urshifurapidstrike": (130, 100, 63, 60, 100, 97),
    "toxapex": (63, 152, 53, 142, 35, 35),
    "corviknight": (87, 105, 85, 42, 110, 67),
    "greattusk": (131, 100, 53, 97, 100, 87),
    "irontreads": (100, 110, 80, 70, 100, 90),
    "zamazenta": (120, 120, 60, 80, 92, 105),
    "zamazentahero": (120, 120, 60, 80, 92, 105),
    "zacian": (120, 115, 80, 80, 115, 138),
    "zamazentacrowned": (120, 140, 80, 80, 115, 138),
    "kyogre": (100, 90, 150, 140, 100, 90),
    "groudon": (150, 140, 100, 90, 90, 90),
    "rayquaza": (150, 90, 150, 90, 90, 95),
    "palkia": (120, 100, 150, 120, 100, 100),
    "dialga": (120, 100, 120, 150, 100, 90),
    "giratina": (100, 120, 100, 120, 150, 90),
    "zekrom": (100, 150, 120, 100, 90, 100),
    "reshiram": (120, 100, 150, 120, 100, 90),
    "kyurem": (120, 90, 130, 130, 90, 95),
    "xerneas": (131, 95, 131, 98, 95, 99),
    "lunala": (137, 89, 113, 107, 137, 97),
    "solgaleo": (137, 107, 113, 89, 137, 97),
    "necrozma": (107, 113, 89, 107, 79, 79),
    "miraidon": (135, 115, 85, 100, 100, 135),
    "koraidon": (135, 115, 100, 85, 100, 135),
    "fluttermane": (55, 55, 135, 135, 55, 135),
    "garganacl": (100, 130, 90, 80, 100, 35),
    "ironclad": (90, 130, 80, 70, 100, 50),
    "glimmora": (100, 100, 60, 130, 90, 90),
    "amoonguss": (114, 70, 85, 80, 80, 30),
    "celesteela": (97, 101, 107, 97, 101, 61),
    "naganadel": (120, 60, 85, 100, 100, 140),
    "blissey": (255, 10, 75, 135, 75, 55),
    "chansey": (250, 5, 5, 35, 105, 50),
    "tinkaton": (75, 98, 80, 65, 70, 109),
    "annihilape": (110, 115, 60, 80, 90, 90),
    "meowscarada": (110, 70, 70, 110, 70, 123),
    "ironleaves": (90, 130, 90, 88, 90, 108),
    "ironcrown": (95, 100, 90, 100, 90, 100),
    "samurotthisui": (100, 110, 100, 60, 100, 100),
    "weavile": (120, 65, 60, 85, 85, 125),
    "scizor": (130, 100, 55, 80, 80, 65),
    "skarmory": (80, 140, 40, 70, 70, 70),
    "gliscor": (95, 125, 45, 75, 95, 95),
    "hippowdon": (108, 112, 68, 80, 97, 47),
    "alomomola": (165, 75, 40, 45, 80, 65),
    "mandibuzz": (110, 110, 65, 95, 95, 65),
    "donphan": (120, 120, 60, 60, 60, 50),
    "krookodile": (117, 80, 70, 65, 92, 92),
    "azumarill": (80, 50, 50, 60, 80, 50),
    "basculegion": (120, 70, 95, 80, 98, 78),
    "basculegionf": (120, 70, 95, 80, 98, 78),
    "hatterene": (57, 90, 95, 136, 103, 29),
    "ribombee": (60, 60, 55, 95, 70, 124),
    "palafin": (100, 97, 81, 106, 87, 100),
    "palafinhero": (100, 97, 81, 106, 87, 100),
    "maushold": (110, 85, 70, 75, 75, 50),
    "dachsbun": (115, 90, 60, 90, 95, 65),
    "arcanine": (110, 80, 100, 80, 90, 95),
    "snarlax": (160, 110, 65, 65, 110, 30),
    "sneasler": (120, 53, 75, 75, 120, 100),
    "veluza": (113, 82, 83, 117, 73, 70),
    "haxorus": (147, 90, 60, 70, 97, 97),
    "zapdos": (90, 85, 125, 90, 100, 100),
    "zapdosgalar": (90, 85, 125, 90, 100, 100),
    "moltres": (90, 90, 85, 125, 90, 90),
    "articuno": (90, 85, 100, 125, 85, 85),
    "moltresgalar": (90, 90, 85, 125, 90, 90),
    "lurantis": (105, 90, 50, 80, 80, 45),
    "slurpuff": (82, 86, 60, 86, 72, 72),
    "mimikyu": (55, 90, 80, 50, 105, 96),
    "mimikyubusted": (55, 90, 80, 50, 105, 96),
    "empoleon": (84, 88, 101, 88, 60, 60),
    "infernape": (104, 71, 104, 71, 84, 108),
    "lilligant": (71, 75, 50, 91, 110, 105),
    "kricketune": (77, 35, 65, 55, 75, 85),
    "ambipom": (75, 66, 100, 60, 115, 100),
    "aggron": (70, 140, 60, 50, 110, 50),
    "aggronmega": (70, 140, 60, 50, 110, 50),
    "slowbro": (95, 110, 80, 100, 80, 30),
    "slowking": (95, 80, 100, 110, 80, 30),
    "hawlucha": (78, 92, 75, 74, 63, 118),
    "noivern": (85, 80, 97, 80, 123, 123),
    "pangoro": (124, 78, 69, 71, 96, 58),
}


def get_base_stats(species_id: str) -> tuple[int, int, int, int, int, int] | None:
    """Look up ``(base_atk, base_def, base_spa, base_spd, base_hp, base_spe)``.

    Returns ``None`` for unknown species. The caller is expected to fall
    back to a safe default (e.g. 100/100/100/100/100/100).
    """
    if not species_id:
        return None
    key = species_id.lower().replace(" ", "").replace("-", "").replace(".", "")
    return _BASE_STATS.get(key)


__all__ = ["get_base_stats"]
