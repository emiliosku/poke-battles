# pokeapi

FastAPI service: REST + WebSocket + orchestrator + DB.

## Endpoints

- `POST /battles` — create a battle (returns id; clients watch via WS)
- `GET /battles/{id}` — battle summary (winner, turns, duration)
- `GET /teams` — list user's teams
- `POST /teams` — create a team from Showdown paste
- `GET /teams/{id}` — get a team
- `DELETE /teams/{id}` — delete a team
- `POST /simulations` — run a simulation (round-robin or team-vs-team)
- `GET /simulations/{id}` — simulation result
- `GET /leaderboard?format=…` — top ratings
- `GET /replays/{id}` — battle replay (event log)
- `WS /ws/battles/{id}` — live event stream

## Local dev

```bash
uv pip install -e "packages/api[dev]"

# SQLite (default)
export DATABASE_URL=sqlite+aiosqlite:///./pokeapi.db

# Postgres (Supabase)
export DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/pokeapi

# Run migrations
alembic upgrade head

# Start server
uvicorn pokeapi.main:app --reload --port 8000
```

## Docker

```bash
docker build -f packages/api/Dockerfile -t pokeapi .
docker run -p 8000:8000 -e DATABASE_URL=… pokeapi
```
