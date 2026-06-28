import { describe, expect, it } from "vitest";
import { spriteUrls } from "./sprites";

describe("spriteUrls", () => {
  it("returns the full folder chain for a single slug", () => {
    const urls = spriteUrls("hatterene");
    expect(urls).toEqual([
      "https://play.pokemonshowdown.com/sprites/gen5ani/hatterene.gif",
      "https://play.pokemonshowdown.com/sprites/ani/hatterene.gif",
      "https://play.pokemonshowdown.com/sprites/dex/hatterene.png",
      "https://play.pokemonshowdown.com/sprites/gen5/hatterene.png",
      "https://play.pokemonshowdown.com/sprites/home/hatterene.png",
      "https://play.pokemonshowdown.com/sprites/bw/hatterene.png",
      "https://play.pokemonshowdown.com/sprites/xyani/hatterene.gif",
    ]);
  });

  it("returns an empty list for empty/null/undefined input", () => {
    expect(spriteUrls("")).toEqual([]);
    expect(spriteUrls(null)).toEqual([]);
    expect(spriteUrls(undefined)).toEqual([]);
  });

  it("tries the slugs in the order they're passed, dedupes", () => {
    // Charizard-Mega-X: canonical (species_id) is "charizardmegax",
    // the form-aware sprite slug is "charizard-megax". The CDN serves
    // the latter. The caller chooses the order; here the caller puts
    // canonical first (as the API does, since canonical is the
    // primary lookup key), so the first URL is the canonical gen5ani.
    const urls = spriteUrls("charizardmegax", "charizard-megax");
    expect(urls[0]).toBe(
      "https://play.pokemonshowdown.com/sprites/gen5ani/charizardmegax.gif",
    );
    // The derived slug's URLs come after the canonical's. They would
    // be reached via the <img>'s onError fallback chain if the
    // canonical 404s.
    expect(urls).toContain(
      "https://play.pokemonshowdown.com/sprites/ani/charizard-megax.gif",
    );
    // No duplicates across the two slug inputs.
    expect(new Set(urls).size).toBe(urls.length);
  });

  it("puts the derived slug first when called in derived-then-canonical order", () => {
    // This is the production call order: PokemonSprite's ``primaryId``
    // is the API's sprite_id (form-aware), ``fallbackId`` is the
    // species_id (canonical). So the form-aware URL — the one that
    // actually resolves for megas / regionals — comes first.
    const urls = spriteUrls("slowking-galar", "slowkinggalar");
    expect(urls[0]).toBe(
      "https://play.pokemonshowdown.com/sprites/gen5ani/slowking-galar.gif",
    );
    // Canonical URLs come after the derived's.
    const derivedIndex = urls.findIndex((u) => u.includes("slowking-galar.gif"));
    const canonicalIndex = urls.findIndex((u) => u.includes("slowkinggalar.gif"));
    expect(derivedIndex).toBe(0);
    expect(canonicalIndex).toBeGreaterThan(derivedIndex);
  });

  it("deduplicates when both slugs resolve to the same URL", () => {
    // Some species have canonical == derived (e.g. base Pikachu). The
    // chain must not contain duplicate URLs.
    const urls = spriteUrls("pikachu", "pikachu");
    expect(new Set(urls).size).toBe(urls.length);
  });

  it("prefers the home sprite first when variant=\"home\"", () => {
    const urls = spriteUrls("hatterene", { variant: "home" });
    expect(urls[0]).toBe(
      "https://play.pokemonshowdown.com/sprites/home/hatterene.png",
    );
    // And the rest of the default chain is appended as a fallback so
    // species without a home image (e.g. CAP) still render.
    expect(urls).toContain(
      "https://play.pokemonshowdown.com/sprites/gen5ani/hatterene.gif",
    );
  });

  it("home variant keeps the form-aware slug first for megas / regionals", () => {
    const urls = spriteUrls("slowking-galar", "slowkinggalar", { variant: "home" });
    expect(urls[0]).toBe(
      "https://play.pokemonshowdown.com/sprites/home/slowking-galar.png",
    );
    const derivedHome = urls.findIndex((u) => u === "https://play.pokemonshowdown.com/sprites/home/slowking-galar.png");
    const canonicalHome = urls.findIndex((u) => u === "https://play.pokemonshowdown.com/sprites/home/slowkinggalar.png");
    expect(derivedHome).toBe(0);
    expect(canonicalHome).toBeGreaterThan(derivedHome);
  });
});
