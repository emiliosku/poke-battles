import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, type BattleResponse, type ReplayResponse } from "../api";
import { Battlefield, formatEvent, visibleTimelineEvents } from "../battleView";

export default function Replays() {
  const location = useLocation();
  const initialBattleId = typeof location.state === "object" && location.state && "battleId" in location.state
    ? String(location.state.battleId)
    : "";
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [battle, setBattle] = useState<BattleResponse | null>(null);
  const [battleId, setBattleId] = useState(initialBattleId);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<"timeline" | "raw">("timeline");

  const load = async (id = battleId) => {
    if (!id.trim()) return;
    setError("");
    setReplay(null);
    setBattle(null);
    setLoading(true);
    try {
      const [result, battleResult] = await Promise.all([
        api.replays.get(id.trim()),
        api.battles.get(id.trim()).catch(() => null),
      ]);
      setReplay(result);
      setBattle(battleResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialBattleId) void load(initialBattleId);
  }, []);

  const timeline = replay ? visibleTimelineEvents(replay.events) : [];
  const lastEvent = timeline[timeline.length - 1];

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
            {lastEvent && <div className="notice">Final event: {formatEvent(lastEvent)}</div>}
            <Battlefield battle={battle} events={timeline} />
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
              {view === "timeline" && timeline.length === 0 && <p>No replay events recorded.</p>}
              {view === "timeline" && timeline.map((event, index) => (
                <div className="event-line" key={`${event.kind}-${index}`}>
                  <span className="badge">T{event.turn}</span> {formatEvent(event)}
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
