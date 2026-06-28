import { describe, expect, it } from "vitest";
import { slotsFor } from "./SpriteDebug";

// The probe returns hits in FOLDER_EXT order but with missing
// folders excluded, so hits[i] does NOT correspond to FOLDERS[i] when
// any earlier folder is missing. Each slot must look up its own hit
// by folder name so the slot label and image always agree.

describe("SpriteDebug.slotsFor", () => {
  const FOLDERS = ["gen5ani", "ani", "dex", "gen5", "home", "bw", "xyani"];

  it("returns 7 slots, one per folder, in FOLDER order", () => {
    const slots = slotsFor("pikachu", []);
    expect(slots.map((s) => s.folder)).toEqual(FOLDERS);
    expect(slots.every((s) => s.hit === null)).toBe(true);
  });

  it("places a hit in its own folder's slot when all 7 are present", () => {
    const hits = FOLDERS.map((f) => `${f} pikachu.${f === "gen5ani" || f === "ani" || f === "xyani" ? "gif" : "png"}`);
    const slots = slotsFor("pikachu", hits);
    for (const s of slots) {
      expect(s.hit).not.toBeNull();
      expect(s.hit).toMatch(new RegExp(`^${s.folder} `));
    }
  });

  it("places missing folders' slots as misses, not shifted left", () => {
    // aerodactyl-mega: gen5ani 404s, everything else 200s. The
    // previous index-based mapping would put the ani image in the
    // gen5ani slot — a real bug, since the label said gen5ani but
    // the image was ani. With folder-keyed lookup, gen5ani is a
    // miss and ani shows in the ani slot.
    const hits = [
      "ani aerodactyl-mega.gif",
      "dex aerodactyl-mega.png",
      "gen5 aerodactyl-mega.png",
      "home aerodactyl-mega.png",
      "bw aerodactyl-mega.png",
      "xyani aerodactyl-mega.gif",
    ];
    const slots = slotsFor("aerodactyl-mega", hits);
    expect(slots[0]?.folder).toBe("gen5ani");
    expect(slots[0]?.hit).toBeNull();
    expect(slots[1]?.folder).toBe("ani");
    expect(slots[1]?.hit).toBe("ani aerodactyl-mega.gif");
    expect(slots[2]?.folder).toBe("dex");
    expect(slots[2]?.hit).toBe("dex aerodactyl-mega.png");
    expect(slots[3]?.folder).toBe("gen5");
    expect(slots[3]?.hit).toBe("gen5 aerodactyl-mega.png");
    expect(slots[4]?.folder).toBe("home");
    expect(slots[4]?.hit).toBe("home aerodactyl-mega.png");
    expect(slots[5]?.folder).toBe("bw");
    expect(slots[5]?.hit).toBe("bw aerodactyl-mega.png");
    expect(slots[6]?.folder).toBe("xyani");
    expect(slots[6]?.hit).toBe("xyani aerodactyl-mega.gif");
  });

  it("handles a hit in the middle being missing", () => {
    // gen5 and bw missing, rest present.
    const hits = [
      "gen5ani slug.gif",
      "ani slug.gif",
      "dex slug.png",
      "home slug.png",
      "xyani slug.gif",
    ];
    const slots = slotsFor("slug", hits);
    expect(slots.map((s) => s.hit)).toEqual([
      "gen5ani slug.gif",
      "ani slug.gif",
      "dex slug.png",
      null, // gen5
      "home slug.png",
      null, // bw
      "xyani slug.gif",
    ]);
  });

  it("ignores malformed hit strings", () => {
    const slots = slotsFor("slug", ["", "no-space", "ani slug.gif"]);
    expect(slots[1]?.hit).toBe("ani slug.gif");
    // The empty and no-space strings produced no entries in the map,
    // so no other slot picks up garbage.
    expect(slots.filter((s) => s.hit !== null)).toHaveLength(1);
  });
});
