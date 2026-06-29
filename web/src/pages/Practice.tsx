import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  wsUrl,
  type BattleEvent,
  type BattleResponse,
  type FormatOption,
  type ModelOption,
  type PracticeActionRequest,
  type PracticeMoveOption,
  type PracticeOption,
  type PracticeSwitchPokemon,
  type PracticeTeamPreviewRequest,
  type Team,
} from "../api";
import { useAuth } from "../auth";
import { Battlefield, formatEvent, visibleTimelineEvents } from "../battleView";

const terminalStatuses = new Set(["finished", "failed", "user_timeout_loss", "timed_out_points", "timed_out_draw"]);

const TYPE_COLORS: Record<string, string> = {
  normal: "#A8A77A", fire: "#EE8130", water: "#6390F0", electric: "#F7D02C",
  grass: "#7AC74C", ice: "#96D9D6", fighting: "#C22E28", poison: "#A33EA1",
  ground: "#E2BF65", flying: "#A98FF3", psychic: "#F95587", bug: "#A6B91A",
  rock: "#B6A136", ghost: "#735797", dragon: "#6F35FC", dark: "#705746",
  steel: "#B7B7CE", fairy: "#D685AD", stellar: "#40C5BB", "???": "#68A090",
};

function typeColor(type?: string): string {
  if (!type) return "#64748b";
  return TYPE_COLORS[type.toLowerCase()] || "#64748b";
}

function useHotkeys(handler: (key: string) => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      const k = e.key.toLowerCase();
      if (/^[1-9]$/.test(k)) handler(k);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handler]);
}

function secondsLeft(expiresAt?: string): number | null {
  if (!expiresAt) return null;
  return Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 1000));
}

const INTRO_MS = 2200;

// --- sprite chain (gen5ani -> ani -> dex) ---------------------------------
function spriteUrls(speciesId: string): string[] {
  if (!speciesId) return [];
  return [
    `https://play.pokemonshowdown.com/sprites/gen5ani/${speciesId}.gif`,
    `https://play.pokemonshowdown.com/sprites/ani/${speciesId}.gif`,
    `https://play.pokemonshowdown.com/sprites/dex/${speciesId}.png`,
  ];
}

function MonSprite({
  speciesId,
  name,
  size = 40,
  spriteId,
}: {
  speciesId: string;
  name: string;
  size?: number;
  spriteId?: string;
}) {
  // Prefer the dash-form sprite id (e.g. "slowking-galar") so the CDN
  // slug matches the variant. Fall back to the id form (e.g.
  // "slowkinggalar") when the payload doesn't ship a separate
  // spriteId — that path is for legacy payloads only.
  const urlId = spriteId || speciesId;
  const urls = spriteUrls(urlId);
  const [idx, setIdx] = useState(0);
  const [failed, setFailed] = useState(urls.length === 0);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    setIdx(0);
    setFailed(urls.length === 0);
    setLoaded(false);
  }, [urlId]);
  if (failed || !urls[idx]) {
    return (
      <div className="mon-icon fallback" style={{ width: size, height: size }} title={name}>
        <span className="mon-icon-initial">{name.charAt(0).toUpperCase()}</span>
      </div>
    );
  }
  return (
    <span className="mon-icon" style={{ width: size, height: size }}>
      {!loaded && <span className="mon-icon-shimmer" />}
      <img
        className={`mon-icon-img ${loaded ? "" : "loading"}`}
        src={urls[idx]}
        width={size}
        height={size}
        alt={name}
        onLoad={() => setLoaded(true)}
        onError={() => (idx + 1 < urls.length ? setIdx(idx + 1) : setFailed(true))}
      />
    </span>
  );
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
  const [teamPreview, setTeamPreview] = useState<PracticeTeamPreviewRequest | null>(null);
  const [teamPreviewPicks, setTeamPreviewPicks] = useState<Set<string>>(new Set());
  const [remaining, setRemaining] = useState<number | null>(null);
  const [wsState, setWsState] = useState("idle");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState("");
  const [introDone, setIntroDone] = useState(false);

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
      api.practice
        .teamPreview(id)
        .then((result) => {
          if (!cancelled) setTeamPreview(result.preview);
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
        const payload = JSON.parse(msg.data) as BattleEvent | PracticeActionRequest | PracticeTeamPreviewRequest | { kind: string };
        if (payload.kind === "practice_action_required") {
          setAction(payload as PracticeActionRequest);
          return;
        }
        if (payload.kind === "practice_action_submitted") {
          setAction(null);
          return;
        }
        if (payload.kind === "practice_team_preview") {
          setTeamPreview(payload as PracticeTeamPreviewRequest);
          setTeamPreviewPicks(new Set());
          return;
        }
        if (payload.kind === "practice_team_preview_submitted") {
          setTeamPreview(null);
          setTeamPreviewPicks(new Set());
          return;
        }
        if (payload.kind === "practice_user_timeout") {
          setAction(null);
          setTeamPreview(null);
          setTeamPreviewPicks(new Set());
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
    if (!id || !battle || !terminalStatuses.has(battle.status) || events.length > 0) return;
    api.replays.get(id)
      .then((replay) => setEvents(replay.events))
      .catch(() => undefined);
  }, [battle, events.length, id]);

  // Pre-battle intro: brief overlay so the user sees "Battle starting"
  // before any action panel appears. Resets on battle id change.
  useEffect(() => {
    setIntroDone(false);
    if (!id) return;
    const t = window.setTimeout(() => setIntroDone(true), INTRO_MS);
    return () => window.clearTimeout(t);
  }, [id]);

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

  const toggleTeamPreviewPick = (optionId: string) => {
    if (!teamPreview) return;
    setTeamPreviewPicks((current) => {
      const next = new Set(current);
      if (next.has(optionId)) {
        next.delete(optionId);
        return next;
      }
      if (next.size >= teamPreview.pick) {
        return next;
      }
      next.add(optionId);
      return next;
    });
  };

  const submitTeamPreview = async () => {
    if (!id || !teamPreview) return;
    const ordered = Array.from(teamPreviewPicks);
    if (ordered.length !== teamPreview.pick) return;
    setSubmitting("preview");
    setError("");
    try {
      await api.practice.submitTeamPreview(id, {
        request_id: teamPreview.request_id,
        option_ids: ordered,
      });
      setTeamPreview(null);
      setTeamPreviewPicks(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting("");
    }
  };

  const moveOptions = useMemo(
    () => (action ? action.options.filter((o): o is Extract<PracticeOption, { kind: "move" }> => o.kind === "move") : []),
    [action],
  );
  const switchOptions = useMemo(
    () => (action ? action.options.filter((o): o is Extract<PracticeOption, { kind: "switch" }> => o.kind === "switch") : []),
    [action],
  );

  useHotkeys((key) => {
    if (!action || submitting) return;
    const idx = Number(key) - 1;
    const opt = action.options[idx];
    if (opt) void submitAction(opt.id);
  });

  function renderMoveButton(opt: Extract<PracticeOption, { kind: "move" }>, index: number) {
    const move = opt.move as PracticeMoveOption;
    const color = typeColor(move.type);
    const ppText = move.pp ? `${move.pp.current}/${move.pp.max}` : null;
    const disabled = Boolean(submitting) || move.disabled;
    return (
      <button
        type="button"
        className="move-button"
        disabled={disabled}
        onClick={() => void submitAction(opt.id)}
        key={opt.id}
        title={move.disabled ? move.disabled_reason : move.label}
        style={{
          borderColor: color,
          background: `linear-gradient(180deg, ${color}28, ${color}10)`,
        }}
      >
        <span className="move-key" aria-hidden="true">{index + 1}</span>
        <span className="move-label">{submitting === opt.id ? "Submitting..." : move.label}</span>
        <span className="move-meta">
          {move.type && <span className="move-type" style={{ background: color }}>{move.type}</span>}
          {ppText && <span className="move-pp">PP {ppText}</span>}
        </span>
      </button>
    );
  }

  function renderSwitchButton(opt: Extract<PracticeOption, { kind: "switch" }>, index: number, hotkey: number) {
    const mon = opt.pokemon as PracticeSwitchPokemon;
    const primaryType = mon.types[0];
    const color = typeColor(primaryType);
    const disabled = Boolean(submitting) || mon.fainted;
    const label = mon.fainted ? `${mon.name} · fainted` : mon.name;
    return (
      <button
        type="button"
        className={`switch-button ${mon.fainted ? "fainted" : ""}`}
        disabled={disabled}
        key={opt.id}
        onClick={() => void submitAction(opt.id)}
        title={`Switch to ${mon.name}`}
        style={{ borderColor: mon.fainted ? "var(--line)" : color }}
      >
        <span className="switch-key" aria-hidden="true">{hotkey}</span>
        <MonSprite speciesId={mon.species_id} spriteId={mon.sprite_id} name={mon.name} size={42} />
        <span className="switch-body">
          <span className="switch-label">{submitting === opt.id ? "Submitting..." : label}</span>
          <span className="switch-meta">
            <span className="hp-track small"><span className="hp-fill" style={{ width: `${mon.hp_percent}%`, background: mon.fainted ? "var(--muted)" : "var(--green)" }} /></span>
            <span className="switch-hp">{mon.hp_percent}%</span>
            {mon.types.length > 0 && <span className="switch-type" style={{ background: color }}>{mon.types[0]}</span>}
            {mon.types[1] && <span className="switch-type" style={{ background: typeColor(mon.types[1]) }}>{mon.types[1]}</span>}
            {mon.status && mon.status !== "active" && !mon.fainted && <span className="switch-status">{mon.status}</span>}
          </span>
        </span>
      </button>
    );
  }

  function renderDoubleOrder(opt: Extract<PracticeOption, { kind: "double" }>, index: number, hotkey: number) {
    const isFirstMove = opt.first.kind === "move";
    const isFirstSwitch = opt.first.kind === "switch";
    const isSecondMove = opt.second.kind === "move";
    const isSecondSwitch = opt.second.kind === "switch";
    const move = isFirstMove ? (opt.first.move as PracticeMoveOption) : isSecondMove ? (opt.second.move as PracticeMoveOption) : null;
    const switchMon = isFirstSwitch ? (opt.first.pokemon as PracticeSwitchPokemon) : isSecondSwitch ? (opt.second.pokemon as PracticeSwitchPokemon) : null;
    const color = typeColor(move?.type || switchMon?.types?.[0]);
    return (
      <button
        type="button"
        className="move-button"
        disabled={Boolean(submitting)}
        onClick={() => void submitAction(opt.id)}
        key={opt.id}
        title={opt.label}
        style={{
          borderColor: color,
          background: `linear-gradient(180deg, ${color}28, ${color}10)`,
        }}
      >
        <span className="move-key" aria-hidden="true">{hotkey}</span>
        <span className="move-label">{submitting === opt.id ? "Submitting..." : opt.label}</span>
        <span className="move-meta">
          {move && move.type && <span className="move-type" style={{ background: color }}>{move.type}</span>}
          {switchMon && switchMon.types[0] && <span className="move-type" style={{ background: typeColor(switchMon.types[0]) }}>{switchMon.types[0]}</span>}
        </span>
      </button>
    );
  }

  // ----- Renders one of three phases for the action card ------------------
  function renderTeamPreview() {
    if (!teamPreview) return null;
    const pick = teamPreview.pick;
    const selected = teamPreviewPicks.size;
    const ready = selected === pick;
    return (
      <>
        <div className="action-timer" role="timer" aria-live="polite">
          <strong>{remaining ?? 0}s</strong> left to pick {pick} lead{pick === 1 ? "" : "s"}
        </div>
        <div className="action-section">
          <h3 className="action-section-title">
            Choose {pick} lead{pick === 1 ? "" : "s"}
            <span className="muted"> {selected}/{pick} selected</span>
          </h3>
          <p className="muted small">
            In Showdown, doubles lead preview lets you decide which Pokémon open the battle. The rest stay on the bench until you switch them in.
          </p>
          <div className="switches-grid">
            {teamPreview.options.map((opt, i) => {
              const mon = opt.pokemon;
              const primaryType = mon.types[0];
              const color = typeColor(primaryType);
              const isSelected = teamPreviewPicks.has(opt.id);
              const order = isSelected ? Array.from(teamPreviewPicks).indexOf(opt.id) + 1 : 0;
              const disabled = submitting === "preview";
              return (
                <button
                  type="button"
                  className={`switch-button${isSelected ? " selected" : ""}`}
                  disabled={disabled}
                  key={opt.id}
                  onClick={() => toggleTeamPreviewPick(opt.id)}
                  title={`Pick ${mon.name} as lead ${order || ""}`.trim()}
                  style={{ borderColor: color }}
                >
                  <span className="switch-key" aria-hidden="true">{i + 1}</span>
                  <MonSprite speciesId={mon.species_id} spriteId={mon.sprite_id} name={mon.name} size={42} />
                  <span className="switch-body">
                    <span className="switch-label">
                      {mon.name}
                      {isSelected ? ` · lead #${order}` : ""}
                    </span>
                    <span className="switch-meta">
                      <span className="hp-track small"><span className="hp-fill" style={{ width: `${mon.hp_percent}%`, background: "var(--green)" }} /></span>
                      <span className="switch-hp">{mon.hp_percent}%</span>
                      {mon.types.length > 0 && <span className="switch-type" style={{ background: color }}>{mon.types[0]}</span>}
                      {mon.types[1] && <span className="switch-type" style={{ background: typeColor(mon.types[1]) }}>{mon.types[1]}</span>}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
          <button
            type="button"
            className="button"
            disabled={!ready || submitting === "preview"}
            onClick={() => void submitTeamPreview()}
          >
            {submitting === "preview" ? "Submitting..." : ready ? "Send leads" : `Pick ${pick - selected} more`}
          </button>
        </div>
      </>
    );
  }

  function renderActionBody() {
    if (teamPreview) {
      return renderTeamPreview();
    }
    if (!action) {
      if (battle && terminalStatuses.has(battle.status)) {
        return <div className="action-waiting muted">Battle {battle.status}.</div>;
      }
      return (
        <div className="action-waiting">
          <span className="spinner" aria-hidden="true" />
          Waiting for Showdown to request your next action...
        </div>
      );
    }

    if (action.phase === "team_preview") {
      return (
        <>
          <div className="action-timer" role="timer" aria-live="polite">
            <strong>{remaining ?? 0}s</strong> left to pick leads
          </div>
          <div className="action-section">
            <h3 className="action-section-title">
              Choose {action.pick} lead{action.pick === 1 ? "" : "s"}
              <span className="muted"> press 1–{action.options.length}</span>
            </h3>
            <p className="muted small">
              In Showdown, doubles lead preview lets you decide which Pokémon open the battle. The rest stay on the bench until you switch them in.
            </p>
            <div className="switches-grid">
              {switchOptions.map((opt, i) => renderSwitchButton(opt, i, i + 1))}
            </div>
          </div>
        </>
      );
    }

    if (action.phase === "switch") {
      return (
        <>
          <div className="action-timer" role="timer" aria-live="polite">
            <strong>{remaining ?? 0}s</strong> left to replace your fainted Pokémon
          </div>
          <div className="action-section">
            <h3 className="action-section-title">
              Send in a replacement
              <span className="muted"> press 1–{action.options.length}</span>
            </h3>
            <div className="switches-grid">
              {switchOptions.map((opt, i) => renderSwitchButton(opt, i, i + 1))}
            </div>
          </div>
        </>
      );
    }

    if (action.phase === "move") {
      const doubleOpts = action.options.filter(
        (o): o is Extract<PracticeOption, { kind: "double" }> => o.kind === "double",
      );
      if (doubleOpts.length > 0) {
        return (
          <>
            <div className="action-timer" role="timer" aria-live="polite">
              <strong>{remaining ?? 0}s</strong> left to choose
              <span className="muted"> · miss the timer and the practice battle is forfeit</span>
            </div>
            <div className="action-section">
              <h3 className="action-section-title">
                Doubles order
                <span className="muted"> press 1–{doubleOpts.length}</span>
              </h3>
              <p className="muted small">
                Each order runs both Pokémon at once. Pick a slot-1 and slot-2 action.
              </p>
              <div className="moves-grid">
                {doubleOpts.map((opt, i) => renderDoubleOrder(opt, i, i + 1))}
              </div>
            </div>
          </>
        );
      }
      return (
        <>
          <div className="action-timer" role="timer" aria-live="polite">
            <strong>{remaining ?? 0}s</strong> left to choose
            <span className="muted"> · miss the timer and the practice battle is forfeit</span>
          </div>
          <div className="action-section">
            <h3 className="action-section-title">Moves <span className="muted">press 1–{moveOptions.length}</span></h3>
            {moveOptions.length === 0 && <p className="muted">No moves available.</p>}
            <div className="moves-grid">
              {moveOptions.map((opt, i) => renderMoveButton(opt, i))}
            </div>
          </div>
          {switchOptions.length > 0 && (
            <div className="action-section">
              <h3 className="action-section-title">
                Or switch out
                <span className="muted"> press {moveOptions.length + 1}–{action.options.length}</span>
              </h3>
              <div className="switches-grid">
                {switchOptions.map((opt, i) => renderSwitchButton(opt, i, moveOptions.length + i + 1))}
              </div>
            </div>
          )}
        </>
      );
    }

    // phase === "free"
    return <div className="action-waiting muted">No action required.</div>;
  }

  if (!user) {
    return <main className="page"><section className="hero"><span className="eyebrow">Practice</span><h1>Sign in to train against AI.</h1></section><Link className="button" to="/signin">Sign in</Link></main>;
  }

  if (id) {
    const phaseLabel =
      teamPreview ? "Choose your leads"
      : action?.phase === "team_preview" ? "Choose your leads"
      : action?.phase === "switch" ? "Forced switch"
      : action?.phase === "move" ? "Choose your action"
      : battle && !terminalStatuses.has(battle.status) ? "Waiting"
      : "Battle ended";

    return (
      <main className="page">
        <section className="hero">
          <span className="eyebrow">Practice battle</span>
          <h1>{id}</h1>
          <p>You vs {battle?.player2_username || "AI"} · {battle?.format || "loading…"}</p>
        </section>
        {error && <div className="notice error">{error}</div>}
        <section className="grid two">
          <Battlefield battle={battle} events={events} />
          {introDone ? (
            <div className="card stack action-card">
              <div className="action-head">
                <h2>{phaseLabel}</h2>
                <span className={`ws-dot ws-${wsState}`} title={`WebSocket: ${wsState}`} />
              </div>
              {battle && <div className="row"><span className="badge">{battle.status}</span><span>{battle.format}</span><span>{battle.turns ?? 0} turns</span></div>}
              {battle?.winner && <div className="notice">Winner: <strong>{battle.winner}</strong></div>}
              {renderActionBody()}
            </div>
          ) : (
            <div className="card stack action-card intro-card" data-testid="battle-intro">
              <div className="action-head">
                <h2>Battle starting</h2>
                <span className={`ws-dot ws-${wsState}`} title={`WebSocket: ${wsState}`} />
              </div>
              <div className="intro-line">
                <span className="intro-eyebrow">You</span>
                <strong>{battle?.player1_username || "you"}</strong>
                <span className="vs">vs</span>
                <strong>{battle?.player2_username || "AI"}</strong>
                <span className="intro-eyebrow">Opponent</span>
              </div>
              <div className="intro-format">{battle?.format || "loading format…"}</div>
              <div className="action-waiting">
                <span className="spinner" aria-hidden="true" />
                Sending Pokémon to the field…
              </div>
              <p className="muted small">
                Move actions unlock once both leads are in. Until then, you can review your team.
              </p>
            </div>
          )}
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
