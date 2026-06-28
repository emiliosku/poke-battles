import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type FormatOption,
  type PokemonPreview,
  type Team,
  type TeamPreviewResponse,
} from "../api";
import { useAuth } from "../auth";
import { PokemonSprite, prefetchSprites, useDebouncedValue } from "../sprites";

function previewSpecies(paste: string): string[] {
  return paste
    .split(/\n\s*\n/)
    .map((block) => block.trim().split("\n")[0]?.replace(/\s*@.*$/, "").trim())
    .filter(Boolean)
    .slice(0, 6) as string[];
}

function MoveSlotList({ moves }: { moves: string[] }) {
  const slots = useMemo(() => {
    const filled = moves.slice(0, 4);
    while (filled.length < 4) filled.push("");
    return filled;
  }, [moves]);
  return (
    <div className="paste-preview-moves" aria-label="Moves">
      {slots.map((move, idx) => (
        <div key={`${idx}-${move || "empty"}`} className={`move-slot${move ? "" : " empty"}`}>
          {move || "—"}
        </div>
      ))}
    </div>
  );
}

function PreviewRow({ pokemon }: { pokemon: PokemonPreview }) {
  const label = pokemon.nickname || pokemon.species;
  return (
    <div className="paste-preview-row">
      <div className="paste-preview-sprite">
        <PokemonSprite
          primaryId={pokemon.sprite_id}
          fallbackId={pokemon.species_id}
          label={label}
          className="preview-sprite"
          variant="home"
        />
        <div className="paste-preview-name">{label}</div>
        <div className="paste-preview-meta">
          {pokemon.ability || "No ability"}
        </div>
        <div className="paste-preview-meta">
          {pokemon.item ? `Held: ${pokemon.item}` : "No item"}
        </div>
      </div>
      <MoveSlotList moves={pokemon.moves} />
    </div>
  );
}

function PastePreviewList({ pokemon }: { pokemon: PokemonPreview[] }) {
  return (
    <div className="paste-preview-list" data-testid="paste-preview-list">
      {pokemon.map((p) => (
        <PreviewRow key={p.species_id} pokemon={p} />
      ))}
    </div>
  );
}

function PastePreviewSkeleton({ count }: { count: number }) {
  return (
    <div className="paste-preview-list" aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="paste-preview-row skeleton-row">
          <div className="paste-preview-sprite">
            <div className="sprite-orb empty preview-sprite" />
            <div className="paste-preview-name">Loading…</div>
          </div>
          <div className="paste-preview-moves">
            {Array.from({ length: 4 }).map((__, j) => (
              <div key={j} className="move-slot empty">…</div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function usePreview(
  paste: string,
  isOpen: boolean,
): { pokemon: PokemonPreview[] | null; loading: boolean; error: string } {
  const debounced = useDebouncedValue(paste, 300);
  const trimmed = debounced.trim();
  const [state, setState] = useState<{ pokemon: PokemonPreview[] | null; loading: boolean; error: string }>({
    pokemon: null,
    loading: false,
    error: "",
  });
  const controllerRef = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!isOpen || !trimmed) {
      controllerRef.current?.abort();
      setState({ pokemon: null, loading: false, error: "" });
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    api.teams
      .preview(trimmed)
      .then((res: TeamPreviewResponse) => {
        if (controller.signal.aborted) return;
        // Kick off sprite downloads in parallel so by the time the rows
        // mount, the browser has the images in flight (or already cached).
        // The team preview uses the HOME variant, so pre-warm that chain.
        prefetchSprites(
          res.pokemon.map((p) => ({
            canonical: p.species_id,
            derived: p.sprite_id,
          })),
          "home",
        );
        setState({ pokemon: res.pokemon, loading: false, error: "" });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : String(err);
        setState({ pokemon: null, loading: false, error: message });
      });
    return () => controller.abort();
  }, [trimmed, isOpen]);
  return state;
}

function TeamCard({
  team,
  expanded,
  onToggle,
  onDelete,
}: {
  team: Team;
  expanded: boolean;
  onToggle: () => void;
  onDelete: (team: Team) => Promise<void> | void;
}) {
  const preview = usePreview(team.paste, expanded);
  return (
    <article
      className={`notice team-card${expanded ? " expanded" : ""}`}
      onClick={onToggle}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggle();
        }
      }}
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
    >
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong>{team.name}</strong>
        <span className="row" style={{ gap: 10 }}>
          <span className="muted">{expanded ? "Hide" : "Show"}</span>
          <button
            className="button ghost"
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              void onDelete(team);
            }}
          >
            Delete
          </button>
        </span>
      </div>
      <p>
        {team.format || "unknown format"} · {team.pokemon_count} Pokémon ·{" "}
        {team.is_public ? "public" : "private"}
      </p>
      {expanded && (
        <div className="team-card-preview" onClick={(e) => e.stopPropagation()}>
          {preview.loading && <PastePreviewSkeleton count={team.pokemon_count || 1} />}
          {preview.error && (
            <>
              <div className="notice error">{preview.error}</div>
              <ul className="muted" style={{ paddingLeft: 18, margin: 0 }}>
                {previewSpecies(team.paste).map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </>
          )}
          {preview.pokemon && <PastePreviewList pokemon={preview.pokemon} />}
        </div>
      )}
    </article>
  );
}

export default function Teams() {
  const { user } = useAuth();
  const [teams, setTeams] = useState<Team[]>([]);
  const [formats, setFormats] = useState<FormatOption[]>([]);
  const [name, setName] = useState("");
  const [paste, setPaste] = useState("");
  const [format, setFormat] = useState("gen9randombattle");
  const [isPublic, setIsPublic] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [expandedTeamId, setExpandedTeamId] = useState<number | null>(null);

  const load = async () => {
    if (!user) return;
    setLoading(true);
    setError("");
    try {
      const [teamResult, formatResult] = await Promise.all([api.teams.list(), api.meta.formats()]);
      setTeams(teamResult);
      setFormats(formatResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [user]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api.teams.create({ name, paste, format, is_public: isPublic });
      setName("");
      setPaste("");
      setIsPublic(false);
      await load();
      setCreateOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const del = async (team: Team) => {
    if (!window.confirm(`Delete team "${team.name}"?`)) return;
    try {
      await api.teams.delete(team.id);
      setExpandedTeamId((current) => (current === team.id ? null : current));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const preview = usePreview(paste, createOpen);

  if (!user) {
    return (
      <main className="page">
        <section className="hero">
          <span className="eyebrow">Teams</span>
          <h1>Sign in to build teams.</h1>
        </section>
        <Link className="button" to="/signin">Sign in</Link>
      </main>
    );
  }

  return (
    <main className="page">
      <section className="hero">
        <span className="eyebrow">Team lab</span>
        <h1>Import Showdown squads.</h1>
        <p>Paste a Pokémon Showdown team, validate it on the API, and reuse it in future battle modes.</p>
      </section>

      <section className="card stack" style={{ marginTop: 16 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2>Your teams</h2>
          {loading && <span className="muted">Loading...</span>}
        </div>
        {teams.length === 0 && <p>No teams yet.</p>}
        <div className="grid two">
          {teams.map((team) => (
            <TeamCard
              key={team.id}
              team={team}
              expanded={expandedTeamId === team.id}
              onToggle={() =>
                setExpandedTeamId((current) => (current === team.id ? null : team.id))
              }
              onDelete={del}
            />
          ))}
        </div>
      </section>

      <section className="card stack" style={{ marginTop: 16 }}>
        <button
          type="button"
          className="collapsible-header"
          aria-expanded={createOpen}
          aria-controls="create-team-panel"
          onClick={() => setCreateOpen((v) => !v)}
        >
          <span>Create team</span>
          <span className="chevron" aria-hidden="true">›</span>
        </button>
        {createOpen && (
          <div id="create-team-panel" className="stack" style={{ marginTop: 12 }}>
            {error && <div className="notice error" aria-live="polite">{error}</div>}
            <div className="grid two">
              <form className="card stack" onSubmit={create}>
                <label className="field"><span>Name</span><input value={name} onChange={(e) => setName(e.target.value)} required /></label>
                <label className="field"><span>Format</span>
                  <select value={format} onChange={(e) => setFormat(e.target.value)}>
                    {formats.length === 0 && <option value="gen9randombattle">Gen 9 Random Battle</option>}
                    {formats.map((fmt) => <option key={fmt.id} value={fmt.id}>{fmt.name}</option>)}
                  </select>
                </label>
                <label className="field"><span>Showdown paste</span><textarea rows={13} value={paste} onChange={(e) => setPaste(e.target.value)} required /></label>
                <label className="row"><input style={{ width: "auto" }} type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} /> Public team</label>
                <button className="button" type="submit">Create team</button>
              </form>

              <div className="card stack">
                <h2>Paste preview</h2>
                {!paste.trim() && <p>Paste a team to preview the party list.</p>}
                {paste.trim() && preview.loading && <PastePreviewSkeleton count={Math.max(1, preview.pokemon?.length || 1)} />}
                {paste.trim() && preview.error && (
                  <>
                    <div className="notice error">{preview.error}</div>
                    {previewSpecies(paste).length === 0 ? (
                      <p className="muted">No Pokémon detected.</p>
                    ) : (
                      <ul className="muted" style={{ paddingLeft: 18, margin: 0 }}>
                        {previewSpecies(paste).map((s) => (
                          <li key={s}>{s}</li>
                        ))}
                      </ul>
                    )}
                  </>
                )}
                {paste.trim() && preview.pokemon && preview.pokemon.length > 0 && (
                  <PastePreviewList pokemon={preview.pokemon} />
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
