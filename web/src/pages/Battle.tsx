import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, wsUrl, type BattleEvent, type BattleResponse, type FormatOption, type ModelOption, type Team } from "../api";
import { useAuth } from "../auth";

interface SideState {
  label: string;
  active: string;
  hp: number;
  status: string;
  lastMove: string;
}

const initialSides: [SideState, SideState] = [
  { label: "Player 1", active: "Awaiting switch", hp: 100, status: "ready", lastMove: "" },
  { label: "Player 2", active: "Awaiting switch", hp: 100, status: "ready", lastMove: "" },
];

function sideIndex(raw?: string): 0 | 1 {
  return raw?.startsWith("p2") ? 1 : 0;
}

function displayPokemon(raw?: string): string {
  if (!raw) return "Unknown";
  const cleaned = raw.split(":").pop()?.trim() || raw;
  return cleaned.split(",")[0]?.trim() || cleaned;
}

function applyEvent(sides: [SideState, SideState], event: BattleEvent): [SideState, SideState] {
  const next: [SideState, SideState] = [{ ...sides[0] }, { ...sides[1] }];
  if (event.kind === "switch") {
    const idx = sideIndex(event.side);
    next[idx].active = displayPokemon(event.side);
    next[idx].hp = 100;
    next[idx].status = "active";
  }
  if (event.kind === "move") {
    const idx = sideIndex(event.source);
    next[idx].lastMove = event.detail || "move";
  }
  if (event.kind === "damage" || event.kind === "heal") {
    const idx = sideIndex(event.target);
    next[idx].active = displayPokemon(event.target) || next[idx].active;
    if (typeof event.quantity === "number") next[idx].hp = Math.max(0, Math.min(100, event.quantity));
  }
  if (event.kind === "faint") {
    const idx = sideIndex(event.target);
    next[idx].active = displayPokemon(event.target) || next[idx].active;
    next[idx].hp = 0;
    next[idx].status = "fainted";
  }
  if (event.kind === "status") {
    const idx = sideIndex(event.target);
    next[idx].status = event.detail || "status";
  }
  return next;
}

function formatEvent(event: BattleEvent): string {
  if (event.kind === "turn_start") return `Turn ${event.turn}`;
  if (event.kind === "move") return `${displayPokemon(event.source)} used ${event.detail}`;
  if (event.kind === "switch") return `${event.side} switched in ${event.detail || "a Pokémon"}`;
  if (event.kind === "damage") return `${displayPokemon(event.target)} took damage (${event.detail})`;
  if (event.kind === "heal") return `${displayPokemon(event.target)} healed (${event.detail})`;
  if (event.kind === "faint") return `${displayPokemon(event.target)} fainted`;
  if (event.kind === "battle_end") return `Winner: ${event.detail}`;
  return [event.kind, event.side || event.target || event.source, event.detail].filter(Boolean).join(" · ");
}

function Battlefield({ battle, events }: { battle: BattleResponse | null; events: BattleEvent[] }) {
  const sides = events.reduce(applyEvent, initialSides);
  sides[0].label = battle?.player1_username || "Player 1";
  sides[1].label = battle?.player2_username || "Player 2";

  return (
    <div className="battlefield" aria-label="Battlefield viewer">
      <div className="combatant top">
        <div className="row" style={{ justifyContent: "space-between" }}><strong>{sides[1].label}</strong><span className="badge red">{battle?.model2 || "model"}</span></div>
        <h3>{sides[1].active}</h3>
        <div className="hp-track"><div className="hp-fill" style={{ width: `${sides[1].hp}%` }} /></div>
        <p>{sides[1].hp}% HP · {sides[1].status}</p>
        <div className="sprite-orb">{sides[1].active.slice(0, 1)}</div>
      </div>
      <div className="combatant bottom">
        <div className="row" style={{ justifyContent: "space-between" }}><strong>{sides[0].label}</strong><span className="badge green">{battle?.model1 || "model"}</span></div>
        <h3>{sides[0].active}</h3>
        <div className="hp-track"><div className="hp-fill" style={{ width: `${sides[0].hp}%` }} /></div>
        <p>{sides[0].hp}% HP · {sides[0].status}</p>
        <div className="sprite-orb">{sides[0].active.slice(0, 1)}</div>
      </div>
    </div>
  );
}

export default function Battle() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [battle, setBattle] = useState<BattleResponse | null>(null);
  const [formats, setFormats] = useState<FormatOption[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [format, setFormat] = useState("gen9randombattle");
  const [p1Model, setP1Model] = useState("random");
  const [p2Model, setP2Model] = useState("random");
  const [p1Name, setP1Name] = useState("trainer-red");
  const [p2Name, setP2Name] = useState("trainer-blue");
  const [team1Id, setTeam1Id] = useState("");
  const [team2Id, setTeam2Id] = useState("");
  const [error, setError] = useState("");
  const [rawLog, setRawLog] = useState<string[]>([]);
  const [events, setEvents] = useState<BattleEvent[]>([]);
  const [wsState, setWsState] = useState("idle");

  useEffect(() => {
    Promise.all([api.meta.formats(), api.meta.models(), user ? api.teams.list() : Promise.resolve([])])
      .then(([formatResult, modelResult, teamResult]) => {
        setFormats(formatResult);
        setModels(modelResult);
        setTeams(teamResult);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [user]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    const load = async () => {
      try {
        const result = await api.battles.get(id);
        if (!cancelled) setBattle(result);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    };
    void load();
    const poll = window.setInterval(() => {
      void load();
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(poll);
    };
  }, [id]);

  useEffect(() => {
    if (!id) return;
    setEvents([]);
    setRawLog([]);
    const raw = new WebSocket(wsUrl(`/battles/${id}/raw`));
    const structured = new WebSocket(wsUrl(`/battles/${id}`));
    raw.onopen = () => setWsState("connected");
    raw.onclose = () => setWsState("closed");
    raw.onerror = () => setWsState("error");
    raw.onmessage = (ev) => setRawLog((prev) => [...prev.slice(-240), String(ev.data)]);
    structured.onmessage = (ev) => {
      try {
        const event = JSON.parse(String(ev.data)) as BattleEvent;
        setEvents((prev) => [...prev.slice(-300), event]);
      } catch {
        // Ignore non-JSON keepalive messages.
      }
    };
    return () => {
      raw.close();
      structured.close();
    };
  }, [id]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const result = await api.battles.create({
        format,
        player1: { model_name: p1Model, username: p1Name },
        player2: { model_name: p2Model, username: p2Name },
        team1_id: team1Id ? Number(team1Id) : undefined,
        team2_id: team2Id ? Number(team2Id) : undefined,
      });
      navigate(`/battle/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (id) {
    return (
      <main className="page">
        <section className="hero"><span className="eyebrow">Live battle</span><h1>{id}</h1></section>
        {error && <div className="notice error">{error}</div>}
        <section className="grid two">
          <Battlefield battle={battle} events={events} />
          <div className="card stack">
            <h2>Battle control</h2>
            {battle && <div className="row"><span className="badge">{battle.status}</span><span>{battle.format}</span><span>{battle.turns ?? 0} turns</span></div>}
            {battle?.winner && <div className="notice">Winner: <strong>{battle.winner}</strong></div>}
            <div className="notice">WebSocket: {wsState}</div>
            {battle?.status === "finished" && <Link className="button" to="/replays" state={{ battleId: battle.id }}>Open replay</Link>}
          </div>
        </section>
        <section className="grid two" style={{ marginTop: 16 }}>
          <div className="card"><h2>Battle narration</h2><div className="event-log">{events.length === 0 && <p>Waiting for live events...</p>}{events.map((event, i) => <div className="event-line" key={`${event.kind}-${i}`}>{formatEvent(event)}</div>)}</div></div>
          <div className="card"><h2>Raw protocol</h2><div className="event-log">{rawLog.length === 0 && <p>Waiting for raw protocol...</p>}{rawLog.map((line, i) => <div className="event-line" key={`${line}-${i}`}>{line}</div>)}</div></div>
        </section>
      </main>
    );
  }

  if (!user) {
    return <main className="page"><section className="hero"><span className="eyebrow">Battle</span><h1>Sign in to launch battles.</h1></section><Link className="button" to="/signin">Sign in</Link></main>;
  }

  return (
    <main className="page">
      <section className="hero"><span className="eyebrow">Matchmaker</span><h1>Start an AI duel.</h1><p>Select models, optional teams, and watch the match unfold in the arena.</p></section>
      {error && <div className="notice error">{error}</div>}
      <form className="card stack" onSubmit={create}>
        <label className="field"><span>Format</span><select value={format} onChange={(e) => setFormat(e.target.value)}>{formats.map((fmt) => <option key={fmt.id} value={fmt.id}>{fmt.name}</option>)}</select></label>
        <div className="grid two">
          <fieldset className="stack"><legend>Player 1</legend><label className="field"><span>Model</span><select value={p1Model} onChange={(e) => setP1Model(e.target.value)}>{models.map((model) => <option key={model.name} value={model.name}>{model.name}</option>)}</select></label><label className="field"><span>Username</span><input value={p1Name} onChange={(e) => setP1Name(e.target.value)} required /></label><label className="field"><span>Team</span><select value={team1Id} onChange={(e) => setTeam1Id(e.target.value)}><option value="">Random/default</option>{teams.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label></fieldset>
          <fieldset className="stack"><legend>Player 2</legend><label className="field"><span>Model</span><select value={p2Model} onChange={(e) => setP2Model(e.target.value)}>{models.map((model) => <option key={model.name} value={model.name}>{model.name}</option>)}</select></label><label className="field"><span>Username</span><input value={p2Name} onChange={(e) => setP2Name(e.target.value)} required /></label><label className="field"><span>Team</span><select value={team2Id} onChange={(e) => setTeam2Id(e.target.value)}><option value="">Random/default</option>{teams.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label></fieldset>
        </div>
        <div className="notice">Custom team IDs are accepted by the API but engine execution still needs the backend team wiring slice to make them affect the match.</div>
        <button className="button" type="submit">Launch battle</button>
      </form>
    </main>
  );
}
