import { useEffect, useState } from "react";
import { api, type FormatOption, type RatingEntry } from "../api";

export default function Leaderboard() {
  const [entries, setEntries] = useState<RatingEntry[]>([]);
  const [formats, setFormats] = useState<FormatOption[]>([]);
  const [format, setFormat] = useState("gen9randombattle");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.meta.formats().then(setFormats).catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const result = await api.leaderboard(format || undefined);
        if (!cancelled) setEntries(result);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [format]);

  return (
    <main className="page">
      <section className="hero">
        <span className="eyebrow">Ratings</span>
        <h1>Model ladder.</h1>
        <p>Glicko-style ratings update after completed battles and expose the strongest current agents per format.</p>
      </section>
      {error && <div className="notice error">{error}</div>}
      <section className="card stack">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <label className="field" style={{ minWidth: 280 }}>
            <span>Format</span>
            <select value={format} onChange={(e) => setFormat(e.target.value)}>
              {formats.map((fmt) => <option key={fmt.id} value={fmt.id}>{fmt.name}</option>)}
              {formats.length === 0 && <option value="gen9randombattle">Gen 9 Random Battle</option>}
            </select>
          </label>
          {loading && <span className="badge">Loading</span>}
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Rank</th>
                <th scope="col">Subject</th>
                <th scope="col">Format</th>
                <th scope="col">Rating</th>
                <th scope="col">RD</th>
                <th scope="col">Games</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, index) => (
                <tr key={`${entry.subject}-${entry.format}`}>
                  <td><span className="badge amber">#{index + 1}</span></td>
                  <td><strong>{entry.subject}</strong></td>
                  <td>{entry.format}</td>
                  <td>{Math.round(entry.rating)}</td>
                  <td>{Math.round(entry.rd)}</td>
                  <td>{entry.games}</td>
                </tr>
              ))}
              {entries.length === 0 && !loading && (
                <tr><td colSpan={6} style={{ textAlign: "center" }}>No ratings yet. Finish a battle to seed the ladder.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
