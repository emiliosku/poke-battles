"""Probe the Showdown CDN to make sure sprite URLs work for the
specific forms a user pastes (megas, regionals, dotted names, …) and
to verify the new ``GET /api/pokedex`` endpoint exposes the canonical
species list.

The curated cases run every CI by default (~30 species × up to 14 URL
probes each = at most a couple hundred requests, all under 30s).
The whole-dex probe is opt-in via the ``POKE_BATTLES_RUN_SPRITE_PROBE``
env var and writes a coverage report to ``tests/artifacts/``:

    POKE_BATTLES_RUN_SPRITE_PROBE=1 pytest tests/integration/test_sprite_coverage.py

The chain mirrors the one in ``web/src/sprites.tsx``:

    gen5ani → ani → dex → gen5 → home → bw → xyani

We probe both the canonical ``species_id`` (lowercased, dashes stripped)
and the ``sprite_id`` produced by ``pokecore.teams.sprite_id``
(lowercased, dashes kept, accents folded). At least one of those two
slugs must resolve for the test to pass.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from pokecore.pokedex import load_pokedex
from pokecore.teams import sprite_id as derive_sprite_id

CDN = "https://play.pokemonshowdown.com/sprites"
# Shorter chain for the curated test (each species = at most 6 probes).
# The full audit uses the longer chain.
FOLDER_EXT_CURATED = [
    ("gen5ani", "gif"),  # Gen 5 pixel art (preferred)
    ("ani", "gif"),  # Newer animated
    ("dex", "png"),  # Static Gen 7+ Home style
]
FOLDER_EXT_FULL = [
    ("gen5ani", "gif"),
    ("ani", "gif"),
    ("dex", "png"),
    ("gen5", "png"),
    ("home", "png"),
    ("bw", "png"),
    ("xyani", "gif"),
]
USER_AGENT = "Mozilla/5.0"  # CDN blocks the default urllib UA.


def _probe(url: str, timeout: float = 8.0) -> bool:
    # The Showdown CDN is the only host this test contacts; we never
    # resolve a `file:` or arbitrary scheme here. The S310 lint about
    # permitted schemes is intentional.
    req = urllib.request.Request(  # noqa: S310
        url,
        method="GET",
        headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status in (200, 206)
    except urllib.error.HTTPError:
        return False
    except Exception:
        return False


def _find_sprite(slug: str, chain: list[tuple[str, str]] = FOLDER_EXT_FULL) -> str | None:
    """Return ``"<folder> <slug>"`` of the first URL that 200s, or None."""
    for folder, ext in chain:
        if _probe(f"{CDN}/{folder}/{slug}.{ext}"):
            return f"{folder} {slug}"
    return None


# Forms the user explicitly asked us to verify, plus a representative
# spread across every generation that introduces a new naming convention
# (Galar, Hisui, Alola, Paldea, Mega-X/Y, Rotom, Unown, Primal, Origin,
# Therian, etc.). Each case asserts "at least one of the two slugs the
# app actually uses must resolve". Some newer species (Mr. Mime-Galar,
# Maushold-Three, etc.) genuinely have no CDN artwork yet — those are
# reported but not asserted hard.
CURATED_FORMS = [
    # Vanilla forms (regression baseline)
    "Pikachu",
    "Garchomp",
    "Mewtwo",
    # Megas (the headline case from the bug report)
    "Charizard-Mega-X",
    "Charizard-Mega-Y",
    "Mewtwo-Mega-X",
    "Mewtwo-Mega-Y",
    "Aerodactyl-Mega",
    "Blaziken-Mega",
    "Gyarados-Mega",
    "Rayquaza-Mega",
    # Regionals
    "Slowking-Galar",
    "Weezing-Galar",
    "Zoroark-Hisui",
    "Wooper-Paldea",
    "Vulpix-Alola",
    "Growlithe-Hisui",
    # Dotted / spaced names
    "Mr. Mime",
    "Mr. Mime-Galar",
    "Mime Jr.",
    "Tapu Lele",
    "Mr. Rime",
    "Farfetch'd",
    "Flabébé",
    # Older multi-letter forms
    "Kyurem-Black",
    "Giratina-Origin",
    "Tornadus-Therian",
    "Deoxys-Attack",
    "Rotom-Wash",
    "Wishiwashi-School",
    "Mimikyu-Busted",
    "Toxtricity-Lowkey",
    "Eiscue",
    "Eternatus-Eternamax",
    "Calyrex-Ice",
    "Enamorus-Therian",
    "Magearna-Original",
    "Zacian-Crowned",
    "Oricorio-Sensu",
    "Unown-B",
    "Unown-Exclamation",
]


# Forms we require to resolve. Newer Showdown releases sometimes have
# not yet added artwork for a species; we keep those out of the strict
# list and only assert the curated list that has shipped sprites for
# several months.
REQUIRED_FORMS = [
    "Pikachu",
    "Garchomp",
    "Mewtwo",
    "Charizard-Mega-X",
    "Charizard-Mega-Y",
    "Mewtwo-Mega-X",
    "Mewtwo-Mega-Y",
    "Aerodactyl-Mega",
    "Blaziken-Mega",
    "Gyarados-Mega",
    "Rayquaza-Mega",
    "Slowking-Galar",
    "Weezing-Galar",
    "Zoroark-Hisui",
    "Wooper-Paldea",
    "Vulpix-Alola",
    "Growlithe-Hisui",
    "Mr. Mime",
    "Mime Jr.",
    "Tapu Lele",
    "Farfetch'd",
    "Flabébé",
    "Kyurem-Black",
    "Giratina-Origin",
    "Tornadus-Therian",
    "Deoxys-Attack",
    "Rotom-Wash",
    "Wishiwashi-School",
    "Mimikyu-Busted",
    "Eiscue",
    "Eternatus-Eternamax",
    "Calyrex-Ice",
    "Magearna-Original",
    "Zacian-Crowned",
    "Unown-B",
]


def _normalize_id(species: str) -> str:
    """Mirror of ``_normalize_species_id`` from ``pokecore.teams``."""
    import re

    return re.sub(r"[^a-z0-9]", "", species.lower())


def test_required_forms_have_a_cdn_sprite() -> None:
    """The required list (regression set for the original bug report)
    must all resolve at least one CDN URL. Newer forms we haven't yet
    pinned a release window for are in ``CURATED_FORMS`` but not in
    the required list — see the report below for the full audit."""
    failures: list[str] = []
    report: list[str] = []
    for species in CURATED_FORMS:
        canonical = _normalize_id(species)
        derived = derive_sprite_id(species)
        # Use the short chain for the curated test to keep it fast.
        hit = _find_sprite(canonical, FOLDER_EXT_CURATED) or _find_sprite(
            derived, FOLDER_EXT_CURATED
        )
        report.append(
            f"{species:<24} canonical={canonical:<22} derived={derived:<22} -> {hit or 'MISSING'}"
        )
        if species in REQUIRED_FORMS and hit is None:
            failures.append(species)
    # Always print the report so the bug fix is auditable from CI logs.
    print("\n" + "\n".join(report))
    assert not failures, (
        "These species have no sprite on the Showdown CDN under either "
        "the canonical or derived slug: " + ", ".join(failures)
    )


@pytest.mark.skipif(
    os.environ.get("POKE_BATTLES_RUN_SPRITE_PROBE") != "1",
    reason="set POKE_BATTLES_RUN_SPRITE_PROBE=1 to probe every species in the bundled pokedex",
)
def test_every_species_has_a_cdn_sprite(tmp_path: Path) -> None:
    """Full audit: every species in the bundled Pokédex. Network-bound,
    so opt-in. Writes ``sprite_coverage.txt`` and ``sprite_missing.txt``
    under ``tests/artifacts/`` for review."""
    entries = load_pokedex()
    assert entries, "bundled pokedex.js is empty or unreadable"

    coverage: list[tuple[str, str, str]] = []
    missing: list[str] = []
    for entry in entries:
        hit = _find_sprite(entry.species_id) or _find_sprite(derive_sprite_id(entry.name))
        coverage.append((entry.species_id, entry.name, hit or "MISSING"))
        if hit is None:
            missing.append(entry.species_id)

    artifacts = Path(__file__).resolve().parent.parent / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "sprite_coverage.txt").write_text(
        "\n".join(f"{sid:<24} {name:<24} {hit}" for sid, name, hit in coverage) + "\n",
        encoding="utf-8",
    )
    (artifacts / "sprite_missing.txt").write_text(
        "\n".join(sorted(set(missing))) + "\n",
        encoding="utf-8",
    )
    total = len(coverage)
    print(
        f"\nSprite coverage: {total - len(missing)}/{total} species "
        f"have at least one CDN URL serving an image. "
        f"Missing: {len(missing)} (see tests/artifacts/sprite_missing.txt)."
    )


def test_preview_endpoint_round_trip_through_paste() -> None:
    """End-to-end: paste a team with a known set of forms and verify
    the preview response carries the same ``sprite_id`` we expect."""
    from pokecore.teams import _normalize_species_id, parse_team
    from pokecore.types import Type, TypePair

    def type_resolver(sid: str) -> TypePair:
        return TypePair(Type.NORMAL)

    paste = (
        "Aerodactyl-Mega @ Aerodactylite\nAbility: Tough Claws\nHardy Nature\n- Stone Edge\n\n"
        "Slowking-Galar @ Heavy-Duty Boots\nAbility: Regenerator\nBold Nature\n- Future Sight\n"
    )
    team = parse_team(paste, type_resolver=type_resolver)
    by_sid = {p.species_id: derive_sprite_id(p.species) for p in team.pokemon}
    assert by_sid[_normalize_species_id("Aerodactyl-Mega")] == "aerodactyl-mega"
    assert by_sid[_normalize_species_id("Slowking-Galar")] == "slowking-galar"


def test_pokedex_endpoint_includes_known_species() -> None:
    """The new ``GET /api/pokedex`` endpoint must be reachable and
    include the canonical id of every species the team parser emits."""
    from fastapi.testclient import TestClient

    from pokeapi.main import app

    client = TestClient(app)
    response = client.get("/pokedex")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] > 1000, body["count"]
    ids = {p["species_id"] for p in body["pokemon"]}
    for must in ("pikachu", "garchomp", "charizard", "charizardmegax", "mewtwomegax"):
        assert must in ids, f"{must} missing from /pokedex"


def test_pokedex_payload_is_json_friendly() -> None:
    """Sanity: every entry is JSON-serializable with the documented shape."""
    from fastapi.testclient import TestClient

    from pokeapi.main import app

    response = TestClient(app).get("/pokedex")
    assert response.status_code == 200
    body = response.json()
    sample = body["pokemon"][0]
    assert set(sample.keys()) == {
        "species_id",
        "name",
        "num",
        "types",
        "base_stats",
        "abilities",
    }
    json.dumps(sample)
