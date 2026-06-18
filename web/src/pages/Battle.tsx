import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import { api, type BattleResponse } from "../api";

export default function Battle() {
  const { id } = useParams<{ id: string }>();
  const [battle, setBattle] = useState<BattleResponse | null>(null);
  const [format, setFormat] = useState("gen9randombattle");
  const [p1Model, setP1Model] = useState("random");
  const [p2Model, setP2Model] = useState("random");
  const [p1Name, setP1Name] = useState("player-1");
  const [p2Name, setP2Name] = useState("player-2");
  const [error, setError] = useState("");
  const [rawLog, setRawLog] = useState<string[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!id) return;
    const poll = setInterval(async () => {
      try {
        const b = await api.battles.get(id);
        setBattle(b);
        if (b.status === "finished") clearInterval(poll);
      } catch { clearInterval(poll); }
    }, 1000);

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/battles/${id}/raw`);
    ws.onmessage = (ev) => setRawLog((prev) => [...prev.slice(-200), ev.data]);
    wsRef.current = ws;

    return () => {
      clearInterval(poll);
      ws.close();
    };
  }, [id]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const b = await api.battles.create({
        format,
        player1: { model_name: p1Model, username: p1Name },
        player2: { model_name: p2Model, username: p2Name },
      });
      window.location.href = `/battle/${b.id}`;
    } catch (err: unknown) {
      setError(String(err instanceof Error ? err.message : err));
    }
  };

  if (id) {
    return (
      <div>
        <h1>Battle {id}</h1>
        {battle && (
          <div style={{ background: "#fff", padding: 12, borderRadius: 8, marginBottom: 16 }}>
            <p>Status: <strong>{battle.status}</strong></p>
            <p>{battle.player1_username} ({battle.model1}) vs {battle.player2_username} ({battle.model2})</p>
            {battle.winner && <p>Winner: <strong>{battle.winner}</strong></p>}
            {battle.turns && <p>Turns: {battle.turns}</p>}
          </div>
        )}
        <div style={{ display: "flex", gap: 16 }}>
          <div style={{ flex: 1, background: "#fff", borderRadius: 8, minHeight: 400 }}>
            <iframe
              src={`/showdown/`}
              style={{ width: "100%", height: 500, border: "none", borderRadius: 8 }}
              title="Showdown Client"
            />
          </div>
          <div style={{ flex: 1, background: "#111", color: "#0f0", padding: 12, borderRadius: 8, fontFamily: "monospace", fontSize: 12, maxHeight: 500, overflowY: "auto" }}>
            <strong style={{ color: "#fff" }}>Raw Protocol Log</strong>
            {rawLog.map((line, i) => <div key={i}>{line}</div>)}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1>Create Battle</h1>
      {error && <div style={{ color: "red", marginBottom: 8 }}>{error}</div>}
      <form onSubmit={create} style={{ background: "#fff", padding: 12, borderRadius: 8, maxWidth: 400 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label>Format <input value={format} onChange={(e) => setFormat(e.target.value)} /></label>
          <fieldset>
            <legend>Player 1</legend>
            <label>Model <input value={p1Model} onChange={(e) => setP1Model(e.target.value)} placeholder="e.g. random or model key" /></label>
            <label>Username <input value={p1Name} onChange={(e) => setP1Name(e.target.value)} /></label>
          </fieldset>
          <fieldset>
            <legend>Player 2</legend>
            <label>Model <input value={p2Model} onChange={(e) => setP2Model(e.target.value)} placeholder="e.g. random or model key" /></label>
            <label>Username <input value={p2Name} onChange={(e) => setP2Name(e.target.value)} /></label>
          </fieldset>
          <button type="submit">Start Battle</button>
        </div>
      </form>
    </div>
  );
}
