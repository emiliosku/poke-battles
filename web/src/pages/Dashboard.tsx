import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type BattleResponse, type RatingEntry, type SimulationResponse, type Team } from "../api";
import { useAuth } from "../auth";

export default function Dashboard() {
  const { user } = useAuth();
  const [health, setHealth] = useState<{ status: string; version: string; uptime_s: number } | null>(null);
  const [battles, setBattles] = useState<BattleResponse[]>([]);
  const [simulations, setSimulations] = useState<SimulationResponse[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [leaderboard, setLeaderboard] = useState<RatingEntry[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setError("");
      try {
        const [healthResult, leaderboardResult] = await Promise.all([api.health(), api.leaderboard("gen9randombattle")]);
        if (cancelled) return;
        setHealth(healthResult);
        setLeaderboard(leaderboardResult.slice(0, 5));
        if (user) {
          const [teamResult, battleResult, simResult] = await Promise.all([
            api.teams.list(),
            api.battles.list(5),
            api.simulations.list(5),
          ]);
          if (cancelled) return;
          setTeams(teamResult);
          setBattles(battleResult);
          setSimulations(simResult);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [user]);

  return (
    <main className="page">
      <section className="hero">
        <span className="eyebrow">LLM battle command</span>
        <h1>Watch models duel like trainers.</h1>
        <p>Create teams, launch AI-vs-AI battles, follow live protocol events, and compare model ratings from one arena.</p>
      </section>
      {error && <div className="notice error">{error}</div>}
      {!user && <div className="notice">Sign in to manage teams, create battles, and run simulations. Leaderboards remain public.</div>}

      <section className="grid three">
        <div className="card">
          <span className="eyebrow">API</span>
          <div className="stat">{health?.status || "..."}</div>
          <p>v{health?.version || "?"} · uptime {health ? Math.round(health.uptime_s) : "?"}s</p>
        </div>
        <div className="card">
          <span className="eyebrow">Teams</span>
          <div className="stat">{user ? teams.length : "--"}</div>
          <p>Your Showdown pastes ready for battle.</p>
        </div>
        <div className="card">
          <span className="eyebrow">Recent battles</span>
          <div className="stat">{user ? battles.length : "--"}</div>
          <p>Latest jobs for your account.</p>
        </div>
      </section>

      <section className="grid two" style={{ marginTop: 16 }}>
        <div className="card stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2>Battle history</h2>
            <Link className="button secondary" to="/battle">Start battle</Link>
          </div>
          {battles.length === 0 && <p>No battles yet.</p>}
          {battles.map((battle) => (
            <Link className="notice" key={battle.id} to={`/battle/${battle.id}`}>
              <strong>{battle.player1_username}</strong> vs <strong>{battle.player2_username}</strong> · {battle.status}
            </Link>
          ))}
        </div>

        <div className="card stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2>Leaderboard</h2>
            <Link className="button secondary" to="/leaderboard">View all</Link>
          </div>
          {leaderboard.length === 0 && <p>No ratings yet.</p>}
          {leaderboard.map((entry, index) => (
            <div className="row" key={entry.subject}>
              <span className="badge amber">#{index + 1}</span>
              <strong>{entry.subject}</strong>
              <span className="muted">{Math.round(entry.rating)} · {entry.games} games</span>
            </div>
          ))}
        </div>
      </section>

      <section className="grid two" style={{ marginTop: 16 }}>
        <div className="card stack">
          <h2>Recent simulations</h2>
          {simulations.length === 0 && <p>No simulations yet.</p>}
          {simulations.map((sim) => (
            <div className="notice" key={sim.id}>{sim.name ? `${sim.name} · ${sim.id} · ${sim.mode} · ${sim.status}` : `${sim.id} · ${sim.mode} · ${sim.status}`}</div>
          ))}
        </div>
        <div className="card stack">
          <h2>Quick actions</h2>
          <Link className="button" to="/teams">Manage teams</Link>
          <Link className="button secondary" to="/simulations">Run simulations</Link>
          <Link className="button secondary" to="/replays">Open replay</Link>
        </div>
      </section>
    </main>
  );
}
