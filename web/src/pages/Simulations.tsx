import { useState } from "react";
import { api, type SimulationResponse } from "../api";

export default function Simulations() {
  const [sim, setSim] = useState<SimulationResponse | null>(null);
  const [mode, setMode] = useState("team_vs_team");
  const [format, setFormat] = useState("gen9randombattle");
  const [nBattles, setNBattles] = useState(20);
  const [models, setModels] = useState("");
  const [simId, setSimId] = useState("");
  const [error, setError] = useState("");

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSim(null);
    try {
      const modelsList = models.split(",").map((m) => m.trim()).filter(Boolean);
      const result = await api.simulations.create({
        mode,
        format,
        n_battles: nBattles,
        models: modelsList.length > 0 ? modelsList : undefined,
      });
      setSimId(result.id);
      setSim(result);
      poll(result.id);
    } catch (err: unknown) {
      setError(String(err instanceof Error ? err.message : err));
    }
  };

  const poll = (id: string) => {
    const interval = setInterval(async () => {
      try {
        const s = await api.simulations.get(id);
        setSim(s);
        if (s.status === "finished" || s.status === "failed") clearInterval(interval);
      } catch { clearInterval(interval); }
    }, 2000);
  };

  const lookup = async () => {
    if (!simId) return;
    setError("");
    try {
      const s = await api.simulations.get(simId);
      setSim(s);
    } catch (err: unknown) {
      setError(String(err instanceof Error ? err.message : err));
    }
  };

  return (
    <div>
      <h1>Simulations</h1>
      {error && <div style={{ color: "red", marginBottom: 8 }}>{error}</div>}
      <form onSubmit={create} style={{ background: "#fff", padding: 12, borderRadius: 8, marginBottom: 16, maxWidth: 400 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label>Mode
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="team_vs_team">Team vs Team</option>
              <option value="round_robin">Round Robin</option>
              <option value="ladder">Ladder</option>
            </select>
          </label>
          <label>Format <input value={format} onChange={(e) => setFormat(e.target.value)} /></label>
          <label>Number of Battles <input type="number" value={nBattles} onChange={(e) => setNBattles(Number(e.target.value))} min={1} max={500} /></label>
          <label>Models (comma-separated) <input value={models} onChange={(e) => setModels(e.target.value)} placeholder="cerebras/llama3.3-70b,groq/llama3.3-70b" /></label>
          <button type="submit">Create Simulation</button>
        </div>
      </form>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input placeholder="Simulation ID" value={simId} onChange={(e) => setSimId(e.target.value)} />
        <button onClick={lookup}>Lookup</button>
      </div>

      {sim && (
        <div style={{ background: "#fff", padding: 12, borderRadius: 8 }}>
          <h2>Simulation {sim.id}</h2>
          <p>Status: <strong>{sim.status}</strong></p>
          <p>Mode: {sim.mode} — Battles: {sim.n_battles}</p>
          {sim.wins !== null && <p>Wins: {sim.wins} / Losses: {sim.losses} / Draws: {sim.draws}</p>}
          {sim.win_rate !== null && <p>Win Rate: {(sim.win_rate * 100).toFixed(1)}%</p>}
          {sim.results_json && <pre>{JSON.stringify(sim.results_json, null, 2)}</pre>}
        </div>
      )}
    </div>
  );
}
