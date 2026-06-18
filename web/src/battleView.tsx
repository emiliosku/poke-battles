import { useState } from "react";
import type { BattleEvent, BattleResponse } from "./api";

interface SideState {
  label: string;
  active: string;
  speciesId: string;
  hp: number;
  status: string;
  lastMove: string;
}

const initialSides: [SideState, SideState] = [
  { label: "Player 1", active: "Awaiting switch", speciesId: "", hp: 100, status: "ready", lastMove: "" },
  { label: "Player 2", active: "Awaiting switch", speciesId: "", hp: 100, status: "ready", lastMove: "" },
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

function displayPokemon(raw?: string): string {
  if (!raw) return "Unknown";
  const cleaned = raw.split(":").pop()?.trim() || raw;
  return cleaned.split(",")[0]?.trim() || cleaned;
}

function applyEvent(sides: [SideState, SideState], event: BattleEvent): [SideState, SideState] {
  const next: [SideState, SideState] = [{ ...sides[0] }, { ...sides[1] }];
  if (event.kind === "switch") {
    const idx = eventSideIndex(event);
    next[idx].active = event.raw?.pokemon?.pokemon || displayPokemon(event.side);
    next[idx].speciesId = event.raw?.pokemon?.species_id || next[idx].speciesId;
    next[idx].hp = event.raw?.hp?.hp_percent ?? 100;
    next[idx].status = event.raw?.hp?.status || "active";
  }
  if (event.kind === "move") {
    const idx = eventSideIndex(event);
    next[idx].lastMove = event.detail || "move";
  }
  if (event.kind === "damage" || event.kind === "heal") {
    const idx = eventSideIndex(event);
    next[idx].active = event.raw?.target?.pokemon || displayPokemon(event.target) || next[idx].active;
    next[idx].speciesId = event.raw?.target?.species_id || next[idx].speciesId;
    const hp = event.raw?.hp?.hp_percent ?? event.quantity;
    if (typeof hp === "number") next[idx].hp = Math.max(0, Math.min(100, hp));
    if (event.raw?.hp?.status) next[idx].status = event.raw.hp.status;
  }
  if (event.kind === "faint") {
    const idx = eventSideIndex(event);
    next[idx].active = event.raw?.target?.pokemon || displayPokemon(event.target) || next[idx].active;
    next[idx].speciesId = event.raw?.target?.species_id || next[idx].speciesId;
    next[idx].hp = 0;
    next[idx].status = "fainted";
  }
  if (event.kind === "status" || event.kind === "cure_status") {
    const idx = eventSideIndex(event);
    next[idx].status = event.kind === "cure_status" ? "active" : event.detail || "status";
  }
  return next;
}

function PokemonSprite({ side }: { side: SideState }) {
  const [failed, setFailed] = useState(false);
  const url = side.speciesId ? `https://play.pokemonshowdown.com/sprites/gen5ani/${side.speciesId}.gif` : "";
  if (!url || failed) return <div className="sprite-orb">{side.active.slice(0, 1)}</div>;
  return <img className="pokemon-sprite" src={url} alt="" onError={() => setFailed(true)} />;
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
  const sides = visible.reduce(applyEvent, initialSides);
  sides[0].label = battle?.player1_username || "Player 1";
  sides[1].label = battle?.player2_username || "Player 2";

  return (
    <div className="battlefield" aria-label="Battlefield viewer">
      <div className="combatant top">
        <div className="row" style={{ justifyContent: "space-between" }}><strong>{sides[1].label}</strong><span className="badge red">{battle?.model2 || "opponent"}</span></div>
        <h3>{sides[1].active}</h3>
        <div className="hp-track"><div className="hp-fill" style={{ width: `${sides[1].hp}%` }} /></div>
        <p>{sides[1].hp}% HP · {sides[1].status}</p>
        {sides[1].lastMove && <p>Last move: {sides[1].lastMove}</p>}
        <PokemonSprite side={sides[1]} />
      </div>
      <div className="combatant bottom">
        <div className="row" style={{ justifyContent: "space-between" }}><strong>{sides[0].label}</strong><span className="badge green">{battle?.model1 || "you"}</span></div>
        <h3>{sides[0].active}</h3>
        <div className="hp-track"><div className="hp-fill" style={{ width: `${sides[0].hp}%` }} /></div>
        <p>{sides[0].hp}% HP · {sides[0].status}</p>
        {sides[0].lastMove && <p>Last move: {sides[0].lastMove}</p>}
        <PokemonSprite side={sides[0]} />
      </div>
    </div>
  );
}
