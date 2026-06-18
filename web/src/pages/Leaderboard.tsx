import { useEffect, useState } from "react";
import { api, type RatingEntry } from "../api";

export default function Leaderboard() {
  const [entries, setEntries] = useState<RatingEntry[]>([]);
  const [format, setFormat] = useState("");

  const load = () => {
    api.leaderboard(format || undefined).then(setEntries).catch(() => {});
  };

  useEffect(() => { load(); }, [format]);

  return (
    <div>
      <h1>Leaderboard</h1>
      <div style={{ marginBottom: 16 }}>
        <label>
          Format{" "}
          <input placeholder="e.g. gen9randombattle" value={format} onChange={(e) => setFormat(e.target.value)} />
        </label>
      </div>
      <div style={{ background: "#fff", borderRadius: 8, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#eee", textAlign: "left" }}>
              <th style={{ padding: 8 }}>Rank</th>
              <th style={{ padding: 8 }}>Player</th>
              <th style={{ padding: 8 }}>Rating</th>
              <th style={{ padding: 8 }}>RD</th>
              <th style={{ padding: 8 }}>Games</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={e.subject} style={{ borderTop: "1px solid #eee" }}>
                <td style={{ padding: 8 }}>{i + 1}</td>
                <td style={{ padding: 8 }}>{e.subject}</td>
                <td style={{ padding: 8 }}>{Math.round(e.rating)}</td>
                <td style={{ padding: 8 }}>{Math.round(e.rd)}</td>
                <td style={{ padding: 8 }}>{e.games}</td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 16, textAlign: "center", color: "#999" }}>No ratings yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
