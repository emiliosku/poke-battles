import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ApiError,
  api,
  type BattleEvent,
  type BattleResponse,
  type ReplayAnnotation,
  type ReplayResponse,
  type ReplayTeamSnapshot,
} from "../api";
import { Battlefield, formatEvent, visibleTimelineEvents } from "../battleView";
import { PokemonSprite } from "../sprites";

const PAGE_SIZE = 12;
const speeds = [0.5, 1, 1.5, 2, 4];

// TODO(replay-showdown): validate raw logs and add an optional self-hosted
// Showdown viewer after native parser fidelity is sufficient.

function displayDate(value: string | null): string {
  if (!value) return "Unknown time";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

function duration(value: number | null): string {
  if (value === null) return "?";
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return minutes ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function playerLabel(replay: ReplayResponse): string {
  return `${replay.player1.username} vs ${replay.player2.username}`;
}

function replayBattle(replay: ReplayResponse): BattleResponse {
  return {
    id: replay.battle_id,
    format: replay.format,
    status: replay.status,
    player1_username: replay.player1.username,
    player2_username: replay.player2.username,
    model1: replay.player1.model,
    model2: replay.player2.model,
    winner: replay.winner,
    turns: replay.turns,
    duration_s: replay.duration_s,
    created_at: replay.created_at,
    started_at: null,
    finished_at: replay.finished_at,
  };
}

function openingCursor(events: BattleEvent[]): number {
  const seen = new Set<string>();
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    if (event?.kind !== "switch") continue;
    const side = event.raw?.pokemon?.side || event.side?.slice(0, 2);
    if (side) seen.add(side);
    if (seen.has("p1") && seen.has("p2")) return index;
  }
  return Math.min(0, events.length - 1);
}

function TeamStrip({ team, label }: { team: ReplayTeamSnapshot | null; label: string }) {
  if (!team?.roster.length) return <div className="replay-team-empty">{label}: legacy team data unavailable</div>;
  return (
    <div className="replay-team" aria-label={`${label} roster`}>
      <span>{team.name || label}</span>
      <div className="replay-roster">
        {team.roster.map((mon) => (
          <PokemonSprite
            key={`${mon.species_id}-${mon.sprite_id}`}
            primaryId={mon.sprite_id}
            fallbackId={mon.species_id}
            label={mon.species}
            className="replay-roster-sprite"
            variant="home"
          />
        ))}
      </div>
    </div>
  );
}

function ReplayCard({ replay, revealResults }: { replay: ReplayResponse; revealResults: boolean }) {
  const result = replay.winner ? `${replay.winner} won` : replay.status === "finished" ? "Draw" : replay.status;
  return (
    <Link className="replay-card" to={`/replays/${replay.battle_id}`}>
      <div className="replay-card-top">
        <div className="row">
          <span className={`badge ${replay.source === "practice" ? "amber" : ""}`}>{replay.source}</span>
          {replay.is_favorite && <span className="replay-favorite-mark" title="Favorite replay" aria-label="Favorite replay">★</span>}
        </div>
        <span className="replay-date">{displayDate(replay.finished_at || replay.created_at)}</span>
      </div>
      <strong>{playerLabel(replay)}</strong>
      <span className="muted small">{replay.player1.model} · {replay.player2.model}</span>
      <div className="replay-card-rosters">
        <TeamStrip team={replay.team1_snapshot} label={replay.player1.username} />
        <TeamStrip team={replay.team2_snapshot} label={replay.player2.username} />
      </div>
      <div className="replay-card-bottom">
        <span>{replay.format} · {replay.turns ?? "?"} turns · {duration(replay.duration_s)}</span>
        {replay.availability === "unavailable" ? (
          <span className="badge red">Unavailable</span>
        ) : revealResults ? (
          <span className="badge green">{result}</span>
        ) : (
          <span className="badge">Result hidden</span>
        )}
      </div>
      {!!replay.tags?.length && <div className="replay-tag-list">{replay.tags.slice(0, 3).map((tag) => <span className="replay-tag" key={tag}>{tag}</span>)}{replay.tags.length > 3 && <span className="replay-tag">+{replay.tags.length - 3}</span>}</div>}
    </Link>
  );
}

function ReplayLibrary() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get("page") || "1"));
  const search = params.get("search") || "";
  const [searchValue, setSearchValue] = useState(search);
  const [data, setData] = useState<{ items: ReplayResponse[]; total: number } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const revealResults = params.get("results") === "shown";

  const update = (next: Record<string, string | undefined>) => {
    const replacement = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value) replacement.set(key, value);
      else replacement.delete(key);
    }
    setParams(replacement);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    void api.replays.list({
      page,
      page_size: PAGE_SIZE,
      search: params.get("search") || undefined,
      format: params.get("format") || undefined,
      outcome: params.get("outcome") || undefined,
      source: params.get("source") || undefined,
      participant: params.get("participant") || undefined,
      sort: (params.get("sort") as "newest" | "oldest" | "shortest" | "longest" | null) || "newest",
    }).then((result) => {
      if (!cancelled) setData(result);
    }).catch((reason: unknown) => {
      if (reason instanceof ApiError && reason.status === 401) {
        window.sessionStorage.setItem("poke-battles:return-to", `/replays?${params.toString()}`);
        navigate(`/signin?returnTo=${encodeURIComponent(`/replays?${params.toString()}`)}`, { replace: true });
      } else if (!cancelled) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [params, page]);

  const pageCount = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  return (
    <main className="page replay-page">
      <section className="hero replay-library-hero">
        <span className="eyebrow">Replay studio</span>
        <h1>Every battle, playable.</h1>
        <p>Your completed standalone and practice battles become a private archive for review, sharing, and study.</p>
      </section>
      <section className="replay-library-toolbar card flat stack">
        <form className="row" onSubmit={(event) => { event.preventDefault(); update({ search: searchValue || undefined, page: undefined }); }}>
          <input aria-label="Search replays" placeholder="Search teams, players, models, formats" value={searchValue} onChange={(event) => setSearchValue(event.target.value)} />
          <button className="button" type="submit">Search</button>
        </form>
        <div className="replay-filters">
          <select aria-label="Replay source" value={params.get("source") || ""} onChange={(event) => update({ source: event.target.value || undefined, page: undefined })}>
            <option value="">All sources</option><option value="battle">Battles</option><option value="practice">Practice</option>
          </select>
          <input aria-label="Filter by format" placeholder="Format" value={params.get("format") || ""} onChange={(event) => update({ format: event.target.value || undefined, page: undefined })} />
          <input aria-label="Filter by player or model" placeholder="Participant" value={params.get("participant") || ""} onChange={(event) => update({ participant: event.target.value || undefined, page: undefined })} />
          <select aria-label="Replay sort" value={params.get("sort") || "newest"} onChange={(event) => update({ sort: event.target.value, page: undefined })}>
            <option value="newest">Newest completed</option><option value="oldest">Oldest first</option><option value="shortest">Shortest battle</option><option value="longest">Longest battle</option>
          </select>
          <button className="button secondary" type="button" onClick={() => update({ results: revealResults ? undefined : "shown" })}>{revealResults ? "Hide results" : "Reveal results"}</button>
        </div>
      </section>
      {error && <div className="notice error">{error}</div>}
      {loading && <div className="notice">Loading your archive...</div>}
      {!loading && data?.items.length === 0 && (
        <section className="replay-empty card">
          <span className="eyebrow">Your archive is waiting</span>
          <h2>Finish a battle to create your first replay.</h2>
          <p>Standalone battles and practice matches appear here as soon as they complete.</p>
          <div className="row"><Link className="button" to="/battle">Start a battle</Link><Link className="button secondary" to="/practice">Practice a battle</Link></div>
        </section>
      )}
      {!loading && data && data.items.length > 0 && (
        <>
          <div className="replay-grid">{data.items.map((replay) => <ReplayCard key={replay.battle_id} replay={replay} revealResults={revealResults} />)}</div>
          <nav className="replay-pagination" aria-label="Replay pages">
            <button className="button secondary" type="button" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>Previous</button>
            <span>Page {page} of {pageCount}</span>
            <button className="button secondary" type="button" disabled={page >= pageCount} onClick={() => update({ page: String(page + 1) })}>Next</button>
          </nav>
        </>
      )}
    </main>
  );
}

function ReplayPlayer({ replay, shared = false }: { replay: ReplayResponse; shared?: boolean }) {
  const rawEvents = replay.events || [];
  const events = visibleTimelineEvents(rawEvents);
  const eventIndexes = events.map((event) => rawEvents.indexOf(event));
  const [cursor, setCursor] = useState(() => openingCursor(events));
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [railTab, setRailTab] = useState<"timeline" | "study" | "protocol">("timeline");
  const [annotations, setAnnotations] = useState<ReplayAnnotation[]>(replay.annotations);
  const [editingAnnotationId, setEditingAnnotationId] = useState<number | null>(null);
  const [annotationDraft, setAnnotationDraft] = useState({ title: "", note: "", is_highlight: false, is_shared: false });
  const [favorite, setFavorite] = useState(replay.is_favorite || false);
  const [tagText, setTagText] = useState((replay.tags || []).join(", "));
  const [studyMessage, setStudyMessage] = useState("");
  const [shareMessage, setShareMessage] = useState("");
  const [shareScope, setShareScope] = useState<"standard" | "full_study">("standard");
  const [shareUrl, setShareUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const playerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setCursor(openingCursor(events));
    setPlaying(false);
    setRailTab("timeline");
    setAnnotations(replay.annotations);
    setEditingAnnotationId(null);
    setAnnotationDraft({ title: "", note: "", is_highlight: false, is_shared: false });
    setFavorite(replay.is_favorite || false);
    setTagText((replay.tags || []).join(", "));
    setStudyMessage("");
  }, [replay.battle_id]);

  useEffect(() => {
    if (shared || replay.availability !== "available") return;
    let cancelled = false;
    void api.replays.annotations.list(replay.battle_id).then((result) => {
      if (!cancelled) setAnnotations(result);
    }).catch(() => {
      // Replay data already includes annotations; keep it if the refresh fails.
    });
    return () => { cancelled = true; };
  }, [replay.battle_id, replay.availability, shared]);

  useEffect(() => {
    if (!playing || cursor >= events.length - 1) return undefined;
    const timer = window.setTimeout(() => setCursor((value) => Math.min(value + 1, events.length - 1)), Math.max(130, 800 / speed));
    return () => window.clearTimeout(timer);
  }, [playing, cursor, events.length, speed]);

  useEffect(() => {
    if (cursor >= events.length - 1) setPlaying(false);
  }, [cursor, events.length]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement) return;
      if (event.key === " ") { event.preventDefault(); setPlaying((value) => !value); }
      if (event.key === "ArrowRight") { event.preventDefault(); setCursor((value) => Math.min(value + 1, events.length - 1)); }
      if (event.key === "ArrowLeft") { event.preventDefault(); setCursor((value) => Math.max(-1, value - 1)); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [events.length]);

  const createShare = async () => {
    setBusy(true);
    setShareMessage("");
    try {
      const share = await api.replays.share(replay.battle_id, shareScope);
      const url = api.replays.sharePreviewUrl(share.token);
      setShareUrl(url);
      await navigator.clipboard.writeText(url);
      setShareMessage("Share link copied. Creating another link will revoke this one.");
    } catch (reason) {
      setShareMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const revokeShare = async () => {
    setBusy(true);
    try {
      await api.replays.revokeShare(replay.battle_id);
      setShareUrl("");
      setShareMessage("Share link revoked.");
    } catch (reason) {
      setShareMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const removeReplay = async () => {
    if (!window.confirm("Remove this replay, its data, and any share link? The battle result remains in history.")) return;
    setBusy(true);
    try {
      await api.replays.remove(replay.battle_id);
      navigate("/replays");
    } catch (reason) {
      setShareMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const deleteBattle = async () => {
    if (!window.confirm("Permanently delete this battle, replay, and share link? This cannot be undone.")) return;
    setBusy(true);
    try {
      await api.battles.remove(replay.battle_id);
      navigate("/replays");
    } catch (reason) {
      setShareMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const current = cursor >= 0 ? events[cursor] : undefined;
  const selectedEventIndex = cursor >= 0 ? eventIndexes[cursor] : undefined;
  const selectStudyEvent = (eventIndex: number | null, turn: number | null) => {
    const exactIndex = eventIndex === null ? -1 : eventIndexes.indexOf(eventIndex);
    const turnIndex = turn === null ? -1 : events.findIndex((event) => event.turn === turn);
    const nextIndex = exactIndex >= 0 ? exactIndex : turnIndex;
    if (nextIndex >= 0) {
      setPlaying(false);
      setCursor(nextIndex);
    }
  };

  const toggleFavorite = async () => {
    setBusy(true);
    setStudyMessage("");
    try {
      const study = await api.replays.toggleFavorite(replay.battle_id);
      setFavorite(study.is_favorite);
    } catch (reason) {
      setStudyMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const saveTags = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setStudyMessage("");
    try {
      const tags = tagText.split(",").map((tag) => tag.trim()).filter(Boolean);
      const study = await api.replays.setTags(replay.battle_id, tags);
      setTagText(study.tags.join(", "));
    } catch (reason) {
      setStudyMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const saveAnnotation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!current || selectedEventIndex === undefined || selectedEventIndex < 0) {
      setStudyMessage("Select a timeline event before saving a note.");
      return;
    }
    const title = annotationDraft.title.trim();
    if (!title) {
      setStudyMessage("Give this note a title.");
      return;
    }
    setBusy(true);
    setStudyMessage("");
    const data = {
      turn: current.turn,
      event_index: selectedEventIndex,
      title,
      note: annotationDraft.note.trim() || null,
      is_highlight: annotationDraft.is_highlight,
      is_shared: annotationDraft.is_shared,
    };
    try {
      if (editingAnnotationId === null) {
        const annotation = await api.replays.annotations.create(replay.battle_id, data);
        setAnnotations((items) => [...items, annotation]);
      } else {
        const annotation = await api.replays.annotations.update(replay.battle_id, editingAnnotationId, data);
        setAnnotations((items) => items.map((item) => item.id === annotation.id ? annotation : item));
      }
      setEditingAnnotationId(null);
      setAnnotationDraft({ title: "", note: "", is_highlight: false, is_shared: false });
    } catch (reason) {
      setStudyMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const editAnnotation = (annotation: ReplayAnnotation) => {
    setEditingAnnotationId(annotation.id);
    setAnnotationDraft({ title: annotation.title, note: annotation.note || "", is_highlight: annotation.is_highlight, is_shared: annotation.is_shared });
    selectStudyEvent(annotation.event_index, annotation.turn);
  };

  const deleteAnnotation = async (annotationId: number) => {
    setBusy(true);
    setStudyMessage("");
    try {
      await api.replays.annotations.remove(replay.battle_id, annotationId);
      setAnnotations((items) => items.filter((annotation) => annotation.id !== annotationId));
      if (editingAnnotationId === annotationId) {
        setEditingAnnotationId(null);
        setAnnotationDraft({ title: "", note: "", is_highlight: false, is_shared: false });
      }
    } catch (reason) {
      setStudyMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const hasReplay = replay.availability === "available" && events.length > 0;
  if (!hasReplay) {
    return <section className="replay-unavailable card"><span className="eyebrow">Replay unavailable</span><h1>This battle has no playable event record.</h1><p>Its result remains in your history, but playback, sharing, and exports are unavailable.</p>{!shared && <Link className="button" to="/replays">Back to archive</Link>}</section>;
  }

  return (
    <main className={`page replay-player-page ${shared ? "shared-replay" : ""}`}>
      <section className="replay-player-header">
        <div><span className="eyebrow">{shared ? "Shared replay" : "Replay studio"}</span><h1>{playerLabel(replay)}</h1><p>{replay.format} · {replay.turns ?? "?"} turns · {duration(replay.duration_s)} · {displayDate(replay.finished_at || replay.created_at)}</p></div>
        {!shared && <Link className="button secondary" to="/replays">Back to archive</Link>}
      </section>
      {replay.legacy && <div className="notice">Legacy replay: team snapshot metadata was not stored for this battle.</div>}
      <section className="replay-matchup card flat">
        <TeamStrip team={replay.team1_snapshot} label={replay.player1.username} />
        <span className="replay-vs">VS</span>
        <TeamStrip team={replay.team2_snapshot} label={replay.player2.username} />
      </section>
      {!shared && (
        <section className="replay-study-controls card flat">
          <button className={`button ${favorite ? "" : "secondary"}`} type="button" disabled={busy} aria-pressed={favorite} onClick={() => void toggleFavorite()}>{favorite ? "★ Favorited" : "☆ Favorite"}</button>
          <form className="replay-tags-form" onSubmit={(event) => void saveTags(event)}>
            <label htmlFor="replay-tags">Tags</label>
            <input id="replay-tags" value={tagText} onChange={(event) => setTagText(event.target.value)} placeholder="opening, misplay, endgame" />
            <button className="button secondary" type="submit" disabled={busy}>Save tags</button>
          </form>
          {studyMessage && <div className="notice">{studyMessage}</div>}
        </section>
      )}
      {(replay.team1_snapshot?.paste || replay.team2_snapshot?.paste) && (
        <section className="replay-team-sheets">
          {[replay.team1_snapshot, replay.team2_snapshot].map((team, index) => team?.paste && (
            <details key={index}>
              <summary>{index === 0 ? replay.player1.username : replay.player2.username} team sheet</summary>
              <pre>{team.paste}</pre>
            </details>
          ))}
        </section>
      )}
      <section className="replay-player-layout">
        <div className="replay-stage" ref={playerRef}>
          <Battlefield battle={replayBattle(replay)} events={cursor < 0 ? [] : events.slice(0, cursor + 1)} />
          <div className="replay-now" aria-live="polite">{current ? formatEvent(current) : "Pre-battle team preview"}</div>
          <div className="replay-controls">
            <button className="button secondary" type="button" disabled={cursor < 0} onClick={() => setCursor(-1)}>Pre-battle</button>
            <button className="button secondary" type="button" disabled={cursor < 0} onClick={() => setCursor((value) => Math.max(-1, value - 1))}>Previous</button>
            <button className="button" type="button" onClick={() => setPlaying((value) => !value)}>{playing ? "Pause" : "Play"}</button>
            <button className="button secondary" type="button" disabled={cursor >= events.length - 1} onClick={() => setCursor((value) => Math.min(events.length - 1, value + 1))}>Next</button>
            <button className="button secondary" type="button" onClick={() => void playerRef.current?.requestFullscreen?.()}>Theater</button>
            <select aria-label="Playback speed" value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>{speeds.map((value) => <option key={value} value={value}>{value}x</option>)}</select>
          </div>
          <input className="replay-scrubber" aria-label="Replay position" type="range" min={-1} max={events.length - 1} value={cursor} onChange={(event) => { setPlaying(false); setCursor(Number(event.target.value)); }} />
        </div>
        <aside className="replay-analysis card">
          <div className="replay-analysis-heading"><h2>{railTab === "timeline" ? "Timeline" : railTab === "protocol" ? "Protocol" : "Study"}</h2><span className="badge">{cursor < 0 ? "Pre-battle" : `T${current?.turn ?? "?"}`}</span></div>
          <div className="replay-rail-tabs" role="tablist" aria-label="Replay rail">
            <button type="button" role="tab" aria-selected={railTab === "timeline"} className={railTab === "timeline" ? "active" : ""} onClick={() => setRailTab("timeline")}>Timeline</button>
            <button type="button" role="tab" aria-selected={railTab === "study"} className={railTab === "study" ? "active" : ""} onClick={() => setRailTab("study")}>Study</button>
            {!shared && <button type="button" role="tab" aria-selected={railTab === "protocol"} className={railTab === "protocol" ? "active" : ""} onClick={() => setRailTab("protocol")}>Protocol</button>}
          </div>
          {railTab === "timeline" && <div className="replay-timeline">
            <button className={`replay-event ${cursor < 0 ? "active" : ""}`} type="button" onClick={() => { setPlaying(false); setCursor(-1); }}>Pre-battle · teams chosen</button>
            {events.map((event, index) => <button className={`replay-event ${index === cursor ? "active" : ""}`} key={`${event.kind}-${index}`} type="button" onClick={() => { setPlaying(false); setCursor(index); }}><span className="badge">T{event.turn}</span>{formatEvent(event)}</button>)}
          </div>}
          {railTab === "study" && <div className="replay-study-rail">
            <section className="replay-study-section">
              <h3>Key moments</h3>
              {replay.key_moments.length ? replay.key_moments.map((moment, index) => <button className="replay-study-item" type="button" key={`${moment.event_index}-${index}`} onClick={() => selectStudyEvent(moment.event_index, moment.turn)}><span className="badge">T{moment.turn}</span><span><strong>{moment.is_first_faint ? "First faint" : moment.kind}</strong>{moment.target && ` · ${moment.target}`}<small>{moment.detail || "Recorded battle event"}</small></span></button>) : <p className="muted small">No pivotal events were recorded.</p>}
            </section>
            <section className="replay-study-section">
              <h3>Agent rationales</h3>
              {replay.rationales.length ? replay.rationales.map((rationale, index) => <button className="replay-study-item" type="button" key={`${rationale.turn}-${rationale.model}-${index}`} onClick={() => selectStudyEvent(null, rationale.turn)}><span className="badge">T{rationale.turn}</span><span><strong>{rationale.model} · {rationale.action}</strong>{rationale.target && ` → ${rationale.target}`}<small>{rationale.commentary}</small></span></button>) : <p className="muted small">No decision commentary was captured.</p>}
            </section>
            <section className="replay-study-section">
              <h3>{shared ? "Annotations" : "Your annotations"}</h3>
              {annotations.length ? annotations.map((annotation) => <article className="replay-annotation" key={annotation.id}><button className="replay-annotation-anchor" type="button" onClick={() => selectStudyEvent(annotation.event_index, annotation.turn)}><span className="badge">{annotation.turn === null ? "Note" : `T${annotation.turn}`}</span><strong>{annotation.title}</strong>{annotation.is_highlight && <span className="badge amber">Highlight</span>}</button>{annotation.note && <p>{annotation.note}</p>}{!shared && <div className="replay-annotation-actions"><button type="button" onClick={() => editAnnotation(annotation)}>Edit</button><button type="button" onClick={() => void deleteAnnotation(annotation.id)} disabled={busy}>Delete</button></div>}</article>) : <p className="muted small">{shared ? "No shared annotations." : "Add notes to the selected timeline event."}</p>}
              {!shared && <form className="replay-annotation-form" onSubmit={(event) => void saveAnnotation(event)}>
                <span className="muted small">{current ? `Anchored to T${current.turn}: ${formatEvent(current)}` : "Select a timeline event to add a note."}</span>
                <input aria-label="Annotation title" value={annotationDraft.title} onChange={(event) => setAnnotationDraft((draft) => ({ ...draft, title: event.target.value }))} placeholder="What should you remember?" maxLength={120} />
                <textarea aria-label="Annotation note" value={annotationDraft.note} onChange={(event) => setAnnotationDraft((draft) => ({ ...draft, note: event.target.value }))} placeholder="Optional observation" maxLength={2000} rows={3} />
                <div className="replay-annotation-options"><label><input type="checkbox" checked={annotationDraft.is_highlight} onChange={(event) => setAnnotationDraft((draft) => ({ ...draft, is_highlight: event.target.checked }))} /> Highlight</label><label><input type="checkbox" checked={annotationDraft.is_shared} onChange={(event) => setAnnotationDraft((draft) => ({ ...draft, is_shared: event.target.checked }))} /> Include in shares</label></div>
                <div className="row"><button className="button secondary" type="submit" disabled={busy}>{editingAnnotationId === null ? "Add annotation" : "Save annotation"}</button>{editingAnnotationId !== null && <button className="button ghost" type="button" onClick={() => { setEditingAnnotationId(null); setAnnotationDraft({ title: "", note: "", is_highlight: false, is_shared: false }); }}>Cancel</button>}</div>
              </form>}
            </section>
          </div>}
          {railTab === "protocol" && !shared && <pre className="replay-protocol">{replay.raw_log || "No protocol log was stored for this replay."}</pre>}
        </aside>
      </section>
      {!shared && (
        <section className="replay-owner-tools card stack">
          <div><span className="eyebrow">Owner tools</span><h2>Share, export, or remove</h2></div>
          <div className="row">
            <select aria-label="Share scope" value={shareScope} onChange={(event) => setShareScope(event.target.value as "standard" | "full_study")}><option value="standard">Standard share</option><option value="full_study">Full study share</option></select>
            <button className="button" type="button" disabled={busy} onClick={() => void createShare()}>Create and copy link</button>
            <button className="button secondary" type="button" disabled={busy} onClick={() => void revokeShare()}>Revoke link</button>
            <a className="button secondary" href={api.replays.logUrl(replay.battle_id)}>Download .log</a>
            <a className="button secondary" href={api.replays.jsonUrl(replay.battle_id)}>Download .json</a>
            <button className="button ghost" type="button" disabled={busy} onClick={() => void removeReplay()}>Remove replay</button>
            <button className="button ghost" type="button" disabled={busy} onClick={() => void deleteBattle()}>Delete battle</button>
          </div>
          {shareMessage && <div className="notice">{shareMessage}{shareUrl && <><br /><code>{shareUrl}</code></>}</div>}
        </section>
      )}
    </main>
  );
}

function ReplayDetail() {
  const { battleId } = useParams<{ battleId: string }>();
  const navigate = useNavigate();
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!battleId) return;
    let cancelled = false;
    void api.replays.get(battleId).then((result) => { if (!cancelled) setReplay(result); }).catch((reason: unknown) => {
      if (reason instanceof ApiError && reason.status === 401) {
        window.sessionStorage.setItem("poke-battles:return-to", `/replays/${battleId}`);
        navigate(`/signin?returnTo=${encodeURIComponent(`/replays/${battleId}`)}`, { replace: true });
      } else if (!cancelled) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    });
    return () => { cancelled = true; };
  }, [battleId]);
  if (error) return <main className="page"><div className="notice error">{error}</div></main>;
  if (!replay) return <main className="page"><div className="notice">Loading replay...</div></main>;
  return <ReplayPlayer replay={replay} />;
}

export function SharedReplay() {
  const { token } = useParams<{ token: string }>();
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    void api.replays.shared(token).then((result) => { if (!cancelled) setReplay(result); }).catch((reason: unknown) => { if (!cancelled) setError("This shared replay is unavailable or has been revoked."); });
    return () => { cancelled = true; };
  }, [token]);
  if (error) return <main className="page"><section className="replay-unavailable card"><span className="eyebrow">Shared replay</span><h1>{error}</h1><Link className="button" to="/">Open Poké Battles</Link></section></main>;
  if (!replay) return <main className="page"><div className="notice">Loading shared replay...</div></main>;
  return <ReplayPlayer replay={replay} shared />;
}

export default function Replays() {
  return <ReplayLibrary />;
}

export { ReplayDetail };
