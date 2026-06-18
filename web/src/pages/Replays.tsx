import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, type BattleEvent, type ReplayResponse } from "../api";

function eventText(event: BattleEvent): string {
  const subject = event.raw?.source?.pokemon || event.raw?.target?.pokemon || event.raw?.pokemon?.pokemon || event.source || event.target || event.side || "Battle";
  if (event.kind === "turn_start") return `Turn ${event.turn}`;
  if (event.kind === "move") return `${subject} used ${event.detail}`;
  if (event.kind === "switch") return `${subject} switched (${event.raw?.hp?.hp_text || event.detail || "ready"})`;
  if (event.kind === "damage") return `${subject} took damage: ${event.raw?.hp?.hp_text || event.detail}`;
  if (event.kind === "heal") return `${subject} healed: ${event.raw?.hp?.hp_text || event.detail}`;
  if (event.kind === "faint") return `${subject} fainted`;
  if (event.kind === "battle_end") return `Winner: ${event.detail}`;
  return [event.kind, subject, event.detail].filter(Boolean).join(" · ");
}

export default function Replays() {
  const location = useLocation();
  const initialBattleId = typeof location.state === "object" && location.state && "battleId" in location.state
    ? String(location.state.battleId)
    : "";
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [battleId, setBattleId] = useState(initialBattleId);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<"timeline" | "raw">("timeline");

  const load = async (id = battleId) => {
    if (!id.trim()) return;
    setError("");
    setReplay(null);
    setLoading(true);
    try {
      const result = await api.replays.get(id.trim());
      setReplay(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialBattleId) void load(initialBattleId);
  }, []);

  const lastEvent = replay?.events[replay.events.length - 1];

  return (
    <main className="page">
      <section className="hero">
        <span className="eyebrow">Replay archive</span>
        <h1>Rewind the fight.</h1>
        <p>Load a finished battle and read the normalized Showdown event stream as a tactical timeline.</p>
      </section>
      <section className="card stack">
        <div className="row">
          <input placeholder="Battle ID" value={battleId} onChange={(e) => setBattleId(e.target.value)} />
          <button className="button" type="button" disabled={loading} onClick={() => void load()}>{loading ? "Loading..." : "Load replay"}</button>
        </div>
        {error && <div className="notice error">{error}</div>}
      </section>
      {replay && (
        <section className="grid two" style={{ marginTop: 16 }}>
          <div className="card stack">
            <span className="eyebrow">Summary</span>
            <h2>{replay.battle_id}</h2>
            <p>{replay.format} · {replay.turns ?? "?"} turns · {replay.duration_s?.toFixed(1) ?? "?"}s</p>
            {lastEvent && <div className="notice">Final event: {eventText(lastEvent)}</div>}
            <div className="battlefield" style={{ minHeight: 320 }}>
              <div className="combatant top"><strong>Opponent side</strong><div className="sprite-orb">?</div></div>
              <div className="combatant bottom"><strong>Your side</strong><div className="sprite-orb">?</div></div>
            </div>
          </div>
          <div className="card stack">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <h2>{view === "timeline" ? "Timeline" : "Raw protocol"}</h2>
              <div className="row">
                <button className={`button ${view === "timeline" ? "" : "secondary"}`} type="button" onClick={() => setView("timeline")}>Timeline</button>
                <button className={`button ${view === "raw" ? "" : "secondary"}`} type="button" onClick={() => setView("raw")}>Raw</button>
              </div>
            </div>
            <div className="event-log">
              {view === "timeline" && replay.events.length === 0 && <p>No replay events recorded.</p>}
              {view === "timeline" && replay.events.map((event, index) => (
                <div className="event-line" key={`${event.kind}-${index}`}>
                  <span className="badge">T{event.turn}</span> {eventText(event)}
                </div>
              ))}
              {view === "raw" && !replay.raw_log && <p>No raw protocol stored for this replay.</p>}
              {view === "raw" && replay.raw_log?.split("\n").map((line, index) => (
                <div className="event-line" key={`${line}-${index}`}>{line}</div>
              ))}
            </div>
          </div>
        </section>
      )}
    </main>
  );
}
