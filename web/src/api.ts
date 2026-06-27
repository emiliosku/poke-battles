const appBase = (import.meta.env.BASE_URL || "/").replace(/\/$/, "");
const defaultApiBase = import.meta.env.DEV ? "/api" : `${appBase}/api`;
const BASE = (import.meta.env.VITE_API_BASE || defaultApiBase).replace(/\/$/, "");

export interface UserProfile {
  id: string;
  display_name: string | null;
  avatar_url: string | null;
}

export interface AuthMeResponse {
  authenticated: boolean;
  user: UserProfile | null;
}

export interface Team {
  id: number;
  name: string;
  format: string | null;
  paste: string;
  pokemon_count: number;
  is_public: boolean;
  created_at: string;
}

export interface PokemonPreview {
  nickname: string | null;
  species: string;
  species_id: string;
  item: string | null;
  ability: string;
  types: string[];
  moves: string[];
}

export interface TeamPreviewResponse {
  pokemon: PokemonPreview[];
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
  events: BattleEvent[];
  raw_log: string | null;
  duration_s: number | null;
  turns: number | null;
}

export interface BattleEvent {
  kind: string;
  turn: number;
  side?: string;
  target?: string;
  detail?: string;
  quantity?: number;
  source?: string;
  raw?: {
    source?: PokemonRef;
    target?: PokemonRef;
    pokemon?: PokemonRef;
    hp?: {
      hp_text?: string;
      hp_current?: number;
      hp_max?: number;
      hp_percent?: number;
      status?: string;
    };
    status?: string;
    move?: string;
  };
}

export interface PokemonRef {
  side?: string;
  slot?: string;
  pokemon?: string;
  species_id?: string;
}

export interface FormatOption {
  id: string;
  name: string;
  generation: string;
  kind: string;
  team_size: number;
  level: number;
  random_team: boolean;
  requires_team: boolean;
  active_slots: number;
  practice_supported: boolean;
  experimental: boolean;
}

// Structured data about a Pokémon you could switch to. Lets the UI show
// the mon's sprite, type, and remaining HP without guessing from a label.
export interface PracticeSwitchPokemon {
  name: string;
  species_id: string;
  types: string[];
  hp_percent: number;
  status: string;
  position: number;
  fainted: boolean;
}

export interface PracticeMoveOption {
  id: string;
  label: string;
  type: string;
  pp: { current: number; max: number };
  target?: string;
  disabled?: boolean;
  disabled_reason?: string;
}

export type PracticeOption =
  | { kind: "move"; id: string; move: PracticeMoveOption }
  | { kind: "switch"; id: string; pokemon: PracticeSwitchPokemon };

// A single, well-typed choice. `phase` tells the UI what to render:
//   - "team_preview": pick N leads from your full team (doubles only)
//   - "switch": forced switch after a faint, pick one replacement
//   - "move": normal turn, pick a move (or switch out of own choice)
//   - "free": no input needed right now (waiting for opponent / resolved)
export interface PracticeActionRequest {
  kind: "practice_action_required";
  request_id: string;
  battle_id: string;
  expires_at: string;
  phase: "team_preview" | "switch" | "move" | "free";
  pick: number;
  options: PracticeOption[];
}

export interface PracticeActionRequest {
  kind: "practice_action_required";
  request_id: string;
  battle_id: string;
  expires_at: string;
  options: PracticeOption[];
}

export interface ModelOption {
  name: string;
  provider: string;
  tier: string;
  supports_tools: boolean;
  rate_limit_rpm: number | null;
  notes: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") q.set(key, String(value));
  }
  const text = q.toString();
  return text ? `?${text}` : "";
}

async function r<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    credentials: "include",
    ...init,
    headers: init?.body
      ? { "Content-Type": "application/json", ...(init.headers || {}) }
      : init?.headers,
  });
  if (!res.ok) {
    const body = await res.text();
    let message = body;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      message = typeof parsed.detail === "string" ? parsed.detail : body;
    } catch {
      // Keep plain text fallback.
    }
    throw new ApiError(res.status, message || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export function authLoginUrl(provider: "github" | "google"): string {
  return `${BASE}/auth/${provider}/login`;
}

export function wsUrl(path: string): string {
  const explicit = import.meta.env.VITE_WS_BASE as string | undefined;
  if (explicit) return `${explicit.replace(/\/$/, "")}${path}`;
  const wsBase = import.meta.env.DEV ? "/ws" : `${appBase}/ws`;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${wsBase}${path}`;
}

export const api = {
  health: () => r<{ status: string; version: string; uptime_s: number }>("/health"),
  auth: {
    me: () => r<AuthMeResponse>("/auth/me"),
    providers: () => r<Record<"github" | "google", boolean>>("/auth/providers"),
    logout: () => r<void>("/auth/logout", { method: "POST" }),
  },
  meta: {
    formats: () => r<FormatOption[]>("/formats"),
    models: () => r<ModelOption[]>("/models"),
  },
  teams: {
    list: () => r<Team[]>("/teams"),
    create: (data: { name: string; paste: string; format?: string; is_public?: boolean }) =>
      r<Team>("/teams", { method: "POST", body: JSON.stringify(data) }),
    preview: (paste: string) =>
      r<TeamPreviewResponse>("/teams/preview", { method: "POST", body: JSON.stringify({ paste }) }),
    get: (id: number) => r<Team>(`/teams/${id}`),
    delete: (id: number) => r<void>(`/teams/${id}`, { method: "DELETE" }),
  },
  battles: {
    list: (limit = 25) => r<BattleResponse[]>(`/battles${query({ limit })}`),
    create: (data: {
      format: string;
      player1: { model_name: string; username: string };
      player2: { model_name: string; username: string };
      team1_id?: number;
      team2_id?: number;
    }) => r<BattleResponse>("/battles", { method: "POST", body: JSON.stringify(data) }),
    get: (id: string) => r<BattleResponse>(`/battles/${id}`),
  },
  practice: {
    create: (data: {
      format: string;
      player_username: string;
      ai_username?: string;
      ai_model: string;
      user_team_id?: number;
      ai_team_id?: number;
      total_timer_s?: number;
    }) => r<BattleResponse>("/practice/battles", { method: "POST", body: JSON.stringify(data) }),
    action: (battleId: string) => r<{ action: PracticeActionRequest | null }>(`/practice/battles/${battleId}/action`),
    submitAction: (battleId: string, data: { request_id: string; option_id: string }) =>
      r<{ accepted: boolean }>(`/practice/battles/${battleId}/actions`, { method: "POST", body: JSON.stringify(data) }),
  },
  simulations: {
    list: (limit = 25) => r<SimulationResponse[]>(`/simulations${query({ limit })}`),
    create: (data: {
      mode: string;
      format?: string;
      team_a_id?: number;
      team_b_id?: number;
      models?: string[];
      n_battles?: number;
    }) => r<SimulationResponse>("/simulations", { method: "POST", body: JSON.stringify(data) }),
    get: (id: string) => r<SimulationResponse>(`/simulations/${id}`),
  },
  leaderboard: (format?: string) => r<RatingEntry[]>(`/leaderboard${query({ format })}`),
  replays: {
    get: (id: string) => r<ReplayResponse>(`/replays/${id}`),
  },
};
