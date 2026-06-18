import { useEffect, useState } from "react";
import { api, type Team } from "../api";

export default function Teams() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [name, setName] = useState("");
  const [paste, setPaste] = useState("");
  const [format, setFormat] = useState("gen9randombattle");
  const [error, setError] = useState("");

  const load = () => api.teams.list().then(setTeams).catch(() => {});
  useEffect(() => { load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api.teams.create({ name, paste, format });
      setName("");
      setPaste("");
      await load();
    } catch (err: unknown) {
      setError(String(err instanceof Error ? err.message : err));
    }
  };

  const del = async (id: number) => {
    try {
      await api.teams.delete(id);
      await load();
    } catch (err: unknown) {
      setError(String(err instanceof Error ? err.message : err));
    }
  };

  return (
    <div>
      <h1>Teams</h1>
      {error && <div style={{ color: "red", marginBottom: 8 }}>{error}</div>}
      <form onSubmit={create} style={{ background: "#fff", padding: 12, borderRadius: 8, marginBottom: 16 }}>
        <h2>Create Team</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 400 }}>
          <input placeholder="Team name" value={name} onChange={(e) => setName(e.target.value)} required />
          <textarea placeholder="Showdown paste format" value={paste} onChange={(e) => setPaste(e.target.value)} rows={6} required />
          <input placeholder="Format (e.g. gen9ou)" value={format} onChange={(e) => setFormat(e.target.value)} />
          <button type="submit">Create Team</button>
        </div>
      </form>
      <div style={{ display: "grid", gap: 12 }}>
        {teams.map((t) => (
          <div key={t.id} style={{ background: "#fff", padding: 12, borderRadius: 8 }}>
            <strong>{t.name}</strong> ({t.format || "no format"}) — {t.pokemon_count} Pokémon
            <button style={{ marginLeft: 8 }} onClick={() => del(t.id)}>Delete</button>
          </div>
        ))}
      </div>
    </div>
  );
}
