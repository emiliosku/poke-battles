import { describe, expect, it } from "vitest";
import { battleSidesFromEvents, formatEvent, formatEventWithContext, visibleTimelineEvents } from "./battleView";
import type { BattleEvent } from "./api";

describe("battle timeline view helpers", () => {
  it("filters protocol request blobs out of the human timeline", () => {
    const events: BattleEvent[] = [
      { kind: "turn_start", turn: 1 },
      { kind: "switch_request", turn: 1, detail: '{"active":[{"moves":[]}]}' },
      { kind: "message", turn: 1, detail: "Battle" },
      {
        kind: "move",
        turn: 1,
        source: "p1a: Pikachu",
        target: "p2a: Eevee",
        detail: "Thunderbolt",
        raw: { source: { side: "p1", pokemon: "Pikachu" }, target: { side: "p2", pokemon: "Eevee" } },
      },
    ];

    const timeline = visibleTimelineEvents(events);

    expect(timeline.map((event) => event.kind)).toEqual(["turn_start", "move"]);
    expect(formatEvent(timeline[1] as BattleEvent)).toBe("Pikachu used Thunderbolt");
  });

  it("deduplicates adjacent duplicate protocol events", () => {
    const move: BattleEvent = { kind: "move", turn: 3, source: "p1a: Mew", target: "p2a: Mewtwo", detail: "Psychic" };

    expect(visibleTimelineEvents([move, move])).toHaveLength(1);
  });

  it("tracks doubles slots independently", () => {
    const events: BattleEvent[] = [
      {
        kind: "switch",
        turn: 1,
        side: "p1a: Incineroar",
        raw: { pokemon: { side: "p1", slot: "a", pokemon: "Incineroar", species_id: "incineroar" }, hp: { hp_percent: 100 } },
      },
      {
        kind: "switch",
        turn: 1,
        side: "p1b: Flutter Mane",
        raw: { pokemon: { side: "p1", slot: "b", pokemon: "Flutter Mane", species_id: "fluttermane" }, hp: { hp_percent: 75 } },
      },
      {
        kind: "damage",
        turn: 2,
        target: "p1b: Flutter Mane",
        raw: { target: { side: "p1", slot: "b", pokemon: "Flutter Mane", species_id: "fluttermane" }, hp: { hp_percent: 20 } },
      },
    ];

    const [playerSide] = battleSidesFromEvents(events);

    expect(playerSide.slots[0].active).toBe("Incineroar");
    expect(playerSide.slots[0].hp).toBe(100);
    expect(playerSide.slots[1].active).toBe("Flutter Mane");
    expect(playerSide.slots[1].hp).toBe(20);
  });

  it("keeps variant sprite ids from switch events after later base-name damage", () => {
    const events: BattleEvent[] = [
      {
        kind: "switch",
        turn: 1,
        side: "p1a: Slowking",
        raw: {
          pokemon: {
            side: "p1",
            slot: "a",
            pokemon: "Slowking",
            species: "Slowking-Galar",
            species_id: "slowkinggalar",
            sprite_id: "slowking-galar",
          },
          hp: { hp_percent: 100 },
        },
      },
      {
        kind: "damage",
        turn: 1,
        target: "p1a: Slowking",
        raw: {
          target: { side: "p1", slot: "a", pokemon: "Slowking", species_id: "slowking", sprite_id: "slowking" },
          hp: { hp_text: "64/100", hp_percent: 64 },
        },
      },
    ];

    const [playerSide] = battleSidesFromEvents(events);

    expect(playerSide.slots[0].active).toBe("Slowking-Galar");
    expect(playerSide.slots[0].speciesId).toBe("slowkinggalar");
    expect(playerSide.slots[0].spriteId).toBe("slowking-galar");
    expect(playerSide.slots[0].hp).toBe(64);
    expect(formatEventWithContext(events, 0)).toBe("Slowking-Galar switched in (ready)");
    expect(formatEventWithContext(events, 1)).toBe("Slowking-Galar took damage (64/100)");
  });

  it("recovers switch forms from details when normalized events lack species", () => {
    const events: BattleEvent[] = [
      {
        kind: "switch",
        turn: 1,
        side: "p2b: Slowking",
        detail: "Slowking-Galar, L50, F 100/100",
        raw: {
          pokemon: { side: "p2", slot: "b", pokemon: "Slowking", species_id: "slowking" },
          hp: { hp_text: "Slowking-Galar, L50, F" },
        },
      },
      {
        kind: "move",
        turn: 1,
        source: "p2b: Slowking",
        detail: "Sludge Bomb",
        raw: { source: { side: "p2", slot: "b", pokemon: "Slowking", species_id: "slowking" } },
      },
    ];

    const [, opponentSide] = battleSidesFromEvents(events);

    expect(opponentSide.slots[1].active).toBe("Slowking-Galar");
    expect(opponentSide.slots[1].speciesId).toBe("slowkinggalar");
    expect(opponentSide.slots[1].spriteId).toBe("slowking-galar");
    expect(formatEventWithContext(events, 0)).toBe("Slowking-Galar switched in (Slowking-Galar, L50, F)");
    expect(formatEventWithContext(events, 1)).toBe("Slowking-Galar used Sludge Bomb");
  });
});
