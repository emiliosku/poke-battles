import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, wsUrl, type BattleEvent, type BattleResponse, type FormatOption, type ModelOption, type PracticeActionRequest, type Team } from "../api";
import { useAuth } from "../auth";
import { Battlefield, formatEvent, visibleTimelineEvents } from "../battleView";

const terminalStatuses = new Set(["finished", "failed", "user_timeout_loss", "timed_out_points", "timed_out_draw"]);

function secondsLeft(expiresAt?: string): number | null {
  if (!expiresAt) return null;
  return Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 1000));
}

export default function Practice() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [formats, setFormats] = useState<FormatOption[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [format, setFormat] = useState("gen9nationaldexdoublesubers");
  const [customFormat, setCustomFormat] = useState("");
  const [playerName, setPlayerName] = useState("trainer");
  const [aiName, setAiName] = useState("AI");
  const [aiModel, setAiModel] = useState("random");
  const [userTeamId, setUserTeamId] = useState("");
  const [aiTeamId, setAiTeamId] = useState("");
  const [totalTimer, setTotalTimer] = useState("180");
  const [battle, setBattle] = useState<BattleResponse | null>(null);
  const [events, setEvents] = useState<BattleEvent[]>([]);
  const [action, setAction] = useState<PracticeActionRequest | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [wsState, setWsState] = useState("idle");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState("");

  const selectedFormat = formats.find((fmt) => fmt.id === format);
  const effectiveFormat = customFormat.trim() || format;
  const requiresTeams = customFormat.trim() ? false : selectedFormat?.requires_team;
  const launchDisabled = creating || Boolean(requiresTeams && (!userTeamId || !aiTeamId));
  const timeline = visibleTimelineEvents(events);

  useEffect(() => {
    Promise.all([api.meta.formats(), api.meta.models(), user ? api.teams.list() : Promise.resolve([])])
      .then(([formatResult, modelResult, teamResult]) => {
        setFormats(formatResult);
        setModels(modelResult);
        setTeams(teamResult);
        if (modelResult[0]) setAiModel(modelResult[0].name);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [user]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    const load = () => {
      api.battles.get(id)
        .then((result) => {
          if (!cancelled) setBattle(result);
        })
        .catch((err) => {
          if (!cancelled) setError(err instanceof Error ? err.message : String(err));
        });
      api.practice.action(id)
        .then((result) => {
          if (!cancelled) setAction(result.action);
        })
        .catch(() => undefined);
    };
    load();
    const interval = window.setInterval(() => {
      if (!battle || !terminalStatuses.has(battle.status)) load();
    }, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [battle, id]);

  useEffect(() => {
    if (!id || !battle || terminalStatuses.has(battle.status)) return;
    const structured = new WebSocket(wsUrl(`/battles/${id}`));
    structured.onopen = () => setWsState("connected");
    structured.onclose = () => setWsState("closed");
    structured.onerror = () => setWsState("error");
    structured.onmessage = (msg) => {
      try {
        const payload = JSON.parse(msg.data) as BattleEvent | PracticeActionRequest | { kind: string };
        if (payload.kind === "practice_action_required") {
          setAction(payload as PracticeActionRequest);
          return;
        }
        if (payload.kind === "practice_action_submitted") {
          setAction(null);
          return;
        }
        if (payload.kind === "practice_user_timeout") {
          setAction(null);
        }
        setEvents((prev) => [...prev, payload as BattleEvent]);
      } catch {
        // Ignore malformed websocket frames.
      }
    };
    return () => structured.close();
  }, [battle, id]);

  useEffect(() => {
    setRemaining(secondsLeft(action?.expires_at));
    if (!action) return;
    const interval = window.setInterval(() => setRemaining(secondsLeft(action.expires_at)), 500);
    return () => window.clearInterval(interval);
  }, [action]);

  useEffect(() => {
    if (!id || battle?.status !== "finished" || events.length > 0) return;
    api.replays.get(id)
      .then((replay) => setEvents(replay.events))
      .catch(() => undefined);
  }, [battle?.status, events.length, id]);

  const teamOptions = useMemo(
    () => teams.filter((team) => !team.format || team.format === effectiveFormat),
    [effectiveFormat, teams],
  );

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setCreating(true);
    try {
      const result = await api.practice.create({
        format: effectiveFormat,
        player_username: playerName,
        ai_username: aiName,
        ai_model: aiModel,
        user_team_id: userTeamId ? Number(userTeamId) : undefined,
        ai_team_id: aiTeamId ? Number(aiTeamId) : undefined,
        total_timer_s: totalTimer ? Number(totalTimer) : undefined,
      });
      navigate(`/practice/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  };

  const submitAction = async (optionId: string) => {
    if (!id || !action) return;
    setSubmitting(optionId);
    setError("");
    try {
      await api.practice.submitAction(id, { request_id: action.request_id, option_id: optionId });
      setAction(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting("");
    }
  };

  if (!user) {
    return <main className="page"><section className="hero"><span className="eyebrow">Practice</span><h1>Sign in to train against AI.</h1></section><Link className="button" to="/signin">Sign in</Link></main>;
  }

  if (id) {
    return (
      <main className="page">
        <section className="hero"><span className="eyebrow">Practice battle</span><h1>{id}</h1><p>Choose within 30 seconds whenever the battle asks for your move.</p></section>
        {error && <div className="notice error">{error}</div>}
        <section className="grid two">
          <Battlefield battle={battle} events={events} />
          <div className="card stack">
            <h2>Controls</h2>
            {battle && <div className="row"><span className="badge">{battle.status}</span><span>{battle.format}</span><span>{battle.turns ?? 0} turns</span></div>}
            {battle?.winner && <div className="notice">Winner: <strong>{battle.winner}</strong></div>}
            <div className="notice">WebSocket: {wsState}</div>
            {action && <div className="notice"><strong>{remaining ?? 0}s</strong> left to choose. Missing the timer forfeits the practice battle.</div>}
            {!action && battle && !terminalStatuses.has(battle.status) && <p>Waiting for Showdown to request your next action...</p>}
            {action && <div className="stack">{action.options.map((option) => <button className="button secondary" type="button" disabled={Boolean(submitting)} key={option.id} onClick={() => void submitAction(option.id)}>{submitting === option.id ? "Submitting..." : option.label}</button>)}</div>}
          </div>
        </section>
        <section className="grid two" style={{ marginTop: 16 }}>
          <div className="card"><h2>Battle narration</h2><div className="event-log">{timeline.length === 0 && <p>Waiting for battle events...</p>}{timeline.map((event, i) => <div className="event-line" key={`${event.kind}-${i}`}>{formatEvent(event)}</div>)}</div></div>
          <div className="card"><h2>Replay</h2>{battle && terminalStatuses.has(battle.status) ? <Link className="button" to="/replays" state={{ battleId: battle.id }}>Open replay</Link> : <p>Replay is saved after the practice battle ends.</p>}</div>
        </section>
      </main>
    );
  }

  return (
    <main className="page">
      <section className="hero"><span className="eyebrow">Practice mode</span><h1>Train against an AI opponent.</h1><p>Practice battles do not affect leaderboard ratings. Your move timer is fixed at 30 seconds.</p></section>
      {error && <div className="notice error">{error}</div>}
      <form className="card stack" onSubmit={create}>
        <div className="grid two">
          <label className="field"><span>Format</span><select value={format} onChange={(e) => setFormat(e.target.value)}>{formats.map((fmt) => <option key={fmt.id} value={fmt.id}>{fmt.name}{fmt.experimental ? " (experimental)" : ""}</option>)}</select></label>
          <label className="field"><span>Custom Showdown format ID</span><input placeholder="Optional, e.g. gen8ou" value={customFormat} onChange={(e) => setCustomFormat(e.target.value)} /></label>
        </div>
        <div className="grid two">
          <fieldset className="stack"><legend>You</legend><label className="field"><span>Username</span><input value={playerName} onChange={(e) => setPlayerName(e.target.value)} required /></label><label className="field"><span>Team</span><select value={userTeamId} onChange={(e) => setUserTeamId(e.target.value)}><option value="">{requiresTeams ? "Required" : "Random/default"}</option>{teamOptions.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label></fieldset>
          <fieldset className="stack"><legend>AI</legend><label className="field"><span>Model</span><select value={aiModel} onChange={(e) => setAiModel(e.target.value)}>{models.map((model) => <option key={model.name} value={model.name}>{model.name}</option>)}</select></label><label className="field"><span>Username</span><input value={aiName} onChange={(e) => setAiName(e.target.value)} required /></label><label className="field"><span>Team</span><select value={aiTeamId} onChange={(e) => setAiTeamId(e.target.value)}><option value="">{requiresTeams ? "Required" : "Random/default"}</option>{teamOptions.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label></fieldset>
        </div>
        <label className="field"><span>Total battle timer</span><select value={totalTimer} onChange={(e) => setTotalTimer(e.target.value)}><option value="">Off</option><option value="180">3 minutes, decide by points</option><option value="300">5 minutes, decide by points</option><option value="600">10 minutes, decide by points</option></select></label>
        {requiresTeams && <div className="notice">{selectedFormat?.name} requires both teams. National Dex formats should use Showdown-valid National Dex teams.</div>}
        <button className="button" type="submit" disabled={launchDisabled}>{creating ? "Starting..." : "Start practice battle"}</button>
      </form>
    </main>
  );
}
