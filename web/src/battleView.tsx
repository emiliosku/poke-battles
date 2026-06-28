import type { BattleEvent, BattleResponse } from "./api";
import { PokemonSprite } from "./sprites";

interface SlotState {
  active: string;
  speciesId: string;
  hp: number;
  status: string;
  lastMove: string;
  slot: "a" | "b";
}

interface SideState {
  label: string;
  slots: [SlotState, SlotState];
}

const initialSides: [SideState, SideState] = [
  {
    label: "Player 1",
    slots: [
      { active: "Awaiting switch", speciesId: "", hp: 100, status: "ready", lastMove: "", slot: "a" },
      { active: "Awaiting partner", speciesId: "", hp: 100, status: "ready", lastMove: "", slot: "b" },
    ],
  },
  {
    label: "Player 2",
    slots: [
      { active: "Awaiting switch", speciesId: "", hp: 100, status: "ready", lastMove: "", slot: "a" },
      { active: "Awaiting partner", speciesId: "", hp: 100, status: "ready", lastMove: "", slot: "b" },
    ],
  },
];

const timelineKinds = new Set([
  "turn_start",
  "switch",
  "move",
  "damage",
  "heal",
  "faint",
  "status",
  "cure_status",
  "boost",
  "unboost",
  "weather_start",
  "weather_end",
  "field_start",
  "field_end",
  "side_condition_start",
  "side_condition_end",
  "battle_end",
]);

function sideIndex(raw?: string): 0 | 1 {
  return raw?.startsWith("p2") ? 1 : 0;
}

function eventSideIndex(event: BattleEvent): 0 | 1 {
  const side = event.raw?.source?.side || event.raw?.target?.side || event.raw?.pokemon?.side;
  if (side) return side === "p2" ? 1 : 0;
  return sideIndex(event.source || event.target || event.side);
}

function slotIndex(raw?: string): 0 | 1 {
  return raw?.startsWith("b") ? 1 : 0;
}

function eventSlotIndex(event: BattleEvent, ref: "source" | "target" | "pokemon" = "pokemon"): 0 | 1 {
  const pokemonRef = event.raw?.[ref];
  if (pokemonRef?.slot) return slotIndex(pokemonRef.slot);
  const raw = ref === "source" ? event.source : ref === "target" ? event.target : event.side;
  const slot = raw?.match(/^p\da:/) ? "a" : raw?.match(/^p\db:/) ? "b" : undefined;
  return slotIndex(slot);
}

function displayPokemon(raw?: string): string {
  if (!raw) return "Unknown";
  const cleaned = raw.split(":").pop()?.trim() || raw;
  return cleaned.split(",")[0]?.trim() || cleaned;
}

function applyEvent(sides: [SideState, SideState], event: BattleEvent): [SideState, SideState] {
  const next: [SideState, SideState] = [
    { ...sides[0], slots: [{ ...sides[0].slots[0] }, { ...sides[0].slots[1] }] },
    { ...sides[1], slots: [{ ...sides[1].slots[0] }, { ...sides[1].slots[1] }] },
  ];
  if (event.kind === "switch") {
    const idx = eventSideIndex(event);
    const slot = eventSlotIndex(event);
    next[idx].slots[slot].active = event.raw?.pokemon?.pokemon || displayPokemon(event.side);
    next[idx].slots[slot].speciesId = event.raw?.pokemon?.species_id || next[idx].slots[slot].speciesId;
    next[idx].slots[slot].hp = event.raw?.hp?.hp_percent ?? 100;
    next[idx].slots[slot].status = event.raw?.hp?.status || "active";
  }
  if (event.kind === "move") {
    const idx = eventSideIndex(event);
    const slot = eventSlotIndex(event, "source");
    next[idx].slots[slot].lastMove = event.detail || "move";
  }
  if (event.kind === "damage" || event.kind === "heal") {
    const idx = eventSideIndex(event);
    const slot = eventSlotIndex(event, "target");
    next[idx].slots[slot].active = event.raw?.target?.pokemon || displayPokemon(event.target) || next[idx].slots[slot].active;
    next[idx].slots[slot].speciesId = event.raw?.target?.species_id || next[idx].slots[slot].speciesId;
    const hp = event.raw?.hp?.hp_percent ?? event.quantity;
    if (typeof hp === "number") next[idx].slots[slot].hp = Math.max(0, Math.min(100, hp));
    if (event.raw?.hp?.status) next[idx].slots[slot].status = event.raw.hp.status;
  }
  if (event.kind === "faint") {
    const idx = eventSideIndex(event);
    const slot = eventSlotIndex(event, "target");
    next[idx].slots[slot].active = event.raw?.target?.pokemon || displayPokemon(event.target) || next[idx].slots[slot].active;
    next[idx].slots[slot].speciesId = event.raw?.target?.species_id || next[idx].slots[slot].speciesId;
    next[idx].slots[slot].hp = 0;
    next[idx].slots[slot].status = "fainted";
  }
  if (event.kind === "status" || event.kind === "cure_status") {
    const idx = eventSideIndex(event);
    const slot = eventSlotIndex(event, "target");
    next[idx].slots[slot].status = event.kind === "cure_status" ? "active" : event.detail || "status";
  }
  return next;
}

// Showdown ships several sprite paths. gen5ani is missing for many Gen 9 mons,
// so we walk the chain gen5ani → ani (newer animated) → dex (static png).
// The chain-fallback renderer lives in ./sprites.tsx so the Teams preview
// can reuse the exact same behaviour.

function BattleSlotSprite({ slot }: { slot: SlotState }) {
  return <PokemonSprite primaryId={slot.speciesId} label={slot.active} />;
}

export function battleSidesFromEvents(events: BattleEvent[]): [SideState, SideState] {
  return visibleTimelineEvents(events).reduce(applyEvent, initialSides);
}

function usesDoublesSlots(events: BattleEvent[]): boolean {
  return events.some((event) => {
    const refs = [event.raw?.source, event.raw?.target, event.raw?.pokemon];
    return refs.some((ref) => ref?.slot === "b") || [event.source, event.target, event.side].some((raw) => /^p\db:/.test(raw || ""));
  });
}

function CombatSlot({ slot }: { slot: SlotState }) {
  return (
    <div className="combat-slot">
      <span className="badge">Slot {slot.slot.toUpperCase()}</span>
      <h3 className="combat-name">{slot.active}</h3>
      <BattleSlotSprite slot={slot} />
      <div className="hp-track"><div className="hp-fill" style={{ width: `${slot.hp}%` }} /></div>
      <p className="combat-status">{slot.hp}% HP · {slot.status}</p>
      {slot.lastMove && <p className="combat-last">Last move: {slot.lastMove}</p>}
    </div>
  );
}

export function visibleTimelineEvents(events: BattleEvent[]): BattleEvent[] {
  const deduped: BattleEvent[] = [];
  for (const event of events) {
    if (!timelineKinds.has(event.kind)) continue;
    const previous = deduped[deduped.length - 1];
    if (
      previous &&
      previous.kind === event.kind &&
      previous.turn === event.turn &&
      previous.source === event.source &&
      previous.target === event.target &&
      previous.side === event.side &&
      previous.detail === event.detail
    ) {
      continue;
    }
    deduped.push(event);
  }
  return deduped;
}

export function formatEvent(event: BattleEvent): string {
  if (event.kind === "turn_start") return `Turn ${event.turn}`;
  if (event.kind === "move") return `${event.raw?.source?.pokemon || displayPokemon(event.source)} used ${event.detail}`;
  if (event.kind === "switch") return `${event.raw?.pokemon?.pokemon || displayPokemon(event.side)} switched in (${event.raw?.hp?.hp_text || event.detail || "ready"})`;
  if (event.kind === "damage") return `${event.raw?.target?.pokemon || displayPokemon(event.target)} took damage (${event.raw?.hp?.hp_text || event.detail})`;
  if (event.kind === "heal") return `${event.raw?.target?.pokemon || displayPokemon(event.target)} healed (${event.raw?.hp?.hp_text || event.detail})`;
  if (event.kind === "faint") return `${event.raw?.target?.pokemon || displayPokemon(event.target)} fainted`;
  if (event.kind === "status") return `${event.raw?.target?.pokemon || displayPokemon(event.target)} is ${event.detail}`;
  if (event.kind === "cure_status") return `${event.raw?.target?.pokemon || displayPokemon(event.target)} cured ${event.detail}`;
  if (event.kind === "boost") return `${displayPokemon(event.target)} boosted ${event.detail}`;
  if (event.kind === "unboost") return `${displayPokemon(event.target)} lost ${event.detail}`;
  if (event.kind === "weather_start") return `Weather started: ${event.detail}`;
  if (event.kind === "weather_end") return `Weather ended: ${event.detail}`;
  if (event.kind === "field_start") return `Field effect started: ${event.detail}`;
  if (event.kind === "field_end") return `Field effect ended: ${event.detail}`;
  if (event.kind === "side_condition_start") return `${event.side || "Side"}: ${event.detail}`;
  if (event.kind === "side_condition_end") return `${event.side || "Side"}: ${event.detail} ended`;
  if (event.kind === "battle_end") return event.detail === "tie" ? "Battle ended in a tie" : `Winner: ${event.detail || "unknown"}`;
  return [event.kind, event.side || event.target || event.source, event.detail].filter(Boolean).join(" · ");
}

export function Battlefield({ battle, events }: { battle?: BattleResponse | null; events: BattleEvent[] }) {
  const visible = visibleTimelineEvents(events);
  const sides = battleSidesFromEvents(visible);
  sides[0].label = battle?.player1_username || "Player 1";
  sides[1].label = battle?.player2_username || "Player 2";
  const activeSlots = battle?.format.includes("double") || usesDoublesSlots(visible) ? 2 : 1;

  return (
    <div className="battlefield" aria-label="Battlefield viewer">
      <div className="combatant top">
        <div className="combatant-head"><strong>{sides[1].label}</strong><span className="badge red">{battle?.model2 || "opponent"}</span></div>
        <div className="slots-row">
          {sides[1].slots.slice(0, activeSlots).map((slot) => <CombatSlot key={slot.slot} slot={slot} />)}
        </div>
      </div>
      <div className="combatant bottom">
        <div className="combatant-head"><strong>{sides[0].label}</strong><span className="badge green">{battle?.model1 || "you"}</span></div>
        <div className="slots-row">
          {sides[0].slots.slice(0, activeSlots).map((slot) => <CombatSlot key={slot.slot} slot={slot} />)}
        </div>
      </div>
    </div>
  );
}
