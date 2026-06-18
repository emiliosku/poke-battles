import { useState } from "react";
import { api, type ReplayResponse } from "../api";

const EVENT_LABELS: Record<string, string> = {
  battle_start: "Battle Started",
  turn_start: "Turn",
  turn_end: "Turn End",
  switch: "switched in",
  move: "used",
  damage: "took damage",
  heal: "healed",
  boost: "boosted",
  unboost: "lowered",
  status: "got status",
  cure_status: "cured status",
  faint: "fainted",
  weather_start: "Weather started",
  weather_end: "Weather ended",
  field_start: "Field effect started",
  field_end: "Field effect ended",
  side_condition_start: "Side condition applied",
  side_condition_end: "Side condition removed",
  switch_request: "Waiting for player",
  battle_end: "Battle ended",
  message: "",
};

function formatEvent(ev: Record<string, unknown>): string {
  const kind = ev.kind as string;
  const label = EVENT_LABELS[kind] || kind;
  const turn = ev.turn as number;
  const side = ev.side as string | undefined;
  const detail = ev.detail as string | undefined;
  const source = ev.source as string | undefined;
  const target = ev.target as string | undefined;

  if (kind === "turn_start") return `--- Turn ${turn} ---`;
  if (kind === "move") return `${source} ${label} ${detail}${target ? ` → ${target}` : ""}`;
  if (kind === "switch") return `${side} ${label}: ${detail}`;
  if (kind === "damage") return `${side || target} ${label} (${detail})`;
  if (kind === "faint") return `${target || side} ${label}!`;
  if (kind === "battle_end") return `Winner: ${detail}`;

  const parts = [side, target, source].filter(Boolean);
  const prefix = parts.length ? `${parts.join("/")}: ` : "";
  return `${prefix}${label}${detail ? ` — ${detail}` : ""}`;
}

export default function Replays() {
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [battleId, setBattleId] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    setReplay(null);
    try {
      const r = await api.replays.get(battleId);
      setReplay(r);
    } catch (err: unknown) {
      setError(String(err instanceof Error ? err.message : err));
    }
  };

  return (
    <div>
      <h1>Replays</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input placeholder="Battle ID" value={battleId} onChange={(e) => setBattleId(e.target.value)} style={{ flex: 1 }} />
        <button onClick={load}>Load Replay</button>
      </div>
      {error && <div style={{ color: "red", marginBottom: 8 }}>{error}</div>}
      {replay && (
        <div style={{ background: "#fff", borderRadius: 8, padding: 12 }}>
          <h2>Replay: {replay.battle_id}</h2>
          <p>Format: {replay.format} — Turns: {replay.turns ?? "?"} — Duration: {replay.duration_s?.toFixed(1) ?? "?"}s</p>
          <div style={{ fontFamily: "monospace", fontSize: 13, lineHeight: 1.6, maxHeight: 600, overflowY: "auto", background: "#fafafa", padding: 8, borderRadius: 4 }}>
            {replay.events.length === 0 && <p style={{ color: "#999" }}>No events recorded.</p>}
            {replay.events.map((ev, i) => (
              <div key={i}>{formatEvent(ev)}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
