"""Probe the Pokémon Showdown CDN for every species in the bundled
Pokédex and report which slugs resolve to a real image.

This is a debug tool used by the ``/debug/sprites`` page in the web
UI to surface every sprite that the engine knows about. Results are
cached in-memory for an hour so the page can be re-rendered without
re-probing the CDN; pass ``refresh=true`` to bust the cache.

The probe is conservative on resources:

* Concurrency is bounded (default 32 workers).
* One short HTTP GET per (slug, folder) — we set ``Range: bytes=0-0``
  so a CDN miss returns ~70 bytes instead of the full image.
* Timeouts are 5s per request.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass

from pokecore.pokedex import PokedexEntry, load_pokedex
from pokecore.teams import sprite_id as derive_sprite_id

CDN = "https://play.pokemonshowdown.com/sprites"
USER_AGENT = "Mozilla/5.0"  # CDN blocks the default urllib UA.
PROBE_TIMEOUT_S = 5.0
CACHE_TTL_S = 3600.0
DEFAULT_WORKERS = 16  # keep modest — 32 hammered the CI runner

# Mirror of web/src/sprites.tsx — gen5ani (pixel art, gif) first,
# then newer animated, then static Gen 7+, then other visual styles.
FOLDER_EXT: list[tuple[str, str]] = [
    ("gen5ani", "gif"),
    ("ani", "gif"),
    ("dex", "png"),
    ("gen5", "png"),
    ("home", "png"),
    ("bw", "png"),
    ("xyani", "gif"),
]


@dataclass(frozen=True, slots=True)
class SpriteResult:
    species_id: str
    name: str
    types: list[str]
    canonical_slug: str
    derived_slug: str
    # ``"<folder> <slug>.<ext>"`` of every URL that returned 2xx, in
    # ``FOLDER_EXT`` order. Empty when the slug has no sprites on the
    # CDN. The debug page renders all 7 slots so the operator can see
    # which folders the CDN actually serves for each mon.
    canonical_hits: list[str]
    derived_hits: list[str]
    # True for community-created CAP mons; they have a negative ``num``
    # in the Showdown dex and aren't part of the official games.
    is_cap: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SpriteStatusReport:
    checked_at: float
    count: int
    duration_s: float
    results: list[SpriteResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "checked_at": self.checked_at,
            "count": self.count,
            "duration_s": self.duration_s,
            "results": [r.to_dict() for r in self.results],
        }


def _probe(url: str, timeout: float = PROBE_TIMEOUT_S) -> bool:
    req = urllib.request.Request(  # noqa: S310 — debug endpoint, CDN is the only host we touch
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


def _resolve_all(slug: str) -> list[str]:
    """Return ``"<folder> <slug>.<ext>"`` for every URL that 200s, in
    ``FOLDER_EXT`` order. Empty list means the CDN has no sprite for
    this slug under any known folder/format."""
    hits: list[str] = []
    for folder, ext in FOLDER_EXT:
        if _probe(f"{CDN}/{folder}/{slug}.{ext}"):
            hits.append(f"{folder} {slug}.{ext}")
    return hits


def _probe_one(species_id: str, name: str, types: list[str], is_cap: bool) -> SpriteResult:
    canonical = species_id
    derived = derive_sprite_id(name) if name else species_id
    canonical_hits = _resolve_all(canonical)
    # Avoid probing the same slug twice; the debug page treats an empty
    # derived_hits list as "see the canonical cell" for vanilla species.
    derived_hits = _resolve_all(derived) if derived != canonical else []
    return SpriteResult(
        species_id=species_id,
        name=name,
        types=list(types),
        canonical_slug=canonical,
        derived_slug=derived,
        canonical_hits=canonical_hits,
        derived_hits=derived_hits,
        is_cap=is_cap,
    )


def probe_all(
    *,
    workers: int = DEFAULT_WORKERS,
    only_species: Iterable[str] | None = None,
) -> SpriteStatusReport:
    """Run the full probe (or only the given species) and return a report."""
    start = time.monotonic()
    entries: list[PokedexEntry] = list(load_pokedex())
    if only_species is not None:
        wanted = set(only_species)
        entries = [e for e in entries if e.species_id in wanted]
    results: list[SpriteResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _probe_one,
                entry.species_id,
                entry.name,
                list(entry.types),
                # CAP mons get a negative ``num`` in the Showdown dex.
                entry.num < 0,
            ): entry.species_id
            for entry in entries
        }
        for fut in as_completed(futures):
            results.append(fut.result())
    # Keep natural-dex order so the UI is stable across runs.
    results.sort(key=lambda r: (r.types == [], r.name, r.species_id))
    return SpriteStatusReport(
        checked_at=time.time(),
        count=len(results),
        duration_s=time.monotonic() - start,
        results=results,
    )


# --- Caching --------------------------------------------------------------


_cache: SpriteStatusReport | None = None
_cache_at: float = 0.0


def get_status(
    *, refresh: bool = False, only_species: Iterable[str] | None = None
) -> SpriteStatusReport:
    """Return a (cached or fresh) report."""
    global _cache, _cache_at
    now = time.monotonic()
    if (
        not refresh
        and only_species is None
        and _cache is not None
        and now - _cache_at < CACHE_TTL_S
    ):
        return _cache
    report = probe_all(only_species=only_species)
    if only_species is None and not refresh:
        _cache = report
        _cache_at = now
    elif refresh and only_species is None:
        # Caller asked for a fresh full report; cache it.
        _cache = report
        _cache_at = now
    return report


def clear_cache() -> None:
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0


__all__ = [
    "CDN",
    "FOLDER_EXT",
    "SpriteResult",
    "SpriteStatusReport",
    "clear_cache",
    "get_status",
    "probe_all",
]


def _json_default(obj: object) -> object:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    raise TypeError(f"object of type {type(obj).__name__} is not JSON serializable")


def dumps(report: SpriteStatusReport) -> str:
    return json.dumps(report.to_dict(), default=_json_default, ensure_ascii=False)
