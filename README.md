# poke-battles

> LLM-powered Pokémon Showdown agents, cloud-hosted. Clean-room rewrite.

A monorepo with 5 packages:

| Package | Description |
|---|---|
| `packages/core` (`pokecore`) | Pure data: 18×18 type chart, Showdown paste parser, formats, Glicko-2 |
| `packages/engine` (`pokeengine`) | poke-env wrapper, Showdown protocol parser, runner, **end-to-end demo** |
| `packages/llm` (`pokellm`) | LLM agent: prompts, tools, memory, multi-provider (LiteLLM) |
| `packages/api` (`pokeapi`) | FastAPI + SQLAlchemy + WebSocket + orchestrator |
| `pokecli` | Command-line client for talking to the API |

## Quickstart (local)

```bash
# Requires Python 3.12+
git clone https://github.com/your-user/poke-battles.git
cd poke-battles
uv venv --python 3.12
uv sync
make ci            # lint + typecheck + test (≈ 9s)
```

## Run a local battle (no API, no LLM)

```bash
# Clones Showdown (~50 MB) on first run
uv run python -m pokeengine.demo
```

Example output:

```
Showdown ready: pid=132850 port=8000
Battle battle-gen9randombattle-89 finished in 7.9s
  turns:  88
  winner: tie
  events (a): 806
  events (b): 806
  top event kinds: [('message', 267), ('switch_request', 99), ('switch', 92), ('turn_start', 88), ('move', 86)]
```

## Run the API

```bash
# SQLite (default), in-memory option: sqlite:///:memory:
export DATABASE_URL=sqlite:///./pokeapi.db
uv run uvicorn pokeapi.main:app --host 0.0.0.0 --port 8000
```

The API:

- `GET  /health` — health check
- `GET  /teams` / `POST /teams?owner_id=…` / `GET /teams/{id}` / `DELETE /teams/{id}`
- `POST /battles` / `GET /battles/{id}` — battle CRUD; `202 Accepted` then poll `/battles/{id}` for status
- `POST /simulations` / `GET /simulations/{id}` — round-robin / team-vs-team
- `GET  /leaderboard?format=…` — top ratings (Glicko-2)
- `GET  /replays/{battle_id}` — full event log
- `WS   /ws/battles/{battle_id}` — live event stream (JSON-per-line)

OpenAPI docs at `http://127.0.0.1:8000/docs`.

## Use the CLI

```bash
uv pip install -e pokecli
export POKECLI_API=http://127.0.0.1:8000

pokecli health
pokecli teams list
pokecli teams add "My team" --paste @team.txt --owner alice
pokecli teams show 1
pokecli battles create random random           # queue a battle; auto-polls until done
pokecli battles show battle-12345              # one-shot status
pokecli battles watch battle-12345             # live WS event stream (Ctrl-C to stop)
pokecli sims run round-robin --team 1 --models random,random --n 20
pokecli sims show sim-abcdef
pokecli leaderboard
```

Run `pokecli --help` for the full subcommand tree.

## Configure LLM providers

Each provider needs its API key in `.env`:

```bash
CEREBRAS_API_KEY=csk-...
OPENROUTER_API_KEY=sk-or-...
GROQ_API_KEY=gsk-...
MISTRAL_API_KEY=...
GEMINI_API_KEY=AIza...
HF_TOKEN=hf_...
```

Then in `models.yaml`:

```yaml
cerebras/llama3.1-8b:
  provider: cerebras
  model_id: cerebras/llama3.1-8b
  tier: free
  rate_limit_rpm: 30

openrouter/qwen3-72b:
  provider: openrouter
  model_id: openrouter/qwen/qwen3-72b-instruct:free
  tier: free
```

## Deployment to OCI

You have two paths: **Docker Compose** (recommended if you have Docker) or **systemd + uv** (lighter, no Docker required). Both target the OCI ARM free tier (4 OCPUs / 24 GB).

### Option A: Docker Compose (easiest)

The compose file in `deploy/docker-compose.yml` brings up four containers:

```bash
# On the OCI VM
git clone https://github.com/your-user/poke-battles.git /opt/poke-battles
cd /opt/poke-battles
cp .env.example .env  # add your API keys
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml logs -f api
```

Verify:

```bash
curl -s http://127.0.0.1:8000/health | jq
# install pokecli on your laptop, not the VM
pip install /opt/poke-battles/pokecli
POKECLI_API=http://<oci-public-ip>:8000 pokecli health
```

To expose the API publicly, open the OCI VCN's port 8000 ingress rule (or put nginx on :80 / :443 in front — the `web/` Dockerfile is a placeholder; replace it with your own static frontend or use the OCI load balancer).

### Option B: systemd (no Docker)

```bash
# On the OCI ARM VM
sudo bash deploy/oci/install.sh
```

What this does:

1. Installs `python3.12`, `git`, `nginx`, `postgresql`
2. Creates a `poke` system user
3. Clones the repo to `/opt/poke-battles`
4. `uv sync` to install Python deps
5. Clones the Showdown server to `packages/engine/server/`
6. Writes `/etc/systemd/system/poke-battles-api.service` (uvicorn on `127.0.0.1:8000`)
7. Writes `/etc/nginx/conf.d/poke-battles.conf` (reverse proxy on `:80`, with `/api/` and `/ws/` proxying to 8000)
8. Enables + starts both services

After install:

```bash
systemctl status poke-battles-api
journalctl -u poke-battles-api -f
sudo -u poke /opt/poke-battles/.venv/bin/pokecli health
```

Add your LLM keys to `/opt/poke-battles/.env`, then `systemctl restart poke-battles-api`.

### TLS (Let's Encrypt)

```bash
sudo dnf install -y certbot python3-certbot-nginx   # or apt-get on Debian
sudo certbot --nginx -d poke-battles.example.com
```

The included nginx config will be auto-updated for HTTPS.

### Persistent data

- `POSTGRES` data: `/var/lib/postgresql/data` (systemd) or the `pgdata` named volume (docker-compose)
- `Showdown` server: `/var/lib/poke-battles/server` (systemd) or the `showdown-data` volume (docker-compose)
- `Battles/replays` (Postgres tables): same as Postgres data

## Architecture

```
                       ┌──────────────────────┐
                       │  Vercel or static CD  │
                       │  Web frontend (next)  │
                       └──────────┬───────────┘
                                  │ HTTPS / WSS
                                  ▼
        ┌───────────────── OCI ARM free-tier VM ─────────────────┐
        │                                                          │
        │   ┌──────────────────┐                                  │
        │   │  FastAPI (uvicorn)│  ← pokeapi.main:app            │
        │   │  :8000            │  REST + WebSocket              │
        │   └────────┬──────────┘                                  │
        │            │                                              │
        │   ┌────────▼────────┐  ┌────────────────┐                │
        │   │  Orchestrator   │  │  Postgres 16   │                │
        │   │  (in-process    │  │  users, teams,  │                │
        │   │   asyncio queue)│  │  battles,       │                │
        │   └────────┬────────┘  │  replays,        │                │
        │            │              │  ratings         │                │
        │            │ spawns                                            │
        │            ▼              └────────────────┘                │
        │   ┌──────────────────┐                                      │
        │   │  Showdown server  │  ← smogon/pokemon-showdown        │
        │   │  (node)           │  :8000 (internal only)              │
        │   └──────────────────┘                                      │
        │                                                              │
        └──────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                          Langfuse Cloud (free tier)
                          - LLM call traces
                          - token usage
                          - error rates
```

## Development

```bash
make help
make install        # install all packages (incl. pokecli)
make ci             # lint + format + typecheck + test + coverage
make demo           # run a real battle
make typecheck      # mypy --strict
make test-cov       # pytest with coverage report
python3 scripts/ci.py   # the same, without `make` installed
```

## Project layout

```
poke-battles/
├── pyproject.toml          # workspace + tooling config
├── Makefile                # local dev targets
├── scripts/ci.py           # make-less CI runner
├── .github/workflows/ci.yml
│
├── packages/
│   ├── core/    # pokecore: type chart, teams, formats, elo
│   ├── engine/  # pokeengine: poke-env wrapper, parser, runner, demo
│   ├── llm/     # pokellm: prompts, tools, memory, agents
│   └── api/     # pokeapi: FastAPI, DB, orchestrator
│
├── pokecli/    # CLI client (separate workspace package)
│
├── showdown/   # Dockerfile for the Showdown server image
├── showdown-client/  # (optional) smogon web client
│
├── web/        # (skeleton) static frontend
│
├── deploy/
│   ├── docker-compose.yml  # OCI / local Docker stack
│   └── oci/install.sh      # systemd-based installer
│
└── tests/      # cross-package integration tests (Phase 4+)
```

## License

MIT
