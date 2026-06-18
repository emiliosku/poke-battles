# poke-battles Implementation Plan

## Scope
Everything except Phase 4 (Docker container pool, OCI production deployment).

---

## Phase 1: Backend Integration (Critical Path)

### 1.1 Wire Orchestrator to BattleService
- [x] `packages/api/src/pokeapi/main.py`: create `BattleService`, call `orchestrator.set_runner()`
- [x] `packages/api/src/pokeapi/orchestrator/__init__.py`: ensure runner signature matches

### 1.2 Record Raw Protocol Lines
- [x] `packages/engine/src/pokeengine/player.py`: add `_raw_logs` dict, capture raw lines in `_handle_battle_message`
- [x] `packages/engine/src/pokeengine/events.py`: add `raw_log` to `BattleResult`

### 1.3 Add Raw Log to Replay Model + Wire Creation
- [x] `packages/api/src/pokeapi/db/models.py`: add `raw_log` column to `Replay`
- [x] `packages/api/src/pokeapi/routes/battles.py`: create `Replay` record in `on_complete`
- [x] `packages/api/src/pokeapi/services/__init__.py`: expose raw_log from `BattleService.run_battle()`

### 1.4 Add Raw WebSocket Endpoint + Live Broadcasting
- [x] `packages/api/src/pokeapi/routes/ws.py`: add `/ws/battles/{battle_id}/raw` endpoint
- [x] `packages/api/src/pokeapi/services/__init__.py`: broadcast raw lines during battle via `ConnectionManager`

### 1.5 Wire Rating Updates on Battle Completion
- [x] `packages/api/src/pokeapi/routes/battles.py`: call `rate_pair()` in `on_complete`, update `Rating` DB records

### 1.6 Enable Simulation Execution
- [x] `packages/api/src/pokeapi/services/__init__.py`: add `run_simulation()` method
- [x] `packages/api/src/pokeapi/routes/simulations.py`: wire background worker
- [x] `packages/api/src/pokeapi/orchestrator/__init__.py`: ensure orchestrator supports simulation jobs

### 1.7 Create models.yaml
- [x] Create `models.yaml` at repo root with tiered configs (Cerebras, Groq, Gemini, OpenRouter)
- [x] Wire models.yaml loading into API startup

### 1.8 Wire Langfuse Initialization
- [x] `packages/llm/src/pokellm/clients.py`: initialize `langfuse.Client()` if env vars set
- [x] Wire `on_response` trace recording
- [x] Wire `on_tool_call` span recording

### 1.9 Add Smogon Data to Format Validator
- [x] `packages/engine/src/pokeengine/smogon_data.py`: load and cache Showdown data
- [x] `packages/engine/src/pokeengine/format_validator.py`: add species/move/ability/item validation

---

## Phase 2: Infrastructure

### 2.1 Build Showdown Client Docker Image
- [x] Dockerfile already exists and is correct

### 2.2 Update Docker Compose
- [x] `deploy/docker-compose.yml`: add `showdown-client` service
- [x] `web/nginx.conf`: proxy `/showdown/` to showdown-client container

### 2.3 Fix Makefile
- [x] `make install`: add `pokellm`, `pokeapi`, `pokecli`
- [x] `make typecheck/test/coverage`: cover all packages

### 2.4 Fix CI
- [x] `.github/workflows/ci.yml`: extend typecheck, test, coverage to all packages

---

## Phase 3: Frontend (React + Vite)

### 3.1 Initialize React + Vite Project
- [x] Scaffold `web/` with Vite + React + TypeScript
- [x] Install dependencies: `react`, `react-dom`, `react-router-dom`
- [x] Configure API and WebSocket proxies

### 3.2 Dashboard Page
- [x] `web/src/pages/Dashboard.tsx`: system status, recent battles, quick actions

### 3.3 Teams Page
- [x] `web/src/pages/Teams.tsx`: list, create, delete teams with Showdown paste input

### 3.4 Battle Page
- [x] `web/src/pages/Battle.tsx`: create battle, embed Showdown client iframe, raw protocol log
- [x] WebSocket raw protocol live stream

### 3.5 Simulations Page
- [x] `web/src/pages/Simulations.tsx`: create simulation, poll status, view results

### 3.6 Leaderboard Page
- [x] `web/src/pages/Leaderboard.tsx`: format selector, ranked table

### 3.7 Replays Page
- [x] `web/src/pages/Replays.tsx`: load replay by ID, event log viewer

---

## Decision Log

| # | Decision | Choice |
|---|---|---|
| 1 | Scope | (B) Everything except Phase 4 |
| 2 | Priority order | Frontend before auth |
| 3 | Frontend framework | React + Vite |
| 4 | Frontend scope | All 6 pages |
| 5 | LLM providers | Free-tier + OpenRouter |
| 6 | Langfuse | Wire code only (no account setup) |
| 7 | Simulation modes | All three (team_vs_team, round_robin, ladder) |
| 8 | Live viewer | Embed Showdown client |
| 9 | Replays | Event log only |
| 10 | Showdown client integration | Record raw protocol during battle |
| 11 | Showdown client deployment | Separate container |
| 12 | WebSocket architecture | Two separate endpoints |
| 13 | Simulation API | REST endpoints only |
| 14 | models.yaml | Tiered configs |
| 15 | Format validator Phase 3 | Include Smogon data |
| 16 | Smogon data sourcing | Reuse Showdown server's data |
| 17 | Leaderboard | Per-format ratings |
| 18 | Rate limiting | Skip for now |
| 19 | Makefile/CI | Full coverage |
| 20 | Plan approval | Approved |
