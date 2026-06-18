import { describe, expect, it } from "vitest";
import { formatEvent, visibleTimelineEvents } from "./battleView";
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
});
