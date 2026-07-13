import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type FormatOption, type ModelOption, type SimulationResponse, type Team } from "../api";
import { useAuth } from "../auth";

function ResultTable({ sim }: { sim: SimulationResponse }) {
  type Row = { wins?: number; losses?: number; draws?: number; rating?: number };
  const entries = sim.results_json?.entries as Record<string, Row> | undefined;
  const map = sim.results_json?.results_map as Record<string, Row> | undefined;
  if (entries || map) {
    const rows = Object.entries(entries || map || {}).map(([name, value]) => ({ name, ...value }));
    return <div className="table-wrap"><table><thead><tr><th>Model</th><th>Wins</th><th>Losses</th><th>Draws</th><th>Rating</th></tr></thead><tbody>{rows.map((row) => <tr key={row.name}><td>{row.name}</td><td>{row.wins ?? 0}</td><td>{row.losses ?? 0}</td><td>{row.draws ?? 0}</td><td>{typeof row.rating === "number" ? Math.round(row.rating) : "--"}</td></tr>)}</tbody></table></div>;
  }
  return <pre className="notice">{JSON.stringify(sim.results_json, null, 2)}</pre>;
}

function formatEta(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return `${m}m ${s.toString().padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${(m % 60).toString().padStart(2, "0")}m`;
}

function ProgressPanel({ sim }: { sim: SimulationResponse }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const progress = sim.progress;
  if (!progress) return null;
  const pct = progress.n_battles > 0 ? Math.min(100, (progress.battles_done / progress.n_battles) * 100) : 0;
  const startedAt = new Date(sim.created_at).getTime();
  const elapsedSec = Math.max(0.001, (now - startedAt) / 1000);
  const rate = progress.battles_done / elapsedSec;
  const remaining = rate > 0 ? (progress.n_battles - progress.battles_done) / rate : null;
  const etaText = remaining !== null ? formatEta(remaining) : "";

  return (
    <div className="stack">
      <div className="progress-track" role="progressbar" aria-valuenow={progress.battles_done} aria-valuemin={0} aria-valuemax={progress.n_battles}>
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="progress-meta">
        <span>Battle {progress.battles_done} / {progress.n_battles}</span>
        <span>Wins {progress.wins} · Losses {progress.losses} · Draws {progress.draws}</span>
        <span>{etaText ? `ETA ${etaText}` : "Calculating ETA…"}</span>
      </div>
    </div>
  );
}

export default function Simulations() {
  const { user } = useAuth();
  const [sim, setSim] = useState<SimulationResponse | null>(null);
  const [history, setHistory] = useState<SimulationResponse[]>([]);
  const [formats, setFormats] = useState<FormatOption[]>([]);
  const [modelsOptions, setModelsOptions] = useState<ModelOption[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [mode, setMode] = useState("team_vs_team");
  const [name, setName] = useState("");
  const [format, setFormat] = useState("gen9randombattle");
  const [nBattles, setNBattles] = useState(20);
  const [models, setModels] = useState("random,random");
  const [teamAId, setTeamAId] = useState("");
  const [teamBId, setTeamBId] = useState("");
  const [simId, setSimId] = useState("");
  const [error, setError] = useState("");
  const pollRef = useRef<number | null>(null);

  const stopPolling = () => {
    if (pollRef.current !== null) window.clearInterval(pollRef.current);
    pollRef.current = null;
  };

  const loadMeta = async () => {
    if (!user) return;
    const [formatResult, modelResult, teamResult, historyResult] = await Promise.all([
      api.meta.formats(), api.meta.models(), api.teams.list(), api.simulations.list(10),
    ]);
    setFormats(formatResult);
    setModelsOptions(modelResult);
    setTeams(teamResult);
    setHistory(historyResult);
  };

  useEffect(() => {
    loadMeta().catch((err) => setError(err instanceof Error ? err.message : String(err)));
    return stopPolling;
  }, [user]);

  const poll = (id: string) => {
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      try {
        const result = await api.simulations.get(id);
        setSim(result);
        if (result.status === "finished" || result.status === "failed") {
          stopPolling();
          await loadMeta();
        }
      } catch {
        stopPolling();
      }
    }, 2000);
  };

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSim(null);
    try {
      const modelList = models.split(",").map((m) => m.trim()).filter(Boolean);
      const result = await api.simulations.create({
        name: name || undefined,
        mode,
        format,
        n_battles: nBattles,
        models: modelList,
        team_a_id: teamAId ? Number(teamAId) : undefined,
        team_b_id: teamBId ? Number(teamBId) : undefined,
      });
      setSimId(result.id);
      setSim(result);
      poll(result.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const lookup = async () => {
    if (!simId) return;
    setError("");
    try {
      const result = await api.simulations.lookup(simId);
      setSim(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (!user) return <main className="page"><section className="hero"><span className="eyebrow">Simulations</span><h1>Sign in to run tournaments.</h1></section><Link className="button" to="/signin">Sign in</Link></main>;

  return (
    <main className="page">
      <section className="hero"><span className="eyebrow">Model lab</span><h1>Run battle batches.</h1><p>Compare model matchups with team-vs-team, round-robin, and ladder simulations.</p></section>
      {error && <div className="notice error">{error}</div>}
      <section className="grid two simulations-layout">
        <form className="card stack" onSubmit={create}>
          <h2>Create simulation</h2>
          <label className="field"><span>Name</span><input value={name} onChange={(e) => setName(e.target.value)} maxLength={64} placeholder="Optional, unique name" /></label>
          <label className="field"><span>Mode</span><select value={mode} onChange={(e) => setMode(e.target.value)}><option value="team_vs_team">Team vs Team</option><option value="round_robin">Round Robin</option><option value="ladder">Ladder</option></select></label>
          <label className="field"><span>Format</span><select value={format} onChange={(e) => setFormat(e.target.value)}>{formats.map((fmt) => <option key={fmt.id} value={fmt.id}>{fmt.name}</option>)}</select></label>
          <label className="field"><span>Number of battles</span><input type="number" value={nBattles} onChange={(e) => setNBattles(Number(e.target.value))} min={1} max={500} /></label>
          <label className="field"><span>Models</span><input value={models} onChange={(e) => setModels(e.target.value)} list="model-options" /></label>
          <datalist id="model-options">{modelsOptions.map((model) => <option key={model.name} value={model.name} />)}</datalist>
          <div className="grid two"><label className="field"><span>Team A</span><select value={teamAId} onChange={(e) => setTeamAId(e.target.value)}><option value="">Default/random</option>{teams.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label><label className="field"><span>Team B</span><select value={teamBId} onChange={(e) => setTeamBId(e.target.value)}><option value="">Default/random</option>{teams.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label></div>
          <button className="button" type="submit">Start simulation</button>
        </form>
        <div className="card stack"><h2>Lookup</h2><div className="row"><input placeholder="Simulation name or ID" value={simId} onChange={(e) => setSimId(e.target.value)} /><button className="button secondary" type="button" onClick={() => void lookup()}>Lookup</button></div><h2>Recent</h2>{history.map((item) => <button className="notice" type="button" key={item.id} onClick={() => { setSimId(item.id); setSim(item); }}>{item.name ? `${item.name} · ${item.id} · ${item.mode} · ${item.status}` : `${item.id} · ${item.mode} · ${item.status}`}</button>)}</div>
      </section>
      {sim && <section className="card stack" style={{ marginTop: 16 }}><div className="row"><h2>{sim.name || `Simulation ${sim.id}`}</h2><span className="badge">{sim.status}</span></div><p>{sim.name && `${sim.id} · `}{sim.mode} · {sim.n_battles} battles</p>{sim.progress && <ProgressPanel sim={sim} />}{sim.wins !== null && <p>Wins {sim.wins} · Losses {sim.losses} · Draws {sim.draws} · Win rate {sim.win_rate !== null ? `${(sim.win_rate * 100).toFixed(1)}%` : "?"}</p>}{sim.results_json && <ResultTable sim={sim} />}</section>}
    </main>
  );
}
