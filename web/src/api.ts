const BASE = "/api";

export interface Team {
  id: number;
  name: string;
  format: string | null;
  paste: string;
  pokemon_count: number;
  is_public: boolean;
  created_at: string;
}

export interface BattleResponse {
  id: string;
  format: string;
  status: string;
  player1_username: string;
  player2_username: string;
  model1: string;
  model2: string;
  winner: string | null;
  turns: number | null;
  duration_s: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface SimulationResponse {
  id: string;
  status: string;
  mode: string;
  n_battles: number;
  wins: number | null;
  losses: number | null;
  draws: number | null;
  win_rate: number | null;
  ci_95: number | null;
  results_json: Record<string, unknown> | null;
  created_at: string;
  finished_at: string | null;
}

export interface RatingEntry {
  subject: string;
  format: string;
  rating: number;
  rd: number;
  games: number;
}

export interface ReplayResponse {
  battle_id: string;
  format: string;
  events: Record<string, unknown>[];
  duration_s: number | null;
  turns: number | null;
}

async function r<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => r<{ status: string; version: string; uptime_s: number }>("/health"),

  teams: {
    list: () => r<Team[]>("/teams"),
    create: (data: { name: string; paste: string; format?: string }) =>
      r<Team>("/teams", { method: "POST", body: JSON.stringify(data), headers: { "Content-Type": "application/json" } }),
    get: (id: number) => r<Team>(`/teams/${id}`),
    delete: (id: number) => r<void>(`/teams/${id}`, { method: "DELETE" }),
  },

  battles: {
    create: (data: {
      format: string;
      player1: { model_name: string; username: string };
      player2: { model_name: string; username: string };
      team1_id?: number;
      team2_id?: number;
    }) => r<BattleResponse>("/battles", { method: "POST", body: JSON.stringify(data), headers: { "Content-Type": "application/json" } }),
    get: (id: string) => r<BattleResponse>(`/battles/${id}`),
  },

  simulations: {
    create: (data: {
      mode: string;
      format?: string;
      team_a_id?: number;
      team_b_id?: number;
      models?: string[];
      n_battles?: number;
    }) => r<SimulationResponse>("/simulations", { method: "POST", body: JSON.stringify(data), headers: { "Content-Type": "application/json" } }),
    get: (id: string) => r<SimulationResponse>(`/simulations/${id}`),
  },

  leaderboard: (format?: string) => {
    const q = format ? `?format=${encodeURIComponent(format)}` : "";
    return r<RatingEntry[]>(`/leaderboard${q}`);
  },

  replays: {
    get: (id: string) => r<ReplayResponse>(`/replays/${id}`),
  },
};
