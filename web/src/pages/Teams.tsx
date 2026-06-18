import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type FormatOption, type Team } from "../api";
import { useAuth } from "../auth";

function previewSpecies(paste: string): string[] {
  return paste
    .split(/\n\s*\n/)
    .map((block) => block.trim().split("\n")[0]?.replace(/\s*@.*$/, "").trim())
    .filter(Boolean)
    .slice(0, 6) as string[];
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
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const del = async (team: Team) => {
    if (!window.confirm(`Delete team "${team.name}"?`)) return;
    try {
      await api.teams.delete(team.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (!user) {
    return (
      <main className="page">
        <section className="hero"><span className="eyebrow">Teams</span><h1>Sign in to build teams.</h1></section>
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
      {error && <div className="notice error" aria-live="polite">{error}</div>}
      <section className="grid two">
        <form className="card stack" onSubmit={create}>
          <h2>Create team</h2>
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
          {previewSpecies(paste).length === 0 && <p>Paste a team to preview the party list.</p>}
          {previewSpecies(paste).map((species) => <div className="notice" key={species}>{species}</div>)}
        </div>
      </section>

      <section className="card stack" style={{ marginTop: 16 }}>
        <div className="row" style={{ justifyContent: "space-between" }}><h2>Your teams</h2>{loading && <span className="muted">Loading...</span>}</div>
        {teams.length === 0 && <p>No teams yet.</p>}
        <div className="grid two">
          {teams.map((team) => (
            <article className="notice" key={team.id}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong>{team.name}</strong>
                <button className="button ghost" type="button" onClick={() => void del(team)}>Delete</button>
              </div>
              <p>{team.format || "unknown format"} · {team.pokemon_count} Pokémon · {team.is_public ? "public" : "private"}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
