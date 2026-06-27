// Realistic fixtures that exercise both the "happy path" and the broken-sprite path.
// The BattleEvent shape mirrors src/api.ts (BattleEvent, PokemonRef).

export const USER = {
  id: "trainer-red",
  display_name: "Trainer Red",
  avatar_url: null,
};

export const FORMATS = [
  { id: "gen9randombattle", name: "Gen 9 Random Battle", generation: "9", kind: "singles", team_size: 6, level: 84, random_team: true, requires_team: false, active_slots: 1, practice_supported: true, experimental: false },
  { id: "gen9ou", name: "Gen 9 OU", generation: "9", kind: "singles", team_size: 6, level: 100, random_team: false, requires_team: true, active_slots: 1, practice_supported: true, experimental: false },
  { id: "gen9doublesou", name: "Gen 9 Doubles OU", generation: "9", kind: "doubles", team_size: 6, level: 100, random_team: false, requires_team: true, active_slots: 2, practice_supported: true, experimental: false },
  { id: "gen9nationaldexdoublesubers", name: "Gen 9 National Dex Doubles Ubers", generation: "9", kind: "doubles", team_size: 6, level: 100, random_team: false, requires_team: true, active_slots: 2, practice_supported: true, experimental: false },
  { id: "gen3randombattle", name: "Gen 3 Random Battle", generation: "3", kind: "singles", team_size: 6, level: 84, random_team: true, requires_team: false, active_slots: 1, practice_supported: true, experimental: true },
];

export const MODELS = [
  { name: "random", provider: "system", tier: "baseline", supports_tools: false, rate_limit_rpm: null, notes: "Built-in random mover" },
  { name: "gpt-4o-mini", provider: "openai", tier: "fast", supports_tools: true, rate_limit_rpm: 60, notes: "" },
  { name: "gpt-4o", provider: "openai", tier: "standard", supports_tools: true, rate_limit_rpm: 30, notes: "" },
  { name: "claude-3-5-sonnet", provider: "anthropic", tier: "standard", supports_tools: true, rate_limit_rpm: 30, notes: "" },
  { name: "gemini-1.5-pro", provider: "google", tier: "standard", supports_tools: true, rate_limit_rpm: 30, notes: "" },
];

export const TEAMS = [
  { id: 1, name: "Rain Offense", format: "gen9ou", paste: "Kingdra @ Choice Specs\nAbility: Swift Swim\n- Hydro Pump\n- Draco Meteor\n- Hurricane\n- Water Pulse", pokemon_count: 6, is_public: true, created_at: "2026-01-12T18:33:00Z" },
  { id: 2, name: "Trick Room", format: "gen9ou", paste: "Hatterene @ Leftovers\nAbility: Magic Bounce\n- Trick Room\n- Psychic\n- Dazzling Gleam\n- Mystical Fire", pokemon_count: 6, is_public: false, created_at: "2026-01-15T12:01:00Z" },
  { id: 3, name: "Doubles Sun", format: "gen9doublesou", paste: "Torkoal @ Heat Rock\n- Stealth Rock\n- Earthquake\n- Body Press\n- Yawn", pokemon_count: 6, is_public: true, created_at: "2026-02-01T09:21:00Z" },
];

export const TEAM_PASTE = `Garchomp @ Choice Scarf
Ability: Rough Skin
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Earthquake
- Outrage
- Stone Edge
- Stealth Rock

Pikachu @ Light Ball
Ability: Static
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Thunder
- Surf
- Hidden Power Ice
- Volt Tackle

Iron Treads
Ability: Quark Drive
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Earthquake
- Iron Head
- Rapid Spin
- Stealth Rock
`;

export const TEAM_PREVIEW = {
  pokemon: [
    {
      nickname: null,
      species: "Garchomp",
      species_id: "garchomp",
      item: "Choice Scarf",
      ability: "Rough Skin",
      types: ["dragon", "ground"],
      moves: ["Earthquake", "Outrage", "Stone Edge", "Stealth Rock"],
    },
    {
      nickname: null,
      species: "Pikachu",
      species_id: "pikachu",
      item: "Light Ball",
      ability: "Static",
      types: ["electric"],
      moves: ["Thunder", "Surf", "Hidden Power Ice", "Volt Tackle"],
    },
    {
      nickname: null,
      species: "Iron Treads",
      species_id: "irontreads",
      item: null,
      ability: "Quark Drive",
      types: ["ground", "steel"],
      moves: ["Earthquake", "Iron Head", "Rapid Spin", "Stealth Rock"],
    },
  ],
};

export const LEADERBOARD = [
  { subject: "gpt-4o", format: "gen9randombattle", rating: 1742, rd: 38, games: 412 },
  { subject: "claude-3-5-sonnet", format: "gen9randombattle", rating: 1711, rd: 41, games: 397 },
  { subject: "gemini-1.5-pro", format: "gen9randombattle", rating: 1683, rd: 47, games: 351 },
  { subject: "gpt-4o-mini", format: "gen9randombattle", rating: 1602, rd: 58, games: 286 },
  { subject: "random", format: "gen9randombattle", rating: 1504, rd: 72, games: 500 },
  { subject: "gpt-4o", format: "gen9ou", rating: 1811, rd: 33, games: 188 },
  { subject: "claude-3-5-sonnet", format: "gen9ou", rating: 1784, rd: 36, games: 162 },
];

export const HEALTH = { status: "ok", version: "0.1.0", uptime_s: 18234 };

// A finished doubles battle with a mix of species — some have gen5ani sprites
// (pikachu, charizard, ferrothorn) and several Gen 9 mons DO NOT
// (fluttermane, incineroar, roaringmoon). This deliberately exposes the
// broken sprite URL bug.
export const BATTLE_DOUBLES_FINISHED = {
  id: "battle-2026-03-04-0001",
  format: "gen9doublesou",
  status: "finished",
  player1_username: "trainer-red",
  player2_username: "trainer-blue",
  model1: "gpt-4o",
  model2: "claude-3-5-sonnet",
  winner: "trainer-red",
  turns: 14,
  duration_s: 187.2,
  created_at: "2026-03-04T19:00:00Z",
  started_at: "2026-03-04T19:00:08Z",
  finished_at: "2026-03-04T19:03:15Z",
};

export const BATTLE_SINGLES_RUNNING = {
  id: "battle-live-2026-03-09-abcdef",
  format: "gen9randombattle",
  status: "running",
  player1_username: "trainer-red",
  player2_username: "trainer-blue",
  model1: "gpt-4o-mini",
  model2: "gemini-1.5-pro",
  winner: null,
  turns: 6,
  duration_s: 42.0,
  created_at: "2026-03-09T15:00:00Z",
  started_at: "2026-03-09T15:00:04Z",
  finished_at: null,
};

// A doubles battle in progress with a switch + damage + move events for both sides.
export const BATTLE_DOUBLES_EVENTS = [
  { kind: "turn_start", turn: 1 },
  { kind: "switch", turn: 1, side: "p1a: Incineroar", raw: { pokemon: { side: "p1", slot: "a", pokemon: "Incineroar", species_id: "incineroar" }, hp: { hp_percent: 100, status: "active" } } },
  { kind: "switch", turn: 1, side: "p1b: Flutter Mane", raw: { pokemon: { side: "p1", slot: "b", pokemon: "Flutter Mane", species_id: "fluttermane" }, hp: { hp_percent: 100, status: "active" } } },
  { kind: "switch", turn: 1, side: "p2a: Garchomp", raw: { pokemon: { side: "p2", slot: "a", pokemon: "Garchomp", species_id: "garchomp" }, hp: { hp_percent: 100, status: "active" } } },
  { kind: "switch", turn: 1, side: "p2b: Roaring Moon", raw: { pokemon: { side: "p2", slot: "b", pokemon: "Roaring Moon", species_id: "roaringmoon" }, hp: { hp_percent: 100, status: "active" } } },
  { kind: "move", turn: 2, source: "p1a: Incineroar", target: "p2a: Garchomp", detail: "Fake Out", raw: { source: { side: "p1", slot: "a", pokemon: "Incineroar", species_id: "incineroar" }, target: { side: "p2", slot: "a", pokemon: "Garchomp", species_id: "garchomp" } } },
  { kind: "damage", turn: 2, target: "p2a: Garchomp", raw: { target: { side: "p2", slot: "a", pokemon: "Garchomp", species_id: "garchomp" }, hp: { hp_percent: 82, hp_text: "287/350" } } },
  { kind: "move", turn: 2, source: "p1b: Flutter Mane", target: "p2b: Roaring Moon", detail: "Moonblast", raw: { source: { side: "p1", slot: "b", pokemon: "Flutter Mane", species_id: "fluttermane" }, target: { side: "p2", slot: "b", pokemon: "Roaring Moon", species_id: "roaringmoon" } } },
  { kind: "damage", turn: 2, target: "p2b: Roaring Moon", raw: { target: { side: "p2", slot: "b", pokemon: "Roaring Moon", species_id: "roaringmoon" }, hp: { hp_percent: 64, hp_text: "232/363" } } },
  { kind: "move", turn: 2, source: "p2a: Garchomp", target: "p1b: Flutter Mane", detail: "Earthquake", raw: { source: { side: "p2", slot: "a", pokemon: "Garchomp", species_id: "garchomp" }, target: { side: "p1", slot: "b", pokemon: "Flutter Mane", species_id: "fluttermane" } } },
  { kind: "damage", turn: 2, target: "p1b: Flutter Mane", raw: { target: { side: "p1", slot: "b", pokemon: "Flutter Mane", species_id: "fluttermane" }, hp: { hp_percent: 41, hp_text: "124/302" } } },
  { kind: "move", turn: 3, source: "p1a: Incineroar", target: "p2b: Roaring Moon", detail: "Flare Blitz", raw: { source: { side: "p1", slot: "a", pokemon: "Incineroar", species_id: "incineroar" }, target: { side: "p2", slot: "b", pokemon: "Roaring Moon", species_id: "roaringmoon" } } },
  { kind: "damage", turn: 3, target: "p2b: Roaring Moon", raw: { target: { side: "p2", slot: "b", pokemon: "Roaring Moon", species_id: "roaringmoon" }, hp: { hp_percent: 19, hp_text: "69/363" } } },
  { kind: "status", turn: 3, target: "p1a: Incineroar", detail: "brn", raw: { target: { side: "p1", slot: "a", pokemon: "Incineroar", species_id: "incineroar" } } },
  { kind: "turn_start", turn: 4 },
  { kind: "move", turn: 4, source: "p2b: Roaring Moon", target: "p1a: Incineroar", detail: "Knock Off", raw: { source: { side: "p2", slot: "b", pokemon: "Roaring Moon", species_id: "roaringmoon" }, target: { side: "p1", slot: "a", pokemon: "Incineroar", species_id: "incineroar" } } },
  { kind: "damage", turn: 4, target: "p1a: Incineroar", raw: { target: { side: "p1", slot: "a", pokemon: "Incineroar", species_id: "incineroar" }, hp: { hp_percent: 28, hp_text: "112/394" } } },
  { kind: "switch", turn: 5, side: "p1a: Rillaboom", raw: { pokemon: { side: "p1", slot: "a", pokemon: "Rillaboom", species_id: "rillaboom" }, hp: { hp_percent: 100, status: "active" } } },
  { kind: "move", turn: 5, source: "p1b: Flutter Mane", target: "p2b: Roaring Moon", detail: "Moonblast", raw: { source: { side: "p1", slot: "b", pokemon: "Flutter Mane", species_id: "fluttermane" }, target: { side: "p2", slot: "b", pokemon: "Roaring Moon", species_id: "roaringmoon" } } },
  { kind: "damage", turn: 5, target: "p2b: Roaring Moon", raw: { target: { side: "p2", slot: "b", pokemon: "Roaring Moon", species_id: "roaringmoon" }, hp: { hp_percent: 0, hp_text: "0/363" } } },
  { kind: "faint", turn: 5, target: "p2b: Roaring Moon", raw: { target: { side: "p2", slot: "b", pokemon: "Roaring Moon", species_id: "roaringmoon" } } },
  { kind: "battle_end", turn: 14, detail: "trainer-red" },
];

// Replay raw log: just enough lines to fill the right card.
export const REPLAY_RAW_LOG = [
  "|j|!!|gen9doublesou",
  "|j|!!|t1",
  "|switch|p1a: Incineroar|Incineroar, M|100/100",
  "|switch|p1b: Flutter Mane|Flutter Mane, M|100/100",
  "|switch|p2a: Garchomp|Garchomp, M|100/100",
  "|switch|p2b: Roaring Moon|Roaring Moon, M|100/100",
  "|-damage|p2a: Garchomp|287/350",
  "|-damage|p2b: Roaring Moon|232/363",
  "|-damage|p1b: Flutter Mane|124/302",
  "|-damage|p2b: Roaring Moon|69/363",
  "|-status|p1a: Incineroar|brn",
  "|-damage|p1a: Incineroar|112/394",
  "|-damage|p2b: Roaring Moon|0/363",
  "|faint|p2b: Roaring Moon",
  "|win|trainer-red",
].join("\n");

export const REPLAY = {
  battle_id: BATTLE_DOUBLES_FINISHED.id,
  format: BATTLE_DOUBLES_FINISHED.format,
  events: BATTLE_DOUBLES_EVENTS,
  raw_log: REPLAY_RAW_LOG,
  duration_s: 187.2,
  turns: 14,
};

// A normal-turn practice action: 4 moves with type/PP + 3 switches.
// Exercises the 2x2 grid + separate switch row with sprite+name+HP.
export const PRACTICE_ACTION = {
  kind: "practice_action_required",
  request_id: "req-2026-03-09-001",
  battle_id: BATTLE_SINGLES_RUNNING.id,
  expires_at: new Date(Date.now() + 27_000).toISOString(),
  phase: "move",
  pick: 1,
  options: [
    { kind: "move", id: "move 1", move: { id: "move 1", label: "Thunderbolt", type: "electric", pp: { current: 18, max: 24 }, target: "opponent" } },
    { kind: "move", id: "move 2", move: { id: "move 2", label: "Volt Switch", type: "electric", pp: { current: 7, max: 20 }, target: "opponent" } },
    { kind: "move", id: "move 3", move: { id: "move 3", label: "Hidden Power Ice", type: "ice", pp: { current: 12, max: 16 }, target: "opponent" } },
    { kind: "move", id: "move 4", move: { id: "move 4", label: "Encore", type: "normal", pp: { current: 4, max: 5 }, target: "opponent" } },
    { kind: "switch", id: "switch 1", pokemon: { name: "Garchomp", species_id: "garchomp", types: ["dragon", "ground"], hp_percent: 100, status: "active", position: 1, fainted: false } },
    { kind: "switch", id: "switch 2", pokemon: { name: "Ferrothorn", species_id: "ferrothorn", types: ["grass", "steel"], hp_percent: 87, status: "active", position: 2, fainted: false } },
    { kind: "switch", id: "switch 3", pokemon: { name: "Rotom-Wash", species_id: "rotom-wash", types: ["electric", "water"], hp_percent: 53, status: "active", position: 3, fainted: false } },
  ],
};

// Team preview: pick N leads from your full team. Only doubles formats
// have this phase.
export const PRACTICE_ACTION_TEAM_PREVIEW = {
  kind: "practice_action_required",
  request_id: "req-2026-03-09-tp",
  battle_id: BATTLE_SINGLES_RUNNING.id,
  expires_at: new Date(Date.now() + 89_000).toISOString(),
  phase: "team_preview",
  pick: 2,
  options: [
    { kind: "switch", id: "switch 1", pokemon: { name: "Incineroar", species_id: "incineroar", types: ["fire", "dark"], hp_percent: 100, status: "active", position: 1, fainted: false } },
    { kind: "switch", id: "switch 2", pokemon: { name: "Flutter Mane", species_id: "fluttermane", types: ["ghost", "fairy"], hp_percent: 100, status: "active", position: 2, fainted: false } },
    { kind: "switch", id: "switch 3", pokemon: { name: "Rillaboom", species_id: "rillaboom", types: ["grass"], hp_percent: 100, status: "active", position: 3, fainted: false } },
    { kind: "switch", id: "switch 4", pokemon: { name: "Garchomp", species_id: "garchomp", types: ["dragon", "ground"], hp_percent: 100, status: "active", position: 4, fainted: false } },
    { kind: "switch", id: "switch 5", pokemon: { name: "Ferrothorn", species_id: "ferrothorn", types: ["grass", "steel"], hp_percent: 100, status: "active", position: 5, fainted: false } },
    { kind: "switch", id: "switch 6", pokemon: { name: "Rotom-Wash", species_id: "rotom-wash", types: ["electric", "water"], hp_percent: 100, status: "active", position: 6, fainted: false } },
  ],
};

// Forced switch: a Pokémon on the field just fainted. You MUST send in
// a replacement, no moves available.
export const PRACTICE_ACTION_FORCED_SWITCH = {
  kind: "practice_action_required",
  request_id: "req-2026-03-09-fs",
  battle_id: BATTLE_SINGLES_RUNNING.id,
  expires_at: new Date(Date.now() + 29_000).toISOString(),
  phase: "switch",
  pick: 1,
  options: [
    { kind: "switch", id: "switch 1", pokemon: { name: "Garchomp", species_id: "garchomp", types: ["dragon", "ground"], hp_percent: 100, status: "active", position: 1, fainted: false } },
    { kind: "switch", id: "switch 2", pokemon: { name: "Ferrothorn", species_id: "ferrothorn", types: ["grass", "steel"], hp_percent: 64, status: "active", position: 2, fainted: false } },
    { kind: "switch", id: "switch 3", pokemon: { name: "Rotom-Wash", species_id: "rotom-wash", types: ["electric", "water"], hp_percent: 41, status: "brn", position: 3, fainted: false } },
    { kind: "switch", id: "switch 4", pokemon: { name: "Dragapult", species_id: "dragapult", types: ["dragon", "ghost"], hp_percent: 0, status: "fnt", position: 4, fainted: true } },
  ],
};

export const SIMULATIONS = [
  { id: "sim-2026-03-04-0001", status: "finished", mode: "team_vs_team", n_battles: 100, wins: 58, losses: 39, draws: 3, win_rate: 0.58, ci_95: 0.097, results_json: { entries: { "gpt-4o": { wins: 58, losses: 39, draws: 3, rating: 1699 } } }, created_at: "2026-03-04T18:00:00Z", finished_at: "2026-03-04T18:42:00Z" },
  { id: "sim-2026-03-02-0003", status: "finished", mode: "round_robin", n_battles: 60, wins: 33, losses: 22, draws: 5, win_rate: 0.55, ci_95: 0.13, results_json: null, created_at: "2026-03-02T11:00:00Z", finished_at: "2026-03-02T12:15:00Z" },
  { id: "sim-2026-03-01-0007", status: "running", mode: "team_vs_team", n_battles: 200, wins: null, losses: null, draws: null, win_rate: null, ci_95: null, results_json: null, created_at: "2026-03-01T22:00:00Z", finished_at: null },
];

export const BATTLES_HISTORY = [
  { ...BATTLE_DOUBLES_FINISHED },
  { id: "battle-2026-03-03-0009", format: "gen9ou", status: "finished", player1_username: "trainer-red", player2_username: "trainer-blue", model1: "gpt-4o", model2: "gpt-4o-mini", winner: "trainer-red", turns: 22, duration_s: 311.5, created_at: "2026-03-03T17:14:00Z", started_at: "2026-03-03T17:14:05Z", finished_at: "2026-03-03T17:19:16Z" },
  { id: "battle-2026-03-02-0007", format: "gen9randombattle", status: "failed", player1_username: "trainer-red", player2_username: "trainer-blue", model1: "claude-3-5-sonnet", model2: "gpt-4o", winner: null, turns: 4, duration_s: 12.0, created_at: "2026-03-02T19:01:00Z", started_at: "2026-03-02T19:01:02Z", finished_at: "2026-03-02T19:01:14Z" },
];
