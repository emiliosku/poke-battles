import { describe, expect, it } from "vitest";
import { cdnUrlForSlug } from "./spriteDebugUtil";

describe("spriteDebugUtil.cdnUrlForSlug", () => {
  it("returns null for an empty slug", () => {
    expect(cdnUrlForSlug(null)).toBeNull();
    expect(cdnUrlForSlug("")).toBeNull();
  });

  it("reconstructs the URL for a vanilla species", () => {
    expect(cdnUrlForSlug("gen5ani hatterene.gif")).toBe(
      "https://play.pokemonshowdown.com/sprites/gen5ani/hatterene.gif",
    );
  });

  it("reconstructs the URL for a Mega form (form-aware suffix)", () => {
    expect(cdnUrlForSlug("ani charizard-megax.gif")).toBe(
      "https://play.pokemonshowdown.com/sprites/ani/charizard-megax.gif",
    );
  });

  it("reconstructs the URL for a Galarian form", () => {
    expect(cdnUrlForSlug("gen5ani slowking-galar.gif")).toBe(
      "https://play.pokemonshowdown.com/sprites/gen5ani/slowking-galar.gif",
    );
  });

  it("returns null if the slug has no space", () => {
    expect(cdnUrlForSlug("hatterene.gif")).toBeNull();
  });

  it("returns null if the slug has only a folder", () => {
    expect(cdnUrlForSlug("gen5ani")).toBeNull();
  });
});
