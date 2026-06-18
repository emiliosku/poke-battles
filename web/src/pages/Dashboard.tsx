import { useEffect, useState } from "react";
import { api, type BattleResponse, type RatingEntry, type Team } from "../api";

export default function Dashboard() {
  const [health, setHealth] = useState<{ status: string; version: string; uptime_s: number } | null>(null);
  const [recentBattles, setRecentBattles] = useState<BattleResponse[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [leaderboard, setLeaderboard] = useState<RatingEntry[]>([]);

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
    api.battles.create({ format: "gen9randombattle", player1: { model_name: "random", username: "p1" }, player2: { model_name: "random", username: "p2" } })
      .then(() => {})
      .catch(() => {});
  }, []);

  return (
    <div>
      <h1>Dashboard</h1>
      {health && (
        <div style={{ padding: 12, background: "#e8f5e9", borderRadius: 8, marginBottom: 16 }}>
          <strong>API:</strong> {health.status} (v{health.version}) — uptime: {Math.round(health.uptime_s)}s
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={{ background: "#fff", padding: 12, borderRadius: 8 }}>
          <h2>Teams ({teams.length})</h2>
          {teams.length === 0 && <p style={{ color: "#999" }}>No teams yet. Create one in the Teams page.</p>}
        </div>
        <div style={{ background: "#fff", padding: 12, borderRadius: 8 }}>
          <h2>Recent Battles</h2>
          {recentBattles.length === 0 && <p style={{ color: "#999" }}>No battles yet.</p>}
          {recentBattles.map((b) => (
            <div key={b.id} style={{ padding: "4px 0" }}>
              {b.player1_username} vs {b.player2_username} — <strong>{b.status}</strong>
            </div>
          ))}
        </div>
        <div style={{ background: "#fff", padding: 12, borderRadius: 8 }}>
          <h2>Leaderboard Top 5</h2>
          {leaderboard.length === 0 && <p style={{ color: "#999" }}>No ratings yet.</p>}
        </div>
        <div style={{ background: "#fff", padding: 12, borderRadius: 8 }}>
          <h2>Quick Actions</h2>
          <ul>
            <li><a href="/teams">Manage Teams</a></li>
            <li><a href="/battle">Start a Battle</a></li>
            <li><a href="/simulations">Run Simulations</a></li>
          </ul>
        </div>
      </div>
    </div>
  );
}
